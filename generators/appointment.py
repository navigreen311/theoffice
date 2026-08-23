"""5.2 Appointment Generator.

In: positions + the Village roster + certification state. Out: a named agent per
position, and the gap report.

**The Office appoints agents. It does not create them.** The Village produces agents;
The Office appoints them to venture positions and revokes them.

Three rules from master prompt 5.2 and §7.3, and all three are prohibitions:

  * Appointment requires **Unit A for every module the position operates**, and **Unit B
    for every Forge that position touches**. Both. Department certification is
    necessary, never sufficient.
  * An uncertified candidate appears as `requires_certification`, **never as filled**.
  * A shortfall does not auto-reject the Pack, does not auto-appoint an uncertified
    agent, and does not silently reduce scope. It flags to Ivan with the three capacity
    numbers.

**A position can span Forges, and certification is per Forge.** Greenstone's Acquisition
Analyst operates `property_lookup` and `comp_analysis` on CRE Forge *and* `place_call`
on VoiceForge. Unit A is `agent x forge x module`, so each module is checked against its
own Forge, and Unit B is required for every Forge involved rather than one nominated
"operating Forge". Assuming a single Forge per position silently produces an empty
appointment that reads like a certification backlog — found by reading a golden snapshot.

The three numbers (§7.2) exist because one number hides the state. "Certified and free:
2" looks like a hiring problem. Add "certified but allocated elsewhere: 9" and it is a
scheduling problem. Add "produced but not yet certified: 14" and it is a SimForge
backlog. Three different responses, and reporting only the first sends you to the wrong
one.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from generators.artifacts import (
    AppointedAgent,
    Appointment,
    CandidateShortfall,
    CapacityNumbers,
    PositionAppointment,
    RoleDefinition,
)

TIER_RANK = {"suggest": 1, "propose": 2, "auto_execute": 3}


async def module_forge_map(conn: AsyncConnection) -> dict[str, str]:
    """module_id -> forge_id, from the registry.

    A module belongs to exactly one Forge, so this is a lookup rather than a choice.
    Callers must not assume the venture's `operating_forge` owns every module a
    position operates.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT module_id, forge_id FROM forge_module_registry")
        return dict(await cur.fetchall())


async def generate(
    roles: RoleDefinition,
    conn: AsyncConnection,
    *,
    venture_id: str,
    module_forge: dict[str, str] | None = None,
) -> Appointment:
    forge_of = module_forge if module_forge is not None else await module_forge_map(conn)

    appointments: list[PositionAppointment] = []
    certified_free = 0
    certified_allocated = 0
    produced_uncertified = 0

    for position in roles.positions:
        modules = position.forge_modules_operated
        forges_touched = sorted({forge_of[m] for m in modules if m in forge_of})
        unresolved = [m for m in modules if m not in forge_of]

        candidates = await _candidates(conn, position.source_department)
        unit_a = await _unit_a_certs(conn, [c["office_agent_id"] for c in candidates])
        unit_b = await _unit_b_certs(conn, position.source_department, forges_touched)

        eligible: list[AppointedAgent] = []
        shortfalls: list[CandidateShortfall] = []

        for row in candidates:
            agent_id = str(row["office_agent_id"])

            if unresolved:
                # The modules do not resolve to a Forge at all, so nobody can be
                # certified for them. V6 is the gate that blocks on this; reporting
                # it per candidate here would bury the real cause.
                shortfalls.append(
                    CandidateShortfall(agent_id, row["agent_name"], "module_not_registered")
                )
                continue

            certs = unit_a.get(agent_id, {})
            missing = [
                m for m in modules if certs.get((forge_of[m], m), ("never_certified",))[0]
                != "certified"
            ]

            if missing:
                # Name the specific state, never collapse to "not eligible": the fix
                # for `in_training` is to wait, and the fix for `never_certified` is
                # to submit a curriculum.
                reason = sorted(
                    certs.get((forge_of[m], m), ("never_certified", None))[0]
                    for m in missing
                )[0]
                shortfalls.append(CandidateShortfall(agent_id, row["agent_name"], reason))
                if reason in ("never_certified", "in_training"):
                    produced_uncertified += 1
                continue

            missing_unit_b = [f for f in forges_touched if unit_b.get(f) != "certified"]
            if missing_unit_b:
                shortfalls.append(
                    CandidateShortfall(agent_id, row["agent_name"], "missing_unit_b")
                )
                produced_uncertified += 1
                continue

            # Weakest certified tier across every module operated, then capped by the
            # position ceiling. An agent certified auto_execute on four modules and
            # propose on the fifth operates the position at propose.
            weakest = min(
                (certs[(forge_of[m], m)][1] or "suggest" for m in modules),
                key=lambda t: TIER_RANK[t],
                default="suggest",
            )
            eligible.append(
                AppointedAgent(
                    office_agent_id=agent_id,
                    agent_name=row["agent_name"],
                    department=row["department"],
                    certified_modules=sorted(modules),
                    certified_tier=_cap(position.trust_tier_ceiling, weakest),
                )
            )

        # Deterministic: candidates arrive ordered by (agent_name, office_agent_id),
        # so two runs against the same roster appoint the same agents.
        appointed = eligible[: position.headcount]
        certified_free += len(appointed)
        certified_allocated += max(0, len(eligible) - position.headcount)

        appointments.append(
            PositionAppointment(
                position_title=position.position_title,
                headcount_required=position.headcount,
                appointed=appointed,
                unfilled=max(0, position.headcount - len(appointed)),
                requires_certification=sorted(
                    shortfalls, key=lambda s: (s.agent_name, s.office_agent_id)
                ),
            )
        )

    shortfall = any(a.unfilled for a in appointments)
    capacity = CapacityNumbers(
        certified_and_free=certified_free,
        certified_but_allocated=certified_allocated,
        produced_not_yet_certified=produced_uncertified,
    )

    return Appointment(
        venture_id=venture_id,
        appointments=appointments,
        capacity=capacity,
        shortfall=shortfall,
        escalation=_escalation(shortfall, appointments, capacity),
    )


async def _candidates(
    conn: AsyncConnection, department: str
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT office_agent_id, agent_name, department FROM office_agent_identity "
            "WHERE status = 'active' AND department = %s "
            "ORDER BY agent_name, office_agent_id",
            (department,),
        )
        return list(await cur.fetchall())


async def _unit_a_certs(
    conn: AsyncConnection, agent_ids: list[Any]
) -> dict[str, dict[tuple[str, str], tuple[str, str | None]]]:
    """(agent) -> {(forge, module): (state, certified_tier)}.

    State and tier travel together because every caller needs both, and splitting
    them into two lookups is how they end up disagreeing about which cert they
    describe.
    """
    if not agent_ids:
        return {}
    out: dict[str, dict[tuple[str, str], tuple[str, str | None]]] = {}
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT office_agent_id, forge_id, module_id, state, certified_tier "
            "FROM certification WHERE unit = 'A' AND office_agent_id = ANY(%s)",
            (list(agent_ids),),
        )
        for row in await cur.fetchall():
            key = str(row["office_agent_id"])
            out.setdefault(key, {})[(row["forge_id"], row["module_id"])] = (
                row["state"], row["certified_tier"]
            )
    return out


async def _unit_b_certs(
    conn: AsyncConnection, department: str, forges: list[str]
) -> dict[str, str]:
    if not forges:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT forge_id, state FROM certification "
            "WHERE unit = 'B' AND department = %s AND forge_id = ANY(%s)",
            (department, forges),
        )
        return dict(await cur.fetchall())


def _cap(ceiling: str, certified: str) -> str:
    """Part 10.1: certified tier caps declared tier. The lower always wins."""
    return ceiling if TIER_RANK[ceiling] <= TIER_RANK[certified] else certified


def _escalation(
    shortfall: bool, appointments: list[PositionAppointment], capacity: CapacityNumbers
) -> str:
    if not shortfall:
        return "No shortfall. All positions filled by certified agents."
    unfilled = ", ".join(
        f"{a.position_title} ({a.unfilled} of {a.headcount_required})"
        for a in appointments
        if a.unfilled
    )
    return (
        f"CAPACITY SHORTFALL - flag to Ivan for decision. Unfilled: {unfilled}. "
        f"Certified and free: {capacity.certified_and_free}; "
        f"certified but allocated elsewhere: {capacity.certified_but_allocated}; "
        f"produced but not yet certified: {capacity.produced_not_yet_certified}. "
        "The Pack is NOT auto-rejected, no uncertified agent is appointed, and scope "
        "is not silently reduced."
    )
