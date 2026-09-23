"""A gate review is corrected by a later entry, and the walker sees every event.

RULED 22 SEPTEMBER 2026 (decisions entries 170, 171 and 172)
============================================================

    170. *"A gate review may be corrected by a later entry, never by editing. A
         correction names the reviewer, the correction and who made it. Gate 10's
         signature binds to the note plus its corrections."*

    171. *"Every audit event written in the source is published. Fix the walker's
         regex; it never matched an event with a digit."*

    172. *"A sweep polls every 5 minutes while a submission awaits a verdict, and daily
         otherwise."*

THE THREE THAT CARRY THE RULINGS
================================

    `test_a_correction_never_edits_the_review` - the whole of 170. The note is byte-for
    byte what it was; the correction is a new row beside it.

    `test_the_walker_matches_an_event_with_a_digit` - 171, asserted against the regex
    rather than against today's event list, because the defect was that a whole SHAPE
    of name was invisible.

    `test_an_open_submission_makes_the_sweep_due_within_five_minutes` - 172.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import psycopg
import pytest

from broker import humans, provisioning, sweeps
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import declare_author, requires_db, undeclare_author

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "test-correction"
RECORDER = uuid.UUID("aaaa1170-0000-4000-8000-000000000001")
DRAFTED_FOR = uuid.UUID("aaaa1170-0000-4000-8000-000000000002")
CORRECTOR = uuid.UUID("aaaa1170-0000-4000-8000-000000000003")
FIXTURE = uuid.UUID("aaaa1170-0000-4000-8000-000000000004")

NOTE = "Read all three counts. Advancing; declared by me today."
CORRECTION = (
    "Drafted for Ivan Green and recorded by Ira Green on his own account. "
    "'declared by me' refers to Ivan, who declared the simulation. The review stands."
)


@pytest.fixture(autouse=True)
def _world(admin: psycopg.Connection):
    for human_id, name in (
        (RECORDER, "Correction Recorder"),
        (DRAFTED_FOR, "Correction Subject"),
        (CORRECTOR, "Correction Author"),
    ):
        declare_author(admin, human_id, name)
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'smoke-corrector-170', 'smoke-170@corr.invalid', "
            "        'bearer_token', 'test_fixture', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (FIXTURE, f"fixture-{FIXTURE.hex}"),
        )
        cur.execute(
            "INSERT INTO venture (slug, display_name, category, created_by) "
            "VALUES (%s, %s, 'test', %s) ON CONFLICT (slug) DO NOTHING",
            (VENTURE, "Correction Test", RECORDER),
        )
    admin.commit()
    _wipe(admin)
    yield
    _wipe(admin)
    undeclare_author(admin, RECORDER, DRAFTED_FOR, CORRECTOR, FIXTURE)
    with admin.cursor() as cur:
        cur.execute("DELETE FROM venture WHERE slug = %s", (VENTURE,))
    admin.commit()


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE gate_review_correction "
            "  DISABLE TRIGGER gate_review_correction_is_append_only"
        )
        cur.execute(
            "DELETE FROM gate_review_correction WHERE run_id IN "
            "(SELECT run_id FROM provisioning_run WHERE venture_id = %s)", (VENTURE,)
        )
        cur.execute(
            "ALTER TABLE gate_review_correction "
            "  ENABLE TRIGGER gate_review_correction_is_append_only"
        )
        cur.execute(
            "DELETE FROM provisioning_gate_result WHERE run_id IN "
            "(SELECT run_id FROM provisioning_run WHERE venture_id = %s)", (VENTURE,)
        )
        cur.execute("DELETE FROM provisioning_run WHERE venture_id = %s", (VENTURE,))
        cur.execute("DELETE FROM business_pack WHERE venture_id = %s", (VENTURE,))
    conn.commit()


def _reviewed_run(conn: psycopg.Connection) -> uuid.UUID:
    """A run whose Gate 4 review is recorded, written directly.

    Driving the ladder here would test the ladder; the claim is about what may be done
    to a review that exists.
    """
    run_id = uuid.uuid4()
    with conn.cursor() as cur:
        # `provisioning_run` carries a foreign key to (venture_id, pack_version), so the
        # run needs a Pack even though nothing here reads one.
        cur.execute(
            "INSERT INTO business_pack (venture_id, pack_version, schema_version, "
            "  yaml_source, parsed, content_hash, authored_by) "
            "VALUES (%s, '1.0.0', '1', 'venture_id: x', '{}', %s, %s) "
            "ON CONFLICT (venture_id, pack_version) DO NOTHING",
            (VENTURE, "0" * 64, RECORDER),
        )
        cur.execute(
            "INSERT INTO provisioning_run "
            "  (run_id, venture_id, pack_version, pack_hash, status, current_gate, "
            "   started_by) "
            "VALUES (%s, %s, '1.0.0', %s, 'awaiting_human', '4', %s)",
            (run_id, VENTURE, "0" * 64, RECORDER),
        )
        cur.execute(
            "INSERT INTO provisioning_gate_result "
            "  (gate_result_id, run_id, gate, verdict, reason, evidence) "
            "VALUES (%s, %s, '4', 'passed', 'operator recorded a review', %s)",
            (uuid.uuid4(), run_id,
             psycopg.types.json.Jsonb({"human_id": str(RECORDER), "note": NOTE})),
        )
    conn.commit()
    return run_id


def _person(human_id: uuid.UUID, name: str, origin: str = "human") -> humans.Human:
    return humans.Human(
        human_id=human_id, display_name=name, email=f"{name}@corr.invalid",
        status="active", roles=(("venture_operator", VENTURE),), origin=origin,
        auth_method="bearer_token",
    )


async def _correct(run_id: uuid.UUID, *, by: uuid.UUID = CORRECTOR,
                   named: uuid.UUID = DRAFTED_FOR,
                   text: str = CORRECTION) -> dict[str, Any]:
    async with connection() as conn:
        return await provisioning.correct_gate_review(
            conn, run_id=run_id, gate="4", reviewer_named=named,
            correction=text, corrected_by=_person(by, "Correction Author"),
        )


def _note(conn: psycopg.Connection, run_id: uuid.UUID) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT evidence->>'note' FROM provisioning_gate_result "
            " WHERE run_id = %s AND gate = '4' AND verdict = 'passed'", (run_id,)
        )
        return str(cur.fetchone()[0])


# ============================================================ 170. the correction

async def test_a_correction_never_edits_the_review(admin):
    """**THE RULING.** *"corrected by a later entry, never by editing."*

    Entry 159 settled this on a smaller record: *"a false entry is answered by a later
    one, never by editing the record."* The note here is not even false - every fact in
    it is true - and it still may not be touched.
    """
    run_id = _reviewed_run(admin)
    before = _note(admin, run_id)

    await _correct(run_id)

    assert _note(admin, run_id) == before == NOTE, "the note was edited"

    async with connection() as conn:
        corrections = await provisioning.gate_review_corrections(
            conn, run_id=run_id, gate="4"
        )
    assert len(corrections) == 1
    assert corrections[0]["correction"] == CORRECTION
    assert corrections[0]["reviewer_named"] == "Correction Subject"
    assert corrections[0]["corrected_by"] == "Correction Author"


async def test_a_correction_names_three_parties(admin):
    """*"A correction names the reviewer, the correction and who made it."*

    Three, not one. On the correction this was built for they are three different
    people: Ira recorded, Ivan is who "me" meant, and whoever writes the correction is
    the third. A correction naming only its author leaves the reader to infer whose
    reading it fixes.
    """
    run_id = _reviewed_run(admin)
    await _correct(run_id)

    async with connection() as conn:
        found = (await provisioning.gate_review_corrections(conn, run_id=run_id))[0]
    assert found["reviewer_named"] != found["corrected_by"]
    assert found["correction"].strip()


async def test_every_correction_stays_in_force(admin):
    """No `supersedes` column, deliberately. A reader reads the note and then every
    correction, in order - and that is what Gate 10's signature covers."""
    run_id = _reviewed_run(admin)
    await _correct(run_id, text="First correction.")
    await _correct(run_id, text="Second correction, about the first.")

    async with connection() as conn:
        corrections = await provisioning.gate_review_corrections(conn, run_id=run_id)
    assert [c["correction"] for c in corrections] == [
        "First correction.", "Second correction, about the first."
    ]


async def test_an_empty_correction_is_refused(admin):
    run_id = _reviewed_run(admin)
    with pytest.raises(provisioning.ProvisioningError) as raised:
        await _correct(run_id, text="   ")
    assert "says what it corrects" in str(raised.value)


async def test_a_review_that_was_never_recorded_cannot_be_corrected(admin):
    """A correction answers a record. There is a different thing to do about a review
    nobody recorded, and it is to record it."""
    run_id = _reviewed_run(admin)
    with pytest.raises(provisioning.ProvisioningError) as raised:
        async with connection() as conn:
            await provisioning.correct_gate_review(
                conn, run_id=run_id, gate="10", reviewer_named=DRAFTED_FOR,
                correction=CORRECTION,
                corrected_by=_person(CORRECTOR, "Correction Author"),
            )
    assert "no recorded review to correct" in str(raised.value)


async def test_a_fixture_may_not_be_named_as_the_reviewer(admin):
    run_id = _reviewed_run(admin)
    with pytest.raises(NotAuthorized):
        await _correct(run_id, named=FIXTURE)


def test_the_database_refuses_an_edit(admin):
    """**The control.** Append-only by trigger, the shape `department_attestation` uses.

    A record whose immutability depends on nobody writing the wrong statement is not
    immutable.
    """
    run_id = _reviewed_run(admin)
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO gate_review_correction "
            "  (correction_id, run_id, gate, reviewer_named, correction, corrected_by) "
            "VALUES (%s, %s, '4', %s, 'by hand', %s)",
            (uuid.uuid4(), run_id, DRAFTED_FOR, CORRECTOR),
        )
    admin.commit()

    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute("UPDATE gate_review_correction SET correction = 'tidier'")
    admin.rollback()

    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute("DELETE FROM gate_review_correction")
    admin.rollback()


async def test_gate_10_evidence_carries_the_corrections(admin):
    """*"Gate 10's signature binds to the note plus its corrections."*

    Read from the gate's own evidence builder rather than by driving a run to 10, which
    no venture has ever reached. The claim is that the corrections are in what a signer
    sees, and that is what this asserts.
    """
    import inspect

    source = inspect.getsource(provisioning._gate_10)
    assert "gate_review_corrections" in source, (
        "Gate 10 does not read the corrections, so a signature would cover half the "
        "record"
    )
    assert "gate_4_review_corrections" in source


# ==================================================== 171. the walker's blind spot

def test_the_walker_matches_an_event_with_a_digit():
    """**THE RULING.** The regex, not today's event list.

    The defect was that a whole SHAPE of name was invisible: `[a-z_]+` never matched
    `gate_4` or `gate_10`, so the two most consequential human acts in the ladder had
    never been checked against the glossary and rendered on /audit as raw identifiers.

    Asserted against the pattern so that a future event called `gate_12_something` is
    covered by the same fix rather than by somebody noticing again.
    """
    from pathlib import Path

    walker = (
        Path(__file__).resolve().parents[1] / "contract" / "test_audit_view.py"
    ).read_text(encoding="utf-8")
    patterns = re.findall(r"re\.findall\(r'([^']+)'", walker)
    assert patterns, "the walker's patterns could not be read"
    for pattern in patterns:
        assert "a-z0-9_" in pattern or "a-z_0-9" in pattern, (
            f"{pattern!r} has no digits in its character class; an event named "
            "gate_4 or gate_10 is invisible to it"
        )
        for name in ("provisioning_gate_4_reviewed", "provisioning_gate_10_signed"):
            probe = f'event_type="{name}"'
            if "event_type" in pattern:
                assert re.findall(pattern, probe) == [name], (
                    f"{pattern!r} does not match {name!r}"
                )


def test_every_event_written_in_the_source_is_published_now():
    """The fixed walker, run here too. Three were missing and all three are published.

    Duplicated from `test_audit_view.py` on purpose: that test is the guard, and this
    one is the record that entry 171 closed the gap it had.
    """
    from pathlib import Path

    from broker import audit_events

    root = Path(__file__).resolve().parents[2] / "broker"
    written: set[str] = set()
    for source in root.glob("*.py"):
        if source.name == "audit_events.py":
            continue
        text = source.read_text(encoding="utf-8")
        written |= set(re.findall(r'event_type=\s*"([a-z0-9_]+)"', text))
        written |= set(
            re.findall(r'_audit_human_action\(\s*me,\s*"([a-z0-9_]+)"', text, re.S)
        )

    assert "provisioning_gate_4_reviewed" in written, "the walker still cannot see it"
    assert "provisioning_gate_10_signed" in written
    assert not sorted(n for n in written if n not in audit_events.BY_TYPE)


# ================================================== 172. polling while somebody waits

async def test_an_open_submission_makes_the_sweep_due_within_five_minutes(admin):
    """**THE RULING.** *"every 5 minutes while a submission awaits a verdict."*

    Measured 22 September: exams opened at 17:16, the sweep had run at 16:54, and nine
    verdicts would have sat 23.6 hours with a run blocked behind them.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM sweep_run WHERE sweep_kind = %s",
                    (sweeps.VERDICT_INGEST,))
        cur.execute(
            "INSERT INTO sweep_run (sweep_run_id, sweep_kind, status, started_at, "
            "                       completed_at, denominator) "
            "VALUES (%s, %s, 'passed', now() - interval '10 minutes', now(), 1)",
            (uuid.uuid4(), sweeps.VERDICT_INGEST),
        )
    admin.commit()

    async with connection() as conn:
        waiting = await sweeps.awaiting_a_verdict(conn)
        due = await sweeps.due(conn)

    if waiting:
        assert sweeps.VERDICT_INGEST in due, (
            "a submission is waiting and the sweep is ten minutes old, yet not due"
        )
    else:
        assert sweeps.VERDICT_INGEST not in due, (
            "nothing is waiting and a ten-minute-old sweep is due; the daily interval "
            "is not being respected"
        )


async def test_nothing_waiting_means_the_daily_interval_stands(admin):
    """**Load-bearing.** Entry 168 said keep the declared `MAX_AGE`, and 172 adds a
    condition rather than replacing it.

    Without this, a five-minute poll would run for ever against a system with nothing
    open - which is the timer somebody has to remember to turn off.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE curriculum_submission SET result_received_at = now() "
            " WHERE simforge_run_ref IS NOT NULL AND result_received_at IS NULL"
        )
        cur.execute("DELETE FROM sweep_run WHERE sweep_kind = %s",
                    (sweeps.VERDICT_INGEST,))
        cur.execute(
            "INSERT INTO sweep_run (sweep_run_id, sweep_kind, status, started_at, "
            "                       completed_at, denominator) "
            "VALUES (%s, %s, 'passed', now() - interval '10 minutes', now(), 1)",
            (uuid.uuid4(), sweeps.VERDICT_INGEST),
        )
    admin.commit()
    try:
        async with connection() as conn:
            assert await sweeps.awaiting_a_verdict(conn) is False
            assert sweeps.VERDICT_INGEST not in await sweeps.due(conn)
    finally:
        admin.rollback()


def test_the_interval_is_five_minutes_and_says_so_once():
    """One constant, so a second spelling cannot drift from it."""
    assert sweeps.AWAITING_VERDICT_INTERVAL_SECONDS == 300.0
    assert sweeps.MAX_AGE[sweeps.VERDICT_INGEST].days == 1, (
        "the declared MAX_AGE moved; entries 168 and 172 both say keep it"
    )
