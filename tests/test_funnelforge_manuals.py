"""P-16 - the FunnelForge manuals and scenarios, asserted rather than assumed.

WHY THIS FILE EXISTS AT ALL
===========================

    Nothing in this suite checked that a bound module had an operating instruction.
    `scripts/check_module_manuals.py` does, and it is a script rather than a test: it
    needs a running Forge to ask, and it reports NOT_RUN and proves nothing when it
    cannot reach one. FunnelForge's adapter is not deployed anywhere, so that script
    will answer NOT_RUN for `funnelforge` until it is - which means, without this file,
    the nine manuals could be absent, wrong-named, or missing sections and no test
    anywhere would notice.

    That is the same shape as the gap that let V34 ship untested: caught only because a
    pass count did not move.

WHAT THIS DOES AND DOES NOT PROVE
=================================

    It proves that every manual P-16 delivers is discoverable BY THE SAME REGEXES the
    check script uses, that its header names the module its filename implies, that it
    carries all eight Part 6.1 sections, and that its scenario file loads and accounts
    for all seven classes The Office may submit.

    It does not read the manual and it cannot tell you the manual is accurate. Nothing
    in a test can. `docs/forge-adapter.md` trap #4 is the standing answer to that and it
    is a call against a running Forge, not an assertion.

SCOPE - THE FUNNELFORGE NINE ONLY
=================================

    Not CapitalForge's eleven. Widening this file to cover them would be a change to
    coverage P-16 does not own, and if it went red P-16 would be holding somebody else's
    failure. Whether it *should* be widened is raised in P-16's PR, separately.

THE DELIVERED SUBSET IS A CONSTANT, AND THAT IS THE DESIGN
==========================================================

    P-16 delivers five of the nine. The other four are named in OUTSTANDING below and
    are asserted ABSENT - so the day somebody writes one, this file fails until they
    move the name from one list to the other. A partial delivery that is asserted stays
    visible; a partial delivery that is merely incomplete becomes invisible the moment
    somebody stops counting.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from adapters.funnelforge.modules import MODULES
from broker.instructions import REQUIRED_SECTIONS
from generators.scenario_content import SUBMITTABLE_CLASSES, load_module

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = ROOT / "docs" / "instructions"
SCENARIOS = ROOT / "scenarios"

#: Copied from `scripts/check_module_manuals.py` deliberately rather than imported.
#: That file is a script, not a module - importing it by path would drag
#: `broker.db.connection` into a filesystem-only test for nothing. The copy is asserted
#: against the original in `test_the_header_regexes_still_match_the_check_script`, so a
#: change there fails here rather than drifting silently.
FORGE_LINE = re.compile(r"\*\*Forge:\*\*\s*([^*\n]+?)(?:\s{2,}|\n|\*\*)")
MODULE_LINE = re.compile(r"\*\*Module:\*\*\s*`([a-z0-9_]+)`")

#: What P-16 authored. Manual and scenarios, both, to the standard of the eleven.
DELIVERED: dict[str, str] = {
    "send_intake_acknowledgment": "funnelforge-send-intake-acknowledgment.md",
    "distribute_referrer_briefing": "funnelforge-distribute-referrer-briefing.md",
    "schedule_blueprint_call": "funnelforge-schedule-blueprint-call.md",
    "capture_contact": "funnelforge-capture-contact.md",
    "read_funnel_analytics": "funnelforge-read-funnel-analytics.md",
}

#: What P-16 did not author, named individually because "four of nine" is a count and
#: this is a handover. Each is an approved autonomous send with the same request shape,
#: the same two refusals, the same failure table and the same retry rule as
#: `send_intake_acknowledgment`; what is owed per module is the occasion, the recipient,
#: the approved copy quoted, and the compliance entries that copy touches.
OUTSTANDING: tuple[str, ...] = (
    "send_scheduling_confirmation",
    "send_deliverable_cover",
    "send_followup_no_engagement",
    "send_brief_cover",
)

#: Not a module manual. Shared rules govern the six sends and name no module, which is
#: why it carries no `**Module:**` header - see `test_the_shared_rules_file_is_shared`.
SHARED_RULES = "funnelforge-approved-send-rules.md"

#: The eight Part 6.1 sections, as headings in a manual. `broker.instructions` names the
#: fields; this maps each to the heading the manual set uses for it, so a manual missing
#: a section fails here rather than at `validate_sections` when somebody authors it into
#: `forge_operating_instruction`.
SECTION_HEADINGS: dict[str, str] = {
    "what_it_does": "WHAT IT DOES",
    "what_it_does_not_do": "WHAT IT DOES NOT DO",
    "inputs": "INPUT",
    "correct_sequence": "THE CORRECT SEQUENCE",
    "failure_signatures": "WHAT FAILURE LOOKS LIKE",
    "retry_vs_escalate": "RETRY VS ESCALATE",
    "never_do": "NEVER",
    "compliance_coupling": "WHICH LAWS THIS TOUCHES",
}


def _manual(module_id: str) -> Path:
    return INSTRUCTIONS / DELIVERED[module_id]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- meta


def test_delivered_and_outstanding_together_are_the_nine_bound_modules():
    """A meta-test that finds nothing passes for the wrong reason.

    The dispatch map is the naming authority - `sorted(MODULES)` is derived from the
    handlers, so a name is in it if and only if a function is bound. If a tenth module
    is ever bound, or one is removed, this fails and somebody decides which list it
    belongs in rather than the omission going unnoticed.
    """
    assert set(DELIVERED) | set(OUTSTANDING) == set(MODULES), (
        "DELIVERED plus OUTSTANDING must be exactly the modules the adapter dispatches. "
        f"bound={sorted(MODULES)} delivered={sorted(DELIVERED)} "
        f"outstanding={sorted(OUTSTANDING)}"
    )
    assert not set(DELIVERED) & set(OUTSTANDING)
    assert len(MODULES) == 9


def test_the_header_regexes_still_match_the_check_script():
    """The two patterns above are a copy. This is what stops it drifting.

    `scripts/check_module_manuals.py` is what actually decides whether a manual is
    found, and it is not importable without dragging a database module in. So the
    patterns are copied and compared as source text: change them there and this fails
    here, which is the whole point of copying them at all.
    """
    script = _text(ROOT / "scripts" / "check_module_manuals.py")
    assert FORGE_LINE.pattern in script, (
        "the Forge-header pattern no longer matches scripts/check_module_manuals.py. "
        "Update the copy in this file, and re-check that every manual still parses."
    )
    assert MODULE_LINE.pattern in script, (
        "the Module-header pattern no longer matches scripts/check_module_manuals.py."
    )


# ------------------------------------------------------------------- the manuals


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_every_delivered_module_has_a_manual_on_disk(module_id: str):
    path = _manual(module_id)
    assert path.exists(), (
        f"{module_id} is bound and DELIVERED names {path.name}, which is not in "
        "docs/instructions/. Unit A certification is earned against an instruction's "
        "content hash, so a grant for this would be issued against nothing."
    )


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_every_manual_declares_the_forge_and_module_the_check_script_looks_for(
    module_id: str,
):
    """A manual that does not say what it is about cannot be checked.

    `check_module_manuals.py` skips such a file with a warning and moves on - so a
    header that does not parse is not a failure over there, and it means the manual is
    invisible to the only check that exists. It is a failure here.
    """
    text = _text(_manual(module_id))

    forge = FORGE_LINE.search(text)
    assert forge is not None, f"{DELIVERED[module_id]} declares no **Forge:** header"
    slug = forge.group(1).strip().lower().replace(" ", "-")
    assert slug == "funnelforge", (
        f"{DELIVERED[module_id]} declares Forge {slug!r}. `forge_registry` spells it "
        "`funnelforge`, and the check script slugs the header the same way."
    )

    module = MODULE_LINE.search(text)
    assert module is not None, f"{DELIVERED[module_id]} declares no **Module:** header"
    assert module.group(1) == module_id, (
        f"{DELIVERED[module_id]} declares itself the manual for "
        f"{module.group(1)!r}, but DELIVERED files it under {module_id!r}. A file "
        "loaded under one name and read under another is the mismatch this checks for."
    )


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_every_manual_carries_all_eight_part_6_1_sections(module_id: str, section: str):
    """Part 6.1 requires all eight, and both `validate_sections` and a CHECK constraint
    refuse an instruction that is missing one or carries one empty.

    Catching it here means an author finds out while writing rather than when somebody
    runs `broker.instructions.author()` months later.
    """
    heading = SECTION_HEADINGS[section]
    text = _text(_manual(module_id))
    assert heading in text, (
        f"{DELIVERED[module_id]} has no section for {section!r} (looked for "
        f"{heading!r}). `broker.instructions.validate_sections` refuses an instruction "
        "missing it, and so does the table."
    )


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_every_manual_points_at_the_shared_rules(module_id: str):
    """The shared rules carry the facts that would otherwise be restated per manual,
    and restating them per manual is how they drift - `foi-shared-rules.md` says so at
    the top and this manual set follows it."""
    assert SHARED_RULES in _text(_manual(module_id)), (
        f"{DELIVERED[module_id]} does not reference {SHARED_RULES}. Every FunnelForge "
        "manual depends on it; a manual that does not say so reads as self-contained."
    )


def test_the_shared_rules_file_is_shared():
    """It must NOT declare a module, and that is deliberate rather than an oversight.

    `check_module_manuals.py` hard-codes `foi-shared-rules.md` in its `SHARED` set and
    knows nothing about this one, so this file falls to the "declares no Forge and
    Module header pair; skipped" branch - a printed note, not a failure. Adding it to
    `SHARED` is a one-line change outside P-16's scope, and this test is what keeps the
    file honest until somebody makes it: if it ever grows a `**Module:**` header it
    would start claiming to be one module's manual, and the check script would then
    fail whichever module's file it collided with.
    """
    path = INSTRUCTIONS / SHARED_RULES
    assert path.exists(), f"{SHARED_RULES} is missing; every manual references it"
    assert MODULE_LINE.search(_text(path)) is None, (
        f"{SHARED_RULES} has grown a **Module:** header. It is shared rules and names "
        "no module. With one, check_module_manuals.py would read it as some module's "
        "manual and fail the module whose own file it displaced."
    )


# ----------------------------------------------------------------- the scenarios


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_every_delivered_module_has_a_scenario_file_that_loads(module_id: str):
    """The filename is the index the content files partition on, and `load_module`
    refuses a file whose name and `module_id` disagree - so this also proves the pair
    match."""
    path = SCENARIOS / f"{module_id}.yaml"
    assert path.exists(), f"{module_id} has a manual and no scenarios/{module_id}.yaml"
    content = load_module(path)
    assert content.module_id == module_id
    assert content.forge_id == "funnelforge", (
        f"scenarios/{module_id}.yaml declares forge_id {content.forge_id!r}"
    )


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_every_scenario_file_accounts_for_all_seven_submittable_classes(module_id: str):
    """A class that is neither supplied nor declared `not_applicable` is refused on
    submission - `docs/scenario-contract.md` 2, property 1. A class nobody thought about
    does not slip through as presumably fine, so this makes "nobody thought about it"
    fail here instead of at SimForge.
    """
    content = load_module(SCENARIOS / f"{module_id}.yaml")
    accounted = set(content.scenarios) | set(content.not_applicable)
    missing = [c for c in SUBMITTABLE_CLASSES if c not in accounted]
    assert not missing, (
        f"scenarios/{module_id}.yaml accounts for neither an authored scenario nor a "
        f"declared not_applicable for: {', '.join(missing)}"
    )


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_the_two_mandatory_classes_are_present_for_every_delivered_module(
    module_id: str,
):
    """`escalation_required` is mandatory on every module and
    `recovery_after_failure` is mandatory whenever the rubric carries the `recovery`
    dimension - which the default `OPERATION_DIMENSIONS` does, so it is mandatory in
    practice today. Absence of either is a REJECT rather than a label, and a declared
    `not_applicable` is the only other admissible answer.
    """
    content = load_module(SCENARIOS / f"{module_id}.yaml")
    for mandatory in ("escalation_required", "recovery_after_failure"):
        assert (
            mandatory in content.scenarios or mandatory in content.not_applicable
        ), (
            f"scenarios/{module_id}.yaml has no {mandatory!r} and does not declare it "
            "not_applicable. That is a rejected submission, not a missing label."
        )


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_no_scenario_restates_that_escalation_is_expected(module_id: str):
    """`docs/scenario-contract.md` 3.2: prose that restates "escalation is expected"
    has not satisfied the field. The prose names the juncture - what the agent has in
    front of it, what it must stop short of, and to whom it hands the problem.

    This cannot check that the prose is good. It checks the two cheapest ways of
    producing a populated field that is not an answered one: a stub, and a sentence
    short enough that it cannot be naming three things.
    """
    content = load_module(SCENARIOS / f"{module_id}.yaml")
    for cls, scenario in sorted(content.scenarios.items()):
        prose = scenario.expected_escalation.strip()
        assert len(prose) >= 200, (
            f"scenarios/{module_id}.yaml [{cls}] has an expected_escalation of "
            f"{len(prose)} characters. Naming the juncture, the boundary and the "
            "recipient does not fit in that."
        )
        assert prose.lower() not in {
            "escalation is expected.",
            "escalation is expected",
            "none.",
            "n/a",
        }


@pytest.mark.parametrize("module_id", sorted(DELIVERED))
def test_every_authored_scenario_carries_a_situation_distinct_from_its_behaviour(
    module_id: str,
):
    """`docs/scenario-contract.md` 7: the manual sections give rules; a scenario needs
    an occasion. A `situation` that repeats the rule the scenario tests is a rule
    wearing an occasion's name, and the two halves travel in one field on the wire
    (`wire_behavior`), so nothing downstream would separate them again.
    """
    content = load_module(SCENARIOS / f"{module_id}.yaml")
    for cls, scenario in sorted(content.scenarios.items()):
        assert len(scenario.situation.strip()) >= 120, (
            f"scenarios/{module_id}.yaml [{cls}] has a situation too short to be an "
            "occasion. What is in front of the agent when the scenario starts?"
        )
        assert scenario.situation.strip() != scenario.expected_behavior.strip()


# --------------------------------------------------- the gap, asserted not implied


@pytest.mark.parametrize("module_id", sorted(OUTSTANDING))
def test_the_outstanding_four_are_outstanding(module_id: str):
    """P-16 delivered five of nine and said so. This is where that is enforced.

    The moment somebody authors one of these, this test fails - and the fix is to move
    the name from OUTSTANDING into DELIVERED with its filename, at which point every
    assertion above starts applying to it. A partial delivery that fails loudly when it
    is completed is a partial delivery nobody can lose track of.

    If this fails and you did NOT author a manual, something else created a file for one
    of these module ids, and that is the `lender_match` shape: a name registered to
    clear a line. Read it before you keep it.
    """
    stray_manuals = [
        p.name
        for p in INSTRUCTIONS.glob("funnelforge-*.md")
        if (m := MODULE_LINE.search(_text(p))) is not None and m.group(1) == module_id
    ]
    assert not stray_manuals, (
        f"{module_id} is listed OUTSTANDING and {stray_manuals} declares itself its "
        "manual. Move it into DELIVERED so the rest of this file applies to it."
    )
    scenario = SCENARIOS / f"{module_id}.yaml"
    assert not scenario.exists(), (
        f"{module_id} is listed OUTSTANDING and scenarios/{module_id}.yaml exists. "
        "Move it into DELIVERED so the rest of this file applies to it."
    )


def test_the_four_outstanding_are_all_approved_sends():
    """Why these four and not four others, asserted rather than asserted in prose.

    The subset P-16 delivered covers all three non-send modules plus two of the six
    approved sends - the canonical one and the one whose audience and compliance
    exposure differ most. What is left is four sends that share a request shape, two
    refusals, a failure table and a retry rule with a manual that already exists, which
    is the cheapest four to hand over and the reason the split fell here.
    """
    for module_id in OUTSTANDING:
        binding = MODULES[module_id]
        assert binding.template_id is not None, (
            f"{module_id} is OUTSTANDING but binds no template, so it is not one of the "
            "six approved sends. The subset rationale in this file no longer holds - "
            "re-read it before changing the lists."
        )
        assert binding.is_mutating is True
        assert binding.idempotency_support == "at_most_once"
