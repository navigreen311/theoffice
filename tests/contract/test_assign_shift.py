"""`python -m broker assign-shift` - a named operator, a real window, and a call that goes through.

Decisions entry 80: provisioning grants authority and nothing schedules it. A venture that
clears the ladder is authorised and not staffed. This command is the operator's half, and
the test that matters most here is not that a shift row appears - it is that **a brokered
call refused `OffShift` before the command succeeds after it**, with nothing else changed.

Everything else is a refusal, and every refusal must exit non-zero and write nothing.

These tests call the CLI function directly and never request `agent_ctx`: the autouse
`_on_shift_by_default` fixture would otherwise put the agent on shift before the command
under test ran, and every assertion here would be about that fixture's shift.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from broker import __main__ as cli
from broker import humans, village
from broker.db import connection
from broker.shifts import OffShift
from client.office_client import AgentContext
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

#: The venture `granted_agent` issues its grant for.
VENTURE = "burkham-wickmont"
SEED = uuid.uuid4()
QUARTER = "2026Q3"


@pytest.fixture(autouse=True)
def village_quarter(monkeypatch):
    """The Village quarter, under the test's control. These tests must not need a Village."""

    async def quarter() -> str:
        return QUARTER

    monkeypatch.setattr(village, "quarter", quarter)


@pytest.fixture
async def make_operator(admin: psycopg.Connection):
    """A real-origin account, with a role, removed afterwards."""
    made: list[uuid.UUID] = []

    async def _make(
        role: str | None, venture: str | None = VENTURE, domain: str = "staffing.test"
    ) -> tuple[str, uuid.UUID]:
        email = f"op-{uuid.uuid4().hex[:8]}@{domain}"
        async with connection() as conn:
            human_id, _ = await humans.create_human(
                conn, display_name=f"Operator {email[3:9]}", email=email
            )
            if role:
                await humans.grant_role(
                    conn, human_id=human_id, role=role, venture_id=venture, granted_by=SEED
                )
        made.append(human_id)
        return email, human_id

    yield _make

    with admin.cursor() as cur:
        for human_id in made:
            cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
            cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


def at(hours: float) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()


def shifts_of(admin: psycopg.Connection, agent_id: uuid.UUID) -> list[tuple[str, str, str]]:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT venture_id, assigned_by::text, quarter FROM shift_assignment "
            "WHERE office_agent_id = %s ORDER BY shift_start",
            (agent_id,),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


async def assign(
    agent_id: uuid.UUID, email: str, *, start: str = "now", end: str | None = None,
    confirm: bool = False,
) -> int:
    return await cli._assign_shift(
        VENTURE, str(agent_id), email, start, end or at(2), confirm
    )


# ------------------------------------------------------------------ the call goes through

async def test_one_agent_one_window_one_call(
    granted_agent, make_operator, admin, office, stub_forge, capsys
):
    """The smallest real test: refused off shift, assigned by an operator, then it works.

    Same agent, same grant, same module, same Forge. The only thing that changes between
    the refusal and the success is the command under test.
    """
    agent_id, forge_id, module_id = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO venture_forge_manifest "
            "(venture_id, forge_id, module_id, is_required, criticality) "
            "VALUES (%s, %s, %s, TRUE, 'soft')",
            (VENTURE, forge_id, module_id),
        )
    admin.commit()
    ctx = AgentContext(office_agent_id=agent_id, venture_id=VENTURE, task_id="t-staffed")

    with pytest.raises(OffShift):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=ctx)
    assert stub_forge.call_count == 0, "an off-shift agent must not reach the Forge"

    email, _ = await make_operator("venture_operator")
    assert await assign(agent_id, email, confirm=True) == 0, capsys.readouterr().out

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=ctx)
    assert result.status_code == 200
    assert stub_forge.call_count == 1


# ------------------------------------------------------------------ report and write

async def test_the_report_writes_nothing(granted_agent, make_operator, admin, capsys):
    agent_id, forge_id, module_id = granted_agent
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email) == 0
    out = capsys.readouterr().out
    assert "Nothing was written" in out
    assert f"{forge_id}/{module_id}" in out and "resolves" in out
    assert shifts_of(admin, agent_id) == []


async def test_confirm_writes_one_shift_signed_by_the_named_operator(
    granted_agent, make_operator, admin, capsys
):
    agent_id, _, _ = granted_agent
    email, operator_id = await make_operator("venture_operator")

    assert await assign(agent_id, email, confirm=True) == 0
    out = capsys.readouterr().out

    assert shifts_of(admin, agent_id) == [(VENTURE, str(operator_id), QUARTER)]
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE event_type = 'shift_assigned' "
            "AND actor_id = %s",
            (operator_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 1
    # Entry 81: the command says the window ends and nothing follows it.
    assert "goes off shift" in out and "entry 81" in out


async def test_a_stronger_role_with_no_venture_scope_may_staff(
    granted_agent, make_operator, admin
):
    """`ivan` held with no venture applies to every venture."""
    agent_id, _, _ = granted_agent
    email, _ = await make_operator("ivan", venture=None)
    assert await assign(agent_id, email, confirm=True) == 0
    assert len(shifts_of(admin, agent_id)) == 1


# ------------------------------------------------------------------ refusals

async def test_a_venture_with_no_active_grants_is_refused(
    granted_agent, make_operator, admin, capsys
):
    agent_id, _, _ = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET activated_at = NULL WHERE office_agent_id = %s",
            (agent_id,),
        )
    admin.commit()
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email, confirm=True) == 1
    out = capsys.readouterr().out
    assert "has no active grants" in out
    assert "Nothing was written" in out
    assert shifts_of(admin, agent_id) == []


async def test_a_revoked_grant_does_not_count_as_active(
    granted_agent, make_operator, admin, capsys
):
    """Gate 11's predicate: activated AND not covered by a live revocation."""
    agent_id, forge_id, module_id = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO revocation (revocation_id, scope, office_agent_id, forge_id, "
            "module_id, reason, revoked_by, revoked_by_role) "
            "VALUES (%s, 'agent_module', %s, %s, %s, 'test', %s, 'venture_operator')",
            (uuid.uuid4(), agent_id, forge_id, module_id, SEED),
        )
    admin.commit()
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email, confirm=True) == 1
    assert "has no active grants" in capsys.readouterr().out
    assert shifts_of(admin, agent_id) == []


async def test_an_agent_whose_grants_do_not_resolve_is_refused(
    granted_agent, make_operator, admin, capsys
):
    """The venture has an active grant; this agent's does not resolve. On shift it calls nothing."""
    agent_id, forge_id, _ = granted_agent
    with admin.cursor() as cur:
        cur.execute("DELETE FROM certification WHERE forge_id = %s", (forge_id,))
    admin.commit()
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email, confirm=True) == 1
    out = capsys.readouterr().out
    assert "none resolves" in out
    assert "NotCertified" in out
    assert "has no active grants" not in out
    assert shifts_of(admin, agent_id) == []


@pytest.mark.parametrize(
    ("role", "venture"),
    [(None, None), ("venture_operator", "greenstone")],
    ids=["no-role", "operator-of-another-venture"],
)
async def test_an_operator_without_the_role_for_this_venture_is_refused(
    granted_agent, make_operator, admin, capsys, role, venture
):
    agent_id, _, _ = granted_agent
    email, _ = await make_operator(role, venture=venture)

    assert await assign(agent_id, email, confirm=True) == 1
    assert f"may not staff {VENTURE}" in capsys.readouterr().out
    assert shifts_of(admin, agent_id) == []


async def test_a_test_fixture_cannot_put_an_agent_on_duty(
    granted_agent, make_operator, admin, capsys
):
    agent_id, _, _ = granted_agent
    email, _ = await make_operator("ivan", venture=None, domain="example.invalid")

    assert await assign(agent_id, email, confirm=True) == 1
    assert "test_fixture account" in capsys.readouterr().out
    assert shifts_of(admin, agent_id) == []


async def test_an_unknown_operator_is_refused(granted_agent, admin, capsys):
    agent_id, _, _ = granted_agent
    assert await assign(agent_id, "nobody@staffing.test", confirm=True) == 1
    assert "no account with email" in capsys.readouterr().out
    assert shifts_of(admin, agent_id) == []


@pytest.mark.parametrize(
    ("start", "end", "said"),
    [
        ("now", "2030-01-01T00:00:00", "no timezone"),
        ("now", "tomorrow", "not an ISO-8601 timestamp"),
        (at(3), at(2), "--end must be after --start"),
        (at(-3), at(-1), "before now"),
        (at(-1), at(2), "not written after the fact"),
    ],
    ids=["naive", "unparseable", "inverted", "already-over", "backdated"],
)
async def test_a_window_that_is_not_real_is_refused(
    granted_agent, make_operator, admin, capsys, start, end, said
):
    agent_id, _, _ = granted_agent
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email, start=start, end=end, confirm=True) == 1
    assert said in capsys.readouterr().out
    assert shifts_of(admin, agent_id) == []


async def test_an_overlap_is_named_rather_than_raised(
    granted_agent, make_operator, admin, capsys
):
    agent_id, _, _ = granted_agent
    email, _ = await make_operator("venture_operator")
    assert await assign(agent_id, email, end=at(4), confirm=True) == 0
    capsys.readouterr()

    assert await assign(agent_id, email, start=at(1), end=at(6), confirm=True) == 1
    assert "overlaps" in capsys.readouterr().out
    assert len(shifts_of(admin, agent_id)) == 1


async def test_back_to_back_windows_are_not_an_overlap(
    granted_agent, make_operator, admin
):
    """Entry 81: coverage is expressible. `tstzrange` is '[)', so end == next start is allowed."""
    agent_id, _, _ = granted_agent
    email, _ = await make_operator("venture_operator")
    boundary = at(2)
    assert await assign(agent_id, email, end=boundary, confirm=True) == 0
    assert await assign(agent_id, email, start=boundary, end=at(4), confirm=True) == 0
    assert len(shifts_of(admin, agent_id)) == 2


async def test_an_unflushed_previous_shift_blocks_the_next(
    granted_agent, make_operator, admin, capsys
):
    agent_id, _, _ = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO shift_assignment (shift_id, office_agent_id, venture_id, "
            "shift_start, shift_end, assigned_by, quarter) "
            "VALUES (%s, %s, %s, now() - interval '9 hours', now() - interval '1 hour', "
            "%s, %s)",
            (uuid.uuid4(), agent_id, VENTURE, SEED, QUARTER),
        )
    admin.commit()
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email, confirm=True) == 1
    assert "no verified PHI flush" in capsys.readouterr().out
    assert len(shifts_of(admin, agent_id)) == 1


async def test_a_village_that_cannot_say_the_quarter_refuses_and_writes_nothing(
    granted_agent, make_operator, admin, capsys, monkeypatch
):
    async def unreachable() -> str:
        raise village.VillageUnreachableError("connection refused")

    monkeypatch.setattr(village, "quarter", unreachable)
    agent_id, _, _ = granted_agent
    email, _ = await make_operator("venture_operator")

    assert await assign(agent_id, email, confirm=True) == 1
    out = capsys.readouterr().out
    assert "quarter:" in out and "Nothing was assigned" in out
    assert shifts_of(admin, agent_id) == []


async def test_an_unknown_agent_is_refused(make_operator, capsys):
    email, _ = await make_operator("venture_operator")
    code = await cli._assign_shift(VENTURE, "no-such-agent", email, "now", at(2), True)
    assert code == 1
    assert "no Office identity" in capsys.readouterr().out
