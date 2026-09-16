"""5.3 Workflow Generator.

In: `lifecycle_stages` + the defined positions. Out: every operational step, in order.

Master prompt 5.3 requires, for every step: a module resolving in
`forge_module_registry`, a compliance flag **or explicit NONE**, and an escalation path.
Blank is not allowed for the flag, because blank is ambiguous between "no flag applies"
and "nobody checked".

Stage-to-position mapping comes from `Position.lifecycle_stages_owned` — schema
divergence #3, recorded in the plan. Without it this generator can only guess, and a
plausible-looking workflow nobody can trace is worse than no workflow at all.

Steps are emitted stage-major: every stage in the author's declared order, then every
position owning that stage alphabetically, then every module that position operates **in
that stage**. Stage order is the author's because a workflow that runs Close before Source
is not a workflow; the two inner orderings are alphabetical because nothing meaningful
distinguishes them and stability matters more than any particular choice.

ONE STEP PER MODULE, NOT ONE PER (STAGE, MODULE)

    This generator used to emit the cross product of stages owned and modules operated. A
    position owning two stages emitted each of its modules twice, and the approval
    projection counts per (step, holder, module) - so every duplicate was a second approval
    a day for one piece of work.

        Greenstone  Deal Underwriter owns Underwrite and Contract, operates two modules
                    -> four steps, and the Contract stage held no Deal Underwriter module
        Burkham     Compliance Reviewer owns Readiness and Placement, operates three
                    -> six steps for three modules

    `Position.module_stages` says which stage each module runs in, and a module is emitted
    once, there. Measured across the change: Greenstone 12 steps -> 6, Burkham 15 -> 10.

    **An undeclared module raises rather than guessing.** Falling back to the first stage
    owned would place it by list order. Unreachable through the gate ladder - V13 blocks at
    Gate 2 before the generators run - and a backstop for anyone calling this directly.
"""

from __future__ import annotations

from typing import Any

from generators.artifacts import RoleDefinition, Workflow, WorkflowStep
from generators.pack import BusinessPack

NONE_FLAG = "NONE"

# Escalation by trust tier. An auto_execute step has nobody in the loop by design, so
# its escalation must name where a failure goes instead — "the agent retries" is not
# an escalation path.
_ESCALATION = {
    "auto_execute": (
        "On failure signature: retry per the module's retry_vs_escalate rule, then "
        "raise an incident and halt this task. No silent partial."
    ),
    "propose": (
        "Proposal is rejected or times out: return to {position} with the reviewer's "
        "reason. Repeated rejection escalates to the venture operator."
    ),
    "suggest": (
        "Suggestion is declined: record the decision and continue. Escalate to the "
        "venture operator only on a compliance flag."
    ),
}


def generate(pack: BusinessPack, roles: RoleDefinition) -> Workflow:
    stages = _stage_order(pack)
    triggers = {t.type for t in pack.triggers}
    default_trigger = (
        "agent_initiated" if "agent_initiated" in triggers else "human_initiated"
    )

    steps: list[WorkflowStep] = []
    number = 0

    for stage in stages:
        owners = sorted(
            (p for p in roles.positions if stage in p.lifecycle_stages_owned),
            key=lambda p: p.position_title,
        )
        for position in owners:
            supporting = sorted(
                p.position_title
                for p in owners
                if p.position_title != position.position_title
            )
            for module in _modules_in_stage(position, stage):
                number += 1
                flags = position.effective_compliance_flags
                steps.append(
                    WorkflowStep(
                        number=number,
                        step=f"{stage}: {position.position_title} operates {module}",
                        stage=stage,
                        position=position.position_title,
                        supporting=supporting,
                        forge_modules=[module],
                        trigger=default_trigger,
                        inputs=[f"{stage.lower()}_context", f"{module}_request"],
                        outputs=[f"{module}_result"],
                        success_metric=(
                            f"{module} returns a complete result and the ledger row "
                            "records manifest_match=required"
                        ),
                        failure_and_escalation=_ESCALATION[
                            position.trust_tier_ceiling
                        ].format(position=position.position_title),
                        # Explicit NONE, never blank.
                        compliance_flag=", ".join(flags) if flags else NONE_FLAG,
                        # A pending position's work still happens; a human does it.
                        human_held=position.pending,
                    )
                )

    return Workflow(venture_id=pack.venture_id, steps=steps)


def _modules_in_stage(position: Any, stage: str) -> list[str]:
    """The bare module ids this position runs in this stage, in declared order.

    Reads `module_stages`, which is keyed `forge_id/module_id`; the step text and
    `forge_modules` carry the bare half, which is what every downstream reader compares
    against. The split is named rather than inlined, per entry 48.
    """
    missing = [m for m in position.forge_modules_operated if m not in position.module_stages]
    if missing:
        raise ValueError(
            f"{position.position_title}: no stage declared for {', '.join(sorted(missing))}. "
            "Declare it in module_stages - a module placed by list order is a step whose "
            "stage nobody chose."
        )
    return [
        qualified.split("/", 1)[1]
        for qualified in position.forge_modules_operated
        if position.module_stages[qualified] == stage
    ]


def _stage_order(pack: BusinessPack) -> list[str]:
    seen: list[str] = []
    for line in pack.engagement_model.service_lines:
        for stage in line.lifecycle_stages:
            if stage not in seen:
                seen.append(stage)
    return seen
