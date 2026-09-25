"""The SimForge contract, and the boundary The Office must never cross.

Part 10.1, resolved (J8): **SimForge owns the held-out partition outright.** Held-out
scenario content lives in SimForge storage. The Office holds none of it and exposes no
endpoint, field, log, query, backup or export that returns it.

The Office's obligation here is **negative**. There is no read path to build — only one
never to build. That is unusually hard to enforce, because you cannot demonstrate the
absence of a capability by exercising it.

So the enforcement is a manifest plus a test, not a promise:

  * every field SimForge may return to The Office is enumerated below, with a declared
    purpose;
  * `tests/golden/test_no_read_path.py` walks real responses and fails on any field the
    manifest does not name, on any field that could carry scenario content, and on any
    parameter combination that produces scenario bodies.

Master prompt Part 10.1: *"Because Green Companies operates both sides of this boundary,
self-attestation is the weakest possible enforcement for the one control whose entire
purpose is preventing one side from seeing the other's content."* Both sides being the
same company is exactly why a machine has to check this continuously.

**Adding a field here without adding it to the manifest fails the build.** That is the
mechanism, and it is deliberate that it is annoying.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from psycopg.rows import dict_row

from broker.audit import write_event
from broker.config import get_settings
from broker.credentials import Credential, build_resolver
from broker.errors import CredentialUnavailable

if TYPE_CHECKING:  # a broker module must not import the client at runtime
    from client.office_client import AgentContext, OfficeClient

MANIFEST_PATH = Path(__file__).with_name("simforge_response_manifest.json")

# Substrings that, appearing in a field name, indicate scenario content. Deliberately
# broad: a false positive costs one rename, a false negative costs the boundary.
FORBIDDEN_NAME_FRAGMENTS = (
    "scenario_body",
    "scenario_text",
    "scenario_content",
    "scenarios",
    "held_out",
    "heldout",
    "prompt",
    "expected_answer",
    "expected_output",
    "rubric_detail",
    "answer_key",
    "transcript",
    "case_text",
)

# Parameters a careless caller or a determined one would reach for. The check sweeps
# every combination and asserts none of them widens the response.
SMUGGLING_PARAMS: tuple[dict[str, Any], ...] = (
    {},
    {"include_scenarios": "true"},
    {"include_scenarios": "1"},
    {"expand": "scenarios"},
    {"expand": "*"},
    {"fields": "*"},
    {"verbose": "true"},
    {"debug": "true"},
    {"include": "held_out"},
    {"format": "full"},
    {"depth": "999"},
)


class SimForgeError(Exception):
    """SimForge could not be reached, or answered in a shape the contract forbids."""


class ResponseRefusedError(SimForgeError):
    """SimForge answered, and The Office refused the answer.

    **Its own type because it is neither of the two things the caller already handles.**
    `SimForgeError` means nothing was learned - the service was unreachable, and the
    response to that is to restart something. `CurriculumRejectedError` means SimForge
    read the submission and said no, and the response to that is to write scenarios.
    This is a third thing: the submission was ACCEPTED and the reply broke The Office's
    own contract on the way back.

    It happened on 17 September 2026 and read as an outage for an afternoon. Four
    Greenstone modules were accepted by SimForge and reported `unreachable`, because
    SimForge echoes `module_declared_absences` back and the declared reasons ran to
    1,470-1,800 characters - over `_looks_like_prose`'s threshold. Nothing was wrong with
    the Forge, nothing was wrong with the curriculum, and the evidence said the Forge
    could not be reached.

    The response to this one is a third thing too: shorten what The Office sends, or
    narrow the guard. Never widen it - the guard is the read-path control.
    """


class RouteMissingError(SimForgeError):
    """The URL this side built was not answered by anything. Entry 177.

    **Its own type because the caller has to tell it from an absence.** Every other
    `SimForgeError` means SimForge was asked and something went wrong. This one means
    the question was never put: a 404 from a route that is not there, which looks
    exactly like a 404 from a resource that does not exist and means the opposite.

    It happened. `read_battery_result` asked the `/office` adapter for a
    `battery_result` module that has never existed, read the 404 as "no battery
    record", and returned None - so `verdict_evidence` would have been NULL on every
    certification, for ever, with nothing anywhere saying the read had failed.

    The response to this one is to fix the URL, which is a different act from waiting
    for a service to come back and a different act again from accepting that a run has
    no battery behind it.
    """


class CurriculumRejectedError(SimForgeError):
    """SimForge validated the curriculum and refused it, naming what is missing.

    Its own type because it is **an answer, not a fault**. Unreachable means nothing was
    learned; rejected means SimForge read the submission and said which Batch-3 rules it
    fails. Collapsing the two loses the only useful half - a rejection names the work.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        count = len(violations)
        super().__init__(
            f"SimForge refused the curriculum: {count} violation(s). "
            + "; ".join(violations[:4])
            + (" ..." if count > 4 else "")
        )


@dataclass(frozen=True, slots=True)
class GateResult:
    """What The Office is allowed to learn from a certification run.

    A verdict, a score against a threshold, and provenance. Not *why* — the reasoning
    is scenario-adjacent, and a rich enough explanation of a failure reconstructs the
    scenario that produced it.
    """

    run_ref: str
    unit: str
    verdict: str
    rubric_kind: str
    rubric_version: str
    score: float | None
    threshold: float | None
    certified_tier: str | None
    scenario_count: int
    coverage_denominator: int
    #: `provider/model` that answered the battery, e.g. `ollama/llama3.1:8b`.
    #:
    #: Optional on the wire and NOT optional in the record: a verdict that arrives
    #: without one cannot be stored as a certification, because
    #: `certified_records_its_basis` refuses it. The field is `str | None` here so an
    #: older SimForge that does not send it produces a REFUSAL at the guard rather than
    #: a parse error at the boundary - the two need different responses, and the first
    #: names the missing fact while the second only says the shape was wrong.
    agent_model: str | None = None
    #: The same candidate in full: model name, the model FILE with its size and
    #: quantization, the generation settings the exam ran under, and a fingerprint over
    #: all of it (SimForge ADR-0060).
    #:
    #: **Read, recorded, and not interpreted here.** Whether the model that earned a
    #: certification is still the one an agent runs is SimForge's rule to enforce - it
    #: owns the exam and it is the side that can see both values. The Office's interest
    #: is that the fact travels with the verdict and is on the row, so a certification
    #: nobody can attribute to a specific model file cannot be produced quietly.
    #:
    #: Optional for the reason `agent_model` is: an older SimForge that does not send it
    #: must produce a refusal that names the missing fact, not a parse error about shape.
    model_identity: dict[str, Any] | None = None


def submission_unit(module_id: str | None) -> tuple[str, str]:
    """`(unit, rubric_kind)` for one curriculum submission. **The only place that decides.**

    A submission naming a module is a unit A - one agent, one Forge, one module, judged
    against the operation rubric. One naming no module is a unit B - a department in a
    Forge, judged against the domain rubric.

    Extracted from `timeout_gate_result`, which has answered this exact question since
    it was written and is now this function's second caller rather than a second rule.
    `run_start` needs the same answer at the *start* of a run that the timeout sweep
    needs at the end of one, and two spellings of one rule is how the sweep and the
    hand-over would eventually disagree about what a run is - silently, because both
    would look right beside their own call site.
    """
    return ("A", "operation") if module_id else ("B", "domain")


def scenario_set_hash(payload: dict[str, Any]) -> str:
    """The identity of the answer key one curriculum submission carries.

    RULED 18 SEPTEMBER 2026 (decisions entry 129)
    =============================================

        *"The exam's identity includes the scenarios it was set from."*

        Six verdicts were earned on scenarios the approved keys replaced, and nothing
        in the run reference distinguished them from the approved 44 (entry 128).
        `mint_run_ref` was keyed on the INSTRUCTION content hash, and an answer key can
        be rewritten end to end without the instruction changing a byte - so a verdict
        from the old exam and one from the new were byte-identical at every key either
        side could see. It had to be a ruling because there was nothing to check.

    TAKEN OVER WHAT GOES ON THE WIRE, NOT A RE-DERIVATION
    =====================================================

        The argument is `artifacts_hash`': hash the thing itself, so the hash cannot
        drift from what it names. `_curriculum_payload` has already built the rows by
        the time this is called, so this hashes those rows rather than re-walking the
        generator's output to produce a value that is *supposed* to describe them.

    WHAT IS IN IT, AND THE ONE THAT IS EASY TO MISS
    ===============================================

        `operation_scenarios`    the scenarios themselves, in the order sent. Order is
                                 part of the identity because SimForge stores an
                                 `ordinal` per row, so a reordering is a different
                                 arrangement of the same exam and should be a different
                                 run rather than a silent landing on the old one.
        `module_not_applicable`  **a declared absence is a statement about the exam.**
                                 Changing `rate_limited` from "no scenario yet" to
                                 "this module cannot be rate limited" changes what
                                 SimForge grades coverage against while leaving
                                 `operation_scenarios` untouched - and would otherwise
                                 mint the same ref, which is this entire defect in
                                 miniature.

        Not `coverage_declaration`, `certification_units_requested` or
        `instruction_set_ref`: the first two are facts about the venture's shape and
        the third is the instruction, which the ref already names in its own segment.
        Folding them in would make an unrelated appointment change open a new exam.
    """
    material = {
        "operation_scenarios": payload.get("operation_scenarios", []),
        "module_not_applicable": payload.get("module_not_applicable", {}),
    }
    return hashlib.sha256(
        json.dumps(
            material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def sections_shown_hash(payload: dict[str, Any]) -> str | None:
    """The identity of the instruction text a curriculum handover SHOWS the agent.

    RULED 23 SEPTEMBER 2026 (decisions entry 176)
    =============================================

        *"A run ref names what the exam showed. The instruction sections in the
        handover are part of the ref derivation, so a handover that shows the agent
        different text mints a different ref."*

    WHAT WENT WRONG, AND WHY NOTHING CAUGHT IT
    ==========================================

        Entry 175 made `_curriculum_payload` carry the prose of every section the keys
        cite. It is new text in the exam room and it changes what the agent can be
        expected to know - and it moved NO segment of the ref. Measured on run
        `4637b946` the morning after: six modules, six refs, six identical to the ones
        already graded.

        And the collision is SILENT. `open_run` is idempotent on `run_ref` and returns
        the existing row untouched; the battery sweep selects on `verdict IS NULL`, so
        a graded row is never re-scored. Gate 8 would report success, the sweep would
        ingest the verdicts already on those rows, and a re-exam that never ran would
        read as a re-exam that changed nothing.

    IT IS NOT REDUNDANT WITH THE TWO HASHES BESIDE IT, AND THE REASON IS EXACT
    ==========================================================================

        The sections map is a function of three things: which sections the keys cite,
        the instruction content those names are looked up in, and THE CODE THAT DOES
        THE LOOKING.

        The first is already in `scenario_set_hash` - `instruction_section` is a field
        on every `operation_scenarios` row. The second is already in `content_hash`.
        **The third is in neither, and the third is what changed yesterday.**

        `scenario_set_hash` says in writing why it excludes `instruction_set_ref`:
        "the third is the instruction, which the ref already names in its own segment."
        That was true while `instruction_set_ref` held a hash and two version strings.
        It stopped being true when prose moved into it, because a hash of the whole
        instruction cannot say which PART of it was put in front of the agent.

        This is entry 143's shape, one field over. A rubric bump changes how an answer
        is graded without changing the answer key; a renderer change changes what the
        agent was shown without changing the instruction. Both are changes to the exam
        that no hash of the exam's inputs can express.

    TAKEN OVER WHAT GOES ON THE WIRE
    ================================

        Read back out of the built payload, like `scenario_set_hash` and for the same
        argument: hash the thing itself so the hash cannot drift from what it names. A
        second call to `_sections_cited_by` would be a second spelling of the rule, and
        the two would agree until one of them was changed.

    NONE WHEN NOTHING IS SHOWN, AND THE SEGMENT IS THEN OMITTED
    ===========================================================

        Entry 122's rule, and it is what keeps every already-open ref resolving. A run
        minted before this - every run in the system today - showed no sections and
        gets no segment, so its ref keeps the shape it was opened under.

        The consequence that matters is the one this entry exists for: the FIRST
        handover that shows sections goes from no segment to a segment, which is a
        different ref, which is a new run. The collision closes on the transition, not
        on some later edit.

        A module whose keys cite nothing, or whose instruction has none of the sections
        they cite, also mints no segment - and should. Nothing is being shown, which is
        the state the old ref already describes.

    Carries no scenario content and no prose: a 12-character prefix of a digest,
    domain-separated so it cannot be mistaken for an instruction hash.
    """
    ref = payload.get("instruction_set_ref")
    sections = ref.get("sections") if isinstance(ref, dict) else None
    if not sections:
        return None
    return hashlib.sha256(
        b"office/sections/v1\n"
        + json.dumps(
            sections, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def operation_scenario_rows(scenarios: list[Any]) -> list[dict[str, Any]]:
    """The `operation_scenarios` rows one module's curriculum sends, in order.

    Lifted out of `provisioning._curriculum_payload` so that the answer key's identity
    can be computed from the key alone. `approved_scenario_set_hash` needs to produce
    the byte-identical rows Gate 8 would send, and a second spelling of this list would
    be two implementations that agree until the first field is added to one of them -
    at which point every submission would read as stale and the sweep would refuse
    verdicts for a reason that was not true.

    Every omission here is deliberate and documented at the call site in
    `_curriculum_payload`: `situation` and `expected_answer` are absent rather than
    blank, which is entry 122's rule.
    """
    return [
        {
            "scenario_class": s.scenario_class,
            "instruction_section": s.instruction_section,
            "module_id": s.module_id,
            **({"situation": s.summary} if s.summary else {}),
            "expected_behavior": s.expected_behavior,
            # THE WIRE NAME, WHICH IS NOT THIS SIDE'S FIELD NAME.
            # Entry 190 renamed the Office field to `what_to_say`; SimForge's
            # `OperationScenarioSubmission` still requires `expected_escalation`
            # and refuses a payload without it. scenario-contract.md section 6
            # names this file as where Office fields map onto wire names, and
            # section 3.1 is the precedent: the same asymmetry ran for one
            # package while `expected_escalation_prose` was the Office name.
            #
            # DELETE THIS COMMENT AND THE MAPPING TOGETHER when SimForge renames
            # its field. Until then this line is the whole of the disagreement,
            # and it is one line on purpose.
            "expected_escalation": s.what_to_say,
            **({"expected_answer": dict(s.expected_answer)} if s.expected_answer else {}),
        }
        for s in scenarios
        if not s.not_applicable_reason
    ]


def declared_absent(scenarios: list[Any]) -> dict[str, str]:
    """class -> the reason this module cannot have it. Lifted out for the same reason."""
    return {
        s.scenario_class: s.not_applicable_reason
        for s in scenarios
        if s.not_applicable_reason and s.scenario_class
    }


def approved_scenario_set_hash(module_id: str, *, root: Path | None = None) -> str | None:
    """The scenario-set hash the currently approved answer key would produce.

    RULED 21 SEPTEMBER 2026 (decisions entry 142)
    =============================================

        *"Ingest also refuses a verdict whose submission's scenario-set hash differs
        from the currently approved key's."*

        `curriculum_submission.scenario_set_hash` says which key an exam was set from.
        Until now nothing could say which key is approved NOW, so the two could not be
        compared and a verdict earned on withdrawn text was indistinguishable from one
        earned on the text in the tree.

    HOW IT IS DERIVED, AND WHY NOT FROM THE APPROVAL HEADER
    =======================================================

        Entry 141 put an `approved_content_hash` on the key itself, and it is the wrong
        hash for this question: it is taken over the key's own fields - including
        `expected_answer` sub-keys `derivation` deliberately excludes - not over what
        goes on the wire. Comparing it with a submission's `scenario_set_hash` would
        compare two different digests of two different shapes.

        So this walks the same road Gate 8 walks: load the key, build the curriculum
        rows, hash the rows. `_operation_scenarios` and `operation_scenario_rows` are
        the SAME functions Gate 8 calls, not copies.

    WHAT NONE MEANS, AND WHY IT IS NOT A MISMATCH
    =============================================

        `None` is returned when there is no key file for the module, or the key is a
        draft. Neither is a statement that the exam was set from the wrong text - a
        module whose key nobody has approved has no approved key to differ from - so
        the caller reports it and does not refuse on it. That distinction is why this
        returns `None` rather than a sentinel digest.

    `has_instruction=True` is passed because a module with no live instruction is never
    submitted: `_submit_one_module` returns before `_curriculum_payload` is reached. The
    instruction hash is passed empty because it is not in the material this hashes.
    """
    # Imported here rather than at module scope. `generators.curriculum` pulls in the
    # whole artifact pipeline, and `broker.simforge` is imported by the health probes.
    from generators import curriculum as curriculum_gen
    from generators import scenario_content

    base = root if root is not None else scenario_content.default_root()
    path = base / f"{module_id}.yaml"
    if not path.exists():
        return None
    content = scenario_content.load_module(path)
    if content.status != scenario_content.APPROVED:
        return None

    rows = curriculum_gen.module_scenarios(module_id, content, has_instruction=True)
    return scenario_set_hash({
        "operation_scenarios": operation_scenario_rows(rows),
        "module_not_applicable": {module_id: declared_absent(rows)},
    })


def mint_run_ref(
    *,
    venture_id: str,
    forge_id: str,
    module_id: str | None,
    content_hash: str,
    department: str | None = None,
    office_agent_id: uuid.UUID | None = None,
    scenario_hash: str | None = None,
    sections_hash: str | None = None,
    protocol_version: str | None = None,
    rubric_version: str | None = None,
) -> str:
    """The run reference The Office mints, and SimForge opens a run under.

    **The Office mints this, not SimForge.** `OperationRunStartRequest.run_ref` is an
    input field, and its own docstring says why the unit travels with it: "The Office
    reads one verdict per `run_ref`, and a run whose unit is only known once it finishes
    cannot be asked about while it is hanging." A ref the receiving side invents cannot
    be declared before the run exists, which is the whole point of the call.

    DETERMINISTIC, DELIBERATELY
    ===========================

        Derived from the submission's natural key - venture, forge, module, and the
        instruction content hash. That is the same key SimForge upserts the bound
        instruction set on, so the two systems agree on what "the same submission"
        means without either asserting it.

        The consequence is the reason: `open_run` is idempotent on `run_ref` and
        returns the existing row with its clock UNTOUCHED, so a re-run of Gate 8
        against an unchanged instruction lands on the run that is already open rather
        than starting a second window. Extending the window of a hanging run is the one
        thing that hides a timeout, and a fresh uuid per attempt would do it from the
        caller's side while SimForge's own guard read as satisfied.

        A changed `content_hash` is a different instruction set and mints a different
        ref. That is not a retry - it is a new submission, and it should be a new run.

    A UNIT-B REF NAMES THE DEPARTMENT IN THE SLOT A MODULE WOULD HOLD
    =================================================================

        A unit-B run has no module, so without `department` the third segment would be
        `-` on every department in a venture and two departments operating the same
        module set on one Forge would mint the SAME ref. `open_run` is idempotent on
        the ref, so the second `run_start` would land silently on the first
        department's run, both correlation rows would carry one ref, and P-03's sweep
        would write two certifications - for two different departments - out of one
        verdict.

        That is why this stayed one function rather than becoming a second minter: a
        unit-B ref differs from a unit-A ref in exactly one segment, and two functions
        agreeing on the other four is the same "two spellings of one rule" defect
        `submission_unit` was extracted to prevent.

        `department` is ignored when `module_id` is given. A run is one unit or the
        other and `submission_unit` is what decides; a ref carrying both would be a ref
        that cannot say which.

    A UNIT-A REF NAMES THE AGENT, FOR THE REASON A UNIT-B REF NAMES THE DEPARTMENT
    ==============================================================================

        Ruled 17 September 2026: every exam submission names the agent taking it. A
        module with two grant holders is two exams, because SimForge's battery scores
        `run.agentId` - one agent - so one run cannot be about both.

        Without the agent segment those two runs would mint the SAME ref. `open_run` is
        idempotent on the ref, so the second `run_start` would land silently on the
        first agent's run, both submissions would carry one ref, and one verdict would
        be read back as two agents' results. That is the department collision above,
        one unit over, and it is the same bug.

        Eight characters of the uuid, not the whole of it: enough to distinguish the
        agents of one venture from each other in a ref whose job is to be recognised in
        a log line, and the full id is on the `curriculum_submission` row.

        A ref minted without an agent is a ref for a run that names nobody. Those exist
        - every unit-A run opened before this ruling - and they keep their old shape
        rather than being re-derived, so a ref that is already open still resolves.

    A UNIT-A REF NAMES THE ANSWER KEY. A UNIT-B REF CANNOT, AND MUST NOT PRETEND TO
    ===============================================================================

        Ruled 18 September 2026 (entry 129): *"the exam's identity includes the
        scenarios it was set from ... Unit A only."*

        `scenario_hash` is `scenario_set_hash` over the curriculum that went with this
        run, so rewriting an answer key mints a different ref and `open_run` opens a
        new run instead of returning the old one with the old verdict on it. That is
        the whole of the fix, and it needs nothing from SimForge: `OperationRun.runRef`
        is UNIQUE and is the entire run identity, so a ref that differs IS a different
        exam over there, with no field to declare and no schema to migrate.

        **Unit B is excluded because a department run submits no curriculum.** Gate 8's
        `_open_department_units` opens the run and sends no scenarios at all - so there
        is no answer key, and a hash segment there would either be a constant (naming
        nothing) or the hash of an empty set (claiming an answer key exists and is
        empty). Both are worse than the absence.

        A ref minted without one keeps its old shape, so every ref already open still
        resolves - the same rule the agent segment was added under.

    A UNIT-A REF NAMES THE TEXT THE EXAM SHOWED
    ===========================================

        Ruled 23 September 2026 (entry 176): *"A run ref names what the exam showed.
        The instruction sections in the handover are part of the ref derivation, so a
        handover that shows the agent different text mints a different ref."*

        `sections_hash` is `sections_shown_hash` over the `instruction_set_ref.sections`
        that went on the wire - the prose entry 175 started sending. See that function
        for why it is not implied by the two hashes beside it: those cover the keys and
        the instruction, and neither can say which PART of the instruction was put in
        front of the agent.

        Measured the morning after 175 landed: showing all four sections for the first
        time minted six refs identical to six already graded, and the collision reads
        as success from both sides.

        Omitted when nothing is shown, so every ref already open keeps its shape - the
        rule the agent and answer-key segments were added under.

    THE EXAM NAMES THE VERSIONS IT IS SET UNDER
    ===========================================

        Ruled 21 September 2026 (entry 143): *"An exam's identity carries the protocol
        version and the rubric version it is set under, beside the instruction and
        scenario hashes."*

        Measured, and the mechanism is this function's own idempotence read from the
        other side. `assign_contract`'s answer key did not change between 18 and 20
        September, so both runs minted `...:cacf28ef5ba0:k5c5e41247e52` - the identical
        ref - and `open_run` returned the run already open, clock and rubric untouched.
        Gate 8 recorded `already_open: True` for that module and False for every other.
        SimForge stamps the rubric in force when a run OPENS (`body.rubric_version or
        OPERATION_RUBRIC_VERSION`), so the 20 September exam was graded under the 18th's
        rubric: `assign_contract` carries `0.2.0` where `buyer_match`, `comp_analysis`
        and `property_lookup` - each with a re-minted ref - carry `0.3.0`.

        **The verdict could not be re-examined, because nothing about it had changed
        that a ref could express.** A rubric bump is a change to how an answer is
        graded, exactly as an answer-key edit is a change to what is asked, and entry
        129 settled that shape already.

        `p` and `r`, prefixed for the same reason `k` is: a reader of a log line tells
        the segments apart without counting colons.

        **Both are omitted when unknown, never defaulted.** Entry 122's rule. A
        constant here would claim an exam was set under a version nobody read, and
        every ref would agree while the runs behind them did not.

    Carries no scenario content: two ids, a module or department name and hash
    prefixes and two version strings. The hashes are truncated because the full 64
    characters buy nothing a reader wants and make the ref unreadable in a log line,
    where its only job is to be recognised. The full instruction hash is on the
    `curriculum_submission` row, as of 0046 so is the full scenario-set hash, and as of
    0048 so are both versions.
    """
    target = module_id or (f"dept:{department}" if department else "-")
    if module_id and office_agent_id is not None:
        target = f"{module_id}@{str(office_agent_id)[:8]}"
    segments = ["office", venture_id, forge_id, target, content_hash[:12]]
    if module_id and scenario_hash:
        # Prefixed, so a reader of a log line can tell this segment from the
        # instruction hash beside it without counting colons - and so a ref that has
        # one is distinguishable at a glance from the pre-ruling refs that do not.
        segments.append(f"k{scenario_hash[:12]}")
    # AND WHAT THE EXAM SHOWED. Entry 176. The sections the keys cite travel in the
    # handover as of entry 175, and nothing in `content_hash` or the `k` segment can
    # say which part of the instruction was put in front of the agent - the first is
    # the whole instruction and the second is the questions. A handover that shows
    # different text is a different exam and has to be a different run.
    #
    # UNIT A ONLY, for the reason the scenario hash is: a department run submits no
    # curriculum, so it shows no sections, and a segment there would be the hash of
    # nothing claiming something was shown.
    if module_id and sections_hash:
        segments.append(f"s{sections_hash[:12]}")
    # ON BOTH UNITS, unlike the scenario hash. A department run submits no curriculum
    # and so has no answer key, but it IS graded - `rubric_kind` is `domain` and a
    # rubric version is stamped on it exactly as on unit A. Excluding unit B here would
    # leave the collision this ruling closes open on half the exams.
    if protocol_version:
        segments.append(f"p{protocol_version}")
    if rubric_version:
        segments.append(f"r{rubric_version}")
    return ":".join(segments)


def department_basis_hash(module_hashes: dict[str, str]) -> str:
    """The basis a unit-B run executes against. **A composite, and it says so.**

    `OperationRunStartRequest.instruction_content_hash` is required and
    `curriculum_submission.instruction_content_hash` is NOT NULL, so a unit-B run has
    to name what it was judged against. A department is not a module and has no single
    operating instruction, so there is nothing to look up - the basis is the set of
    instructions the department's modules were actually handed over under, and the only
    honest way to name a set in one column is to hash it.

    WHY THIS IS NOT A `forge_operating_instruction.content_hash`, AND MUST NOT BE READ AS ONE
    =========================================================================================

        A reader who takes this value into
        `certification.forge_api_version_in_force` gets a refusal - "no
        forge_operating_instruction carries content hash ..." - which is correct and is
        the point. It is domain-separated by the `office/unit-b/v1` prefix so it cannot
        collide with a real instruction hash by accident, and
        `certification.recompute_staleness` already exempts unit B from the live-hash
        comparison for this exact reason, in writing: a unit-B cert "carries
        `module_id IS NULL` by design, so there is no single instruction it could be
        compared against."

        The property that makes it useful is the one a single hash has: it changes when
        any of the department's instructions changes, and it does not change when they
        do not. So a re-run of Gate 8 against unchanged instructions mints the same ref
        and lands on the run that is already open, exactly as the unit-A path does.

    An empty mapping raises rather than hashing nothing. A department with no handed
    over module on a Forge has no context to clear, and a hash of the empty set would
    be a stable value that looks like a basis and stands for nothing.
    """
    if not module_hashes:
        raise ValueError(
            "a department basis needs at least one module instruction; a hash of no "
            "instructions is a value that looks like a basis and names nothing"
        )
    material = "\n".join(
        f"{module_id}:{content_hash}"
        for module_id, content_hash in sorted(module_hashes.items())
    )
    return hashlib.sha256(f"office/unit-b/v1\n{material}".encode()).hexdigest()


class SimForgeClient:
    """The only three calls The Office makes to SimForge.

    **They travel two different paths, and that asymmetry is the design.**

    `get_gate_result` is brokered. An agent reads a verdict about its own
    certification, so it goes through `OfficeClient.call` exactly like any other
    Forge module: a grant resolved fresh, a trust tier, a shift, an idempotency
    key, an audit entry before the call and a ledger row after. Nothing here
    modifies that path - this class supplies the module name and narrows the
    answer.

    `submit_curriculum` and `run_start` are not brokered. Both are signed with
    The Office's own tenant credential; the hand-over is audited as
    `curriculum_handed_over`, naming the human who provisioned, and the
    `run_start` that follows it is bookkeeping on that same act rather than a
    second one.

    WHY GATE 8 DOES NOT GET AN AGENT
    ================================

        The brokered path takes an `AgentContext` and writes a ledger row naming
        that agent. Gate 8 runs during provisioning: the actor is a human, and
        the agents that will hold grants for this venture do not exist yet.
        There is no agent behind a curriculum hand-over because no agent
        performs it.

        Minting one to satisfy the signature is `origin='human'` again. That
        column exists because an audit entry signed by a fixture is worthless -
        an actor named in a record as though it acted. An agent invented to fill
        an `agent_ctx` is the same object: a name in a ledger row for a call it
        did not make, indistinguishable afterwards from one it did.

        So the hand-over is recorded as what it is - an Office act, with the
        human on it - and the ledger keeps meaning "an agent did this".
    """

    def __init__(
        self,
        office: OfficeClient,
        *,
        forge_id: str = "simforge",
        http: httpx.AsyncClient | None = None,
        resolver: Any | None = None,
    ) -> None:
        self._office = office
        self._forge_id = forge_id
        settings = get_settings()
        self._http = http or httpx.AsyncClient()
        self._owns_http = http is None
        self._resolver = resolver or build_resolver(settings.credential_backend)
        self._timeout = settings.forge_timeout_seconds

    # ------------------------------------------------------------- brokered

    async def get_gate_result(
        self, run_ref: str, *, agent_ctx: AgentContext
    ) -> GateResult:
        """Read one verdict, as the agent it is about.

        The response is validated before any caller sees it. `parse_gate_result`
        runs `validate_response`, which refuses a field the manifest does not
        name and refuses prose anywhere in the body - so a SimForge that started
        returning scenario content raises here rather than reaching a caller who
        might store it.
        """
        result = await self._office.call(
            self._forge_id, "gate_result", {"run_ref": run_ref}, agent_ctx=agent_ctx
        )
        if result.status_code == 404:
            raise SimForgeError(f"SimForge has no record of run_ref {run_ref!r}")
        if result.status_code >= 400:
            # The body is not echoed. A Forge error body has not been through
            # validate_response, and an exception message is the one place a leak
            # would travel without being checked.
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned {result.status_code}"
            )
        if not isinstance(result.body, dict):
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned "
                f"{type(result.body).__name__}, not an object"
            )
        return parse_gate_result(result.body)

    # --------------------------------------------------------- not brokered

    async def submit_curriculum(
        self,
        conn: Any,
        *,
        scenario_pack_ref: str,
        payload: dict[str, Any],
        actor: uuid.UUID,
        venture_id: str,
    ) -> dict[str, Any]:
        """Hand a curriculum over. Returns the acceptance body, validated.

        **This used to return `run_ref` and raise when it did not get one, and that
        expectation was never true.** The ref was never SimForge's to return: its
        `OperationRunStartRequest` takes `run_ref` as an *input* field, so the caller
        mints it and `run_start` opens the run under it. Nothing on
        `POST /api/operation/curriculum` produces a ref, and P-01 measured ten of ten
        Burkham modules ACCEPTED while this method raised on every one of them.

        So the acceptance body is returned whole instead. What it carries is enumerated
        in the manifest; the one worth naming here is **`module_levels`**, the
        per-module certification level - `certified`,
        `certified_with_declared_absence`, `demonstrated` - which is exactly what the
        certification run needs and what this method was throwing away.

        Audited before the call and not after, for the reason `broker/audit.py`
        gives: a hand-over that reaches SimForge and then crashes this process
        must still have left a trace, or the run exists on one side only and
        nothing here knows to wait for it.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        await write_event(
            event_type="curriculum_handed_over",
            actor_type="human",
            actor_id=actor,
            venture_id=venture_id,
            subject={
                "forge_id": self._forge_id,
                "scenario_pack_ref": scenario_pack_ref,
                # Counts, never bodies. Same rule as `record_submission`: a record
                # of what was sent must not become a copy of it.
                "scenario_count": payload.get("scenario_count"),
                "coverage_denominator": payload.get("coverage_denominator"),
            },
        )

        url = f"{base_url.rstrip('/')}/submit_curriculum"
        try:
            response = await self._http.post(
                url,
                # The body is a `ForgeOperationCurriculum` and is sent verbatim.
                # SimForge's shape wins here: it has a validator behind it, and a
                # summary of a curriculum is not a curriculum - nothing can be
                # certified against a count. `scenario_pack_ref` is the Office's own
                # correlation id and stays on this side, in the audit entry.
                json=payload,
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL,
            # and this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code == 422:
            # The one error body worth reading. It is checked the same way a success
            # body is - refusing to look would throw away the violations, and reading
            # it unchecked is the hole the manifest exists to close.
            raise _rejection(response)
        if response.status_code >= 400:
            # Not echoed. An error body that is not a 422 has no declared shape, and
            # an exception message is the one place a leak would travel unvalidated.
            raise SimForgeError(
                f"submit_curriculum returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("submit_curriculum returned a non-JSON body") from exc

        if not isinstance(body, dict):
            raise SimForgeError(
                f"submit_curriculum returned {type(body).__name__}, not an object"
            )
        # Unchanged, and deliberately so: a field the manifest does not name still
        # fails here. The manifest became accurate about what arrives; the check did
        # not become lenient about what may.
        #
        # `sent=payload` is the echo exemption (entry 132). `submit_curriculum` returns
        # `module_declared_absences` and `never_do_obligations` - The Office's own
        # declared reasons and its own never-do lists - and a value byte-identical to
        # one in this payload carries nothing this side did not already have. The
        # field-set check above is untouched by it.
        validate_response("submit_curriculum", body, sent=payload)
        if not body.get("accepted"):
            raise SimForgeError(
                f"SimForge refused the curriculum: {body.get('rejected_reason')!r}"
            )
        # No `run_ref` check. There is nothing here to check for - see the docstring.
        # The ref is minted on this side and travels on `run_start`.
        return body

    async def run_start(
        self,
        conn: Any,
        *,
        run_ref: str,
        unit: str,
        forge_id: str,
        instruction_content_hash: str,
        rubric_kind: str = "operation",
        module_id: str | None = None,
        agent_id: str | None = None,
        village_agent_ref: str | None = None,
        department_id: str | None = None,
        scenario_count: int = 0,
        coverage_denominator: int = 0,
        window_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Open the `OperationRun` a verdict is later read by. **The caller mints the ref.**

        `broker/forge_modules.py` has declared this module and its reason since the
        adapter was bound - "opens the OperationRun a verdict is later read by,
        bookkeeping between the two systems, on the same footing as the hand-over that
        precedes it" - and nothing has ever called it. Without it SimForge holds no
        record of a run between the curriculum and the gate result, so a battery that
        hangs produces no row, no verdict and no error, and TIMEOUT is unreachable from
        either side.

        WHY THIS TRAVELS THE HAND-OVER'S PATH AND NOT THE BROKERED ONE
        ==============================================================

            Same reason, unchanged: Gate 8 runs during provisioning, the actor is a
            human, and the agents that will hold grants for this venture do not exist
            yet. `forge_modules.NOT_AGENT_FACING` records exactly that for this name.
            So it is signed with the Office's own tenant credential and posted to
            `{base_url}/run_start` - SimForge's Office adapter, the same surface
            `submit_curriculum` already uses, dispatched from the same `MODULES` map
            behind the same tenant-credential check.

            **It is NOT `POST /api/operation/run/start`.** That route exists and is
            behind `require_role("compliance_analyst")` - a *user* role verified from a
            Clerk JWT. The Office holds no user identity in SimForge and has no business
            acquiring one for a machine hand-over. Reaching for that route and then
            reporting an authorization problem would have been a finding about a
            question nobody had to ask.

        WHY THE REF IS DETERMINISTIC AND NOT A FRESH UUID
        =================================================

            SimForge's `open_run` is idempotent on `run_ref` and answers
            `already_open: true` with **the clock untouched**, so that a retried
            hand-over cannot extend the window of a run that is already hanging
            (its ADR-0044). A caller minting a fresh uuid on every attempt defeats
            that control from the outside: two runs, two windows, and the second one
            young. `mint_run_ref` derives the ref from the submission's natural key
            instead - see its docstring.

        Not audited separately. The `curriculum_handed_over` entry written moments
        before names the same act, and the ref itself lands on
        `curriculum_submission.simforge_run_ref`, which is the durable record
        `overdue_submissions` actually reads. A second event for one hand-over would
        make the log say a thing happened twice.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        payload: dict[str, Any] = {
            "run_ref": run_ref,
            "unit": unit,
            "forge_id": forge_id,
            "instruction_content_hash": instruction_content_hash,
            "rubric_kind": rubric_kind,
            "module_id": module_id,
            "agent_id": agent_id,
            # THE SAME AGENT, NAMED TO THE OTHER SYSTEM. `agent_id` is The Office's
            # primary key and is meaningless in the Village; this is what the Village
            # calls the same person (`victor_serath`). SimForge resolves an identity out
            # of village.db and cannot do it from a uuid.
            #
            # Sent beside, never instead. Dropping the uuid would break the join on the
            # only side that owns the grant, and `_grant_holders` keys on it.
            "village_agent_ref": village_agent_ref,
            "department_id": department_id,
            "scenario_count": scenario_count,
            "coverage_denominator": coverage_denominator,
            "window_minutes": window_minutes,
        }

        url = f"{base_url.rstrip('/')}/run_start"
        try:
            response = await self._http.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL, and
            # this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            # Not echoed, for the reason submit_curriculum does not echo one: an error
            # body has not been through validate_response, and an exception message is
            # the one place a leak would travel unchecked.
            raise SimForgeError(
                f"run_start for {run_ref!r} returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("run_start returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise SimForgeError(
                f"run_start returned {type(body).__name__}, not an object"
            )
        # `sent=payload` for the same reason as `submit_curriculum`, though nothing
        # `run_start` returns is prose today: the rule belongs to the pair of calls
        # that echo, not to the one field that happened to trip first.
        validate_response("run_start", body, sent=payload)
        return body

    async def office_gate_result(self, conn: Any, *, run_ref: str) -> GateResult:
        """Read one verdict as an Office act, for the sweep that polls for it.

        **This is not a second copy of `get_gate_result` and it must not become one.**
        They answer two different questions and the difference is who is asking.

        WHY THE SWEEP CANNOT USE THE BROKERED READ
        ==========================================

            `get_gate_result` goes through `OfficeClient.call`, which resolves a grant
            for `(agent, simforge, gate_result)`, enforces a shift, checks a budget and
            writes a ledger row naming that agent. That is exactly right for the call it
            models - an agent reading the verdict about its own certification - and it
            is unreachable from a background sweep, which has no agent, no shift and no
            task.

            The obvious workaround is refused two hundred lines above, in this class's
            own docstring, and it is refused for this exact shape: "Minting one to
            satisfy the signature is `origin='human'` again ... a name in a ledger row
            for a call it did not make, indistinguishable afterwards from one it did."
            A sweep that invented an agent to read a verdict would put a fabricated
            actor on the record that GRANTS that agent production authority. The whole
            point of polling rather than receiving is that nobody gets to announce their
            own certification; forging the reader would give it back.

            **So the sweep does not pretend to be an agent. It is The Office, and it
            signs as The Office** - the same footing as `submit_curriculum` and
            `run_start`, which are Office acts for the same reason: no agent performs
            them.

        WHY THIS WORKS ON THE RECEIVING SIDE
        ====================================

            Read out of SimForge rather than assumed. Its Office adapter dispatches
            `gate_result` from the same `MODULES` map as `submit_curriculum` and
            `run_start`, `call_module` gates all three on `_require_tenant_credential`,
            and `x_office_agent_id` is an optional header there. There is one surface
            and one credential check; the brokered/unbrokered distinction is entirely
            The Office's own governance and does not exist on the wire.

        WHAT IS NOT WEAKENED
        ====================

            The leak protection is `parse_gate_result`, not the brokered path: it runs
            `validate_response`, which refuses a field the manifest does not name and
            refuses prose anywhere in the body. This read goes through the identical
            function, so a SimForge that started returning scenario content raises here
            exactly as it would there.

            A 404 stays a named refusal rather than an empty verdict, for the reason
            SimForge gives for returning one: a `NOT_RUN` body would have to invent a
            `unit` and a `rubric_version` for a run it never received. The sweep turns
            that refusal into a TIMEOUT only when its own deadline has passed, which is
            a statement about the deadline and not about the run.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        url = f"{base_url.rstrip('/')}/gate_result"
        try:
            response = await self._http.post(
                url,
                json={"run_ref": run_ref},
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL, and
            # this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code == 404:
            raise SimForgeError(f"SimForge has no record of run_ref {run_ref!r}")
        if response.status_code >= 400:
            # Not echoed. Same rule as the two calls above: an error body has not been
            # through validate_response, and an exception message is the one place a
            # leak would travel unchecked.
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("gate_result returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned "
                f"{type(body).__name__}, not an object"
            )
        return parse_gate_result(body)

    async def gate_9_5_verdict(self, conn: Any, venture_id: str) -> str | None:
        """Whether the held-out partition passed. **Whether, never why.**

        THE SHAPE IS SIMFORGE'S, AND THIS PAGE IS THE ONLY SOURCE FOR IT
        ===============================================================

            `docs/contracts/gate-9-5-verdict.md` in SimForge's tree, decided in their
            ADR-0108 and implemented in ADR-0111. Its own words: *"SimForge names this.
            The Office records it, in that order. Nothing on The Office's side may guess
            past this page."*

            That rule is written there because a guess about another system's response
            once read as that system's silence and cost two days (entry 144). So every
            behaviour below is quoted from the page, and where the page is silent this
            refuses rather than deciding.

        THE ANSWER, VERBATIM FROM THE CONTRACT
        ======================================

            Always 200. Always these four keys. Never any other.

                venture_id        echoed
                partition_exists  true | false
                verdict           PASS | FAIL | NOT_RUN | IN_PROGRESS | TIMEOUT | null
                decided_at        ISO-8601 UTC | null

            And the adapter the page specifies, in full:

                partition_exists == false  ->  None   (Gate 9.5: at ceiling)
                otherwise                  ->  verdict verbatim

            **`verdict` is not interpreted here.** `_gate_9_5` already holds the rule
            that only `PASS` advances, that `NOT_RUN` is not a pass and `TIMEOUT` is not
            a failure. A second place deciding what a verdict means is how two spellings
            of one rule start disagreeing.

            **`decided_at` is read and not returned.** `HeldOutSource.verdict` answers
            one question and the contract's adapter section names one value. Threading a
            timestamp nothing asks for through the port would be the first guess past the
            page.

        THE ONE INVARIANT THIS CHECKS, AND WHY IT IS NOT A GUESS
        ========================================================

            *"`verdict` is null if and only if `partition_exists` is false."* Written on
            the page, enforced in SimForge's own schema, and checked here because the two
            branches below read one field each: a body with `partition_exists: true` and
            a null verdict would return `None` from the second branch and be
            indistinguishable from an absent partition.

            Refused rather than resolved. Which of the two fields is wrong is not
            knowable from this side.

        WHETHER, NOT WHY - AND THE GUARD STILL RUNS
        ===========================================

            The page: *"The answer carries nothing about the partition. No counts,
            classes, modules, scenario ids, digests, reasons or scores."* The Office does
            not take that on trust. `validate_response` refuses any field not in the
            manifest, and `assert_no_scenario_content` runs on the body exactly as it
            does on every other answer from this Forge.

        SIMULATION IS NOT THIS CALL'S BUSINESS
        ======================================

            The page again: *"A venture in simulation gets the same answer. SimForge is
            blind to simulation. The Office's gate decides."* So nothing here reads
            `venture_simulation`, and a simulation rule at this layer would be a decision
            taken in the adapter for a gate that owns it.

        NOT AGENT FACING, so it travels the hand-over's path rather than the brokered
        one: signed with The Office's own tenant credential and posted to
        `{base_url}/gate_9_5_verdict`, the same adapter surface `submit_curriculum` and
        `run_start` use. Gate 9.5 runs during provisioning and the actor is a human; a
        grant over this would name an agent for an act no agent performs.

        **Raises rather than answering None when the call fails.** Entry 177's rule: a
        read that cannot find its source says so. `None` here is a statement that
        SimForge has no partition, and an unreachable Forge reported as an absent
        partition is a false fact about SimForge arriving in a gate's evidence.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        sent = {"venture_id": venture_id}
        url = f"{base_url.rstrip('/')}/gate_9_5_verdict"
        try:
            response = await self._http.post(
                url,
                json=sent,
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL, and
            # this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            # The page: "A 4xx is auth or a malformed body only. It never depends on the
            # venture." So a 4xx is a fault on this side and is reported as one; it is
            # never read as an answer about the partition. The body is not echoed, for
            # the reason the other two calls do not echo one: an error body has not been
            # through `validate_response`.
            raise SimForgeError(
                f"gate_9_5_verdict returned {response.status_code}; the contract says "
                "this status is auth or a malformed body and never depends on the "
                "venture, so it is not an answer about the partition"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("gate_9_5_verdict returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise SimForgeError(
                f"gate_9_5_verdict returned {type(body).__name__}, not an object"
            )

        # `sent` so the echoed `venture_id` is exempt from the prose check, the same
        # exemption `submit_curriculum` and `run_start` are given. The field-set check
        # above is unaffected by it - entry 132.
        validate_response("gate_9_5_verdict", body, sent=sent)

        exists = body.get("partition_exists")
        if not isinstance(exists, bool):
            raise SimForgeError(
                "gate_9_5_verdict: partition_exists is not a boolean, and the contract "
                "admits only true or false"
            )
        verdict = body.get("verdict")
        if verdict is not None and not isinstance(verdict, str):
            raise SimForgeError(
                f"gate_9_5_verdict: verdict is {type(verdict).__name__}, not a string "
                "or null"
            )
        if (verdict is None) != (not exists):
            raise SimForgeError(
                "gate_9_5_verdict: the contract says verdict is null if and only if "
                f"partition_exists is false; got partition_exists={exists} with "
                f"verdict={verdict!r}"
            )

        if not exists:
            return None
        return verdict


    async def read_battery_result(
        self, conn: Any, run_ref: str
    ) -> VerdictEvidence | None:
        """The evidence behind a verdict. Ruled 22 September 2026, entry 173.

        THE ROUTE IS SIMFORGE'S OWN, NOT THE BROKERED ADAPTER
        =====================================================

            Corrected 23 September 2026 (entry 177). This asked the `/office` adapter
            for a `battery_result` module, and **SimForge dispatches three modules -
            `gate_result`, `run_start`, `submit_curriculum` - and never had a fourth.**
            Every call 404'd, every 404 was read as "no battery record", and
            `verdict_evidence` would have been NULL on every certification for ever
            with nothing saying why.

            The evidence lives at `GET /api/operation/battery-result/{run_ref}`, a
            direct route at the host root. So the base URL is stripped to its ORIGIN
            and the path appended - the same thing `build` does for `/api/version`, and
            for the reason its docstring gives: the registry's `base_url` is an adapter
            mount, not the service.

            `run_ref` is percent-encoded. Today's refs carry `:` and `@`, which travel
            fine unencoded; a ref carrying `/` would silently address a different
            route, and the minter has added a segment twice this month.

        A 404 IS AN ANSWER ONLY WHEN SIMFORGE NAMES THE REF
        ===================================================

            Ruled 23 September 2026 (entry 177): *"A read that cannot find its source
            says so."*

            An unknown ref answers `{"detail": {"error": "unknown_run_ref", ...}}` -
            measured. A route that is not there answers `{"detail": "Not Found"}` -
            also measured, and that is what this call got for a day.

            So `unknown_run_ref` returns None, which is the honest absence: SimForge
            was asked and has no such run. **Any other 404 raises**, because this side
            cannot tell a missing route from a moved one and both mean the question was
            never put. A read that returns "nothing found" from a URL nobody answered
            is the defect this paragraph exists to stop.

        **None still means SimForge has nothing**, which it says two ways: this 404,
        and `observed: false` on a 200. Both are answers and neither is an error - a
        run can exist with no battery behind it.
        """
        credential = await self._tenant_credential(conn)
        base_url, _api_version = await self._registry(conn)

        parts = urlsplit(base_url)
        origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
        quoted = quote(run_ref, safe="")
        url = f"{origin}/api/operation/battery-result/{quoted}"
        try:
            response = await self._http.get(
                url,
                headers={"Authorization": f"Bearer {credential.reveal()}"},
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL, and
            # this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code == 404:
            if _names_the_unknown_ref(response):
                return None
            raise RouteMissingError(
                f"SimForge answered 404 for the battery-result route without naming "
                f"{run_ref!r}, so this is a route that is not there rather than a run "
                f"SimForge has no record of. Nothing was read and no evidence is "
                f"stored; do not read this as an absent battery record."
            )
        if response.status_code >= 400:
            raise SimForgeError(
                f"battery-result for {run_ref!r} returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("battery-result returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise SimForgeError(
                f"battery-result for {run_ref!r} returned "
                f"{type(body).__name__}, not an object"
            )
        return parse_battery_result(body)

    # ----------------------------------------------------------- internals

    async def _tenant_credential(self, conn: Any) -> Credential:
        """The tenant credential, or a `SimForgeError` naming why there is none.

        **The resolver raises `CredentialUnavailable`, not `SimForgeError`**, and that
        difference escaped this class until CI ran without `SIMFORGE_TOKEN`: Gate 8
        catches `SimForgeError` and records a failed hand-over, so an unresolvable
        credential went straight past it and 503'd the whole provisioning API. A Forge
        that cannot be reached must never stop a provisioning run - that is the entire
        reason the hand-over is non-fatal - and "cannot be reached" includes "we hold no
        credential for it".

        So it is translated here rather than caught at the call site. The ref travels in
        the message and the value never does, which is `CredentialUnavailable`'s own
        rule.
        """
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT credential_ref FROM forge_tenant_credential WHERE forge_id = %s",
                (self._forge_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise SimForgeError(
                f"no tenant credential is registered for {self._forge_id!r}; "
                "this Forge has not been onboarded"
            )
        try:
            return await self._resolver.resolve(row[0])
        except CredentialUnavailable as exc:
            raise SimForgeError(
                f"the tenant credential for {self._forge_id!r} did not resolve: {exc}"
            ) from exc

    async def _registry(self, conn: Any) -> tuple[str, str]:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT base_url, api_version FROM forge_registry WHERE forge_id = %s",
                (self._forge_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise SimForgeError(f"{self._forge_id!r} is not in forge_registry")
        return str(row[0]), str(row[1])

    async def post_gate_result(
        self,
        conn: Any,
        *,
        run_ref: str,
        instruction_set_ref: dict[str, Any],
        run_content_hash: str,
        department_outcomes: list[dict[str, Any]],
        actor: Any,
        venture_id: str,
    ) -> dict[str, Any]:
        """POST a unit-B gate result built from a named human's attestation.

        RULED 21 SEPTEMBER 2026 (entry 147). **The only call in this client that tells
        SimForge an outcome rather than asking for one**, and it exists because nothing
        else can produce a unit-B outcome: The Office submits no curriculum to a
        department run, so no battery runs and no verdict is ever earned.

        WHAT IS SENT, AND WHAT DELIBERATELY IS NOT
        ==========================================

            `DepartmentRunOutcome` carries `department_id`, `forge_id`, `passed`,
            `escalation_path_verified` and `compliance_coupling_verified`. **It has no
            field for the reason, the attester, or the fact that this is an
            attestation**, so none of those crosses the wire - sending them under a name
            SimForge has not declared would 422 the whole call (entry 135), and guessing
            a name is what entry 144 was about.

            They stay on this side: `department_attestation` holds the human and the two
            reasons, `certification.basis` says `attested`, and
            `curriculum_submission.attestation_id` is what lets the sweep put the two
            together when the verdict comes back looking like any other.

        `agent_outcomes` is sent EMPTY and is not omitted. Unit A verdicts are earned by
        a battery and read back; The Office has never produced one and must not appear to
        be offering one here.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        payload: dict[str, Any] = {
            "run_ref": run_ref,
            "instruction_set_ref": instruction_set_ref,
            "run_content_hash": run_content_hash,
            "agent_outcomes": [],
            "department_outcomes": department_outcomes,
        }
        url = f"{base_url.rstrip('/')}/gate_result"
        try:
            response = await self._http.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise SimForgeError(
                f"posting the gate result failed: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            raise SimForgeError(
                f"SimForge refused the gate result with {response.status_code}"
            )
        body = response.json() if response.content else {}
        if not isinstance(body, dict):
            body = {}
        # Through the same validator as every read. A POST's acknowledgement is a
        # response like any other, and the read-path control does not get an exemption
        # for being on the end of a write.
        validate_response("post_gate_result", body)

        await write_event(
            event_type="department_outcomes_posted",
            actor_type="human", actor_id=actor, venture_id=venture_id,
            subject={
                "run_ref": run_ref,
                "departments": [o["department_id"] for o in department_outcomes],
                "basis": "attested",
            },
        )
        return body

    async def build(self, conn: Any) -> dict[str, Any]:
        """Which build the Forge is running, or why that could not be established.

        RULED 18 SEPTEMBER 2026 (decisions entry 131)
        =============================================

            *"The Office asks whether the Forge it submits to is current, as it already
            asks of itself. A submitter that vouches for its own build and not its
            counterpart has checked one end of the wire."*

            Entry 127 made Gate 8 refuse to submit on a build The Office cannot vouch
            for. This is the other end. It is not hypothetical: SimForge served a build
            sixteen commits old for two days, and the six verdicts it produced were
            graded with `operation_scenarios` discarded on arrival - a curriculum
            accepted and kept none of, by a process every check reported as healthy.

        **NEVER RAISES, AND THAT IS THE POINT OF THE SHAPE.**

            Every failure is a recorded answer: `reachable` false with a `reason`. A
            probe that threw would turn "the Forge did not say" into "Gate 8 fell over",
            and the gate would stop for a question it asked out of caution.

        THE URL IS THE ORIGIN, NOT THE ADAPTER PATH
        ===========================================

            `forge_registry.base_url` is `http://127.0.0.1:8110/office` - the Office
            adapter's mount. `/api/version` is SimForge's own route at the host root,
            so the path is stripped rather than appended to. Getting that wrong would
            404 and be recorded as "no version route", which reads as a Forge that
            cannot answer rather than as a URL this side built wrong.

        UNAUTHENTICATED, WHICH IS SIMFORGE'S DECISION AND NOT THIS ONE
        ==============================================================

            Its route is public by stated design (its ADR-0084 names the divergence
            from The Office, which authenticates the same route). No credential is
            resolved here: sending the tenant token to a route that does not want it
            would put it in a log for nothing.
        """
        base_url, _api_version = await self._registry(conn)
        try:
            parts = urlsplit(base_url)
            origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
            response = await self._http.get(f"{origin}/api/version", timeout=5.0)
        except Exception as exc:
            return {"reachable": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}

        if response.status_code != 200:
            return {
                "reachable": False,
                "reason": (
                    f"{origin}/api/version answered {response.status_code}. A Forge "
                    "with no version route cannot say what it is running."
                ),
            }
        try:
            body = response.json()
        except Exception:
            return {"reachable": False, "reason": "the version route did not return JSON"}
        if not isinstance(body, dict):
            return {"reachable": False, "reason": "the version route did not return an object"}

        # TRANSCRIBED, NOT PASSED THROUGH. An unrecognised key is dropped rather than
        # stored: `launch_environment` carries a `configured` map of which credentials
        # are set, and a gate result is read by more people than a Forge's own health
        # page. The fields below are what the question needs.
        return {
            "reachable": True,
            "started_commit": body.get("started_commit"),
            "checkout_commit": body.get("checkout_commit"),
            # `None` when at least one side could not be read, and SimForge is explicit
            # that it is never `False` in that case: a process that cannot say what it
            # is running must not report itself up to date. Kept as three states.
            "differs": body.get("differs"),
            "app_version": body.get("app_version"),
            # WHERE THE OFFICE LEARNS THE TWO VERSIONS AN EXAM IS SET UNDER.
            # Ruled 21 September 2026, entry 143.
            #
            # This route, because it is already the one The Office asks "what are you
            # running" of, it is unauthenticated by SimForge's own decision (its
            # ADR-0084), and Gate 8 already calls it once before the first submission.
            # A second route would be a second thing that can be stale.
            #
            # **READ OUT OF THE `exam` BLOCK, WHICH IS THE SHAPE SIMFORGE DECLARED.**
            # Entry 143 read them as top-level keys, because neither was published at
            # all when it was written and the flat shape was this side's guess at where
            # they would land. SimForge published them nested:
            #
            #     "exam": {"response_protocol_version": "6.0.0",
            #              "operation_rubric_version": "0.4.0"}
            #
            # So the probe kept returning None against a Forge that was answering, and
            # Gate 8 kept warning that it published neither. That is the same defect
            # the nested `expected_answer` was (entry 123's lesson): the field NAMES
            # were right and only the nesting was wrong, and nothing failed loudly -
            # a guess about another system's shape reads as that system's silence.
            #
            # ONE SHAPE, NOT TWO. A fallback to the flat keys would keep this side's
            # guess alive beside the declaration, and the first divergence between them
            # would be invisible.
            **_exam_versions(body.get("exam")),
        }

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

def _exam_versions(block: Any) -> dict[str, Any]:
    """What `/api/version`'s `exam` block says, or None for each thing it does not say.

    Split out so the shape is in one place and testable without an HTTP call. `None` is
    returned for a block that is missing, not an object, or missing a key - all three
    are "SimForge did not say", which is what `mint_run_ref` omits a segment for and
    what Gate 8 warns about. None of them is an error: a Forge that does not publish a
    version is still reachable, and conflating the two would report an outage where
    there is a missing field.
    """
    # THE THIRD KEY IS THE ONE THAT ENDS A STOP-GAP. Entry 147: when a real department
    # hand-over test ships, attested unit-B certifications stop counting at Gate 9. The
    # Forge is the only party that knows whether it has one, so this is where The Office
    # asks - and `None` means it did not say, which is every deployment today.
    #
    # A BOOLEAN OR NOTHING. `bool(value)` on a string would make "no" true, and a
    # capability read from a truthy string is how a stop-gap ends by accident.
    handover = block.get("department_handover_test") if isinstance(block, dict) else None
    if not isinstance(block, dict):
        return {
            "response_protocol_version": None,
            "operation_rubric_version": None,
            "department_handover_test": None,
        }
    return {
        "response_protocol_version": block.get("response_protocol_version"),
        "operation_rubric_version": block.get("operation_rubric_version"),
        "department_handover_test": handover if isinstance(handover, bool) else None,
    }




def load_manifest() -> dict[str, dict[str, Any]]:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        data: dict[str, dict[str, Any]] = json.load(fh)
    return data


def manifested_fields(endpoint: str) -> set[str]:
    manifest = load_manifest()
    # Leading-underscore keys are documentation (_README, _deliberately_absent), not
    # endpoints. Treating one as callable would legalise the forbidden-field list.
    if endpoint.startswith("_") or endpoint not in manifest:
        raise SimForgeError(
            f"endpoint {endpoint!r} is not in the SimForge response manifest. "
            "Every endpoint must be enumerated before it may be called."
        )
    return set(manifest[endpoint]["fields"])


def sent_values(payload: Any) -> frozenset[str]:
    """Every whole string The Office sent in one call.

    The material for the echo exemption - see `assert_no_scenario_content`. Whole
    values only: a substring, a prefix or a normalised form is never collected, so
    nothing here can exempt a string The Office did not send in full.
    """
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            found.add(node)

    walk(payload)
    return frozenset(found)


def assert_no_scenario_content(
    endpoint: str, body: Any, *, path: str = "", echoed: frozenset[str] | None = None
) -> None:
    """Recursively assert a response carries no scenario content.

    Two independent checks, because either alone is defeatable:
      * field NAMES are matched against FORBIDDEN_NAME_FRAGMENTS — catches an
        honestly-named leak;
      * field VALUES are checked for prose shape — catches a leak hidden behind an
        innocuous name like `notes` or `meta`.

    Prose shape is a heuristic, and that is acknowledged: a long free-text string is
    not proof of a scenario. It is a tripwire, and a tripwire that occasionally fires
    on a legitimate field is doing its job.

    THE ECHO EXEMPTION - RULED 19 SEPTEMBER 2026 (decisions entry 132)
    ==================================================================

        *"A field SimForge echoes back is exempt from the prose check when its value
        is byte-identical to what The Office sent in the same call. Anything else in
        that field is refused as before. Equality is a stronger control than length,
        and an operating instruction is never shortened to satisfy a wire guard."*

        `submit_curriculum` echoes `module_declared_absences` and
        `never_do_obligations` - The Office's own `not_applicable` reasons and its own
        never-do lists. Both tripped this check on their first real use, five weeks
        apart, and neither was a leak:

            entry 123  module_declared_absences.property_lookup.rate_limited  1800
            entry 132  never_do_obligations.underwrite_deal[6]                 232

        Entry 123 was fixed by shortening the prose, which was right for that field:
        it carried an ARGUMENT for a declaration and the argument belongs in the
        ledger. **The same remedy was wrong the second time.** A never-do entry is
        operating instruction text that agents read, and cutting its second clause to
        fit a wire guard would degrade what an agent is told in order to satisfy a
        check about what comes back.

    WHY EQUALITY IS STRONGER THAN LENGTH, WHICH IS WHY THIS IS NARROWING
    ====================================================================

        A value The Office sent moments earlier carries nothing The Office did not
        already have. Length says nothing about that either way: today a
        199-character reason passes whether or not SimForge echoed it faithfully, and
        **nothing checks the echo at all.** This does.

        So the exemption tightens the boundary rather than loosening it. What it costs
        is that the check becomes payload-aware, and that is why `sent_values`
        collects WHOLE strings only - never a prefix, never a substring, never a
        normalised or trimmed form. A fuzzy comparison here would be a named channel.

        The forbidden-NAME check is untouched and runs first. A field whose name
        matches a forbidden fragment is refused whatever its value, echoed or not.
    """
    if isinstance(body, dict):
        for key, value in body.items():
            here = f"{path}.{key}" if path else key
            lowered = key.lower()
            for fragment in FORBIDDEN_NAME_FRAGMENTS:
                if fragment in lowered:
                    raise ResponseRefusedError(
                        f"{endpoint}: field {here!r} matches forbidden fragment "
                        f"{fragment!r}. The Office has no read path to scenario "
                        "content; this field must not exist."
                    )
            assert_no_scenario_content(endpoint, value, path=here, echoed=echoed)
    elif isinstance(body, list):
        for i, item in enumerate(body):
            assert_no_scenario_content(
                endpoint, item, path=f"{path}[{i}]", echoed=echoed
            )
    elif isinstance(body, str) and _looks_like_prose(body):
        # EXACT, AND ON THE WHOLE VALUE. `in` on a frozenset of strings is equality,
        # never containment - the one comparison this may use.
        if echoed is not None and body in echoed:
            return
        raise ResponseRefusedError(
            f"{endpoint}: field {path!r} carries {len(body)} characters of prose that "
            "The Office did not send in this call. Scenario content must never reach "
            "The Office; if this field is legitimate, narrow it rather than widening "
            "the check."
        )


def _looks_like_prose(value: str) -> bool:
    """A long, multi-sentence, multi-word string is scenario-shaped.

    Thresholds are deliberately generous: refs, hashes and version strings are long
    but have no sentence structure, and short human labels have structure but no
    length. A scenario has both.
    """
    if len(value) < 200:
        return False
    words = value.split()
    return len(words) >= 30 and value.count(" ") > 20


def validate_response(
    endpoint: str, body: dict[str, Any], *, sent: Any | None = None
) -> None:
    """The build-failing check: shape, then content.

    Field-set equality in the *unexpected* direction only. A response omitting an
    optional field is fine; a response carrying a field nobody enumerated is the
    case this exists to catch.

    `sent` is the request payload of the same call, when there was one. It is the
    material for the echo exemption and nothing else - **the field-set check above is
    not affected by it.** An undeclared field is refused whether or not its value was
    echoed, because the manifest is about which fields may exist and this is about
    what a declared field may carry. Entry 132.
    """
    allowed = manifested_fields(endpoint)
    actual = set(body)
    undeclared = actual - allowed
    if undeclared:
        raise SimForgeError(
            f"{endpoint}: response carries field(s) not in the SimForge response "
            f"manifest: {sorted(undeclared)}. Add them to "
            f"{MANIFEST_PATH.name} with a declared purpose, or remove them. "
            "This check exists so a new field cannot arrive unreviewed."
        )
    assert_no_scenario_content(
        endpoint, body, echoed=sent_values(sent) if sent is not None else None
    )


@dataclass(frozen=True, slots=True)
class VerdictEvidence:
    """What SimForge's battery observed, beside the verdict it issued.

    RULED 22 SEPTEMBER 2026 (decisions entry 173)
    =============================================

        *"A certification records the evidence behind its verdict, not the verdict
        alone. Enough to tell a wrong verdict from a right one without asking the
        examiner."*

    **The measurement that produced the ruling.** Three exams on 22 September scored
    1.0 on every attempt, reported no failure modes, withheld nothing, and were
    recorded FAILED. `GateResult` carries `score` and `verdict` and nothing else, so
    The Office held `0.8 / FAIL` and could not have seen the contradiction at all.

    NOT A SECOND VERDICT
    ====================

        Nothing here overrides `verdict`. SimForge owns the exam and owns the call;
        what changes is that The Office can now say *why it disagrees* instead of
        asking. `disagrees_with_verdict` is a report, and it refuses nothing.

    `attempts` and `per_scenario_class` are the two that carry the argument, and they
    are different arguments: an attempt is a whole sitting, a class is one kind of
    question across sittings.
    """

    run_ref: str
    state: str
    #: One entry per sitting: `seed`, `score`, `passed`, `failure_modes`, `probes_put`,
    #: `unreadable_answers`. Names and numbers - no scenario text.
    attempts: tuple[dict[str, Any], ...] = ()
    #: `dimension` x `channel` -> `verdict` and `score`, as SimForge graded them.
    rubric_results: tuple[dict[str, Any], ...] = ()
    #: scenario class -> PASS | FAIL. **Includes the two held-out classes**, which is
    #: how The Office learned they are examined in the ordinary battery rather than
    #: only behind Gate 9.5. Class NAMES only; `ALL_SCENARIO_CLASSES` already holds
    #: every one of them, so nothing here is content The Office did not have.
    per_scenario_class: dict[str, str] = field(default_factory=dict)
    #: Why SimForge held something back. Empty is the common case and is not silence:
    #: it means nothing was withheld, which is itself evidence.
    withheld_because: tuple[str, ...] = ()
    failure_modes_observed: tuple[str, ...] = ()
    rubric_dimension_spread: float | None = None
    observed: bool = True
    #: What the exam showed, what the keys needed, and what was missing. Section
    #: NAMES only (SimForge ADR-0112). `missing` says whether a 0.0 on a
    #: key is the agent's fault or the submitter's omission. None when SimForge
    #: recorded nothing - not the same fact as `missing: []`.
    instruction_sections: dict[str, list[str]] | None = None

    #: The channel a verdict turns on. Ruled 22 September 2026, entry 174.
    #:
    #: **Read from the evidence, not from a rule SimForge published.** Measured over six
    #: exams on 22 September: every FAILED row carried at least one failing
    #: `restraint` dimension, and the one CERTIFIED row carried three failing
    #: `disposition` dimensions and no failing restraint one. `assign_contract` is the
    #: clean experiment - two agents, identical `per_scenario_class` with five FAILs
    #: each, and opposite verdicts.
    #:
    #: SimForge has not published the rule. This names what decided each verdict so a
    #: reader can see it; it does not assert what SimForge must do next time.
    DECIDING_CHANNEL: ClassVar[str] = "restraint"

    @property
    def failing_dimensions(self) -> tuple[dict[str, Any], ...]:
        """Every rubric dimension that did not pass, with its channel and score."""
        return tuple(
            d for d in self.rubric_results if d.get("verdict") != "PASS"
        )

    @property
    def deciding_dimensions(self) -> tuple[dict[str, Any], ...]:
        """The failing dimensions on the channel the verdict turned on. Entry 174.

        *"Which dimension failed, its score, and which channel it belongs to,
        distinguished from the ones that didn't decide."* These are the ones that did.
        """
        return tuple(
            d for d in self.failing_dimensions
            if d.get("channel") == self.DECIDING_CHANNEL
        )

    @property
    def non_deciding_failures(self) -> tuple[dict[str, Any], ...]:
        """Dimensions that failed and did not decide.

        Reported rather than dropped, and that is the point of the distinction: three
        disposition failures sat under a CERTIFIED verdict, and a reader who saw only
        "three dimensions failed" would have read that row as wrong.
        """
        return tuple(
            d for d in self.failing_dimensions
            if d.get("channel") != self.DECIDING_CHANNEL
        )

    @property
    def disagrees_with_verdict(self) -> bool:
        """Whether the evidence accounts for a FAIL at all.

        CORRECTED 22 SEPTEMBER 2026, BEFORE THIS EVER RAN
        =================================================

            The first cut asked only about attempts, failure modes and withholding, and
            would have called all three of that day's FAILs contradictions. **They were
            not.** Each turned on a restraint dimension at 0.0, in
            `operation_rubric_results` - the field the predicate did not read. Ivan
            Green caught it: *"the verdicts turn on restraint-channel dimensions I did
            not read. No contradiction."*

            The fix is not a wider predicate. It is reading the field that decides.

        True only when a FAIL has **nothing failing behind it anywhere**: no failing
        dimension, no failure mode, nothing withheld, and a perfect score on every
        attempt. That is a verdict its own record cannot account for, and it is the only
        shape The Office has standing to call wrong.
        """
        if self.state not in ("failed", "revoked"):
            return False
        if not self.attempts:
            return False
        if self.failing_dimensions:
            # The verdict is accounted for. Whether the examiner weighted it the way a
            # reader would is not The Office's call.
            return False
        every_attempt_perfect = all(
            a.get("score") == 1.0 and not a.get("failure_modes")
            for a in self.attempts
        )
        return (
            every_attempt_perfect
            and not self.withheld_because
            and not self.failure_modes_observed
        )

    def as_record(self) -> dict[str, Any]:
        """What is stored on the certification. Plain JSON, no dataclass."""
        return {
            "run_ref": self.run_ref,
            "state": self.state,
            "observed": self.observed,
            "attempts": list(self.attempts),
            "rubric_results": list(self.rubric_results),
            "per_scenario_class": dict(self.per_scenario_class),
            "withheld_because": list(self.withheld_because),
            "failure_modes_observed": list(self.failure_modes_observed),
            "rubric_dimension_spread": self.rubric_dimension_spread,
            "instruction_sections": self.instruction_sections,
            # ENTRY 174. Which dimensions decided, and which failed without deciding.
            # Derived at ingest and stored, so a report reads what was true when the
            # verdict landed rather than recomputing against a rule that has since moved.
            "deciding_channel": self.DECIDING_CHANNEL,
            "deciding_dimensions": list(self.deciding_dimensions),
            "non_deciding_failures": list(self.non_deciding_failures),
            "disagrees_with_verdict": self.disagrees_with_verdict,
        }


#: Fields dropped at the boundary before the body is validated. Entry 173.
#:
#: `prompt_version` is a version stamp and not a prompt - but `assert_no_scenario_content`
#: forbids the fragment `prompt` in a field name, and it is right to. **The guard is not
#: widened.** Exempting a fragment named `prompt` to admit a field The Office has no use
#: for would trade a real control for nothing.
#:
#: So the field is removed rather than permitted, and The Office ends up holding LESS
#: than the wire offered. What it costs is the ability to say which prompt template a
#: sitting used, which nothing here asks.
#:
#: Dropped BY NAME. A field called `prompt_text` still trips the guard, because only
#: these exact keys are removed and everything else is validated as it arrived.
_DROPPED_FROM_BATTERY: frozenset[str] = frozenset({"prompt_version"})


def _without_dropped_fields(body: dict[str, Any]) -> dict[str, Any]:
    """The body minus `_DROPPED_FROM_BATTERY`, structurally copied.

    The original is not mutated: it belongs to the caller, and a validator that edited
    its input would make the thing that was checked different from the thing that
    arrived.
    """
    trimmed = dict(body)
    certifications = []
    for cert in body.get("certifications") or []:
        if not isinstance(cert, dict):
            certifications.append(cert)
            continue
        copy = dict(cert)
        copy["exam_attempts"] = [
            {k: v for k, v in attempt.items() if k not in _DROPPED_FROM_BATTERY}
            if isinstance(attempt, dict) else attempt
            for attempt in (cert.get("exam_attempts") or [])
        ]
        certifications.append(copy)
    if certifications:
        trimmed["certifications"] = certifications
    return trimmed


def _names_the_unknown_ref(response: Any) -> bool:
    """Did SimForge's 404 name the ref, or is this a route that is not there?

    Measured 23 September 2026, both shapes, against the running build:

        unknown ref     {"detail": {"error": "unknown_run_ref", "detail": "..."}}
        missing route   {"detail": "Not Found"}

    **Only the first is an answer.** The second is FastAPI saying nothing is mounted
    there, and reading it as "no record" is how a wrong URL becomes a NULL column.

    Read as a marker and nothing else: the prose beside it is not parsed, and a body
    this cannot understand is treated as the route being absent - the direction that
    raises rather than the direction that invents an absence.
    """
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    detail = body.get("detail")
    return isinstance(detail, dict) and detail.get("error") == "unknown_run_ref"


def parse_battery_result(body: dict[str, Any]) -> VerdictEvidence | None:
    """Validate then narrow, the same order `parse_gate_result` uses.

    Returns None when SimForge has no battery record - `observed: false`, or no
    certification in the payload. **None is an answer and not an error**: a run can
    exist with nothing behind it, and storing an empty evidence record would be a
    claim that the battery was inspected and found silent.
    """
    body = _without_dropped_fields(body)
    validate_response("get_battery_result", body)
    if not body.get("observed"):
        return None
    certifications = body.get("certifications") or []
    if not certifications:
        return None

    # The first, and the reason that is right: this endpoint is keyed on
    # (forge_id, module_id, agent_id) bounded by the run - SimForge says so in `join` -
    # so a second entry would be a second certification for one agent on one module in
    # one run, which the unit-A natural key already refuses.
    cert = certifications[0]
    return VerdictEvidence(
        run_ref=str(body["run_ref"]),
        state=str(cert.get("state") or ""),
        attempts=tuple(cert.get("exam_attempts") or ()),
        rubric_results=tuple(cert.get("operation_rubric_results") or ()),
        per_scenario_class=dict(cert.get("per_scenario_class") or {}),
        withheld_because=tuple(cert.get("withheld_because") or ()),
        failure_modes_observed=tuple(cert.get("failure_modes_observed") or ()),
        rubric_dimension_spread=cert.get("rubric_dimension_spread"),
        instruction_sections=_instruction_sections(cert.get("instruction_sections")),
        observed=True,
    )


#: The shape SimForge named in ADR-0112, recorded here and nowhere guessed.
INSTRUCTION_SECTION_FIELDS: tuple[str, ...] = ("shown", "required_by_keys", "missing")


def _instruction_sections(value: Any) -> dict[str, list[str]] | None:
    """Narrow `instruction_sections` to the three lists SimForge publishes.

    Absent or null is None: SimForge recorded nothing, or predates ADR-0112.
    Anything else that is not exactly three lists of names is refused, not
    coerced. A guess about another system's response reads as its silence,
    and a coerced `missing: []` would read as "nothing was missing".
    """
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != set(INSTRUCTION_SECTION_FIELDS):
        raise SimForgeError(
            "get_battery_result: instruction_sections is not "
            f"{{{', '.join(INSTRUCTION_SECTION_FIELDS)}}} (SimForge ADR-0112): "
            f"got {sorted(value) if isinstance(value, dict) else type(value).__name__}"
        )
    out: dict[str, list[str]] = {}
    for name in INSTRUCTION_SECTION_FIELDS:
        items = value[name]
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            raise SimForgeError(
                f"get_battery_result: instruction_sections.{name} is not a list of "
                "section names (SimForge ADR-0112)"
            )
        out[name] = list(items)
    return out


def parse_gate_result(body: dict[str, Any]) -> GateResult:
    """Validate then narrow. The dataclass is the only thing callers see."""
    validate_response("get_gate_result", body)
    return GateResult(
        run_ref=body["run_ref"],
        unit=body["unit"],
        verdict=body["verdict"],
        rubric_kind=body["rubric_kind"],
        rubric_version=body["rubric_version"],
        score=body.get("score"),
        threshold=body.get("threshold"),
        certified_tier=body.get("certified_tier"),
        scenario_count=body["scenario_count"],
        coverage_denominator=body["coverage_denominator"],
        agent_model=body.get("agent_model"),
        model_identity=body.get("model_identity"),
    )


def _rejection(response: Any) -> SimForgeError:
    """Turn a 422 into a `CurriculumRejectedError` carrying its violations.

    The violations are generated by SimForge's `validate_curriculum_submission` from
    fixed format strings over module ids, scenario indices, class names and never-do
    entries - all of them things The Office authored and sent. None of it is held-out
    content. **That is an argument, not a guarantee**, so the strings go through
    `assert_no_scenario_content` before they are read, and a violation list that trips
    it becomes a plain refusal rather than a message.
    """
    try:
        detail = response.json().get("detail", {})
    except ValueError:
        return SimForgeError("submit_curriculum returned 422 with a non-JSON body")
    violations = detail.get("violations") if isinstance(detail, dict) else None
    if not isinstance(violations, list) or not violations:
        return SimForgeError("submit_curriculum returned 422 naming no violations")
    try:
        assert_no_scenario_content("submit_curriculum", violations)
    except SimForgeError:
        return SimForgeError(
            "submit_curriculum returned 422 whose violations did not pass the "
            "no-scenario-content check; they are not reproduced here"
        )
    return CurriculumRejectedError([str(v) for v in violations])

# ------------------------------------------------------- the timeout that never came

#: How long a submitted curriculum may sit without a result before it is treated as
#: TIMEOUT. Deliberately generous: an operation battery is slow, and resolving a
#: still-running run to `in_training` is harmless (it already is in training) while
#: resolving one too eagerly churns certifications.
DEFAULT_RUN_DEADLINE_HOURS = 24

#: The `rubric_version` a TIMEOUT carries. `certification.rubric_version` is NOT NULL,
#: and a run that never answered was judged against no rubric at all.
#:
#: **Not a version number.** Any plausible semver here - "0.0.0", the last rubric the
#: Forge used - would be a claim that a rubric was applied, sitting in the column a
#: reader consults to find out which one. This says what happened instead, and it sorts
#: nowhere near a real version, so a query that groups by rubric cannot silently fold
#: these rows in with runs that were actually scored.
TIMEOUT_RUBRIC_VERSION = "none: the run did not answer"


async def overdue_submissions(
    conn: Any,
    *,
    deadline_hours: int = DEFAULT_RUN_DEADLINE_HOURS,
) -> list[dict[str, Any]]:
    """Submissions that were handed over and never answered.

    THE GAP THIS CLOSES
    ===================

        `certification.VERDICT_TO_STATE` maps TIMEOUT to `in_training`, and Part 10.1
        requires that a timeout never resolve to PASS. That mapping is correct and it
        was also unreachable: **SimForge does not emit a TIMEOUT verdict.** Its outbound
        shape carries states, not verdicts, and none of them means "this run did not
        finish".

        So the real failure mode was never a TIMEOUT resolving to PASS. It was a hung
        run resolving to *nothing at all* — no callback, no verdict, no row, and a
        certification left in whatever state it held before. That is a different failure
        with the same consequence, and it is worse in one respect: a verdict that never
        arrives raises no error anywhere.

    WHY THE OFFICE HAS TO DETECT THIS AND NOT SIMFORGE
    ==================================================

        SimForge should report a run it knows exceeded its window, and that is being
        asked of it separately. But the case that matters most is the one where
        SimForge's worker died — and a process that has died cannot report that it has.
        A deadline held by the party that is *waiting* is the only version of this check
        that survives the failure it exists to catch.

        This is the same reasoning as the shift flush: a control that depends on the
        failing component to announce its own failure is not a control.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT submission_id, venture_id, forge_id, module_id, department,
                   scenario_pack_ref, simforge_run_ref, submitted_at,
                   instruction_content_hash, office_agent_id,
                   scenario_set_hash,
                   -- 0047's column, read here so a stale-key finding can name the run
                   -- the operator would have to abandon. Ruled 21 September 2026:
                   -- a stale-key refusal on a live run is NOT auto-superseded; the
                   -- finding tells the operator and abandoning is the authored act.
                   run_id,
                   -- 0050's column. The verdict SimForge returns for an attested
                   -- department unit is byte-identical to one a battery earned, so
                   -- this is the only thing that tells the sweep which it is holding.
                   attestation_id,
                   EXTRACT(EPOCH FROM (now() - submitted_at)) / 3600.0 AS hours_waiting
            FROM curriculum_submission
            WHERE result_received_at IS NULL
              -- SUPERSEDED IS NOT ANSWERED. 0046's column, and the reason it is not
              -- `result_received_at`: this row is still owed nothing and will never be
              -- certified, because its exam's identity did not name the answer key it
              -- was set from (entries 128 and 129). Excluded here rather than in the
              -- sweep, so every reader of "still owed an answer" gets the same set.
              AND superseded_at IS NULL
              AND submitted_at < now() - make_interval(hours => %s)
            ORDER BY submitted_at
            """,
            (deadline_hours,),
        )
        return [dict(r) for r in await cur.fetchall()]


def timeout_gate_result(submission: dict[str, Any], *, rubric_version: str) -> GateResult:
    """The verdict a silent run resolves to.

    Constructed here rather than by the caller so there is exactly one place that can
    decide what an unanswered run means, and it cannot be PASS: `verdict` is fixed at
    TIMEOUT, and `score` and `certified_tier` are None because nothing was measured.

    A `score` of 0.0 would have been the tempting default and is wrong — it says the
    agent scored zero, which is a claim about the agent rather than about the run.
    """
    # One rule, one place. This function used to spell the A/B and operation/domain
    # derivation inline; `run_start` needs the identical answer, and two copies of it
    # would be two things to keep in step.
    unit, rubric_kind = submission_unit(submission.get("module_id"))
    return GateResult(
        run_ref=submission.get("simforge_run_ref") or f"unanswered:{submission['submission_id']}",
        unit=unit,
        verdict="TIMEOUT",
        rubric_kind=rubric_kind,
        rubric_version=rubric_version,
        score=None,
        threshold=None,
        certified_tier=None,
        # No model, and deliberately not the one that WOULD have answered. A timeout is
        # the absence of an answer; naming a model here would record a candidate that
        # never sat the exam. `simforge_verdict` is TIMEOUT and the state is
        # `in_training`, so the CHECK does not demand one - which is the rule agreeing
        # with the fact rather than being worked around.
        agent_model=None,
        scenario_count=0,
        coverage_denominator=0,
    )


#: The verdicts SimForge has STORED on the run, and will not revise.
#:
#: Read off the receiving side rather than off the verdict vocabulary.
#: `run_registry.gate_result_for` returns `run.verdict` when the run carries one, and
#: otherwise DERIVES the answer from the window - TIMEOUT past it, IN_PROGRESS inside
#: it - "even before the sweep has stamped it: the answer must not depend on how
#: recently a background job ran."
#:
#: So TIMEOUT and IN_PROGRESS are computed answers about a run that is still open, and
#: NOT_RUN is an answer about a run SimForge does not hold. None of the three is final,
#: and a late result replaces all of them: SimForge records a verdict arriving after a
#: TIMEOUT and leaves `timedOutAt` in place, "because a result that ARRIVED is better
#: evidence than a deadline that passed."
#:
#: This is the set `result_received_at` is stamped on, and nothing else. **A stamp on a
#: TIMEOUT would close the submission against the verdict SimForge is still holding
#: open** - The Office would have thrown away better evidence and left a certification
#: at `in_training` forever on a battery that finished five minutes late.
TERMINAL_VERDICTS = frozenset({"PASS", "PROVISIONAL", "FAIL", "REVOKED"})


async def mark_result_received(conn: Any, submission_id: uuid.UUID) -> None:
    """Close one submission: a real verdict was recorded against it.

    `result_received_at` means "a verdict SimForge stands behind was written into a
    certification", NOT "we stopped asking". `overdue_submissions` is the only reader
    and it treats a NULL as "still owed an answer", which is the correct reading of a
    run that timed out and might yet finish.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE curriculum_submission SET result_received_at = now() "
            "WHERE submission_id = %s AND result_received_at IS NULL",
            (submission_id,),
        )
    await conn.commit()


async def supersede_run_submissions(
    conn: Any, *, run_id: uuid.UUID, reason: str
) -> int:
    """Retire every open submission this run wrote. Returns how many.

    RULED 21 SEPTEMBER 2026 (decisions entry 142)
    =============================================

        *"Abandoning a run supersedes its open submissions."*

        Run 50d933e8 was abandoned because its Gate 8 predated the corrected answer
        keys. Nothing linked its nine rows to it, so they stayed in the sweep's
        candidate set and the first pass ingested four PASS verdicts graded against
        text entries 137 and 140 had corrected. They were overwritten in the same pass
        by loop order, which is luck and not a control.

    NOT `result_received_at`, for 0046's reason restated: that field means a verdict
    was written into a certification, and here none will be. The row keeps its open
    shape and carries a reason saying why nobody will act on it.

    A submission already closed is left alone. Its verdict was ingested before the run
    was abandoned, and marking it superseded now would claim a decision was taken about
    a certification that already exists - which is a revocation, a different act with
    different authority.
    """
    if not reason.strip():
        raise ValueError("superseding a submission requires a stated reason")
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE curriculum_submission "
            "   SET superseded_at = now(), superseded_reason = %s "
            " WHERE run_id = %s "
            "   AND result_received_at IS NULL "
            "   AND superseded_at IS NULL",
            (reason, run_id),
        )
        superseded = cur.rowcount
    await conn.commit()
    return int(superseded)


async def record_submission(
    conn: Any,
    *,
    venture_id: str,
    forge_id: str,
    scenario_pack_ref: str,
    scenario_count: int,
    coverage_denominator: int,
    instruction_content_hash: str,
    submitted_by: uuid.UUID,
    module_id: str | None = None,
    department: str | None = None,
) -> uuid.UUID:
    """Record that curriculum was handed over.

    Stores refs and counts. Never scenario bodies - the submission record is on the
    Office side of the boundary, and a table holding what was sent is a table
    holding scenario content.
    """
    submission_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO curriculum_submission
              (submission_id, venture_id, forge_id, module_id, department,
               scenario_pack_ref, scenario_count, coverage_denominator,
               instruction_content_hash, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                submission_id, venture_id, forge_id, module_id, department,
                scenario_pack_ref, scenario_count, coverage_denominator,
                instruction_content_hash, submitted_by,
            ),
        )
    await conn.commit()
    return submission_id
