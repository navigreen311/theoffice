"""B35 - Gate 7 asks the revocation table, not a column nothing writes.

Gate 7 counted `agent_forge_grant WHERE revoked_at IS NULL` and blocked the run if any
of those grants was activated. **Nothing in the broker writes that column.** The only
writers in the repository are two test fixtures; the single production
`UPDATE agent_forge_grant` sets `activated_at`. So the filter removed nothing, the count
included every grant ever issued, and `burkham-wickmont` - two grants activated by Phase
0's bootstrap, the record of the first real brokered call - blocked at Gate 7, one gate
past the furthest any run had reached.

Revocation here is a separate table, consulted per call, never cached: four scopes,
broadest wins, `broker/revocation.py`. That is what `client/office_client.py` asks before
every call, and now what this gate asks, through the same predicate.

**The load-bearing test in this file is the one asserting an active, unrevoked grant
still BLOCKS.** Every other test here asserts that something stops counting, and a gate
that counted nothing would pass all of them. Gate 7's demand did not move: grants are
issued inactive and activated only against a valid sign-off.

Everything runs through `provisioning.advance` rather than by calling `_gate_7` - a gate
tested through its own function is a gate tested somewhere the pipeline does not go.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
import pytest_asyncio

from broker import humans, provisioning, revocation
from broker.db import connection
from broker.errors import Revoked
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


# ------------------------------------------------------------------------ helpers

async def _run_to_gate_7(conn, operator) -> uuid.UUID:
    """A real run, driven to the point where Gate 5 has issued the grants."""
    run_id = await provisioning.start_run(
        conn, venture_id=VENTURE, started_by=operator.human_id
    )
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    await provisioning.record_human_review(
        conn, run_id=run_id, human=operator, note="reviewed the BOM and the gap report"
    )
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    return run_id


async def _recheck_gate_7(conn, run_id: uuid.UUID, operator):
    """Rewind to Gate 7 and re-run it through the pipeline. Returns its outcome.

    Rewinding is test-only and deliberately not a public operation, for the reason
    `test_pipeline._set_run_gate` gives: a production caller able to set the current
    gate could set it to 11 and skip certification entirely.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET status = 'running', current_gate = '7' "
            "WHERE run_id = %s", (run_id,),
        )
    await conn.commit()
    outcomes = await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    return next(o for o in outcomes if o.gate == "7")


def _activate_all(admin: psycopg.Connection, actor: uuid.UUID) -> None:
    """The state Phase 0's bootstrap left `burkham-wickmont` in: grants live."""
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET activated_at = now(), activated_by = %s "
            "WHERE venture_id = %s", (actor, VENTURE),
        )
    admin.commit()


def _grants(admin: psycopg.Connection) -> list[tuple]:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT grant_id, office_agent_id, forge_id, module_id "
            "FROM agent_forge_grant WHERE venture_id = %s ORDER BY granted_at",
            (VENTURE,),
        )
        return list(cur.fetchall())


async def _officer(name: str, email: str, role: str) -> humans.Human:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=email
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=VENTURE,
            granted_by=AUTHOR,
        )
        resolved = await humans.authenticate(conn, token)
    assert resolved is not None
    return resolved


@pytest.fixture(autouse=True)
def clear_revocations(world, admin: psycopg.Connection):
    """`wipe_venture` does not reach `revocation`, and `revocation.office_agent_id` is a
    foreign key onto the identities `teardown_world` deletes.

    So a revocation left behind here does not fail this test - it fails the *next* one,
    in a teardown, naming a constraint instead of a cause. The contract suite already
    clears this table for the same reason.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM revocation")
    admin.commit()
    yield
    with admin.cursor() as cur:
        cur.execute("DELETE FROM revocation")
    admin.commit()


@pytest_asyncio.fixture
async def compliance_officer(world) -> humans.Human:
    """Venture-scope revocation needs one; `operator` is only a venture_operator.

    Authority is checked in `assert_authority`, so a test that passed the role as a
    string while holding a weaker one would be testing a claim rather than a role.
    """
    return await _officer(
        "Cora Compliance", "cora.compliance@provisioning.invalid", "compliance_officer"
    )


@pytest_asyncio.fixture
async def ivan(world) -> humans.Human:
    """Forge scope is Ivan's alone - `SCOPE_MIN_ROLE` says so and `assert_authority`
    enforces it."""
    return await _officer("Ivan", "ivan@provisioning.invalid", "ivan")


# -------------------------------------------------- the gate did not widen

async def test_an_active_grant_with_no_revocation_still_blocks(
    feasible_pack, operator, admin: psycopg.Connection
):
    """**The test that proves this package did not ship a gate that passes.**

    Gate 7's rule is unchanged: grants are issued inactive and activated only against a
    valid Gate 10 signature. An activated grant with nothing revoking it is exactly the
    condition the gate exists to catch, and it still blocks.
    """
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)

    async with connection() as conn:
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.BLOCKED
    assert "already active before Gate 11" in gate_7.reason
    assert gate_7.evidence["already_active"] == len(_grants(admin)) > 0
    assert gate_7.evidence["active_but_revoked"] == 0
    assert gate_7.evidence["revocation_scopes"] == []


# ------------------------------------------------------ the four scopes, broadest wins

async def test_an_agent_module_revocation_stops_a_grant_counting(
    feasible_pack, operator, admin: psycopg.Connection
):
    """The narrowest scope: one grant, named by agent, Forge and module."""
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)
    rows = _grants(admin)
    assert rows, "the run must have issued grants for this to mean anything"

    async with connection() as conn:
        for _grant_id, agent_id, forge_id, module_id in rows:
            await revocation.revoke(
                conn, scope="agent_module", reason="B35 test: one module stopped",
                revoked_by=operator.human_id, revoked_by_role="venture_operator",
                office_agent_id=agent_id, forge_id=forge_id, module_id=module_id,
            )
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence["already_active"] == 0
    assert gate_7.evidence["active_but_revoked"] == len(rows)
    assert gate_7.evidence["revocation_scopes"] == ["agent_module"]


async def test_an_agent_scoped_revocation_stops_every_grant_that_agent_holds(
    feasible_pack, operator, admin: psycopg.Connection
):
    """One scope up: the agent cannot reach any Forge, so none of its grants count."""
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)
    rows = _grants(admin)
    agents = {row[1] for row in rows}

    async with connection() as conn:
        for agent_id in agents:
            await revocation.revoke(
                conn, scope="agent", reason="B35 test: agent stopped",
                revoked_by=operator.human_id, revoked_by_role="venture_operator",
                office_agent_id=agent_id,
            )
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence["already_active"] == 0
    assert gate_7.evidence["active_but_revoked"] == len(rows)
    assert gate_7.evidence["revocation_scopes"] == ["agent"]


async def test_a_venture_scoped_revocation_stops_the_whole_engagement(
    feasible_pack, operator, compliance_officer, admin: psycopg.Connection
):
    """One row, no agent named, and every grant for the engagement stops counting.

    This is the shape a column on the grant could never express, and the reason the
    header of `broker/revocation.py` refuses to store revocation there: a venture-scope
    stop also covers grants issued *after* it was declared.
    """
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)

    async with connection() as conn:
        await revocation.revoke(
            conn, scope="venture", reason="B35 test: engagement stopped",
            revoked_by=compliance_officer.human_id,
            revoked_by_role="compliance_officer", venture_id=VENTURE,
        )
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence["already_active"] == 0
    assert gate_7.evidence["active_but_revoked"] == len(_grants(admin))
    assert gate_7.evidence["revocation_scopes"] == ["venture"]


async def test_a_forge_scoped_revocation_stops_every_grant_against_that_forge(
    feasible_pack, operator, ivan, admin: psycopg.Connection
):
    """The widest scope, and the only one no grant column could ever hold: a Forge-wide
    stop is not a property of any single grant."""
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)
    rows = _grants(admin)
    forges = {row[2] for row in rows}

    async with connection() as conn:
        for forge_id in forges:
            await revocation.revoke(
                conn, scope="forge", reason="B35 test: Forge stopped",
                revoked_by=ivan.human_id, revoked_by_role="ivan", forge_id=forge_id,
            )
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence["already_active"] == 0
    assert gate_7.evidence["active_but_revoked"] == len(rows)
    assert gate_7.evidence["revocation_scopes"] == ["forge"]


async def test_the_broadest_scope_is_the_one_reported(
    feasible_pack, operator, compliance_officer, admin: psycopg.Connection
):
    """Two revocations over the same grant.

    The call path reports the broader one, because an agent stopped by a wide
    revocation needs a different response from one whose own grant was pulled. The gate
    reports the same, because it reads the same ordering rather than its own.
    """
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)
    rows = _grants(admin)

    async with connection() as conn:
        for _grant_id, agent_id, forge_id, module_id in rows:
            await revocation.revoke(
                conn, scope="agent_module", reason="the narrow one",
                revoked_by=operator.human_id, revoked_by_role="venture_operator",
                office_agent_id=agent_id, forge_id=forge_id, module_id=module_id,
            )
        await revocation.revoke(
            conn, scope="venture", reason="the broad one",
            revoked_by=compliance_officer.human_id,
            revoked_by_role="compliance_officer", venture_id=VENTURE,
        )
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence["revocation_scopes"] == ["venture"], (
        "broadest wins, as check_revocations has it"
    )


# ------------------------------------------------------------------ the round trip

async def test_reinstating_a_revocation_makes_the_grant_count_again(
    feasible_pack, operator, admin: psycopg.Connection
):
    """`reinstate()` exists, so this must round-trip.

    A kill switch with no off position is not a control, and the way that ships is by
    `reinstated_at IS NULL` being a term the caller has to remember to add. It is inside
    the shared predicate instead.
    """
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)
    rows = _grants(admin)

    async with connection() as conn:
        revocation_ids = []
        for _grant_id, agent_id, forge_id, module_id in rows:
            revocation_ids.append(
                await revocation.revoke(
                    conn, scope="agent_module", reason="B35 test: stopped",
                    revoked_by=operator.human_id, revoked_by_role="venture_operator",
                    office_agent_id=agent_id, forge_id=forge_id, module_id=module_id,
                )
            )
        stopped = await _recheck_gate_7(conn, run_id, operator)

        for revocation_id in revocation_ids:
            await revocation.reinstate(
                conn, revocation_id=revocation_id, reinstated_by=operator.human_id,
                reinstated_by_role="venture_operator",
                reason="B35 test: the stop is lifted",
            )
        resumed = await _recheck_gate_7(conn, run_id, operator)

    assert stopped.verdict == provisioning.PASSED
    assert stopped.evidence["already_active"] == 0
    assert resumed.verdict == provisioning.BLOCKED, (
        "a lifted revocation stops covering the grant, so Gate 7 sees it again"
    )
    assert resumed.evidence["already_active"] == len(rows)


# -------------------------------------------------------------- one source of truth

async def test_the_gate_and_the_call_path_agree_grant_for_grant(
    feasible_pack, operator, admin: psycopg.Connection
):
    """The binding assertion: the set Gate 7 discounts is exactly the set the call path
    refuses.

    This is the defect the project keeps recording - a second spelling of a rule that
    agrees with the first until it does not. `covered_grants` and `check_revocations`
    share one predicate, and this asserts the consequence rather than the sharing.
    """
    async with connection() as conn:
        await _run_to_gate_7(conn, operator)

    _activate_all(admin, operator.human_id)
    rows = _grants(admin)
    assert len(rows) >= 2, "this needs more than one grant to distinguish anything"

    async with connection() as conn:
        # One grant stopped narrowly; the rest left alone.
        _grant_id, agent_id, forge_id, module_id = rows[0]
        await revocation.revoke(
            conn, scope="agent_module", reason="B35 test: exactly one",
            revoked_by=operator.human_id, revoked_by_role="venture_operator",
            office_agent_id=agent_id, forge_id=forge_id, module_id=module_id,
        )

        covered = await revocation.covered_grants(conn, venture_id=VENTURE)

        refused = set()
        for grant_id, agent, forge, module in rows:
            try:
                await revocation.check_revocations(
                    conn, office_agent_id=agent, forge_id=forge,
                    module_id=module, venture_id=VENTURE,
                )
            except Revoked:
                refused.add(grant_id)

    assert refused, "the fixture must actually revoke something"
    assert set(covered) == refused
    assert len(refused) == 1


# ------------------------------------------------------------- the unchanged passes

async def test_gate_7_passes_when_the_venture_holds_no_grants_at_all(
    feasible_pack, operator, admin: psycopg.Connection
):
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)

    with admin.cursor() as cur:
        cur.execute("DELETE FROM agent_forge_grant WHERE venture_id = %s", (VENTURE,))
    admin.commit()

    async with connection() as conn:
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence == {
        "grants": 0, "already_active": 0, "revoked": 0,
        "active_but_revoked": 0, "revocation_scopes": [],
    }


async def test_gate_7_passes_on_grants_that_exist_and_are_inactive(
    feasible_pack, operator, admin: psycopg.Connection
):
    """The ordinary path: Gate 5 issued them, Gate 11 has not activated them."""
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    rows = _grants(admin)
    assert gate_7.verdict == provisioning.PASSED
    assert gate_7.evidence["grants"] == len(rows) > 0
    assert gate_7.evidence["already_active"] == 0
    assert gate_7.evidence["revoked"] == 0
