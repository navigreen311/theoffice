"""A draft answer key is loaded, validated, reported - and never submitted.

Ruled by Ivan Green, 17 September 2026: *"Answer keys are drafted by Claude and
approved by Ivan Green. A draft is never submitted until approved."*

WHY `status` IS REQUIRED AND HAS NO DEFAULT
===========================================

    A missing status would have to mean one of the two, and both readings are wrong.
    Defaulting to `approved` submits unreviewed prose that SimForge then GRADES an agent
    against - the rubber stamp the ruling exists to prevent, arrived at by omission.
    Defaulting to `draft` silently stops a venture that is already certifying. The key
    is one line and the ambiguity is not worth having.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_an_approved_key_is_still_submitted`. Every other test asserts that something
    is withheld, and a loader that withheld everything would pass all of them while
    stopping every venture on the platform.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from generators import scenario_content as sc

_BODY = """
scenarios:
  - scenario_class: happy_path
    situation: A caller asks for a thing and the module returns it.
    expected_behavior: Report what came back and nothing further.
    expected_escalation: None fires; the call answered completely.
not_applicable:
  malformed_input: Nothing a caller sends to this module can be wrong.
  partial_failure: Every response is total; there is no partial shape.
  rate_limited: This Forge cannot return 429 on a module call.
  permission_denied: There is no permission boundary on this module.
  escalation_required: There is no juncture at which this module hands over.
  recovery_after_failure: The only recovery is the free retry.
"""


def _write(tmp_path: Path, name: str, head: str) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(
        textwrap.dedent(head).strip() + "\n" + _BODY, encoding="utf-8"
    )
    return path


# ------------------------------------------------------------------- the status key

def test_a_file_with_no_status_is_refused(tmp_path):
    """Not defaulted. Both defaults are wrong in opposite directions."""
    path = _write(tmp_path, "thing", "module_id: thing\nforge_id: cre-forge")
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "status" in str(refused.value)


def test_a_status_nobody_defined_is_refused(tmp_path):
    path = _write(
        tmp_path, "thing", "module_id: thing\nforge_id: cre-forge\nstatus: reviewed"
    )
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "'reviewed'" in str(refused.value)


def test_an_approval_with_no_name_on_it_is_refused(tmp_path):
    """An approval nobody is answerable for is the shape a rubber stamp has."""
    path = _write(
        tmp_path, "thing", "module_id: thing\nforge_id: cre-forge\nstatus: approved"
    )
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "approved_by" in str(refused.value)


def test_an_approval_with_no_date_on_it_is_refused(tmp_path):
    """**When** is half of an approval, and the half that goes stale.

    A key approved before its scenarios were rewritten is a different approval from one
    approved after, and `approved_by` alone cannot tell the two apart. Greenstone's five
    were approved on 17 September, superseded by SimForge's split keys, and approved
    again on the 18th. Without a date the second approval is indistinguishable from the
    first still sitting there.
    """
    path = _write(
        tmp_path, "thing",
        'module_id: thing\nforge_id: cre-forge\nstatus: approved\n'
        'approved_by: "Ivan Green"',
    )
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "approved_on" in str(refused.value)


def test_an_approval_dated_in_prose_is_refused(tmp_path):
    """One format, so no reader has to parse two. `18 September 2026` is refused."""
    path = _write(
        tmp_path, "thing",
        'module_id: thing\nforge_id: cre-forge\nstatus: approved\n'
        'approved_by: "Ivan Green"\napproved_on: "18 September 2026"',
    )
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "18 September 2026" in str(refused.value)


def test_a_draft_that_carries_a_date_is_refused(tmp_path):
    """The same rule as the name, on the other half of the signature."""
    path = _write(
        tmp_path, "thing",
        'module_id: thing\nforge_id: cre-forge\nstatus: draft\n'
        'approved_on: "2026-09-18"',
    )
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "draft" in str(refused.value)


def test_a_draft_that_names_an_approver_is_refused(tmp_path):
    """A name beside a draft is a signature on something nobody signed."""
    path = _write(
        tmp_path, "thing",
        'module_id: thing\nforge_id: cre-forge\nstatus: draft\napproved_by: "Ivan Green"',
    )
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "draft" in str(refused.value)


# --------------------------------------------------------------- what is submitted

def test_a_draft_is_loaded_and_validated_but_never_submitted(tmp_path):
    """Loaded, so a mistake in it is still found. Withheld, so it is never graded."""
    _write(tmp_path, "thing", "module_id: thing\nforge_id: cre-forge\nstatus: draft")
    loaded = sc.load_all(tmp_path)

    assert "thing" in loaded.modules, "a draft must still be loaded and validated"
    assert loaded.for_module("thing") is None, (
        "a draft reached the generator; it would be submitted to SimForge and graded"
    )
    assert list(loaded.drafts()) == ["thing"], (
        "the draft is invisible - 'nobody has written it' and 'it is waiting for "
        "Ivan' are different pieces of work"
    )


def test_an_approved_key_is_still_submitted(tmp_path):
    """**The test that keeps this a gate rather than an off switch.**

    Every other test here asserts something is withheld. A loader that withheld
    everything would satisfy all of them and stop every venture on the platform.
    """
    _write(
        tmp_path, "thing",
        'module_id: thing\nforge_id: cre-forge\nstatus: approved\n'
        'approved_by: "Ivan Green"\napproved_on: "2026-09-18"',
    )
    loaded = sc.load_all(tmp_path)

    content = loaded.for_module("thing")
    assert content is not None, "an approved answer key was withheld"
    assert content.approved_by == "Ivan Green"
    assert loaded.drafts() == {}


# --------------------------------------------------- the five drafted on 17 September

GREENSTONE = (
    "assign_contract", "buyer_match", "comp_analysis", "property_lookup",
    "underwrite_deal",
)


def test_greenstones_five_are_approved_and_carry_all_44_scenarios():
    """**Approved by Ivan Green on 18 September 2026**, after review of all 44.

    They were approved on the 17th, superseded by SimForge's split keys the same week,
    and drafts again until he had read the replacements. That round trip is the reason
    `status` exists: nothing about the first approval carried forward to prose nobody
    had seen, and nothing here is grandfathered.

    44 across 27 `(module, class)` pairs - the count SimForge grades, which is what the
    A2.1 amendment (entry 124) was ratified to keep equal.
    """
    loaded = sc.load_all()
    total = 0
    for module_id in GREENSTONE:
        content = loaded.for_module(module_id)
        assert content is not None, f"{module_id} is approved and still withheld"
        assert content.status == sc.APPROVED
        assert content.approved_by == "Ivan Green"
        assert content.approved_on == "2026-09-18"
        total += sum(len(v) for v in content.scenarios.values())

        accounted = set(content.scenarios) | set(content.not_applicable)
        assert accounted == set(sc.SUBMITTABLE_CLASSES), (
            f"{module_id} does not account for every submittable class: missing "
            f"{sorted(set(sc.SUBMITTABLE_CLASSES) - accounted)}"
        )

    assert total == 44, f"expected the 44 reviewed scenarios, found {total}"


def test_burkhams_twenty_are_untouched_by_greenstones_approval():
    """**An approval covers what was read, and nothing else.**

    Ivan approved Greenstone's 44. Burkham's 20 were not in front of him, so they stay
    drafts - which is the same rule that threw out the grandfathering on 17 September,
    applied to the opposite direction: an approval does not spread by adjacency any more
    than use becomes review.
    """
    loaded = sc.load_all()
    drafts = loaded.drafts()
    assert len(drafts) == 20, f"expected Burkham's 20 still drafted, found {len(drafts)}"
    assert not (set(drafts) & set(GREENSTONE))
    assert all(c.approved_by == "" and c.approved_on == "" for c in drafts.values())


def test_every_split_key_scenario_carries_its_gradeable_half():
    """44 of 44. The whole reason the keys were split.

    `expected_behavior` is prose a judge reads; `expected_answer` is what a machine can
    check without one. A split key missing it is a key that has been reformatted rather
    than split.
    """
    loaded = sc.load_all()
    missing = []
    for module_id in GREENSTONE:
        for cls, occasions in loaded.modules[module_id].scenarios.items():
            for i, a in enumerate(occasions):
                if not a.expected_answer.get("act"):
                    missing.append(f"{module_id}/{cls}[{i}]")
    assert not missing, f"scenarios with no gradeable half: {missing}"


def test_no_approved_key_still_asks_an_open_question():
    """An approved key states what to do. It does not ask.

    Each of the five carried OPEN markers while it was a draft - eleven of them, one per
    question the author refused to answer on Ivan's behalf. Approval is what turned each
    into a ruling. A surviving OPEN in an approved file would be a question SimForge
    grades an agent against, which is the failure this pair of states exists to prevent.
    """
    loaded = sc.load_all()
    for module_id in GREENSTONE:
        content = loaded.modules[module_id]
        prose = [a.wire_behavior() + " " + a.expected_escalation
                 for v in content.scenarios.values() for a in v]
        prose += list(content.not_applicable.values())
        asking = [p for p in prose if "OPEN" in p]
        assert not asking, (
            f"{module_id}: {len(asking)} approved scenario(s) still ask an open question"
        )


def test_no_declared_reason_would_be_refused_coming_back():
    """**A reason SimForge echoes must survive The Office reading it back.**

    `submit_curriculum` returns `module_declared_absences` - our own
    `not_applicable` reasons - and `assert_no_scenario_content` refuses any echoed
    string of 200+ characters that reads like prose. So a reason long enough to be
    thorough is a reason that makes the module unreachable, and on 17 September 2026
    four Greenstone modules were accepted by SimForge and refused by The Office on
    exactly that.

    The threshold is transcribed from `_looks_like_prose`, with its source named, for
    the same reason `test_portfolio_health_declaration` transcribes SimForge's
    classifier: this suite does not import the broker's wire layer, and a drift in
    either would fail there first.
    """
    loaded = sc.load_all()
    too_long = {}
    # APPROVED KEYS ONLY, and the scope is the rule rather than a convenience: a draft
    # is never submitted, so it is never echoed and cannot be refused coming back. The
    # twenty Burkham drafts carry long reasons today and 49 of them would trip this -
    # which is real debt, and it comes due at approval, not now. Widening this test to
    # cover them would block Ivan's review on prose length before he has read a word.
    for module_id in loaded.modules:
        content = loaded.for_module(module_id)
        if content is None:
            continue
        for cls, reason in content.not_applicable.items():
            # `broker/simforge.py::_looks_like_prose`
            if len(reason) >= 200 and len(reason.split()) >= 30 and reason.count(" ") > 20:
                too_long[f"{module_id}/{cls}"] = len(reason)
    assert not too_long, (
        "these declared reasons would be refused when SimForge echoes them back, "
        f"making the module unreachable for a reason nothing is wrong with: {too_long}. "
        "Put the argument in the ledger and the evidence in the Forge's issue tracker; "
        "the wire carries one sentence."
    )


def test_every_answer_key_in_the_repository_carries_a_status():
    """Total, not just the new five. A file with no status cannot load at all."""
    loaded = sc.load_all()
    assert loaded.root_exists
    assert loaded.modules, "no answer keys loaded; the root resolved somewhere empty"
    assert all(c.status in (sc.DRAFT, sc.APPROVED) for c in loaded.modules.values())
