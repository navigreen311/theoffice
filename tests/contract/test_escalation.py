"""Two escalation paths, and neither one is a name.

The failure being prevented is quiet. "Flag to Gardner" is a valid string on the day it
is written and a valid string on the day Gardner dies; nothing about it knows the
difference. The Village rolls for mortality and auto-hires into the vacated seat, so the
COO chair is refilled while every escalation still points at whoever used to sit in it.

That is the same shape as the department list this project already removed: a copy cannot
know the world moved.

The other half is the separation. A governance decision routed up the Village's chain of
command reaches the COO, who runs the organisation the decision is about. The Office
exists above the Village so that "can we staff this" is not answered by the party that
wants the answer to be yes.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import escalation, humans
from broker.db import connection
from broker.escalation import Path, SeatVacant, WrongPath

pytestmark = pytest.mark.asyncio

DEPARTMENT, TITLE = escalation.COO_POSITION


def _seat(conn: psycopg.Connection, ref: str, name: str, *, status: str = "active",
          title: str = TITLE, department: str = DEPARTMENT) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO village_agent (village_agent_ref, agent_name, department, "
            "title, role_key, status, source) "
            "VALUES (%s, %s, %s, %s, 'department_head', %s, 'import') "
            "ON CONFLICT (village_agent_ref) DO UPDATE SET "
            "  agent_name = EXCLUDED.agent_name, title = EXCLUDED.title, "
            "  department = EXCLUDED.department, status = EXCLUDED.status",
            (ref, name, department, title, status),
        )
    conn.commit()


@pytest.fixture
def village(admin: psycopg.Connection):
    refs = ["esc-coo-1", "esc-coo-2", "esc-cfo"]

    def clear() -> None:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM village_agent WHERE village_agent_ref = ANY(%s)",
                        (refs,))
        admin.commit()

    clear()
    yield admin
    clear()


@pytest.fixture
async def operator(admin: psycopg.Connection):
    """A real account, because the test database has none.

    Every account the suite creates is a fixture by construction, and
    `attributable_actor` excludes fixtures on purpose - so a governance route has
    nobody to go to unless a test says otherwise. Marked explicitly rather than by
    inventing an email the classifier happens not to recognise.
    """
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="Escalation operator", email="esc@x.escalation.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="ivan", venture_id=None, granted_by=human_id
        )
    with admin.cursor() as cur:
        # Suspend any other real account so this test does not depend on which one
        # `created_at` happens to favour.
        cur.execute(
            "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
            "suspended_by = human_id WHERE origin = 'human' AND human_id <> %s",
            (human_id,),
        )
        cur.execute(
            "UPDATE office_human SET origin = 'human' WHERE human_id = %s", (human_id,)
        )
    admin.commit()

    yield human_id

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET status = 'active', suspended_at = NULL, "
            "suspended_by = NULL WHERE origin = 'human'"
        )
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


# ============================================================ THE POSITION, NOT THE NAME

async def test_the_coo_is_resolved_from_the_roster(village):
    _seat(village, "esc-coo-1", "Gardner")

    async with connection() as conn:
        holder = await escalation.coo(conn)

    assert holder is not None
    assert holder.agent_name == "Gardner"
    assert holder.title == TITLE


async def test_a_new_occupant_inherits_the_escalation_path(village):
    """THE test. Gardner dies, the Village hires, escalations follow the seat.

    Nothing here mentions Gardner except as a value in the roster. If the path were
    written as a name, this test would pass while pointing at a departed agent - which
    is exactly what makes the failure hard to see.
    """
    _seat(village, "esc-coo-1", "Gardner")
    async with connection() as conn:
        before = await escalation.operational(conn, reason="shift cover")
    assert before.to == "Gardner"

    # A mortality roll, and the Village fills the seat.
    _seat(village, "esc-coo-1", "Gardner", status="departed")
    _seat(village, "esc-coo-2", "Wren Halloway")

    async with connection() as conn:
        after = await escalation.operational(conn, reason="shift cover")

    assert after.to == "Wren Halloway"
    assert after.position == f"{DEPARTMENT}/{TITLE}"
    # The route names the seat both times. That is what did not change.
    assert before.position == after.position


async def test_a_departed_holder_does_not_still_hold_the_seat(village):
    """Marked departed, not deleted - and a marked row must not resolve as the holder."""
    _seat(village, "esc-coo-1", "Gardner", status="departed")

    async with connection() as conn:
        assert await escalation.coo(conn) is None


async def test_a_vacant_seat_is_reported_not_rerouted(village):
    """No fallback holder. The next-ranking agent was not given this authority.

    A best-effort delivery here would hand one agent's authority to another quietly,
    which is a worse outcome than an escalation that visibly has nowhere to go.
    """
    _seat(village, "esc-cfo", "Adrian Belvar", title="CFO")

    with pytest.raises(SeatVacant) as exc:
        async with connection() as conn:
            await escalation.operational(conn, reason="shift cover")

    assert exc.value.context["position"] == f"{DEPARTMENT}/{TITLE}"
    # And it says what to do, because a seat the Village has already refilled looks
    # identical from here until somebody syncs.
    assert "sync-roster" in str(exc.value)


async def test_the_role_key_is_not_the_seat(village):
    """`department_head` is a ladder rung and twelve agents hold it.

    Resolving the COO by `role_key` would return whichever department head sorted first.
    The seat is the department plus the title.
    """
    _seat(village, "esc-cfo", "Adrian Belvar", title="CFO")
    _seat(village, "esc-coo-2", "A Head", department="research", title=TITLE)

    async with connection() as conn:
        assert await escalation.coo(conn) is None


# ============================================================ THE TWO PATHS DO NOT MEET

@pytest.mark.parametrize("kind", sorted(escalation.GOVERNANCE_ONLY))
async def test_no_governance_decision_may_be_settled_inside_the_village(kind):
    """Including by the COO. That is the whole reason The Office sits above it."""
    with pytest.raises(WrongPath):
        escalation.assert_path(kind, Path.OPERATIONAL)

    escalation.assert_path(kind, Path.GOVERNANCE)


async def test_an_operational_question_is_allowed_up_the_chain():
    """A guard that refuses everything is not a guard."""
    escalation.assert_path("shift_cover", Path.OPERATIONAL)


async def test_an_unrecognised_kind_is_not_silently_downgraded():
    """Open by default, and the comment in the module says why.

    A whitelist of operational kinds would let the next governance decision somebody
    adds route into the Village until they remembered to list it. This is the weaker
    guarantee, chosen knowingly, and asserted so the choice is visible.
    """
    escalation.assert_path("something_new", Path.OPERATIONAL)


async def test_a_capacity_shortfall_is_governance():
    """§7.3 in the master prompt is a decision about whether the Village has people.

    Asked and answered inside the Village, it is the organisation certifying its own
    capacity.
    """
    assert "capacity_shortfall" in escalation.GOVERNANCE_ONLY
    with pytest.raises(WrongPath):
        escalation.assert_path("capacity_shortfall", Path.OPERATIONAL)


async def test_a_governance_route_names_a_real_person(admin, operator):
    """It goes to a human, and `attributable_actor` decides which one.

    An escalation delivered to `smoke-1a2b3c4d` is not delivered. The rule is enforced
    in one place and this asserts the escalation path uses it rather than its own query.
    """
    async with connection() as conn:
        route = await escalation.governance(conn, reason="capacity shortfall")

    assert route.path is Path.GOVERNANCE
    assert route.human_id is not None
    assert route.holder is None, "a governance route has no agent in it"

    with admin.cursor() as cur:
        cur.execute(
            "SELECT origin FROM office_human WHERE human_id = %s", (route.human_id,)
        )
        assert cur.fetchone()[0] == "human"


async def test_a_governance_route_cannot_be_addressed_to_an_agent():
    """There is no parameter for it, which is the point.

    The mistake is not made by choosing the COO on purpose. It is made by passing
    through whatever recipient the caller already had in hand, so the function takes no
    recipient at all.
    """
    import inspect

    params = set(inspect.signature(escalation.governance).parameters) - {"conn"}
    assert params == {"reason"}


async def test_no_module_names_the_coo_by_name():
    """The constant is a position. A name anywhere near it is the bug coming back.

    Read as source rather than imported, because the failure is a hardcoded string and
    an import would only see the value it resolves to today.
    """
    import pathlib

    source = pathlib.Path("broker/escalation.py").read_text(encoding="utf-8")
    body = "\n".join(
        line for line in source.splitlines()
        if not line.strip().startswith("#")
    )
    # The docstring explains the rule using the name, which is prose. What must not
    # appear is the name in code.
    code = body.split('"""')
    executable = "".join(code[i] for i in range(0, len(code), 2))
    assert "Gardner" not in executable
    assert escalation.COO_POSITION == ("executive", "COO")


async def test_the_two_paths_produce_different_shapes(village, operator):
    """A reader of an audit entry can tell which route a decision took."""
    _seat(village, "esc-coo-1", "Gardner")

    async with connection() as conn:
        op = (await escalation.operational(conn, reason="shift cover")).as_dict()
        gov = (await escalation.governance(conn, reason="capacity")).as_dict()

    assert op["path"] == "operational"
    assert op["position"] and op["holder_ref"] and op["human_id"] is None
    assert gov["path"] == "governance"
    assert gov["human_id"] and gov["position"] is None and gov["holder"] is None


async def test_a_governance_route_with_no_real_account_refuses(admin):
    """It stops rather than delivering to nobody, or to a fixture."""
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
            "suspended_by = human_id WHERE origin = 'human'"
        )
    admin.commit()
    try:
        with pytest.raises(humans.NoAttributableActorError):
            async with connection() as conn:
                await escalation.governance(conn, reason="capacity")
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "UPDATE office_human SET status = 'active', suspended_at = NULL, "
                "suspended_by = NULL WHERE origin = 'human'"
            )
        admin.commit()


async def test_position_holder_is_general_not_coo_shaped(village):
    """The COO is one caller of it. The Village has eleven other department heads."""
    _seat(village, "esc-cfo", "Adrian Belvar", title="CFO")

    async with connection() as conn:
        holder = await escalation.position_holder(conn, DEPARTMENT, "CFO")

    assert holder is not None and holder.agent_name == "Adrian Belvar"
    assert holder.present


async def test_a_route_survives_serialisation(village):
    """Routes go into audit subjects, which are JSON."""
    import json

    _seat(village, "esc-coo-1", "Gardner")
    async with connection() as conn:
        route = await escalation.operational(conn, reason="shift cover")

    assert json.loads(json.dumps(route.as_dict()))["holder"] == "Gardner"
    assert uuid.UUID  # imported for the type in Route; keep the reference honest
