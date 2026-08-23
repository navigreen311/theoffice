"""5.5 Curriculum Generator.

In: Pack + Workflow + Appointments + Forge Operating Instructions.
Out: the Scenario Pack for SimForge, **with coverage denominators stated.**

Two kinds, never merged — Part 10.1 keeps the two rubrics separate, so the scenarios
that feed them are separate too:

  **domain** scenarios  authored by a human in the Pack. Judgment in context.
                        Graded by the 8-dimension domain rubric. Unit B.
  **operation** scenarios  derived here, one per (position x module). Sequence
                        correctness, failure recognition, escalation discipline,
                        never-do adherence, recovery. Graded by the operation rubric.
                        Unit A.

**The Office authors; SimForge runs.** Nothing here reads a held-out set, and nothing
in this package can — see `broker/simforge.py` and `tests/golden/test_no_read_path.py`.

Every operation scenario carries the `instruction_content_hash` it was derived from.
That is what makes certification staleness computable: rewrite the instructions and the
certification earned against the old hash stops matching.

"Report the denominator. No green check without a coverage count." Every coverage
dimension states what it covered *of how many*, and names what it missed. A coverage
report that lists only what is covered is a report you cannot act on.
"""

from __future__ import annotations

from psycopg import AsyncConnection

from generators.artifacts import (
    Appointment,
    Coverage,
    CurriculumScenario,
    RoleDefinition,
    ScenarioPack,
    Workflow,
)
from generators.pack import BusinessPack


async def generate(
    pack: BusinessPack,
    roles: RoleDefinition,
    workflow: Workflow,
    appointment: Appointment,
    conn: AsyncConnection | None = None,
) -> ScenarioPack:
    hashes = await _instruction_hashes(conn)

    domain = [
        CurriculumScenario(
            scenario_id=s.scenario_id,
            kind="domain",
            role=s.role,
            domain=s.domain,
            module_id=None,
            compliance_flags_exercised=sorted(s.compliance_flags_exercised),
            expected_escalation=s.expected_escalation,
            summary=s.summary,
            instruction_content_hash=None,
        )
        for s in sorted(pack.scenarios, key=lambda s: s.scenario_id)
    ]

    # One operation scenario per (position, module). Derived rather than authored,
    # because the operation rubric tests the module's own failure signatures and
    # never-do list — which live in the instructions, not in a human's imagination.
    operation: list[CurriculumScenario] = []
    for position in roles.positions:
        for module in position.forge_modules_operated:
            operation.append(
                CurriculumScenario(
                    scenario_id=f"op-{position.position_title.lower().replace(' ', '-')}-{module}",
                    kind="operation",
                    role=position.position_title,
                    domain="operation",
                    module_id=module,
                    compliance_flags_exercised=list(position.effective_compliance_flags),
                    # Every operation scenario tests escalation discipline: knowing
                    # when to stop is the competence the operation rubric is for.
                    expected_escalation=True,
                    summary=(
                        f"Operate {module} as {position.position_title}: correct "
                        "sequence, recognise the module's failure signatures "
                        "(failure vs slow success vs silent partial), honour its "
                        "retry-vs-escalate rule and its never-do list."
                    ),
                    instruction_content_hash=hashes.get(module),
                )
            )
    operation.sort(key=lambda s: s.scenario_id)

    return ScenarioPack(
        venture_id=pack.venture_id,
        domain_scenarios=domain,
        operation_scenarios=operation,
        coverage=_coverage(pack, roles, workflow, domain, operation, hashes),
    )


async def _instruction_hashes(conn: AsyncConnection | None) -> dict[str, str]:
    if conn is None:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, content_hash FROM forge_operating_instruction "
            "WHERE superseded_at IS NULL"
        )
        return {module_id: content_hash for module_id, content_hash in await cur.fetchall()}


def _coverage(
    pack: BusinessPack,
    roles: RoleDefinition,
    workflow: Workflow,
    domain: list[CurriculumScenario],
    operation: list[CurriculumScenario],
    hashes: dict[str, str],
) -> list[Coverage]:
    """Four dimensions, each with its denominator and its misses named."""
    positions = {p.position_title for p in roles.positions}
    roles_with_domain = {s.role for s in domain}
    modules = {m for p in roles.positions for m in p.forge_modules_operated}
    modules_with_ops = {s.module_id for s in operation if s.module_id}
    flags = {f for p in roles.positions for f in p.effective_compliance_flags}
    flags_exercised = {
        f for s in (*domain, *operation) for f in s.compliance_flags_exercised
    }
    modules_with_hash = {m for m in modules if hashes.get(m)}

    return [
        Coverage(
            dimension="roles_with_domain_scenarios",
            covered=len(positions & roles_with_domain),
            denominator=len(positions),
            uncovered=sorted(positions - roles_with_domain),
        ),
        Coverage(
            dimension="modules_with_operation_scenarios",
            covered=len(modules & modules_with_ops),
            denominator=len(modules),
            uncovered=sorted(modules - modules_with_ops),
        ),
        Coverage(
            dimension="compliance_flags_exercised",
            covered=len(flags & flags_exercised),
            denominator=len(flags),
            uncovered=sorted(flags - flags_exercised),
        ),
        Coverage(
            dimension="modules_with_authored_instructions",
            covered=len(modules_with_hash),
            denominator=len(modules),
            # A module with no authored instructions cannot produce a meaningful
            # operation scenario: SimForge would have nothing to grade against.
            uncovered=sorted(modules - modules_with_hash),
        ),
    ]
