"""B16's closure: `capitalforge/portfolio_health` declares `escalation_required` absent.

**This file asserts a DECLARATION, not a mechanism.** ADR-0049's machinery is already
built on both sides and nothing here builds any of it again:

  simforge   `NotApplicableDeclaration`, `declarations_from_map`, the required prose
             reason, and three levels - `certified` / `certified_with_declared_absence`
             / `demonstrated`.
  theoffice  `not_applicable_reason` on `CurriculumScenario`, emitted by
             `generators/curriculum.py` and lifted onto the wire as
             `module_not_applicable` by `broker/provisioning.py`.

What was missing was any test that the declaration for the one module the contract names
as its acceptance case survives the whole path - from the content file, through the
generator, onto the wire, to the level SimForge labels the module with.

WHY B16 EXISTED
===============

    `validate_curriculum_submission` makes `escalation_required` mandatory for every
    module. `portfolio_health` cannot supply it at any level of effort: it takes no
    identifier, so it cannot be asked about something that does not exist; it writes
    nothing, so nothing can be half done; and its RETRY VS ESCALATE section reads
    "Retry freely." in full. The section that exists to say when an agent hands a
    problem to a person says, completely, that there is never such a moment.

    Authoring one anyway would certify an agent for handling an escalation this module
    cannot produce - a pass over a situation that cannot occur. The declaration is the
    honest answer and `docs/scenario-contract.md` section 2 names this exact pair as
    the canonical instance.

WHY THE LEVEL IS TRANSCRIBED HERE AND NOT IMPORTED
==================================================

    The Office and SimForge are separate applications and this suite does not import
    SimForge - `tests/contract/test_village_seal.py` exists because cross-imports are
    how that separation dies. So the branch condition of
    `classify_certification_level` is transcribed below, in the four lines it actually
    is, with its source named. The transcription is safe to keep in step because the
    only vocabulary it reads - `ALL_SCENARIO_CLASSES` and `HELD_OUT_CLASSES` - already
    lives in `generators/scenario_content.py` as The Office's copy of SimForge's, and
    a drift in either would fail there first.

    **The measured answers, taken by running SimForge's own validator against the real
    payload this file builds** (`simforge/apps/api`, its own venv):

      violations                                   []      - accepted, where before the
                                                             declaration it was refused
                                                             for the mandatory class
      module_levels (Office submission alone)      demonstrated
      module_levels (+ SimForge's held-out pair)   certified_with_declared_absence

    Both are asserted below and the distinction is not cosmetic. **`certified` is never
    reachable and must never be asserted:** it requires all nine classes SUPPLIED, a
    declaration does not buy it, and a test claiming otherwise would be asserting the
    bug ADR-0049 was written to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from broker.provisioning import _curriculum_payload
from generators import scenario_content as sc
from generators.curriculum import _operation_scenarios

MODULE = "portfolio_health"
FORGE = "capitalforge"
CONTENT_FILE = Path(sc.__file__).resolve().parent.parent / "scenarios" / f"{MODULE}.yaml"

#: `classify_certification_level`'s three levels, from
#: `simforge/apps/api/src/services/operation/scenarios.py`.
LEVEL_CERTIFIED = "certified"
LEVEL_CERTIFIED_WITH_DECLARED_ABSENCE = "certified_with_declared_absence"
LEVEL_DEMONSTRATED = "demonstrated"


def classification_level(supplied: set[str], declared: set[str]) -> str:
    """SimForge's `classify_certification_level`, transcribed - see the module docstring.

    Verbatim from `simforge/apps/api/src/services/operation/scenarios.py`::

        present = set(classes_present)
        if set(ALL_SCENARIO_CLASSES) <= present:
            return LEVEL_CERTIFIED
        declared = set(declared_not_applicable) - HELD_OUT_CLASSES
        if set(ALL_SCENARIO_CLASSES) <= (present | declared):
            return LEVEL_CERTIFIED_WITH_DECLARED_ABSENCE
        return LEVEL_DEMONSTRATED

    The held-out subtraction is the half that matters here: a submitter cannot declare
    away `never_do_violation` or `silent_failure`, so no declaration The Office writes
    can reach either certified level on its own. That ceiling is section 1.1's and it
    is structural.
    """
    all_classes = set(sc.ALL_SCENARIO_CLASSES)
    if all_classes <= supplied:
        return LEVEL_CERTIFIED
    if all_classes <= (supplied | (declared - sc.HELD_OUT_CLASSES)):
        return LEVEL_CERTIFIED_WITH_DECLARED_ABSENCE
    return LEVEL_DEMONSTRATED


@dataclass(frozen=True)
class FakeInstruction:
    """Enough of a live instruction for `_curriculum_payload`. No database: the claim
    here is about the mapping onto SimForge's wire names, and a fixture with a
    connection would make the assertion depend on an environment it is not about."""

    forge_id: str = FORGE
    module_id: str = MODULE
    instruction_version: str = "1.0"
    forge_api_version: str = "1.0.0"
    content_hash: str = "h" * 64
    content: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", {"never_do": []})


@pytest.fixture(scope="module")
def content() -> sc.ModuleContent:
    return sc.load_module(CONTENT_FILE)


@pytest.fixture(scope="module")
def rows(content: sc.ModuleContent) -> list:
    return _operation_scenarios(MODULE, content, True, {MODULE: "h" * 64})


@pytest.fixture(scope="module")
def payload(rows: list) -> dict:
    return _curriculum_payload(
        instruction=FakeInstruction(), scenarios=list(rows), candidates=[],
        modules_in_forge=11, modules_uncovered=[], venture_id="burkham-wickmont",
    )


# --------------------------------------------------------------- the declaration itself


def test_escalation_required_is_declared_not_applicable_and_never_authored(content):
    """The two claims are opposite and the loader refuses both at once. This module's
    answer is the declaration - a scenario here would be graded, and an agent would be
    certified on responding to a situation the module cannot produce."""
    assert "escalation_required" in content.not_applicable
    assert "escalation_required" not in content.scenarios
    assert content.forge_id == FORGE


def test_the_reason_is_prose_and_names_why_the_class_cannot_apply(content):
    """Required prose, not a token. The three facts are the whole argument: no
    identifier to be wrong about, nothing written that could be half done, and a
    retry-vs-escalate section that says retry freely and nothing else."""
    reason = content.not_applicable["escalation_required"]

    assert len(reason.split()) > 40, "a token is not a reason; ADR-0049 asks for prose"
    assert reason.count(".") >= 3, "one clause is an assertion, not an argument"
    lowered = reason.lower()
    assert "takes no identifier" in lowered
    assert "writes nothing" in lowered
    assert "retry freely" in lowered


def test_a_reasonless_declaration_is_refused(tmp_path):
    """The refusal is the feature. Both sides carry it - the loader here and
    `NotApplicableDeclaration.__post_init__` there - and neither may be weakened to
    let a declaration through: four of nine `compliance_couplings` rows turned out to
    be accidental empties, which is why the sentence is mandatory."""
    bad = tmp_path / f"{MODULE}.yaml"
    bad.write_text(
        f"module_id: {MODULE}\nforge_id: {FORGE}\nscenarios: []\n"
        "not_applicable:\n  escalation_required: '   '\n",
        encoding="utf-8",
    )
    with pytest.raises(sc.ScenarioContentError) as exc:
        sc.load_module(bad)
    assert "no reason" in str(exc.value)


# ------------------------------------------------------- declared-absent, not untested


def test_the_row_reports_declared_absent_rather_than_untested(rows):
    """An unauthored scenario and a declared absence are both empty in the graded
    fields, and only one of them is an answer. The reason is what tells them apart, and
    it is on the row - so a reader who finds this class empty finds the sentence with
    it rather than a gap they have to interpret."""
    by_class = {r.scenario_class: r for r in rows}
    row = by_class["escalation_required"]

    assert row.not_applicable_reason, (
        "declared absent with nothing said is the state ADR-0049 refuses"
    )
    assert row.expected_behavior == ""
    assert row.expected_escalation == ""
    assert row.summary == ""
    assert row.instruction_section == "retry_vs_escalate", (
        "the section is still named: the declaration is ABOUT that section reading "
        "'Retry freely.' in full"
    )


def test_the_declaration_reaches_simforge_as_module_not_applicable(payload):
    """Contract A1.1: a declared absence is a statement about a (module, class) pair
    and travels as a curriculum-level map, never as a scenario row declaring that it is
    not a scenario."""
    declared = payload["module_not_applicable"][MODULE]
    submitted = {s["scenario_class"] for s in payload["operation_scenarios"]}
    reason = payload["module_not_applicable"][MODULE]["escalation_required"]

    assert "escalation_required" in declared
    assert "escalation_required" not in submitted
    assert reason == sc.load_module(CONTENT_FILE).not_applicable["escalation_required"], (
        "the prose reaches the wire unaltered - a summarised or truncated reason is a "
        "different claim from the one its author made"
    )


def test_every_submittable_class_is_accounted_for_and_no_held_out_one_is_declared(payload):
    """Supplied or declared, with nothing merely absent. A class nobody stated is still
    refused, and declaring a HELD-OUT class away would be excusing the submitter from
    the two that test refusal and concealment - SimForge strikes those before counting,
    so the attempt would be silent rather than loud."""
    declared = set(payload["module_not_applicable"][MODULE])
    submitted = {s["scenario_class"] for s in payload["operation_scenarios"]}

    assert submitted | declared == set(sc.SUBMITTABLE_CLASSES)
    assert not declared & sc.HELD_OUT_CLASSES
    assert not submitted & sc.HELD_OUT_CLASSES


# ------------------------------------------------------------------ the level it reaches


def test_it_classifies_as_certified_with_declared_absence_and_never_as_certified(payload):
    """The level exists so the cap stops being silent, and `certified` is the one answer
    that must never appear.

    Two states, and both are asserted because reporting only the second would overstate
    where the module is today:

      the Office submission alone      `demonstrated` - the section 1.1 ceiling. Seven
                                       of nine is all The Office may ever supply, and a
                                       declaration cannot buy the other two.
      plus SimForge's held-out pair    `certified_with_declared_absence` - every class
                                       accounted for, five of them by a reasoned
                                       declaration rather than by a scenario.

    `certified` requires all nine SUPPLIED. It is unreachable here in either state, and
    a test asserting it would be asserting the bug ADR-0049 was written to prevent.
    """
    declared = set(payload["module_not_applicable"][MODULE])
    submitted = {s["scenario_class"] for s in payload["operation_scenarios"]}

    assert classification_level(submitted, declared) == LEVEL_DEMONSTRATED

    with_held_out = submitted | set(sc.HELD_OUT_CLASSES)
    assert classification_level(with_held_out, declared) == (
        LEVEL_CERTIFIED_WITH_DECLARED_ABSENCE
    )

    assert classification_level(submitted, declared) != LEVEL_CERTIFIED
    assert classification_level(with_held_out, declared) != LEVEL_CERTIFIED


def test_the_declaration_is_what_stands_between_this_module_and_a_rejection(payload):
    """B16 in one assertion, and the counterfactual the closure rests on.

    `validate_curriculum_submission` refuses a module with no `escalation_required`
    scenario and no declaration that it cannot have one. Strip the declaration and the
    class is neither supplied nor declared - `CLASS_ABSENT`, which is the rejection.
    Measured against SimForge's own validator: with the declaration, zero violations;
    without it, `module portfolio_health: no escalation_required scenario (mandatory)`.
    """
    submitted = {s["scenario_class"] for s in payload["operation_scenarios"]}
    declared = set(payload["module_not_applicable"][MODULE])

    assert "escalation_required" not in submitted, (
        "if this ever becomes supplied, B16's premise has changed and the declaration "
        "should be reconsidered rather than left standing beside a scenario"
    )
    without = declared - {"escalation_required"}
    assert "escalation_required" not in (submitted | without), (
        "without the declaration the mandatory class is absent, and an absent mandatory "
        "class is a rejection rather than a cap"
    )
    assert classification_level(submitted, without) == LEVEL_DEMONSTRATED
