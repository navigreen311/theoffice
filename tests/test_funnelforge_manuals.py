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

    P-16 delivered five of the nine and named the other four in OUTSTANDING, asserted
    ABSENT - so the day somebody wrote one, this file failed until the name moved from
    one list to the other. A partial delivery that is asserted stays visible; a partial
    delivery that is merely incomplete becomes invisible the moment somebody stops
    counting.

    **THE MECHANISM FIRED AS DESIGNED AND THE LIST IS NOW EMPTY.** P-16b authored the
    remaining four - `send_scheduling_confirmation`, `send_deliverable_cover`,
    `send_followup_no_engagement`, `send_brief_cover` - and moving each name across is
    what brought every assertion above to bear on it. Nine manuals, nine scenario sets.

    OUTSTANDING IS KEPT RATHER THAN DELETED, and that is not sentiment. It is where a
    tenth bound module lands: the meta-test refuses a name that is in neither list, so
    the next person to bind one chooses a list rather than discovering months later that
    a module has no instruction. An empty tuple with a live meta-test is a working
    mechanism; a deleted one is a gap that reads as completeness.

    Two tests below changed shape when the list emptied, because a parametrised test
    over an empty tuple is a skip that reports as a pass, and the two things they were
    proving still need proving. See each docstring.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from adapters.funnelforge.modules import MODULES
from broker.instructions import REQUIRED_SECTIONS
from generators.scenario_content import SUBMITTABLE_CLASSES, load_module

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = ROOT / "docs" / "instructions"
SCENARIOS = ROOT / "scenarios"

#: Burkham's Compliance Library, as a file. **Not the table.** `compliance_library_entry`
#: is keyed on `entry_ref` with no venture column and is shared across ventures, so it
#: holds this file's entries plus Greenstone's two - a count read from the table is a
#: different number and answers a different question. These checks read the file, which
#: is what shared rule 10 makes a claim about.
LIBRARY = ROOT / "packs" / "compliance-library" / "burkham-wickmont.yaml"

#: Shared rule 10 states the entry count in words. This is what lets a test compare a
#: sentence to the file it describes. Deliberately small: if the library grows past
#: twenty-five, extending this is the moment somebody re-reads the sentence.
NUMBER_WORDS: dict[str, int] = {
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "twenty-one": 21, "twenty-two": 22, "twenty-three": 23, "twenty-four": 24,
    "twenty-five": 25,
}

#: The sentence in shared rule 10 that states the count, as a pattern rather than as a
#: number, so the test reads what the prose currently claims instead of hard-coding it.
LIBRARY_COUNT_CLAIM = re.compile(r"\*\*holds ([a-z-]+) entries\*\*")

#: Any `compliance/<name>-v<n>` ref, wherever a FunnelForge doc cites one.
COMPLIANCE_REF = re.compile(r"compliance/[a-z0-9-]+v\d")

#: Refs a FunnelForge doc may name WITHOUT them being Burkham's, and the reason.
#:
#: Shared rule 10 names these two to make the point that `compliance_library_entry` is
#: keyed on `entry_ref` with no venture column, so a ref resolving in the table says
#: nothing about whose entry answered. They are **Greenstone's**, cited by
#: `packs/greenstone.yaml`.
#:
#: **Neither has a library file anywhere in this repository.** `packs/compliance-library/`
#: holds exactly one file, Burkham's. These two exist only as rows - seeded, not authored
#: from git - which is recorded in `docs/blocking.md` B41 and is why they cannot simply be
#: resolved against the directory.
#:
#: The exclusion is asserted rather than trusted: `test_the_greenstone_refs_are_still_not
#: _burkhams` fails if either is ever written into Burkham's file, at which point the name
#: belongs in the check above rather than in this list.
NOT_BURKHAMS: frozenset[str] = frozenset(
    {"compliance/ftc-tsr-v2", "compliance/nv-two-party-consent-v1"}
)


def _library_entry_refs() -> set[str]:
    """Every `entry_ref` in Burkham's library file. Loaded, not counted by grep."""
    doc = yaml.safe_load(LIBRARY.read_text(encoding="utf-8")) or {}
    entries = doc.get("entries") or []
    return {
        e["entry_ref"]
        for e in entries
        if isinstance(e, dict) and e.get("entry_ref")
    }

#: Copied from `scripts/check_module_manuals.py` deliberately rather than imported.
#: That file is a script, not a module - importing it by path would drag
#: `broker.db.connection` into a filesystem-only test for nothing. The copy is asserted
#: against the original in `test_the_header_regexes_still_match_the_check_script`, so a
#: change there fails here rather than drifting silently.
FORGE_LINE = re.compile(r"\*\*Forge:\*\*\s*([^*\n]+?)(?:\s{2,}|\n|\*\*)")
MODULE_LINE = re.compile(r"\*\*Module:\*\*\s*`([a-z0-9_]+)`")

#: Every bound module. Manual and scenarios, both, to the standard of the eleven.
#: The first five are P-16's; the last four are P-16b's, moved here out of OUTSTANDING,
#: which is what put them under every assertion in this file.
DELIVERED: dict[str, str] = {
    "send_intake_acknowledgment": "funnelforge-send-intake-acknowledgment.md",
    "distribute_referrer_briefing": "funnelforge-distribute-referrer-briefing.md",
    "schedule_blueprint_call": "funnelforge-schedule-blueprint-call.md",
    "capture_contact": "funnelforge-capture-contact.md",
    "read_funnel_analytics": "funnelforge-read-funnel-analytics.md",
    "send_scheduling_confirmation": "funnelforge-send-scheduling-confirmation.md",
    "send_deliverable_cover": "funnelforge-send-deliverable-cover.md",
    "send_followup_no_engagement": "funnelforge-send-followup-no-engagement.md",
    "send_brief_cover": "funnelforge-send-brief-cover.md",
}

#: Bound modules with no manual. **Empty, and kept.**
#:
#: P-16 put four names here and P-16b emptied it. It is not deleted because the
#: meta-test refuses a bound name that is in neither list, so this is where a tenth
#: module lands the day somebody binds one - a decision, taken then, rather than a
#: manual nobody notices is missing. What is owed for a name that appears here is what
#: was owed for those four: the occasion, the recipient and what that recipient believes
#: when the message arrives, the approved copy quoted in full, and the compliance
#: entries that copy touches. Everything shared lives in the shared rules and is not
#: restated per module.
OUTSTANDING: tuple[str, ...] = ()

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


def test_nothing_is_outstanding_and_no_stray_file_claims_a_name_that_is():
    """P-16 delivered five of nine and said so; P-16b delivered the other four.

    **This test is not parametrised, and that is the change P-16b made rather than an
    oversight.** It was `@pytest.mark.parametrize("module_id", sorted(OUTSTANDING))`,
    which was right while four names were in the list and becomes a *skip* the moment
    the list empties - and a skip reports in the same green summary line as a pass. The
    thing this file exists to prevent is a gap that reports itself as filled, so the
    test that guards the gap must not be the one that quietly stops running.

    So it now asserts both halves explicitly. That OUTSTANDING is empty, which is a
    statement about the nine that a reader can see failed if it stops being true. And,
    for any name that IS in it, that no manual and no scenario file has appeared for
    that name - the original assertion, kept whole, because the day a tenth module is
    bound this is what makes authoring its manual visible instead of optional.

    If the loop below ever fails, the fix is to move the name into DELIVERED with its
    filename, at which point every assertion above starts applying to it. If it fails
    and you did NOT author a manual, something else created a file for that module id,
    and that is the `lender_match` shape: a name registered to clear a line. Read it
    before you keep it.
    """
    assert OUTSTANDING == (), (
        "OUTSTANDING is no longer empty. That is not a failure by itself - it is how a "
        f"newly bound module announces that nobody has written its manual: {OUTSTANDING}. "
        "Author it, or record here why it is owed and by whom, and then update this "
        "assertion deliberately rather than to make a red line green."
    )
    for module_id in OUTSTANDING:
        stray_manuals = [
            p.name
            for p in INSTRUCTIONS.glob("funnelforge-*.md")
            if (m := MODULE_LINE.search(_text(p))) is not None
            and m.group(1) == module_id
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


def test_the_six_approved_sends_are_the_six_the_manual_set_says_they_are():
    """The shape claim the manual set rests on, asserted against the dispatch map.

    **This replaces `test_the_four_outstanding_are_all_approved_sends`**, which looped
    over OUTSTANDING to prove that the four handed over were approved sends sharing a
    request shape with a manual that already existed. That was a live assertion while
    the list had four names in it and became a vacuous pass when it emptied - the loop
    body simply stops executing, and nothing says so.

    What it was really proving is still worth proving and is now true of the whole set:
    six modules bind a template and three do not, and every manual in this set is
    written on that split. The send manuals lean on `send_intake_acknowledgment` for a
    request shape, two refusals, a failure table and a retry rule; the three non-sends
    do not, because they have none of it. If a binding ever changes side - a send loses
    its template, or `capture_contact` gains one - the manual that leans on the shared
    shape is describing a module that no longer has it, and this is where that surfaces.
    """
    sends = {m for m, b in MODULES.items() if b.template_id is not None}
    non_sends = set(MODULES) - sends

    assert len(sends) == 6, (
        f"the manual set is written around six approved sends and finds {len(sends)}: "
        f"{sorted(sends)}. `funnelforge-approved-send-rules.md` and every send manual "
        "state six; re-read them before changing a binding."
    )
    assert non_sends == {
        "schedule_blueprint_call",
        "capture_contact",
        "read_funnel_analytics",
    }, f"the three non-send modules are not the three the manuals name: {sorted(non_sends)}"

    for module_id in sorted(sends):
        binding = MODULES[module_id]
        assert binding.is_mutating is True
        assert binding.idempotency_support == "at_most_once", (
            f"{module_id} declares idempotency_support "
            f"{binding.idempotency_support!r}. Shared rule 8 and every send manual's "
            "retry rule are written on `at_most_once`, and V31's refusal is over "
            "exactly that shape - a change here changes what those manuals teach."
        )


# ------------------------------------------- the library, read rather than described


def test_the_library_file_is_there_and_is_not_empty():
    """A meta-test, because every check below would pass over a missing file.

    `_library_entry_refs` returns an empty set for a file that is absent, a file whose
    `entries` key is gone, and a file that genuinely holds nothing - and an empty set
    satisfies a subset check vacuously. This is what stops the two tests below from
    reporting green over exactly the state shared rule 10 once wrongly described.
    """
    assert LIBRARY.exists(), (
        f"{LIBRARY.name} is missing. Shared rule 10 tells an agent to read the entry, "
        "and every ref the nine manuals cite would resolve to nothing."
    )
    assert len(_library_entry_refs()) >= 12, (
        "Burkham's Compliance Library holds fewer than twelve entries. That is either a "
        "real regression or a parse failure, and both need a human before this is edited "
        "to match."
    )


def test_shared_rule_10_states_the_entry_count_the_library_actually_holds():
    """The claim that went stale, now checked against the thing it claims about.

    Rule 10 said the Library ships empty while nineteen entries sat in git - the error
    the correction paragraph records. Then the correction *itself* paired today's count
    with the first commit, where the count was seventeen. Both failures are the same
    failure: **a number about a file, written in prose, with nothing reading the file.**

    So this reads the file. If somebody adds a twentieth entry, the sentence in shared
    rule 10 stops being true and this says so on the commit that made it untrue, rather
    than nine days later in a manual that inherited it.

    It deliberately does NOT check the commit hashes or the dated history in that
    paragraph. Those are claims about the past and the past does not drift; the count is
    a claim about now, and now is what goes stale.
    """
    prose = _text(INSTRUCTIONS / SHARED_RULES)
    match = LIBRARY_COUNT_CLAIM.search(prose)
    assert match is not None, (
        f"{SHARED_RULES} no longer states the library's entry count in the form "
        "`**holds <word> entries**`. The sentence is what this test compares against "
        "the file - if it was rewritten, update the pattern deliberately; if it was "
        "deleted, the count claim is back to being unchecked prose."
    )
    word = match.group(1)
    assert word in NUMBER_WORDS, (
        f"{SHARED_RULES} states the count as {word!r}, which is not in NUMBER_WORDS. "
        "Add it if the library really grew; do not delete this assertion."
    )
    claimed = NUMBER_WORDS[word]
    actual = len(_library_entry_refs())
    assert claimed == actual, (
        f"{SHARED_RULES} says the Compliance Library holds {word} ({claimed}) entries "
        f"and {LIBRARY.name} holds {actual}. The prose is the thing that is wrong here "
        "unless an entry was deleted - read the file, then fix the sentence. This is the "
        "B41 shape: a count in a manual that nothing was checking."
    )


def test_every_compliance_ref_the_funnelforge_docs_cite_resolves_in_the_library():
    """What rule 10's original error would have caused, had it been true.

    The retracted sentence said *"every ref above names an entry an agent cannot read"*.
    It was false - every ref resolved - but nothing in this suite could have told the
    difference, which is why it survived into a shared-rules file that all nine manuals
    point at. An agent told an entry is unreadable does not go and read it.

    This checks the refs rather than the sentence, across the shared rules and all nine
    manuals at once. A manual that cites an entry nobody wrote fails here, and so does a
    library edit that renames or removes an entry a manual depends on - which is the
    direction that would otherwise go unnoticed, because the manual is not touched by it.

    Scope is the FunnelForge set. V28 checks Pack rows against the *table*; nothing
    checked manual prose against anything.
    """
    library = _library_entry_refs()
    cited: dict[str, list[str]] = {}
    for path in sorted(INSTRUCTIONS.glob("funnelforge-*.md")):
        for ref in COMPLIANCE_REF.findall(_text(path)):
            cited.setdefault(ref, []).append(path.name)

    assert cited, (
        "no compliance refs found in any funnelforge-*.md. Every send manual's "
        "`WHICH LAWS THIS TOUCHES` section names at least one, so finding none means "
        "this test stopped looking rather than that the manuals stopped citing."
    )

    unresolved = {
        ref: sorted(set(files))
        for ref, files in cited.items()
        if ref not in library and ref not in NOT_BURKHAMS
    }
    assert not unresolved, (
        "these compliance refs are cited by FunnelForge manuals and are absent from "
        f"{LIBRARY.name}: "
        + "; ".join(f"{ref} (cited by {', '.join(f)})" for ref, f in sorted(unresolved.items()))
        + ". Either the entry was renamed or removed and the manuals were not "
        "followed through, or a manual cites an entry nobody wrote. An agent told to "
        "read the entry would find nothing."
    )


def test_the_shared_rules_name_the_gate_per_send_rather_than_once():
    """Rule 10a exists because "it applies to all six" is how a gate becomes a formality.

    `outbound-contact-boundary-v1` bears differently on the six: satisfied by the
    occasion on the two transactional sends, doing real work on the follow-up, and
    marking a boundary `brief_cover` **cannot see** because nothing on that path reads
    engagement status. A reader who meets the entry once, in a list of laws, learns that
    it applies and not where it bites.

    This cannot check the table is *right*. It checks that every send is named in it, so
    a seventh approved send cannot be added without somebody deciding what the gate does
    to it.
    """
    prose = _text(INSTRUCTIONS / SHARED_RULES)
    assert "### 10a." in prose, (
        f"{SHARED_RULES} has lost rule 10a, the per-send gate table. Without it the "
        "governing entry is named once for all six and an agent cannot tell which of "
        "them it actually refuses."
    )
    section = prose.split("### 10a.", 1)[1]

    # **Row-wise, not section-wise, and that distinction was found by watching this
    # test fail to fail.** Checking `f"`{send}`" in section` passes for a send that has
    # lost its table row and is merely *mentioned* in the prose underneath - which is
    # the state this test exists to catch, and it reported green on it. The name must
    # open a row.
    rows = {
        m.group(1)
        for m in re.finditer(r"^\|\s*`([a-z0-9_]+)`\s*\|", section, re.MULTILINE)
    }
    sends = sorted(
        MODULES[m].template_id
        for m in MODULES
        if MODULES[m].template_id is not None
    )
    missing = [s for s in sends if s not in rows]
    assert not missing, (
        f"rule 10a has no table row for {missing} against "
        "`compliance/outbound-contact-boundary-v1`. Every approved send is "
        "Burkham-initiated contact with an individual, so the gate applies to it - what "
        "the table records is whether the occasion supplies the evidence or the module "
        "is blind to it. A send with no row has had that question skipped. (Being named "
        "in the paragraph below the table is not a row.)"
    )
    assert not rows - set(sends), (
        f"rule 10a has rows for {sorted(rows - set(sends))}, which are not approved "
        "sends. The table is about the six; a row for anything else means a binding "
        "changed or the table drifted from the dispatch map."
    )


def test_the_greenstone_refs_are_still_not_burkhams():
    """The exclusion list above, checked rather than trusted.

    `NOT_BURKHAMS` exists so that shared rule 10 can name two entries as an example of
    the venture-blindness of `compliance_library_entry` without the ref check reading
    them as Burkham citations. An exclusion list is a claim like any other, and this is
    the claim: these two are not in Burkham's file.

    If Burkham ever adopts one - two ventures under one compliance regime arguably
    *should* share a row, which `scripts/load_compliance_library.py` records as an open
    decision - this fails, and the fix is to take the name out of `NOT_BURKHAMS` so the
    ref check starts covering it. Without this, that adoption would silently leave a
    genuine Burkham entry permanently unchecked.
    """
    library = _library_entry_refs()
    adopted = sorted(NOT_BURKHAMS & library)
    assert not adopted, (
        f"{adopted} is in {LIBRARY.name} and is also listed in NOT_BURKHAMS as another "
        "venture's. One of the two is now wrong. If Burkham has adopted the entry, "
        "remove it from NOT_BURKHAMS so the ref check covers it; if the file grew it by "
        "accident, that is a venture writing over a shared row - read "
        "scripts/load_compliance_library.py before resolving it either way."
    )
