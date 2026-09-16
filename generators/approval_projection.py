"""5.4 Approval Projection — what the humans will be asked to decide.

This replaces the Task Ledger Generator. The Village's Decomposer produces tasks with
owners and priorities from its ObjectiveBoard; two systems doing that job with no
arbitration between them is one system too many, and the Village's is the one wired to
agents that actually pull work.

WHAT IS NOT HERE ANY MORE

    task ids, owners, SLAs, per-task volumes, assignment. All of it was The Office
    deciding what an agent does and when, which is now the Village's.

WHAT SURVIVED, AND WHY

    `projected_daily_approvals` — how many decisions each human role will be handed per
    day. It is not a statement about agent work assignment at all; it is a statement
    about *human* capacity, and the Decomposer has no opinion about how many approvals a
    compliance officer can absorb before they stop reading them.

    It is the sole input to validator rule V13, which is what stops a venture shipping
    with more approvals than any human can absorb - the state in which trust tiers become
    decorative because the reviewer is clicking through. Deleting this with the rest of
    the generator would have deleted Gate 4.5's capacity check.

HOW IT IS COUNTED

    One projected item per workflow step per appointed agent, for every step whose
    effective trust tier is below `auto_execute` - an agent that acts on its own asks
    nobody. An unfilled position still counts at the position's ceiling: the estimate must
    not get cheaper because nobody was appointed.
"""

from __future__ import annotations

from typing import Any

from generators.artifacts import (
    AppointedAgent,
    Appointment,
    ApprovalProjection,
    DefinedPosition,
    RoleDefinition,
    Workflow,
)
from generators.pack import BusinessPack

# ------------------------------------------------------------------ declared volume
#
# `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8` used to live here: decisions per appointed agent
# per day, per workflow step, for every module of every venture. It is gone, and nothing
# falls back to it.
#
# It was an unattributed constant (entry 46) doing the work of a business fact. Greenstone
# projected 64 approvals a day against a venture closing one deal a week, and the figure
# moved when a headcount changed rather than when the business did.
#
# What replaces it is `Position.expected_weekly_volume`, declared per module with
# provenance, divided by `capacity_demand.operating_days_per_week`, which is also declared.
# **An undeclared module blocks and is named.** A default here is how the last one started.


class VolumeNotDeclaredError(Exception):
    """Raised when demand cannot be computed because the Pack did not say.

    Carries the unnamed modules so a caller can report them rather than restate the
    mechanism. V13 catches this at both gates and turns it into a FAIL naming each one;
    the generators let it raise, because by then Gate 2 has already refused.
    """

    def __init__(self, venture_id: str, missing: list[str], reason: str) -> None:
        self.venture_id = venture_id
        self.missing = missing
        self.reason = reason
        super().__init__(reason)


def daily_rate_of(pack: BusinessPack, position: DefinedPosition | Any, qualified: str) -> float:
    """The declared weekly volume for one module, as a daily rate.

    **Not multiplied by headcount, deliberately.** A rate is a property of the business,
    not of the roster: two Deal Underwriters do not make the venture close twice as many
    deals. The constant this replaces WAS per holder, which is why adding a headcount
    raised projected demand without anything happening in the world.
    """
    weekly = position.expected_weekly_volume.get(qualified)
    days = pack.capacity_demand.operating_days_per_week
    if weekly is None:
        raise VolumeNotDeclaredError(
            pack.venture_id, [f"{position.position_title}/{qualified}"],
            "no expected_weekly_volume declared",
        )
    if days is None:
        raise VolumeNotDeclaredError(
            pack.venture_id, [],
            "capacity_demand.operating_days_per_week is not declared, so a weekly "
            "volume cannot be converted to a daily rate",
        )
    return weekly / days


def modules_needing_volume(pack: BusinessPack) -> list[str]:
    """Every `position/forge/module` below `auto_execute` with no declared volume.

    **`auto_execute` modules are exempt and that is not a loophole.** Such a module asks
    nobody, so no volume of it can reach a reviewer; requiring a rate for it would be
    requiring a number that multiplies by zero. Lowering a module's tier later makes its
    volume newly required, and this is what names it.

    Read from the Pack alone, so Gate 2 and Gate 4.5 ask the same question.
    """
    missing: list[str] = []
    for position in pack.positions_required:
        if position.pending_activation is not None:
            # No agent demand, so no rate is required. The work is real and two humans do
            # it; what it does not do is queue an approval.
            continue
        for qualified in position.forge_modules_operated:
            tier = position.module_trust_tiers.get(qualified, position.trust_tier_ceiling)
            if tier == "auto_execute":
                continue
            if qualified not in position.expected_weekly_volume:
                missing.append(f"{position.position_title}/{qualified}")
    return sorted(missing)


def demand_from_the_pack(pack: BusinessPack) -> dict[str, float]:
    """Approvals a day per reviewer role, from the Pack alone - Gate 2's demand side.

    **This is the same quantity Gate 4.5 computes, by the same declared rates.** Before
    declared volume the two gates computed different things from different inputs: Gate 2
    multiplied headcount by a constant, Gate 4.5 walked the real workflow. Gate 2 was the
    optimistic one, by an order of magnitude, and both docstrings said so at length.

    They converge now. The one difference left is real and narrow: Gate 4.5 caps each
    module's tier by what its appointed agents are actually certified to, which does not
    exist at Gate 2. A module the Pack declares `propose` and every holder is certified
    `auto_execute` for counts here and not there.

    Raises `VolumeNotDeclaredError` naming every module, rather than answering from a default.
    """
    missing = modules_needing_volume(pack)
    if missing:
        raise VolumeNotDeclaredError(
            pack.venture_id, missing, "no expected_weekly_volume declared",
        )
    if pack.capacity_demand.operating_days_per_week is None and any(
        p.expected_weekly_volume for p in pack.positions_required
    ):
        raise VolumeNotDeclaredError(
            pack.venture_id, [],
            "capacity_demand.operating_days_per_week is not declared, so a weekly "
            "volume cannot be converted to a daily rate",
        )

    by_role: dict[str, float] = {}
    for position in pack.positions_required:
        if position.pending_activation is not None:
            continue
        # DECLARED FLAGS ONLY, BECAUSE AT GATE 2 THERE ARE NO OTHERS.
        #
        # Gate 4.5 routes by declared UNION implied, where implied comes from
        # `forge_module_registry.compliance_flags_implied` - a live world read that does not
        # exist at Gate 2. So a position whose reviewer is decided by an IMPLIED flag routes
        # to the venture operator here and to the compliance officer there.
        #
        # Measured, both live ventures, and it changes nothing on either today: CRE Forge's
        # five modules imply no flags at all since entry 105, and Burkham declares both of
        # its humans `compliance_officer`, so every route resolves to the same role whichever
        # flag set is used. It is a real divergence with no current instance, which is worth
        # more written down than discovered later.
        reviewer = _reviewer_for(pack, list(position.compliance_flags_in_scope))
        for qualified in position.forge_modules_operated:
            tier = position.module_trust_tiers.get(qualified, position.trust_tier_ceiling)
            if tier == "auto_execute":
                continue
            by_role[reviewer] = by_role.get(reviewer, 0.0) + daily_rate_of(
                pack, position, qualified
            )
    return dict(sorted(by_role.items()))


def generate(
    pack: BusinessPack,
    roles: RoleDefinition,
    workflow: Workflow,
    appointment: Appointment,
    module_forge: dict[str, str] | None = None,
) -> ApprovalProjection:
    by_title = {p.position_title: p for p in roles.positions}
    # Defaulted so every existing caller keeps working: with no map, no key resolves and every
    # module falls back to the position ceiling - which is exactly the behaviour before
    # per-module tiers existed.
    forge_of = module_forge or {}
    appointed_by_title = {a.position_title: a.appointed for a in appointment.appointments}

    approvals_by_role: dict[str, float] = {}

    for step in workflow.steps:
        position = by_title[step.position]
        appointed = appointed_by_title.get(step.position, [])

        # One projection per appointed agent. An unfilled position still produces one,
        # at the ceiling: the work exists whether or not anybody was appointed to it, and
        # a projection that shrank when a position went unfilled would make a shortfall
        # look like relief.
        holders: list[str | None] = [a.office_agent_id for a in appointed] or [None]

        # Per (step, holder, MODULE), not per (step, holder).
        #
        # A step touching three modules at one tier counted once and still does - the
        # modules collapse to a single decision when they share a tier. What changed is that
        # they no longer have to share one: an `auto_execute` module contributes zero even
        # where the position's ceiling is `propose`, which is the whole point of a per-module
        # declaration and is lost if the count stays per step.
        #
        # A step naming NO module still counts once, at the position's tier. Such a step is
        # work the position does that reaches no Forge, and it is a human decision or it is
        # nothing - `or [None]` keeps it in the projection rather than silently dropping it.
        if position.pending:
            # Ruling: a pending position adds no agent demand. Its steps stay in the
            # workflow marked `human_held` - the work happens, a founder does it, and the
            # hours land in `other_hours` rather than in an approval queue.
            continue

        if not step.forge_modules:
            # A step reaching no Forge. The generator no longer emits one - it emits one
            # step per declared module - and a rate cannot be declared for a module that
            # does not exist, so this refuses rather than inventing one.
            #
            # It used to count once at the position's tier, on the reasoning that such a
            # step is "a human decision or it is nothing". That was right while every step
            # cost the same constant; there is no constant now, and guessing one here would
            # be the only place in the projection that still had one.
            raise VolumeNotDeclaredError(
                pack.venture_id,
                [f"{step.position}/step {step.number}"],
                "a workflow step names no module, so no declared volume applies to it",
            )

        for module in step.forge_modules:
            forge = forge_of.get(module)
            qualified = f"{forge}/{module}" if forge else module

            # THE TIER IS TAKEN ACROSS HOLDERS, NOT PER HOLDER.
            #
            # The volume is one rate for the module - the business runs `assign_contract`
            # so many times a week however many agents hold it - so it is counted once.
            # What still varies per holder is certification, and the most restrictive one
            # wins: if any appointed agent runs this module at `propose`, that agent's
            # share of the volume reaches a reviewer, and a projection that took the
            # strongest certification would report zero for work that is being reviewed.
            #
            # Erring restrictive is the same direction the old per-holder count erred, and
            # V13's own message says which way to be wrong: under-estimating produces a
            # green check on a reviewer who is already saturated.
            tiers = [
                _effective_tier(
                    _declared_tier(position, module, forge_of), appointed, agent_id, qualified
                )
                for agent_id in holders
            ]
            if all(t == "auto_execute" for t in tiers):
                continue  # acts on its own; asks nobody
            reviewer = _reviewer_for(pack, list(position.effective_compliance_flags))
            approvals_by_role[reviewer] = approvals_by_role.get(
                reviewer, 0.0
            ) + daily_rate_of(pack, position, qualified)

    return ApprovalProjection(
        venture_id=pack.venture_id,
        projected_daily_approvals=dict(sorted(approvals_by_role.items())),
    )


def _declared_tier(
    position: DefinedPosition, module: str | None, forge_of: dict[str, str]
) -> str:
    """What the Pack declares for this module, falling back to the position's ceiling.

    Keys are `forge_id/module_id`, so the Forge has to be resolved before the lookup.

    **An unresolved module falls back to the ceiling rather than raising.** A module absent
    from the registry is V6's finding and it blocks at Gate 2; making the projection throw
    would replace a named rule failure with a stack trace one gate earlier.

    `None` is a step naming no module - work that reaches no Forge - and it cannot carry a
    per-module override.
    """
    if module is None:
        return position.trust_tier_ceiling
    forge = forge_of.get(module)
    if forge is None:
        return position.trust_tier_ceiling
    return position.module_trust_tiers.get(
        f"{forge}/{module}", position.trust_tier_ceiling
    )


#: The tier ladder, ranked. Mirrors `runtime_config._TIER_RANK` and
#: `broker.certification.TIER_RANK`; `generators` does not import `broker`.
_TIER_RANK = {"suggest": 1, "propose": 2, "auto_execute": 3}


def _effective_tier(
    declared: str, appointed: list[AppointedAgent], agent_id: str | None, key: str | None = None
) -> str:
    """The tier this work actually runs at: the LOWER of declared and certified.

    An unfilled position falls back to the declared tier - the estimate must not get cheaper
    because nobody was appointed.

    **It used to return `certified_tier` outright for an appointed agent, and that silently
    discarded a per-module declaration.** `AppointedAgent.certified_tier` is one value for the
    whole position (5.2 takes the weakest across its modules), so a Pack declaring
    `client_read: auto_execute` under a `propose` position got the agent's single certified
    tier for every module and the override did nothing. Measured: a filled Burkham reported
    zero approvals where the per-module tally said 80.

    Both directions cap. Certification cannot raise what the Pack declares, and the Pack
    cannot raise what an agent is certified to - which is Part 10.1 read per module instead of
    per position.
    """
    for a in appointed:
        if a.office_agent_id == agent_id:
            # This module's own certified tier. `certified_tiers` replaced a position-wide
            # scalar on 13 September 2026 - reading that scalar here is what made every
            # per-module declaration inert, because one `propose` module set the floor for
            # every `auto_execute` one beside it.
            certified = a.certified_tiers.get(key or "") if key else None
            if certified is None:
                # No entry for this module: it is not one this agent was appointed for, so
                # the declaration stands uncapped. Falling back to the weakest of the map
                # would reintroduce the floor this change removed.
                return declared
            return (
                declared if _TIER_RANK[declared] <= _TIER_RANK[certified] else certified
            )
    return declared


def _reviewer_for(pack: BusinessPack, flags: list[str]) -> str:
    """Which human role reviews this.

    Compliance-flagged work routes to the compliance officer where one exists; everything
    else to the venture operator. Falls back to the first declared human rather than
    inventing a role that has no coverage hours behind it - a projection against a role
    nobody staffs would divide by zero in V13 and read as infinite overload.
    """
    roles = {h.role for h in pack.human_capacity}
    if flags and "compliance_officer" in roles:
        return "compliance_officer"
    if "venture_operator" in roles:
        return "venture_operator"
    return sorted(roles)[0]
