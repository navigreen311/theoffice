"""A grant may be retired by a named human, with a reason and an audit event.

RULED 23 SEPTEMBER 2026 (decisions entry 182)
=============================================

    *"A grant may be retired by a named human, with a reason and an audit event. Sets
    superseded_at; never a guess and never automatic. Measured: superseded_at has one
    writer, which retires only bootstrap grants a ladder grant replaced, so a revoked
    origin='unknown' grant cannot be retired at all."*

THE THREE VERBS, ONE TABLE, A KEYSTROKE APART
=============================================

    revoke      the authority was WRONG. Its own table, consulted on every call.
    deactivate  the grant has not passed Gate 11 yet. `activated_at` only.
    retire      the grant is FINISHED. Not the row that answers any more, and nothing
                is claimed about whether it should have existed.

    `test_retiring_is_not_revoking_and_not_deactivating` is the one that keeps them
    apart.
"""

from __future__ import annotations

import uuid

import pytest

from broker import account_origin, grants, humans
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

FORGE = "probe-forge"
VENTURE = "greenstone"


@pytest.fixture(autouse=True)
async def _clean_probe_rows():
    yield
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM agent_forge_grant WHERE forge_id LIKE 'probe-forge%'")
            await cur.execute(
                "DELETE FROM office_agent_identity WHERE department LIKE 'probe-%'")
            await cur.execute(
                "DELETE FROM forge_module_registry WHERE forge_id LIKE 'probe-forge%'")
            await cur.execute(
                "DELETE FROM forge_registry WHERE forge_id LIKE 'probe-forge%'")
            # THE OPERATORS STAY. The app role holds no DELETE on `office_human_role`,
            # and the other contract suites leave theirs too. They are inert:
            # `venture_operator`, so no administrator count moves, and each has a unique
            # `@retire.test` address. The rows that actually pollute a count - grants and
            # identities - are the four above, and one of them already caught a leak.
        await conn.commit()


async def _forge(conn, *modules: str) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO forge_registry (forge_id, display_name, base_url, "
            "  api_version, auth_model, credential_mode, health_status) "
            "VALUES (%s, %s, 'http://probe.invalid', '1.0.0', 'bearer', "
            "        'brokered', 'GREEN') ON CONFLICT DO NOTHING",
            (FORGE, FORGE))
        for module_id in modules:
            await cur.execute(
                "INSERT INTO forge_module_registry (forge_id, module_id, module_name, "
                "  idempotency_support, is_mutating) "
                "VALUES (%s, %s, %s, 'natural', false) ON CONFLICT DO NOTHING",
                (FORGE, module_id, module_id))


async def _grant(conn, *, module_id: str, venture_id: str = VENTURE) -> uuid.UUID:
    agent_id, grant_id = uuid.uuid4(), uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_agent_identity (office_agent_id, agent_name, "
            "  village_agent_ref, department, status) "
            "VALUES (%s, %s, %s, %s, 'active')",
            (agent_id, f"Probe {str(agent_id)[:8]}", f"probe_{str(agent_id)[:8]}",
             f"probe-{uuid.uuid4().hex[:8]}"))
        await cur.execute(
            "INSERT INTO agent_forge_grant (grant_id, office_agent_id, forge_id, "
            "  module_id, venture_id, granted_by, origin, activated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'unknown', now())",
            (grant_id, agent_id, FORGE, module_id, venture_id, uuid.uuid4()))
    return grant_id


async def _row(conn, grant_id):
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT superseded_at, activated_at, is_assignable "
            "  FROM agent_forge_grant WHERE grant_id = %s", (grant_id,))
        return await cur.fetchone()


async def _operator(conn, *, origin: str = account_origin.HUMAN):
    """A venture_operator of a DECLARED origin.

    `retire` calls `assert_named_human`, so a `test_fixture` account is refused - entry
    148's rule, and `test_a_fixture_cannot_retire_a_grant` is the half that pins it.
    """
    human_id, _token = await humans.create_human(
        conn, origin=origin,
        display_name=f"Op {uuid.uuid4().hex[:6]}",
        email=f"op-{uuid.uuid4().hex[:8]}@retire.test",
    )
    await humans.grant_role(
        conn, human_id=human_id, role="venture_operator", venture_id=VENTURE,
        granted_by=human_id,
    )
    return await humans.get_human(conn, human_id)


# ======================================================== the ruling

async def test_a_named_human_retires_a_grant_with_a_reason():
    """**THE RULING.** `superseded_at` is set, and nothing else about the row moves."""
    async with connection() as conn:
        await _forge(conn, "alpha")
        grant = await _grant(conn, module_id="alpha")
        await conn.commit()

        before = await _row(conn, grant)
        assert before[0] is None and before[1] is not None

        retired = await grants.retire(
            conn, grant_ids=[grant], human=await _operator(conn),
            reason="no position draws from this department")

        after = await _row(conn, grant)
        assert after[0] is not None, "superseded_at was not set"
        assert after[1] == before[1], "activated_at moved; retiring is not deactivating"
        assert after[2] is False, "a retired grant is not assignable"
        assert [r["grant_id"] for r in retired] == [str(grant)]


async def test_it_writes_an_audit_event_naming_every_grant():
    """"2 grants" is not something a reader can check. A list is."""
    async with connection() as conn:
        await _forge(conn, "alpha", "beta")
        a = await _grant(conn, module_id="alpha")
        b = await _grant(conn, module_id="beta")
        await conn.commit()

        await grants.retire(conn, grant_ids=[a, b], human=await _operator(conn),
                            reason="the reason on the record")

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT subject FROM audit_log WHERE event_type = 'grant_retired' "
                " ORDER BY audit_id DESC LIMIT 1")
            subject = (await cur.fetchone())[0]

    assert subject["reason"] == "the reason on the record"
    assert {g["grant_id"] for g in subject["grants"]} == {str(a), str(b)}
    for g in subject["grants"]:
        assert g["module"].startswith(f"{FORGE}/")
        assert g["origin"] == "unknown"


async def test_retiring_is_not_revoking_and_not_deactivating():
    """**The line this must not cross.** Three verbs, one table.

    Retiring writes no revocation row: nothing is claimed about whether the authority
    should have existed. And it leaves `activated_at` alone, which is what says the
    grant passed Gate 11 - a fact about its history, not about whether it still
    answers.
    """
    import inspect

    source = inspect.getsource(grants.retire)
    assert "INSERT INTO revocation" not in source
    assert "activated_at" not in source.split('"""')[-1], (
        "retire must not touch activated_at; that is deactivate's column")

    async with connection() as conn:
        await _forge(conn, "alpha")
        grant = await _grant(conn, module_id="alpha")
        await conn.commit()
        await grants.retire(conn, grant_ids=[grant], human=await _operator(conn),
                            reason="finished")
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM revocation WHERE reason = %s",
                              ("finished",))
            assert (await cur.fetchone())[0] == 0


# ======================================================== never a guess

async def test_it_takes_ids_and_never_a_predicate():
    """*"Never a guess."* A retirement that selects rows by a rule is the automatic
    path this exists beside. A caller that wants twenty rows names twenty."""
    import inspect

    sig = inspect.signature(grants.retire)
    assert "grant_ids" in sig.parameters
    for matcher in ("origin", "module_id", "forge_id", "where"):
        assert matcher not in sig.parameters


async def test_an_unknown_id_refuses_the_whole_call():
    """**Nothing partial.** A half-done retirement leaves the operator deciding which
    half happened."""
    async with connection() as conn:
        await _forge(conn, "alpha")
        real = await _grant(conn, module_id="alpha")
        await conn.commit()

        with pytest.raises(NotAuthorized) as caught:
            await grants.retire(
                conn, grant_ids=[real, uuid.uuid4()],
                human=await _operator(conn), reason="x")
        assert "Nothing was retired" in str(caught.value)
        assert (await _row(conn, real))[0] is None, "the real one was retired anyway"


async def test_an_already_retired_grant_refuses_rather_than_moving_the_date():
    """Re-retiring would overwrite the date the row actually stopped answering."""
    async with connection() as conn:
        await _forge(conn, "alpha")
        grant = await _grant(conn, module_id="alpha")
        await conn.commit()
        await grants.retire(conn, grant_ids=[grant], human=await _operator(conn),
                            reason="first")
        first = (await _row(conn, grant))[0]

        with pytest.raises(NotAuthorized) as caught:
            await grants.retire(conn, grant_ids=[grant],
                                human=await _operator(conn), reason="second")
        assert "already retired" in str(caught.value)
        assert (await _row(conn, grant))[0] == first


async def test_no_reason_and_no_ids_are_both_refused():
    async with connection() as conn:
        await _forge(conn, "alpha")
        grant = await _grant(conn, module_id="alpha")
        await conn.commit()
        human = await _operator(conn)

        with pytest.raises(NotAuthorized):
            await grants.retire(conn, grant_ids=[grant], human=human, reason="   ")
        with pytest.raises(NotAuthorized):
            await grants.retire(conn, grant_ids=[], human=human, reason="x")
        assert (await _row(conn, grant))[0] is None


# ======================================================== never automatic

def test_the_automatic_writer_is_untouched():
    """*"Never automatic."* The bootstrap retirement rule keeps its own narrowness.

    Its comment is the reason this function exists rather than a widening of it: *"An
    `unknown` row must not retire anything - nothing is retired on a guess."* That is
    right about a rule and says nothing about a judgement.
    """
    from pathlib import Path

    source = Path("generators/runtime_config.py").read_text(encoding="utf-8")
    assert "AND b.origin = 'bootstrap'" in source
    assert "AND l.origin          = 'ladder'" in source


def test_retire_is_the_only_other_writer_of_superseded_at():
    """If a third appears, it should be a decision rather than a discovery."""
    from pathlib import Path

    writers = []
    for path in Path("broker").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "UPDATE agent_forge_grant" in text and "SET superseded_at" in text:
            writers.append(path.name)
    assert writers == ["grants.py"], writers


async def test_a_fixture_cannot_retire_a_grant():
    """Entry 148: only a named human may decide. A fixture names nobody who can
    answer for a grant that stopped answering."""
    async with connection() as conn:
        await _forge(conn, "alpha")
        grant = await _grant(conn, module_id="alpha")
        fixture = await _operator(conn, origin=account_origin.TEST_FIXTURE)
        await conn.commit()

        with pytest.raises(NotAuthorized):
            await grants.retire(conn, grant_ids=[grant], human=fixture,
                                reason="by a fixture")
        assert (await _row(conn, grant))[0] is None


async def test_the_role_is_checked_in_every_venture_the_list_spans():
    """Checking the first would let one venture's operator retire another's."""
    async with connection() as conn:
        await _forge(conn, "alpha", "beta")
        mine = await _grant(conn, module_id="alpha", venture_id=VENTURE)
        theirs = await _grant(conn, module_id="beta", venture_id="burkham-wickmont")
        human = await _operator(conn)  # venture_operator on greenstone ONLY
        await conn.commit()

        with pytest.raises(NotAuthorized):
            await grants.retire(conn, grant_ids=[mine, theirs], human=human,
                                reason="across two ventures")
        assert (await _row(conn, mine))[0] is None, "the authorized one went anyway"
