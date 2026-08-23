"""Teach the verifier to see tail truncation.

Found by test. A hash chain detects content tampering and deletion *between*
entries, because the survivors stop linking. Deleting the newest N entries breaks
nothing: the remaining chain is internally perfect. `ok = true` on a truncated
audit log is the most dangerous possible false negative - it is the shape an
attacker would choose.

The sequence is the corroborating witness. It has advanced past max(audit_id).

Deliberately NOT folded into `ok`: a rolled-back INSERT also consumes a sequence
value, so a nonzero gap has an innocent explanation and a guilty one. Reporting it
as tampering would cry wolf on every rolled-back transaction, and a verifier that
cries wolf is one people learn to ignore. It is reported as its own number, for a
human to explain, with `ok` reserved for a provable break.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # last_value is needed to detect truncation. Reading it is harmless; office_app
    # already holds USAGE (it consumes the sequence through the chain trigger).
    op.execute("GRANT SELECT ON SEQUENCE audit_log_audit_id_seq TO office_app")

    op.execute("DROP FUNCTION IF EXISTS audit_log_verify_chain()")
    op.execute("""
        CREATE FUNCTION audit_log_verify_chain()
        RETURNS TABLE (
          ok                   BOOLEAN,
          checked_count        BIGINT,
          first_break_audit_id BIGINT,
          tail_gap             BIGINT,
          reason               TEXT
        ) LANGUAGE plpgsql STABLE AS $$
        DECLARE
          r             RECORD;
          v_expect_prev TEXT := audit_log_genesis_hash();
          v_expect_id   BIGINT := NULL;
          v_count       BIGINT := 0;
          v_recomputed  TEXT;
          v_max_id      BIGINT;
          v_seq_last    BIGINT;
          v_seq_called  BOOLEAN;
          v_tail_gap    BIGINT;
        BEGIN
          SELECT last_value, is_called INTO v_seq_last, v_seq_called
            FROM audit_log_audit_id_seq;
          SELECT COALESCE(max(audit_id), 0) INTO v_max_id FROM audit_log;

          -- is_called = false means the sequence has never been consumed, so
          -- last_value is the *next* value rather than the last issued one.
          v_tail_gap := CASE WHEN v_seq_called THEN v_seq_last ELSE 0 END - v_max_id;
          IF v_tail_gap < 0 THEN
            v_tail_gap := 0;
          END IF;

          FOR r IN SELECT * FROM audit_log ORDER BY audit_id LOOP

            IF r.prev_hash <> v_expect_prev THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id, v_tail_gap,
                format('prev_hash mismatch at %s: expected %s, found %s '
                       '(a preceding entry was altered or removed)',
                       r.audit_id, v_expect_prev, r.prev_hash);
              RETURN;
            END IF;

            v_recomputed := audit_log_compute_hash(
              r.audit_id, r.event_type, r.actor_type, r.actor_id,
              r.venture_id, r.subject, r.trace_id, r.ts, r.prev_hash);

            IF v_recomputed <> r.entry_hash THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id, v_tail_gap,
                format('entry_hash mismatch at %s: stored %s, recomputed %s '
                       '(this entry''s contents were altered)',
                       r.audit_id, r.entry_hash, v_recomputed);
              RETURN;
            END IF;

            IF v_expect_id IS NOT NULL AND r.audit_id <> v_expect_id THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id, v_tail_gap,
                format('audit_id gap: expected %s, found %s (an entry was deleted)',
                       v_expect_id, r.audit_id);
              RETURN;
            END IF;

            v_expect_prev := r.entry_hash;
            v_expect_id   := r.audit_id + 1;
            v_count       := v_count + 1;
          END LOOP;

          IF v_tail_gap > 0 THEN
            RETURN QUERY SELECT TRUE, v_count, NULL::BIGINT, v_tail_gap,
              format('chain verified over %s entries, but the sequence is %s ahead '
                     'of max(audit_id) - either the newest %s entries were deleted, '
                     'or that many inserts rolled back. INVESTIGATE.',
                     v_count, v_tail_gap, v_tail_gap);
            RETURN;
          END IF;

          RETURN QUERY SELECT TRUE, v_count, NULL::BIGINT, 0::BIGINT,
            format('chain verified over %s entries', v_count);
        END $$
    """)

    op.execute("GRANT EXECUTE ON FUNCTION audit_log_verify_chain() TO office_app")
    op.execute("""
        COMMENT ON FUNCTION audit_log_verify_chain() IS
        'Detects content tampering, link tampering, mid-chain deletion, and - via '
        'tail_gap - truncation of the newest entries, which the chain alone cannot '
        'see. tail_gap is advisory, not a verdict: a rolled-back insert produces one '
        'innocently. Reports checked_count as the denominator.'
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS audit_log_verify_chain()")
    op.execute("REVOKE SELECT ON SEQUENCE audit_log_audit_id_seq FROM office_app")
    op.execute("""
        CREATE FUNCTION audit_log_verify_chain()
        RETURNS TABLE (
          ok BOOLEAN, checked_count BIGINT, first_break_audit_id BIGINT, reason TEXT
        ) LANGUAGE plpgsql STABLE AS $$
        DECLARE
          r RECORD;
          v_expect_prev TEXT := audit_log_genesis_hash();
          v_count BIGINT := 0;
          v_recomputed TEXT;
        BEGIN
          FOR r IN SELECT * FROM audit_log ORDER BY audit_id LOOP
            IF r.prev_hash <> v_expect_prev THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id, 'prev_hash mismatch';
              RETURN;
            END IF;
            v_recomputed := audit_log_compute_hash(
              r.audit_id, r.event_type, r.actor_type, r.actor_id,
              r.venture_id, r.subject, r.trace_id, r.ts, r.prev_hash);
            IF v_recomputed <> r.entry_hash THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id, 'entry_hash mismatch';
              RETURN;
            END IF;
            v_expect_prev := r.entry_hash;
            v_count := v_count + 1;
          END LOOP;
          RETURN QUERY SELECT TRUE, v_count, NULL::BIGINT,
            format('chain verified over %s entries', v_count);
        END $$
    """)
    op.execute("GRANT EXECUTE ON FUNCTION audit_log_verify_chain() TO office_app")
