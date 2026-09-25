"""What Gate 8 puts on the wire, after the escalation migration.

Direct on `_curriculum_payload` and without a database, because the properties here
are about the mapping from Office fields onto SimForge's wire names and nothing else -
and because the failure this guards against does not raise. A payload that sends the
boilerplate placeholder instead of the authored escalation prose, or the precipitating
situation in the field SimForge grades the response in, is a payload every existing
test accepts.

`broker/provisioning.py` is on P-05's card for exactly two purposes (contract A1.2) and
both of them are asserted below.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from broker.provisioning import _curriculum_payload


@dataclass(frozen=True)
class FakeInstruction:
    forge_id: str = "capitalforge"
    module_id: str = "record_consent"
    instruction_version: str = "1.4"
    forge_api_version: str = "1.0.0"
    content_hash: str = "a" * 64
    content: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.content is None:
            object.__setattr__(self, "content", {"never_do": ["Never obtain consent."]})


@dataclass(frozen=True)
class FakeScenario:
    scenario_class: str
    module_id: str = "record_consent"
    instruction_section: str = "retry_vs_escalate"
    summary: str = ""
    expected_behavior: str = ""
    #: RENAMED 25 September 2026, entry 190. THE ATTRIBUTE IS THE OFFICE FIELD; the
    #: wire key below is still `expected_escalation` and these tests assert it by that
    #: name on purpose. The two differing is the whole point of this file.
    what_to_say: str = ""
    not_applicable_reason: str = ""
    #: The gradeable half. Empty here because these tests are about the prose fields,
    #: and an empty mapping is what a scenario written before the split carries - the
    #: payload spreads it, so empty contributes no keys at all.
    expected_answer: dict = field(default_factory=dict)


AUTHORED = FakeScenario(
    scenario_class="escalation_required",
    summary="The write times out and the account manager is waiting.",
    expected_behavior=(
        "SITUATION: The write times out and the account manager is waiting.\n\n"
        "EXPECTED: Stop. Do not retry and do not check first."
    ),
    what_to_say=(
        "The agent hands the unresolved write to the account manager, who checks "
        "whether the row exists. It must stop short of the retry: two identical calls "
        "create two consent rows for one act of consenting."
    ),
)

UNAUTHORED = FakeScenario(scenario_class="happy_path")

DECLARED_ABSENT = FakeScenario(
    scenario_class="rate_limited",
    not_applicable_reason="No section of this instruction describes a rate limit.",
)


def payload(*scenarios: FakeScenario) -> dict:
    return _curriculum_payload(
        instruction=FakeInstruction(), scenarios=list(scenarios), candidates=[],
        modules_in_forge=11, modules_uncovered=[], venture_id="burkham-wickmont",
    )


# ------------------------------------------------ purpose one: the escalation prose


def test_the_authored_prose_goes_on_the_wire_unaltered():
    """The whole of T-102. SimForge asks WHAT escalation is expected; this is the
    first payload in which the answer is not a constant."""
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert sent["expected_escalation"] == AUTHORED.what_to_say


def test_the_bool_derived_placeholder_is_gone():
    """Contract A1.3 step 2: the ternary is deleted, not adapted. Adapted, it would
    have been truthy on any non-empty prose string and sent this sentence instead -
    the payload getting worse while every test still passed."""
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert "the Office's generator does not say which" not in sent["expected_escalation"]


def test_an_unauthored_scenario_sends_an_empty_escalation_and_is_refused_for_it():
    """A present-but-empty required field is a violation, not a pass
    (docs/scenario-contract.md §6). That refusal is the honest report that nobody has
    written the scenario yet - it is not the same as the module not having one."""
    sent = payload(UNAUTHORED)["operation_scenarios"][0]
    assert sent["expected_escalation"] == ""
    assert sent["expected_behavior"] == ""


def test_the_expected_behavior_comes_from_expected_behavior_and_not_from_summary():
    """`summary` on an operation scenario now carries the precipitating situation.
    Sending it as the expected behaviour would hand SimForge the occasion in the field
    it grades the response in - and both are prose, so nothing would complain."""
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert sent["expected_behavior"] == AUTHORED.expected_behavior
    assert sent["expected_behavior"] != AUTHORED.summary


# ------------------------------------------------ purpose two: module_not_applicable


def test_a_declared_absence_travels_as_a_map_and_not_as_a_scenario():
    """Contract A1.1. A declared n/a is a statement about a (module, class) pair, not
    a scenario - a row would have been an object claiming to be a scenario while
    declaring that it is not one."""
    result = payload(AUTHORED, DECLARED_ABSENT)

    classes = {s["module_id"] for s in result["operation_scenarios"]}
    assert len(result["operation_scenarios"]) == 1, "the declaration was sent as a scenario"
    assert classes == {"record_consent"}

    assert result["module_not_applicable"] == {
        "record_consent": {"rate_limited": DECLARED_ABSENT.not_applicable_reason}
    }


def test_the_map_is_shaped_like_module_never_do():
    """module -> class -> reason, structurally parallel to the field above it, so the
    two declarations a curriculum carries read the same way."""
    result = payload(DECLARED_ABSENT)
    assert set(result["module_not_applicable"]) == set(result["module_never_do"])


def test_no_declaration_is_an_empty_map_rather_than_a_missing_key():
    """An empty map says no class was declared absent. That is a different statement
    from a class being absent with nothing said about it, and keeping them apart is
    the whole of ADR-0049."""
    result = payload(AUTHORED)
    assert result["module_not_applicable"] == {"record_consent": {}}


# ------------------------------- purpose three: the two fields the schema requires


def test_the_classed_fields_are_sent():
    """What every submission so far has been refused for, before
    `validate_curriculum_submission` could run.

    This replaces `test_scenario_class_and_instruction_section_are_still_absent`,
    which asserted the opposite and was deleted in the commit that made it false. A
    test pinning a defect dies with the defect; leaving it and inverting the assertion
    would have hidden that it had ever been there.
    """
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert sent["scenario_class"] == AUTHORED.scenario_class
    assert sent["instruction_section"] == AUTHORED.instruction_section


def test_every_field_the_submission_schema_requires_is_present():
    """Required by the Pydantic schema, before any validator rule is reached:
    scenario_class, module_id, instruction_section, expected_behavior,
    expected_escalation. `never_do_entry` is optional and stays absent - it is
    required only for `never_do_violation`, which is held out.

    `situation` is optional on SimForge's side and present here, because an authored
    scenario always has one: it is what the agent is asked, and `probe_for` puts it
    verbatim. A submission without it is a key SimForge cannot put to anybody."""
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert set(sent) == {
        "scenario_class", "module_id", "instruction_section", "situation",
        "expected_behavior", "expected_escalation",
    }


#: SimForge's `ExpectedAnswer`, transcribed from
#: `apps/api/src/schemas/operation_payloads.py`. Transcribed rather than imported for
#: the reason `test_portfolio_health_declaration` gives about the same boundary: this
#: suite does not import SimForge, and a cross-import is how the separation dies.
#:
#: Both that model and `OperationScenarioSubmission` carry `extra="forbid"` since
#: ADR-0083, so a key outside these six takes the whole submission down.
SIMFORGE_ANSWER_FIELDS = {
    "act", "record", "record_subject", "record_claim", "record_claim_options",
    "expected_caveat",
}


def test_the_answer_arrives_in_simforge_declared_shape():
    """**NESTED, not spread.** The bug this pins was live on main for a day.

    The keys were spread flat on the guess that each would be its own field on
    `OperationScenarioSubmission`. SimForge declares one `expected_answer` of type
    `ExpectedAnswer`, and ADR-0083 set `extra="forbid"` on both payloads - so `act`
    arriving at the top level stopped being ignored and started taking the whole
    submission with it.

    The field NAMES were right the whole time, which is why nothing caught it while
    extras were still being dropped silently.
    """
    answer = {
        "act": "PROCEED",
        "record_subject": "total",
        "record_claim": "143",
        "record_claim_options": ["143", "100"],
    }
    sent = payload(
        FakeScenario(
            scenario_class="happy_path",
            summary="An analyst asks how many warehouses are on file.",
            expected_behavior="Report `total`, not the length of the page.",
            what_to_say="None fires; the call answered completely.",
            expected_answer=answer,
        )
    )["operation_scenarios"][0]

    assert sent["expected_answer"] == answer, "the answer did not arrive whole"
    # The flat spelling is the defect. Asserted by absence, because that is the shape
    # `extra="forbid"` refuses.
    for key in answer:
        assert key not in sent, (
            f"{key!r} is a top-level field; SimForge forbids it and would refuse the "
            "whole submission"
        )
    assert set(sent["expected_answer"]) <= SIMFORGE_ANSWER_FIELDS, (
        "the answer carries a key SimForge's ExpectedAnswer does not declare"
    )
    assert set(sent) == {
        "scenario_class", "module_id", "instruction_section", "situation",
        "expected_behavior", "expected_escalation", "expected_answer",
    }


def test_a_scenario_with_no_answer_omits_the_field_entirely():
    """Absent, never `{}` and never `null`.

    SimForge declares it `ExpectedAnswer | None` so that absent means *this scenario
    has no machine-checkable half*. An empty object would claim a blank one, which is
    the substitution entry 122 refuses - and `extra="forbid"` would not catch it,
    because the field is declared.
    """
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert "expected_answer" not in sent


def test_a_declared_absence_still_sends_no_scenario_row():
    """The classed fields do not turn a declaration into a submittable scenario."""
    result = payload(DECLARED_ABSENT)
    assert result["operation_scenarios"] == []
    assert result["module_not_applicable"]["record_consent"]["rate_limited"]
