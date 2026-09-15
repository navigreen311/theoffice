"""Put one agent on shift for one venture: a named operator and a real window.

Decisions entry 80. **Provisioning grants authority; nothing schedules it.** A venture that
clears every gate is authorised and not staffed, and the ladder is right not to change that:
it has no operator who knows who is on duty and no window to write. This module is the
smallest thing that does the other job, and it does it through `shifts.assign_shift`, the
one function that creates assignments, so every refusal that function owns still holds.

WHAT IT REFUSES, BEFORE ANYTHING IS WRITTEN
===========================================

    operator    unknown, not a real account, inactive, or without venture_operator+
    agent       unknown, or its identity is not active
    window      naive, empty, already over, or starting in the past
    venture     has no active grants - a shift there staffs nothing
    agent       holds no grant that resolves for the venture
    shifts      overlaps one this agent already holds, or follows an unflushed one
    quarter     the Village cannot say what it is, or the agent works another venture in it

**Every check is collected rather than stopping at the first**, so a report names
everything in the way at once. `apply` plans again rather than trusting a report it was
handed: a plan is a description, and a stale description is how a refusal gets skipped.

"Can this agent call anything" is asked of `grants.resolve_grant` and
`revocation.covered_grants` - the call path's own answer and Gate 11's own predicate. A
third spelling of "callable" here would be a third thing to keep in step.

WHAT IT DOES NOT DO
===================

    **The window ends, and nothing follows it** (decisions entry 81). The schema refuses an
    overlap and nothing refuses a gap. The difference from the bootstrap's eight hours is
    only that a named person chose this end. The success message says so.

    Manifest declaration, budget and rate limits are call-time checks with their own
    refusals. A shift promises the agent is on duty, not that a given call will pass.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from psycopg import AsyncConnection
from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from broker import grants, humans, revocation, shifts
from broker.errors import NotAuthorized, OfficeError

#: The weakest role that may put an agent on duty, checked against the venture's scope.
#: `ivan` and `compliance_officer` outrank it and pass.
REQUIRED_ROLE = "venture_operator"

#: How far in the past a window may start. A few minutes absorbs the time between reading
#: the report and confirming it; anything more is backdating a record of who was on duty.
BACKDATE_TOLERANCE = timedelta(minutes=5)


class StaffingError(Exception):
    """One or more checks refused the assignment. Nothing was written."""

    def __init__(self, refusals: list[str]) -> None:
        super().__init__("; ".join(refusals))
        self.refusals = refusals


@dataclass(frozen=True, slots=True)
class ModuleAnswer:
    """What the call path would say about one module this agent holds a grant for."""

    forge_id: str
    module_id: str
    grant_id: uuid.UUID | None
    refusal: str | None

    @property
    def resolves(self) -> bool:
        return self.refusal is None


@dataclass
class Plan:
    venture_id: str
    start: datetime | None
    end: datetime | None
    operator_id: uuid.UUID | None = None
    operator_name: str | None = None
    role_acted_as: str | None = None
    agent_id: uuid.UUID | None = None
    agent_name: str | None = None
    quarter: str | None = None
    venture_grants: int = 0
    venture_active_grants: int = 0
    modules: list[ModuleAnswer] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refusals

    @property
    def resolving(self) -> list[ModuleAnswer]:
        return [m for m in self.modules if m.resolves]


def parse_when(value: str, *, now: datetime) -> datetime:
    """`now`, or an ISO-8601 timestamp that says which timezone it is in.

    A naive timestamp is refused rather than assumed to be UTC or local. The shift is
    compared against the database's clock, and a guessed offset is a window hours away
    from the one the operator meant.
    """
    if value.strip().lower() == "now":
        return now
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{value!r} is not an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(
            f"{value!r} has no timezone. Give an offset (2026-09-15T18:00:00-07:00) or Z; "
            "a guessed offset is a window somewhere other than the one meant."
        )
    return parsed


async def _db_now(conn: AsyncConnection) -> datetime:
    """The clock `assert_on_shift_for` reads. A shift that starts "now" must be current by it."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT now()")
        row = await cur.fetchone()
    assert row is not None
    now: datetime = row[0]
    return now


async def _operator(conn: AsyncConnection, plan: Plan, email: str) -> None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT human_id, origin FROM office_human WHERE lower(email) = lower(%s)",
            (email.strip(),),
        )
        row = await cur.fetchone()
    if row is None:
        plan.refusals.append(f"operator: no account with email {email!r}")
        return
    if row["origin"] != "human":
        plan.refusals.append(
            f"operator: {email!r} is a {row['origin']} account. A shift records who put an "
            "agent on duty, and a fixture names nobody who can answer for it."
        )
        return

    human = await humans.get_human(conn, row["human_id"])
    if human is None:  # deleted between the two reads
        plan.refusals.append(f"operator: {email!r} could not be loaded")
        return
    plan.operator_id = human.human_id
    plan.operator_name = human.display_name
    try:
        plan.role_acted_as = humans.authorize(
            human, required_role=REQUIRED_ROLE, venture_id=plan.venture_id
        )
    except NotAuthorized as exc:
        plan.refusals.append(
            f"operator: {human.display_name} may not staff {plan.venture_id} - {exc.message}"
        )


async def _agent(conn: AsyncConnection, plan: Plan, agent: str) -> None:
    try:
        as_id: uuid.UUID | None = uuid.UUID(agent.strip())
    except ValueError:
        as_id = None
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT office_agent_id, agent_name, status FROM office_agent_identity "
            "WHERE office_agent_id = %s OR village_agent_ref = %s",
            (as_id, agent.strip()),
        )
        row = await cur.fetchone()
    if row is None:
        plan.refusals.append(
            f"agent: no Office identity for {agent!r} (an office_agent_id or a Village ref)"
        )
        return
    plan.agent_id = row["office_agent_id"]
    plan.agent_name = row["agent_name"]
    if row["status"] != "active":
        plan.refusals.append(f"agent: {row['agent_name']}'s identity is {row['status']}")


def _window(plan: Plan, now: datetime) -> None:
    if plan.start is None or plan.end is None:
        return
    if plan.end <= plan.start:
        plan.refusals.append("window: --end must be after --start")
    elif plan.end <= now:
        plan.refusals.append(f"window: it ended at {plan.end.isoformat()}, before now")
    if plan.start < now - BACKDATE_TOLERANCE:
        plan.refusals.append(
            f"window: it starts at {plan.start.isoformat()}, more than "
            f"{int(BACKDATE_TOLERANCE.total_seconds() // 60)} minutes ago. A shift is a "
            "record of who was on duty; it is not written after the fact."
        )


async def _authority(conn: AsyncConnection, plan: Plan) -> None:
    covered = await revocation.covered_grants(conn, venture_id=plan.venture_id)

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT grant_id, activated_at IS NOT NULL FROM agent_forge_grant "
            "WHERE venture_id = %s",
            (plan.venture_id,),
        )
        rows = await cur.fetchall()
    plan.venture_grants = len(rows)
    plan.venture_active_grants = sum(1 for gid, active in rows if active and gid not in covered)
    if plan.venture_active_grants == 0:
        plan.refusals.append(
            f"venture: {plan.venture_id} has no active grants ({plan.venture_grants} issued, "
            "0 activated and un-revoked). A shift here would put an agent on duty with "
            "nothing it may call. Grants are activated at Gate 11."
        )

    if plan.agent_id is None:
        return
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT forge_id, module_id FROM agent_forge_grant "
            "WHERE office_agent_id = %s AND venture_id = %s ORDER BY forge_id, module_id",
            (plan.agent_id, plan.venture_id),
        )
        pairs = await cur.fetchall()

    for forge_id, module_id in pairs:
        try:
            resolved = await grants.resolve_grant(
                conn, office_agent_id=plan.agent_id, forge_id=forge_id,
                module_id=module_id, venture_id=plan.venture_id,
            )
        except OfficeError as exc:
            plan.modules.append(
                ModuleAnswer(forge_id, module_id, None, f"{type(exc).__name__}: {exc.message}")
            )
            continue
        cover = covered.get(resolved.grant_id)
        plan.modules.append(
            ModuleAnswer(
                forge_id, module_id, resolved.grant_id,
                f"Revoked: {cover.scope} revocation - {cover.reason}" if cover else None,
            )
        )

    if not plan.resolving:
        held = len(plan.modules)
        plan.refusals.append(
            f"agent: {plan.agent_name} holds {held} grant(s) for {plan.venture_id} and none "
            "resolves. On shift it could call nothing."
        )


async def _shifts(conn: AsyncConnection, plan: Plan) -> None:
    if plan.agent_id is None:
        return

    if plan.start is not None and plan.end is not None and plan.end > plan.start:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT venture_id, shift_start, shift_end FROM shift_assignment "
                "WHERE office_agent_id = %s "
                "  AND tstzrange(shift_start, shift_end) && tstzrange(%s, %s) "
                "ORDER BY shift_start LIMIT 1",
                (plan.agent_id, plan.start, plan.end),
            )
            clash = await cur.fetchone()
        if clash is not None:
            plan.refusals.append(
                f"shift: overlaps {plan.agent_name}'s {clash['venture_id']} shift "
                f"{clash['shift_start'].isoformat()} to {clash['shift_end'].isoformat()}"
            )

    prior = await shifts.previous_shift(conn, plan.agent_id)
    if prior is not None and not prior["flush_verified"]:
        plan.refusals.append(
            f"shift: the previous {prior['venture_id']} shift has no verified PHI flush, "
            "and the next assignment is blocked until it does"
        )

    try:
        plan.quarter = await shifts.current_quarter()
    except shifts.QuarterUnknown as exc:
        plan.refusals.append(f"quarter: {exc.message}")
        return
    held = await shifts.quarter_venture(conn, plan.agent_id, plan.quarter)
    if held is not None and held != plan.venture_id:
        plan.refusals.append(
            f"quarter: {plan.agent_name} already works {held} in {plan.quarter}. One agent "
            "works one venture per agent-quarter."
        )


async def plan(
    conn: AsyncConnection,
    *,
    venture_id: str,
    agent: str,
    operator_email: str,
    start: str,
    end: str,
) -> Plan:
    """Every check, and nothing written."""
    now = await _db_now(conn)
    result = Plan(venture_id=venture_id, start=None, end=None)
    for label, value in (("start", start), ("end", end)):
        try:
            setattr(result, label, parse_when(value, now=now))
        except ValueError as exc:
            result.refusals.append(f"window: --{label} {exc}")

    await _operator(conn, result, operator_email)
    await _agent(conn, result, agent)
    _window(result, now)
    await _authority(conn, result)
    await _shifts(conn, result)
    return result


async def apply(
    conn: AsyncConnection,
    *,
    venture_id: str,
    agent: str,
    operator_email: str,
    start: str,
    end: str,
) -> tuple[Plan, uuid.UUID]:
    """Plan again, then write one shift through `assign_shift`. Raises StaffingError."""
    checked = await plan(
        conn, venture_id=venture_id, agent=agent, operator_email=operator_email,
        start=start, end=end,
    )
    if not checked.ok:
        raise StaffingError(checked.refusals)
    assert checked.agent_id and checked.operator_id and checked.start and checked.end

    try:
        shift_id = await shifts.assign_shift(
            conn,
            office_agent_id=checked.agent_id,
            venture_id=venture_id,
            shift_start=checked.start,
            shift_end=checked.end,
            assigned_by=checked.operator_id,
            # The quarter this plan resolved, not a second read: a roll-over between the
            # check and the write is how a second venture gets into a checked quarter.
            quarter=checked.quarter,
        )
    except (shifts.ShiftBlocked, shifts.QuarterConflict, shifts.QuarterUnknown) as exc:
        await conn.rollback()
        raise StaffingError([f"assign_shift: {exc.message}"]) from exc
    except pg_errors.ExclusionViolation as exc:
        # Something wrote a shift between the plan and the insert. The database is the
        # rule that holds; this only names which rule it was.
        await conn.rollback()
        name = exc.diag.constraint_name or "an exclusion constraint"
        raise StaffingError([f"shift: refused by {name} at write time"]) from exc
    return checked, shift_id


def describe(result: Plan) -> list[str]:
    """The report, as lines. Kept apart from the CLI so a test can read it."""
    lines = [
        f"Venture   {result.venture_id}",
        f"Operator  {result.operator_name or '-'}"
        + (f" (acting as {result.role_acted_as})" if result.role_acted_as else ""),
        f"Agent     {result.agent_name or '-'}"
        + (f" ({result.agent_id})" if result.agent_id else ""),
        f"Window    {result.start.isoformat() if result.start else '?'} to "
        f"{result.end.isoformat() if result.end else '?'}",
        f"Quarter   {result.quarter or 'unknown'}",
        f"Venture grants: {result.venture_active_grants} active of {result.venture_grants}",
    ]
    if result.modules:
        lines.append("Modules this agent holds a grant for:")
        for m in result.modules:
            verdict = "resolves" if m.resolves else m.refusal
            lines.append(f"  {m.forge_id + '/' + m.module_id:44} {verdict}")
    return lines
