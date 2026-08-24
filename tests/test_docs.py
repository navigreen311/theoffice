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

import re
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
