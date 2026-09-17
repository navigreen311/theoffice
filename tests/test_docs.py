"""O11 - a gap list that is wrong is worse than no gap list.

Four `## Known gaps` sections described a system that had not existed for several
phases: `call-path.md` said Vault was unimplemented and trust tiers were "recorded, not
enforced" - both false; `certification.md` said the authoring UI did not exist - it did.
Each was accurate when written, and nothing swept it afterwards.

That is the same rot Gate 6's hardcoded knowledge-base list had, in prose. It sends a
reader either to build something that already exists or to trust something that does
not, and the second is the expensive one.

This does not check that the gaps are *true* - no test can. It checks that every list
carries the date somebody last looked, so a reader can weigh it, and that the ones this
increment corrected have not silently returned.
"""

from __future__ import annotations

import os
import re
import subprocess
from itertools import pairwise
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
GAP_HEADING = "## Known gaps"
VERIFIED = re.compile(r"\*Last verified: (\d{4}-\d{2}-\d{2})\.\*")


def docs_with_gap_lists() -> list[Path]:
    return sorted(
        p for p in DOCS.glob("*.md") if GAP_HEADING in p.read_text(encoding="utf-8")
    )


def test_there_are_gap_lists_to_check():
    """A meta-test that finds nothing passes for the wrong reason."""
    assert len(docs_with_gap_lists()) >= 8


@pytest.mark.parametrize(
    "doc", docs_with_gap_lists(), ids=lambda p: p.name
)
def test_every_gap_list_says_when_it_was_last_verified(doc: Path):
    """The date is the point.

    An undated gap list is read as current, because there is nothing to read it as
    instead. A dated one that is nine months old is still wrong and is *visibly* wrong,
    which is the whole difference.
    """
    text = doc.read_text(encoding="utf-8")
    section = text.split(GAP_HEADING, 1)[1]
    match = VERIFIED.search(section[:400])
    assert match, (
        f"{doc.name} has a gap list with no `*Last verified: YYYY-MM-DD.*` line. The "
        "increment that changes behaviour is the increment that updates the list; the "
        "date is what lets a reader tell whether that happened."
    )


# The specific claims this increment corrected. Each was true once, and each would be a
# regression rather than a rewrite if it came back.
RETIRED_CLAIMS = [
    ("docs/call-path.md", "Vault is not implemented"),
    ("docs/call-path.md", "trust_tier` is recorded, not enforced"),
    ("docs/call-path.md", "**No rate limiting.**"),
    ("docs/certification.md", "The authoring UI does not exist"),
    ("docs/generators.md", "Nothing runs the pipeline in production"),
    ("docs/governance.md", "Manifest rows are hand-inserted"),
    # B41. This one was never true - the Library held seventeen entries on the day it
    # was committed, nine days before the sentence was written. It is listed here for
    # the same reason as the five above: the sentence told an agent that a control it
    # could read did not exist, and `outbound-contact-boundary-v1` is a gate that
    # forbids sends these modules would otherwise make. A claim that a control is absent
    # is worse than silence, because silence invites a look.
    #
    # Matched on the second sentence rather than the first. The correction paragraph now
    # standing in that file quotes the retracted claim in order to retract it, so a
    # pattern on "the Compliance Library ships empty" would fail on the fix.
    (
        "docs/instructions/funnelforge-approved-send-rules.md",
        "No entry is committed anywhere in this repository",
    ),
]


@pytest.mark.parametrize(("doc", "claim"), RETIRED_CLAIMS)
def test_a_corrected_claim_does_not_come_back(doc: str, claim: str):
    """Each of these described the system accurately at some point.

    They are listed by exact text rather than by summary so that this fails on the
    sentence returning, and does not fail on somebody writing a *new* gap that happens
    to mention Vault.
    """
    text = (DOCS.parent / doc).read_text(encoding="utf-8")
    assert claim not in text, (
        f"{doc} claims {claim!r} again. That was true once and is not now - check "
        "whether the capability regressed before re-adding the sentence."
    )


# --------------------------------------------------------------- the ledger numbering

DECISIONS = DOCS / "decisions.md"

#: What a PR writes instead of a number. Ruled by Ivan Green, 17 September 2026:
#: **entry numbers are assigned at merge, not at authoring.**
PLACEHOLDER = "## NEXT."

#: `## 116. A venture needs an answer key` -> 116. Anchored, because `## 3.5` appears in
#: prose inside several entries and a loose pattern would read gate numbers as entries.
ENTRY_HEADING = re.compile(r"^## (\d+)\. ", re.MULTILINE)

#: The placeholder AS A HEADING. Anchored for a second reason: the rule has to be
#: described somewhere, and the entry that records it necessarily writes `## NEXT.` in
#: prose several times. Counting every occurrence would make the rule's own entry the
#: thing that fails the rule, and main could never be clean.
PLACEHOLDER_HEADING = re.compile(r"^## NEXT\. ", re.MULTILINE)


def entry_numbers() -> list[int]:
    return [int(m) for m in ENTRY_HEADING.findall(DECISIONS.read_text(encoding="utf-8"))]


def test_entry_numbers_are_unique():
    """**The one that would have caught it.**

    On 17 September 2026 three open PRs claimed entry 115 and two claimed 116. Nothing
    failed, and nothing could have: each PR appends to the END of this file with
    different surrounding context, so two branches adding `## 116.` merge cleanly and
    main ends up holding two of them. Git has no opinion about the number in a heading.

    This runs against the MERGE RESULT on every pull request - which is what GitHub
    checks out for a `pull_request` event - so the second PR to claim a number fails
    before it lands rather than after.
    """
    numbers = entry_numbers()
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    assert not duplicates, (
        f"docs/decisions.md has more than one entry numbered {duplicates}. Two branches "
        "claimed the same number and git merged them cleanly because they appended in "
        "different places. Renumber the later one - see the numbering rule in the "
        "ledger."
    )


def test_entry_numbers_are_contiguous_from_one():
    """A gap is the other half of a collision, and it is the quieter half.

    A PR that claims 117 while main is at 115 merges just as cleanly as one that claims
    115 twice. Nothing is duplicated and nothing is lost, but every reference to "entry
    116" afterwards points at nothing, and the absence reads as an entry somebody
    deleted rather than one nobody wrote.

    Contiguity is also what makes `## NEXT.` work: the number to assign is always
    `max + 1`, with no register to consult and nothing to remember.
    """
    numbers = entry_numbers()
    assert numbers, "no entries found; the heading pattern no longer matches the file"
    expected = list(range(1, len(numbers) + 1))
    missing = sorted(set(expected) - set(numbers))
    assert sorted(numbers) == expected, (
        f"docs/decisions.md is not contiguous from 1. Missing: {missing or 'none'}; "
        f"highest: {max(numbers)}; count: {len(numbers)}."
    )


def test_entries_are_in_order():
    """Numbered in the order they appear, so the file reads as a sequence.

    Sorting is not enough on its own: a file holding 1..119 in a shuffled order would
    satisfy both tests above and still send a reader hunting.
    """
    numbers = entry_numbers()
    assert numbers == sorted(numbers), (
        "docs/decisions.md entries are out of order. The first descent is at "
        f"{next((b for a, b in pairwise(numbers) if b < a), None)}."
    )


def _checkout_is_main() -> bool:
    """Whether the thing being tested IS main, asked three ways in priority order.

    `GITHUB_BASE_REF` is set on a `pull_request` event and empty on a push, so it is the
    first and most reliable signal: a PR is never main, whatever it is merging into.
    `GITHUB_REF` then names the branch on a push. Off CI there is neither, so the branch
    is read from git.

    **Unknown resolves to "not main", which skips the check.** A wrong skip is a rule
    enforced one run later, by the push to main that follows; a wrong assertion is every
    developer on every branch red for writing the placeholder the rule tells them to
    write. The asymmetry is the whole reason this function exists rather than one
    environment variable.
    """
    if os.environ.get("GITHUB_BASE_REF"):
        return False
    ref = os.environ.get("GITHUB_REF")
    if ref:
        return ref == "refs/heads/main"
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10,
            cwd=DECISIONS.parent,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return branch.returncode == 0 and branch.stdout.strip() == "main"


def test_no_placeholder_reaches_main():
    """`## NEXT.` is a number nobody has assigned yet, and main holds no such thing.

    **This half deliberately does not run on a pull request**, and that is the rule
    working rather than a hole in it. A PR is SUPPOSED to carry `## NEXT.` - that is
    what stops two branches claiming one number - so a check that fired there would fail
    every PR on the one property it is meant to have.

    The window is therefore between a merge and the push-to-main run that follows it.
    What closes that window is the other half of the rule, which is a person: whoever
    merges assigns the number. **This test catches them forgetting; it is not what stops
    them.** Said plainly because a test named like this one invites the opposite
    reading.
    """
    if not _checkout_is_main():
        pytest.skip("not main: `## NEXT.` is expected on a branch, and is the point")

    text = DECISIONS.read_text(encoding="utf-8")
    count = len(PLACEHOLDER_HEADING.findall(text))
    assert count == 0, (
        f"{count} entry heading(s) still read `{PLACEHOLDER}`. The number is assigned "
        f"at merge: replace each with the next free number ({max(entry_numbers() or [0]) + 1} "
        "and upward, in the order they appear)."
    )


def test_the_placeholder_is_what_the_rule_says_it_is():
    """The constant above and the ledger's own words, asserted against each other.

    A rule recorded in prose and enforced by a constant is two spellings of one thing,
    and this is the test that keeps them in step. If the ledger ever says the
    placeholder is something else, this fails rather than the enforcement quietly
    checking for a string nobody writes any more.
    """
    text = DECISIONS.read_text(encoding="utf-8")
    assert f"`{PLACEHOLDER}`" in text, (
        f"no entry in docs/decisions.md mentions `{PLACEHOLDER}`. Either the rule was "
        "never recorded or the placeholder changed and this check now enforces a string "
        "nobody uses."
    )
