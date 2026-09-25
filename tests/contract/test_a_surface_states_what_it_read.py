"""A surface states what it read, never what was true when it was written.

RULED 24 SEPTEMBER 2026 (decisions entry 185)
=============================================

    *"A surface states what it read, never what was true when it was written. The Gate
    9.5 ceiling block on both provisioning pages is static prose from ~15 September,
    asserting the partition does not exist while the endpoint returns PASS. Read the
    gate or say nothing."*

WHAT IT SAID, AND HOW LONG IT HAD BEEN WRONG
============================================

    `console/app/provisioning/page.tsx` carried a fixed block whose own subtitle was
    the confession: *"Stated here rather than discovered at the gate."* It said
    SimForge's held-out partition did not exist yet - true when it was written, and
    still on the page on 24 September while `gate_9_5_verdict` answered
    `partition_exists: true, verdict: PASS`.

    Nothing connected them. It was not cached and not stale data: **Gate 9.5 has never
    run** - zero rows in `provisioning_gate_result` for that gate, on any run, ever -
    so there was nothing to cache. The page was not asking and the gate was not
    reached.

THE THREE SHAPES, AND WHY NONE MAY BORROW ANOTHER
=================================================

    read: false                        nobody could ask. Entry 177's rule.
    partition_exists: false            the deployment ceiling.
    partition_exists: true + verdict   the gate answered. PASS clears it; a FAIL is a
                                       failure AT the gate, not a ceiling.
"""

from __future__ import annotations

import pytest

from broker import provisioning

pytestmark = pytest.mark.anyio

UNREADABLE = {"read": False, "reason": "could not reach SimForge: ConnectError"}
ABSENT = {"read": True, "partition_exists": False, "verdict": None}
PASSED = {"read": True, "partition_exists": True, "verdict": "PASS"}
FAILED = {"read": True, "partition_exists": True, "verdict": "FAIL"}


def _ladder(held_out):
    return provisioning.ladder_for([], "4", "running", held_out=held_out)


def _gate(rows, gate="9.5"):
    return next(r for r in rows if r["gate"] == gate)


# ======================================================== the ruling

def test_an_absent_partition_is_the_only_thing_that_draws_a_ceiling():
    """**THE RULING.** The claim is made when it is read, and not otherwise."""
    assert _gate(_ladder(ABSENT))["is_ceiling"] is True


def test_a_verdict_is_not_a_ceiling():
    """The state the page was wrong about for nine days.

    A partition that exists and answers means the gate is reachable. PASS clears it.
    """
    assert _gate(_ladder(PASSED))["is_ceiling"] is False


def test_a_fail_is_a_failure_at_the_gate_and_still_not_a_ceiling():
    """`CEILING_GATE`'s own comment required this before anything read it:

    *"a held-out verdict of FAIL is a real failure at the same gate, and reading the
    two the same way would report a venture that failed adversarial testing as merely
    waiting for infrastructure."*
    """
    assert _gate(_ladder(FAILED))["is_ceiling"] is False


def test_a_read_that_failed_draws_nothing():
    """**Entry 177, on a surface.**

    "Nobody could ask" is not "there is no partition". A lock drawn on a failed read is
    the same assertion this entry removes, arriving from the other direction.
    """
    assert _gate(_ladder(UNREADABLE))["is_ceiling"] is False


def test_a_caller_that_did_not_ask_asserts_nothing():
    """`held_out=None` - the default. A surface that did not ask has nothing to say."""
    assert _gate(_ladder(None))["is_ceiling"] is False


@pytest.mark.parametrize("reading", [UNREADABLE, ABSENT, PASSED, FAILED, None])
def test_no_other_gate_is_ever_a_ceiling(reading):
    rows = _ladder(reading)
    assert [r["gate"] for r in rows if r["is_ceiling"]] in ([], ["9.5"])


# ======================================================== the description

def test_the_gate_description_states_what_the_gate_does():
    """It read *"No deployment can pass this yet"* until 24 September.

    A description is a fact about the gate; whether it can be passed is a reading, and
    the two had been living in one string.
    """
    description = provisioning.GATE_DESCRIPTIONS["9.5"]
    # The stale claim, exactly. Not a keyword sweep: "cannot" is legitimate here -
    # "SimForge owns it and The Office cannot see it" is a fact about the gate.
    assert "No deployment can pass this yet" not in description
    assert "pass this yet" not in description


def test_neither_provisioning_page_asserts_the_partition_is_absent():
    """The prose the ruling names, gone from both files.

    Read off the source rather than rendered, because what matters is that the sentence
    is not in the file to go stale again.
    """
    from pathlib import Path

    for page in (
        Path("console/app/provisioning/page.tsx"),
        Path("console/app/provisioning/[venture]/page.tsx"),
    ):
        text = page.read_text(encoding="utf-8")
        assert "does not exist yet" not in text, page
        assert "Stated here rather than discovered at the gate" not in text, page


def test_the_index_block_renders_from_the_reading():
    """It takes the ventures and branches on what each one read."""
    from pathlib import Path

    text = Path("console/app/provisioning/page.tsx").read_text(encoding="utf-8")
    assert "function HeldOutCeiling" in text
    assert "held_out?.read" in text
    assert "partition_exists" in text
    assert "Asked of SimForge on this request" in text


# ======================================================== the reading itself

class _Source:
    def __init__(self, answer=None, raises=None):
        self.answer, self.raises = answer, raises

    async def verdict(self, venture_id):
        if self.raises is not None:
            raise self.raises
        return self.answer


async def test_the_reading_reports_each_shape(monkeypatch):
    from broker.simforge import SimForgeError

    cases = [
        (_Source(answer=None), {"read": True, "partition_exists": False,
                                "verdict": None}),
        (_Source(answer="PASS"), {"read": True, "partition_exists": True,
                                  "verdict": "PASS"}),
    ]
    for source, expected in cases:
        monkeypatch.setattr(provisioning, "_held_out_source",
                            lambda *a, _s=source, **k: _s)
        assert await provisioning.held_out_reading(object(), "greenstone") == expected

    monkeypatch.setattr(
        provisioning, "_held_out_source",
        lambda *a, **k: _Source(raises=SimForgeError("could not reach SimForge")))
    answer = await provisioning.held_out_reading(object(), "greenstone")
    assert answer["read"] is False
    assert "could not reach" in answer["reason"]


async def test_the_reading_never_raises(monkeypatch):
    """It is drawn on a page. A Forge that cannot be reached must not take the page
    down with it - `_forge_build`'s rule, one surface over."""
    monkeypatch.setattr(
        provisioning, "_held_out_source",
        lambda *a, **k: _Source(raises=RuntimeError("boom")))
    answer = await provisioning.held_out_reading(object(), "greenstone")
    assert answer["read"] is False
    assert "RuntimeError" in answer["reason"]
