"""The control sweeps and the ended-shift flush run without anybody asking.

RULED 22 SEPTEMBER 2026 (decisions entries 168 and 169)
=======================================================

    168. *"A sweep runs on its own, in the API's lifespan, as deadlines do. Keep the
         declared MAX_AGE intervals. Measured: verdict_ingest 3 runs ever, last 21 Sep;
         audit_chain and certification_staleness last ran in August; deadline_expiry 221
         runs. A withdrawn SimForge verdict that nobody reads leaves an agent holding
         authority it lost."*

    169. *"A shift that ends is flushed, at shift_end, by that same scheduler, with no
         reassignment. Measured: flush_phi's only caller is rotate, so a flush is
         reachable only as a side effect of assigning a new shift. Three Greenstone
         agents have been blocked since 17 Sep."*

THE THREE THAT CARRY THE RULINGS
================================

    `test_the_api_lifespan_starts_both_runners` - "in the API's lifespan" is the whole
    of 168. `run_all` said "safe to invoke from cron" for weeks and nothing invoked it.

    `test_due_reads_the_declared_max_age` - *"keep the declared MAX_AGE intervals."* One
    schedule, not a second one written beside the first.

    `test_an_ended_shift_is_flushed_and_nothing_is_assigned` - the flush, and the half of
    169 that is a refusal rather than an action.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

from broker import shifts, sweeps
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "test-sweep-venture"
AGENT = uuid.UUID("f0f0f0f0-0000-4000-8000-000000000169")
ASSIGNER = uuid.UUID("f0f0f0f0-0000-4000-8000-00000000016a")


@pytest.fixture(autouse=True)
def _world(admin: psycopg.Connection):
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'Sweep Assigner', 'sweep@assigner.invalid', 'bearer_token', "
            "        'test_fixture', %s) ON CONFLICT (human_id) DO NOTHING",
            (ASSIGNER, f"sweep-{ASSIGNER.hex}"),
        )
        cur.execute(
            "INSERT INTO office_agent_identity "
            "  (office_agent_id, village_agent_ref, agent_name, department, status) "
            "VALUES (%s, %s, 'Sweep Agent', 'operations', 'active') "
            "ON CONFLICT (office_agent_id) DO NOTHING",
            (AGENT, f"village:sweep:{AGENT.hex[:8]}"),
        )
    admin.commit()
    _wipe(admin)
    yield
    _wipe(admin)
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_agent_identity WHERE office_agent_id = %s",
                    (AGENT,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (ASSIGNER,))
    admin.commit()


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_working_memory WHERE office_agent_id = %s",
                    (AGENT,))
        cur.execute("DELETE FROM shift_assignment WHERE office_agent_id = %s", (AGENT,))
    conn.commit()


def _shift(
    conn: psycopg.Connection, *, ended: bool, attempted: bool = False
) -> uuid.UUID:
    """One shift, open or closed, written directly so the clock can be chosen."""
    shift_id = uuid.uuid4()
    start = datetime.now(UTC) - timedelta(hours=9)
    end = start + timedelta(hours=8) if ended else datetime.now(UTC) + timedelta(hours=1)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO shift_assignment "
            "  (shift_id, office_agent_id, venture_id, shift_start, shift_end, "
            "   assigned_by, quarter, flush_attempted_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, '2030Q3', %s)",
            (shift_id, AGENT, VENTURE, start, end, ASSIGNER,
             datetime.now(UTC) if attempted else None),
        )
    conn.commit()
    return shift_id


def _phi(conn: psycopg.Connection, shift_id: uuid.UUID, rows: int = 3) -> None:
    """PHI-tagged working memory. `content_ref` is a pointer, never the content - the
    flush reads only the classification, and so does this."""
    with conn.cursor() as cur:
        for n in range(rows):
            cur.execute(
                "INSERT INTO agent_working_memory "
                "  (memory_id, office_agent_id, shift_id, venture_id, "
                "   data_classification, content_ref) "
                "VALUES (%s, %s, %s, %s, 'phi', %s)",
                (uuid.uuid4(), AGENT, shift_id, VENTURE, f"blob://sweep-test/{n}"),
            )
    conn.commit()


def _memory_rows(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM agent_working_memory "
            " WHERE office_agent_id = %s AND data_classification = 'phi'",
            (AGENT,),
        )
        return int(cur.fetchone()[0])


def _row(conn: psycopg.Connection, shift_id: uuid.UUID) -> dict[str, Any]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT * FROM shift_assignment WHERE shift_id = %s", (shift_id,))
        return dict(cur.fetchone())


# ============================================================= 168. the runner

def test_the_api_lifespan_starts_both_runners():
    """**THE RULING.** *"in the API's lifespan, as deadlines do."*

    `sweeps.run_all` has carried the docstring "safe to invoke from cron" since it was
    written and nothing ever invoked it - the same sentence `broker/__main__.py` carried
    about deadlines until entry 156, and the same outcome. Read from the source so that
    removing the runner fails here rather than showing up as a sweep that last ran in
    August.
    """
    from broker import app

    source = inspect.getsource(app.lifespan)
    assert "deadlines.running()" in source
    assert "sweeps.running()" in source, (
        "the API no longer starts the sweep runner; nothing else does either"
    )


def test_the_runner_and_run_all_share_one_registry():
    """A sweep added to one is added to both.

    There were two lists of sweep kinds and a runner added later would have been a
    third. `test_gate_9` learned this lesson on a different table: two controls over one
    invariant, and the second did not know about the first.
    """
    assert set(sweeps.SCHEDULED) <= set(sweeps._SWEEPS)
    assert set(sweeps._SWEEPS) <= set(sweeps.MAX_AGE), (
        "a sweep the runner can run but MAX_AGE does not describe has no schedule"
    )


def test_the_restore_drill_is_not_scheduled_and_that_is_deliberate():
    """It shells out to `pg_restore` and takes as long as a restore takes.

    A quarterly job that starts itself inside the API process is a quarterly job that
    will one day start itself during an incident. `freshness` keeps reporting it
    `never_run`, which is not green - the correct state for a control nobody has
    exercised.
    """
    assert sweeps.RESTORE_DRILL in sweeps.MAX_AGE
    assert sweeps.RESTORE_DRILL not in sweeps.SCHEDULED
    assert sweeps.RESTORE_DRILL not in sweeps._SWEEPS


async def test_due_reads_the_declared_max_age(admin):
    """*"Keep the declared MAX_AGE intervals."* One schedule, not two.

    `freshness()` already calls a sweep older than its `MAX_AGE` stale, and stale is not
    green. A separate interval would let the thing that decides when to run and the
    thing that decides whether the result counts disagree - and the one that reports
    would be the one nobody noticed had drifted.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM sweep_run WHERE sweep_kind = %s",
                    (sweeps.AUDIT_CHAIN,))
        # A pass from inside the window: not due.
        cur.execute(
            "INSERT INTO sweep_run (sweep_run_id, sweep_kind, status, started_at, "
            "                       completed_at, denominator) "
            "VALUES (%s, %s, 'passed', now() - interval '1 hour', now(), 1)",
            (uuid.uuid4(), sweeps.AUDIT_CHAIN),
        )
    admin.commit()
    async with connection() as conn:
        assert sweeps.AUDIT_CHAIN not in await sweeps.due(conn)

    with admin.cursor() as cur:
        cur.execute("DELETE FROM sweep_run WHERE sweep_kind = %s",
                    (sweeps.AUDIT_CHAIN,))
        # A pass from beyond it: due. One day is what MAX_AGE declares.
        cur.execute(
            "INSERT INTO sweep_run (sweep_run_id, sweep_kind, status, started_at, "
            "                       completed_at, denominator) "
            "VALUES (%s, %s, 'passed', now() - interval '30 hours', "
            "        now() - interval '30 hours', 1)",
            (uuid.uuid4(), sweeps.AUDIT_CHAIN),
        )
    admin.commit()
    async with connection() as conn:
        assert sweeps.AUDIT_CHAIN in await sweeps.due(conn)

    assert sweeps.MAX_AGE[sweeps.AUDIT_CHAIN] == timedelta(days=1), (
        "the declared interval moved; entry 168 says keep it"
    )


async def test_a_sweep_that_never_ran_is_due(admin):
    """`never_run` is due, and that is not an edge case.

    Measured 22 September: `audit_chain` and `certification_staleness` last ran in
    August, and `restore_drill` had never run at all.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM sweep_run WHERE sweep_kind = %s",
                    (sweeps.VERDICT_INGEST,))
    admin.commit()
    async with connection() as conn:
        assert sweeps.VERDICT_INGEST in await sweeps.due(conn)


# ====================================================== 169. the ended-shift flush

async def test_an_ended_shift_is_flushed_and_nothing_is_assigned(admin):
    """**THE RULING.** *"A shift that ends is flushed, at shift_end... with no
    reassignment."*

    `flush_phi` had one caller - `rotate` - so a flush was reachable only as a side
    effect of assigning a new shift, and `assign_shift` refuses when the previous shift
    has no verified flush. Three Greenstone agents sat in that closed loop from 17
    September.

    **No reassignment** is the ruling, not an economy. Nobody asked for a rotation; a
    window closed. A scheduler that assigned the next shift would be deciding who works
    next, which is a person's decision.
    """
    shift_id = _shift(admin, ended=True)
    _phi(admin, shift_id)
    assert _memory_rows(admin) == 3

    before = _shift_count(admin)
    async with connection() as conn:
        report = await shifts.flush_ended_shifts(conn)

    assert report["shifts_flushed"] == [str(shift_id)]
    assert report["ended_unflushed_considered"] == 1
    assert _memory_rows(admin) == 0

    row = _row(admin, shift_id)
    assert row["flush_verified"] is True
    assert row["flush_completed_at"] is not None
    assert row["flush_attempted_at"] is not None

    assert _shift_count(admin) == before, (
        "the flush assigned a shift; entry 169 says it assigns nothing"
    )


def _shift_count(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM shift_assignment WHERE office_agent_id = %s",
                    (AGENT,))
        return int(cur.fetchone()[0])


async def test_an_open_shift_is_left_alone(admin):
    """**Load-bearing.** A flush that cleared a working agent's memory mid-shift would
    be the temporal PHI wall firing early, which is worse than firing late."""
    shift_id = _shift(admin, ended=False)
    _phi(admin, shift_id)

    async with connection() as conn:
        report = await shifts.flush_ended_shifts(conn)

    assert report["ended_unflushed_considered"] == 0
    assert _memory_rows(admin) == 3
    assert _row(admin, shift_id)["flush_attempted_at"] is None


async def test_a_flush_that_was_already_attempted_is_not_retried(admin):
    """`flush_attempted_at IS NULL`, not `NOT flush_verified`.

    A flush that ran and FAILED is a `FlushFailed` incident somebody has to look at, and
    a loop retrying it every minute would turn a standing alarm into a log nobody reads.
    """
    shift_id = _shift(admin, ended=True, attempted=True)
    _phi(admin, shift_id)

    async with connection() as conn:
        report = await shifts.flush_ended_shifts(conn)

    assert report["ended_unflushed_considered"] == 0
    assert _memory_rows(admin) == 3, "a failed flush was silently retried"
    assert str(shift_id) not in report["shifts_flushed"]


async def test_the_flush_unblocks_the_next_assignment(admin):
    """What the three Greenstone agents were waiting for.

    `assign_shift` raises `ShiftBlocked` on a previous shift with no verified flush. This
    is the whole point of the entry: the block is correct and the thing that clears it
    now happens on its own.
    """
    from broker.errors import OfficeError

    ended = _shift(admin, ended=True)
    _phi(admin, ended)

    async with connection() as conn:
        with pytest.raises(OfficeError) as raised:
            await shifts.assign_shift(
                conn, office_agent_id=AGENT, venture_id=VENTURE,
                shift_start=datetime.now(UTC),
                shift_end=datetime.now(UTC) + timedelta(hours=8),
                assigned_by=ASSIGNER, quarter="2030Q3",
            )
        assert "flush" in str(raised.value)

        await shifts.flush_ended_shifts(conn)

        # Now it is only the quarter rule standing in the way, which is a different
        # refusal about a different fact - and proves the flush block is gone.
        try:
            await shifts.assign_shift(
                conn, office_agent_id=AGENT, venture_id=VENTURE,
                shift_start=datetime.now(UTC),
                shift_end=datetime.now(UTC) + timedelta(hours=8),
                assigned_by=ASSIGNER, quarter="2030Q3",
            )
        except OfficeError as exc:
            assert "flush" not in str(exc), (
                "still blocked on the flush after flushing"
            )


async def test_the_runner_flushes_every_tick_not_on_a_max_age(admin):
    """The flush is a continuous condition, not a control with a freshness window.

    `run_forever` calls it before the `due()` gate, so a shift that ends is flushed
    within a tick rather than whenever the next daily sweep happens to fall due.
    """
    source = inspect.getsource(sweeps.run_forever)
    flush_at = source.index("flush_ended_shifts")
    due_at = source.index("await due(conn)")
    assert flush_at < due_at, (
        "the flush is inside or after the MAX_AGE gate; entry 169 says at shift_end"
    )
    assert sweeps.TICK_SECONDS <= 60, (
        "a tick longer than a minute means PHI sits after a window closes"
    )
