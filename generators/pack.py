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

# The enum is CLOSED and `Strict` forbids unknown keys, so a framework absent from
# this list cannot be declared at all — the Pack fails to load rather than warning.
# That is the right default (a typo'd framework is silently unenforced otherwise) and
# it means adding a venture's real compliance surface is a schema change, deliberately.
#
# The six below were added for Burkham Wickmont, whose ten declared frameworks could
# not be expressed: six had no value, and V3 requires a resolving `runtime_flag` per
# declared framework — so a framework that cannot be declared is one that cannot be
# enforced at runtime either. The gap was not cosmetic.
#
# Each is the STATUTE or rule an agent's behaviour couples to, not a topic. `FTC_TSR`
# is the Telemarketing Sales Rule and is NOT a general FTC Act value; the two are
# different obligations and conflating them would attach telemarketing duties to a
# video script, or Section 5 duties to an outbound call, at random.
ComplianceFramework = Literal[
    "HIPAA", "HCQC", "TILA", "FCRA", "ECOA", "UDAAP", "CROA", "FTC_TSR",
    "NRS_648_NV", "STATE_LENDER_LICENSURE", "MCA_DISCLOSURE_CA_SB1235",
    "TWO_PARTY_CONSENT_RECORDING", "VOICE_CLONING_CONSENT", "GDPR", "CCPA", "PCI_DSS",

    # --- Added for Burkham Wickmont -------------------------------------------
    #
    # GLBA. The notable one. Every Plaid connection carries Gramm-Leach-Bliley
    # obligations, and a lending venture handling client bank data had no way to
    # declare them. Decision A makes Plaid the V1 statement source, so this is a
    # framework Burkham engages on its first client, not an edge case.
    "GLBA",

    # 18 U.S.C. §1014 and §1344 — false statements on a credit application. This is
    # the criminal exposure behind the per-application written authorisation rule, and
    # it is why `submit_application` sits at the highest authority level. Named as one
    # value because the two sections attach to the same act.
    "FALSE_STATEMENT_TO_LENDER",

    # CFPB Regulation Z. TILA is already present as the statute; Reg Z is the rule that
    # implements it, and the trigger-term disclosure obligations an advertisement
    # engages are Reg Z's, not TILA's directly. Kept separate for that reason: a Pack
    # declaring TILA is saying something about cost-of-credit disclosure, and one
    # declaring Reg Z is saying something about how it advertises.
    "REG_Z_ADVERTISING",

    # CFPB Section 1071 - small-business lending data collection, phasing in 2026-2027
    # at the issuer level. Declarable now because the phase-in is inside the horizon
    # this venture launches in.
    "CFPB_1071",

    # State commercial financing disclosure regimes beyond California.
    # `MCA_DISCLOSURE_CA_SB1235` already covers CA. NY, UT, VA, GA, CT and FL each have
    # their own, and the Regulatory Engine holds per-state modules — so this value
    # carries the `jurisdiction` list rather than being split six ways.
    "STATE_COMMERCIAL_FINANCING_DISCLOSURE",

    # Card network rules — lawful-use language, cash-advance fee disclosure, AML and
    # sanctions obligations flowed down by Visa and Mastercard. Contractual rather than
    # statutory, and binding in the same way for an agent's behaviour. NOT PCI_DSS,
    # which is about cardholder data handling and is a different obligation entirely.
    "CARD_NETWORK_RULES",

    # Referral fee regulation, which varies by state and by product. Burkham pays
    # partners and referrers, so an agent proposing a payout engages this; `CCPA`'s
    # neighbour `STATE_LENDER_LICENSURE` covers who may lend, not who may be paid for
    # an introduction.
    "REFERRAL_FEE_REGULATION",

    # State comprehensive privacy regimes other than California's. `CCPA` is already a
    # value and stays one — it is the regime with the most distinct obligations — while
    # VCDPA, CPA, CTDPA and the rest share a shape and travel on the `jurisdiction`
    # list. Declaring only CCPA, as Burkham's documents effectively did, understates
    # the surface by every state but one.
    "STATE_PRIVACY_COMPREHENSIVE",

    # FTC Act § 5, 15 U.S.C. § 45. Its own value rather than an alias for UDAAP,
    # which was the first version of this list and was wrong. UDAAP is Dodd-Frank
    # § 1031, CFPB-enforced, and includes "abusive"; FTC Act § 5 is FTC-enforced UDAP.
    # Different statutes, different enforcers, different standards — and a venture
    # whose deceptive-claims discipline cites 15 U.S.C. § 45 is declaring this one.
    "FTC_ACT",

    # Not a statute, and it does not need to be. The enum already carries obligation
    # SURFACES rather than only statute names — TWO_PARTY_CONSENT_RECORDING and
    # VOICE_CLONING_CONSENT are both scope boundaries. This one is the boundary around
    # tax advice: Burkham prepares information a CPA uses and reaches no tax conclusion.
    # A statute earns a value when an agent must do something specific because of it;
    # IRC §163(j) does not, and the discipline around it does.
    "TAX_ADVICE_SCOPE",
]

#: Frameworks a reader may expect and will not find, with what to use instead.
#:
#: Written down because the failure mode is silent: a Pack author who cannot find
#: "FTC Act" may reach for `FTC_TSR`, which is the Telemarketing Sales Rule and a
#: different obligation, and the Pack would validate while attaching the wrong duties.
FRAMEWORK_ALIASES: dict[str, str] = {
    "FTC_ACT_SECTION_5": "FTC_ACT",
    "FTC_SECTION_5": "FTC_ACT",
    "REGULATION_Z": "REG_Z_ADVERTISING",
    "GRAMM_LEACH_BLILEY": "GLBA",
    "18_USC_1014": "FALSE_STATEMENT_TO_LENDER",
    "18_USC_1344": "FALSE_STATEMENT_TO_LENDER",
    "VCDPA": "STATE_PRIVACY_COMPREHENSIVE",
    "VISA_MASTERCARD_RULES": "CARD_NETWORK_RULES",
}
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
