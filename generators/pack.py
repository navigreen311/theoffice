"""Business Pack — schema v3.

The input artifact. A human authors one YAML document per venture; the seven
generators consume it and produce a working agent team.

Pydantic handles *shape* — required fields, types, enums — and fails at load.
`generators/validator.py` handles *meaning*: cross-references, capacity arithmetic,
whether a declared framework resolves to a runtime flag.

They are separate because the two failures read differently to an author. A missing
`venture_name` is a typo. "Projected daily approvals exceed reviewer capacity" is a
design problem with the venture, and telling someone that in the same breath as a
YAML indentation error buries it.

Changes from v2, per master prompt: `estimated_agent_count` removed (the roster
exists; The Office appoints from it), `capacity_demand` added, `positions_required`
added — The Office names venture-specific roles rather than reading them from a list.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = 3

# There is deliberately no VILLAGE_DEPARTMENTS here any more.
#
# This module held twelve department names. The Village was rebuilt and nine of them
# stopped existing - `Research & Market Intelligence` became `research`,
# `Finance & Administration` became `banking` - and nothing failed, because a copy cannot
# know it has gone stale. Packs naming departments that had not existed for two days
# validated cleanly.
#
# The list is read from the Village by `broker.departments`, and validated by rules V29
# and V30. When the Village cannot be reached those rules report NOT_RUN rather than
# falling back to a copy, because a check against a stale list is worse than no check:
# it produces a pass.

ComplianceFramework = Literal[
    "HIPAA", "HCQC", "TILA", "FCRA", "ECOA", "UDAAP", "CROA", "FTC_TSR",
    "NRS_648_NV", "STATE_LENDER_LICENSURE", "MCA_DISCLOSURE_CA_SB1235",
    "TWO_PARTY_CONSENT_RECORDING", "VOICE_CLONING_CONSENT", "GDPR", "CCPA", "PCI_DSS",
]
TrustTier = Literal["auto_execute", "propose", "suggest"]
Criticality = Literal["hard", "soft"]


class Strict(BaseModel):
    """Unknown keys are an error, not a shrug.

    A Pack with `positons_required` should fail loudly. Silently ignoring it would
    produce a venture with no positions and no explanation.
    """

    model_config = ConfigDict(extra="forbid")


class Identity(Strict):
    venture_name: str
    legal_entity: str
    parent: str = "Green Companies LLC"
    operating_status: Literal["launching", "operating", "scaling", "winding_down"]
    category: str
    positioning_one_liner: str = Field(max_length=200)


class ComplianceSurface(Strict):
    framework: ComplianceFramework
    jurisdiction: list[str] | Literal["FEDERAL", "ALL"]
    applies_when: str
    runtime_flag: str
    library_entry_ref: str | None = None
    library_gap: bool = False


class Market(Strict):
    target_personas: list[str] = Field(min_length=1)
    target_geographies: list[str] = Field(min_length=1)
    compliance_surface: list[ComplianceSurface] = Field(default_factory=list)


class ServiceLine(Strict):
    service_line_name: str
    lifecycle_stages: list[str] = Field(min_length=3)
    pricing_structure: Literal["subscription", "retainer", "success_fee", "hybrid", "project"]
    revenue_model: Literal["MRR", "project", "hybrid"]


class EngagementModel(Strict):
    service_lines: list[ServiceLine] = Field(min_length=1)
    conversion_events: list[str]
    disqualification_criteria: list[str]
    out_of_scope_at_launch: list[str]


class Position(Strict):
    """A venture-specific role. The Office names these; it does not look them up."""

    position_title: str
    reports_to: str
    duties: list[str]
    forge_modules_operated: list[str]
    source_department: str
    compliance_flags_in_scope: list[str]
    headcount: int = Field(ge=1)
    trust_tier_ceiling: TrustTier
    lifecycle_stages_owned: list[str] = Field(default_factory=list)
    """Which lifecycle stages this position acts in. Empty means all of them.

    Schema divergence #3, recorded in docs/plans/. Generator 5.3 must emit a step
    naming a position, a module, a flag and an escalation for each stage - and schema
    v3 as specified maps stages to service lines and modules to positions, but nothing
    maps a position to a stage. Without this the generator can only guess, and a
    plausible-looking workflow nobody can trace is worse than none. The blueprint
    should be amended.
    """


class CapacityDemand(Strict):
    agent_days_per_week: float
    peak_concurrent_positions: int
    shift_pattern: str
    ramp_schedule: list[dict[str, Any]] = Field(default_factory=list)


class RateLimitPolicy(Strict):
    max_rps: float
    burst: int
    backoff: str
    on_429: str


class ForgeBinding(Strict):
    forge: str
    api_version: str
    criticality: Criticality
    modules_expected: list[str] = Field(default_factory=list)
    compliance_flags_propagated: list[str] = Field(default_factory=list)
    fallback_behavior: Literal["halt", "queue", "skip_step", "manual_handoff"] | None = None
    rate_limit_policy: RateLimitPolicy | None = None
    credential_mode: Literal["brokered", "native"] = "brokered"
    cost_center: str
    module_gap: bool = False


class ExternalSoftware(Strict):
    name: str
    purpose: str
    criticality: Criticality
    data_types_transmitted: list[str]
    dpa_or_baa_status: Literal["signed", "pending", "not_required"]


class ForgeDependencies(Strict):
    operating_forge: str
    training_forge: str = "SimForge"
    forge_bindings: list[ForgeBinding] = Field(min_length=1)
    external_software: list[ExternalSoftware] = Field(default_factory=list)


class OperatingInstructionRef(Strict):
    forge_id: str
    module_id: str
    instruction_version: str
    forge_api_version: str
    version_sensitivity: Literal["major", "major.minor", "major.minor.patch"] = "major.minor"
    sensitivity_rationale: str | None = None
    content_hash: str | None = None
    authored_by: str


class Trigger(Strict):
    trigger_id: str
    type: Literal["scheduled", "forge_webhook", "human_initiated", "agent_initiated"]
    max_invocations_per_hour: int | None = None
    max_chain_depth: int = 3


class Budget(Strict):
    monthly_usd_cap: float
    soft_cap_pct: int = 80
    hard_cap_action: Literal["pause", "throttle"] = "pause"
    per_agent_usd_daily_cap: float
    per_task_usd_ceiling: float
    cost_alert_recipients: list[str] = Field(min_length=1)


class HumanCapacity(Strict):
    human_name: str
    role: str
    coverage_hours: float
    timezone: str
    backup_human: str | None = None
    max_daily_approvals: int
    median_review_minutes: float = 5.0
    auth_method: Literal["sso_mfa", "mfa_only"]


class SeparationOfDuties(Strict):
    gate_signoff_policy: Literal["distinct_humans", "single_human_permitted"]
    single_human_justification: str | None = None


class Availability(Strict):
    office_unreachable_behavior: Literal["halt", "degrade_to_propose"]
    audit_write_failure_behavior: Literal["fail_closed", "queue_durable"]
    rto_minutes: int
    rpo_minutes: int


class DataRetention(Strict):
    data_type: str
    retention: str
    legal_basis: str
    deletion_mechanism: Literal["crypto_shred", "hard_delete", "tombstone"]


class KpiTarget(Strict):
    kpi_name: str
    target_value: float
    unit: str
    measurement_source: str
    measurement_frequency: str
    owner: str


class Scenario(Strict):
    """Authored by The Office, run by SimForge.

    The Pack carries scenario *content* on the way out. It never carries held-out
    content, and nothing in The Office reads any back - see docs/certification.md.
    """

    scenario_id: str
    role: str
    domain: str
    compliance_flags_exercised: list[str] = Field(default_factory=list)
    expected_escalation: bool = False
    summary: str


class Teardown(Strict):
    forge_tenant_disposition: str
    audit_log_disposition: str
    phi_disposition: str
    teardown_signoff_required: bool


class Lifecycle(Strict):
    teardown_policy: Teardown


class BusinessPack(Strict):
    schema_version: int = SCHEMA_VERSION
    identity: Identity
    environment: Literal["sandbox", "staging", "production"]
    market: Market
    engagement_model: EngagementModel
    positions_required: list[Position] = Field(min_length=1)
    capacity_demand: CapacityDemand
    forge_dependencies: ForgeDependencies
    forge_operating_instructions: list[OperatingInstructionRef] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    budget: Budget
    human_capacity: list[HumanCapacity] = Field(min_length=1)
    separation_of_duties: SeparationOfDuties
    availability: Availability
    data_retention: list[DataRetention] = Field(default_factory=list)
    kpi_targets: dict[str, list[KpiTarget]] = Field(default_factory=dict)
    scenarios: list[Scenario] = Field(default_factory=list)
    lifecycle: Lifecycle

    @property
    def venture_id(self) -> str:
        """Stable slug used as `venture_id` everywhere downstream.

        Derived rather than authored so it cannot drift from the name, and so two
        Packs cannot claim the same venture by disagreeing about capitalisation.
        """
        return self.identity.venture_name.strip().lower().replace(" ", "-").replace("&", "and")

    @property
    def declared_frameworks(self) -> list[str]:
        return [c.framework for c in self.market.compliance_surface]


class PackLoadError(Exception):
    """The document is not a schema-v3 Business Pack."""


def load_pack(path: str | Path) -> BusinessPack:
    """Parse and shape-validate a Pack. Meaning is checked by the validator."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackLoadError(f"{p.name} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise PackLoadError(f"{p.name} does not contain a mapping at the top level")

    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise PackLoadError(
            f"{p.name} declares schema_version {version!r}; this Office reads "
            f"schema v{SCHEMA_VERSION} only. v1 and v2 Packs are not upgraded "
            "automatically - the tenant boundary moved, so a mechanical upgrade "
            "would produce a Pack that parses and means something different."
        )

    return BusinessPack.model_validate(raw)
