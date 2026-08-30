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
) -> ApprovalProjection:
    by_title = {p.position_title: p for p in roles.positions}
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

        for agent_id in holders:
            tier = _effective_tier(position.trust_tier_ceiling, appointed, agent_id)
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


def _effective_tier(
    ceiling: str, appointed: list[AppointedAgent], agent_id: str | None
) -> str:
    """The tier this work actually runs at.

    An unfilled position falls back to the ceiling: the estimate must not get cheaper
    because nobody was appointed.
    """
    for a in appointed:
        if a.office_agent_id == agent_id:
            return a.certified_tier
    return ceiling


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
