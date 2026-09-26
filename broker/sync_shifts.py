"""`office sync-shifts` — the Village's shift calendar, diffed against The Office.

RULED 25 SEPTEMBER 2026 (decisions entry 197)
=============================================

    *"A department may serve more than one venture; an agent may not, in a quarter. The
    Pack declares which departments a venture draws on, not which venture owns a
    department. An agent's venture for a quarter comes from its shift assignment, a
    deliberate act, never inferred from a department."*

WHY THIS CANNOT BE `sync-roster`, AND WHAT IT IS INSTEAD
========================================================

    `sync-roster` diffs and applies in both directions because both sides name one
    entity: an agent, by `village_agent_ref`. Shifts do not have that property. The
    Village's feed is

        departments -> { Operations: { shifts: { MORNING | EVENING | NIGHT: [refs] } } }

    and it carries **no venture at all**. The Village does not have the concept. It
    answers *who is working, in which department, in which phase*; The Office needs
    *which venture this agent may serve this quarter*.

    Measured 25 September 2026, on live grants grouped by the holder's department:
    `operations` holds 24 for `burkham-wickmont` and 4 for `greenstone`. So the venture
    is not recoverable from the department either, and entry 197 rules that it must not
    be: it comes from the shift assignment, which is a person's act.

    **So this command assigns nobody.** It ends shifts the Village says are over, which
    needs no venture, and it REPORTS everything else for a human to decide. A reconciler
    that guessed the venture would be inventing the one fact the ruling says must be
    authored - and it would invent it most often for `operations`, the department where
    it is most ambiguous and most consequential.

WHAT IT REPORTS

    unassigned      on shift in the Village, no current assignment here
    to_end          assigned here, and the Village says that shift is over
    stale_quarter   assigned here under a quarter the Village has left
    off_pack        assigned to a venture whose Pack draws on no such department
    blocked         the previous shift has no verified flush, so nothing can be assigned

    Only `to_end` is applied. The rest are a report.

WHY IT NEVER APPLIES AGAINST A DEGRADED ANSWER

    `sync-roster` refuses a cached roster because a stale one reads as mass departure.
    The same hazard is sharper here: a cached or empty shift feed reads as *nobody is on
    shift*, `to_end` would close every assignment, and the client's shift check would
    then refuse every call in the system. `village.shifts(degrade=False)` is what stops
    that, and an empty `departments` map is refused rather than believed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, packs, shifts, village


class SyncError(Exception):
    """The calendar could not be read, or the change could not be applied."""


@dataclass
class Change:
    """One agent's difference between the Village's calendar and The Office's."""

    kind: str  # unassigned | to_end | stale_quarter | off_pack | blocked
    village_agent_ref: str
    agent_name: str
    detail: str
    office_agent_id: uuid.UUID | None = None
    shift_id: uuid.UUID | None = None


@dataclass
class Diff:
    """What a sync would do. Nothing here has been applied."""

    quarter: str = ""
    village_phase: str = ""
    village_on_shift: int = 0
    office_on_shift: int = 0
    changes: list[Change] = field(default_factory=list)

    def of(self, kind: str) -> list[Change]:
        return [c for c in self.changes if c.kind == kind]

    @property
    def empty(self) -> bool:
        return not self.changes

    def summary(self) -> dict[str, Any]:
        return {
            "quarter": self.quarter,
            "village_phase": self.village_phase,
            "village_on_shift": self.village_on_shift,
            "office_on_shift": self.office_on_shift,
            "unassigned": len(self.of("unassigned")),
            "to_end": len(self.of("to_end")),
            "stale_quarter": len(self.of("stale_quarter")),
            "off_pack": len(self.of("off_pack")),
            "blocked": len(self.of("blocked")),
            "changes": [
                {
                    "kind": c.kind,
                    "village_agent_ref": c.village_agent_ref,
                    "agent_name": c.agent_name,
                    "detail": c.detail,
                }
                for c in self.changes
            ],
        }


async def _village_on_shift() -> tuple[str, set[str]]:
    """The current phase, and every agent ref the Village says is working in it.

    Never a cached answer, and an empty map is refused. Both for the reason in the
    module docstring: believing a silent Village would end every shift in the system.
    """
    try:
        answer = await village.shifts(degrade=False)
    except village.VillageUnreachableError as exc:
        raise SyncError(
            f"the Village did not answer ({exc}). Nothing was compared and nothing was "
            "changed - a sync against a cached calendar would read as nobody being on "
            "shift, and ending every shift refuses every call in the system."
        ) from exc

    phase = str(answer.data.get("current_phase") or "")
    departments = answer.data.get("departments") or {}
    if not phase or not departments:
        raise SyncError(
            "the Village answered with no current phase or no departments. Refusing to "
            "treat that as an empty calendar."
        )

    on_shift: set[str] = set()
    for dept in departments.values():
        block = (dept or {}).get("shifts") or {}
        entry = block.get(phase) or {}
        on_shift.update(entry.get("agents") or [])
    return phase, on_shift


async def _office_agents(conn: AsyncConnection) -> dict[str, dict[str, Any]]:
    """Every active identity, keyed by Village ref. Revoked agents are not scheduled."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT office_agent_id, village_agent_ref, agent_name, department "
            "  FROM office_agent_identity "
            " WHERE status = 'active' AND village_agent_ref IS NOT NULL"
        )
        return {r["village_agent_ref"]: dict(r) for r in await cur.fetchall()}


async def _pack_departments(conn: AsyncConnection, venture_id: str) -> set[str] | None:
    """The departments a venture's live Pack draws on, from its positions.

    `None` when the venture has no live Pack - which is not the same as drawing on no
    department, and `off_pack` must not fire on it.
    """
    stored = await packs.live(conn, venture_id)
    if stored is None:
        return None
    return {p.source_department for p in stored.pack.positions_required}


async def diff(conn: AsyncConnection) -> Diff:
    """What has changed. Reads both sides and writes nothing."""
    quarter = await shifts.current_quarter()
    phase, village_refs = await _village_on_shift()
    agents = await _office_agents(conn)

    out = Diff(quarter=quarter, village_phase=phase, village_on_shift=len(village_refs))
    pack_cache: dict[str, set[str] | None] = {}

    for ref, agent in sorted(agents.items()):
        agent_id = agent["office_agent_id"]
        name = agent["agent_name"] or ref
        current = await shifts.current_shift(conn, agent_id)
        working = ref in village_refs
        if current is not None:
            out.office_on_shift += 1

        if working and current is None:
            # THE ONE THIS COMMAND CANNOT FIX. Entry 197: the venture is a deliberate
            # act, and nothing in the Village's answer names one.
            prior = await shifts.previous_shift(conn, agent_id)
            if prior is not None and not prior["flush_verified"]:
                out.changes.append(Change(
                    "blocked", ref, name,
                    f"on shift in {phase}, and the previous shift on "
                    f"{prior['venture_id']} has no verified PHI flush",
                    office_agent_id=agent_id, shift_id=prior["shift_id"],
                ))
            else:
                held = await shifts.quarter_venture(conn, agent_id, quarter)
                detail = f"on shift in {phase}, no assignment here"
                if held:
                    # `one_venture_per_agent_quarter` will hold them to this one, so
                    # say so now rather than letting the operator find out on insert.
                    detail += f"; already worked {held} in {quarter}"
                out.changes.append(Change(
                    "unassigned", ref, name, detail, office_agent_id=agent_id,
                ))
            continue

        if current is None:
            continue

        if not working:
            out.changes.append(Change(
                "to_end", ref, name,
                f"assigned to {current['venture_id']}, not on shift in {phase}",
                office_agent_id=agent_id, shift_id=current["shift_id"],
            ))
            continue

        # On shift on both sides. The assignment stands; what may not is its quarter or
        # its venture's Pack.
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT quarter FROM shift_assignment WHERE shift_id = %s",
                (current["shift_id"],),
            )
            row = await cur.fetchone()
        assigned_quarter = (row or {}).get("quarter")
        if assigned_quarter and assigned_quarter != quarter:
            out.changes.append(Change(
                "stale_quarter", ref, name,
                f"assigned under {assigned_quarter}; the Village is in {quarter}",
                office_agent_id=agent_id, shift_id=current["shift_id"],
            ))

        venture_id = str(current["venture_id"])
        if venture_id not in pack_cache:
            pack_cache[venture_id] = await _pack_departments(conn, venture_id)
        declared = pack_cache[venture_id]
        if declared is not None and agent["department"] not in declared:
            out.changes.append(Change(
                "off_pack", ref, name,
                f"assigned to {venture_id}, whose Pack draws on "
                f"{', '.join(sorted(declared)) or 'no department'} and not "
                f"{agent['department']}",
                office_agent_id=agent_id, shift_id=current["shift_id"],
            ))

    return out


async def apply(
    conn: AsyncConnection, *, actor: uuid.UUID, confirmed: bool = False
) -> dict[str, Any]:
    """End the shifts the Village says are over. **Assigns nobody.**

    Recomputed here rather than taking a diff the caller made earlier, for the reason
    `sync_roster.apply` gives: between showing a diff and confirming it the Village may
    have changed phase, and applying a stale diff would write a calendar that never
    existed on either side.

    ONLY `to_end`. Entry 197 puts the venture in the shift assignment and makes that a
    deliberate act, so `unassigned` is reported and left: a command that picked a
    venture would be inventing the fact the ruling says must be authored. Ending needs
    no venture - the agent is already on one - which is why this half can be automatic
    and the other half cannot.

    Ending sets `shift_end` to now. The flush is NOT run here: `sweep_flush_ended_shifts`
    owns that and runs on its own, and a second path that flushed would be a second
    place for the ordering in Part 7.5 to be got wrong.
    """
    if not confirmed:
        raise SyncError(
            "sync-shifts ends shift assignments and will not run without --confirm. "
            "Run it without the flag first to see the diff."
        )

    changes = await diff(conn)
    ending = changes.of("to_end")
    now = datetime.now(UTC)

    async with conn.cursor() as cur:
        for change in ending:
            await cur.execute(
                "UPDATE shift_assignment SET shift_end = %s "
                " WHERE shift_id = %s AND shift_end > %s",
                (now, change.shift_id, now),
            )
    await conn.commit()

    await audit.write_event(
        event_type="shift_calendar_reconciled",
        actor_type="human",
        actor_id=actor,
        venture_id=None,
        subject={
            "quarter": changes.quarter,
            "village_phase": changes.village_phase,
            "ended": [
                {"agent": c.agent_name, "shift_id": str(c.shift_id)} for c in ending
            ],
            # REPORTED IN THE EVENT, not only on the screen. What this command did NOT
            # do is the interesting half, and an audit entry that recorded only the
            # ended shifts would read as a full reconciliation.
            "left_for_a_human": {
                kind: len(changes.of(kind))
                for kind in ("unassigned", "stale_quarter", "off_pack", "blocked")
            },
        },
    )
    return {"ended": len(ending), **changes.summary()}
