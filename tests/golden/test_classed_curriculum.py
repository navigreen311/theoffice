"""Classed operation scenarios: the shape, and the three ways a class is accounted for.

The golden snapshot asserts what the generator emits for **Greenstone**, whose seven
modules have no authored content and never will this run - so it exercises the
mechanical half and nothing else. These tests exercise the authored half, against the
one module that has content: `capitalforge/record_consent`, which is Burkham's.

Without them, "the content interface works" would rest on a snapshot of a venture the
interface does not touch. That is the shape of evidence this run keeps refusing.
"""

from __future__ import annotations

import pytest

from generators import scenario_content as sc
from generators.curriculum import _operation_scenarios
from tests.golden.test_scenario_content import WORKED_EXAMPLE

HASHES = {"record_consent": "c" * 64}


@pytest.fixture
def record_consent() -> sc.ModuleContent:
    return sc.load_module(WORKED_EXAMPLE)


# ------------------------------------------------------------------ the authored module


def test_every_submittable_class_gets_exactly_one_row(record_consent):
    """The key is (module, class), so seven classes is seven rows and no more."""
    rows = _operation_scenarios("record_consent", record_consent, True, HASHES)
    assert len(rows) == len(sc.SUBMITTABLE_CLASSES)
    assert len({r.scenario_class for r in rows}) == len(rows)
    assert {r.scenario_id for r in rows} == {
        f"op-record_consent-{c}" for c in sc.SUBMITTABLE_CLASSES
    }


def test_no_held_out_class_is_ever_emitted(record_consent):
    rows = _operation_scenarios("record_consent", record_consent, True, HASHES)
    assert not {r.scenario_class for r in rows} & sc.HELD_OUT_CLASSES


def test_an_authored_class_carries_the_occasion_the_act_and_the_escalation(record_consent):
    rows = {r.scenario_class: r for r in
            _operation_scenarios("record_consent", record_consent, True, HASHES)}
    authored = rows["escalation_required"]

    assert authored.summary, "the precipitating situation is missing"
    assert authored.summary == record_consent.scenarios["escalation_required"].situation
    assert authored.expected_behavior.startswith("SITUATION: ")
    assert "\n\nEXPECTED: " in authored.expected_behavior
    assert authored.expected_escalation
    assert not authored.not_applicable_reason
    assert authored.instruction_section == "retry_vs_escalate"


def test_a_declared_absence_carries_a_reason_and_nothing_else(record_consent):
    """Not a scenario pretending to be one: no behaviour, no escalation, no situation -
    a statement about a (module, class) pair, and the reason is the whole of it."""
    rows = {r.scenario_class: r for r in
            _operation_scenarios("record_consent", record_consent, True, HASHES)}
    declared = rows["rate_limited"]

    assert declared.not_applicable_reason
    assert declared.expected_behavior == ""
    assert declared.expected_escalation == ""
    assert declared.summary == ""


def test_the_key_carries_no_position_and_no_flags(record_consent):
    """Contract A2.1 and A2.2(a). A scenario belongs to the module; naming one of
    several operators would read as though it belonged to that one, and stamping a
    position's whole flag set on it would read as though the flags were exercised."""
    for row in _operation_scenarios("record_consent", record_consent, True, HASHES):
        assert row.role == ""
        assert row.compliance_flags_exercised == []
        assert row.kind == "operation"
        assert row.module_id == "record_consent"
        assert row.instruction_content_hash == HASHES["record_consent"]


def test_never_do_entry_is_empty_on_every_row(record_consent):
    """Required for `never_do_violation` alone, and that class is held out - so from
    The Office's side it is always empty, on every class, forever."""
    rows = _operation_scenarios("record_consent", record_consent, True, HASHES)
    assert all(r.never_do_entry == "" for r in rows)


# ------------------------------------------------------------------ the unauthored module


def test_a_module_with_an_instruction_and_no_content_gets_the_three_mechanical_classes():
    rows = _operation_scenarios("place_call", None, True, {})
    assert {r.scenario_class for r in rows} == set(sc.MECHANICAL_SECTIONS)
    assert {r.instruction_section for r in rows} == set(sc.MECHANICAL_SECTIONS.values())


def test_an_unauthored_scenario_is_empty_rather_than_boilerplate():
    """The old generator wrote "Operate X as Y: correct sequence, recognise the
    module's failure signatures..." - the section headings rearranged, and it was going
    to be graded. Empty is refused on submission; boilerplate passes."""
    for row in _operation_scenarios("place_call", None, True, {}):
        assert row.summary == ""
        assert row.expected_behavior == ""
        assert row.expected_escalation == ""
        assert row.not_applicable_reason == ""
        assert row.scenario_class, "a scenario with no class is not a classed probe"


def test_a_module_with_no_live_instruction_emits_nothing():
    """The mechanical map derives from instruction sections. With no instruction there
    are no sections, nothing to bind a certification to, and nothing to grade against -
    and `modules_with_authored_instructions` already names the module."""
    assert _operation_scenarios("no_such_module", None, False, {}) == []


def test_authored_content_survives_a_module_having_no_instruction(record_consent):
    """Authored scenarios exist because a person wrote them, not because a section
    does. They are emitted; the three mechanical ones are not."""
    rows = _operation_scenarios("record_consent", record_consent, False, {})
    assert {r.scenario_class for r in rows} == set(sc.SUBMITTABLE_CLASSES)
    assert all(r.instruction_content_hash is None for r in rows)


# ------------------------------------------------------- contract A3: an absent key


def _serialised(scenario) -> dict:
    """One scenario as it appears in the artifact - through the real serialiser, not
    through `dataclasses.asdict`, because the omission happens in the serialiser."""
    from generators.artifacts import ScenarioPack

    pack = ScenarioPack(
        venture_id="v", domain_scenarios=[scenario], operation_scenarios=[], coverage=[]
    )
    return pack.to_dict()["domain_scenarios"][0]


def _scenario(kind: str):
    from generators.artifacts import CurriculumScenario

    return CurriculumScenario(
        scenario_id="s1", kind=kind, role="Analyst", domain="d", module_id=None,
        compliance_flags_exercised=[], summary="A human asks for something.",
        instruction_content_hash=None,
    )


def test_a_domain_scenario_has_no_expected_escalation_key_at_all():
    """Contract A3. **The key is absent, not empty.**

    Asserted as absence and never as `== ""`, deliberately: an emptiness test passes
    the day a refactor puts an empty string back, and nothing notices. The property
    being protected is that a reader cannot mistake a vacated field for an unfilled
    one, and only an absent key has that property.
    """
    assert "expected_escalation" not in _serialised(_scenario("domain"))


def test_an_operation_scenario_still_has_the_key():
    """The field is inapplicable to a domain scenario, not deleted from the dataclass.
    On an operation scenario it is the canonical field the contract means, and empty
    there means "nobody has authored this yet" - which is a real state and must remain
    expressible."""
    from generators.artifacts import ScenarioPack

    pack = ScenarioPack(
        venture_id="v", domain_scenarios=[], coverage=[],
        operation_scenarios=[_scenario("operation")],
    )
    row = pack.to_dict()["operation_scenarios"][0]
    assert "expected_escalation" in row
    assert row["expected_escalation"] == ""


def test_the_other_contract_fields_are_still_present_and_empty_on_a_domain_scenario():
    """A3 drops one key and not six. The other five were empty from birth, which is at
    least consistently uninformative; section 8's recommendation about them is open and
    is not implemented here."""
    row = _serialised(_scenario("domain"))
    for field in ("scenario_class", "instruction_section", "expected_behavior",
                  "never_do_entry", "not_applicable_reason"):
        assert field in row and row[field] == "", field
