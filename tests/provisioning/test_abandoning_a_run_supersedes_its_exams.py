"""Abandoning a run retires the exams it set, and nothing else.

RULED 21 SEPTEMBER 2026 (entry 142)
===================================

    *"Abandoning a run supersedes its open submissions."*

WHAT MADE IT A RULING
=====================

    Run 50d933e8 was abandoned on 20 September because its Gate 8 predated the
    corrected answer keys. Its nine `curriculum_submission` rows were not touched -
    nothing linked them to it - so the first run of the verdict sweep, hours later,
    read four PASS verdicts off them and wrote four certifications against withdrawn
    text.

    `abort_run` has always been careful about what it does NOT do: it leaves grants
    alone, because a grant is authority somebody holds and an abort has no standing to
    withdraw it. The submissions are the other case. They are exams THIS RUN set on a
    curriculum THIS RUN handed over, and abandoning the run withdraws the curriculum.

THE LOAD-BEARING TESTS IN THIS FILE
===================================

    `test_a_closed_submission_is_left_alone` and
    `test_another_runs_open_submissions_are_left_alone`. Every other test asserts a row was
    retired, and an `abort_run` that superseded the whole table would satisfy all of
    them while quietly ending certification for every venture on the platform.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from broker import provisioning, simforge
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
REASON = "its Gate 8 predates the corrected answer keys"


@pytest_asyncio.fixture
async def conn(feasible_pack, operator) -> AsyncIterator:
    async with connection() as opened:
        opened.operator = operator  # type: ignore[attr-defined]
        yield opened


async def _run(conn, operator) -> uuid.UUID:
    return await provisioning.start_run(
        conn, venture_id=VENTURE, started_by=operator.human_id
    )


async def _submission(
    conn, run_id: uuid.UUID | None, *, closed: bool = False,
    module_id: str = "assign_contract",
) -> uuid.UUID:
    """One submission, optionally already answered, aged past every deadline."""
    submission_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO curriculum_submission "
            "  (submission_id, venture_id, forge_id, module_id, scenario_pack_ref, "
            "   scenario_count, coverage_denominator, instruction_content_hash, "
            "   submitted_by, simforge_run_ref, submitted_at, run_id) "
            "VALUES (%s, %s, 'cre-forge', %s, 'pack/x', 7, 5, 'abc123', %s, "
            "        %s, now() - interval '72 hours', %s)",
            (
                submission_id, VENTURE, module_id, conn.operator.human_id,
                f"office:{VENTURE}:cre-forge:{module_id}:{submission_id.hex[:12]}",
                run_id,
            ),
        )
        if closed:
            await cur.execute(
                "UPDATE curriculum_submission SET result_received_at = now() "
                "WHERE submission_id = %s",
                (submission_id,),
            )
    await conn.commit()
    return submission_id


async def _row(conn, submission_id: uuid.UUID) -> dict:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT superseded_at, superseded_reason, result_received_at, run_id "
            "  FROM curriculum_submission WHERE submission_id = %s",
            (submission_id,),
        )
        row = await cur.fetchone()
    assert row is not None
    return {
        "superseded_at": row[0], "superseded_reason": row[1],
        "result_received_at": row[2], "run_id": row[3],
    }


# ----------------------------------------------------------------- the ruling

async def test_abandoning_a_run_supersedes_its_open_submissions(conn, operator):
    run_id = await _run(conn, operator)
    submission_id = await _submission(conn, run_id)

    await provisioning.abort_run(
        conn, run_id=run_id, human=operator, reason=REASON
    )

    row = await _row(conn, submission_id)
    assert row["superseded_at"] is not None
    assert str(run_id)[:8] in row["superseded_reason"]
    assert REASON in row["superseded_reason"]
    assert operator.display_name in row["superseded_reason"]


async def test_a_superseded_submission_leaves_the_sweeps_queue(conn, operator):
    """The consequence that matters. `overdue_submissions` is the candidate set, and
    a row still in it is a verdict the sweep will ingest."""
    run_id = await _run(conn, operator)
    submission_id = await _submission(conn, run_id)
    before = {r["submission_id"] for r in await simforge.overdue_submissions(
        conn, deadline_hours=0
    )}
    assert submission_id in before

    await provisioning.abort_run(conn, run_id=run_id, human=operator, reason=REASON)

    after = {r["submission_id"] for r in await simforge.overdue_submissions(
        conn, deadline_hours=0
    )}
    assert submission_id not in after


async def test_superseding_claims_no_verdict_arrived(conn, operator):
    """0046's distinction, restated for this writer.

    `result_received_at` means a verdict was written into a certification. Stamping it
    here would record that one was, when the ruling is that none will be.
    """
    run_id = await _run(conn, operator)
    submission_id = await _submission(conn, run_id)
    await provisioning.abort_run(conn, run_id=run_id, human=operator, reason=REASON)

    row = await _row(conn, submission_id)
    assert row["result_received_at"] is None
    assert row["superseded_at"] is not None


# ------------------------------------------------- the two that keep it from being a wipe

async def test_a_closed_submission_is_left_alone(conn, operator):
    """**Load-bearing.** Its verdict was ingested before the run was abandoned, and a
    certification already exists. Marking it superseded now would claim a decision was
    taken about that certification - which is a revocation, a different act with
    different authority.
    """
    run_id = await _run(conn, operator)
    closed = await _submission(conn, run_id, closed=True)

    await provisioning.abort_run(conn, run_id=run_id, human=operator, reason=REASON)

    row = await _row(conn, closed)
    assert row["result_received_at"] is not None
    assert row["superseded_at"] is None
    assert row["superseded_reason"] is None


async def test_another_runs_open_submissions_are_left_alone(conn, operator):
    """**Load-bearing.** An `abort_run` that superseded on venture rather than on run
    would retire the live run's exams too - which is what happened in reverse on
    20 September, and would be a worse version of it.
    """
    other = await _submission(conn, None)
    run_id = await _run(conn, operator)
    mine = await _submission(conn, run_id)

    await provisioning.abort_run(conn, run_id=run_id, human=operator, reason=REASON)

    assert (await _row(conn, mine))["superseded_at"] is not None
    assert (await _row(conn, other))["superseded_at"] is None


# ----------------------------------------------------------------- the link itself

async def test_a_submission_records_the_run_that_set_it(conn, operator):
    """Without this column the ruling can only be applied by matching timestamps.

    Gate 8 has always known which run it is - `_Context` holds `run_id`, and
    `scenario_pack_ref` spells it as `run:<uuid>` text - and the row threw it away.
    """
    run_id = await _run(conn, operator)
    submission_id = await _submission(conn, run_id)
    assert (await _row(conn, submission_id))["run_id"] == run_id


async def test_superseding_requires_a_reason(conn, operator):
    """The CHECK 0046 added says a mark and a reason travel together. This refuses the
    empty one at the writer, so the constraint is never the first thing to notice."""
    run_id = await _run(conn, operator)
    with pytest.raises(ValueError):
        await simforge.supersede_run_submissions(conn, run_id=run_id, reason="   ")


async def test_the_count_is_on_the_audit_event(conn, operator):
    """A later reader asking why the sweep stopped being owed nine verdicts should find
    the answer on the act, not by diffing two tables."""
    run_id = await _run(conn, operator)
    await _submission(conn, run_id, module_id="assign_contract")
    await _submission(conn, run_id, module_id="buyer_match")

    await provisioning.abort_run(conn, run_id=run_id, human=operator, reason=REASON)

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT subject FROM audit_log "
            " WHERE event_type = 'provisioning_run_aborted' "
            " ORDER BY audit_id DESC LIMIT 1"
        )
        row = await cur.fetchone()
    assert row is not None
    assert row[0]["submissions_superseded"] == 2
