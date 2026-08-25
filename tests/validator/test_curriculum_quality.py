"""Whether a curriculum teaches anything, as opposed to merely existing.

`authored` meant a row exists and no section is empty. The live cre-forge curriculum
passes that test with `"what_it_does": "Documented."`, `"inputs": {"a": "b"}` and
`"correct_sequence": ["a", "b"]` - eight sections present, none empty, a valid
`content_hash` over the lot, and 234 certifications across the portfolio bound to those
hashes.

A hash of the word "Documented." is a valid hash of nothing. Every certification bound to
it inherits that emptiness: the agents read as certified to operate a module nobody has
described, and nothing in the system disagreed.

These tests pin the detection rules in one place, because three readers depend on the
same answer - the console renders it, V11 refuses a Pack on it, and the compliance page
counts it. A screen that decided for itself what "thin" meant would eventually disagree
with the rule that blocks a release.
"""

from __future__ import annotations

import pytest

from broker.curriculum_quality import SECTION_ORDER, assess, assess_section


def complete_curriculum() -> dict[str, object]:
    """A curriculum that actually teaches the module. The control for every case below."""
    return {
        "what_it_does": (
            "Matches a property against the buyer network and returns ranked buyers "
            "with the criteria each one matched on."
        ),
        "what_it_does_not_do": (
            "Does not contact buyers, does not reserve or assign a deal, and does not "
            "write anything to the CRM."
        ),
        "inputs": {
            "property_id": "The subject property; must already exist in the CRE Forge.",
            "max_results": "How many ranked buyers to return. Defaults to ten.",
        },
        "correct_sequence": [
            "Confirm the property exists and is not already assigned.",
            "Call buyer_match with the property id.",
            "Read the ranked list; do not act on it in this module.",
        ],
        "failure_signatures": {
            "silent_partial": "Fewer buyers than max_results with no error - the index is stale.",
            "rate_limited": "429 with Retry-After. The network is throttling, not empty.",
            "not_found": "404 means the property id is wrong, not that no buyer matched.",
        },
        "retry_vs_escalate": (
            "Retry a 5xx twice with backoff. Escalate any 4xx to a human - a 4xx means "
            "the request was wrong and repeating it will not help."
        ),
        "never_do": [
            "Never re-submit after a 200.",
            "Never present a ranked buyer as an assigned buyer.",
        ],
        "compliance_coupling": ["tsr_disclosure_required"],
    }


def test_a_complete_curriculum_reads_as_complete():
    result = assess(complete_curriculum())
    assert result["state"] == "complete"
    assert result["complete"] == result["total"] == len(SECTION_ORDER)
    assert result["teaches_nothing"] is False


# ============================================ THE ONE THAT MATTERS MOST

def test_the_live_curriculum_is_not_authored():
    """The exact content in the database, which the page badged `authored`.

    If this ever reads as complete, the console is back to calling a hash of the word
    "Documented." an authored curriculum, and 234 certifications go back to resting on
    it silently.
    """
    live = {
        "inputs": {"a": "b"},
        "never_do": ["Never re-submit after a 200"],
        "what_it_does": "Documented.",
        "correct_sequence": ["a", "b"],
        "retry_vs_escalate": "Retry 5xx twice; escalate 4xx.",
        "failure_signatures": {"silent_partial": "short result"},
        "compliance_coupling": ["tsr_disclosure_required"],
        "what_it_does_not_do": "Documented.",
    }
    result = assess(live)

    assert result["state"] == "stub"
    assert result["teaches_nothing"] is True
    assert set(result["placeholder_sections"]) == {
        "what_it_does",
        "what_it_does_not_do",
        "inputs",
        "correct_sequence",
    }
    # And the reason names the defect rather than saying "invalid".
    what_it_does = next(
        s for s in result["sections"] if s["section"] == "what_it_does"
    )
    assert "Documented." in what_it_does["reason"]


@pytest.mark.parametrize(
    "value",
    ["Documented.", "documented", "TODO", "TBD", "PENDING_AUTHORING", "N/A", "-", "  "],
)
def test_placeholder_prose_is_a_stub(value: str):
    """Ways of not writing the section. Compared case-insensitively after stripping."""
    assert assess_section("what_it_does", value)["state"] == "stub"


def test_metasyntactic_keys_are_a_stub():
    """`inputs: {a: b}` documents the shape of a dictionary, not any input's meaning."""
    result = assess_section("inputs", {"a": "b"})
    assert result["state"] == "stub"
    assert "shape of a dictionary" in result["reason"]


def test_a_list_of_single_characters_is_a_stub():
    result = assess_section("correct_sequence", ["a", "b"])
    assert result["state"] == "stub"
    assert "single character" in result["reason"]


def test_short_prose_is_thin_rather_than_a_stub():
    """Real words, not enough of them. A different problem from a placeholder, and it
    needs a different response - so it is a warning rather than a failure."""
    result = assess_section("retry_vs_escalate", "Retry twice.")
    assert result["state"] == "thin"
    assert "characters" in result["reason"]


def test_one_failure_signature_is_thin():
    """The 4xx, timeout and rate-limit cases are the ones an operator meets."""
    result = assess_section("failure_signatures", {"silent_partial": "short result"})
    assert result["state"] == "thin"
    assert "4xx" in result["reason"]


def test_a_missing_section_is_distinct_from_a_stub():
    """Different work: one was never written, the other was filled in with a word that
    means 'not yet'."""
    curriculum = complete_curriculum()
    del curriculum["failure_signatures"]

    result = assess(curriculum)
    assert result["state"] == "missing"
    assert result["missing_sections"] == ["failure_signatures"]
    assert result["teaches_nothing"] is True


def test_thin_does_not_block_but_stub_does():
    """`thin` is real content that does not go far enough; `stub` is not content.

    Only one of them may stop a release, and confusing the two would either block work
    on a short-but-honest sentence or let a placeholder through.
    """
    thin = complete_curriculum()
    thin["failure_signatures"] = {"only_one": "The index goes stale and returns fewer."}
    assert assess(thin)["state"] == "thin"
    assert assess(thin)["teaches_nothing"] is False

    stub = complete_curriculum()
    stub["what_it_does"] = "TODO"
    assert assess(stub)["teaches_nothing"] is True


def test_every_required_section_is_assessed():
    """All eight, whatever the content. A section nobody assesses is a section that can
    quietly become a placeholder."""
    result = assess({})
    assert [s["section"] for s in result["sections"]] == list(SECTION_ORDER)
    assert result["state"] == "missing"
    assert len(result["missing_sections"]) == len(SECTION_ORDER)


def test_the_console_and_the_validator_agree():
    """The shared cases in `tests/fixtures/curriculum_cases.json`.

    These rules exist twice - here, and in `console/lib/curriculum.ts` so the authoring
    form can grey out Publish as somebody types. Two implementations of one rule drift,
    and the drift is worse than usual: the form would say a section is fine and the
    server would reject the save, or the form would say it is a stub and the server would
    take it.

    Neither side owns the cases. The console's vitest suite reads the same file.
    """
    import json
    from pathlib import Path

    cases = json.loads(
        (Path(__file__).resolve().parents[1] / "fixtures" / "curriculum_cases.json")
        .read_text(encoding="utf-8")
    )["cases"]

    assert len(cases) > 10, "the shared case file is too small to pin anything"

    for case in cases:
        actual = assess_section(case["section"], case["value"])["state"]
        assert actual == case["state"], (
            f"{case['name']}: Python says {actual}, the shared case says "
            f"{case['state']}. If the rule changed, change it in both places and update "
            f"the case."
        )
