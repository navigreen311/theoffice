"""A superseded exam leaves the sweep's queue without claiming a verdict arrived.

WHY NOT `result_received_at`
============================

    Entry 128 ruled that six verdicts earned on superseded scenarios are not ingested.
    Prose alone could not carry that: the rows stayed in `sweep_verdict_ingest`'s
    candidate set and one `python -m broker sweep` would have written all six.

    `result_received_at` was the tempting field and it is the wrong one. Its own
    docstring: *"`result_received_at` means 'a verdict SimForge stands behind was
    written into a certification', NOT 'we stopped asking'."* Stamping it here would
    record that a certification was written when the ruling is that none will be, and
    every later reader would conclude a verdict arrived.

    So 0046 adds a separate mark with a reason beside it. **The row keeps its
    verdict-shaped hole**, which is the true statement: an exam was set, an answer came
    back, and nobody will act on it.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_an_ordinary_open_submission_is_still_swept`. Every other test asserts a row
    is excluded, and a reader that excluded everything would satisfy all of them while
    silently ending certification on the platform.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from broker import simforge
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

REASON = "superseded for the test's own reason"

REF = "office:greenstone:cre-forge:assign_contract@cc49a49c:abc123def456"

@pytest_asyncio.fixture
async def conn(operator) -> AsyncIterator:
    """A connection, and a human to hang `submitted_by` on."""
    async with connection() as opened:
        opened.operator = operator  # type: ignore[attr-defined]
        yield opened


async def _submission(conn, *, ref: str | None, module_id: str = "assign_contract"):
    """One open submission, aged past every deadline so nothing hides behind a window."""
    submission_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO curriculum_submission "
            "  (submission_id, venture_id, forge_id, module_id, scenario_pack_ref, "
            "   scenario_count, coverage_denominator, instruction_content_hash, "
            "   submitted_by, simforge_run_ref, submitted_at) "
            "VALUES (%s, 'greenstone', 'cre-forge', %s, 'pack/x', 7, 5, 'abc123', "
            "        %s, %s, now() - interval '72 hours')",
            (submission_id, module_id, conn.operator.human_id, ref),
        )
    await conn.commit()
    return submission_id


async def _supersede(conn, submission_id, *, reason: str = REASON):
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE curriculum_submission "
            "   SET superseded_at = now(), superseded_reason = %s "
            " WHERE submission_id = %s",
            (reason, submission_id),
        )
    await conn.commit()


async def _ids(conn) -> set[uuid.UUID]:
    rows = await simforge.overdue_submissions(conn, deadline_hours=0)
    return {r["submission_id"] for r in rows}


# ----------------------------------------------------------------- the exclusion

async def test_an_ordinary_open_submission_is_still_swept(conn):
    """**The test that keeps this an exclusion rather than an off switch.**

    Every other test here asserts a row is dropped from the candidate set. A reader
    that dropped everything would satisfy all of them and end certification quietly.
    """
    submission_id = await _submission(conn, ref=REF)
    assert submission_id in await _ids(conn)


async def test_a_superseded_submission_leaves_the_candidate_set(conn):
    submission_id = await _submission(conn, ref=REF)
    assert submission_id in await _ids(conn)

    await _supersede(conn, submission_id)
    assert submission_id not in await _ids(conn)


async def test_superseding_claims_no_verdict_arrived(conn):
    """The whole reason this is not `result_received_at`.

    A reader asking "did a verdict come back for this exam" must still get no. The row
    is excluded from the sweep and remains, truthfully, unanswered.
    """
    submission_id = await _submission(conn, ref=REF)
    await _supersede(conn, submission_id)

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT result_received_at, superseded_at, superseded_reason "
            "  FROM curriculum_submission WHERE submission_id = %s",
            (submission_id,),
        )
        received, superseded, reason = await cur.fetchone()

    assert received is None, (
        "the row claims a verdict was written into a certification; the ruling is that "
        "none will be"
    )
    assert superseded is not None
    assert reason == REASON


async def test_a_mark_with_no_reason_is_refused(conn):
    """A row excluded from every sweep with no record of who decided or why is the
    shape this codebase keeps refusing. 0046's CHECK makes it unrepresentable."""
    submission_id = await _submission(conn, ref=REF)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE curriculum_submission SET superseded_at = now() "
                " WHERE submission_id = %s",
                (submission_id,),
            )
    await conn.rollback()


async def test_a_reason_with_no_mark_is_refused(conn):
    """Both directions. A reason beside an unsuperseded row reads as a decision that
    was taken and did not take effect."""
    submission_id = await _submission(conn, ref=REF)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE curriculum_submission SET superseded_reason = %s "
                " WHERE submission_id = %s",
                (REASON, submission_id),
            )
    await conn.rollback()
