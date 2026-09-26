"""A call started and not completed, surfaced. Entry 199.

The evidence has existed since the first call: `forge_call_intent` is written before the
Forge is touched and the ledger row after. Nothing looked. These assert that something
does now, and that it does only what the ruling permits - report, never retry, never
close the row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg.types.json import Jsonb

from broker import sweeps
from broker.config import get_settings
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

AGENT = uuid.UUID("c8afb0e6-c632-4e07-8943-d5159a1d2298")


def _cutoff_seconds() -> int:
    return int(get_settings().forge_timeout_seconds * sweeps.INCOMPLETE_AFTER_TIMEOUTS)


def _write_intent(
    admin: psycopg.Connection, call_id: uuid.UUID, *, age_seconds: int
) -> uuid.UUID:
    """A pre-call intent, aged. `audit_log.ts` is written explicitly so the sweep's
    cutoff can be exercised without waiting for it."""
    trace_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log "
            "  (event_type, actor_type, actor_id, venture_id, trace_id, subject, ts) "
            "VALUES ('forge_call_intent', 'agent', %s, 'greenstone', %s, %s, "
            "        now() - make_interval(secs => %s))",
            (
                AGENT,
                trace_id,
                Jsonb({
                    "call_id": str(call_id),
                    "forge_id": "cre-forge",
                    "module_id": "assign_contract",
                    "task_id": "task-199",
                    "approved_proposal_id": None,
                }),
                age_seconds,
            ),
        )
    admin.commit()
    return trace_id


def _write_ledger(
    admin: psycopg.Connection,
    call_id: uuid.UUID,
    trace_id: uuid.UUID,
    *,
    ts_end: datetime | None,
    age_seconds: int = 0,
) -> None:
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_call_ledger "
            "  (call_id, trace_id, office_agent_id, venture_id, forge_id, module_id, "
            "   api_version, ts_start, ts_end, trust_tier_at_call, "
            "   compliance_flags_active, data_types_touched, manifest_match, "
            "   payload_hash, task_id) "
            "VALUES (%s, %s, %s, 'greenstone', 'cre-forge', 'assign_contract', "
            "        '1.0.0', now() - make_interval(secs => %s), %s, 'propose', "
            "        '{}', '{}', 'required', 'h', 'task-199')",
            (call_id, trace_id, AGENT, age_seconds, ts_end),
        )
    admin.commit()


@pytest.fixture
def clean_calls(admin: psycopg.Connection):
    """Only the incidents. **The ledger and the audit log cannot be cleaned.**

    `ledger_append_only_guard` refuses UPDATE and DELETE on both, which is the whole
    reason the sweep deduplicates: an incomplete call is permanent, so it is reported
    once and counted afterwards. These tests live with the same fact - every row they
    write stays, and every assertion is scoped to its own `call_id` rather than to an
    empty table.
    """
    def wipe():
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM incident WHERE kind = 'call_started_and_not_completed'"
            )
        admin.commit()

    wipe()
    yield
    wipe()


def _reported(result, call_id: uuid.UUID) -> list[dict]:
    return [a for a in result.findings["attempted"] if a["call_id"] == str(call_id)]


async def test_an_intent_with_no_ledger_row_is_reported(admin, clean_calls):
    """The shape that has always been possible and never been visible."""
    call_id = uuid.uuid4()
    _write_intent(admin, call_id, age_seconds=_cutoff_seconds() + 60)

    async with connection() as conn:
        result = await sweeps.sweep_incomplete_calls(conn)

    assert result.status == "failed"
    assert result.findings["intent_without_ledger_row"] >= 1
    attempted = _reported(result, call_id)
    assert len(attempted) == 1
    # WHAT WAS ATTEMPTED, which is the ruling's wording. A count sends a person to a
    # query; these send them to the deal.
    assert attempted[0]["shape"] == "intent_without_ledger_row"
    assert attempted[0]["module_id"] == "assign_contract"
    assert attempted[0]["task_id"] == "task-199"
    assert attempted[0]["office_agent_id"] == str(AGENT)


async def test_a_ledger_row_with_no_outcome_is_reported(admin, clean_calls):
    call_id, trace_id = uuid.uuid4(), uuid.uuid4()
    _write_ledger(
        admin, call_id, trace_id, ts_end=None, age_seconds=_cutoff_seconds() + 60
    )

    async with connection() as conn:
        result = await sweeps.sweep_incomplete_calls(conn)

    assert result.findings["ledger_row_without_outcome"] >= 1
    mine = _reported(result, call_id)
    assert [a["shape"] for a in mine] == ["ledger_row_without_outcome"]


async def test_a_completed_call_is_not_reported(admin, clean_calls):
    """Intent plus ledger row plus an outcome. The ordinary case, and it is silent."""
    call_id = uuid.uuid4()
    trace_id = _write_intent(admin, call_id, age_seconds=_cutoff_seconds() + 60)
    _write_ledger(
        admin, call_id, trace_id, ts_end=datetime.now(UTC),
        age_seconds=_cutoff_seconds() + 60,
    )

    async with connection() as conn:
        result = await sweeps.sweep_incomplete_calls(conn)

    assert _reported(result, call_id) == []


async def test_a_call_still_in_flight_is_not_reported(admin, clean_calls):
    """A call in flight is not an orphan. The cutoff is what says so."""
    call_id = uuid.uuid4()
    _write_intent(admin, call_id, age_seconds=5)

    async with connection() as conn:
        result = await sweeps.sweep_incomplete_calls(conn)

    assert _reported(result, call_id) == []


async def test_the_cutoff_is_derived_from_the_forge_timeout(admin, clean_calls):
    """Not a number of minutes. It moves when the timeout moves, or it is remembered
    separately and stops agreeing with it."""
    async with connection() as conn:
        result = await sweeps.sweep_incomplete_calls(conn)
    assert result.findings["cutoff_seconds"] == (
        get_settings().forge_timeout_seconds * sweeps.INCOMPLETE_AFTER_TIMEOUTS
    )


async def test_it_raises_an_incident_a_human_can_act_on(admin, clean_calls):
    call_id = uuid.uuid4()
    _write_intent(admin, call_id, age_seconds=_cutoff_seconds() + 60)

    async with connection() as conn:
        await sweeps.sweep_incomplete_calls(conn)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT severity, detail FROM incident "
            " WHERE kind = 'call_started_and_not_completed' ORDER BY raised_at DESC "
            " LIMIT 1"
        )
        row = cur.fetchone()
    assert row is not None, "nothing told anybody"
    assert row[0] == "HIGH"
    assert row[1]["attempted"][0]["call_id"] == str(call_id)


async def test_it_neither_retries_nor_closes_the_row(admin, clean_calls):
    """Entry 198: never silently retried. Entry 199: it reports, and that is all.

    Closing the row would invent the outcome this sweep exists to say is unknown -
    the same error marking a proposal executed before the call would have made.
    """
    call_id, trace_id = uuid.uuid4(), uuid.uuid4()
    _write_ledger(
        admin, call_id, trace_id, ts_end=None, age_seconds=_cutoff_seconds() + 60
    )

    async with connection() as conn:
        await sweeps.sweep_incomplete_calls(conn)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT ts_end FROM agent_call_ledger WHERE call_id = %s", (call_id,)
        )
        assert cur.fetchone()[0] is None, "the sweep must not close the row"
        # Scoped to THIS call. The ledger is append-only, so every row an earlier test
        # wrote is still here - counting by task would count them too.
        cur.execute(
            "SELECT count(*) FROM agent_call_ledger WHERE call_id = %s", (call_id,)
        )
        assert cur.fetchone()[0] == 1, "the sweep must not re-send the call"


async def test_an_incomplete_call_is_reported_once_and_counted_afterwards(
    admin, clean_calls
):
    """The append-only ledger is why. Entry 199.

    `ledger_append_only_guard` refuses UPDATE and DELETE, so nothing a human does makes
    this query stop matching. A sweep that re-raised every hour for ever would be an
    incident nobody can close, which teaches people to close the page.
    """
    call_id = uuid.uuid4()
    _write_intent(admin, call_id, age_seconds=_cutoff_seconds() + 60)

    async with connection() as conn:
        first = await sweeps.sweep_incomplete_calls(conn)
        second = await sweeps.sweep_incomplete_calls(conn)

    assert first.status == "failed"
    assert _reported(first, call_id)

    assert second.status == "passed", "the second run must not re-raise"
    assert _reported(second, call_id) == []
    # STILL COUNTED, though. The condition has not gone away and the number says so.
    assert second.findings["intent_without_ledger_row"] >= 1
    assert second.findings["already_reported"] >= 1

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM incident "
            " WHERE kind = 'call_started_and_not_completed'"
        )
        assert cur.fetchone()[0] == 1, "one incident, not one an hour"


async def test_an_hour_is_its_max_age(admin):
    """The shortest interval of the five, and the reason is in the constant's comment."""
    assert sweeps.MAX_AGE[sweeps.INCOMPLETE_CALLS] == timedelta(hours=1)
