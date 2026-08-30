"""Where a decision goes when the person facing it may not make it.

There are two paths and they do not meet.

    OPERATIONAL   up the Village's own chain of command, to the COO position.
                  Work questions. Who covers a shift, which objective takes the
                  quarter, whether a deputy's draft is good enough.

    GOVERNANCE    out of the Village entirely, to a human. Capacity shortfall,
                  certification, revocation, an incident, anything that changes who
                  may act. No agent decides these, including the COO.

The separation is the point. If governance escalations could route through the
operational path, the COO would be approving the capacity of the organisation the COO
runs, and The Office would be a reporting layer rather than a governing one. Part 10.1
puts The Office above the Village precisely so that the answer to "can we staff this"
does not come from the party that wants the answer to be yes.

THE POSITION, NEVER THE NAME
============================

Gardner is the COO. Gardner is also an agent, with a mortality roll, and the Village
auto-hires into a vacated seat. An escalation path written as "flag to Gardner" points at
a corpse the first time that roll comes up, and it points there silently - the string is
still valid, the agent is still in the roster marked departed, and nothing about the
constant knows it has gone stale. That is the same failure the department list had: a
copy cannot know the world moved.

So the COO is stored as a position - `executive` / `COO` - and resolved against the
roster every time. When the seat is empty the answer is that it is empty. There is no
fallback holder, because a fallback here would silently hand one agent's authority to
another.

The same reasoning applies on the governance side, where `humans.attributable_actor`
already refuses to name a test fixture. An escalation delivered to `smoke-1a2b3c4d` is
not delivered.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import humans
from broker.errors import OfficeError

#: The COO position, in the Village's own terms. Not a name, and not a `role_key`:
#: `department_head` is the ladder rung and twelve agents hold it. The seat is the
#: department plus the title.
COO_POSITION = ("executive", "COO")


class Path(Enum):
    """The two routes, named so that a caller has to choose one."""

    OPERATIONAL = "operational"
    GOVERNANCE = "governance"


class SeatVacant(OfficeError):
    """Nobody holds the position this escalation is addressed to.

    Reported rather than rerouted. The next-best agent is somebody who was not given
    this authority, and quietly promoting them is how an escalation path becomes a way
    to reach whoever happens to be available.
    """

    audit_event = "escalation_seat_vacant"
    status_code = 409


class WrongPath(OfficeError):
    """A governance decision was addressed to an agent.

    The COO may not certify, revoke, or accept a capacity shortfall in the Village the
    COO runs. This is the check that says so, rather than trusting each caller to
    remember which of the two paths their decision belongs on.
    """

    audit_event = "escalation_wrong_path"
    status_code = 403


@dataclass(frozen=True, slots=True)
class Holder:
    """Whoever currently occupies a position."""

    village_agent_ref: str
    agent_name: str
    department: str
    title: str
    status: str

    @property
    def present(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True, slots=True)
class Route:
    """Where one escalation goes, and on what grounds."""

    path: Path
    to: str
    reason: str
    #: The position, for an operational route. Kept beside the holder so a reader can
    #: see the escalation was addressed to a seat and who was in it at the time.
    position: str | None = None
    holder: Holder | None = None
    human_id: uuid.UUID | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path.value,
            "to": self.to,
            "reason": self.reason,
            "position": self.position,
            "holder": self.holder.agent_name if self.holder else None,
            "holder_ref": self.holder.village_agent_ref if self.holder else None,
            "human_id": str(self.human_id) if self.human_id else None,
        }


async def position_holder(
    conn: AsyncConnection, department: str, title: str
) -> Holder | None:
    """Who holds a position right now, or None if the seat is empty.

    Reads the roster rather than a constant. `sync-roster` keeps that table current and
    marks a departed agent `departed` rather than deleting the row, so a seat vacated by
    a mortality roll reads as vacant here on the next sync instead of continuing to
    resolve to somebody who is gone.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT village_agent_ref, agent_name, department, title, status "
            "FROM village_agent "
            "WHERE department = %s AND title = %s AND status = 'active' "
            "ORDER BY village_agent_ref LIMIT 1",
            (department, title),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Holder(
        village_agent_ref=row["village_agent_ref"],
        agent_name=row["agent_name"],
        department=row["department"],
        title=row["title"],
        status=row["status"],
    )


async def coo(conn: AsyncConnection) -> Holder | None:
    """Whoever is COO today."""
    return await position_holder(conn, *COO_POSITION)


async def operational(conn: AsyncConnection, *, reason: str) -> Route:
    """Escalate up the Village's chain of command, to the COO position.

    Raises when the seat is empty. A caller that wanted a best-effort delivery can catch
    it; what it cannot do is receive a different agent without noticing.
    """
    department, title = COO_POSITION
    holder = await coo(conn)
    if holder is None:
        raise SeatVacant(
            f"the {title} position in {department} is vacant, so this escalation has "
            "nowhere to go. It was not rerouted: the next-ranking agent was not given "
            "this authority. Run `python -m broker sync-roster` if the Village has "
            "already hired a replacement.",
            position=f"{department}/{title}",
            reason=reason,
        )
    return Route(
        path=Path.OPERATIONAL,
        to=holder.agent_name,
        reason=reason,
        position=f"{department}/{title}",
        holder=holder,
    )


async def governance(conn: AsyncConnection, *, reason: str) -> Route:
    """Escalate out of the Village, to a human who can be held to the decision.

    Deliberately not parameterised by agent. There is no argument that would let a
    caller address a governance decision to the COO, because the way that mistake gets
    made is not by choosing wrongly - it is by passing through whatever recipient was
    already in hand.
    """
    human_id = await humans.attributable_actor(conn)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT display_name FROM office_human WHERE human_id = %s", (human_id,)
        )
        row = await cur.fetchone()
    return Route(
        path=Path.GOVERNANCE,
        to=row["display_name"] if row else str(human_id),
        reason=reason,
        human_id=human_id,
    )


#: Decisions that change who may act. None of these may be settled inside the Village,
#: including by the COO, and this is the list rather than a judgement call at each site.
GOVERNANCE_ONLY = frozenset({
    "capacity_shortfall",
    "certification",
    "revocation",
    "incident",
    "grant",
    "appointment",
})


def assert_path(kind: str, path: Path) -> None:
    """Refuse a governance decision addressed to an agent.

    Called by anything that routes an escalation, so the rule is enforced once rather
    than remembered at each site. `kind` is deliberately open: an unrecognised kind is
    allowed on either path, because a whitelist here would silently downgrade a new
    governance decision to an operational one on the day somebody added it.
    """
    if kind in GOVERNANCE_ONLY and path is Path.OPERATIONAL:
        raise WrongPath(
            f"{kind} is a governance decision and cannot be escalated inside the "
            "Village. The COO runs the organisation this question is about, which is "
            "the reason The Office sits above it.",
            kind=kind,
            attempted_path=path.value,
        )
