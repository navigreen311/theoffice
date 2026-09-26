"""The Village's shift calendar, diffed against The Office. Entry 197.

The asymmetry with `sync-roster` is what these assert. That command applies in both
directions because both sides name one entity. This one ends shifts and assigns nobody,
because the Village's feed carries no venture and entry 197 rules that the venture comes
from a deliberate assignment rather than from a department.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from broker import sync_shifts, village
from broker.db import connection
from tests.conftest import requires_db
from tests.provisioning.conftest import VENTURE

pytestmark = [requires_db, pytest.mark.db]

IVAN = uuid.UUID("78869b20-e83a-4fbc-90bc-d58560f79bfb")


def _answer(phase: str, departments: dict) -> village.Answer:
    return village.Answer(
        data={"current_phase": phase, "departments": departments},
        fetched_at=datetime.now(UTC),
    )


@pytest.fixture
def village_says(monkeypatch):
    """Stand in for the Village's calendar. `degrade=False` is asserted, not assumed."""
    calls: dict = {}

    def install(phase: str, departments: dict):
        async def fake(*, degrade: bool = True):
            calls["degrade"] = degrade
            return _answer(phase, departments)

        monkeypatch.setattr(village, "shifts", fake)
        return calls

    return install


@pytest.fixture
def at_quarter(monkeypatch):
    def install(quarter: str):
        async def fake():
            return quarter

        monkeypatch.setattr(sync_shifts.shifts, "current_quarter", fake)

    return install


# --------------------------------------------------------------- refusing to guess

async def test_a_silent_village_is_refused_rather_than_read_as_nobody_on_shift(
    monkeypatch, at_quarter
):
    """The hazard sharper than sync-roster's: ending every shift refuses every call."""
    at_quarter("2033Q3")

    async def unreachable(*, degrade: bool = True):
        raise village.VillageUnreachableError("connection refused")

    monkeypatch.setattr(village, "shifts", unreachable)

    async with connection() as conn:
        with pytest.raises(sync_shifts.SyncError) as exc:
            await sync_shifts.diff(conn)
    assert "nobody being on shift" in str(exc.value)


async def test_an_empty_calendar_is_refused(village_says, at_quarter):
    at_quarter("2033Q3")
    village_says("MORNING", {})

    async with connection() as conn:
        with pytest.raises(sync_shifts.SyncError) as exc:
            await sync_shifts.diff(conn)
    assert "Refusing to treat that as an empty calendar" in str(exc.value)


async def test_the_calendar_is_never_read_from_cache(village_says, at_quarter):
    """`degrade=False`, asserted. A cached answer is the whole hazard above."""
    at_quarter("2033Q3")
    calls = village_says("MORNING", {"Operations": {"shifts": {"MORNING": {"agents": []}}}})

    async with connection() as conn:
        await sync_shifts.diff(conn)
    assert calls["degrade"] is False


# --------------------------------------------------------------- the diff

async def test_an_agent_on_shift_with_no_assignment_is_reported_not_assigned(
    village_says, at_quarter, admin: psycopg.Connection, granted_agent
):
    """ENTRY 197'S POINT. The Village names no venture, so this command picks none."""
    agent_id, _, _ = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "SELECT village_agent_ref, department FROM office_agent_identity "
            " WHERE office_agent_id = %s",
            (agent_id,),
        )
        ref, dept = cur.fetchone()
    at_quarter("2033Q3")
    village_says("MORNING", {dept: {"shifts": {"MORNING": {"agents": [ref]}}}})

    async with connection() as conn:
        changes = await sync_shifts.diff(conn)

    unassigned = [c for c in changes.of("unassigned") if c.village_agent_ref == ref]
    assert len(unassigned) == 1
    assert "no assignment here" in unassigned[0].detail
    assert changes.of("to_end") == []


async def test_an_assignment_the_village_has_ended_is_reported_and_ended(
    village_says, at_quarter, admin: psycopg.Connection, granted_agent
):
    agent_id, _, _ = granted_agent
    now = datetime.now(UTC)
    with admin.cursor() as cur:
        cur.execute(
            "SELECT village_agent_ref, department FROM office_agent_identity "
            " WHERE office_agent_id = %s",
            (agent_id,),
        )
        ref, dept = cur.fetchone()
        cur.execute(
            "INSERT INTO shift_assignment "
            "  (shift_id, office_agent_id, venture_id, shift_start, shift_end, "
            "   assigned_by, quarter) "
            "VALUES (%s, %s, %s, %s, %s, %s, '2033Q3')",
            (uuid.uuid4(), agent_id, VENTURE, now - timedelta(hours=1),
             now + timedelta(hours=7), IVAN),
        )
    admin.commit()

    at_quarter("2033Q3")
    village_says("MORNING", {dept: {"shifts": {"MORNING": {"agents": []}}}})

    async with connection() as conn:
        changes = await sync_shifts.diff(conn)
        assert [c.village_agent_ref for c in changes.of("to_end")] == [ref]
        result = await sync_shifts.apply(conn, actor=IVAN, confirmed=True)

    assert result["ended"] == 1
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM shift_assignment "
            " WHERE office_agent_id = %s AND shift_end > now()",
            (agent_id,),
        )
        assert cur.fetchone()[0] == 0


async def test_a_stale_quarter_is_reported(
    village_says, at_quarter, admin: psycopg.Connection, granted_agent
):
    """The state the board is actually in: assignments say 2030Q3, the Village 2033Q3."""
    agent_id, _, _ = granted_agent
    now = datetime.now(UTC)
    with admin.cursor() as cur:
        cur.execute(
            "SELECT village_agent_ref, department FROM office_agent_identity "
            " WHERE office_agent_id = %s",
            (agent_id,),
        )
        ref, dept = cur.fetchone()
        cur.execute(
            "INSERT INTO shift_assignment "
            "  (shift_id, office_agent_id, venture_id, shift_start, shift_end, "
            "   assigned_by, quarter) "
            "VALUES (%s, %s, %s, %s, %s, %s, '2030Q3')",
            (uuid.uuid4(), agent_id, VENTURE, now - timedelta(hours=1),
             now + timedelta(hours=7), IVAN),
        )
    admin.commit()

    at_quarter("2033Q3")
    village_says("MORNING", {dept: {"shifts": {"MORNING": {"agents": [ref]}}}})

    async with connection() as conn:
        changes = await sync_shifts.diff(conn)

    stale = [c for c in changes.of("stale_quarter") if c.village_agent_ref == ref]
    assert len(stale) == 1
    assert "2030Q3" in stale[0].detail and "2033Q3" in stale[0].detail


async def test_apply_refuses_without_confirmation(village_says, at_quarter):
    at_quarter("2033Q3")
    village_says("MORNING", {"Operations": {"shifts": {"MORNING": {"agents": []}}}})

    async with connection() as conn:
        with pytest.raises(sync_shifts.SyncError) as exc:
            await sync_shifts.apply(conn, actor=IVAN)
    assert "--confirm" in str(exc.value)


async def test_apply_assigns_nobody(
    village_says, at_quarter, admin: psycopg.Connection, granted_agent
):
    """The half this command deliberately does not do. Entry 197."""
    agent_id, _, _ = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "SELECT village_agent_ref, department FROM office_agent_identity "
            " WHERE office_agent_id = %s",
            (agent_id,),
        )
        ref, dept = cur.fetchone()
    at_quarter("2033Q3")
    village_says("MORNING", {dept: {"shifts": {"MORNING": {"agents": [ref]}}}})

    async with connection() as conn:
        result = await sync_shifts.apply(conn, actor=IVAN, confirmed=True)

    assert result["ended"] == 0
    assert result["unassigned"] == 1
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM shift_assignment WHERE office_agent_id = %s",
            (agent_id,),
        )
        assert cur.fetchone()[0] == 0, "an unassigned agent stays unassigned"


async def test_the_audit_event_records_what_was_left_for_a_human(
    village_says, at_quarter, admin: psycopg.Connection, granted_agent
):
    """An event listing only the ended shifts would read as a full reconciliation."""
    agent_id, _, _ = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "SELECT village_agent_ref, department FROM office_agent_identity "
            " WHERE office_agent_id = %s",
            (agent_id,),
        )
        ref, dept = cur.fetchone()
    at_quarter("2033Q3")
    village_says("MORNING", {dept: {"shifts": {"MORNING": {"agents": [ref]}}}})

    async with connection() as conn:
        await sync_shifts.apply(conn, actor=IVAN, confirmed=True)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT subject FROM audit_log "
            " WHERE event_type = 'shift_calendar_reconciled' ORDER BY ts DESC LIMIT 1"
        )
        subject = cur.fetchone()[0]
    assert subject["left_for_a_human"]["unassigned"] == 1
    assert subject["ended"] == []
