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
from dataclasses import dataclass, field, fields, is_dataclass
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
        # `fields` + `getattr` rather than `asdict`, because asdict converts NESTED
        # dataclasses itself and this function would then never see them - so a nested
        # instance could not declare anything about its own serialisation. The output
        # is otherwise identical: every value still goes through `_plain` below.
        out = {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
        # A dataclass may declare that a field does not apply to the instance it is
        # on, and an inapplicable field is DROPPED rather than emptied. An empty value
        # in the place a real one used to sit reads as "not yet filled in"; an absent
        # key can only be read one way. See CurriculumScenario.omit_from_serialisation
        # and docs/scenario-contract.md section 12.
        omit = getattr(value, "omit_from_serialisation", None)
        for key in omit() if omit is not None else ():
            out.pop(key, None)
        return out
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

    #: `forge_id/module_id` for each operated module, carrying the Pack's declaration
    #: through unchanged.
    #:
    #: **Qualified 14 September 2026, executing entry 48. This moved `artifacts_hash`**,
    #: which is what a Gate 10 signature binds to - the same class of change as
    #: `certified_tiers` in entry 52, and the reason both live Packs were republished and
    #: their runs restarted rather than re-signed in place.
    #:
    #: Use `module_ids` to compare against anything keyed on the bare id, and
    #: `module_pairs` wherever the Forge matters. Splitting inline is what this
    #: qualification was ruled against.
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

    #: Per-module overrides of `trust_tier_ceiling`. Empty means one tier across every module,
    #: which is what every Pack declared before 13 September 2026.
    #:
    #: Last, and defaulted, so the field order of this artifact is unchanged for every existing
    #: construction site - this class is frozen, slotted, and hashed into `artifacts_hash`, so a
    #: field inserted in the middle would be a signature change dressed as an addition.
    module_trust_tiers: dict[str, str] = field(default_factory=dict)

    #: Which ONE stage each module runs in, carried through from the Pack. The workflow
    #: generator reads it to emit one step per module instead of one per (stage, module).
    module_stages: dict[str, str] = field(default_factory=dict)

    #: Declared invocations per week, per module. Carried so the artifact records the rate
    #: the projection was computed from - a projection whose inputs are only in the Pack is
    #: a number a reader has to go and find.
    expected_weekly_volume: dict[str, float] = field(default_factory=dict)

    #: Which human role reviews each module's approvals, keyed `forge_id/module_id`.
    #:
    #: The ROLE only. The `why` stays in the Pack, which is stored verbatim as
    #: `business_pack.yaml_source`, so the reason is preserved where it was written
    #: rather than copied into an artifact that would then have two of it.
    module_reviewer_roles: dict[str, str] = field(default_factory=dict)

    #: Declared, unfilled, pending activation.
    pending: bool = False

    #: Who holds the work until it activates. **Prose, and checked against no account** -
    #: unlike `human_name` and `backup_human`, which resolve against `office_human`. If it
    #: should ever be checked, that comes after the rename.
    pending_deferred_to: str = ""

    #: Appended, defaulted, and last - for the reason `module_trust_tiers` states above:
    #: this class is frozen, slotted and hashed into `artifacts_hash`, so a field inserted
    #: in the middle is a signature change dressed as an addition.

    @property
    def module_ids(self) -> list[str]:
        """The bare `module_id` of each operated module, in order.

        The named projection for comparing against anything keyed on the bare id -
        `forge_module_registry`, `forge_operating_instruction`, the curriculum's module
        set. Mirrors `generators.pack.Position.module_ids`, and exists for the same
        reason: splitting is fine, splitting invisibly inside a comparison is not.
        """
        return [m.split("/", 1)[1] for m in self.forge_modules_operated]

    @property
    def module_pairs(self) -> list[tuple[str, str]]:
        """`(forge_id, module_id)` for each operated module, in order."""
        return [(f, m) for f, m in (x.split("/", 1) for x in self.forge_modules_operated)]


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

    #: Every module the position operates - **the exam roster**, and what Gate 5 issues a
    #: grant for.
    #:
    #: Ruled 21 September 2026 (entry 145). Grants were built from `certified_modules`,
    #: which made the ladder circular: an uncertified appointee got no grant, so
    #: `_exam_takers` found nobody, so no exam was set, so no verdict could ever be
    #: written. The two lists were one until the circle had to be cut, and this is the
    #: half that says what an agent may be EXAMINED on.
    modules: list[str]

    #: The subset of `modules` this agent already holds a current unit-A certification
    #: for. What an agent may be TRUSTED with, and still the only list `certified` and
    #: the capacity numbers are computed from.
    certified_modules: list[str]

    #: The tier this agent operates each module at, keyed `forge_id/module_id`. The lower of
    #: what the Pack declares for that module and what the agent is certified to, for the
    #: modules it IS certified on.
    #:
    #: **This replaced a single `certified_tier` on 13 September 2026, and the property given up
    #: is worth naming.** That field was the WEAKEST certified tier across every module the
    #: position operated, capped by the position ceiling - so an agent certified `auto_execute`
    #: on four modules and `propose` on a fifth operated all five at `propose`. A position-wide
    #: floor, and a real safety default: one weak certification restrained everything beside it.
    #:
    #: **It is given up because it is the model per-module tiers exist to replace.** A position
    #: is not one authority level. Keeping the floor meant the concept was declarable in a Pack,
    #: storable in `agent_forge_grant`, enforceable by `resolve_grant` and certifiable by
    #: `record_result` - and invisible at the one place V13 reads it, which made every
    #: per-module declaration inert.
    #:
    #: **What replaces it is stricter per call, not looser.** The floor was one number applied
    #: to a whole position; this is one number per module, enforced at the grant on every call
    #: by `resolve_grant`, which raises `NotCertified` unless that module's own certification is
    #: current. A module that should be restrained is restrained by its own tier rather than by
    #: the weakest of its neighbours - and a module that should not be is no longer dragged down
    #: by one.
    #:
    #: **A module the agent is not certified on is ABSENT from this map**, ruled
    #: 21 September 2026: *"an uncertified module's planned tier reads as none, not the
    #: declared tier. A plan that claims authority nothing earned reads as authority."*
    #: Never blanked and never floored to `suggest`, which is still an authority level.
    certified_tiers: dict[str, str]

    #: How many of this position's modules the agent already holds a live grant for.
    #:
    #: The first ranking key, ruled 21 September 2026. A grant is what an exam is opened
    #: against, so a seat moving away from a holder discards an exam in flight. Counted
    #: rather than flagged: full incumbency outranks partial, and partial outranks none,
    #: without anybody having to pick a threshold.
    live_grants: int = 0

    def omit_from_serialisation(self) -> tuple[str, ...]:
        """`live_grants` is a ranking input, not a fact about the appointment.

        **AND IT MUST NOT REACH `artifacts_hash`.** Appointment now reads
        `agent_forge_grant`, and Gate 5 WRITES it. A grant-derived field in the artifact
        is a feedback loop: Gate 5 issues grants for the agents it seated, the next
        regeneration sees them, the hash moves, and every Gate 10 signature bound to the
        old hash goes void. Measured the first time this was built - twelve tests went
        red with `Gate 10 awaiting_human`, on a run where nothing about the appointment
        had changed.

        The ORDERING it feeds is stable under that loop, which is why it can be used at
        all: Gate 5 grants to exactly the agents already seated, so preferring grant
        holders re-seats the same agents. The number changes; the seating does not.

        Dropped, not zeroed. A `0` sitting where a real count used to sit reads as "this
        agent holds nothing", which would be false for every agent after Gate 5.
        """
        return ("live_grants",)

    #: Unit A current on every module in `modules` **and** unit B current on every Forge
    #: they touch. Both, exactly as 5.2 requires - what entry 145 moved is where that
    #: test is enforced, not what it means.
    #:
    #: **This is the field that keeps the gap report honest.** An appointment may now
    #: contain an uncertified agent, so a reader counting `len(appointed)` would be
    #: reading a staffing level that cannot operate. `CapacityNumbers.certified_and_free`
    #: counts this flag, and `requires_certification` still names every uncertified
    #: candidate with the specific state that explains it.
    certified: bool = True


@dataclass(frozen=True, slots=True)
class CandidateShortfall:
    office_agent_id: str
    agent_name: str
    reason: str
    """`never_certified` | `in_training` | `stale_instructions` | `stale_forge` |
    `failed` | `revoked` | `wrong_department` | `missing_unit_b` |
    `module_not_registered`.

    **Two of these mean "not eligible" and the rest mean "not certified", and after
    entry 145 that difference decides whether the candidate can fill a seat.**
    `revoked` and `module_not_registered` say the agent cannot sit the exam at all;
    every other value says the exam has not been passed yet, which is what Gate 4.5
    stopped refusing a seat for.

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

    #: Set when the last seat was decided by roster order - that is, when the candidate
    #: seated and the candidate passed over were indistinguishable on grants held and on
    #: certification, so nothing but the alphabet separated them.
    #:
    #: Ruled 21 September 2026: *"the tie-break is reported, never silent."* `None` when
    #: the boundary was decided by a reason, because a reason is reported by the field it
    #: is read from.
    tie_break: str | None = None

    def omit_from_serialisation(self) -> tuple[str, ...]:
        """Reported at Gate 4.5, not carried in the hashed artifact.

        Same reason as `AppointedAgent.live_grants`, one level up: whether the boundary
        was a tie depends on who holds a grant, and Gate 5 writes grants. Left in the
        artifact it would flip from a sentence to `null` the first time a venture's
        grants were issued, and void the Gate 10 signature for it.

        **It is still never silent.** V24 puts it in the Gate 4.5 result's own sentence,
        which is what an operator reads and what the Provisioning Console renders - and
        that is where a decision about who operates a venture belongs, rather than in a
        file whose job is to be signed.
        """
        return ("tie_break",)

    #: Declared, unfilled, pending activation. Emitted rather than omitted so V24 can NAME
    #: it: a position that vanished from the appointment would be a position nobody could
    #: report, which is the opposite of declaring it deferred. `unfilled` is 0 for such an
    #: entry - the headcount is not a shortfall, it is a decision.
    pending: bool = False


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
    """**Counts candidates EXAMINED FOR POSITIONS BEING APPOINTED. Not uncertified
    identities in the venture.**

    The name reads as a fact about the venture - *how many agents have been produced and
    are not yet certified*. It is a fact about **one appointment run**. It increments
    inside the per-position candidate loop in `generators.appointment`, once per candidate
    that loop examined and refused, and only for `never_certified`, `in_training` and
    `missing_unit_b`. An uncertified identity in a department no position draws on is
    never counted, because it is never examined.

    How the two readings were separated, since both survive most evidence: issuing 12
    operations identities moved it 14 -> 26, which **both** readings predict, because
    operations feeds a Greenstone position - every new identity was also a candidate.
    Issuing 25 administration and marketing identities moved it **26 -> 26**. Greenstone
    has no position in either department, so nothing examined them. See `docs/decisions.md`
    entry 27 and `blocking.md` B23.

    **The identically-named number on `GET /api/ventures/{id}/capacity` is a different
    population.** That one counts every active row in `office_agent_identity` with no
    certified unit-A row, across all departments, examined or not. Two numbers, one name,
    and they do not have to agree. `tests/golden/test_generators.py` pins the divergence.

    **Not renamed. Escalated.** The field is serialized into
    `tests/golden/snapshots/greenstone_appointment.json` and into `artifacts_hash`, which
    Gate 4.5 signatures are taken against, and one of its call sites is off-limits to the
    package that found this. See `PARALLEL_BUILD_ESCALATION.md`.
    """

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
    escalation_path: str = "governance"
    """Which of the two routes this takes: `governance` leaves the Village, `operational`
    goes up its chain of command to the COO.

    A capacity shortfall is always governance. The COO runs the organisation whose
    capacity is in question, and an escalation that stayed inside it would be that
    organisation deciding whether it has enough people - which is the reason The Office
    sits above the Village. `broker.escalation.assert_path` refuses the other value."""


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

    human_held: bool = False
    """This step's position is pending activation, so a human does the work.

    The step stays in the workflow because the work happens. What changes is that no agent
    is appointed to it and the approval projection takes no demand from it - the time is
    non-review hours on a founder, not an approval queue.
    """


@dataclass(frozen=True, slots=True)
class Workflow(Artifact):
    venture_id: str
    steps: list[WorkflowStep]


# -------------------------------------------------------------------- 5.4 Task Ledger

@dataclass(frozen=True, slots=True)
class ApprovalProjection(Artifact):
    """What the humans will be asked to decide, per day, per role.

    This replaced `TaskLedger`. The ledger carried task ids, owners, SLAs, per-task
    volumes and assignment - all of it The Office deciding what an agent does and when,
    which is the Village Decomposer's job. Two systems producing tasks with no
    arbitration between them is one too many.

    The projection is what survived, because it is not about agent work at all: it is
    about human capacity, and it is the sole input to validator rule V13. Deleting it
    with the rest of the ledger would have deleted Gate 4.5's capacity check.
    """

    venture_id: str

    #: Approvals a day per role. **Float since declared volume replaced the constant 8.**
    #: A venture closing one deal a week runs `assign_contract` 0.2 times a day, and
    #: rounding that to zero or one is the difference between "no reviewer load" and "five
    #: times the real load". The figure is a rate, and rates are not integers.
    projected_daily_approvals: dict[str, float]


# --------------------------------------------------------------------- 5.5 Curriculum

@dataclass(frozen=True, slots=True)
class CurriculumScenario:
    """One scenario, in the shape `docs/scenario-contract.md` agrees on.

    The fields below `instruction_content_hash` are the contract's, added by P-00 and
    frozen with it. **Every one is defaulted**, so nothing that constructs a
    CurriculumScenario today has to change to keep working - the empty default is the
    honest value for a generator that does not yet produce classed scenarios, and
    P-05 is what fills them.

    Empty is not a claim. `not_applicable_reason=""` means no declaration is being
    made, NOT "not applicable, reason omitted" - that second state is refused, and the
    difference is the whole of ADR-0049.
    """

    scenario_id: str
    kind: str
    role: str
    domain: str
    module_id: str | None
    compliance_flags_exercised: list[str]
    summary: str
    instruction_content_hash: str | None

    # ---- the scenario contract, frozen 2026-09-08 --------------------------------
    scenario_class: str = ""
    """One of SimForge's nine, or empty. The Office does not coin new ones - an
    unknown class is a rejection by design, so that a class nobody considered cannot
    pass as one somebody did. Two of the nine (`never_do_violation`, `silent_failure`)
    are held out and The Office must never populate them."""

    instruction_section: str = ""
    """Which section of the operating instruction this scenario probes. Required and
    non-empty on submission; a present-but-empty string is a violation, not a pass."""

    expected_behavior: str = ""
    """What the agent does. Replaces `summary`'s generated boilerplate as the field
    SimForge reads - `summary` stays for the Pack-side domain scenarios, and on an
    operation scenario it carries the precipitating situation, which is the half of a
    scenario no manual contains and which has no field of its own on either side."""

    expected_escalation: str = ""
    """Prose naming the escalation the scenario expects.

    THE TRANSITIONAL WINDOW IS CLOSED. This field was `expected_escalation_prose` for
    one package's duration, alongside a bool of the same name; the suffix existed only
    to avoid the collision while both were live, and P-05 deleted the bool and took
    the name back. The Office field and the wire name agree again, which is what
    docs/scenario-contract.md section 6 promised.

    A reader arriving from `generators/pack.py` should note that Scenario there still
    carries `expected_escalation: bool`, and that it is a DIFFERENT CLASS. V23 reads
    that one. Two distinctions have worn this name for a while; only one of them
    changed.

    A value that restates "escalation is expected" has not satisfied this. The prose
    names the juncture: what the agent has in front of it, what it must stop short of
    doing, and to whom it hands the problem.
    """

    never_do_entry: str = ""
    """The never-do list entry a `never_do_violation` scenario tests.

    Required for that class alone, and that class is held out - so from The Office's
    side this is always empty, and its non-empty case is SimForge's own authoring.
    Present here so a SimForge-authored scenario round-trips through this dataclass.
    """

    not_applicable_reason: str = ""

    expected_answer: dict[str, Any] = field(default_factory=dict)
    """The machine-checkable half of the answer, from SimForge's split-key design:
    the act, the subject a record is about, the claim, the options it was chosen from,
    and any required caveat.

    Empty for every scenario written before the split, and emitted as ABSENT rather
    than as a blank mapping - a scenario claiming an empty answer would be claiming a
    gradeable half it does not have."""
    """Prose saying why a class this module cannot have is absent (ADR-0049).

    A declared absence, never an inferred one. A class neither supplied nor declared
    is still refused; a declaration without this sentence is also refused. Four of
    nine `compliance_couplings` rows were accidental empties, which is why the
    sentence is mandatory rather than encouraged."""

    def omit_from_serialisation(self) -> tuple[str, ...]:
        """`expected_escalation` does not appear at all on a DOMAIN scenario.

        **Contract amendment A3, ruled 8 September 2026.** Not an empty string - the
        key is dropped. A1.4 removed the bool from domain scenarios and A1.3 step 4
        then renamed the prose field into the vacated name, so the key survived
        holding `""`. Neither amendment described that, and an empty string sitting
        where real information used to sit reads as "not yet filled in" when the truth
        is "this concept does not apply to a domain scenario".

        That is a stated absence turned into a value, which this project has ruled
        against three times: a one-item sequence saying there is no ordering, an empty
        flag list meaning no framework applies, a NOT_RUN read as progress. **A reader
        cannot tell a vacated field from an unfilled one. An absent key can only be
        read one way.**

        The other five contract fields stay, empty, on a domain scenario. They were
        empty from birth, and a field never populated is at least consistently
        uninformative - see docs/scenario-contract.md section 8, whose recommendation
        about those five is still open and is deliberately not implemented here.
        """
        return ("expected_escalation",) if self.kind == "domain" else ()


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

    #: The tier this grant plans, or **None when the holder is not certified for this
    #: module** - ruled 21 September 2026, carried by 0049.
    #:
    #: The grant is still issued: it is the exam ticket `_exam_takers` reads. What it
    #: does not carry is an authority-shaped number nothing earned, in the column
    #: `resolve_grant` caps a live call against.
    trust_tier: str | None


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
    approval_projection: ApprovalProjection
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
