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
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

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


class ModuleReviewer(Strict):
    """Which human role reviews one module's approvals, and why it is not the flags saying so.

    **A dict rather than a bare role string, and the `why` is required.** The same shape as
    `compliance_couplings.NoFramework(why=)`, `HumanHeld.why` and ADR-0049's declared
    `not_applicable` - three fields that exist because a schema which could not express a
    considered choice got a false value written into it instead. A bare role here would be
    the fourth: a routing decision with nothing recording what it was for.

    **It only narrows.** It may send a module's approvals to the compliance officer where
    the flags would have sent them elsewhere. It may never send a FLAGGED module's
    approvals away from the compliance officer - `Position` refuses that, naming the module
    and the flag. Allowing it with a reason attached would make this field a way to move
    compliance work off the compliance officer with a sentence. Decisions entry 108,
    ruling 4.
    """

    role: str = Field(min_length=2)

    #: Why this module routes here. Long enough to be a sentence rather than a label,
    #: because the thing worth recording is the arrangement and not the destination.
    why: str = Field(min_length=20)


class Position(Strict):
    """A venture-specific role. The Office names these; it does not look them up."""

    position_title: str
    reports_to: str
    duties: list[str]

    #: The modules this position operates, each as `forge_id/module_id`.
    #:
    #: **QUALIFY WHERE THE FIELD DOES NOT ALREADY CARRY THE FORGE. LEAVE IT BARE WHERE IT
    #: DOES.** That is the whole rule, it is checkable by reading the field's container,
    #: and it decides every module reference in a Pack:
    #:
    #:     forge_modules_operated          a flat list on a position. Nothing around it
    #:                                     names a Forge, so a bare name means nothing on
    #:                                     its own -> QUALIFY
    #:     module_trust_tiers              same position, same problem -> QUALIFY
    #:     forge_bindings[].modules_expected  nested inside a ForgeBinding whose first
    #:                                     field is `forge` -> the container carries it
    #:                                     -> LEAVE BARE. Qualifying would write the Forge
    #:                                     twice per entry and create a second place for
    #:                                     the two to disagree.
    #:     grant / certification / registry columns   `forge_id` and `module_id` are
    #:                                     separate columns -> already carried -> unchanged
    #:
    #: Qualified 14 September 2026, executing entry 48's ruling of the 13th. Until then
    #: this was bare while `module_trust_tiers` on the same position was qualified, and
    #: the validator below reconciled them by *discarding* the forge half to compare -
    #: two spellings for one concept, bridged by throwing information away.
    #:
    #: `module_forge_map`'s own docstring records what the bare form cannot express: a
    #: module id registered by two Forges resolves to whichever row came first, which it
    #: calls "deterministic rather than correct". Zero collisions existed when this
    #: landed. **Latent ambiguity is the cheapest state to fix, and the second Forge bound
    #: to a department is when it stops being latent.**
    forge_modules_operated: list[str]
    source_department: str
    compliance_flags_in_scope: list[str]
    headcount: int = Field(ge=1)
    trust_tier_ceiling: TrustTier

    #: Per-module overrides of `trust_tier_ceiling`, keyed `forge_id/module_id`.
    #:
    #: **Qualified from the first line it was written**, while it costs nothing. A bare module
    #: name is unambiguous only while one Forge is bound, and `forge_module_registry`'s primary
    #: key is `(forge_id, module_id)` - the schema has always permitted two Forges exposing one
    #: name. `client_read` and `client_read_pii` both being CapitalForge is the near-miss that
    #: makes a bare key look safe.
    #:
    #: Absent means today's behaviour exactly: one tier across every module this position
    #: operates.
    #:
    #: **The storage was always per-module; only the declaration was not.**
    #: `agent_forge_grant` carries one `trust_tier` per (agent, forge, module) row and
    #: `resolve_grant` gates each call on that row's value - so a position holding
    #: `client_read` at `auto_execute` and `submit_application` at `propose` has always been a
    #: representable, enforceable runtime state. What did not exist was a way for a Pack to ask
    #: for it, so `runtime_config` fanned one ceiling across every module an agent held.
    #:
    #: **Why a position and not a workflow step.** The tier is authority granted to an agent for
    #: a module; a step is work that uses it. The same module reached from two steps is the same
    #: authority, and declaring it twice invites the two to disagree.
    #:
    #: A tier here is still a CEILING. Certification caps it per Part 10.1, and an agent
    #: certified below its declared tier operates at the certified one.
    module_trust_tiers: dict[str, TrustTier] = Field(default_factory=dict)

    #: Which ONE lifecycle stage this module runs in, keyed `forge_id/module_id`.
    #:
    #: **The workflow generator emitted the cross product, and the projection billed for
    #: it.** Steps are stage-major - every stage, then every position owning it, then every
    #: module that position operates - so a position owning two stages emitted each of its
    #: modules TWICE. Greenstone's Deal Underwriter owns Underwrite and Contract and
    #: operates two modules: four steps, and the Contract stage contains no Deal Underwriter
    #: module at all. Burkham's Compliance Reviewer owns Readiness and Placement and
    #: operates three: six steps for three modules.
    #:
    #: The projection counts per (step, holder, module), so each duplicate was a second
    #: approval a day for one piece of work. `module_trust_tiers` above already states the
    #: principle this field completes: *"The same module reached from two steps is the same
    #: authority, and declaring it twice invites the two to disagree."* The tier was
    #: declared once per module. The step was not.
    #:
    #: Measured across this change: Greenstone 12 steps -> 6, Burkham 15 -> 10.
    #:
    #: **Undeclared blocks rather than defaulting.** Falling back to the first stage owned
    #: would place the module by list order, and B24 is what happens when a gate verdict
    #: turns on which line came first in the YAML.
    module_stages: dict[str, str] = Field(default_factory=dict)

    #: Expected invocations per WEEK, keyed `forge_id/module_id`.
    #:
    #: **This is what replaces `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8`** - an unattributed
    #: constant (entry 46) that stood in for every module of every venture. Greenstone
    #: projected 64 approvals a day against a venture closing one deal a week.
    #:
    #: **Per week, because that is the unit the basis is stated in.** The Greenstone basis
    #: is "about one closed assignment a week, ramping to two by Month 12". Converting that
    #: by hand before writing it down would put an arithmetic step between the ruling and
    #: the Pack, in the one place nobody would check it.
    #: `capacity_demand.operating_days_per_week` performs the conversion and is itself
    #: declared, so no divisor is inferred anywhere.
    #:
    #: **Not multiplied by headcount.** A rate is a property of the business, not of the
    #: roster: two Deal Underwriters do not make the venture close twice as many deals. The
    #: old constant WAS per holder, which is why adding a headcount raised projected demand
    #: without anything new happening in the world.
    #:
    #: A module at `auto_execute` needs no entry - it asks nobody, so no volume of it can
    #: reach a reviewer. Every other operated module must carry one, or the projection
    #: blocks and names it.
    expected_weekly_volume: dict[str, float] = Field(default_factory=dict)

    #: Where `expected_weekly_volume` came from. Required as soon as any volume is declared.
    #:
    #: Reuses `CapacityProvenance` deliberately rather than defining a parallel type: a
    #: volume is the same kind of claim as a review time, and it fails the same way -
    #: asserted once, inherited silently, never attributed. B20 and B21 are that failure for
    #: the numbers one field over.
    volume_provenance: CapacityProvenance | None = None

    #: Which human role reviews this module's approvals, keyed `forge_id/module_id`.
    #:
    #: **Routing was a side effect of compliance flags and nothing could state it.**
    #: `_reviewer_for` sent flagged work to the compliance officer and everything else to
    #: the venture operator, per POSITION - so a module's reviewer was decided by the other
    #: modules its position happened to operate.
    #:
    #: Greenstone's `assign_contract` is the case. It routes to the compliance officer
    #: today only because Buyer Network Manager carries `recording_consent_required`. The
    #: moment that flag becomes founder-held and leaves the position, the approval lands on
    #: the venture operator - Ivan, who usually wrote the MAO, which is the arrangement the
    #: ruling forbids. Measured: `{compliance_officer: 0.2}` becomes
    #: `{venture_operator: 0.2}`, and nothing fails.
    #:
    #: **Both gates read it identically**, because it is declared rather than derived. Gate
    #: 2 routes by declared flags and Gate 4.5 by declared UNION implied; a module that
    #: declares its reviewer is not exposed to that difference at all.
    module_reviewer_roles: dict[str, ModuleReviewer] = Field(default_factory=dict)

    #: Declared, unfilled, and not yet activated. `None` is an ordinary position.
    #:
    #: **`headcount` stays `ge=1` and keeps its real number.** A pending position is not a
    #: position of zero people - it is a position of two that no agent holds yet, and
    #: writing 0 would lose the size of the thing being deferred. What changes is who counts
    #: it: V24 skips it and names it, appointment emits it unfilled without calling that a
    #: shortfall, the projection takes no agent demand from it, and bootstrap refuses to
    #: certify a pair whose only operator is this.
    #:
    #: **`deferred_to` is where the humans holding the work are named, and it is prose.**
    #: It is not checked against `office_human`, the way `human_name` and `backup_human`
    #: are. If it should ever be checked, that comes after the rename - "Ivan Green" is not
    #: yet what the account is called. Recorded so the next reader does not mistake a
    #: sentence for a join.
    #:
    #: Reuses `PendingActivation` rather than defining a parallel type. The shape is the
    #: same one Burkham's referral-fee obligation uses and the discipline is the same: a
    #: trigger a reviewer can check, not "when it becomes relevant".
    pending_activation: PendingActivation | None = None

    @property
    def module_ids(self) -> list[str]:
        """The bare `module_id` of each operated module, in declared order.

        **The projection that makes the qualified declaration usable, named rather than
        inlined.** `forge_module_registry` keys on `(forge_id, module_id)` as two columns,
        so every lookup against it needs the bare half - and before entry 48 was executed
        each call site did that split silently inside a comparison, which is the shape the
        ruling objected to. Splitting is not the defect; splitting *invisibly* is. This is
        the same operation with a name, so a reader sees a projection happening.

        Use `module_pairs` wherever the Forge is also needed. Reach for this one only when
        comparing against something that carries the Forge separately.
        """
        return [m.split("/", 1)[1] for m in self.forge_modules_operated]

    @property
    def module_pairs(self) -> list[tuple[str, str]]:
        """`(forge_id, module_id)` for each operated module, in declared order.

        The shape `forge_module_registry`, `agent_forge_grant` and `certification` all key
        on. Preferred over `module_ids` anywhere the Forge matters, because it cannot lose
        the half that the qualification exists to carry.
        """
        return [(f, m) for f, m in (x.split("/", 1) for x in self.forge_modules_operated)]

    @field_validator("forge_modules_operated")
    @classmethod
    def _modules_are_qualified(cls, value: list[str], info: ValidationInfo) -> list[str]:
        """Each entry is `forge_id/module_id`, and the two failure kinds are signalled apart.

        A FIELD validator rather than a model one, so the error's location NAMES the
        field - `positions_required.0.forge_modules_operated`. A model validator reports
        at the position, which elides to `("positions_required",)` and cannot be told from
        any other failure on the same object. `broker.packs.V3_QUALIFICATIONS` keys on the
        field path, so the location is load-bearing rather than cosmetic.

        TWO BRANCHES, TWO ERROR TYPES, AND THE SPLIT IS THE POINT.

        A BARE name is a document written before entry 48 landed on 14 September 2026 -
        valid under the revision of v3 it was published as, and a row to migrate rather
        than a document to inspect. It is signalled with a `PydanticCustomError` whose
        type the Pack store's ledger names, so a stored row reports as OLD not MALFORMED.

        A name with MORE than one separator was never valid under any revision. It stays a
        plain `ValueError`, which `_predated_tightenings` refuses like every other
        validator failure - *"a wrong type or a failed validator is a document that
        disagrees with the schema, not one that is older than it."*

        The distinction is made HERE, once, where the values are in hand. The matcher
        reads the signal rather than re-deriving it: a second derivation is a second place
        to disagree.
        """
        title = info.data.get("position_title", "position")

        unqualified = sorted(m for m in value if m.count("/") == 0)
        if unqualified:
            raise PydanticCustomError(
                "unqualified_module_ref",
                "{title}: forge_modules_operated entries must be 'forge_id/module_id'. "
                "Unqualified: {names}. Nothing around this list names a Forge, so a bare "
                "module name is unambiguous only while one Forge is bound - and "
                "`forge_module_registry`'s key has always been the pair. QUALIFY WHERE "
                "THE FIELD DOES NOT ALREADY CARRY THE FORGE; "
                "`forge_bindings[].modules_expected` stays bare because its container's "
                "first field is `forge`.",
                {"title": title, "names": ", ".join(unqualified)},
            )

        malformed = sorted(m for m in value if m.count("/") > 1)
        if malformed:
            raise ValueError(
                f"{title}: forge_modules_operated entries are 'forge_id/module_id', "
                f"exactly one separator. Malformed: {', '.join(malformed)}. This is not a "
                "Pack that predates the qualification - no revision of v3 ever accepted "
                "this shape."
            )
        return value

    @model_validator(mode="after")
    def _overrides_are_qualified_and_operated(self) -> Position:
        """Keys are `forge_id/module_id`, and name a module this position operates.

        Two checks, and they fail differently on purpose. An unqualified key is a form error
        the author can fix without knowing the venture; an unoperated module is a typo or a
        stale edit and needs the position's own list to diagnose.

        Refused rather than ignored: a silently-ignored override reads as applied, and the
        failure mode is a module running at a tier somebody believes they lowered.

        The forge half is checked against `forge_dependencies` at Pack level - a position
        cannot see the bindings from here.
        """
        unqualified = sorted(k for k in self.module_trust_tiers if k.count("/") != 1)
        if unqualified:
            raise ValueError(
                f"{self.position_title}: module_trust_tiers keys must be 'forge_id/module_id'. "
                f"Unqualified: {', '.join(unqualified)}. A bare module name is unambiguous only "
                "while one Forge is bound."
            )
        # Both sides qualified since 14 September 2026, so they are compared directly.
        # This used to be `k.split("/", 1)[1] not in operated` - the forge half discarded
        # to make a qualified key match a bare list, which is what entry 48 ruled against.
        operated = set(self.forge_modules_operated)
        unknown = sorted(k for k in self.module_trust_tiers if k not in operated)
        if unknown:
            raise ValueError(
                f"{self.position_title}: module_trust_tiers names {', '.join(unknown)}, which "
                f"this position does not operate. It operates {', '.join(sorted(operated))}."
            )
        return self

    @model_validator(mode="after")
    def _stage_and_volume_maps_are_well_formed(self) -> Position:
        """`module_stages` and `expected_weekly_volume` name operated modules and owned stages.

        The same two error kinds as the tier map above, for the same reason: an unqualified
        key is a form error fixable without knowing the venture, an unoperated module is a
        stale edit that needs the position's own list to diagnose.

        **Absence is not checked here.** A Pack authored before these fields existed must
        still LOAD - Burkham's does, and blocking it at parse time would replace a named
        rule failure with a stack trace before any gate ran. What an undeclared volume must
        do is block the projection, by name, which is `approval_projection`'s job and not
        the parser's.

        The stage half is checked against this position's own `lifecycle_stages_owned`
        rather than the Pack's stage order: a position cannot run a module in a stage it
        does not own, and that is the tighter of the two checks.
        """
        operated = set(self.forge_modules_operated)
        for field_name, mapping in (
            ("module_stages", self.module_stages),
            ("expected_weekly_volume", self.expected_weekly_volume),
        ):
            unqualified = sorted(k for k in mapping if k.count("/") != 1)
            if unqualified:
                raise ValueError(
                    f"{self.position_title}: {field_name} keys must be "
                    f"'forge_id/module_id'. Unqualified: {', '.join(unqualified)}."
                )
            unknown = sorted(k for k in mapping if k not in operated)
            if unknown:
                raise ValueError(
                    f"{self.position_title}: {field_name} names {', '.join(unknown)}, "
                    f"which this position does not operate. It operates "
                    f"{', '.join(sorted(operated))}."
                )

        if self.lifecycle_stages_owned:
            owned = set(self.lifecycle_stages_owned)
            wrong = sorted(
                f"{k} -> {v}" for k, v in self.module_stages.items() if v not in owned
            )
            if wrong:
                raise ValueError(
                    f"{self.position_title}: module_stages puts {'; '.join(wrong)}, but "
                    f"this position owns {', '.join(sorted(owned))}. A position cannot "
                    "run a module in a stage it does not own."
                )

        unqualified = sorted(k for k in self.module_reviewer_roles if k.count("/") != 1)
        if unqualified:
            raise ValueError(
                f"{self.position_title}: module_reviewer_roles keys must be "
                f"'forge_id/module_id'. Unqualified: {', '.join(unqualified)}."
            )
        unknown = sorted(k for k in self.module_reviewer_roles if k not in operated)
        if unknown:
            raise ValueError(
                f"{self.position_title}: module_reviewer_roles names "
                f"{', '.join(unknown)}, which this position does not operate. It operates "
                f"{', '.join(sorted(operated))}."
            )

        # RULING 4: A DECLARATION ONLY NARROWS.
        #
        # A flagged module may be routed TO the compliance officer and never away from one.
        # The alternative - allow it and rely on somebody reading the `why` - makes this
        # field a way to move compliance work off the compliance officer with a sentence
        # attached. Decisions entry 108.
        #
        # **Checked against DECLARED flags only, because that is all a Pack can see.**
        # `forge_module_registry.compliance_flags_implied` is a live world read and does not
        # exist at parse time, so a module flagged ONLY by the registry is not caught here.
        # Measured when this landed and there is no such case: CRE Forge implies no flags
        # since entry 105, and Burkham declares no reviewers. Recorded rather than left to
        # be discovered, same shape as the Gate 2 / Gate 4.5 flag divergence in entry 107.
        if self.compliance_flags_in_scope:
            away = sorted(
                (k, v.role) for k, v in self.module_reviewer_roles.items()
                if v.role != "compliance_officer"
            )
            if away:
                named = "; ".join(f"{k} -> {role}" for k, role in away)
                raise ValueError(
                    f"{self.position_title}: module_reviewer_roles routes {named}, but this "
                    f"position carries {', '.join(sorted(self.compliance_flags_in_scope))}. "
                    "A declared reviewer only narrows: it may send a module's approvals to "
                    "the compliance officer and may never send a flagged module's approvals "
                    "away from one."
                )

        if self.expected_weekly_volume and self.volume_provenance is None:
            raise ValueError(
                f"{self.position_title}: expected_weekly_volume is declared with no "
                "volume_provenance. A rate nobody is named for is the defect B20 and B21 "
                "record one field over."
            )
        return self
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

    #: How many days a week this venture operates. The divisor that turns a weekly
    #: `expected_weekly_volume` into the daily rate both V13s compare against.
    #:
    #: **Declared, because nothing in a Pack supplied one.** Measured before this field
    #: existed: `agent_days_per_week` is agent-days summed across the venture (35 for
    #: Greenstone, 40 for Burkham), not a calendar week; `shift_pattern` says "5
    #: shifts/week" in free prose in both Packs; `ramp_schedule` carries agent-days in the
    #: same units as the first. Gate 2's V13 divided `agent_days_per_week` by a hardcoded
    #: `7.0` and nothing said why.
    #:
    #: Reading "5 shifts/week" out of `shift_pattern` was the available shortcut and is
    #: refused: a divisor parsed from prose is a number whose provenance is a regex.
    #:
    #: **Optional in the schema, required in practice.** A Pack authored before this field
    #: must load; what it must not do is reach a verdict. `approval_projection` blocks and
    #: names the venture when a weekly volume needs converting and this is absent.
    operating_days_per_week: float | None = Field(default=None, gt=0)
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


# `Position.volume_provenance` is annotated `CapacityProvenance | None`, and Position is
# defined above it. With `from __future__ import annotations` the annotation is a string,
# so the model is left incomplete until the name resolves. Rebuilt here, explicitly, rather
# than relying on `BusinessPack`'s construction to do it as a side effect.
Position.model_rebuild()


class HumanCapacity(Strict):
    human_name: str
    role: str

    #: The person's TOTAL declared hours a day for this venture. Kept, and now documented
    #: as the total rather than as review time, which is what it had silently been.
    #:
    #: `broker.proposals.queue` and the console's reviewer card display this, and a total
    #: is the right thing to show there - "6h" is the commitment. What was wrong was V13
    #: reading it as review supply.
    coverage_hours: float

    #: Of `coverage_hours`, the part spent reviewing. **The only figure V13 counts as
    #: supply, at either gate.**
    #:
    #: `coverage_hours` meant review coverage and nothing else, so there was nowhere to put
    #: "4h writing, 1h countersigning" (entry 96 §5). Declaring those hours as coverage
    #: asserts review capacity that is committed elsewhere; omitting them understates what
    #: the person is doing. The schema had one kind of hour and the venture has three.
    review_hours: float | None = Field(default=None, ge=0)

    #: Of `coverage_hours`, the part spent countersigning.
    #:
    #: **Countersigns create demand, and nothing projects it yet - that gap is open, not
    #: closed by this field.** V13's demand is keyed to (workflow step, holder, module):
    #: agent-originated proposals. A countersign is keyed to an ARTIFACT - an MAO, an
    #: assignment agreement - authored by a human, and `proposal.office_agent_id` is NOT
    #: NULL, so The Office cannot raise a human-authored item at all (entry 96 §3).
    #:
    #: So this hour is declared and subtracted from review supply, which is honest, and its
    #: demand is not projected, which is incomplete. Sizing it needs the human-authored-item
    #: surface first. Recorded rather than approximated: a countersign demand invented here
    #: would be the constant 8 again, one field over.
    countersign_hours: float | None = Field(default=None, ge=0)

    #: Of `coverage_hours`, everything that is neither review nor countersign - writing
    #: MAOs, seller calls, dispositions. Declared so the total reconciles, and counted as
    #: supply by nothing.
    other_hours: float | None = Field(default=None, ge=0)
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

    #: **Required. No default, as of 13 September 2026.**
    #:
    #: It carried `5.0`, which meant omitting it did not withhold a number - it asserted five
    #: minutes, unattributed, with no provenance able to describe where five came from. The field
    #: immediately below already said why that is wrong: *"no default, because a default is how the
    #: four numbers this field exists for became unattributed in the first place."* That comment
    #: was about this field, and this field was the one that still had one.
    #:
    #: The number remains unmeasured for every venture in this repository - no review has ever been
    #: timed, and `proposal.queue_to_decision_seconds` is wall-clock including queue rather than
    #: review effort (B21). `provenance` is where that is said; V13 carries it into its evidence
    #: so a reader cannot act on a shortfall without meeting what the shortfall was computed from.
    median_review_minutes: float
    #: How this reviewer authenticates. **The Pack may only name what the platform can
    #: enforce** - ruled 21 September 2026, entry 159, checked by V42.
    #:
    #: `bearer_token` joins the two that were here because it is what every account on
    #: this platform actually had while both Packs declared `sso_mfa`: a token The Office
    #: issued and stores hashed. `sso_mfa` stays SPELLABLE so an existing Pack still
    #: parses and V42 can report it as the finding it is, rather than the document
    #: failing to load with a schema error that says nothing about why.
    auth_method: Literal["bearer_token", "sso_mfa", "mfa_only"]
    #: Required. See `CapacityProvenance` - no default, because a default is how the
    #: four numbers this field exists for became unattributed in the first place.
    provenance: CapacityProvenance

    @property
    def hours_are_split(self) -> bool:
        """Whether this entry declares what its hours are spent on."""
        return self.review_hours is not None

    @model_validator(mode="after")
    def _the_split_is_whole_or_absent(self) -> HumanCapacity:
        """All three kinds, or none, and they add up to the total.

        **All-or-nothing, because a half-declared split is worse than none.** With
        `review_hours` given and `other_hours` omitted, the missing hours read as zero and
        the entry asserts that the person does nothing but review and countersign - a
        stronger claim than the Pack meant to make, arrived at by leaving a field out.

        **The sum is checked because the total is what the console shows.** A split that
        does not reconcile leaves the reviewer card and V13 describing two different people.
        Tolerance is 0.01h so a declared 0.5 + 0.25 + 0.25 is not refused by float
        representation.

        A Pack that declares no split loads. It does not reach a V13 verdict - that is the
        rule's refusal to make, with the role named, not the parser's.
        """
        kinds = {
            "review_hours": self.review_hours,
            "countersign_hours": self.countersign_hours,
            "other_hours": self.other_hours,
        }
        declared = {k: v for k, v in kinds.items() if v is not None}
        if not declared:
            return self
        if len(declared) != len(kinds):
            missing = ", ".join(sorted(set(kinds) - set(declared)))
            raise ValueError(
                f"{self.human_name}: {missing} left undeclared beside "
                f"{', '.join(sorted(declared))}. Declare all three or none - an omitted "
                "kind reads as zero, which asserts more than leaving the split out does."
            )
        total = sum(kinds.values())  # type: ignore[arg-type]
        if abs(total - self.coverage_hours) > 0.01:
            raise ValueError(
                f"{self.human_name}: review {self.review_hours:g} + countersign "
                f"{self.countersign_hours:g} + other {self.other_hours:g} = {total:g}, "
                f"against coverage_hours {self.coverage_hours:g}. The split must "
                "reconcile with the total the console shows."
            )
        return self


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

    @model_validator(mode="after")
    def _tier_overrides_name_a_bound_forge(self) -> BusinessPack:
        """The forge half of every `module_trust_tiers` key names a Forge this Pack binds.

        The position validator checks the form and that the module is operated; it cannot see
        `forge_dependencies` from inside a position. This is the other half, and it is what
        makes a qualified key MEAN something rather than merely look qualified.

        Checked against the binding's own `modules_expected`, which is where this Pack already
        carries the (forge, module) pairing - so `capitalforge/place_call` is caught as wrong
        even though both halves exist somewhere.
        """
        bound = {
            b.forge: set(b.modules_expected) for b in self.forge_dependencies.forge_bindings
        }
        wrong: list[str] = []
        for position in self.positions_required:
            for key in position.module_trust_tiers:
                forge, module = key.split("/", 1)
                if forge not in bound:
                    wrong.append(
                        f"{position.position_title}: {key} names Forge {forge!r}, which this "
                        f"Pack does not bind (bound: {', '.join(sorted(bound))})"
                    )
                elif module not in bound[forge]:
                    wrong.append(
                        f"{position.position_title}: {key} - {forge!r} is bound but does not "
                        f"expect {module!r}"
                    )
        if wrong:
            raise ValueError("; ".join(wrong))
        return self

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
