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
        'approved_by: "Ivan Green"',
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


def test_greenstones_five_are_approved_and_account_for_every_submittable_class():
    """The repository's own content, asserted rather than described in a comment.

    These five were what SimForge refused on run cb3a47f6 with `missing
    expected_behavior, expected_escalation` - because no file existed. They were drafted
    on 17 September 2026 and approved the same day, once Ivan answered the eight open
    questions the drafts had recorded rather than guessed at.

    **The completeness check is the one that says the refusal is actually addressed.** A
    file that exists and leaves a class unaccounted for is refused exactly as a missing
    file is, so "a key exists" proves nothing on its own.
    """
    loaded = sc.load_all()
    for module_id in GREENSTONE:
        content = loaded.modules.get(module_id)
        assert content is not None, f"{module_id}: no answer key"
        assert content.status == sc.APPROVED, (
            f"{module_id} is marked {content.status!r}; Ivan Green approved these five "
            "on 17 September 2026."
        )
        assert content.approved_by == "Ivan Green"
        assert loaded.for_module(module_id) is not None, (
            f"{module_id} is approved and still withheld from the generator"
        )

        accounted = set(content.scenarios) | set(content.not_applicable)
        assert accounted == set(sc.SUBMITTABLE_CLASSES), (
            f"{module_id} does not account for every submittable class: missing "
            f"{sorted(set(sc.SUBMITTABLE_CLASSES) - accounted)}"
        )


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
                 for a in content.scenarios.values()]
        prose += list(content.not_applicable.values())
        asking = [p for p in prose if "OPEN" in p]
        assert not asking, (
            f"{module_id}: {len(asking)} approved scenario(s) still ask an open question"
        )


def test_every_answer_key_in_the_repository_carries_a_status():
    """Total, not just the new five. A file with no status cannot load at all."""
    loaded = sc.load_all()
    assert loaded.root_exists
    assert loaded.modules, "no answer keys loaded; the root resolved somewhere empty"
    assert all(c.status in (sc.DRAFT, sc.APPROVED) for c in loaded.modules.values())
