"""Phase 3.3 acceptance — the temporal PHI wall.

Master prompt Part 8: "MedLink's PHI must never reach Collingswood's FunnelForge CDP —
and the same agent may serve both across consecutive shifts."

That is the scenario every test here is built around: **one agent, two ventures, two
consecutive shifts.** Testing the flush on an agent that only ever serves one venture
would pass without proving anything, because there is no boundary to cross.

The control being tested is not "the flush runs". It is "**a failed flush blocks the
next assignment**" — Part 8 says blocks, "rather than logging and continuing", and the
difference between those two is the entire wall.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from broker import shifts
from broker.db import connection
from broker.shifts import FlushFailed, ShiftBlocked
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

OPERATOR = uuid.uuid4()
MEDLINK = "medlink-pro"
COLLINGSWOOD = "collingswood"


def window(offset_hours: int, length_hours: int = 8) -> tuple[datetime, datetime]:
    start = datetime.now(UTC) + timedelta(hours=offset_hours)
    return start, start + timedelta(hours=length_hours)


@pytest.fixture
async def agent_on_medlink(seed_agent, admin: psycopg.Connection):
    """An agent mid-shift on MedLink, with PHI and non-PHI working memory.

    The non-PHI rows matter: a flush that deletes everything would pass a test that
    only checks PHI is gone, while destroying the venture's own working state.
    """
    start, end = window(-1)
    async with connection() as conn:
        shift_id = await shifts.assign_shift(
            conn, office_agent_id=seed_agent, venture_id=MEDLINK,
            shift_start=start, shift_end=end, assigned_by=OPERATOR,
        )
        for classification, ref in (
            ("phi", "medlink://patient/1001"),
            ("phi", "medlink://patient/1002"),
            ("recording", "voiceforge://call/77"),
            ("internal", "medlink://roster-note"),
            ("public", "medlink://facility-list"),
        ):
            await shifts.record_memory(
                conn, office_agent_id=seed_agent, venture_id=MEDLINK,
                data_classification=classification, content_ref=ref, shift_id=shift_id,
            )
    return seed_agent, shift_id


async def phi_rows(conn, agent_id) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM agent_working_memory "
            "WHERE office_agent_id = %s AND data_classification IN ('phi','recording')",
            (agent_id,),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


# ------------------------------------------------------------- tagged at write

async def test_memory_cannot_be_written_without_a_classification(seed_agent):
    """S1 — Part 8: tagged at write time, never inferred at flush time.

    Inferring at flush means scanning content with a heuristic, and a heuristic that
    misses once has leaked PHI across a venture boundary permanently.
    """
    async with connection() as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error):
            await cur.execute(
                "INSERT INTO agent_working_memory "
                "(memory_id, office_agent_id, venture_id, content_ref) "
                "VALUES (%s, %s, %s, %s)",
                (str(uuid.uuid4()), seed_agent, MEDLINK, "x://y"),
            )


async def test_an_unknown_classification_is_rejected(seed_agent):
    async with connection() as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.Error):
            await cur.execute(
                "INSERT INTO agent_working_memory (memory_id, office_agent_id, "
                "venture_id, data_classification, content_ref) VALUES (%s,%s,%s,%s,%s)",
                (str(uuid.uuid4()), seed_agent, MEDLINK, "probably_fine", "x://y"),
            )


# ------------------------------------------------------------------- the flush

async def test_flush_removes_phi_and_leaves_everything_else(agent_on_medlink):
    """S2 — a flush that deletes everything would pass a PHI-only assertion while
    destroying the venture's own working state."""
    agent_id, shift_id = agent_on_medlink

    async with connection() as conn:
        result = await shifts.flush_phi(
            conn, office_agent_id=agent_id, shift_id=shift_id
        )
        assert await phi_rows(conn, agent_id) == 0

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT data_classification FROM agent_working_memory "
                "WHERE office_agent_id = %s ORDER BY data_classification",
                (agent_id,),
            )
            remaining = [r[0] for r in await cur.fetchall()]

    assert remaining == ["internal", "public"]
    assert result.verified is True
    assert result.before == {"internal": 1, "phi": 2, "public": 1, "recording": 1}
    assert result.after == {"internal": 1, "public": 1}


async def test_flush_records_checkable_evidence(agent_on_medlink, admin):
    """S3 — "flush verified" means a third party can check it.

    A boolean saying the flush succeeded is a claim. A count before and a count of
    zero after is evidence.
    """
    agent_id, shift_id = agent_on_medlink
    async with connection() as conn:
        await shifts.flush_phi(conn, office_agent_id=agent_id, shift_id=shift_id)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT flush_verified, flush_attempted_at, flush_completed_at, flush_evidence "
            "FROM shift_assignment WHERE shift_id = %s",
            (shift_id,),
        )
        row = cur.fetchone()

    assert row is not None
    verified, attempted, completed, evidence = row
    assert verified is True
    assert attempted is not None and completed is not None
    assert evidence["before"]["phi"] == 2
    assert "phi" not in evidence["after"]
    assert evidence["verified"] is True


async def test_a_surviving_phi_row_fails_the_flush_and_leaves_it_unverified(
    agent_on_medlink, admin, monkeypatch
):
    """S6 — attempted is not verified.

    Simulated by making the delete a no-op: the operation completes and the outcome
    is wrong, which is exactly the case that must block rather than retry.
    """
    agent_id, shift_id = agent_on_medlink
    original = shifts._classification_counts

    async def unchanged(conn, office_agent_id):
        # Report PHI still present after the delete, as a partial failure would.
        counts = await original(conn, office_agent_id)
        counts.setdefault("phi", 1)
        counts["phi"] = max(counts.get("phi", 0), 1)
        return counts

    monkeypatch.setattr(shifts, "_classification_counts", unchanged)

    async with connection() as conn:
        with pytest.raises(FlushFailed) as exc:
            await shifts.flush_phi(conn, office_agent_id=agent_id, shift_id=shift_id)

    assert exc.value.context["remaining"]["phi"] >= 1

    with admin.cursor() as cur:
        cur.execute(
            "SELECT flush_attempted_at IS NOT NULL, flush_verified "
            "FROM shift_assignment WHERE shift_id = %s", (shift_id,)
        )
        row = cur.fetchone()
    assert row == (True, False), "attempted must be recorded, verified must not"


async def test_the_flush_is_audited(agent_on_medlink, admin):
    """S8."""
    agent_id, shift_id = agent_on_medlink
    async with connection() as conn:
        await shifts.flush_phi(conn, office_agent_id=agent_id, shift_id=shift_id)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log "
            "WHERE event_type = 'shift_phi_flush' AND actor_id = %s", (agent_id,)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 1


async def test_flush_runs_for_a_revoked_agent(agent_on_medlink, admin):
    """S7 — Part 8: "this is a control, not a competence claim."

    Tying the flush to standing would mean the agents most likely to have made a mess
    are the ones least likely to clean it up.
    """
    agent_id, shift_id = agent_on_medlink
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_agent_identity SET status = 'revoked', revoked_at = now(), "
            "revoked_by = %s, revocation_reason = 'test' WHERE office_agent_id = %s",
            (str(OPERATOR), agent_id),
        )
    admin.commit()

    async with connection() as conn:
        result = await shifts.flush_phi(
            conn, office_agent_id=agent_id, shift_id=shift_id
        )
        assert result.verified is True
        assert await phi_rows(conn, agent_id) == 0


# --------------------------------------------------- the block, which is the wall

async def test_an_unflushed_previous_shift_blocks_the_next_assignment(
    seed_agent, admin
):
    """S5 — THE control. Part 8: blocks, "rather than logging and continuing".

    One agent, MedLink then Collingswood. Without the block, PHI-tagged memory from
    the first shift is still present when the second begins.
    """
    start, end = window(-10, 8)
    async with connection() as conn:
        await shifts.assign_shift(
            conn, office_agent_id=seed_agent, venture_id=MEDLINK,
            shift_start=start, shift_end=end, assigned_by=OPERATOR,
        )
        await shifts.record_memory(
            conn, office_agent_id=seed_agent, venture_id=MEDLINK,
            data_classification="phi", content_ref="medlink://patient/9",
        )

        next_start, next_end = window(1)
        with pytest.raises(ShiftBlocked) as exc:
            await shifts.assign_shift(
                conn, office_agent_id=seed_agent, venture_id=COLLINGSWOOD,
                shift_start=next_start, shift_end=next_end, assigned_by=OPERATOR,
            )

    assert exc.value.context["previous_venture"] == MEDLINK
    assert exc.value.context["flush_verified"] is False


async def test_a_verified_flush_permits_the_next_assignment(seed_agent):
    """S4 — the wall lets a clean agent through, or it is just an outage."""
    start, end = window(-10, 8)
    async with connection() as conn:
        first = await shifts.assign_shift(
            conn, office_agent_id=seed_agent, venture_id=MEDLINK,
            shift_start=start, shift_end=end, assigned_by=OPERATOR,
        )
        await shifts.record_memory(
            conn, office_agent_id=seed_agent, venture_id=MEDLINK,
            data_classification="phi", content_ref="medlink://patient/9",
        )
        await shifts.flush_phi(conn, office_agent_id=seed_agent, shift_id=first)

        next_start, next_end = window(1)
        second = await shifts.assign_shift(
            conn, office_agent_id=seed_agent, venture_id=COLLINGSWOOD,
            shift_start=next_start, shift_end=next_end, assigned_by=OPERATOR,
        )
    assert second != first


async def test_a_non_phi_venture_is_not_exempt(seed_agent):
    """S13 — Part 7.5: uniform, "including non-PHI ventures".

    "A single uniform rule is enforceable where a conditional one is not" - and the
    condition is where the bug lives.
    """
    start, end = window(-10, 8)
    async with connection() as conn:
        await shifts.assign_shift(
            conn, office_agent_id=seed_agent, venture_id="greenstone",
            shift_start=start, shift_end=end, assigned_by=OPERATOR,
        )
        # Greenstone handles no PHI, so nothing is tagged phi. The rule still applies:
        # the previous shift has no verified flush.
        next_start, next_end = window(1)
        with pytest.raises(ShiftBlocked):
            await shifts.assign_shift(
                conn, office_agent_id=seed_agent, venture_id=COLLINGSWOOD,
                shift_start=next_start, shift_end=next_end, assigned_by=OPERATOR,
            )


# ------------------------------------------------------------------- the boundary

async def test_rotate_performs_the_four_steps_in_order(agent_on_medlink, admin):
    """S12 — Part 7.5: flush + verify -> re-resolve grants -> switch -> audit."""
    agent_id, shift_id = agent_on_medlink

    async with connection() as conn:
        # End the current shift so the next one does not overlap.
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE shift_assignment SET shift_end = now() - interval '1 minute' "
                "WHERE shift_id = %s", (shift_id,)
            )
        await conn.commit()

        start, end = window(1)
        new_shift = await shifts.rotate(
            conn, office_agent_id=agent_id, from_shift_id=shift_id,
            to_venture_id=COLLINGSWOOD, shift_start=start, shift_end=end,
            assigned_by=OPERATOR,
        )
        assert await phi_rows(conn, agent_id) == 0

    with admin.cursor() as cur:
        cur.execute(
            "SELECT event_type FROM audit_log WHERE actor_id IN (%s, %s) "
            "ORDER BY audit_id", (agent_id, str(OPERATOR))
        )
        events = [r[0] for r in cur.fetchall()]
        cur.execute(
            "SELECT subject->'order' FROM audit_log "
            "WHERE event_type = 'shift_boundary_completed'"
        )
        order_row = cur.fetchone()

    assert "shift_phi_flush" in events
    assert "shift_assigned" in events
    assert "shift_boundary_completed" in events
    assert events.index("shift_phi_flush") < events.index("shift_boundary_completed"), (
        "the flush must be audited before the boundary it enabled"
    )
    assert order_row is not None
    assert order_row[0] == [
        "flush", "verify", "resolve_grants", "switch_context", "audit"
    ]
    assert new_shift is not None


async def test_rotate_stops_at_a_failed_flush_and_creates_no_new_shift(
    agent_on_medlink, admin, monkeypatch
):
    """A failed flush must have nothing to switch into. Verify before switch."""
    agent_id, shift_id = agent_on_medlink

    async def still_dirty(conn, office_agent_id):
        return {"phi": 1}

    monkeypatch.setattr(shifts, "_classification_counts", still_dirty)

    async with connection() as conn:
        start, end = window(1)
        with pytest.raises(FlushFailed):
            await shifts.rotate(
                conn, office_agent_id=agent_id, from_shift_id=shift_id,
                to_venture_id=COLLINGSWOOD, shift_start=start, shift_end=end,
                assigned_by=OPERATOR,
            )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM shift_assignment "
            "WHERE office_agent_id = %s AND venture_id = %s", (agent_id, COLLINGSWOOD)
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0, "a failed flush must create no new shift"


# -------------------------------------------------------- uninterruptible

def test_the_client_library_exposes_no_way_to_skip_a_boundary():
    """S11 — Part 8: "agent-uninterruptible".

    An agent's only path to anything is OfficeClient. If the library grew a flush,
    skip or defer, an agent could reach it - so the absence is asserted rather than
    assumed.
    """
    from client.office_client import OfficeClient

    surface = {name for name in dir(OfficeClient) if not name.startswith("_")}
    forbidden = {"flush", "skip_flush", "defer_flush", "rotate", "end_shift",
                 "assign_shift", "clear_memory", "set_shift"}
    assert not (surface & forbidden), (
        f"OfficeClient exposes boundary controls to agents: {surface & forbidden}"
    )
    assert surface == {"call", "aclose"}, (
        f"OfficeClient surface changed: {surface}. Anything added here is reachable "
        "by an agent - confirm it cannot affect a shift boundary."
    )
