"""Gate 8 asks the Forge which build it is running, records it, and warns - never blocks.

WHY THE QUESTION EXISTS
=======================

    Ruled 18 September 2026 (entry 131): *"The Office asks whether the Forge it submits
    to is current, as it already asks of itself. A submitter that vouches for its own
    build and not its counterpart has checked one end of the wire."*

    Entry 127 made this gate refuse to submit on a build The Office cannot vouch for.
    This is the other end, and it is not hypothetical: SimForge served a build sixteen
    commits old for two days. The six verdicts it produced were graded with
    `operation_scenarios` discarded on arrival - a curriculum accepted and kept none
    of, by a process every check reported healthy. Finding that took reading a commit
    SHA out of `openapi.json` by hand, days later (entry 128).

WHY IT WARNS
============

    A stale Forge does not change what is SENT; it changes what is done with a correct
    submission. This gate does not block on facts about the Forge - not an outage, not
    a refused response - because *"blocking the ladder on a service that is allowed to
    be down would be worse"*, and CI runs no SimForge at all. `differs` also cannot
    decide compatibility: it answers whether SimForge's checkout moved past its
    process, not whether this payload will be understood.

    And the right instrument against a stale GRADER already exists: entry 129 put the
    answer key into the exam's identity and entry 128 refused to ingest six verdicts
    earned under a superseded one. The answer to "this verdict may not be trustworthy"
    is to not trust the verdict, not to deny an agent an exam over a doubt about the
    marking.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_a_stale_forge_does_not_stop_the_exam`. Every other test here asserts that
    something is recorded or said, and a probe that quietly began blocking would
    satisfy all of them while stopping every ladder on every machine without a
    SimForge.
"""

from __future__ import annotations

import pytest

from broker import provisioning
from tests.conftest import requires_db
from tests.provisioning.test_simforge_handover import (  # noqa: F401 - fixtures
    SimForgeAccepts,
    at_gate_8,
)

pytestmark = [requires_db, pytest.mark.db]

CURRENT = "a" * 40
MOVED_ON = "b" * 40


def _gate_8(outcomes):
    for outcome in outcomes:
        if outcome.gate == "8":
            return outcome
    raise AssertionError("Gate 8 did not run")


class ForgeSays(SimForgeAccepts):
    """A SimForge that answers `/api/version` with whatever the test hands it."""

    def __init__(self, answer, **kwargs) -> None:
        super().__init__(**kwargs)
        self._answer = answer

    async def build(self, conn) -> dict:
        return self._answer


class ForgeCannotBeAsked(SimForgeAccepts):
    """A client with no `build` method - every fake written before this existed."""


class ForgeThrowsOnTheProbe(SimForgeAccepts):
    async def build(self, conn) -> dict:
        raise RuntimeError("the version route fell over")


CURRENT_FORGE = {
    "reachable": True, "started_commit": CURRENT, "checkout_commit": CURRENT,
    "differs": False, "app_version": "1.0.0",
}
STALE_FORGE = {
    "reachable": True, "started_commit": CURRENT, "checkout_commit": MOVED_ON,
    "differs": True, "app_version": "1.0.0",
}
SILENT_FORGE = {"reachable": False, "reason": "ConnectError: nothing there"}


async def _run(at_gate_8, operator, forge):  # noqa: F811
    conn, run_id = at_gate_8
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=forge,
    )
    return _gate_8(outcomes)


# ------------------------------------------------------------------ it does not block

async def test_a_stale_forge_does_not_stop_the_exam(at_gate_8, operator):  # noqa: F811
    """**The test that keeps this a record rather than a second refusal.**

    Every other test here asserts something is recorded or said. A probe that began
    blocking would satisfy all of them while stopping every ladder on every machine
    that has no SimForge - which is every CI runner.
    """
    forge = ForgeSays(STALE_FORGE)
    gate_8 = await _run(at_gate_8, operator, forge)

    assert gate_8.verdict == provisioning.PASSED
    assert forge.calls, "a stale Forge stopped the curriculum going over"


async def test_a_forge_that_will_not_say_does_not_stop_the_exam(at_gate_8, operator):  # noqa: F811
    """An outage in the probe is still an outage, and this gate never blocks on one."""
    gate_8 = await _run(at_gate_8, operator, ForgeSays(SILENT_FORGE))
    assert gate_8.verdict == provisioning.PASSED


async def test_a_probe_that_throws_is_an_answer_and_not_a_crash(at_gate_8, operator):  # noqa: F811
    """A question asked out of caution must not be what stops the run."""
    gate_8 = await _run(at_gate_8, operator, ForgeThrowsOnTheProbe())

    assert gate_8.verdict == provisioning.PASSED
    assert gate_8.evidence["forge_build"]["reachable"] is False
    assert "RuntimeError" in gate_8.evidence["forge_build"]["reason"]


# ----------------------------------------------------------------- what is recorded

async def test_the_forges_build_is_on_the_gate_result(at_gate_8, operator):  # noqa: F811
    """**The field that turns an investigation into a lookup.**

    Entry 128's six verdicts were graded by a build sixteen commits old and nothing
    anywhere recorded it. Both ends of the wire are now on the row, named the same way.
    """
    gate_8 = await _run(at_gate_8, operator, ForgeSays(CURRENT_FORGE))

    recorded = gate_8.evidence["forge_build"]
    assert recorded["reachable"] is True
    assert recorded["started_commit"] == CURRENT
    assert recorded["checkout_commit"] == CURRENT
    assert recorded["differs"] is False
    assert gate_8.evidence["submitting_build"]["commit"], (
        "only one end of the wire is on the record"
    )


async def test_a_client_that_cannot_be_asked_is_recorded_as_such(at_gate_8, operator):  # noqa: F811
    """Not the same finding as a Forge that would not answer.

    Every SimForge fake written before this existed has no `build` method. "This client
    could not be asked" is true and is a different sentence from "the Forge is down".
    """
    gate_8 = await _run(at_gate_8, operator, ForgeCannotBeAsked())

    recorded = gate_8.evidence["forge_build"]
    assert recorded["reachable"] is False
    assert "cannot be asked" in recorded["reason"]


async def test_the_build_is_recorded_once_not_once_per_module(at_gate_8, operator):  # noqa: F811
    """One answer, taken at a known moment.

    A probe per module would ask the same question five times and could report two
    different builds for one run - a worse record than one answer with a timestamp.
    """
    class Counting(ForgeSays):
        probes = 0

        async def build(self, conn) -> dict:
            Counting.probes += 1
            return self._answer

    await _run(at_gate_8, operator, Counting(CURRENT_FORGE))
    assert Counting.probes == 1, f"the Forge was asked {Counting.probes} times"


# -------------------------------------------------------------------- what is SAID

async def test_a_stale_forge_is_named_in_the_gates_sentence(at_gate_8, operator):  # noqa: F811
    """In the sentence, not only in the evidence.

    A verdict graded by a stale Forge is indistinguishable from any other once it is
    written down. The moment to say so is the moment the exam is set, where somebody
    is reading - which is the one thing entry 128's six verdicts never got.
    """
    gate_8 = await _run(at_gate_8, operator, ForgeSays(STALE_FORGE))

    assert "WARNING" in gate_8.reason
    assert CURRENT[:12] in gate_8.reason
    assert MOVED_ON[:12] in gate_8.reason
    assert "moved past" in gate_8.reason


async def test_a_silent_forge_says_so_differently(at_gate_8, operator):  # noqa: F811
    """Two findings, two responses: a route to add, or a restart."""
    gate_8 = await _run(at_gate_8, operator, ForgeSays(SILENT_FORGE))

    assert "WARNING" in gate_8.reason
    assert "did not say which build" in gate_8.reason


async def test_a_current_forge_adds_no_noise(at_gate_8, operator):  # noqa: F811
    """A warning that fires on the good case is a warning nobody reads."""
    gate_8 = await _run(at_gate_8, operator, ForgeSays(CURRENT_FORGE))
    assert "WARNING" not in gate_8.reason


async def test_differs_being_unknown_is_not_treated_as_current(at_gate_8, operator):  # noqa: F811
    """**SimForge is explicit that `differs` is never `false` when it could not read
    one side**, because a process that cannot say what it is running must not report
    itself up to date. `None` must not be read as "no difference" on this side either.
    """
    unknown = dict(CURRENT_FORGE, differs=None, checkout_commit=None)
    gate_8 = await _run(at_gate_8, operator, ForgeSays(unknown))

    assert gate_8.evidence["forge_build"]["differs"] is None
    assert "WARNING" not in gate_8.reason, (
        "an unreadable checkout is not the same finding as a confirmed drift; it is "
        "reported on the row rather than shouted"
    )
