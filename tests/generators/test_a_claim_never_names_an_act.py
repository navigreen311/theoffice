"""A permitted claim value never names an act.

RULED 19 SEPTEMBER 2026 (decisions entry 133)
=============================================

    *"A permitted claim value never names an act. A claim states the fact, never the
    act."*

    SimForge measured it on `comp_analysis/malformed_input`: showing
    `REFUSED - NOT A UUID` in the permitted claims moved `REFUSE` from **25 of 40 to
    35 of 40**, replicated, and the neutral wording returned it to the no-naming
    baseline.

    Five of the 44 keys carried an act word in their options. **All five named REFUSE
    and not one of them expects REFUSE** - four expect DECLINE, one expects PROCEED.
    So the priming was pulling the agent toward an act every one of those keys grades
    as wrong.

WHY THE OPTIONS AND NOT THE PROSE
=================================

    `record_claim_options` is one of the few things the agent SEES. SimForge's
    `probe_for` puts the situation and the permitted claims; it never renders
    `expected_behavior`, *"because that field is what a good ANSWER looks like and
    showing it would hand the agent the answer"*. So an act word in the options is
    read by the model, and the same word in the expected behaviour is not.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_every_expected_claim_is_one_of_its_own_options`. The others forbid words. A
    reword that satisfied them by emptying an option list, or by leaving the expected
    claim outside it, would make every one of those scenarios ungradeable while the
    word check passed.
"""

from __future__ import annotations

import re

import pytest

from generators import scenario_content as sc

GREENSTONE = (
    "assign_contract", "buyer_match", "comp_analysis", "property_lookup",
    "underwrite_deal",
)

#: SimForge's four, transcribed from `services/operation/battery.py` - `ACT_PROCEED`,
#: `ACT_REFUSE`, `ACT_DECLINE`, `ACT_ESCALATE`. Transcribed rather than imported for the
#: reason the rest of this suite gives: a cross-import is how the separation dies.
ACTS = ("PROCEED", "REFUSE", "DECLINE", "ESCALATE")

#: Inflections included, and that is the whole reason this catches anything. The five
#: offending options said **REFUSED**, not `REFUSE`, so a bare-token match found none of
#: them. The defect is priming, not an exact token, and a past participle primes.
_ACT_WORD = re.compile(rf"\b({'|'.join(ACTS)})(S|D|ED|ING)?\b", re.IGNORECASE)


def _answers():
    loaded = sc.load_all()
    for module_id in GREENSTONE:
        content = loaded.for_module(module_id)
        assert content is not None, f"{module_id} is withheld"
        for scenario_class, occasions in content.scenarios.items():
            for i, authored in enumerate(occasions):
                yield f"{module_id}/{scenario_class}[{i}]", authored.expected_answer


def test_no_permitted_claim_names_an_act():
    """The ruling, over all 44."""
    naming = [
        (where, option)
        for where, answer in _answers()
        for option in (answer.get("record_claim_options") or [])
        if _ACT_WORD.search(str(option))
    ]
    assert not naming, (
        "these permitted claims name an act, which primes the agent toward it: "
        f"{naming}. A claim states the fact - `NOT A UUID`, not `REFUSED - NOT A UUID`."
    )


def test_no_expected_claim_names_an_act():
    """The same rule on the value the key expects.

    Four of the five offenders were expected claims as well as options, so a fix that
    cleaned the list and left the answer would have put the expected claim outside its
    own list - ungradeable, and passing the test above.
    """
    naming = [
        (where, answer["record_claim"])
        for where, answer in _answers()
        if answer.get("record_claim") and _ACT_WORD.search(str(answer["record_claim"]))
    ]
    assert not naming, f"these expected claims name an act: {naming}"


def test_every_expected_claim_is_one_of_its_own_options():
    """**The test that keeps the others from being satisfied by deletion.**

    A reword that emptied an option list, or left the expected claim out of it, would
    make the scenario ungradeable while every word check above passed.
    """
    orphaned = [
        (where, answer.get("record_claim"), answer.get("record_claim_options"))
        for where, answer in _answers()
        if answer.get("record_claim_options")
        and answer.get("record_claim") not in answer["record_claim_options"]
    ]
    assert not orphaned, (
        f"the expected claim is not among the permitted claims: {orphaned}. The agent "
        "is shown the list and cannot answer with something that is not on it."
    )


def test_no_situation_names_an_act():
    """The other field the agent is shown.

    `probe_for` puts the situation verbatim. An act word there primes exactly as one in
    the options does, and this was clean when the ruling was made - asserted so it stays
    that way rather than being rediscovered by another measurement.
    """
    naming = []
    loaded = sc.load_all()
    for module_id in GREENSTONE:
        for scenario_class, occasions in loaded.for_module(module_id).scenarios.items():
            for i, authored in enumerate(occasions):
                found = sorted({m.group(0) for m in _ACT_WORD.finditer(authored.situation)})
                if found:
                    naming.append((f"{module_id}/{scenario_class}[{i}]", found))
    assert not naming, f"these situations name an act: {naming}"


@pytest.mark.parametrize(
    ("module_id", "scenario_class", "ordinal", "claim", "options"),
    [
        ("buyer_match", "malformed_input", 0, "NOT A UUID",
         ["ACCEPTED", "NOT A UUID", "NO SUCH DEAL"]),
        ("buyer_match", "malformed_input", 1, "NO SUCH DEAL",
         ["ACCEPTED", "NOT A UUID", "NO SUCH DEAL"]),
        ("comp_analysis", "malformed_input", 0, "NOT A UUID",
         ["ACCEPTED", "NOT A UUID"]),
        ("property_lookup", "happy_path", 1, "ACCEPTED",
         ["ACCEPTED", "EMPTY"]),
        ("property_lookup", "malformed_input", 0, "EMPTY",
         ["ACCEPTED", "EMPTY"]),
    ],
)
def test_the_five_corrected_keys_carry_exactly_this(
    module_id, scenario_class, ordinal, claim, options
):
    """Pinned by value, because the fact must be identical to what Ivan approved.

    The correction removed a word and changed no fact: the service said `deal_id must
    be a UUID`, so the claim is that it is not a UUID. The act it prompted for was
    never the act the key expects.
    """
    answer = sc.load_all().for_module(module_id).scenarios[scenario_class][ordinal]
    assert answer.expected_answer["record_claim"] == claim
    assert answer.expected_answer["record_claim_options"] == options


def test_the_five_are_still_approved_and_not_re_approved():
    """**A correction to Ivan's own ruling is not a new approval.**

    The keys keep `approved_by` and `approved_on` from 18 September. Moving the date
    would say he read 44 scenarios again on the day five words were removed, and
    `approved_on` exists precisely so that claim cannot be made loosely (entry 126).
    """
    loaded = sc.load_all()
    for module_id in GREENSTONE:
        content = loaded.modules[module_id]
        assert content.status == sc.APPROVED
        assert content.approved_by == "Ivan Green"
        assert content.approved_on == "2026-09-18"
