"""5.4 Task Ledger Generator.

In: Workflow + Appointments. Out: every task owned, tiered, SLA'd and volume-estimated.

Master prompt 5.4 names one output as required in its own right: **projected daily
approval volume per human role.** That number is the input to validator rule V13, and
V13 is what stops a venture shipping with more approvals than any human can absorb —
the state in which trust tiers become decorative.

`task_id` is UUIDv5 over (venture, step, position, module, agent), so re-running the
generator produces the same ids. A task that changes id every run cannot be reconciled
against the ledger rows it produced.
"""

from __future__ import annotations

from generators.artifacts import (
    AppointedAgent,
    Appointment,
    LedgerTask,
    RoleDefinition,
    TaskLedger,
    Workflow,
    derive_id,
)
from generators.pack import BusinessPack

# Conservative defaults until real volumes exist. Named constants rather than inline
# magic numbers, because these are estimates someone will want to argue with.
DEFAULT_SLA_MINUTES = {"auto_execute": 15, "propose": 240, "suggest": 480}
DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8


def generate(
    pack: BusinessPack,
    roles: RoleDefinition,
    workflow: Workflow,
    appointment: Appointment,
    *,
    module_forge: dict[str, str],
    idempotency_by_module: dict[str, str] | None = None,
) -> TaskLedger:
    # A position can operate modules on more than one Forge, so the Forge is looked
    # up per module rather than taken from the venture's nominal operating_forge.
    idempotency_by_module = idempotency_by_module or {}
    by_title = {p.position_title: p for p in roles.positions}
    appointed_by_title = {a.position_title: a.appointed for a in appointment.appointments}

    tasks: list[LedgerTask] = []
    approvals_by_role: dict[str, int] = {}

    for step in workflow.steps:
        position = by_title[step.position]
        appointed = appointed_by_title.get(step.position, [])
        module = step.forge_modules[0]

        # One task per appointed agent. An unfilled position produces a task with no
        # assigned agent rather than no task at all — the work still exists, and
        # hiding it would make the shortfall invisible downstream.
        holders: list[str | None] = [a.office_agent_id for a in appointed] or [None]

        for agent_id in holders:
            tier = _effective_tier(position.trust_tier_ceiling, appointed, agent_id)
            volume = DEFAULT_DAILY_VOLUME_PER_HEADCOUNT
            tasks.append(
                LedgerTask(
                    task_id=str(
                        derive_id(
                            pack.venture_id,
                            str(step.number),
                            step.position,
                            module,
                            agent_id or "UNFILLED",
                        )
                    ),
                    step_number=step.number,
                    position=step.position,
                    assigned_agent=agent_id,
                    forge_id=module_forge.get(module, "UNREGISTERED"),
                    module_id=module,
                    trust_tier=tier,
                    compliance_flags=list(position.effective_compliance_flags),
                    sla_minutes=DEFAULT_SLA_MINUTES[tier],
                    expected_daily_volume=volume,
                    idempotency_class=idempotency_by_module.get(module, "key"),
                )
            )
            if tier != "auto_execute":
                reviewer = _reviewer_for(pack, position.effective_compliance_flags)
                approvals_by_role[reviewer] = approvals_by_role.get(reviewer, 0) + volume

    return TaskLedger(
        venture_id=pack.venture_id,
        tasks=sorted(
            tasks, key=lambda t: (t.step_number, t.assigned_agent or "", t.task_id)
        ),
        projected_daily_approvals=dict(sorted(approvals_by_role.items())),
    )


def _effective_tier(
    ceiling: str, appointed: list[AppointedAgent], agent_id: str | None
) -> str:
    """The tier this task actually runs at.

    An unfilled position falls back to the ceiling: the estimate must not get cheaper
    because nobody was appointed.
    """
    for a in appointed:
        if a.office_agent_id == agent_id:
            return a.certified_tier
    return ceiling


def _reviewer_for(pack: BusinessPack, flags: list[str]) -> str:
    """Which human role reviews this task.

    Compliance-flagged work routes to the compliance officer where one exists;
    everything else to the venture operator. Falls back to the first declared human
    rather than inventing a role that has no coverage hours behind it.
    """
    roles = {h.role for h in pack.human_capacity}
    if flags and "compliance_officer" in roles:
        return "compliance_officer"
    if "venture_operator" in roles:
        return "venture_operator"
    return sorted(roles)[0]
