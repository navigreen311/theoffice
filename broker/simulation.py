"""A venture declared in simulation, and what that defers.

RULED 22 SEPTEMBER 2026 (decisions entry 166)
=============================================

    *"A venture may be declared in simulation by a named human, with a reason and a
    date. In simulation, an unreviewed compliance entry is recorded as deliberately
    deferred, not as verified, and does not fail a gate. Leaving simulation is a
    separate named act; every unreviewed entry fails again the moment it does. No
    attestation may ever read TRUE on the strength of simulation. Greenstone and Burkham
    Wickmont are both in simulation as of today, declared by Ivan Green, reason: mock
    runs and simulations before real clients."*

WHY THIS EXISTS AT ALL
======================

    Entry 165, the day before: an entry is relied on only when approved AND
    counsel-reviewed, and anything treating a draft as authoritative refuses. Measured
    the same day - all 21 entries are drafts, none counsel-reviewed. And there is **no
    counsel until there are real clients**, so the drafts stay drafts for a long time.

    Taken together those two facts stop every venture at Gate 2 indefinitely, which is
    further from Gate 12 than the day before the rule.

DEFERRED IS NOT VERIFIED, AND THIS MODULE KEEPS THEM APART
==========================================================

    `knowledge.is_relied_on` is untouched. A deferred entry is **still not relied on**,
    still reads DRAFT, and still has no approver and no counsel review. What simulation
    changes is what a gate DOES about that: it records the deferral, names who declared
    it and why, and does not fail.

    Two predicates rather than one, deliberately:

        knowledge.is_relied_on(entry)     the entry stands on its own
        gate_may_defer(...)               somebody decided not to require that yet

    Collapsing them would make a declaration of simulation read, three screens later, as
    a compliance entry a lawyer approved. That is precisely the confusion entry 165 was
    written to end, arriving through a different door.

WHAT SIMULATION NEVER DOES
==========================

    **No attestation may read TRUE on the strength of it.** `attestation.attest` refuses
    `compliance_coupling_verified=True` while the venture is in simulation, and there is
    no override argument. A deferral is a decision to postpone a check; an attestation
    is a person's statement that the check passed, and the second cannot be built out of
    the first.

    The consequence is stated rather than worked around: an attestation in simulation
    cannot pass, so Unit B by attestation cannot certify, so **Gate 9 is not reachable
    while a venture is in simulation.** Simulation moves a venture past Gates 2 and 6.
    It does not move it to 12, and it is not meant to.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import humans


class SimulationError(Exception):
    """A refusal this module made."""


@dataclass(frozen=True, slots=True)
class Simulation:
    """One declaration. Live while `left_at` is None."""

    simulation_id: uuid.UUID
    venture_id: str
    declared_by: uuid.UUID
    declared_by_name: str
    declared_at: datetime
    reason: str
    left_by: uuid.UUID | None = None
    left_by_name: str | None = None
    left_at: datetime | None = None
    left_reason: str | None = None

    @property
    def live(self) -> bool:
        return self.left_at is None

    def as_evidence(self) -> dict[str, Any]:
        """What a gate puts in its evidence when it defers on this.

        The whole declaration, not a boolean. A gate outcome reading
        `{"simulation": true}` would record that something was deferred and lose who
        decided it and why - which is the entire content of the ruling.
        """
        return {
            "simulation_id": str(self.simulation_id),
            "declared_by": self.declared_by_name,
            "declared_at": self.declared_at.isoformat(),
            "reason": self.reason,
        }


_COLUMNS = (
    "s.simulation_id, s.venture_id, s.declared_by, s.declared_at, s.reason, "
    "s.left_by, s.left_at, s.left_reason, "
    "d.display_name AS declared_by_name, l.display_name AS left_by_name"
)
_FROM = (
    "  FROM venture_simulation s "
    "  JOIN office_human d ON d.human_id = s.declared_by "
    "  LEFT JOIN office_human l ON l.human_id = s.left_by "
)


def _shape(row: dict[str, Any]) -> Simulation:
    return Simulation(
        simulation_id=row["simulation_id"],
        venture_id=row["venture_id"],
        declared_by=row["declared_by"],
        declared_by_name=row["declared_by_name"],
        declared_at=row["declared_at"],
        reason=row["reason"],
        left_by=row["left_by"],
        left_by_name=row["left_by_name"],
        left_at=row["left_at"],
        left_reason=row["left_reason"],
    )


async def current(conn: AsyncConnection, venture_id: str) -> Simulation | None:
    """The live declaration for this venture, or None.

    None means *not in simulation*, which is the safe direction: every caller treats it
    as "the entry 165 rule applies in full", so a venture nobody declared gets the
    stricter answer rather than the looser one.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_COLUMNS} {_FROM} WHERE s.venture_id = %s AND s.left_at IS NULL",
            (venture_id,),
        )
        row = await cur.fetchone()
    return _shape(dict(row)) if row else None


async def history(
    conn: AsyncConnection, venture_id: str | None = None
) -> list[Simulation]:
    """Every declaration ever made, newest first. Left ones included.

    A venture that was in simulation last month and is not now explains a gate result
    from last month, and a reader who can only see the current state cannot account for
    it.
    """
    where = "WHERE s.venture_id = %s " if venture_id else ""
    params = (venture_id,) if venture_id else ()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_COLUMNS} {_FROM} {where}ORDER BY s.declared_at DESC", params
        )
        return [_shape(dict(r)) for r in await cur.fetchall()]


async def declare(
    conn: AsyncConnection, *, venture_id: str, declared_by: uuid.UUID, reason: str
) -> Simulation:
    """Declare a venture in simulation. A named human, a reason, and a date.

    **The reason is required and non-blank**, at three layers: here, the column's CHECK,
    and the route's schema. This is the field that will be read in six months by
    somebody asking why a gate passed over a draft, and a declaration whose reason is
    empty answers that question with nothing.

    The date is `now()` rather than a parameter. A declaration that could be backdated
    would be able to explain a gate result it did not exist for.
    """
    if not reason.strip():
        raise SimulationError(
            "a declaration of simulation gives a reason. It is what a reader finds "
            "when they ask why a gate passed over an unreviewed compliance entry, and "
            "an empty one answers that with silence."
        )

    await humans.assert_named_human_by_id(
        conn, human_id=declared_by, act="declare a venture in simulation"
    )

    if (live := await current(conn, venture_id)) is not None:
        raise SimulationError(
            f"{venture_id} is already in simulation, declared by "
            f"{live.declared_by_name} on {live.declared_at.date()}: {live.reason} "
            "A second declaration would record a decision nobody took. Leave the "
            "current one first if the reason has changed."
        )

    simulation_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO venture_simulation "
            "  (simulation_id, venture_id, declared_by, reason) "
            "VALUES (%s, %s, %s, %s)",
            (simulation_id, venture_id, declared_by, reason.strip()),
        )
    await conn.commit()
    declared = await current(conn, venture_id)
    assert declared is not None
    return declared


async def leave(
    conn: AsyncConnection, *, venture_id: str, left_by: uuid.UUID, reason: str
) -> Simulation:
    """Leave simulation. A separate named act, and not reversible.

    *"Every unreviewed entry fails again the moment it does."* Nothing here re-checks
    the library or warns about what is about to start failing - deliberately. A leaving
    act that reported "this will break Gate 2 for two entries" would invite the reading
    that it is a negotiation, and it is not: it is somebody saying the venture is no
    longer in simulation, which is a fact about the venture and not about the library.

    The caller that wants that warning first can ask `knowledge.compliance_entries`
    before calling, and the console does.
    """
    if not reason.strip():
        raise SimulationError(
            "leaving simulation gives a reason, like declaring it does. It is the same "
            "kind of act in the other direction."
        )

    await humans.assert_named_human_by_id(
        conn, human_id=left_by, act="take a venture out of simulation"
    )

    live = await current(conn, venture_id)
    if live is None:
        raise SimulationError(
            f"{venture_id} is not in simulation, so there is nothing to leave. "
            "Every unreviewed compliance entry is already failing its gates."
        )

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE venture_simulation "
            "   SET left_by = %s, left_at = now(), left_reason = %s "
            " WHERE simulation_id = %s AND left_at IS NULL",
            (left_by, reason.strip(), live.simulation_id),
        )
    await conn.commit()

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT {_COLUMNS} {_FROM} WHERE s.simulation_id = %s",
            (live.simulation_id,),
        )
        row = await cur.fetchone()
    assert row is not None
    return _shape(dict(row))


#: The SQL half of "this venture may defer an unreviewed entry". Used inside the two
#: queries that decide whether a flag is explained, so the rule is one expression rather
#: than a Python branch wrapped around a query and a second one wrapped around another.
IN_SIMULATION_SQL = (
    "EXISTS (SELECT 1 FROM venture_simulation vs "
    "         WHERE vs.venture_id = %(venture_id)s AND vs.left_at IS NULL)"
)


async def deferring(conn: AsyncConnection) -> set[str]:
    """Every venture currently in simulation.

    For readers that ask about many ventures at once - the coverage panel does - so the
    alternative is a query per venture or a second spelling of the predicate.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT venture_id FROM venture_simulation WHERE left_at IS NULL"
        )
        return {r[0] for r in await cur.fetchall()}


__all__ = [
    "IN_SIMULATION_SQL",
    "Simulation",
    "SimulationError",
    "current",
    "declare",
    "deferring",
    "history",
    "leave",
]
