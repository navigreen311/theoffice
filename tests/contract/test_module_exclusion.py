"""A module that must never be granted, enforced where it cannot be forgotten.

The point of these tests is that the guard holds against a writer who does not know
it exists. `generators/runtime_config.py` and `broker/bootstrap_phase0.py` both INSERT
grants, and a future third writer will not consult a Python constant. So the assertion
that matters is the one made against a raw INSERT.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import db
from broker.errors import ModuleExcluded, UnknownForge
from broker.grants import resolve_grant
from client.office_client import AgentContext
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


@pytest.fixture(autouse=True)
def _declared_in_manifest(request):
    """Same reason as test_call_path.py: the manifest gate is not what these test.

    It matters here for exactly one test - the one that makes a real call before the
    exclusion exists. The others are refused at grant resolution, which is upstream of
    the manifest, so they would pass whether or not this ran. Declaring for all of them
    keeps that difference from looking like significance.
    """
    if "granted_agent" in request.fixturenames:
        request.getfixturevalue("declare_module")(required=True)


def _exclude(admin: psycopg.Connection, forge_id: str, module_id: str) -> None:
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_module_exclusion
                   (forge_id, module_id, reason, evidence, recorded_by)
            VALUES (%s, %s, 'stubbed: answers without doing the work',
                    'tests/contract/test_module_exclusion.py', 'test')
            """,
            (forge_id, module_id),
        )
    admin.commit()


def _insert_grant(
    conn: psycopg.Connection, agent_id: uuid.UUID, forge_id: str, module_id: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id,
               trust_tier, operation_cert_ref, dept_context_cert_ref, granted_by,
               activated_at)
            VALUES (%s, %s, %s, %s, 'burkham-wickmont', 'auto_execute',
                    'simforge://unitA/x/1.0.0', 'simforge://unitB/finance/1.0.0',
                    %s, now())
            """,
            (str(uuid.uuid4()), agent_id, forge_id, module_id, str(uuid.uuid4())),
        )


def test_a_grant_for_an_excluded_module_is_refused_by_the_database(
    admin: psycopg.Connection, seed_agent: uuid.UUID, registered_forge: tuple[str, str]
) -> None:
    """The guard is a trigger, so it holds for a writer that never heard of it."""
    forge_id, module_id = registered_forge
    _exclude(admin, forge_id, module_id)

    with pytest.raises(psycopg.errors.IntegrityConstraintViolation) as exc:
        _insert_grant(admin, seed_agent, forge_id, module_id)
    admin.rollback()

    # The reason travels with the refusal. A constraint that only says "no" sends the
    # reader to the schema to find out what they did.
    assert "answers without doing the work" in str(exc.value)
    assert module_id in str(exc.value)


def test_an_existing_grant_for_an_excluded_module_can_still_be_revoked(
    admin: psycopg.Connection, seed_agent: uuid.UUID, registered_forge: tuple[str, str]
) -> None:
    """The trigger is BEFORE INSERT only, deliberately.

    Excluding a module whose grant is already out there must not make that grant
    unrevokable - that would leave the dangerous case permanently in place, which is
    the exact opposite of the intent.
    """
    forge_id, module_id = registered_forge
    _insert_grant(admin, seed_agent, forge_id, module_id)
    admin.commit()

    _exclude(admin, forge_id, module_id)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET revoked_at = now() "
            "WHERE office_agent_id = %s AND forge_id = %s",
            (seed_agent, forge_id),
        )
        assert cur.rowcount == 1
    admin.commit()


async def test_a_grant_that_predates_the_exclusion_is_refused_at_call_time(
    office, stub_forge, agent_ctx: AgentContext, granted_agent, admin: psycopg.Connection
) -> None:
    """Defense in depth: the trigger cannot reach a row written before it applied."""
    _, forge_id, module_id = granted_agent

    await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert stub_forge.call_count == 1

    _exclude(admin, forge_id, module_id)

    with pytest.raises(ModuleExcluded) as exc:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)

    assert str(exc.value.context["exclusion_reason"]).startswith("stubbed")
    # The Forge was never touched. A module excluded for answering without doing the
    # work must not be reached at all.
    assert stub_forge.call_count == 1


async def test_exclusion_outranks_a_suspended_identity(
    office, stub_forge, agent_ctx: AgentContext, granted_agent, admin: psycopg.Connection
) -> None:
    """Two things are wrong; the one that is true of every agent is reported."""
    _, forge_id, module_id = granted_agent
    _exclude(admin, forge_id, module_id)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_agent_identity SET status = 'suspended' WHERE office_agent_id = %s",
            (agent_ctx.office_agent_id,),
        )
    admin.commit()

    with pytest.raises(ModuleExcluded):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert stub_forge.call_count == 0


async def test_an_unregistered_excluded_module_reports_the_exclusion_not_unknown(
    admin: psycopg.Connection, seed_agent: uuid.UUID
) -> None:
    """The normal case for an exclusion: no registry row, and never will be.

    Without this, the modules CapitalForge must never expose report as merely
    'not registered' - which reads as an onboarding gap somebody should close,
    rather than a decision somebody made.
    """
    forge_id = f"unregistered-{uuid.uuid4().hex[:8]}"
    _exclude(admin, forge_id, "voice_call_initiate")

    try:
        async with db.connection() as conn:
            with pytest.raises(ModuleExcluded) as exc:
                await resolve_grant(
                    conn,
                    office_agent_id=seed_agent,
                    forge_id=forge_id,
                    module_id="voice_call_initiate",
                    venture_id="burkham-wickmont",
                )
            assert exc.value.context["exclusion_reason"]

            # An unexcluded, unregistered module still reports as unknown. The two
            # answers must stay distinguishable, or the exclusion tells nobody anything.
            with pytest.raises(UnknownForge):
                await resolve_grant(
                    conn,
                    office_agent_id=seed_agent,
                    forge_id=forge_id,
                    module_id="something_else",
                    venture_id="burkham-wickmont",
                )
    finally:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM forge_module_exclusion WHERE forge_id = %s", (forge_id,))
        admin.commit()


def test_the_declared_exclusions_apply_and_re_apply_unchanged(
    admin: psycopg.Connection,
) -> None:
    """The seeder is the automation artifact; this is the assertion that it works.

    Applied twice, because an exclusion table that drifts on a second run would be a
    table nobody could safely re-seed - and re-seeding is how a new checkout gets the
    guard at all.
    """
    from broker.module_exclusions import ALL
    from scripts.apply_module_exclusions import apply, check

    try:
        inserted, updated = apply(admin)
        admin.commit()
        assert inserted + updated == len(ALL)
        assert check(admin) == []

        first_recorded = admin.execute(
            "SELECT recorded_at FROM forge_module_exclusion "
            "WHERE forge_id = 'capitalforge' AND module_id = 'voice_call_initiate'"
        ).fetchone()[0]

        again_inserted, again_updated = apply(admin)
        admin.commit()
        assert again_inserted == 0
        assert again_updated == len(ALL)
        assert check(admin) == []

        # `recorded_at` is when the finding was made, not when the script last ran.
        second_recorded = admin.execute(
            "SELECT recorded_at FROM forge_module_exclusion "
            "WHERE forge_id = 'capitalforge' AND module_id = 'voice_call_initiate'"
        ).fetchone()[0]
        assert first_recorded == second_recorded
    finally:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM forge_module_exclusion WHERE forge_id = 'capitalforge'")
        admin.commit()
