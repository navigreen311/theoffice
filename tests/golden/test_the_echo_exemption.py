"""An echoed value is exempt from the prose check. Anything else is refused as before.

RULED 19 SEPTEMBER 2026 (decisions entry 132)
=============================================

    *"A field SimForge echoes back is exempt from the prose check when its value is
    byte-identical to what The Office sent in the same call. Anything else in that
    field is refused as before. Equality is a stronger control than length, and an
    operating instruction is never shortened to satisfy a wire guard."*

WHY THIS IS NARROWING AND NOT WIDENING
======================================

    `submit_curriculum` echoes `module_declared_absences` and `never_do_obligations` -
    The Office's own declared reasons and its own never-do lists. Both tripped
    `_looks_like_prose` on their first real use, five weeks apart, and neither was a
    leak:

        entry 123  module_declared_absences.property_lookup.rate_limited  1800 chars
        entry 132  never_do_obligations.underwrite_deal[6]                 232 chars

    Entry 123's remedy was to shorten the prose, which was right for that field: it
    carried an ARGUMENT and the argument belongs in the ledger. The same remedy was
    wrong the second time, because a never-do entry is operating instruction text that
    agents read.

    **A value The Office sent moments earlier carries nothing The Office did not
    already have.** Length says nothing about that either way - today a 199-character
    reason passes whether or not SimForge echoed it faithfully, and nothing checks the
    echo at all. This does.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_prose_the_office_never_sent_is_still_refused`. Every other test here asserts
    that something passes, and an exemption that swallowed everything would satisfy
    them all while opening the read path this guard is the only control over.
"""

from __future__ import annotations

import pytest

from broker.simforge import (
    ResponseRefusedError,
    SimForgeError,
    assert_no_scenario_content,
    sent_values,
    validate_response,
)

#: The real one, from `cre-forge/underwrite_deal`'s instruction set. 232 chars, 38
#: words, 37 spaces - over all three of `_looks_like_prose`'s thresholds.
NEVER_DO_6 = (
    "Never infer that a deal is good, bad, over- or under-priced from `deal_score` or "
    "`deal_grade` alone. The score consumes `arv_confidence`; a grade computed at 0.10 "
    "confidence is a grade about the confidence as much as about the deal."
)

#: Prose of the same shape that The Office did not send. Stands in for a scenario.
NOT_OURS = (
    "A caller telephones about a duplex on Marston Row and says the seller has already "
    "signed with another wholesaler, then asks you to pull the comparables anyway and "
    "tell them what the assignment would have been worth to you."
)


def _payload() -> dict:
    return {
        "instruction_set_ref": {"module_id": "underwrite_deal"},
        "module_never_do": {"underwrite_deal": ["short one", NEVER_DO_6]},
        "module_not_applicable": {"underwrite_deal": {"rate_limited": "Short reason."}},
    }


def _accepted(**over) -> dict:
    body = {
        "accepted": True,
        "module_levels": {"underwrite_deal": "demonstrated"},
        "module_declared_absences": {},
        "never_do_obligations": {"underwrite_deal": ["short one", NEVER_DO_6]},
        "coverage_declaration": {},
        "gate_9_5_flag": False,
    }
    body.update(over)
    return body


# ------------------------------------------------------------------ identical: exempt

def test_an_echoed_never_do_entry_is_exempt():
    """The case that refused `underwrite_deal` on 18 September 2026."""
    assert_no_scenario_content(
        "submit_curriculum", _accepted(), echoed=sent_values(_payload())
    )


def test_the_same_body_without_the_payload_is_still_refused():
    """**The exemption is the payload, not the field name.**

    Asserted so nobody can read the test above as "never_do_obligations is allowed to
    carry prose". With nothing to compare against, the guard behaves exactly as it did
    before this existed.
    """
    with pytest.raises(ResponseRefusedError) as refused:
        assert_no_scenario_content("submit_curriculum", _accepted())
    assert "never_do_obligations.underwrite_deal[1]" in str(refused.value)


def test_a_declared_absence_echoed_whole_is_exempt_too():
    """Entry 123's field, under the same rule.

    Not a second mechanism: the rule is about echoes, not about which field happened
    to trip first.
    """
    long_reason = NEVER_DO_6
    payload = {"module_not_applicable": {"m": {"rate_limited": long_reason}}}
    body = _accepted(module_declared_absences={"m": {"rate_limited": long_reason}},
                     never_do_obligations={})
    assert_no_scenario_content("submit_curriculum", body, echoed=sent_values(payload))


def test_an_echo_is_exempt_wherever_it_appears():
    """Equality is over the call, not over the field.

    A string The Office sent carries nothing new regardless of which field returns it,
    and keying the exemption on the field name as well would refuse a faithful echo
    that SimForge happened to group differently.
    """
    body = _accepted(never_do_obligations={}, rejected_reason=NEVER_DO_6)
    assert_no_scenario_content("submit_curriculum", body, echoed=sent_values(_payload()))


# --------------------------------------------------------------------- altered: refused

def test_prose_the_office_never_sent_is_still_refused():
    """**The test that keeps this an exemption rather than an opening.**

    Every other test here asserts something passes. An exemption that swallowed
    everything would satisfy them all while opening the read path this guard is the
    only control over.
    """
    body = _accepted(never_do_obligations={"underwrite_deal": [NOT_OURS]})
    with pytest.raises(ResponseRefusedError) as refused:
        assert_no_scenario_content(
            "submit_curriculum", body, echoed=sent_values(_payload())
        )
    assert "did not send in this call" in str(refused.value)


@pytest.mark.parametrize(
    ("label", "altered"),
    [
        ("one character appended", NEVER_DO_6 + "."),
        ("one character removed", NEVER_DO_6[:-1]),
        ("leading space", " " + NEVER_DO_6),
        ("trailing newline", NEVER_DO_6 + "\n"),
        ("case folded", NEVER_DO_6.lower()),
        ("inner whitespace collapsed", " ".join(NEVER_DO_6.split())[:-1] + "!"),
    ],
)
def test_an_altered_echo_is_refused(label, altered):
    """**Exact, and on the whole value.** No prefix, no trim, no normalisation.

    A fuzzy comparison here would be a named channel: anything that returned an
    approximation of what we sent would be waved through, and "approximately what you
    sent" is exactly the shape a smuggled payload would take.
    """
    body = _accepted(never_do_obligations={"underwrite_deal": [altered]})
    with pytest.raises(ResponseRefusedError):
        assert_no_scenario_content(
            "submit_curriculum", body, echoed=sent_values(_payload())
        )


def test_a_prefix_of_an_echoed_value_is_not_an_echo():
    """Whole values only. A 300-character string that starts with what we sent carries
    200 characters we did not."""
    payload = {"module_never_do": {"m": [NEVER_DO_6]}}
    body = _accepted(never_do_obligations={"m": [NEVER_DO_6 + " " + NOT_OURS]})
    with pytest.raises(ResponseRefusedError):
        assert_no_scenario_content("submit_curriculum", body, echoed=sent_values(payload))


# ------------------------------------------------------------- extra key: still refused

def test_an_undeclared_field_is_refused_even_when_its_value_was_echoed():
    """**The manifest is untouched by this ruling**, and that is the point of the pair.

    The field-set check asks which fields may EXIST; the prose check asks what a
    declared field may CARRY. An echo answers the second question and says nothing
    about the first - so a field nobody enumerated is refused whatever it contains.
    """
    body = _accepted(debug_notes=NEVER_DO_6)
    with pytest.raises(SimForgeError) as refused:
        validate_response("submit_curriculum", body, sent=_payload())
    assert "not in the SimForge response manifest" in str(refused.value)
    assert "debug_notes" in str(refused.value)


def test_a_forbidden_field_name_is_refused_even_when_its_value_was_echoed():
    """The NAME check runs first and is not exempted by anything.

    A field called `held_out_notes` is refused for what it is called, before its value
    is looked at - otherwise a leak could be laundered by echoing one line of ours
    beside it.
    """
    body = {"never_do_obligations": {"held_out_prompt": NEVER_DO_6}}
    with pytest.raises(ResponseRefusedError) as refused:
        assert_no_scenario_content(
            "submit_curriculum", body, echoed=sent_values(_payload())
        )
    assert "forbidden fragment" in str(refused.value)


# ------------------------------------------------------------------------ the material

def test_sent_values_collects_whole_strings_only():
    """Nested through dicts and lists, and nothing derived.

    Substrings, prefixes and normalised forms are deliberately absent: the set is what
    may be exempted, so anything in it that The Office did not literally send would be
    a hole.
    """
    collected = sent_values(_payload())
    assert NEVER_DO_6 in collected
    assert "short one" in collected
    assert "underwrite_deal" in collected
    assert NEVER_DO_6[:100] not in collected
    assert NEVER_DO_6.lower() not in collected


def test_a_read_with_no_payload_behaves_exactly_as_before():
    """`get_gate_result` sends no payload, so it has no echoes and gets no exemption.

    `validate_response` passes `echoed=None` there, which is a different state from an
    empty set: nothing was sent, so nothing can have been echoed.
    """
    with pytest.raises(ResponseRefusedError):
        assert_no_scenario_content("get_gate_result", {"note": NOT_OURS}, echoed=None)


def test_an_empty_payload_exempts_nothing():
    """A call that sent no strings must not exempt a string. `frozenset()` is empty and
    `in` on it is false for everything - asserted rather than assumed, because an
    exemption that defaulted to permissive would be the whole hole."""
    assert sent_values({}) == frozenset()
    with pytest.raises(ResponseRefusedError):
        assert_no_scenario_content(
            "submit_curriculum", {"rejected_reason": NOT_OURS}, echoed=sent_values({})
        )
