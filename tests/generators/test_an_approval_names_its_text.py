"""An approval records the hash of the text it covers, and a stale one refuses to load.

RULED 20 SEPTEMBER 2026 (entry 141)
===================================

    *"An approval records the content hash of the text approved, beside `approved_by`
    and `approved_on`. Two approvals of different text must never read alike, and an
    approval whose hash no longer matches its file is stale. The date says when; the
    hash says what."*

WHAT THE DATE COULD NOT DO
==========================

    `approved_on` was added in entry 126 so two approvals of one key could be told
    apart. It has DAY resolution, and on 20 September that was not enough: Ivan approved
    `property_lookup` twice that day - once on the pre-spec text, once on the text the
    first operation spec obliged - and both read `2026-09-20`. Entry 140 recorded that
    the field could not separate them unaided. This is the answer.

WHY NOT A TIMESTAMP
===================

    A timestamp separates the two and says nothing about what changed. The hash answers
    the question a reader actually has - **is this approval still about the text in front
    of me** - and fails loudly when it is not, rather than carrying a signature over prose
    nobody read.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_re_tagging_does_not_invalidate_an_approval`. Every other test here demands the
    hash or refuses a mismatch, and a hash taken over the whole file would satisfy all of
    them while invalidating three approvals the next time somebody wrote a comment.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from generators import scenario_content as sc

GREENSTONE = (
    "assign_contract", "buyer_match", "comp_analysis", "property_lookup",
    "underwrite_deal",
)

_BODY = """
scenarios:
  - scenario_class: happy_path
    derivation: reproducible
    situation: A caller asks for a thing and the module returns it.
    expected_behavior: Report what came back and nothing further.
    what_to_say: None fires; the call answered completely.
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


def _hash_of(body: str = _BODY) -> str:
    """The hash the loader will compute for `body`, via a draft that skips the check."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "thing.yaml"
        path.write_text(
            "module_id: thing\nforge_id: cre-forge\nstatus: draft\n" + body,
            encoding="utf-8",
        )
        loaded = sc.load_module(path)
    return sc.approved_content_hash(loaded.scenarios, loaded.not_applicable)


def _approved(body: str = _BODY, *, hash_: str | None = None) -> str:
    return (
        'module_id: thing\nforge_id: cre-forge\nstatus: approved\n'
        'approved_by: "Ivan Green"\napproved_on: "2026-09-20"\n'
        f'approved_content_hash: "{hash_ if hash_ is not None else _hash_of(body)}"'
    )


# ------------------------------------------------------------------ the loader's rules

def test_an_approved_key_with_no_hash_is_refused(tmp_path):
    """The date alone is what entry 140 found insufficient."""
    path = _write(tmp_path, (
        'module_id: thing\nforge_id: cre-forge\nstatus: approved\n'
        'approved_by: "Ivan Green"\napproved_on: "2026-09-20"'
    ))
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "approved_content_hash" in str(refused.value)


def test_a_draft_carrying_a_hash_is_refused(tmp_path):
    """A hash beside a draft names text nobody approved - the same rule the name and
    the date already follow."""
    path = _write(tmp_path, (
        "module_id: thing\nforge_id: cre-forge\nstatus: draft\n"
        f'approved_content_hash: "{_hash_of()}"'
    ))
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "draft" in str(refused.value)


def test_a_matching_hash_loads(tmp_path):
    """The positive case, so none of the refusals above is satisfied by refusing all."""
    content = sc.load_module(_write(tmp_path, _approved()))
    assert content.status == sc.APPROVED
    assert content.approved_content_hash == _hash_of()


def test_edited_text_under_an_old_hash_is_refused(tmp_path):
    """**The whole point.** A file changed after approval stops loading.

    Not a warning and not a silent reload: a stale approval reads as a signature over
    prose the signer never saw, which is worse than no approval at all.
    """
    edited = _BODY.replace(
        "Report what came back and nothing further.",
        "Report what came back, and also estimate what it implies.",
    )
    path = _write(tmp_path, _approved(hash_=_hash_of()), edited)
    with pytest.raises(sc.ScenarioContentError) as refused:
        sc.load_module(path)
    assert "changed after it was approved" in str(refused.value)
    assert "editing the hash to match" in str(refused.value)


def test_a_changed_declared_absence_is_caught_too(tmp_path):
    """`not_applicable` is text a module is graded against - entry 129 put it in the
    exam's identity for the same reason, and an approval covers it."""
    edited = _BODY.replace(
        "This Forge cannot return 429 on a module call.",
        "The limiter is configured and never installed.",
    )
    path = _write(tmp_path, _approved(hash_=_hash_of()), edited)
    with pytest.raises(sc.ScenarioContentError):
        sc.load_module(path)


# --------------------------------------------------------- what must NOT move the hash

def test_re_tagging_does_not_invalidate_an_approval(tmp_path):
    """**The test that keeps this a hash of the TEXT rather than of the file.**

    Entry 137 tagged all 44 scenarios `reproducible` or `constructed` and moved nobody's
    approval, because a tag says how a scenario was derived and not what it grades. A
    hash over the whole file would have invalidated three approvals for that change - and
    would invalidate one for a comment.
    """
    retagged = _BODY.replace("derivation: reproducible", "derivation: constructed")
    content = sc.load_module(_write(tmp_path, _approved(hash_=_hash_of()), retagged))
    assert content.scenarios["happy_path"][0].derivation == sc.CONSTRUCTED


def test_a_draft_note_does_not_move_the_hash(tmp_path):
    """Authoring commentary, not graded text."""
    noted = _BODY.replace(
        "    what_to_say: None fires; the call answered completely.\n",
        "    what_to_say: None fires; the call answered completely.\n"
        "    draft_note: Q4 ruled this shape; recorded for the next author.\n",
    )
    sc.load_module(_write(tmp_path, _approved(hash_=_hash_of()), noted))


# ------------------------------------------------------------ the five, as they stand

def test_every_greenstone_approval_matches_its_text():
    """Backfilled 20 September from the text each one covers now.

    All five, and **a draft's absence of a hash is asserted rather than skipped** - a
    draft carrying an approval hash is exactly the stale approval entry 141 exists to
    refuse, and it would be invisible to a loop that only checked the approved ones. The
    branch is unreachable today and stays, because it was reachable on 21 September and
    will be again.
    """
    loaded = sc.load_all()
    checked = 0
    for module_id in GREENSTONE:
        content = loaded.modules[module_id]
        if content.status != sc.APPROVED:
            assert not content.approved_content_hash, (
                f"{module_id} is a draft and records an approval hash"
            )
            continue
        assert content.approved_content_hash, f"{module_id} records no hash"
        assert content.approved_content_hash == sc.approved_content_hash(
            content.scenarios, content.not_applicable
        )
        checked += 1
    assert checked == 5, f"expected five approved Greenstone keys, checked {checked}"


def test_no_two_approvals_read_alike():
    """**The case that produced the ruling, asserted over whatever is approved now.**

    `buyer_match` and `property_lookup` were both approved on 20 September, and the date
    could not tell them apart - which is what entry 140 found and what the hash answers.
    `property_lookup` went back to draft on the 21st, so that exact pair no longer
    exists; pinning the test to it would have made it pass by having nothing to compare.

    So it asserts the property rather than the incident: **no two approved keys share a
    hash**, on any date. That is the claim the ruling makes, and it survives the next key
    going to draft as well as this one did not.
    """
    loaded = sc.load_all()
    approved = [
        loaded.modules[m] for m in GREENSTONE
        if loaded.modules[m].status == sc.APPROVED
    ]
    assert len(approved) >= 2, "fewer than two approvals; nothing to compare"
    hashes = [c.approved_content_hash for c in approved]
    assert len(set(hashes)) == len(hashes), (
        "two approved keys carry the same content hash: "
        f"{sorted(c.module_id for c in approved)}"
    )
