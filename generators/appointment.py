"""5.2 Appointment Generator.

In: positions + the Village roster + certification state. Out: a named agent per
position, and the gap report.

**The Office appoints agents. It does not create them.** The Village produces agents;
The Office appoints them to venture positions and revokes them.

RULED 21 SEPTEMBER 2026 (entry 145), SUPERSEDING 5.2 AS APPLIED AT GATE 4.5
===========================================================================

    *"Gate 4.5 checks that every seat has a candidate eligible to sit the exam.
    Certification is required at Gate 11, where authority is granted. An appointment at
    4.5 issues an inactive grant and confers no authority; it is an exam ticket. 'Never
    auto-appoint uncertified agents' stands, meaning production authority."*

    5.2's rule was applied at the wrong end, and the cost was a closed loop: 4.5 seated
    only certified agents, Gate 5 granted only to the seated, Gate 8 examined only
    grant holders, and the sweep certified only the examined. **No agent could ever
    become certified without an off-ladder bootstrap certification.** Recorded as entry
    30 on 13 September and hidden for eight days by bootstrap rows, until the first
    verdict-ingest sweep replaced them with what SimForge actually said and three
    positions emptied.

ELIGIBLE, PRECISELY, AND WHERE EACH PART IS READ FROM
=====================================================

    A candidate is **eligible to sit the exam** when all three hold. Each is a thing
    Gate 8 requires before it can open a run for that agent, and nothing else is:

      1. `office_agent_identity.status = 'active'`, and `department` equal to the
         position's `source_department`. Read by `_candidates` in this module, and the
         same predicate `_exam_takers` joins and Gate 11 requires.
      2. Every module the position operates resolves to a Forge in
         `forge_module_registry`. Read by `module_forge_map`. A module no Forge
         registers cannot be submitted - Gate 8 skips it by name - so nobody can sit it.
      3. No live revocation covers `(agent, forge, module)` for any of those modules.
         Read by `revocation.covered_targets`, which is `_covers` at a third
         cardinality. `_exam_takers` drops a revoked holder, so a revoked candidate
         would fill a seat whose exam nobody ever sits.

    **Certification is not in the list**, and that is the whole ruling. A live operating
    instruction is not in it either: Gate 6 blocks a module that has none, and restating
    it here would report a Gate 6 finding as an empty seat.

WHAT STANDS UNCHANGED
=====================

  * Appointment requires **Unit A for every module the position operates**, and **Unit B
    for every Forge that position touches**, to be CERTIFIED. Both. Department
    certification is necessary, never sufficient. `AppointedAgent.certified` carries it,
    Gate 11 enforces it, and `resolve_grant` refuses every call without it.
  * An uncertified candidate appears as `requires_certification` with the specific state
    that explains it. It may now also appear in `appointed`, holding an exam ticket and
    no authority.
  * A shortfall does not auto-reject the Pack, does not auto-appoint an uncertified
    agent into AUTHORITY, and does not silently reduce scope. It flags to Ivan with the
    three capacity numbers.

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

from broker import certification, escalation, revocation
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
    live_grants = await _live_grants(conn, venture_id)

    appointments: list[PositionAppointment] = []
    certified_free = 0
    certified_allocated = 0
    produced_uncertified = 0

    for position in roles.positions:
        modules = position.module_ids
        forges_touched = sorted({forge_of[m] for m in modules if m in forge_of})
        unresolved = [m for m in modules if m not in forge_of]

        candidates = await _candidates(conn, position.source_department)
        unit_a = await _unit_a_certs(conn, [c["office_agent_id"] for c in candidates])
        unit_b = await _unit_b_certs(conn, position.source_department, forges_touched)

        # ELIGIBILITY'S THIRD TEST, ASKED ONCE PER POSITION - see this module's header.
        # A candidate holds no grant for the module yet, so `covered_grants` cannot see
        # it; `covered_targets` asks the same four scopes about a triple that has none.
        covered = await revocation.covered_targets(
            conn,
            venture_id=venture_id,
            targets=[
                (str(row["office_agent_id"]), forge_of[m], m)
                for row in candidates for m in modules if m in forge_of
            ],
        )

        eligible: list[AppointedAgent] = []
        shortfalls: list[CandidateShortfall] = []

        for row in candidates:
            agent_id = str(row["office_agent_id"])

            if unresolved:
                # The modules do not resolve to a Forge at all, so nobody can sit an
                # exam for them and nobody can be certified for them. V6 is the gate
                # that blocks on this; reporting it per candidate here would bury the
                # real cause.
                shortfalls.append(
                    CandidateShortfall(agent_id, row["agent_name"], "module_not_registered")
                )
                continue

            if any((agent_id, forge_of[m], m) in covered for m in modules):
                # NOT ELIGIBLE, and this is the test that stops the change being a
                # loosening. `_exam_takers` drops a revoked holder, so a revoked
                # candidate appointed here would fill a seat whose exam nobody sits -
                # a position that reads filled and produces nothing.
                shortfalls.append(
                    CandidateShortfall(agent_id, row["agent_name"], "revoked")
                )
                continue

            certs = unit_a.get(agent_id, {})
            missing = [
                m for m in modules if certs.get((forge_of[m], m), ("never_certified",))[0]
                != "certified"
            ]
            missing_unit_b = [f for f in forges_touched if unit_b.get(f) != "certified"]

            if missing or missing_unit_b:
                # STILL A SHORTFALL, AND NOW ALSO STILL A CANDIDATE. Ruled 21 September
                # 2026, entry 145: Gate 4.5 checks that a seat has somebody who can sit
                # the exam, and certification is required at Gate 11 where authority is
                # granted. So this appears in `requires_certification` exactly as it
                # always did - the gap report still says who is not certified and why -
                # and is no longer struck off the eligible list for it.
                #
                # Name the specific state, never collapse to "not eligible": the fix
                # for `in_training` is to wait, and the fix for `never_certified` is
                # to submit a curriculum. Unit B is named only when unit A is complete,
                # so a candidate missing both is sent to the more basic one first.
                reason = (
                    "missing_unit_b" if not missing
                    else sorted(
                        certs.get((forge_of[m], m), ("never_certified", None))[0]
                        for m in missing
                    )[0]
                )
                shortfalls.append(CandidateShortfall(agent_id, row["agent_name"], reason))
                if reason in ("never_certified", "in_training", "missing_unit_b"):
                    produced_uncertified += 1

            # One tier per module: the lower of what the Pack declares for THAT module and
            # what this agent is certified to for it.
            #
            # This replaced a position-wide floor - the weakest certified tier across every
            # module, capped by the ceiling - on 13 September 2026. See
            # `AppointedAgent.certified_tiers` for the property that was given up and why.
            #
            # Keyed `forge_id/module_id`, matching the Pack's `module_trust_tiers`, so the two
            # are looked up the same way and cannot drift in spelling.
            #
            # AN UNCERTIFIED MODULE HAS NO PLANNED TIER, AND THE KEY IS ABSENT.
            #
            # Ruled 21 September 2026: *"An uncertified module's planned tier reads as
            # none, not the declared tier. A plan that claims authority nothing earned
            # reads as authority."*
            #
            # The first draft of this took the declared tier, on the argument that the
            # old `.get(key, declared)` fallback already did. It did - and the fallback
            # was only ever reached for a module the agent WAS certified on with a NULL
            # `certified_tier`. Once a seat could be held by an uncertified agent, the
            # same line started writing `auto_execute` onto a plan nothing had earned,
            # and `agent_forge_grant.trust_tier` is the column `resolve_grant` caps a
            # live call against.
            #
            # Absent, never blank and never a floor. `suggest` would be the tempting
            # placeholder and it is still an authority level - entry 122's rule, and the
            # reason 0049 makes the grant's column nullable rather than defaulting it.
            tiers = {}
            for m in modules:
                if m in missing:
                    continue
                key = f"{forge_of[m]}/{m}"
                declared = position.module_trust_tiers.get(key, position.trust_tier_ceiling)
                tiers[key] = _cap(declared, certs[(forge_of[m], m)][1] or "suggest")

            eligible.append(
                AppointedAgent(
                    office_agent_id=agent_id,
                    # HOW MUCH OF THIS SEAT THIS CANDIDATE ALREADY HOLDS. Counted rather
                    # than reduced to a flag: a candidate holding a grant for both of a
                    # position's modules is more the incumbent than one holding a grant
                    # for one of them, and a threshold would have had to pick a number
                    # nobody ruled. Descending, so full incumbency outranks partial and
                    # partial outranks none.
                    live_grants=sum(
                        live_grants.get((agent_id, forge_of[m], m), 0) for m in modules
                    ),
                    agent_name=row["agent_name"],
                    department=row["department"],
                    # EVERY MODULE THE POSITION OPERATES - the exam roster. `certified_modules`
                    # is the subset already earned, and the two were one list until entry 145:
                    # building grants from the earned subset meant an uncertified appointee got
                    # no grant, so `_exam_takers` found nobody and the exam that would have
                    # certified them was never set.
                    modules=sorted(modules),
                    certified_modules=sorted(m for m in modules if m not in missing),
                    certified_tiers=tiers,
                    # THE DISTINCTION THE GAP REPORT KEEPS. Unit A on every module and unit B
                    # on every Forge - both, exactly as 5.2 requires. What moved is where it is
                    # enforced, not what it means.
                    certified=not missing and not missing_unit_b,
                )
            )

        # THE ORDER SEATS ARE FILLED IN. Three keys, and the first two are the whole of
        # the rule; the third is a last resort that has to say so.
        #
        #   1. LIVE GRANTS HELD, descending. Ruled 21 September 2026: eligibility prefers
        #      an existing live grant holder for the seat, and a seat does not change
        #      hands because of list order. A grant is what an exam is opened against, so
        #      moving a seat away from a holder discards an exam in flight.
        #   2. CERTIFIED, first. With more eligible candidates than seats, seating an
        #      uncertified one while a certified one waited would turn a position that
        #      can operate today into one waiting on an exam.
        #   3. ROSTER ORDER, which `_candidates` already fixed as
        #      `(agent_name, office_agent_id)`. `sort` is stable, so this needs no key -
        #      and **when it decides a seat, `_tie_break` says so.**
        eligible.sort(key=lambda a: (-a.live_grants, not a.certified))
        tie_break = _tie_break(eligible, position.headcount)

        # A PENDING position appoints nobody and reports no shortfall. Its headcount is not
        # a gap to fill - it is a number somebody deferred on purpose, and appointing into
        # it would give an agent authority over work the ruling says two humans do.
        if position.pending:
            appointments.append(
                PositionAppointment(
                    position_title=position.position_title,
                    headcount_required=position.headcount,
                    appointed=[],
                    unfilled=0,
                    requires_certification=[],
                    pending=True,
                )
            )
            continue
        appointed = eligible[: position.headcount]
        # COUNTED ON `certified`, NOT ON `len(appointed)`. Section 7.2's first number means
        # what it says, and an appointment that now includes uncertified candidates would
        # otherwise make it read as a staffing level that can operate today.
        certified_free += sum(1 for a in appointed if a.certified)
        certified_allocated += sum(
            1 for a in eligible[position.headcount:] if a.certified
        )

        appointments.append(
            PositionAppointment(
                position_title=position.position_title,
                headcount_required=position.headcount,
                appointed=appointed,
                unfilled=max(0, position.headcount - len(appointed)),
                requires_certification=sorted(
                    shortfalls, key=lambda s: (s.agent_name, s.office_agent_id)
                ),
                tie_break=tie_break,
            )
        )

    # SHORTFALL STILL MEANS "THIS VENTURE CANNOT FULLY OPERATE", which is the condition
    # 7.3 escalates on. Entry 145 moved what Gate 4.5 BLOCKS on; nobody ruled that Ivan
    # stops being told.
    #
    # A seat held by an uncertified candidate is a capacity shortfall in 7.2's sense -
    # the work cannot be done today - and reading this off `unfilled` alone would have
    # silently switched the governance escalation off on the day seats stopped emptying.
    # That is the loosening this change must not smuggle in.
    shortfall = any(a.unfilled for a in appointments) or any(
        not agent.certified for a in appointments for agent in a.appointed
    )
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
        # Stated on the artifact rather than left to whoever reads the sentence. The
        # recipient is resolved at delivery by `broker.escalation.governance`, which
        # refuses to name a test fixture; what is fixed here is which of the two routes
        # a shortfall may take, and it is never the one inside the Village.
        escalation_path=escalation.Path.GOVERNANCE.value,
    )


async def _live_grants(
    conn: AsyncConnection, venture_id: str
) -> dict[tuple[str, str, str], int]:
    """(agent, forge, module) -> 1 for every live grant this venture holds.

    RULED 21 SEPTEMBER 2026: *"Eligibility prefers an existing live grant holder for the
    seat. Roster order is a tie-break only when no candidate holds a grant... A seat does
    not change hands because of list order."*

    **A grant is what an exam is opened against.** `_exam_takers` returns the holders of
    a live grant, so a candidate holding one either has an exam in flight or has sat one.
    Moving the seat to somebody else discards that: entry 144's first measurement had
    `buyer_match`'s two seats pass from Ronan and Seraphine Valek - both with exams
    IN_PROGRESS and one with a recorded FAIL - to two candidates who came earlier in the
    roster and had never been examined.

    `superseded_at IS NULL` only. A revoked holder is excluded from eligibility
    altogether, one test earlier, so it never reaches the ranking - and excluding it here
    as well would be a second spelling of `covered_targets`.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT office_agent_id, forge_id, module_id FROM agent_forge_grant "
            " WHERE venture_id = %s AND superseded_at IS NULL",
            (venture_id,),
        )
        return {(str(a), f, m): 1 for a, f, m in await cur.fetchall()}


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
    """This department's Unit B state per Forge, as appointment should read it.

    **A VOID SIMULATION CERTIFICATION READS AS `simulation_certification_void`, NOT AS
    `certified`.** Entry 167: a simulation certification is void the moment its venture
    leaves simulation, and the row still says `certified` because nothing here rewrites
    a certification.

    Reported as its own state rather than dropped, because this function's caller uses
    the value to explain a shortfall - "never_certified" would send somebody to earn a
    certification that exists, and a missing key would read as a Forge nobody has
    touched.
    """
    if not forges:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT forge_id, "
            f"       CASE WHEN {certification.certified_and_live('c')} THEN c.state "
            "            WHEN c.simulation_ref IS NOT NULL "
            "              THEN 'simulation_certification_void' "
            "            ELSE c.state END AS state "
            "  FROM certification c "
            " WHERE c.unit = 'B' AND c.department = %s AND c.forge_id = ANY(%s)",
            (department, forges),
        )
        return dict(await cur.fetchall())


def _cap(ceiling: str, certified: str) -> str:
    """Part 10.1: certified tier caps declared tier. The lower always wins."""
    return ceiling if TIER_RANK[ceiling] <= TIER_RANK[certified] else certified


def _tie_break(eligible: list[AppointedAgent], headcount: int) -> str | None:
    """The sentence a seat decided by roster order owes its reader, or None.

    RULED 21 SEPTEMBER 2026: *"the tie-break is reported, never silent."*

    A tie-break happened when the last candidate seated and the first left out are
    **indistinguishable on every key that is a reason** - grants held and certification -
    so the only thing that separated them was where their names fall in the roster. That
    is a real decision about who operates a venture, taken on alphabetical order, and it
    should never be read off a list quietly.

    `None` when the boundary is not a tie: somebody was seated over somebody else because
    they hold more of the seat already, or because they are certified and the other is
    not. Those are reasons, and they are reported by the fields they are read from.
    """
    if len(eligible) <= headcount or headcount <= 0:
        return None
    seated, passed_over = eligible[headcount - 1], eligible[headcount]
    if (seated.live_grants, seated.certified) != (
        passed_over.live_grants, passed_over.certified
    ):
        return None
    holding = (
        f"both hold {seated.live_grants} live grant(s) for this position"
        if seated.live_grants else "neither holds a grant for this position"
    )
    standing = "both certified" if seated.certified else "neither certified"
    return (
        f"roster order decided the last seat: {seated.agent_name} over "
        f"{passed_over.agent_name} - {holding} and {standing}, so nothing but the "
        "alphabet separated them"
    )


def _escalation(
    shortfall: bool, appointments: list[PositionAppointment], capacity: CapacityNumbers
) -> str:
    """§7.3. The path it travels is on the artifact beside it.

    The three numbers and the four closing clauses are unchanged. What the sentence
    gained in entry 145 is a second way to be short: a seat nobody eligible can fill,
    and a seat filled by somebody who cannot yet operate it. Both are "flag to Ivan",
    and telling them apart is the point of naming them separately.
    """
    escalation.assert_path("capacity_shortfall", escalation.Path.GOVERNANCE)
    if not shortfall:
        return "No shortfall. All positions filled by certified agents."
    unfilled = ", ".join(
        f"{a.position_title} ({a.unfilled} of {a.headcount_required})"
        for a in appointments
        if a.unfilled
    ) or "none"
    waiting = ", ".join(
        f"{a.position_title} ({sum(1 for x in a.appointed if not x.certified)} of "
        f"{a.headcount_required})"
        for a in appointments
        if any(not x.certified for x in a.appointed)
    )
    seated = f" Seated and awaiting certification: {waiting}." if waiting else ""
    return (
        f"CAPACITY SHORTFALL - flag to Ivan for decision. Unfilled: {unfilled}.{seated} "
        f"Certified and free: {capacity.certified_and_free}; "
        f"certified but allocated elsewhere: {capacity.certified_but_allocated}; "
        f"produced but not yet certified: {capacity.produced_not_yet_certified}. "
        "The Pack is NOT auto-rejected, no uncertified agent is granted production "
        "authority, and scope is not silently reduced."
    )
