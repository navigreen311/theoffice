"""The seven artifacts, and the determinism machinery underneath them.

Master prompt Part 5: "Deterministic transformers. Same Pack in, same artifacts out.
LLM temperature >0 only inside sub-tasks where determinism is impossible, never at
structural level."

There is no LLM in this package at all. Structural generation must be reproducible or
the golden snapshots are theatre — a diff that sometimes appears is a diff nobody
investigates.

Three rules make that true, and every artifact below obeys them:

  * **No `uuid4`.** Identifiers are UUIDv5 derived from their natural key, which also
    makes Generator 5.7's idempotency structural rather than a code path someone has
    to remember to write.
  * **No wall-clock timestamps inside artifacts.** A generated artifact that embeds
    `now()` differs from itself on every run.
  * **Every collection is sorted by an explicit key**, never left in dict insertion or
    query order. Postgres makes no ordering promise without ORDER BY, and a snapshot
    that passes locally and fails in CI teaches people to re-record snapshots.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

# One namespace for every derived identifier in The Office. Fixed forever: changing it
# would silently re-key every grant and task in every venture.
OFFICE_NAMESPACE = uuid.UUID("6f0a1f2e-9c3d-5b47-8a1e-0d2c4b6a8e10")


def derive_id(*parts: str) -> uuid.UUID:
    """A stable id for a natural key.

    UUIDv5 rather than a counter, so two runs on different machines agree, and so a
    re-run of Generator 5.7 collides with its own prior rows instead of inserting
    duplicates. Idempotency by construction beats idempotency by ON CONFLICT.
    """
    return uuid.uuid5(OFFICE_NAMESPACE, "|".join(parts))


def _plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in sorted(value.items())}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


class Artifact:
    """Mixin giving every artifact a canonical, diffable serialisation."""

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)  # type: ignore[no-any-return]

    def to_json(self) -> str:
        """Sorted keys, two-space indent, trailing newline.

        Stable formatting so a golden diff shows what changed in the artifact rather
        than what changed in the serialiser.
        """
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ----------------------------------------------------------------- 5.1 Role Definition

@dataclass(frozen=True, slots=True)
class DefinedPosition:
    position_title: str
    reports_to: str
    duties: list[str]
    forge_modules_operated: list[str]
    source_department: str
    declared_compliance_flags: list[str]
    implied_compliance_flags: list[str]
    """Derived from `forge_module_registry.compliance_flags_implied`.

    A Pack author names the flags they know about. The modules carry the ones the
    Forge itself implies, and an author who omits one has not thereby escaped it.
    """
    effective_compliance_flags: list[str]
    headcount: int
    trust_tier_ceiling: str
    lifecycle_stages_owned: list[str]


@dataclass(frozen=True, slots=True)
class RoleDefinition(Artifact):
    venture_id: str
    positions: list[DefinedPosition]
    unresolved_modules: list[str]
    """Modules a position operates that are not in `forge_module_registry`.

    Reported rather than raised: V6 is the gate that blocks on this, and a generator
    that also raised would report the same problem twice in two vocabularies.
    """


# -------------------------------------------------------------------- 5.2 Appointment

@dataclass(frozen=True, slots=True)
class AppointedAgent:
    office_agent_id: str
    agent_name: str
    department: str
    certified_modules: list[str]
    certified_tier: str


@dataclass(frozen=True, slots=True)
class CandidateShortfall:
    office_agent_id: str
    agent_name: str
    reason: str
    """`never_certified` | `in_training` | `stale_instructions` | `stale_forge` |
    `failed` | `revoked` | `wrong_department` | `missing_unit_b`.

    Named, never collapsed to "not eligible" - Part 10.1, and because the fix for
    `in_training` is to wait while the fix for `wrong_department` is to look elsewhere.
    """


@dataclass(frozen=True, slots=True)
class PositionAppointment:
    position_title: str
    headcount_required: int
    appointed: list[AppointedAgent]
    unfilled: int
    requires_certification: list[CandidateShortfall]


@dataclass(frozen=True, slots=True)
class CapacityNumbers:
    """§7.2 — all three, always. One number hides the state.

    "Certified and free" alone looks like a hiring problem. Add "certified but
    allocated" and it may be a scheduling problem. Add "produced but not certified"
    and it may be a SimForge backlog. Three different responses.
    """

    certified_and_free: int
    certified_but_allocated: int
    produced_not_yet_certified: int

    @property
    def total_considered(self) -> int:
        return (
            self.certified_and_free
            + self.certified_but_allocated
            + self.produced_not_yet_certified
        )


@dataclass(frozen=True, slots=True)
class Appointment(Artifact):
    venture_id: str
    appointments: list[PositionAppointment]
    capacity: CapacityNumbers
    shortfall: bool
    escalation: str
    """§7.3: flag to Ivan for decision. Never auto-reject the Pack, never auto-appoint
    an uncertified agent, never silently reduce scope."""


# ----------------------------------------------------------------------- 5.3 Workflow

@dataclass(frozen=True, slots=True)
class WorkflowStep:
    number: int
    step: str
    stage: str
    position: str
    supporting: list[str]
    forge_modules: list[str]
    trigger: str
    inputs: list[str]
    outputs: list[str]
    success_metric: str
    failure_and_escalation: str
    compliance_flag: str
    """A flag, or the literal string NONE. Never blank.

    5.3: "every step carries a flag or explicit NONE". Blank is ambiguous between
    "no flag applies" and "nobody checked".
    """


@dataclass(frozen=True, slots=True)
class Workflow(Artifact):
    venture_id: str
    steps: list[WorkflowStep]


# -------------------------------------------------------------------- 5.4 Task Ledger

@dataclass(frozen=True, slots=True)
class LedgerTask:
    task_id: str
    step_number: int
    position: str
    assigned_agent: str | None
    forge_id: str
    module_id: str
    trust_tier: str
    compliance_flags: list[str]
    sla_minutes: int
    expected_daily_volume: int
    idempotency_class: str


@dataclass(frozen=True, slots=True)
class TaskLedger(Artifact):
    venture_id: str
    tasks: list[LedgerTask]
    projected_daily_approvals: dict[str, int]
    """Per human role. 5.4 names this a required additional output, and it is the
    input to validator rule V13 - approval volume no human can absorb is what makes
    a trust tier decorative."""


# --------------------------------------------------------------------- 5.5 Curriculum

@dataclass(frozen=True, slots=True)
class CurriculumScenario:
    scenario_id: str
    kind: str
    role: str
    domain: str
    module_id: str | None
    compliance_flags_exercised: list[str]
    expected_escalation: bool
    summary: str
    instruction_content_hash: str | None


@dataclass(frozen=True, slots=True)
class Coverage:
    dimension: str
    covered: int
    denominator: int
    uncovered: list[str]

    @property
    def complete(self) -> bool:
        return self.covered == self.denominator


@dataclass(frozen=True, slots=True)
class ScenarioPack(Artifact):
    venture_id: str
    domain_scenarios: list[CurriculumScenario]
    operation_scenarios: list[CurriculumScenario]
    coverage: list[Coverage]
    """"Report the denominator. No green check without a coverage count." Every
    dimension states what it covered *of how many*."""


# ------------------------------------------------------------------ 5.6 Forge Manifest

@dataclass(frozen=True, slots=True)
class ManifestEntry:
    forge_id: str
    module_id: str
    declared: bool
    required: bool
    criticality: str
    module_gap: bool
    required_by: list[str]


@dataclass(frozen=True, slots=True)
class Reconciliation:
    required_not_declared: list[str]
    """FAILS the Pack (5.6). A workflow step needs a module the Pack never declared."""
    declared_not_required: list[str]
    """WARN (V25). Declared and paid for, used by nothing."""
    hard_dependency_on_gap: list[str]
    """Cannot provision (5.6 / V8)."""

    @property
    def blocks_provisioning(self) -> bool:
        return bool(self.required_not_declared or self.hard_dependency_on_gap)


@dataclass(frozen=True, slots=True)
class ForgeManifest(Artifact):
    venture_id: str
    entries: list[ManifestEntry]
    reconciliation: Reconciliation


# ----------------------------------------------------------------- 5.7 Runtime Config

@dataclass(frozen=True, slots=True)
class PlannedGrant:
    grant_id: str
    office_agent_id: str
    forge_id: str
    module_id: str
    trust_tier: str


@dataclass(frozen=True, slots=True)
class RuntimeConfig(Artifact):
    venture_id: str
    environment: str
    grants: list[PlannedGrant]
    manifest_rows: list[ManifestEntry]
    rate_limits: dict[str, dict[str, float]]
    budget: dict[str, float]
    compliance_flags: list[str]
    blocked_reason: str | None
    """Set when the Manifest reconciliation blocks provisioning. 5.7 consumes the
    Manifest, not the Pack - so a Pack that would provision and a Manifest that
    would not cannot disagree."""


# ------------------------------------------------------------------- the whole set

@dataclass(frozen=True, slots=True)
class Advisory(Artifact):
    """Something a human should see at Gate 4, and how much it matters.

    This used to be a bare string in a list called `warnings`, which is how a rule that
    FAILS at the next gate came to be filed under "Generator warnings (2)" alongside a
    genuine advisory. A reviewer reading that count sees two warnings; what they have is
    one blocking failure and one warning, and the difference decides whether advancing
    is worth doing at all.

    `blocks_at` is the gate that will stop the run. Carrying it means the console can say
    *where* the run will halt rather than inferring it from the text of a message.
    """

    severity: str            # "fail" | "warn"
    message: str
    source: str              # which generator or gate raised it
    rule_id: str | None = None
    blocks_at: str | None = None
    # Pack blocks the rule reads. Lets a console link land on the fields to change
    # rather than at the top of the document.
    blocks: tuple[str, ...] = ()

    @property
    def blocking(self) -> bool:
        return self.severity == "fail"


@dataclass(frozen=True, slots=True)
class GeneratedArtifacts(Artifact):
    venture_id: str
    roles: RoleDefinition
    appointment: Appointment
    workflow: Workflow
    task_ledger: TaskLedger
    curriculum: ScenarioPack
    forge_manifest: ForgeManifest
    runtime_config: RuntimeConfig
    advisories: list[Advisory] = field(default_factory=list)

    @property
    def warnings(self) -> list[str]:
        """The flat strings, for callers that predate `advisories`.

        Derived rather than stored, so the two cannot disagree - and deliberately still
        includes the failures, because a caller asking for "everything a human should
        see" should not silently stop being shown the blocking half.
        """
        return [a.message for a in self.advisories]

    @property
    def blocking_advisories(self) -> list[Advisory]:
        return [a for a in self.advisories if a.blocking]
