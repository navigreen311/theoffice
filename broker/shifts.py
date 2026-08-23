"""Shift assignment, and the verified PHI flush at the boundary.

Master prompt Part 7.5 and Part 8. **The PHI wall is temporal, not spatial.** One
Village, one agent, consecutive shifts on different ventures — so the wall runs at the
boundary rather than between two places.

The boundary is one operation in a fixed order, and every step's position matters:

    1. flush PHI-tagged working memory
    2. verify the flush — count, do not assert
    3. re-resolve grants for the incoming venture
    4. switch venture context (create the new assignment)
    5. write the audit entry

Flush before re-resolve, so the outgoing venture's data is gone before the incoming
venture's authority exists. Verify before switch, so a failed flush has nothing to
switch into. Audit last, because an audit written first records an intention rather than
an event.

**A failed flush blocks the next assignment.** Not logs and continues. That check lives
in `assign_shift`, the one function that creates assignments, so there is no second path
that forgets it.

**Nothing here is reachable from `OfficeClient`.** Part 8 requires the clear to be
"agent-uninterruptible", and an agent's only path to anything is the client library. The
library has no flush, no skip and no defer, and a test asserts its public surface still
contains none.

**The flush runs regardless of certification state.** Part 8: "this is a control, not a
competence claim." Tying it to certification would mean the agents most likely to have
made a mess are the ones least likely to clean it up.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from broker import audit
from broker.errors import OfficeError

# Classifications the boundary destroys. PHI is the statutory one; a call recording in a
# two-party-consent state is the same shape of problem and is treated the same way.
FLUSHED_CLASSIFICATIONS = ("phi", "recording")


class FlushFailed(OfficeError):
    """The flush ran and PHI-tagged memory survived it.

    Distinct from a database error: the operation completed and the outcome was wrong,
    which is the case that must block rather than retry.
    """

    audit_event = "shift_flush_failed"
    status_code = 500


class ShiftBlocked(OfficeError):
    """The agent's previous shift has no verified flush.

    Part 8: a failed flush blocks the next assignment rather than logging and
    continuing.
    """

    audit_event = "shift_assignment_blocked_unflushed"
    status_code = 409


class OffShift(OfficeError):
    """The call's venture is not the venture this agent is currently on shift for.

    Part 7.5: one venture per agent per shift, locked, with no mid-shift switching
    under any condition - including non-PHI ventures, because a uniform rule is
    enforceable where a conditional one is not.
    """

    audit_event = "call_refused_off_shift"


@dataclass(frozen=True, slots=True)
class FlushResult:
    shift_id: uuid.UUID
    before: dict[str, int]
    after: dict[str, int]
    verified: bool

    @property
    def evidence(self) -> dict[str, Any]:
        return {
            "before": self.before,
            "after": self.after,
            "flushed_classifications": list(FLUSHED_CLASSIFICATIONS),
            "verified": self.verified,
        }


async def record_memory(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    venture_id: str,
    data_classification: str,
    content_ref: str,
    shift_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Write one working-memory reference, classified.

    `data_classification` is a required argument with no default, mirroring the column.
    A convenience default here would defeat the constraint underneath it.
    """
    memory_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO agent_working_memory
              (memory_id, office_agent_id, shift_id, venture_id,
               data_classification, content_ref)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (memory_id, office_agent_id, shift_id, venture_id,
             data_classification, content_ref),
        )
    await conn.commit()
    return memory_id


async def _classification_counts(
    conn: AsyncConnection, office_agent_id: uuid.UUID
) -> dict[str, int]:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT data_classification, count(*) FROM agent_working_memory "
            "WHERE office_agent_id = %s GROUP BY data_classification "
            "ORDER BY data_classification",
            (office_agent_id,),
        )
        return {row[0]: int(row[1]) for row in await cur.fetchall()}


async def flush_phi(
    conn: AsyncConnection, *, office_agent_id: uuid.UUID, shift_id: uuid.UUID
) -> FlushResult:
    """Destroy PHI-tagged working memory and prove it is gone.

    Reads only the classification, never the content. Content this could read is
    content it could misjudge, and the whole point of tagging at write time is that
    the flush does not have to judge anything.

    Verification is a re-count after the delete rather than trusting the rowcount:
    a concurrent write between delete and commit would leave PHI behind, and a
    rowcount cannot see that.
    """
    before = await _classification_counts(conn, office_agent_id)

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE shift_assignment SET flush_attempted_at = now() WHERE shift_id = %s",
            (shift_id,),
        )
        await cur.execute(
            "DELETE FROM agent_working_memory "
            "WHERE office_agent_id = %s AND data_classification = ANY(%s)",
            (office_agent_id, list(FLUSHED_CLASSIFICATIONS)),
        )

    after = await _classification_counts(conn, office_agent_id)
    verified = not any(after.get(c, 0) for c in FLUSHED_CLASSIFICATIONS)

    result = FlushResult(shift_id=shift_id, before=before, after=after, verified=verified)

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE shift_assignment "
            "SET flush_completed_at = now(), flush_verified = %s, flush_evidence = %s "
            "WHERE shift_id = %s",
            (verified, Jsonb(result.evidence), shift_id),
        )
    await conn.commit()

    await audit.write_event(
        event_type="shift_phi_flush" if verified else FlushFailed.audit_event,
        actor_type="system",
        actor_id=office_agent_id,
        subject={"shift_id": str(shift_id), **result.evidence},
    )

    if not verified:
        raise FlushFailed(
            "PHI-tagged working memory survived the flush; the next assignment is "
            "blocked until this is resolved",
            shift_id=str(shift_id),
            remaining={c: after.get(c, 0) for c in FLUSHED_CLASSIFICATIONS},
        )

    return result


async def previous_shift(
    conn: AsyncConnection, office_agent_id: uuid.UUID
) -> dict[str, Any] | None:
    """The agent's most recent shift that has already ended."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT shift_id, venture_id, shift_end, flush_completed_at, flush_verified "
            "FROM shift_assignment "
            "WHERE office_agent_id = %s AND shift_end <= now() "
            "ORDER BY shift_end DESC LIMIT 1",
            (office_agent_id,),
        )
        return await cur.fetchone()


async def current_shift(
    conn: AsyncConnection, office_agent_id: uuid.UUID, *, at: datetime | None = None
) -> dict[str, Any] | None:
    """The shift this agent is on right now, if any."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT shift_id, venture_id, shift_start, shift_end FROM shift_assignment "
            "WHERE office_agent_id = %s AND shift_start <= COALESCE(%s, now()) "
            "  AND shift_end > COALESCE(%s, now()) LIMIT 1",
            (office_agent_id, at, at),
        )
        return await cur.fetchone()


async def assert_on_shift_for(
    conn: AsyncConnection, *, office_agent_id: uuid.UUID, venture_id: str
) -> uuid.UUID:
    """Refuse a call whose venture is not the agent's current shift venture.

    The schema already forbids overlapping shifts. Nothing forbade an agent holding
    grants for two ventures from serving both inside one shift - which is exactly the
    mid-shift switching Part 7.5 rules out. This is that rule, enforced.

    Uniform: a non-PHI venture is not exempt. "A single uniform rule is enforceable
    where a conditional one is not", and the condition is where the bug lives.
    """
    shift = await current_shift(conn, office_agent_id)
    if shift is None:
        raise OffShift(
            "agent is not on shift; calls must occur within an assigned shift",
            venture_id=venture_id,
        )
    if shift["venture_id"] != venture_id:
        raise OffShift(
            "agent is on shift for a different venture; mid-shift venture switching "
            "is not permitted under any condition",
            venture_id=venture_id,
            shift_venture_id=shift["venture_id"],
            shift_id=str(shift["shift_id"]),
        )
    return uuid.UUID(str(shift["shift_id"]))


async def assign_shift(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    venture_id: str,
    shift_start: datetime,
    shift_end: datetime,
    assigned_by: uuid.UUID,
) -> uuid.UUID:
    """Create a shift assignment, refusing if the previous shift was never flushed.

    The block lives here rather than in a caller because this is the only function
    that creates assignments. A check in a caller is a check the next caller forgets.
    """
    prior = await previous_shift(conn, office_agent_id)
    if prior is not None and not prior["flush_verified"]:
        raise ShiftBlocked(
            "previous shift has no verified PHI flush; assignment is blocked",
            previous_shift_id=str(prior["shift_id"]),
            previous_venture=prior["venture_id"],
            flush_completed=prior["flush_completed_at"] is not None,
            flush_verified=False,
        )

    shift_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO shift_assignment
              (shift_id, office_agent_id, venture_id, shift_start, shift_end, assigned_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (shift_id, office_agent_id, venture_id, shift_start, shift_end, assigned_by),
        )
    await conn.commit()

    await audit.write_event(
        event_type="shift_assigned",
        actor_type="human",
        actor_id=assigned_by,
        venture_id=venture_id,
        subject={
            "shift_id": str(shift_id),
            "office_agent_id": str(office_agent_id),
            "shift_start": shift_start.isoformat(),
            "shift_end": shift_end.isoformat(),
            "previous_shift_id": str(prior["shift_id"]) if prior else None,
        },
    )
    return shift_id


async def rotate(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    from_shift_id: uuid.UUID,
    to_venture_id: str,
    shift_start: datetime,
    shift_end: datetime,
    assigned_by: uuid.UUID,
) -> uuid.UUID:
    """The shift boundary, in the order Part 7.5 states.

        flush + verify -> re-resolve grants -> switch context -> audit

    Every step's position is load-bearing. Flush before re-resolve, so the outgoing
    venture's data is gone before the incoming venture's authority exists. Verify
    before switch, so a failed flush has nothing to switch into.

    Certification state is not consulted. A revoked or suspended agent still flushes:
    the flush is a control, not a competence claim, and the agents most likely to have
    made a mess are the ones least likely to be in good standing.
    """
    # 1 + 2. Raises FlushFailed if anything survived, which stops the rotation here.
    await flush_phi(conn, office_agent_id=office_agent_id, shift_id=from_shift_id)

    # 3. Re-resolve grants for the incoming venture. Read-only and advisory: the call
    # path resolves grants live on every call anyway, so this exists to surface a
    # rotation into a venture the agent cannot actually work, at the boundary rather
    # than at the agent's first refused call.
    grants = await _live_grants(conn, office_agent_id, to_venture_id)

    # 4. Switch context. assign_shift re-checks the flush independently - this
    # function is not the only way a shift gets created, and the block belongs to
    # assignment rather than to rotation.
    shift_id = await assign_shift(
        conn,
        office_agent_id=office_agent_id,
        venture_id=to_venture_id,
        shift_start=shift_start,
        shift_end=shift_end,
        assigned_by=assigned_by,
    )

    # 5. Audit the boundary itself, distinctly from the flush and the assignment.
    await audit.write_event(
        event_type="shift_boundary_completed",
        actor_type="system",
        actor_id=office_agent_id,
        venture_id=to_venture_id,
        subject={
            "from_shift_id": str(from_shift_id),
            "to_shift_id": str(shift_id),
            "to_venture_id": to_venture_id,
            "grants_resolved": grants,
            "order": ["flush", "verify", "resolve_grants", "switch_context", "audit"],
        },
    )
    return shift_id


async def _live_grants(
    conn: AsyncConnection, office_agent_id: uuid.UUID, venture_id: str
) -> int:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM agent_forge_grant "
            "WHERE office_agent_id = %s AND venture_id = %s AND revoked_at IS NULL",
            (office_agent_id, venture_id),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0
