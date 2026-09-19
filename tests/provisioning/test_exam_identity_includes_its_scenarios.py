"""A changed answer key is a different exam, and the run reference says so.

WHAT THIS PREVENTS, AND IT ALREADY HAPPENED
===========================================

    Six verdicts were earned on scenarios the approved keys replaced. `mint_run_ref`
    was keyed on the INSTRUCTION content hash, and an answer key can be rewritten end
    to end without the instruction changing a byte - so a verdict from the old exam and
    one from the new were **byte-identical at every key either side could see**
    (entry 128). The ingest sweep had nothing to tell them apart with, which is why
    that had to be a ruling rather than a check.

    Worse than indistinguishable: `open_run` is idempotent on the ref, so re-submitting
    a rewritten curriculum landed on the run that was already open and SimForge replied
    `already_open`. The new answer key would never have got a run of its own.

THE CHEAP VERSION, RULED 18 SEPTEMBER 2026
==========================================

    The hash goes inside the ref STRING. `OperationRun.runRef` is UNIQUE and is the
    whole of a run's identity on SimForge, so a ref that differs is a different exam
    over there - with no field to declare, no payload to change and no migration on
    that side. Which matters, because `OperationRunStartRequest` now carries
    `extra="forbid"`: a field The Office invented would be REFUSED, not ignored, and
    every exam would fail to open.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_an_unchanged_answer_key_still_mints_the_same_ref`. Every other test asserts
    that something CHANGES the ref, and a ref that changed on every call would satisfy
    all of them while opening a second run with a fresh window on every retry - which
    is the one thing `mint_run_ref` was made deterministic to prevent.
"""

from __future__ import annotations

import uuid

import pytest

from broker.simforge import mint_run_ref, scenario_set_hash

AGENT = uuid.UUID("cc49a49c-c7aa-459d-9ecb-ecb46100216f")
INSTRUCTION = "cacf28ef5ba0113b34b2107e6777cd0ebbbf6b8fd0eaf0cf0bccc81431acf1fe"


def _payload(scenarios=None, not_applicable=None, **rest):
    """A curriculum payload with only the fields the hash is defined over."""
    return {
        "instruction_set_ref": {"module_id": "assign_contract",
                                "content_hash": INSTRUCTION},
        "operation_scenarios": scenarios if scenarios is not None else [
            {"scenario_class": "happy_path", "module_id": "assign_contract",
             "expected_behavior": "Report what came back and nothing further.",
             "expected_escalation": "", "instruction_section": "retry_vs_escalate"},
        ],
        "module_not_applicable": (
            not_applicable if not_applicable is not None
            else {"assign_contract": {"rate_limited": "This Forge cannot return 429."}}
        ),
        **rest,
    }


def _ref(payload, *, module_id="assign_contract", agent=AGENT, department=None):
    return mint_run_ref(
        venture_id="greenstone", forge_id="cre-forge", module_id=module_id,
        content_hash=INSTRUCTION, office_agent_id=agent, department=department,
        scenario_hash=scenario_set_hash(payload) if module_id else None,
    )


# ------------------------------------------------------------------- what moves it

def test_an_unchanged_answer_key_still_mints_the_same_ref():
    """**The test that keeps this deterministic rather than merely different.**

    Every other test here asserts the ref CHANGES. A ref that changed on every call
    would satisfy all of them and open a second run with a fresh window on every
    retry - extending the window of a hanging run, which is the one thing
    `mint_run_ref`'s determinism exists to prevent.
    """
    assert _ref(_payload()) == _ref(_payload())


def test_rewriting_a_scenario_mints_a_different_exam():
    """The case that produced six unusable verdicts."""
    rewritten = _payload(scenarios=[
        {"scenario_class": "happy_path", "module_id": "assign_contract",
         "expected_behavior": "Report what came back AND name the counterparty.",
         "expected_escalation": "", "instruction_section": "retry_vs_escalate"},
    ])
    assert _ref(_payload()) != _ref(rewritten)


def test_adding_a_scenario_mints_a_different_exam():
    more = _payload(scenarios=_payload()["operation_scenarios"] + [
        {"scenario_class": "permission_denied", "module_id": "assign_contract",
         "expected_behavior": "Decline and say which boundary refused.",
         "expected_escalation": "", "instruction_section": "authority"},
    ])
    assert _ref(_payload()) != _ref(more)


def test_a_changed_declared_absence_mints_a_different_exam():
    """**The one that is easy to miss**, and it changes no scenario at all.

    Moving `rate_limited` from "nobody has written one" to "this module cannot be rate
    limited" changes what SimForge grades coverage against while
    `operation_scenarios` stays byte-identical. Leaving it out of the hash would mint
    the same ref for a different exam, which is this whole defect in miniature.
    """
    reworded = _payload(not_applicable={
        "assign_contract": {"rate_limited": "The limiter is configured, never installed."}
    })
    assert _ref(_payload()) != _ref(reworded)


def test_reordering_the_scenarios_mints_a_different_exam():
    """SimForge stores an `ordinal` per row, so the arrangement is part of the exam."""
    pair = [
        {"scenario_class": "happy_path", "module_id": "assign_contract",
         "expected_behavior": "First.", "expected_escalation": "",
         "instruction_section": "retry_vs_escalate"},
        {"scenario_class": "happy_path", "module_id": "assign_contract",
         "expected_behavior": "Second.", "expected_escalation": "",
         "instruction_section": "retry_vs_escalate"},
    ]
    assert _ref(_payload(scenarios=pair)) != _ref(_payload(scenarios=pair[::-1]))


# --------------------------------------------------------------- what does NOT move it

def test_an_appointment_change_does_not_mint_a_new_exam():
    """The hash is over the answer key, not over the venture's shape.

    `certification_units_requested` and `coverage_declaration` describe who might be
    certified and how much of the Forge is covered. Folding them in would re-open every
    exam in a venture the moment somebody was appointed, and none of the scenarios
    would have changed.
    """
    with_extra = _payload(
        certification_units_requested=[{"agent_id": "someone", "module_id": "x"}],
        coverage_declaration={"modules_in_forge": 9, "modules_covered": 4},
    )
    assert _ref(_payload()) == _ref(with_extra)


def test_the_instruction_hash_still_has_its_own_segment():
    """Two facts, two segments. A changed instruction is still a different exam."""
    other = mint_run_ref(
        venture_id="greenstone", forge_id="cre-forge", module_id="assign_contract",
        content_hash="f" * 64, office_agent_id=AGENT,
        scenario_hash=scenario_set_hash(_payload()),
    )
    assert other != _ref(_payload())
    assert INSTRUCTION[:12] in _ref(_payload())


# ----------------------------------------------------------------------- unit B, and old refs

def test_a_department_ref_carries_no_answer_key():
    """**A unit-B run submits no curriculum**, so it has none to name.

    `_open_department_units` opens the run and sends no scenarios. A hash segment there
    would be either a constant, naming nothing, or the hash of an empty set, claiming
    an answer key exists and is empty. Both are worse than the absence.
    """
    dept = mint_run_ref(
        venture_id="greenstone", forge_id="cre-forge", module_id=None,
        department="banking", content_hash=INSTRUCTION,
    )
    assert dept == "office:greenstone:cre-forge:dept:banking:cacf28ef5ba0"
    assert "k" + INSTRUCTION[:12] not in dept


def test_a_ref_minted_without_a_key_keeps_its_old_shape():
    """Every ref already open must still resolve.

    The same rule the agent segment was added under: a run SimForge is holding is
    identified by the string it was opened with, and re-deriving it would orphan the
    run rather than update it.
    """
    old = mint_run_ref(
        venture_id="greenstone", forge_id="cre-forge", module_id="assign_contract",
        content_hash=INSTRUCTION, office_agent_id=AGENT,
    )
    assert old == "office:greenstone:cre-forge:assign_contract@cc49a49c:cacf28ef5ba0"


def test_the_new_segment_is_recognisable_without_counting_colons():
    """`k` prefix. A reader meeting a ref in a log can tell the two hashes apart, and
    a pre-ruling ref from a post-ruling one, without knowing the format."""
    ref = _ref(_payload())
    assert ref.rsplit(":", 1)[-1].startswith("k")
    assert ref.count(":") == 5


@pytest.mark.parametrize("missing", ["operation_scenarios", "module_not_applicable"])
def test_a_payload_missing_a_half_still_hashes(missing):
    """Never raises. A hash that can fail is an identity that cannot be minted, and the
    caller would have to decide what to do about it at the one moment it must not."""
    payload = _payload()
    payload.pop(missing)
    assert len(scenario_set_hash(payload)) == 64
