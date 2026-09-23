"""The handover carries the prose of every section its keys cite.

RULED 22 SEPTEMBER 2026 (decisions entry 175)
=============================================

    *"The Office sends the instruction sections its keys are written against. A
    curriculum handover carries the prose of every section a key cites, from the live
    instruction row. Measured: it has never sent them, so every exam graded an agent on
    four sections it was never shown."*

WHAT WAS MEASURED, ON BOTH SIDES
================================

    SimForge, from Ivan Green: every Greenstone exam recorded all four of
    `correct_sequence`, `failure_signatures`, `inputs` and `retry_vs_escalate` as
    MISSING.

    The Office, from `_curriculum_payload`: the only prose it has ever sent is
    `module_never_do`. `instruction_set_ref` carried a hash and a version; every
    `operation_scenario` row named the section it probes and carried none of its text.

    So the agent saw a never-do list and an answer grammar, and was graded on four
    sections nobody had sent it. Every failure mode we could see - naming a prohibition,
    act-line discipline, protocol conformance - is a mode about following instructions
    that were not in the room.

THE TWO THAT CARRY THE RULING
=============================

    `test_every_section_the_keys_cite_is_sent` - the ruling.

    `test_the_prose_comes_from_the_row_the_hash_names` - the half that keeps it honest:
    prose from anywhere else could disagree with the hash the certification binds to.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from broker import provisioning
from generators.artifacts import CurriculumScenario
from tests.conftest import requires_db

#: The four every Greenstone module's keys cite, measured 22 September 2026.
CITED = ("correct_sequence", "failure_signatures", "inputs", "retry_vs_escalate")


class _Instruction:
    """Enough of a live instruction row. The prose and the hash travel together."""

    def __init__(self, content: dict[str, Any], content_hash: str = "c" * 64) -> None:
        self.forge_id = "cre-forge"
        self.module_id = "property_lookup"
        self.instruction_version = "1.0.0"
        self.forge_api_version = "1.4.0"
        self.content_hash = content_hash
        self.content = content


def _live(**overrides: Any) -> _Instruction:
    content: dict[str, Any] = {
        "what_it_does": "Searches this tenant's property records.",
        "what_it_does_not_do": "It does not value anything.",
        "inputs": "`query` is required and is a string.",
        "correct_sequence": "Read `total` before reporting a count.",
        "failure_signatures": "A 200 with `total: 0` is an answer, not a failure.",
        "retry_vs_escalate": "RETRY FREELY. ESCALATE, DO NOT RETRY, on 422.",
        "never_do": ["Never report the page length as the number of matches."],
        "compliance_coupling": ["no_framework_applies"],
    }
    content.update(overrides)
    return _Instruction(content)


def _scenario(section: str, module_id: str = "property_lookup") -> CurriculumScenario:
    return CurriculumScenario(
        scenario_id=f"s-{section}", kind="operation", role="Acquisition Analyst",
        domain="sourcing", module_id=module_id, compliance_flags_exercised=[],
        summary="", instruction_content_hash=None,
        scenario_class="happy_path", instruction_section=section,
    )


# ======================================================== what is sent

def test_every_section_the_keys_cite_is_sent():
    """**THE RULING.** Four keys, four sections, in full.

    These are the exact four SimForge recorded as missing on every Greenstone exam.
    """
    instruction = _live()
    scenarios = [_scenario(name) for name in CITED]

    sections = provisioning._sections_cited_by(scenarios, instruction)

    assert sorted(sections) == sorted(CITED)
    for name in CITED:
        assert sections[name] == instruction.content[name], (
            f"{name} was altered on the way out"
        )


def test_a_section_no_key_cites_is_not_sent():
    """**Load-bearing.** Cited, not enumerated.

    Sending the whole instruction would be simpler and wrong in one specific way: it
    would put `never_do` in `sections` as well as in `module_never_do`, and SimForge
    renders both - the agent would read its prohibitions twice and `required_by_keys`
    would stop matching what was shown.
    """
    sections = provisioning._sections_cited_by([_scenario("inputs")], _live())
    assert sorted(sections) == ["inputs"]
    assert "never_do" not in sections
    assert "what_it_does" not in sections


def test_a_fifth_section_travels_without_anybody_widening_a_constant():
    """A key that starts probing a new section brings it along.

    The four are today's measurement, not a definition. A hardcoded list would need
    somebody to notice and edit it, and the noticing is the part that failed for as
    long as this payload existed.
    """
    instruction = _live(escalation_ladder="Escalate to the named human on file.")
    scenarios = [*(_scenario(n) for n in CITED), _scenario("escalation_ladder")]

    sections = provisioning._sections_cited_by(scenarios, instruction)
    assert "escalation_ladder" in sections
    assert sections["escalation_ladder"] == "Escalate to the named human on file."


def test_a_cited_section_the_instruction_lacks_is_omitted_not_blanked():
    """An empty string would be sent, shown, and recorded as PRESENT.

    `missing` would stop naming it, which is the one outcome worse than not sending it:
    the exam would report that the agent had been shown a section that was blank.
    """
    instruction = _live()
    scenarios = [_scenario("a_section_nobody_wrote")]

    sections = provisioning._sections_cited_by(scenarios, instruction)
    assert sections == {}


def test_a_blank_section_is_omitted_too():
    instruction = _live(inputs="   ")
    sections = provisioning._sections_cited_by([_scenario("inputs")], instruction)
    assert sections == {}


def test_a_structured_section_is_rendered_rather_than_dropped():
    """A key citing it is a key asking the agent to have read it."""
    instruction = _live(failure_signatures={"hard_failure": "422", "silent": "200"})
    sections = provisioning._sections_cited_by(
        [_scenario("failure_signatures")], instruction
    )
    assert "failure_signatures" in sections
    assert json.loads(sections["failure_signatures"])["hard_failure"] == "422"


# ======================================================== where it comes from

def test_the_prose_comes_from_the_row_the_hash_names():
    """**The half that keeps it honest.**

    `instruction.content` is the object `content_hash` was computed over. Prose read
    from a file or a second query could disagree with the hash the certification binds
    to, and nothing downstream would catch it - a certification would name text the
    agent never saw and no check would fire.
    """
    import inspect

    source = inspect.getsource(provisioning._sections_cited_by)
    assert "instruction.content" in source
    assert "load_module" not in source and "open(" not in source


def test_the_payload_carries_them_under_simforges_own_field_name():
    """`InstructionSetRef.sections`, `{name: prose}`.

    Read out of SimForge's schema rather than chosen: entry 144 cost a day to a guess
    about another system's shape reading as that system's silence, which is why
    `HANDOVER_TEST_KEY` is written down. The field is optional there and its absence is
    RECORDED rather than refused, so a build without it ignores this and sets the same
    exam it sets today.
    """
    import inspect

    source = inspect.getsource(provisioning._curriculum_payload)
    assert '"sections": sections' in source
    # Inside `instruction_set_ref`, not beside it: a top-level key would be dropped by
    # a schema that names its fields.
    ref_block = source[
        source.index('"instruction_set_ref"'):
        source.index('"certification_units_requested"')
    ]
    assert "sections" in ref_block


def test_nothing_is_sent_when_no_key_cites_anything():
    """A submission whose keys name no section sends no `sections` key at all.

    An empty map would be `shown: []` - which is what SimForge already records when the
    field is absent, and sending it explicitly claims The Office looked and found none.
    """
    instruction = _live()
    assert provisioning._sections_cited_by([], instruction) == {}

    import inspect

    source = inspect.getsource(provisioning._curriculum_payload)
    assert '**({"sections": sections} if sections else {})' in source


# ======================================================== against the real instruction

@requires_db
@pytest.mark.db
async def test_against_greenstones_live_instructions(world):
    """The real rows, and the real four.

    Not a fixture instruction: the claim is about what would actually be handed over
    for the five modules whose exams recorded all four sections as missing. `world`
    authors them, so this fails rather than skips if one loses a section.
    """
    from broker import instructions as instruction_store
    from broker.db import connection

    async with connection() as conn:
        for module_id in (
            "property_lookup", "comp_analysis", "buyer_match",
            "underwrite_deal", "assign_contract",
        ):
            live = await instruction_store.live(
                conn, forge_id="cre-forge", module_id=module_id
            )
            assert live is not None, f"no live instruction for {module_id}"
            scenarios = [_scenario(name, module_id) for name in CITED]
            sections = provisioning._sections_cited_by(scenarios, live)

            assert sorted(sections) == sorted(CITED), (
                f"{module_id} would still hand over an incomplete instruction set"
            )
            for name in CITED:
                assert sections[name].strip(), f"{module_id}/{name} is empty"
