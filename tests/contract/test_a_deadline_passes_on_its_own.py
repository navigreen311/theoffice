"""A deadline passes without anybody looking, and the record says when it passed.

RULED 22 SEPTEMBER 2026 (decisions entries 156 and 157)
=======================================================

    156: *"A deadline passes on its own. A scheduled job expires overdue proposals and
    escalations. Measured: e19ca4ce expired at 05:17:15 and stayed pending until
    10:07:23, when a page load triggered it."*

    157: *"An expiry records when the deadline passed, not when it was noticed.
    Measured: the entry reads 10:07:23, which is when I opened the page."*

THE TWO THAT WOULD HAVE FAILED BEFORE
=====================================

    `test_nothing_on_the_read_path_expires_anything` and
    `test_the_record_says_when_the_deadline_passed`. Everything else here would have
    passed on the old code, because the old code expired correctly - it just only did it
    when somebody opened a page, and then wrote the wrong time on it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from broker import deadlines
from broker.db import connection
from tests.conftest import requires_db
from tests.world import build_world, teardown_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


@pytest.fixture
def world(admin: psycopg.Connection):
    """The bridged world, so a proposal has an agent identity to name."""
    build_world(admin)
    yield admin
    teardown_world(admin)


def _proposal(admin: psycopg.Connection, *, agent_id: uuid.UUID, expires_at: datetime,
              status: str = "pending") -> uuid.UUID:
    proposal_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO proposal
              (proposal_id, office_agent_id, venture_id, forge_id, module_id, task_id,
               trust_tier, payload, payload_hash, idempotency_key, trace_id, status,
               expires_at)
            VALUES (%s, %s, %s, 'cre-forge', 'assign_contract', %s, 'propose',
                    '{}'::jsonb, %s, %s, %s, %s, %s)
            """,
            (proposal_id, agent_id, VENTURE, f"t-{proposal_id.hex[:8]}",
             proposal_id.hex, proposal_id.hex, uuid.uuid4(), status, expires_at),
        )
    admin.commit()
    return proposal_id


def _an_agent(admin: psycopg.Connection) -> uuid.UUID:
    with admin.cursor() as cur:
        cur.execute("SELECT office_agent_id FROM office_agent_identity LIMIT 1")
        row = cur.fetchone()
    assert row, "this test needs an agent identity in the world"
    return row[0]


#: Fixed so the escalation tests can name a recipient and clean up after themselves.
RECIPIENT = uuid.UUID("d3ad1117-0000-4000-8000-00000000d00d")


def _a_human(admin: psycopg.Connection) -> uuid.UUID:
    """A named recipient, created here.

    `governance_names_a_human` (entry 149) requires a GOVERNANCE escalation to name
    somebody, and `build_world` creates no `office_human` rows - it builds the bridge,
    not the roster. Declared `test_fixture` because that is what it is (entry 151).
    """
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'Deadline Recipient', 'deadline@recipient.invalid', "
            "        'bearer_token', 'test_fixture', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (RECIPIENT, f"deadline-{RECIPIENT.hex}"),
        )
    admin.commit()
    return RECIPIENT


def _drop_human(admin: psycopg.Connection) -> None:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (RECIPIENT,))
    admin.commit()


def _cleanup(admin: psycopg.Connection, proposal_id: uuid.UUID) -> None:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM proposal WHERE proposal_id = %s", (proposal_id,))
    admin.commit()


# ---------------------------------------------------------------- it happens at all

async def test_the_sweep_expires_an_overdue_proposal(world, admin):
    agent = _an_agent(admin)
    overdue = _proposal(
        admin, agent_id=agent, expires_at=datetime.now(UTC) - timedelta(hours=5)
    )
    try:
        async with connection() as conn:
            found = await deadlines.run_once(conn)
        assert found["proposals_expired"] >= 1
        with admin.cursor() as cur:
            cur.execute("SELECT status FROM proposal WHERE proposal_id = %s", (overdue,))
            assert cur.fetchone()[0] == "expired"
    finally:
        _cleanup(admin, overdue)


async def test_a_proposal_inside_its_deadline_is_left_alone(world, admin):
    agent = _an_agent(admin)
    live = _proposal(
        admin, agent_id=agent, expires_at=datetime.now(UTC) + timedelta(hours=2)
    )
    try:
        async with connection() as conn:
            await deadlines.run_once(conn)
        with admin.cursor() as cur:
            cur.execute("SELECT status FROM proposal WHERE proposal_id = %s", (live,))
            assert cur.fetchone()[0] == "pending"
    finally:
        _cleanup(admin, live)


async def test_expiry_never_approves(world, admin):
    """**The most attractive shortcut on this page, and it does not exist.**

    A queue that drains itself looks like a queue being worked. An agent below
    `auto_execute` asked to act, nobody answered, and it did not act - that is the
    correct outcome, and a timeout that approved would make the trust tier a delay
    rather than a decision.
    """
    agent = _an_agent(admin)
    overdue = _proposal(
        admin, agent_id=agent, expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    try:
        async with connection() as conn:
            await deadlines.run_once(conn)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT status, decided_by, decided_at, queue_to_decision_seconds "
                "  FROM proposal WHERE proposal_id = %s", (overdue,)
            )
            status, decided_by, decided_at, seconds = cur.fetchone()
        assert status == "expired"
        assert decided_by is None and decided_at is None and seconds is None
    finally:
        _cleanup(admin, overdue)


# ------------------------------------------------- it happens without anybody looking

def test_nothing_on_the_read_path_expires_anything():
    """**LOAD-BEARING.** The defect, asserted as the absence that replaced it.

    `GET /api/proposals/queue` called `expire_overdue` before reading, so the only thing
    that ever expired anything was somebody opening a page - and the reviewer an item
    was routed to would have had it expired out from under her by the act of opening the
    page she was meant to decide it on.

    Read from the source rather than by calling the route, because the assertion is
    about what the handler CONTAINS. A behavioural test would pass on a day the sweep
    happened to have run a moment earlier.
    """
    src = (Path(__file__).resolve().parents[2] / "broker" / "app.py").read_text(
        encoding="utf-8"
    )
    parts = re.split(r"\n@app\.(get|post|put|patch|delete)\(", src)
    offenders = []
    for i in range(1, len(parts) - 1, 2):
        if parts[i] != "get":
            continue
        handler = parts[i + 1].split("\n@app.")[0]
        route = re.match(r'"([^"]+)"', parts[i + 1])
        body = re.sub(r"#.*", "", handler)          # comments may name it
        body = re.sub(r'""".*?"""', "", body, flags=re.S)
        if re.search(r"expire_overdue|run_once\(|expire_overdue_", body):
            offenders.append(route.group(1) if route else "?")
    assert offenders == [], (
        f"these GET routes expire something: {offenders}. A deadline passes on its own "
        "(entry 156); a read that writes makes expiry a side effect of attention."
    )


async def test_the_runner_keeps_going_after_a_failed_pass(monkeypatch):
    """One transient error must not leave the job stopped until somebody notices.

    That is the failure this whole entry is about, one level up: a deadline job that
    died yesterday and a deadline that passed today look identical from the outside.
    """
    calls = {"n": 0}

    async def flaky(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")
        return {"proposals_expired": 0, "escalations_expired": 0}

    monkeypatch.setattr(deadlines, "run_once", flaky)
    task = asyncio.create_task(deadlines.run_forever(interval_seconds=0.01))
    try:
        for _ in range(200):
            await asyncio.sleep(0.01)
            if calls["n"] >= 3:
                break
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    assert calls["n"] >= 3, (
        f"the loop stopped after {calls['n']} pass(es); a failed tick must not end it"
    )


async def test_a_pass_is_recorded_so_somebody_can_ask_whether_it_ran(world, admin):
    """The question anybody asks first about a deadline that did not pass.

    The verdict-ingest sweep had no record and the answer was "nobody knows"; this is
    that lesson applied before it costs anything.
    """
    async with connection() as conn:
        await deadlines.run_once(conn)
    with admin.cursor() as cur:
        cur.execute(
            "SELECT status, completed_at, findings FROM sweep_run "
            " WHERE sweep_kind = %s ORDER BY started_at DESC LIMIT 1",
            (deadlines.SWEEP_KIND,),
        )
        row = cur.fetchone()
    assert row is not None, "the sweep left no record that it ran"
    status, completed_at, findings = row
    assert status == "passed" and completed_at is not None
    body = findings if isinstance(findings, dict) else json.loads(findings)
    assert "proposals_expired" in body
    # RENAMED BY ENTRY 158. This was `escalations_overdue_without_a_deadline` - the
    # visible form of the question entry 156 left open. Four hours answered it, so the
    # counter is now simply how many are late.
    assert "escalations_overdue" in body


# ------------------------------------------- it records when the deadline passed

async def test_the_record_says_when_the_deadline_passed(world, admin):
    """**LOAD-BEARING.** Entry 159.

    The entry that produced the ruling read 10:07:23 for a deadline that had passed at
    05:17:15 - a true statement about when somebody opened a page, filed as the time an
    event happened.
    """
    agent = _an_agent(admin)
    deadline = datetime.now(UTC) - timedelta(hours=5)
    overdue = _proposal(admin, agent_id=agent, expires_at=deadline)
    try:
        async with connection() as conn:
            await deadlines.run_once(conn)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT subject, ts FROM audit_log "
                " WHERE event_type = 'proposal_expired' "
                "   AND subject->>'proposal_id' = %s", (str(overdue),)
            )
            row = cur.fetchone()
        assert row is not None, "no entry was written"
        subject = row[0] if isinstance(row[0], dict) else json.loads(row[0])

        assert datetime.fromisoformat(subject["expired_at"]) == deadline, (
            "the entry records some other moment as the expiry"
        )
        # AND the notice time is there too, separately. Both facts, neither pretending
        # to be the other.
        noticed = datetime.fromisoformat(subject["noticed_at"])
        assert noticed > deadline
        assert subject["lag_seconds"] == pytest.approx(
            (noticed - deadline).total_seconds(), abs=1
        )
    finally:
        _cleanup(admin, overdue)


async def test_the_chain_timestamp_is_still_chain_time(world, admin):
    """`ts` is when the row was written and stays so.

    Entry 159 is about the SUBJECT. Backdating `ts` would put a row in the hash chain
    claiming to predate rows already in it, which breaks the one property the chain has
    - so the fix is an extra field, not a rewritten one.
    """
    agent = _an_agent(admin)
    deadline = datetime.now(UTC) - timedelta(hours=9)
    overdue = _proposal(admin, agent_id=agent, expires_at=deadline)
    try:
        async with connection() as conn:
            await deadlines.run_once(conn)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT ts FROM audit_log WHERE event_type = 'proposal_expired' "
                "   AND subject->>'proposal_id' = %s", (str(overdue),)
            )
            ts = cur.fetchone()[0]
        assert ts > deadline, "ts was backdated; it must say when the entry was written"
    finally:
        _cleanup(admin, overdue)


# ------------------------------------------------- escalations, and the open question

async def test_an_escalation_with_no_deadline_never_expires(world, admin):
    """**The rule this does NOT invent.**

    Entry 158 says a job expires overdue escalations. Nothing anywhere says what makes
    one overdue - not the Pack, not the schema, not the ledger - so the column has no
    default and the sweep expires nothing. A twenty-four-hour default here would be a
    number nobody chose, arriving through a migration.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM escalation_record WHERE expires_at IS NOT NULL"
        )
        assert cur.fetchone()[0] == 0, (
            "something gave an escalation a deadline; entry 156 leaves that to Ivan"
        )

    async with connection() as conn:
        found = await deadlines.run_once(conn)
    assert found["escalations_expired"] == 0


async def test_an_escalation_that_has_a_deadline_does_expire(world, admin):
    """The mechanism is real, so the day a deadline is ruled nothing else has to change."""
    escalation_id = uuid.uuid4()
    deadline = datetime.now(UTC) - timedelta(hours=2)
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO escalation_record
              (escalation_id, venture_id, department, path, kind, reason, raised_by,
               raised_by_kind, routed_to_name, routed_to_human, expires_at)
            VALUES (%s, %s, 'research', 'governance', 'certification',
                    'drill: does the deadline pass on its own', %s, 'agent',
                    'Somebody Named', %s, %s)
            """,
            (escalation_id, VENTURE, uuid.uuid4(), _a_human(admin), deadline),
        )
    admin.commit()
    try:
        async with connection() as conn:
            found = await deadlines.run_once(conn)
        assert found["escalations_expired"] >= 1
        with admin.cursor() as cur:
            cur.execute(
                "SELECT expired_at FROM escalation_record WHERE escalation_id = %s",
                (escalation_id,),
            )
            expired_at = cur.fetchone()[0]
        assert expired_at == deadline, "the row records the notice time, not the deadline"
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM escalation_record WHERE escalation_id = %s",
                (escalation_id,),
            )
        admin.commit()
        _drop_human(admin)


async def test_a_received_escalation_is_not_expired(world, admin):
    """Receipt is a person saying they have it. A timeout does not overwrite that.

    What is late after a receipt is the ANSWER, which is a different deadline and a
    different question - and not one entry 156 rules on.
    """
    escalation_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO escalation_record
              (escalation_id, venture_id, department, path, kind, reason, raised_by,
               raised_by_kind, routed_to_name, routed_to_human, expires_at, received_at,
               received_by)
            VALUES (%s, %s, 'research', 'governance', 'certification',
                    'received before the deadline', %s, 'agent', 'Somebody Named',
                    %s, %s, now(), %s)
            """,
            (escalation_id, VENTURE, uuid.uuid4(), _a_human(admin),
             datetime.now(UTC) - timedelta(hours=2), uuid.uuid4()),
        )
    admin.commit()
    try:
        async with connection() as conn:
            await deadlines.run_once(conn)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT expired_at FROM escalation_record WHERE escalation_id = %s",
                (escalation_id,),
            )
            assert cur.fetchone()[0] is None
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM escalation_record WHERE escalation_id = %s",
                (escalation_id,),
            )
        admin.commit()
        _drop_human(admin)


async def test_an_expiry_cannot_record_a_time_that_is_not_the_deadline(world, admin):
    """0055's CHECK. Entry 159 as a constraint rather than a convention.

    The job could write `now()` into `expired_at` and no reader would know. This makes
    that impossible instead of discouraged.
    """
    escalation_id = uuid.uuid4()
    deadline = datetime.now(UTC) - timedelta(hours=3)
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO escalation_record
              (escalation_id, venture_id, department, path, kind, reason, raised_by,
               raised_by_kind, routed_to_name, routed_to_human, expires_at)
            VALUES (%s, %s, 'research', 'governance', 'certification', 'check test',
                    %s, 'agent', 'Somebody Named', %s, %s)
            """,
            (escalation_id, VENTURE, uuid.uuid4(), _a_human(admin), deadline),
        )
    admin.commit()
    try:
        with pytest.raises(
            psycopg.errors.CheckViolation, match="an_expiry_is_the_deadline"
        ), admin.cursor() as cur:
            cur.execute(
                "UPDATE escalation_record SET expired_at = now() WHERE escalation_id = %s",
                (escalation_id,),
            )
        admin.rollback()
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM escalation_record WHERE escalation_id = %s",
                (escalation_id,),
            )
        admin.commit()
        _drop_human(admin)
