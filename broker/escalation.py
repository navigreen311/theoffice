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
from broker.audit import write_event
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


# ======================================================= the record an escalation leaves

@dataclass(frozen=True, slots=True)
class Escalation:
    """One escalation, and what has happened to it so far."""

    escalation_id: uuid.UUID
    venture_id: str
    department: str | None
    route: Route
    kind: str
    raised_at: Any
    raised_by: uuid.UUID
    raised_by_kind: str
    received_at: Any = None
    received_by: uuid.UUID | None = None
    answered_at: Any = None
    answered_by: uuid.UUID | None = None
    answer: str | None = None

    @property
    def travelled(self) -> bool:
        """Raised, received AND answered. Anything less is a path nobody has shown works.

        Ruled 21 September 2026: *"An escalation path cannot be attested verified until
        it can be shown to have been travelled."* Received is the half that matters -
        raised-and-answered by one process in one second proves a function returns.
        """
        return self.received_at is not None and self.answered_at is not None


async def raise_escalation(
    conn: AsyncConnection,
    *,
    kind: str,
    path: Path,
    venture_id: str,
    reason: str,
    raised_by: uuid.UUID,
    raised_by_kind: str = "agent",
    department: str | None = None,
) -> Escalation:
    """Route an escalation AND record that it was raised.

    RULED 21 SEPTEMBER 2026 (decisions entry 149)
    =============================================

        *"An escalation leaves a record: raised, by whom, routed to which named human,
        received, and answered, with timestamps. Both escalation paths return a route
        and write nothing."*

    `governance` and `operational` stay exactly what they were: resolvers, which answer
    "who would this go to" without asserting that anybody sent anything. **Resolving a
    route is not raising an escalation**, and a function that wrote a row every time
    somebody asked the question would fill the record with escalations nobody made.

    This is the act. It resolves through the same two functions, writes the row, and
    returns both.

    `assert_path` is called FIRST, before anything is written. A governance decision
    addressed to an agent is refused rather than recorded as refused.
    """
    assert_path(kind, path)
    if not reason.strip():
        raise OfficeError("an escalation says why it was raised")
    if raised_by_kind not in ("agent", "human"):
        raise OfficeError(f"unknown raiser kind {raised_by_kind!r}")

    route = (
        await governance(conn, reason=reason) if path is Path.GOVERNANCE
        else await operational(conn, reason=reason)
    )
    if route.to is None or not str(route.to).strip():
        # An operational route with an empty COO seat resolves to nobody, and
        # `operational` says so rather than substituting a holder. Raising into that is
        # not an escalation, it is a message addressed to a vacancy.
        raise OfficeError(
            f"the {path.value} path resolves to nobody right now; there is nothing to "
            "escalate to and a row saying otherwise would be a delivery nobody made"
        )

    escalation_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO escalation_record "
            "  (escalation_id, venture_id, department, path, kind, reason, "
            "   raised_by, raised_by_kind, routed_to_name, routed_to_human) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                escalation_id, venture_id, department, path.value, kind, reason.strip(),
                raised_by, raised_by_kind, route.to, route.human_id,
            ),
        )
    await conn.commit()

    await write_event(
        event_type="escalation_raised",
        actor_type=raised_by_kind, actor_id=raised_by, venture_id=venture_id,
        subject={
            "escalation_id": str(escalation_id), "kind": kind, "path": path.value,
            "department": department, "routed_to": route.to,
            "routed_to_human": str(route.human_id) if route.human_id else None,
        },
    )
    found = await get(conn, escalation_id)
    assert found is not None
    return found


async def record_receipt(
    conn: AsyncConnection, *, escalation_id: uuid.UUID, received_by: uuid.UUID
) -> Escalation:
    """Somebody on the other end picked it up.

    **The step the two paths could not demonstrate.** Delivery is what an escalation
    path is, and both of them returned a recipient's name and stopped there.

    Idempotent on the first receipt: a second call leaves the original timestamp alone,
    because when it was picked up is a fact and the second caller is not a second
    pickup.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE escalation_record SET received_at = now(), received_by = %s "
            " WHERE escalation_id = %s AND received_at IS NULL",
            (received_by, escalation_id),
        )
    await conn.commit()

    found = await get(conn, escalation_id)
    if found is None:
        raise LookupError(f"no such escalation {escalation_id}")
    if found.received_at is not None:
        await write_event(
            event_type="escalation_received",
            actor_type="human", actor_id=received_by, venture_id=found.venture_id,
            subject={"escalation_id": str(escalation_id),
                     "department": found.department},
        )
    return found


async def record_answer(
    conn: AsyncConnection, *, escalation_id: uuid.UUID, answered_by: uuid.UUID,
    answer: str,
) -> Escalation:
    """What the recipient decided. Refused before a receipt, and refused empty.

    The CHECK in 0051 refuses both as well, and this refuses them first so a caller
    meets a sentence rather than a constraint name.
    """
    if not answer.strip():
        raise OfficeError("an escalation is answered with a sentence, not a flag")
    found = await get(conn, escalation_id)
    if found is None:
        raise LookupError(f"no such escalation {escalation_id}")
    if found.received_at is None:
        raise OfficeError(
            "this escalation has not been received, so it cannot be answered. An answer "
            "before a receipt is not a path that worked; it is two timestamps somebody "
            "wrote."
        )

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE escalation_record SET answered_at = now(), answered_by = %s, "
            "       answer = %s "
            " WHERE escalation_id = %s AND answered_at IS NULL",
            (answered_by, answer.strip(), escalation_id),
        )
    await conn.commit()

    await write_event(
        event_type="escalation_answered",
        actor_type="human", actor_id=answered_by, venture_id=found.venture_id,
        subject={"escalation_id": str(escalation_id), "department": found.department,
                 "answer": answer.strip()},
    )
    answered = await get(conn, escalation_id)
    assert answered is not None
    return answered


async def get(conn: AsyncConnection, escalation_id: uuid.UUID) -> Escalation | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM escalation_record WHERE escalation_id = %s", (escalation_id,)
        )
        row = await cur.fetchone()
    return _escalation(row) if row else None


async def travelled(
    conn: AsyncConnection, *, venture_id: str, department: str
) -> Escalation | None:
    """The newest escalation for this department that was raised, received AND answered.

    **What `attestation.attest` reads before it will accept `escalation_path_verified`.**
    Ruled 21 September 2026: an escalation path cannot be attested verified until it can
    be shown to have been travelled.

    `department = %s` and never NULL: a venture-wide escalation is evidence about the
    venture's path, not about research's, and counting it would let one drill attest
    three departments.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM escalation_record "
            " WHERE venture_id = %s AND department = %s "
            "   AND received_at IS NOT NULL AND answered_at IS NOT NULL "
            " ORDER BY answered_at DESC LIMIT 1",
            (venture_id, department),
        )
        row = await cur.fetchone()
    return _escalation(row) if row else None


async def outstanding(conn: AsyncConnection, *, venture_id: str) -> list[Escalation]:
    """Raised and not yet answered, oldest first. The queue a drill produces."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM escalation_record "
            " WHERE venture_id = %s AND answered_at IS NULL ORDER BY raised_at",
            (venture_id,),
        )
        rows = await cur.fetchall()
    return [_escalation(row) for row in rows]


def _escalation(row: dict[str, Any]) -> Escalation:
    return Escalation(
        escalation_id=row["escalation_id"],
        venture_id=row["venture_id"],
        department=row["department"],
        route=Route(
            path=Path(row["path"]),
            to=row["routed_to_name"],
            reason=row["reason"],
            human_id=row["routed_to_human"],
        ),
        kind=row["kind"],
        raised_at=row["raised_at"],
        raised_by=row["raised_by"],
        raised_by_kind=row["raised_by_kind"],
        received_at=row["received_at"],
        received_by=row["received_by"],
        answered_at=row["answered_at"],
        answered_by=row["answered_by"],
        answer=row["answer"],
    )
