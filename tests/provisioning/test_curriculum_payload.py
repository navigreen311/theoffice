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

from dataclasses import dataclass

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
    summary: str = ""
    expected_behavior: str = ""
    expected_escalation: str = ""
    not_applicable_reason: str = ""


AUTHORED = FakeScenario(
    scenario_class="escalation_required",
    summary="The write times out and the account manager is waiting.",
    expected_behavior=(
        "SITUATION: The write times out and the account manager is waiting.\n\n"
        "EXPECTED: Stop. Do not retry and do not check first."
    ),
    expected_escalation=(
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
    assert sent["expected_escalation"] == AUTHORED.expected_escalation


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


# ------------------------------------------------ what is still not sent


def test_scenario_class_and_instruction_section_are_still_absent():
    """Not because the generator lacks them - it produces both now - but because
    adding them is a third purpose in a file this package holds for two. E-001 in
    PARALLEL_BUILD_ESCALATION.md. This test exists so that the day they appear, it is
    a decision somebody made rather than a line that drifted in."""
    sent = payload(AUTHORED)["operation_scenarios"][0]
    assert "scenario_class" not in sent
    assert "instruction_section" not in sent
