"""Invariant 2 - the audit chain is tamper-evident.

The tamper tests run as superuser on purpose. The threat model is not "office_app
edits a row" - role grants already stop that, and test_append_only proves it. The
threat model is someone with database-level access altering history. The chain is
what makes that detectable rather than preventable.
"""

import threading
import uuid
from itertools import pairwise

import psycopg
import pytest

from tests.conftest import insert_audit, requires_db, tail_gap, verify_chain

pytestmark = [requires_db, pytest.mark.db]

GENESIS = "0" * 64


def test_empty_chain_verifies_with_zero_count(app, clean_audit):
    """An empty table is 'ok', but the count is what distinguishes it from a real one."""
    ok, count, break_id, _reason = verify_chain(app)
    assert ok is True
    assert count == 0
    assert break_id is None


def test_first_entry_links_to_genesis(app, clean_audit):
    insert_audit(app)
    with app.cursor() as cur:
        cur.execute("SELECT prev_hash FROM audit_log ORDER BY audit_id LIMIT 1")
        row = cur.fetchone()
    assert row is not None
    assert row[0] == GENESIS


def test_chain_verifies_over_many_entries(app, clean_audit):
    for i in range(25):
        insert_audit(app, event_type=f"event_{i}")

    ok, count, break_id, reason = verify_chain(app)
    assert ok is True, reason
    assert count == 25
    assert break_id is None
    assert "25" in reason


def test_each_entry_links_to_its_predecessor(app, clean_audit):
    for _ in range(5):
        insert_audit(app)

    with app.cursor() as cur:
        cur.execute("SELECT audit_id, prev_hash, entry_hash FROM audit_log ORDER BY audit_id")
        rows = cur.fetchall()

    assert rows[0][1] == GENESIS
    for prev, curr in pairwise(rows):
        assert curr[1] == prev[2], f"entry {curr[0]} does not link to {prev[0]}"


def test_caller_cannot_choose_its_own_hashes(app, clean_audit):
    """A writer supplying prev_hash/entry_hash must not be able to forge position."""
    forged = "f" * 64
    with app.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log
              (event_type, actor_type, actor_id, subject, prev_hash, entry_hash)
            VALUES ('forge_attempt', 'agent', %s, '{}'::jsonb, %s, %s)
            RETURNING prev_hash, entry_hash
            """,
            (str(uuid.uuid4()), forged, forged),
        )
        row = cur.fetchone()
    app.commit()
    assert row is not None
    assert row[0] == GENESIS, "supplied prev_hash was not overwritten"
    assert row[1] != forged, "supplied entry_hash was not overwritten"


def test_content_tampering_is_detected(admin, app, clean_audit):
    """Alter a row's payload as superuser; the verifier must name that exact row."""
    for _ in range(5):
        insert_audit(app)
    target = 3

    with admin.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute(
            "UPDATE audit_log SET subject = '{\"k\": \"TAMPERED\"}'::jsonb WHERE audit_id = %s",
            (target,),
        )
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    admin.commit()

    ok, count, break_id, reason = verify_chain(app)
    assert ok is False
    assert break_id == target
    assert "entry_hash mismatch" in reason
    assert count == target - 1, "count should report how many entries verified before the break"


def test_deletion_is_detected(admin, app, clean_audit):
    """Delete a middle row. The surviving links still join, so the audit_id gap is
    the only thing that reveals it - which is why the verifier checks for one."""
    for _ in range(6):
        insert_audit(app)

    with admin.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log WHERE audit_id = 4")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    admin.commit()

    ok, _count, break_id, reason = verify_chain(app)
    assert ok is False
    assert break_id == 5
    assert "prev_hash mismatch" in reason or "audit_id gap" in reason


def test_tail_deletion_is_reported_as_tail_gap(admin, app, clean_audit):
    """Deleting the newest entries leaves a chain that verifies perfectly.

    That is the most dangerous false negative available, and the shape an attacker
    would choose. Only the sequence position reveals it, so the verifier reports
    it separately from `ok`.
    """
    for _ in range(5):
        insert_audit(app)

    assert tail_gap(app) == 0, "no gap before tampering"

    with admin.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log WHERE audit_id IN (4, 5)")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    admin.commit()

    ok, count, break_id, reason = verify_chain(app)
    assert ok is True, "link-walking alone genuinely cannot see a tail deletion"
    assert count == 3
    assert break_id is None

    assert tail_gap(app) == 2, "the sequence is the only witness to a tail deletion"
    assert "INVESTIGATE" in reason
    assert "sequence" in reason.lower()


def test_tail_gap_is_advisory_not_a_verdict(app, clean_audit):
    """A rolled-back insert also consumes a sequence value.

    tail_gap must stay out of `ok` for exactly this reason - otherwise every
    rolled-back transaction reads as tampering and the signal gets ignored.
    """
    insert_audit(app)

    with app.cursor() as cur:
        cur.execute(
            "INSERT INTO audit_log (event_type, actor_type, actor_id, subject) "
            "VALUES ('rolled_back', 'system', gen_random_uuid(), '{}'::jsonb)"
        )
    app.rollback()

    ok, count, _, _ = verify_chain(app)
    assert ok is True, "a rolled-back insert must not read as tampering"
    assert count == 1
    assert tail_gap(app) == 1, "the innocent case produces a gap too - hence advisory"


def test_hash_is_timezone_independent(app, clean_audit):
    """Recomputing under a different session TimeZone must give the same hash.

    timestamptz::text renders in the session zone; if the payload used it, a
    verifier in another zone would report false tampering.
    """
    insert_audit(app)

    hashes = []
    for tz in ("UTC", "America/Los_Angeles", "Asia/Tokyo"):
        with app.cursor() as cur:
            cur.execute(f"SET TIME ZONE '{tz}'")
            cur.execute(
                """
                SELECT audit_log_compute_hash(audit_id, event_type, actor_type, actor_id,
                                              venture_id, subject, trace_id, ts, prev_hash)
                FROM audit_log ORDER BY audit_id LIMIT 1
                """
            )
            row = cur.fetchone()
        assert row is not None
        hashes.append(row[0])
    app.rollback()

    assert len(set(hashes)) == 1, f"hash varied with session TimeZone: {hashes}"


def test_delimiter_injection_cannot_collide(app, clean_audit):
    """Two entries whose fields differ only by where a delimiter falls must differ.

    This is the concrete failure that string-concatenation hashing allows.
    """
    insert_audit(app, event_type="a|b", subject='{"x": "c"}')
    insert_audit(app, event_type="a", subject='{"x": "b|c"}')

    with app.cursor() as cur:
        cur.execute("SELECT entry_hash FROM audit_log ORDER BY audit_id")
        rows = cur.fetchall()
    assert rows[0][0] != rows[1][0]

    ok, count, _, reason = verify_chain(app)
    assert ok is True, reason
    assert count == 2


def test_concurrent_writers_do_not_fork_the_chain(app_dsn, admin, clean_audit):
    """Twelve threads inserting at once must produce one linear chain."""
    n = 12
    errors: list[Exception] = []
    barrier = threading.Barrier(n)

    def write() -> None:
        try:
            with psycopg.connect(app_dsn) as conn:
                barrier.wait(timeout=15)
                insert_audit(conn, event_type="concurrent")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"concurrent writes failed: {errors}"

    with psycopg.connect(app_dsn) as conn:
        ok, count, _break_id, reason = verify_chain(conn)
    assert ok is True, reason
    assert count == n


def test_repeatable_read_is_rejected_not_silently_forked(app_dsn, clean_audit):
    """Under REPEATABLE READ the trigger can read a stale tip.

    That must surface as a constraint violation, never as a silently forked chain.
    This is the behaviour the UNIQUE(prev_hash) backstop exists for.
    """
    insert_audit_ok = False
    with psycopg.connect(app_dsn) as seed:
        insert_audit(seed, event_type="seed")
        insert_audit_ok = True
    assert insert_audit_ok

    conn_a = psycopg.connect(app_dsn)
    conn_b = psycopg.connect(app_dsn)
    try:
        for c in (conn_a, conn_b):
            c.execute("SET default_transaction_isolation = 'repeatable read'")
            c.commit()

        # Both take their snapshot before either writes.
        conn_a.execute("SELECT 1")
        conn_b.execute("SELECT 1")

        conn_a.execute(
            "INSERT INTO audit_log (event_type, actor_type, actor_id, subject) "
            "VALUES ('a', 'system', gen_random_uuid(), '{}'::jsonb)"
        )
        conn_a.commit()

        with pytest.raises(psycopg.Error) as exc:
            conn_b.execute(
                "INSERT INTO audit_log (event_type, actor_type, actor_id, subject) "
                "VALUES ('b', 'system', gen_random_uuid(), '{}'::jsonb)"
            )
            conn_b.commit()
        conn_b.rollback()

        msg = str(exc.value).lower()
        assert "unique" in msg or "duplicate key" in msg or "serial" in msg, (
            f"expected a constraint or serialization failure, got: {exc.value}"
        )
    finally:
        conn_a.close()
        conn_b.close()

    with psycopg.connect(app_dsn) as conn:
        ok, _, _, reason = verify_chain(conn)
    assert ok is True, f"chain must remain intact after the rejected write: {reason}"
