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

from generators.artifacts import (
    AppointedAgent,
    Appointment,
    ApprovalProjection,
    DefinedPosition,
    RoleDefinition,
    Workflow,
)
from generators.pack import BusinessPack

#: Decisions per appointed agent per day, per workflow step. Conservative and named
#: rather than inline, because it is an estimate somebody will want to argue with - and
#: V13's whole job is to be argued with before a venture ships rather than after.
DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8


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

    approvals_by_role: dict[str, int] = {}

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
        for agent_id in holders:
            modules: list[str | None] = list(step.forge_modules) or [None]
            for module in modules:
                tier = _effective_tier(
                    _declared_tier(position, module, forge_of), appointed, agent_id
                )
                if tier == "auto_execute":
                    continue  # acts on its own; asks nobody
                reviewer = _reviewer_for(pack, list(position.effective_compliance_flags))
                approvals_by_role[reviewer] = (
                    approvals_by_role.get(reviewer, 0) + DEFAULT_DAILY_VOLUME_PER_HEADCOUNT
                )

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
    declared: str, appointed: list[AppointedAgent], agent_id: str | None
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
            return (
                declared
                if _TIER_RANK[declared] <= _TIER_RANK[a.certified_tier]
                else a.certified_tier
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
