"""5.5 Curriculum Generator.

In: Pack + Workflow + Appointments + Forge Operating Instructions + authored scenario
content. Out: the Scenario Pack for SimForge, **with coverage denominators stated.**

Two kinds, never merged — Part 10.1 keeps the two rubrics separate, so the scenarios
that feed them are separate too:

  **domain** scenarios  authored by a human in the Pack. Judgment in context.
                        Graded by the 8-dimension domain rubric. Unit B.
  **operation** scenarios  one per **(module, scenario_class)**. Sequence correctness,
                        failure recognition, escalation discipline, never-do
                        adherence, recovery. Graded by the operation rubric. Unit A.

**The Office authors; SimForge runs.** Nothing here reads a held-out set, and nothing
in this package can — see `broker/simforge.py` and `tests/golden/test_no_read_path.py`.

Every operation scenario carries the `instruction_content_hash` it was derived from.
That is what makes certification staleness computable: rewrite the instructions and the
certification earned against the old hash stops matching.

"Report the denominator. No green check without a coverage count." Every coverage
dimension states what it covered *of how many*, and names what it missed. A coverage
report that lists only what is covered is a report you cannot act on.


WHY THE KEY IS (MODULE, CLASS) AND NOT (POSITION, MODULE)
=========================================================

`docs/scenario-contract.md` §11, amendment A2.1. **A scenario class probes a module's
instruction section, not a role's use of it.** `permission_denied` on
`submit_application` is a fact about that module's hard-failure signature and does not
become a different fact because a different position invoked it. Keeping the position
would have meant authoring the same occasion once per position that operates the
module — the same prose several times, diverging the moment one copy is edited.

Two things moved with it, and neither is allowed to move quietly:

**`compliance_flags_exercised` is empty on an operation scenario now.** It used to be
`position.effective_compliance_flags` — every flag a position holds, stamped onto every
module that position operates. That is not what "exercised" means. It read as *these
flags were exercised* when the true statement was *some position holding these flags
could have exercised them*, and it made the compliance coverage dimension complete by
construction rather than by evidence. Nothing outside this file read the field on an
operation scenario (grepped, `docs/scenario-generation.md` records the finding), so the
one consequence is that the `compliance_flags_exercised` dimension below now counts
what domain scenarios actually exercise. **That number can go down. Down is the
correction, not a regression.**

**Role coverage has a new home and it is `positions_with_all_modules_covered`.**
Position is still a live dimension — Gate 4.5, the approval projection and the
appointment path all reason about positions — so dropping it from the scenario key
moves the question rather than answering it. It is now *derived*: a position is covered
when every module it operates has an operation scenario. Derived rather than carried,
and computed here rather than promised in prose, so that it cannot quietly stop being
derivable.


WHAT THIS GENERATOR AUTHORS, AND WHAT IT REFUSES TO
===================================================

The three mechanically-mapped classes (`generators.scenario_content.MECHANICAL_SECTIONS`)
are emitted for every module with a live instruction, because their source sections are
required and non-empty on every instruction. Everything else — the occasion, what the
agent does, and the escalation as prose — comes from an authored content file or does
not exist.

**It is not filled in with a generated sentence when no content file exists.** The old
generator wrote one summary per (position, module) — *"Operate X as Y: correct
sequence, recognise the module's failure signatures…"* — which is the module's section
headings rearranged, and it was going to be GRADED. `expected_behavior` and
`expected_escalation` are left empty instead, and an empty required field is a
violation on submission rather than a pass, so SimForge refuses the scenario and names
it. An unauthored scenario that is refused is a true statement about where the work is;
a boilerplate one that passes is not.
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
from generators.scenario_content import (
    ALL_SCENARIO_CLASSES,
    HELD_OUT_CLASSES,
    MECHANICAL_SECTIONS,
    SUBMITTABLE_CLASSES,
    ModuleContent,
    ScenarioContentError,
    ScenarioContentSet,
    load_all,
)


async def generate(
    pack: BusinessPack,
    roles: RoleDefinition,
    workflow: Workflow,
    appointment: Appointment,
    conn: AsyncConnection | None = None,
    content: ScenarioContentSet | None = None,
) -> ScenarioPack:
    live = await _live_instructions(conn)
    hashes = {module: forge_hash[1] for module, forge_hash in live.items()}
    authored = content if content is not None else load_all()

    domain = [
        CurriculumScenario(
            scenario_id=s.scenario_id,
            kind="domain",
            role=s.role,
            domain=s.domain,
            module_id=None,
            compliance_flags_exercised=sorted(s.compliance_flags_exercised),
            summary=s.summary,
            instruction_content_hash=None,
        )
        for s in sorted(pack.scenarios, key=lambda s: s.scenario_id)
    ]

    modules = sorted({m for p in roles.positions for m in p.forge_modules_operated})
    operation: list[CurriculumScenario] = []
    for module in modules:
        module_content = authored.for_module(module)
        if module_content is not None and module in live:
            _check_forge(module_content, live[module][0])
        operation.extend(
            _operation_scenarios(module, module_content, module in live, hashes)
        )
    operation.sort(key=lambda s: s.scenario_id)

    return ScenarioPack(
        venture_id=pack.venture_id,
        domain_scenarios=domain,
        operation_scenarios=operation,
        coverage=_coverage(pack, roles, workflow, domain, operation, hashes, authored),
    )


def _operation_scenarios(
    module: str,
    content: ModuleContent | None,
    has_instruction: bool,
    hashes: dict[str, str],
) -> list[CurriculumScenario]:
    """One scenario per (module, class), for every class this module accounts for.

    A class is accounted for three ways, and the differences between them are the
    whole point of the contract:

      mechanically      the class's source section is required on every instruction,
                        so the scenario exists whether or not anybody authored it.
                        Unauthored, it carries empty required fields and is refused
                        on submission - which is what "nobody has written this yet"
                        should look like.
      authored          a content file supplies the occasion, the behaviour and the
                        escalation prose.
      declared absent   a content file says the module cannot have this class, and
                        why. ADR-0049: stated, never inferred, and never a pass.

    A class accounted for in none of the three ways is simply not here, and SimForge
    refuses the submission for it rather than capping the module silently.
    """
    classes: list[str] = []
    if has_instruction:
        classes.extend(MECHANICAL_SECTIONS)
    if content is not None:
        classes.extend(content.scenarios)
        classes.extend(content.not_applicable)

    out: list[CurriculumScenario] = []
    for scenario_class in sorted(set(classes)):
        authored = content.scenarios.get(scenario_class) if content else None
        reason = content.not_applicable.get(scenario_class, "") if content else ""
        section = (
            content.section_for(scenario_class) if content
            else MECHANICAL_SECTIONS.get(scenario_class, "")
        )
        out.append(
            CurriculumScenario(
                scenario_id=f"op-{module}-{scenario_class}",
                kind="operation",
                # No position in the key (contract A2.1). Empty rather than a
                # plausible-looking join across the positions that operate this
                # module: a scenario belongs to the module, and naming one of
                # several operators here would read as though it belonged to that
                # one.
                role="",
                domain="operation",
                module_id=module,
                # See the module docstring. Empty is the honest value; the union
                # this replaces was complete by construction.
                compliance_flags_exercised=[],
                # The precipitating situation, which is the half of a scenario no
                # manual contains. `summary` is the only field on this dataclass that
                # can carry it - there is no `situation` field on either side of the
                # contract. Empty when unauthored, never a generated sentence.
                summary=authored.situation if authored else "",
                instruction_content_hash=hashes.get(module),
                scenario_class=scenario_class,
                instruction_section=section,
                expected_behavior=authored.wire_behavior() if authored else "",
                expected_escalation=(
                    authored.expected_escalation if authored else ""
                ),
                # Required for `never_do_violation` alone, and that class is held out,
                # so from The Office's side it is always empty. Its non-empty case is
                # reserved for SimForge's own authoring.
                never_do_entry="",
                not_applicable_reason=reason,
            )
        )
    return out


def _check_forge(content: ModuleContent, forge_id: str) -> None:
    if content.forge_id != forge_id:
        raise ScenarioContentError(
            f"{content.module_id}.yaml declares forge_id {content.forge_id!r}, but "
            f"the live instruction for that module belongs to {forge_id!r}. A "
            "content file filed under the wrong Forge authors scenarios against a "
            "manual nobody will grade them with."
        )


async def _live_instructions(conn: AsyncConnection | None) -> dict[str, tuple[str, str]]:
    """module_id -> (forge_id, content_hash), for live instructions only."""
    if conn is None:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, forge_id, content_hash FROM forge_operating_instruction "
            "WHERE superseded_at IS NULL"
        )
        return {
            module_id: (forge_id, content_hash)
            for module_id, forge_id, content_hash in await cur.fetchall()
        }


def _coverage(
    pack: BusinessPack,
    roles: RoleDefinition,
    workflow: Workflow,
    domain: list[CurriculumScenario],
    operation: list[CurriculumScenario],
    hashes: dict[str, str],
    content: ScenarioContentSet,
) -> list[Coverage]:
    """Eight dimensions, each with its denominator and its misses named."""
    positions = {p.position_title for p in roles.positions}
    roles_with_domain = {s.role for s in domain}
    modules = {m for p in roles.positions for m in p.forge_modules_operated}
    modules_with_ops = {s.module_id for s in operation if s.module_id}
    flags = {f for p in roles.positions for f in p.effective_compliance_flags}
    flags_exercised = {
        f for s in (*domain, *operation) for f in s.compliance_flags_exercised
    }
    modules_with_hash = {m for m in modules if hashes.get(m)}
    modules_with_content = {m for m in modules if content.for_module(m) is not None}

    # A class is accounted for when a scenario exists for it - authored, mechanical or
    # declared absent. "Every submittable class accounted for" is what SimForge needs
    # to stop refusing the module, and it is not the same question as "is there a
    # scenario", which is why it gets its own denominator.
    accounted: dict[str, set[str]] = {}
    for s in operation:
        if s.module_id and s.scenario_class:
            accounted.setdefault(s.module_id, set()).add(s.scenario_class)
    complete_modules = {
        m for m in modules if set(SUBMITTABLE_CLASSES) <= accounted.get(m, set())
    }

    # Role coverage's home after the position dimension left the scenario key: a
    # position is covered when every module it operates has an operation scenario.
    covered_positions = {
        p.position_title for p in roles.positions
        if set(p.forge_modules_operated) <= modules_with_ops
    }

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
            # Every module a position operates has a scenario, so every position's
            # operating surface is covered. Derived from RoleDefinition rather than
            # carried on the scenario row - see the module docstring.
            dimension="positions_with_all_modules_covered",
            covered=len(covered_positions),
            denominator=len(positions),
            uncovered=sorted(positions - covered_positions),
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
            # A module with no authored instructions cannot produce a meaningful
            # operation scenario: SimForge would have nothing to grade against.
            denominator=len(modules),
            uncovered=sorted(modules - modules_with_hash),
        ),
        Coverage(
            # The B4 authorship denominator. A module with no content file emits its
            # mechanical scenarios with empty required fields, which SimForge refuses
            # - so this is the number that says how much of the curriculum is written
            # rather than merely shaped.
            dimension="modules_with_authored_scenario_content",
            covered=len(modules_with_content),
            denominator=len(modules),
            uncovered=sorted(modules - modules_with_content),
        ),
        Coverage(
            # THE RECORDED CAP. Constant by construction, and that is the point: the
            # two held-out classes are SimForge's to author and The Office may never
            # submit one, so seven of nine is a ceiling no amount of authoring moves.
            # A reader who finds a module at `demonstrated` rather than `certified`
            # should find this line before concluding somebody left work undone.
            dimension="scenario_classes_the_office_may_submit",
            covered=len(SUBMITTABLE_CLASSES),
            denominator=len(ALL_SCENARIO_CLASSES),
            uncovered=sorted(HELD_OUT_CLASSES),
        ),
        Coverage(
            dimension="modules_accounting_for_every_submittable_class",
            covered=len(complete_modules),
            denominator=len(modules),
            uncovered=sorted(modules - complete_modules),
        ),
    ]
