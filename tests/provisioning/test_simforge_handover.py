"""Gate 8's hand-over, and the two fields that were never right.

`handed_over_to_simforge` was hard-coded `False` with an honest comment, and
`simforge_run_ref` was never written at all. The second was the expensive one: it is
what `overdue_submissions` and `timeout_gate_result` key on, so the timeout sweep
`broker/simforge.py` argues for at length could never resolve anything. See
docs/blocking.md B8.

So the assertions here are about the row and about what a sweep can do with it, not
about the flag. A gate reporting a hand-over is easy to write and easy to believe; a
submission that can be correlated to a verdict is the thing that was missing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from broker import provisioning
from broker.db import connection
from broker.simforge import SimForgeError, overdue_submissions
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


class HeldOutPasses:
    async def verdict(self, venture_id: str) -> str | None:
        return "PASS"


class SimForgeAccepts:
    """Answers the way the response manifest says it may."""

    def __init__(self, run_ref: str = "sf-run-test-0001") -> None:
        self.run_ref = run_ref
        self.calls: list[dict] = []

    async def submit_curriculum(self, conn, **kwargs) -> str:
        self.calls.append(kwargs)
        return self.run_ref

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


class SimForgeIsDown:
    """The case the old code reported as a hand-over regardless."""

    async def submit_curriculum(self, conn, **kwargs) -> str:
        raise SimForgeError("could not reach SimForge: ConnectError")

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


@pytest_asyncio.fixture
async def at_gate_8(feasible_pack, operator) -> AsyncIterator[tuple]:
    """A run parked immediately before Gate 8 runs.

    The first `advance` stops at Gate 4 waiting for a person; recording the review
    releases it. The *test* makes the next call, so it chooses which SimForge Gate 8
    meets.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed for the hand-over test"
        )
        yield conn, run_id


async def _submissions(conn, venture_id: str = VENTURE) -> list[dict]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT scenario_pack_ref, simforge_run_ref, scenario_count
            FROM curriculum_submission WHERE venture_id = %s
            ORDER BY submitted_at
            """,
            (venture_id,),
        )
        rows = await cur.fetchall()
    return [{"pack_ref": r[0], "run_ref": r[1], "count": r[2]} for r in rows]


def _gate_8(outcomes):
    for o in outcomes:
        if o.gate == "8":
            return o
    raise AssertionError(f"gate 8 did not run; reached {[o.gate for o in outcomes]}")


async def test_an_accepted_handover_stores_the_run_ref(at_gate_8, operator):
    """The row a sweep can act on.

    Asserted on `curriculum_submission.simforge_run_ref` and not on the gate's own
    evidence dict, because the evidence is what the old code got wrong while looking
    right: it wrote a row nothing could correlate and reported the gate as passed.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    rows = await _submissions(conn)
    assert rows, "gate 8 wrote no submission"
    assert rows[-1]["run_ref"] == "sf-run-test-0001"

    gate = _gate_8(outcomes)
    assert gate.evidence["handed_over_to_simforge"] is True
    assert gate.evidence["simforge_run_ref"] == "sf-run-test-0001"

    # The hand-over carried counts and the human who provisioned - never an agent.
    assert fake.calls[0]["actor"] == operator.human_id
    assert fake.calls[0]["payload"]["scenario_count"] == rows[-1]["count"]


async def test_an_unreachable_simforge_is_not_reported_as_a_handover(
    at_gate_8, operator
):
    """The gate still passes, and says plainly that nothing landed.

    Passing is correct: the Office's half - the curriculum, the counts, the row - is
    complete and reproducible. What must not happen is the run reading as handed over.
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=SimForgeIsDown(),
    )

    gate = _gate_8(outcomes)
    assert gate.verdict == provisioning.PASSED
    assert gate.evidence["handed_over_to_simforge"] is False
    assert gate.evidence["simforge_run_ref"] is None
    assert "not received by SimForge" in gate.reason
    assert "ConnectError" in gate.evidence["handover_error"]

    rows = await _submissions(conn)
    assert rows[-1]["run_ref"] is None


async def test_the_timeout_sweep_can_now_resolve_a_submission(at_gate_8, operator):
    """B8, asserted as a consequence rather than as a field.

    `overdue_submissions` returns unanswered rows past a deadline, and
    `timeout_gate_result` builds a TIMEOUT verdict keyed on `simforge_run_ref`. Every
    row Gate 8 wrote carried NULL there, so the sweep could find a submission and had
    nothing to key a verdict on. This asserts the ref survives all the way to the
    verdict the sweep would produce.
    """
    conn, run_id = at_gate_8
    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses(),
        simforge=SimForgeAccepts("sf-run-overdue"),
    )

    # deadline_hours=0: everything unanswered is overdue, which is what a hung run
    # looks like without waiting a day to see one.
    overdue = await overdue_submissions(conn, deadline_hours=0)
    mine = [r for r in overdue if r["venture_id"] == VENTURE]
    assert mine, "the sweep found nothing"

    from broker.simforge import timeout_gate_result

    verdict = timeout_gate_result(mine[-1], rubric_version="1.4.0")
    assert verdict.verdict == "TIMEOUT"
    # The ref, not the `unanswered:<submission_id>` placeholder the helper falls back
    # to. That fallback was the only branch this could ever take before.
    assert verdict.run_ref == "sf-run-overdue"
