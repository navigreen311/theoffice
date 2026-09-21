"""Every scenario on an approved key is tagged, and the tag is not how it is promoted.

RULED 20 SEPTEMBER 2026 (entry 137)
===================================

    *"Every scenario is tagged reproducible or constructed at authoring. A functional
    battery draws only from reproducible. A constructed scenario is never promoted by
    editing the tag - it is re-derived against the sandbox or stays out."*

    reproducible  the probe can be put against a sandbox and the stated response
                  follows from the code path for any adequately seeded tenant.
    constructed   the stated response asserts a count or value only a particular
                  fixture produces, or the request cannot produce it at all.

WHAT THIS FILE CAN AND CANNOT HOLD
==================================

    It can hold the loader's rules and the classification as it stands. **It cannot
    stop somebody editing `constructed` to `reproducible`** - no test can, because the
    file is the only record of either claim. The ruling's second sentence is a rule for
    people, and the counts below are what makes breaking it visible: a promotion that
    was not a re-derivation moves this number and nothing else.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_a_draft_may_be_part_tagged`. The others demand the tag, and a loader that
    demanded it everywhere would refuse every Burkham draft - 94 scenarios nobody has
    classified - and take twenty answer keys out of the tree to enforce a rule about
    approval.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from generators import scenario_content as sc
from tests.approval import approved_header

GREENSTONE = (
    "assign_contract", "buyer_match", "comp_analysis", "property_lookup",
    "underwrite_deal",
)

#: The eleven, by name. Classified 20 September against CRE Forge at `3e48d5d`.
CONSTRUCTED = {
    # `total: 87` at a default limit of 50 cannot occur - buyer_matching.py:88 slices
    # before forge.py:223 counts. Corrected in the same change and still constructed:
    # the corrected form quotes three ranked buyers, which a sandbox must seed.
    ("buyer_match", "happy_path", 1),
    ("buyer_match", "happy_path", 0),
    ("buyer_match", "partial_failure", 0),
    ("comp_analysis", "happy_path", 0),
    ("comp_analysis", "escalation_required", 0),
    # `%query%` over address/city/county/zip only (property.py:298-308), and
    # `filters=None` from forge.py:125 - so no query reaches property_type.
    ("property_lookup", "happy_path", 0),
    ("property_lookup", "happy_path", 2),
    ("property_lookup", "escalation_required", 0),
    ("property_lookup", "partial_failure", 1),
    ("property_lookup", "partial_failure", 2),
    ("underwrite_deal", "happy_path", 0),
}

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


def _write(tmp_path: Path, head: str, body: str = _BODY) -> Path:
    path = tmp_path / "thing.yaml"
    path.write_text(textwrap.dedent(head).strip() + "\n" + body, encoding="utf-8")
    return path


_TAGGED = _BODY.replace(
    "  - scenario_class: happy_path\n",
    "  - scenario_class: happy_path\n    derivation: reproducible\n",
)

#: Entry 141: an approved key's hash must match its own body, so each header is DERIVED
#: from the body it will sit above. `_APPROVED` sits above the untagged `_BODY` and is
#: used only where the missing tag is the subject.
_APPROVED = approved_header(_BODY, approved_by="Ivan Green", approved_on="2026-09-18")
_APPROVED_TAGGED = approved_header(
    _TAGGED, approved_by="Ivan Green", approved_on="2026-09-18"
)


# ------------------------------------------------------------------- the loader's rules

def test_an_approved_key_with_an_untagged_scenario_is_refused(tmp_path):
    """The rule, and the message names WHICH scenario.

    "This key is not tagged" sends an author to read forty scenarios looking for which
    one - so the refusal lists them.
    """
    path = _write(tmp_path, _APPROVED)
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "derivation" in str(refused.value)
    assert "happy_path[0]" in str(refused.value)


def test_a_draft_may_be_part_tagged(tmp_path):
    """**The test that keeps this a rule about approval rather than about files.**

    Demanding the tag everywhere would refuse every Burkham draft - 94 scenarios nobody
    has classified - and pull twenty answer keys out of the tree. A draft is never
    submitted and so can never be drawn into a battery, which is the only thing the tag
    decides.
    """
    path = _write(tmp_path, "module_id: thing\nforge_id: cre-forge\nstatus: draft")
    content = sc.load_module(path)
    assert content.scenarios["happy_path"][0].derivation == ""


def test_a_third_word_is_refused(tmp_path):
    """Two values, because a third would be a third meaning nobody ruled on."""
    body = _BODY.replace(
        "  - scenario_class: happy_path\n",
        "  - scenario_class: happy_path\n    derivation: probably\n",
    )
    # A DRAFT, deliberately: the value check fires in `_scenario` and the approval rules
    # run before the scenarios are read, so a draft is what reaches this refusal. The
    # vocabulary is the subject here, not the status.
    path = _write(tmp_path, "module_id: thing\nforge_id: cre-forge\nstatus: draft", body)
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "'probably'" in str(refused.value)


def test_a_tagged_approved_key_loads(tmp_path):
    """The positive case, so none of the above is satisfied by refusing everything."""
    content = sc.load_module(_write(tmp_path, _APPROVED_TAGGED, _TAGGED))
    assert content.status == sc.APPROVED
    assert content.scenarios["happy_path"][0].derivation == sc.REPRODUCIBLE


# ------------------------------------------------------- the classification as it stands

def test_all_44_are_tagged():
    """Draft or approved. The two drafted in entry 137 keep their tags: they were
    classified before the correction and the correction did not change how they are
    derived."""
    loaded = sc.load_all()
    untagged = [
        f"{module_id}/{cls}[{i}]"
        for module_id in GREENSTONE
        for cls, occasions in loaded.modules[module_id].scenarios.items()
        for i, a in enumerate(occasions)
        if not a.derivation
    ]
    assert not untagged, f"untagged: {untagged}"


def test_the_eleven_constructed_are_exactly_these():
    """**Pinned by name, because this is the number that moves when somebody promotes
    a scenario by editing a word.**

    A re-derivation against the sandbox is a change to the scenario's situation and its
    expected answer. A promotion is a change to one word. Only the first should ever
    move this set while the prose stays still.
    """
    loaded = sc.load_all()
    found = {
        (module_id, cls, i)
        for module_id in GREENSTONE
        for cls, occasions in loaded.modules[module_id].scenarios.items()
        for i, a in enumerate(occasions)
        if a.derivation == sc.CONSTRUCTED
    }
    assert found == CONSTRUCTED, (
        f"added: {sorted(found - CONSTRUCTED)}  removed: {sorted(CONSTRUCTED - found)}"
    )


def test_thirty_three_are_reproducible():
    """The complement, counted rather than inferred."""
    loaded = sc.load_all()
    reproducible = [
        a for module_id in GREENSTONE
        for occasions in loaded.modules[module_id].scenarios.values()
        for a in occasions
        if a.derivation == sc.REPRODUCIBLE
    ]
    assert len(reproducible) == 33


def test_the_tag_is_not_sent_to_simforge():
    """Entry 135's ordering rule: SimForge declares a field before The Office sends it.

    `OperationScenarioSubmission` declares no `derivation`, and it carries
    `extra="forbid"` - so sending one would 422 every submission rather than being
    ignored. The tag lives here until the far side has somewhere to put it.

    ASSERTED ON THE ROWS, NOT ON THE SOURCE TEXT. This read
    `provisioning._curriculum_payload`'s literal until entry 142 lifted the row builder
    into `simforge.operation_scenario_rows`, at which point the grep stopped finding
    its substring - a guard that goes quiet when the code it guards moves. The rows are
    built from a real tagged key instead, so the check follows the function wherever it
    lives and would also catch a tag arriving through a field nobody spelled here.
    """
    from broker import simforge
    from generators import curriculum as curriculum_gen

    loaded = sc.load_all()
    for module_id in GREENSTONE:
        rows = simforge.operation_scenario_rows(
            curriculum_gen.module_scenarios(module_id, loaded.modules[module_id])
        )
        assert rows, f"{module_id} produced no submittable rows"
        for row in rows:
            assert "derivation" not in row, (
                f"`derivation` reaches {module_id}'s curriculum payload. SimForge does "
                "not declare it and forbids extras, so this would refuse every "
                "submission (entry 135)."
            )
