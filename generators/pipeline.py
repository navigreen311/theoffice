"""Run all seven generators, in dependency order.

Gate 3 of the provisioning pipeline. Every generator is pure except 5.2 and 5.5, which
read the roster and the instruction hashes, and 5.7's `apply()`, which is the only thing
in this package that writes.

The order is not a preference. 5.4 needs 5.2's appointments to know who owns a task;
5.6 needs 5.3 and 5.4 to know what is *required*; 5.7 consumes 5.6's reconciliation
rather than the Pack, so a Pack that would provision and a Manifest that would not
cannot disagree.
"""

from __future__ import annotations

from psycopg import AsyncConnection

from generators import (
    appointment as appointment_gen,
)
from generators import (
    curriculum as curriculum_gen,
)
from generators import (
    forge_manifest as manifest_gen,
)
from generators import (
    roles as roles_gen,
)
from generators import (
    runtime_config as runtime_gen,
)
from generators import (
    task_ledger as ledger_gen,
)
from generators import (
    workflow as workflow_gen,
)
from generators.artifacts import (
    Advisory,
    Appointment,
    ForgeManifest,
    GeneratedArtifacts,
    RoleDefinition,
    ScenarioPack,
)
from generators.pack import BusinessPack
from generators.validator import (
    ValidationReport,
    Verdict,
    rule_blocks,
    validate_gate_4_5,
)


async def run_all(pack: BusinessPack, conn: AsyncConnection) -> GeneratedArtifacts:
    # Resolved once and threaded through everything downstream. A position can operate
    # modules on more than one Forge - Greenstone's Acquisition Analyst uses CRE Forge
    # and VoiceForge - and certification, grants and ledger rows are all per Forge.
    #
    # There is deliberately no forge_id override. The registry is the only authority on
    # which Forge owns a module; letting a caller assert otherwise would let a venture
    # certify an agent against the wrong Forge and never notice.
    module_forge = await appointment_gen.module_forge_map(conn)

    roles = await roles_gen.generate(pack, conn)
    appointment = await appointment_gen.generate(
        roles, conn, venture_id=pack.venture_id, module_forge=module_forge
    )
    workflow = workflow_gen.generate(pack, roles)

    idempotency = await _idempotency_classes(conn)
    task_ledger = ledger_gen.generate(
        pack, roles, workflow, appointment,
        module_forge=module_forge, idempotency_by_module=idempotency,
    )

    curriculum = await curriculum_gen.generate(pack, roles, workflow, appointment, conn)
    forge_manifest = manifest_gen.generate(pack, workflow, task_ledger)
    runtime = runtime_gen.generate(
        pack, roles, appointment, forge_manifest, module_forge=module_forge
    )

    # Gate 4.5 re-checks capacity against the real Task Ledger. V13 at Gate 2 could
    # only estimate from the Pack, and that estimate is the optimistic one.
    gate_4_5 = await validate_gate_4_5(pack, task_ledger, appointment)

    return GeneratedArtifacts(
        venture_id=pack.venture_id,
        roles=roles,
        appointment=appointment,
        workflow=workflow,
        task_ledger=task_ledger,
        curriculum=curriculum,
        forge_manifest=forge_manifest,
        runtime_config=runtime,
        advisories=_warnings(
            roles, appointment, forge_manifest, curriculum, gate_4_5
        ),
    )


async def _idempotency_classes(conn: AsyncConnection) -> dict[str, str]:
    async with conn.cursor() as cur:
        await cur.execute("SELECT module_id, idempotency_support FROM forge_module_registry")
        return dict(await cur.fetchall())


def _warnings(
    roles: RoleDefinition,
    appointment: Appointment,
    forge_manifest: ForgeManifest,
    curriculum: ScenarioPack,
    gate_4_5: ValidationReport,
) -> list[Advisory]:
    """Everything a human should see at Gate 4, in one place.

    Collected rather than logged: Gate 4 is a human reviewing artifacts, and a
    warning that only exists in a log line is a warning that review will miss.
    """
    out: list[Advisory] = []

    # A rule that FAILS at Gate 4.5 is not a warning. It is a known halt one gate after
    # the one the human is being asked to clear, and the reviewer is entitled to know
    # that before they write a review nothing will use.
    for result in gate_4_5.results:
        if result.verdict is Verdict.FAIL:
            out.append(Advisory(
                severity="fail", message=result.message,
                source="gate_4_5", rule_id=result.rule_id, blocks_at="4.5",
                blocks=tuple(rule_blocks().get(result.rule_id, ())),
            ))

    if roles.unresolved_modules:
        out.append(Advisory(
            severity="warn",
            message=(
                "Modules not in forge_module_registry: "
                f"{', '.join(roles.unresolved_modules)}"
            ),
            source="roles",
        ))
    if appointment.shortfall:
        out.append(Advisory(
            severity="warn", message=appointment.escalation, source="appointment",
        ))
    if forge_manifest.reconciliation.declared_not_required:
        out.append(Advisory(
            severity="warn",
            message=(
                "Declared and paid for, used by nothing: "
                f"{', '.join(forge_manifest.reconciliation.declared_not_required)}"
            ),
            source="forge_manifest", rule_id="V25",
        ))
    for coverage in curriculum.coverage:
        if not coverage.complete:
            out.append(Advisory(
                severity="warn",
                message=(
                    f"Coverage {coverage.dimension}: {coverage.covered}/"
                    f"{coverage.denominator} - missing "
                    f"{', '.join(coverage.uncovered)}"
                ),
                source="curriculum",
            ))
    return out
