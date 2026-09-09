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
from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class HumanHeld(Strict):
    """A declared absence: this obligation is real, and no agent role holds it.

    **The third application of one pattern, and the reason it keeps recurring.**
    `compliance_couplings.NoFramework(why=...)` exists because `validate_sections`
    refused an empty coupling list, so SimForge's two modules carried
    `tsr_disclosure_required` - Greenstone's flag, on a Forge whose Packs declare
    `[]`. A schema that cannot express an honest absence gets a false value written
    into it. ADR-0049 is the same shape again for scenario classes: a declared
    `not_applicable` with a required reason, because a module that cannot supply a
    class was otherwise capped silently and permanently.

    This is the third. V22 requires every declared `runtime_flag` to appear in some
    scenario's `compliance_flags_exercised`, and for an obligation no position holds
    there is no true value - only inventing a scenario for a duty no role has, or
    deleting a real obligation. Both are false. So the absence is declared instead,
    and it carries the sentence that justifies it.

    **`why` is required and non-empty for the reason `NoFramework`'s is: nothing can
    tell an accidental declaration from a considered one.** Four of nine coupling rows
    were accidental empties before that was enforced.

    **This type does not gate anything on its own, and must never ship without the
    rule that checks a discharge.** Marking a flag human-held removes it from V22's
    subject; if nothing then asks whether the obligation was actually discharged, any
    flag nobody wants to write a scenario for could be marked human-held and V22 would
    go quiet. Today V22 fails loudly and wrongly - it names a missing scenario when the
    truth is that no agent holds the duty. `HumanHeld` without a discharge rule would
    pass silently and wrongly, which is worse: a loud wrong answer is at least read.

    **This was produced deliberately rather than argued.** On 8 September, with this
    type landed and no discharge rule, Burkham Wickmont validated at **32 PASS / 0 FAIL
    / 1 NOT_RUN of 33** - the single NOT_RUN being V24, which never runs at Gate 2 by
    construction. **Gate 2 cleared, for a venture whose referral-fee obligation nobody
    had verified, on the strength of one YAML key.** That is what this type does alone.
    It is why it and V34 ship together, and why that tree was never merged.
    """

    why: str = Field(min_length=1)

    #: Set when the obligation is real but its trigger has not fired, so no
    #: verification is due yet. See `PendingActivation`. Absent means the obligation is
    #: LIVE: V34 requires a current discharge and fails without one.
    pending_activation: PendingActivation | None = None


class PendingActivation(Strict):
    """The obligation is real, its trigger has not fired, and no verification is due.

    **This is the one state of the four that passes V34 without a discharge, so it is
    the one that could become the escape in a fourth costume.** What stops it is that it
    must carry a condition somebody can check.

    Burkham's is real: no referral fee has ever been paid, no partner relationship
    exists, and Partner Agreement & Payout Center is deferred to V1.5. **"Module 8.2
    activates and a referral relationship is being structured" is a condition a person
    can check. "When it becomes relevant" is not.**

    **What the schema enforces and what it cannot.** `activates_when` must exist and be
    substantial - a `min_length` catches the empty string and the one-word placeholder.
    **It cannot judge whether the condition is checkable**, because that is a semantic
    question about the world, and a validator that pretended to answer it would be
    asserting something it cannot know. **That check is a reviewer's, and this docstring
    is where they are told it is theirs.**

    The four states of a human-held obligation, of which this is one:

      pending_activation    real, trigger has not fired, no verification due  -> PASSES
      live_unverified       trigger fired, no current discharge               -> FAILS
      live_verified         current discharge covering the jurisdictions      -> PASSES
      verification_expired  lapsed, or scope no longer reaches                -> FAILS

    The bottom two are derived from `obligation_discharge`. **The distinction this type
    adds is "not yet due" versus "due and nobody has done it"** - and it is declared on
    the Pack rather than stored or derived, because **a clock cannot know whether a
    partner exists.**
    """

    #: The trigger. A reviewer must be able to check whether it has fired.
    activates_when: str = Field(min_length=20)

    #: What is deferred until then, and to whom. Kept beside the trigger so a reader
    #: asking "who does this become due for?" finds the answer in the same place.
    deferred_to: str = Field(min_length=1)


class ComplianceSurface(Strict):
    framework: ComplianceFramework
    jurisdiction: list[str] | Literal["FEDERAL", "ALL"]
    applies_when: str
    runtime_flag: str
    library_entry_ref: str | None = None
    library_gap: bool = False
    #: Set when no agent role holds this obligation. See `HumanHeld`; a human-held
    #: flag is accounted for by V22 and is the subject of the discharge rule instead.
    human_held: HumanHeld | None = None


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


class CapacityProvenance(Strict):
    """Where a reviewer's numbers came from. Required, and refused when it says nothing.

    **The third application of one pattern.** `compliance_couplings.NoFramework(why=...)`
    exists because a schema that could not express an honest absence got a false value
    written into it. ADR-0049's declared `not_applicable` is the same shape for scenario
    classes. `HumanHeld.why` is the same shape for an obligation no agent holds. In each,
    the fix is not "allow it to be empty" - it is **a distinct type that carries a
    reason**, so a considered value and an inherited one cannot be confused.

    This is that shape for capacity numbers, and it exists because they were confused.
    `blocking.md` B20 and B21: Burkham's `human_capacity` is byte-for-byte identical to
    Greenstone's, Burkham's copy is labelled INVENTED in a YAML comment that no schema
    requires and no rule reads, and **Greenstone's original carries no comment at all** -
    which made the unlabelled one the more dangerous of the two. V13 has been failing
    both ventures on those numbers, comparing a derived demand to an undocumented supply.

    **`basis` is the distinction that did not exist:**

      declared   a named person asserted it on a stated basis. Not measured, and honest
                 about that.
      inherited  copied from somewhere else. **`source` is required and must name where**,
                 because "copied from Greenstone's human_capacity block" is checkable and
                 "historical" is the cheap escape wearing a third costume.
      measured   derived from observation, and `source` names what was observed. **Note
                 `proposal.queue_to_decision_seconds` is NOT this** for `median_review_minutes`: it
                 is wall-clock including queue time, not review effort. See B21.

    **Every entry must carry one, including the ones that existed before this field.** A
    field new entries must fill while old ones sit exempt is a field that documents
    nothing - and filling the four that already exist is what retires B20 and B21 by
    construction rather than by trust.
    """

    basis: Literal["declared", "inherited", "measured"]

    #: Who established it. A person, not a role - "the compliance team" names nobody.
    established_by: str = Field(min_length=2)

    #: What it rests on. Long enough to be a sentence rather than a label.
    detail: str = Field(min_length=20)

    #: Required for `inherited` and `measured`; refused as a bare word. What was copied
    #: from, or what was observed.
    source: str | None = None

    @model_validator(mode="after")
    def _source_required_when_not_declared(self) -> CapacityProvenance:
        if self.basis in ("inherited", "measured"):
            # A bare word is refused regardless of length. The first cut used a
            # `< 10` threshold and "historical" - the exact example this field exists
            # to refuse - is ten characters, so it passed. A source names something,
            # which takes more than one token.
            src = (self.source or "").strip()
            if len(src) < 10 or len(src.split()) < 2:
                raise ValueError(
                    f"basis={self.basis!r} needs a `source` naming where the value came "
                    "from. 'Copied from Greenstone's human_capacity block' is checkable; "
                    "'historical' is not, and an unnamed source is the thing this field "
                    "exists to refuse."
                )
        return self


class HumanCapacity(Strict):
    human_name: str
    role: str
    coverage_hours: float
    timezone: str
    backup_human: str | None = None

    #: A declared daily figure that **nothing enforces**. It was `max_daily_approvals`,
    #: which reads as a cap; no gate, rule or validator reads it, and V13 computes its
    #: capacity verdict from `coverage_hours` and `median_review_minutes` alone. Its only
    #: consumer is a display: `broker.proposals.queue` subtracts today's decisions from
    #: it to show "N approvals left today". A reviewer may exceed it and nothing notices.
    #:
    #: Renamed rather than dropped because a per-reviewer daily cap is a reasonable
    #: control to declare and may become one; what could not persist was a number that
    #: looked enforced and was not. See `blocking.md` B23.
    advisory_daily_approval_ceiling: int

    median_review_minutes: float = 5.0
    auth_method: Literal["sso_mfa", "mfa_only"]
    #: Required. See `CapacityProvenance` - no default, because a default is how the
    #: four numbers this field exists for became unattributed in the first place.
    provenance: CapacityProvenance


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
