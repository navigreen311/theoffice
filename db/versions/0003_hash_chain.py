"""Tamper-evident hash chain on audit_log.

Invariant 2. Until Forges support per-principal identity, this chain is the only
thing standing between "we have an audit trail" and "we have a table someone
could have edited".

Three decisions worth stating, because each prevents a specific silent failure:

  1. audit_id is assigned INSIDE the trigger, under the advisory lock - not by a
     column DEFAULT. If the sequence were consumed before the lock, two writers
     could take ids in one order and the lock in the other, leaving chain order
     disagreeing with audit_id order. The chain would verify row-by-row and still
     be wrong.

  2. The hashed payload is built with jsonb_build_object, not string concatenation.
     Concatenation with a delimiter is forgeable: a field containing the delimiter
     lets two different entries produce identical payloads. jsonb escapes for us.

  3. The timestamp is normalised to an explicit UTC format string. timestamptz::text
     renders in the session TimeZone, so a verifier running in a different session
     would recompute different hashes and report false tampering.

Concurrency: writers serialise on an advisory lock, and UNIQUE(prev_hash) makes a
fork a constraint violation rather than a corruption. Audit writes must run at
READ COMMITTED - under REPEATABLE READ the trigger's snapshot predates a
concurrently committed row, so it would chain onto a stale tip. That case is
REJECTED by the unique constraint, never silently accepted. Tested.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GENESIS_HASH = "0" * 64


def upgrade() -> None:
    op.execute(f"""
        CREATE FUNCTION audit_log_genesis_hash() RETURNS TEXT
        LANGUAGE sql IMMUTABLE AS $$ SELECT {GENESIS_HASH!r}::text $$
    """)

    op.execute("""
        CREATE FUNCTION audit_log_compute_hash(
          p_audit_id   BIGINT,
          p_event_type TEXT,
          p_actor_type TEXT,
          p_actor_id   UUID,
          p_venture_id TEXT,
          p_subject    JSONB,
          p_trace_id   UUID,
          p_ts         TIMESTAMPTZ,
          p_prev_hash  TEXT
        ) RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
          SELECT encode(
            sha256(convert_to(
              jsonb_build_object(
                'audit_id',   p_audit_id,
                'event_type', p_event_type,
                'actor_type', p_actor_type,
                'actor_id',   p_actor_id,
                'venture_id', p_venture_id,
                'subject',    p_subject,
                'trace_id',   p_trace_id,
                'ts',         to_char(p_ts AT TIME ZONE 'UTC',
                                      'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
                'prev_hash',  p_prev_hash
              )::text, 'UTF8')),
            'hex')
        $$
    """)
    op.execute("""
        COMMENT ON FUNCTION audit_log_compute_hash IS
        'Canonical entry hash. jsonb_build_object gives deterministic key order and '
        'unambiguous escaping; the UTC format string makes the result independent of '
        'the session TimeZone.'
    """)

    op.execute("""
        CREATE FUNCTION audit_log_chain() RETURNS TRIGGER
        LANGUAGE plpgsql AS $$
        DECLARE
          v_prev TEXT;
        BEGIN
          -- Serialise writers. See module docstring on isolation level.
          PERFORM pg_advisory_xact_lock(hashtext('audit_log_chain'));

          NEW.audit_id := nextval('audit_log_audit_id_seq');

          SELECT entry_hash INTO v_prev
            FROM audit_log ORDER BY audit_id DESC LIMIT 1;

          NEW.prev_hash  := COALESCE(v_prev, audit_log_genesis_hash());
          NEW.entry_hash := audit_log_compute_hash(
            NEW.audit_id, NEW.event_type, NEW.actor_type, NEW.actor_id,
            NEW.venture_id, NEW.subject, NEW.trace_id, NEW.ts, NEW.prev_hash);

          RETURN NEW;
        END $$
    """)
    op.execute("""
        COMMENT ON FUNCTION audit_log_chain() IS
        'Overwrites any caller-supplied audit_id, prev_hash or entry_hash. '
        'A writer cannot choose its own position in the chain.'
    """)

    op.execute("""
        CREATE TRIGGER audit_log_chain_before_insert
          BEFORE INSERT ON audit_log
          FOR EACH ROW EXECUTE FUNCTION audit_log_chain()
    """)

    # Verification returns the denominator (checked_count) alongside the verdict.
    # A bare "ok = true" with no count cannot distinguish a verified chain from an
    # empty table. CLAUDE.md invariant 13.
    op.execute("""
        CREATE FUNCTION audit_log_verify_chain()
        RETURNS TABLE (
          ok                   BOOLEAN,
          checked_count        BIGINT,
          first_break_audit_id BIGINT,
          reason               TEXT
        ) LANGUAGE plpgsql STABLE AS $$
        DECLARE
          r             RECORD;
          v_expect_prev TEXT := audit_log_genesis_hash();
          v_expect_id   BIGINT := NULL;
          v_count       BIGINT := 0;
          v_recomputed  TEXT;
        BEGIN
          FOR r IN SELECT * FROM audit_log ORDER BY audit_id LOOP

            IF r.prev_hash <> v_expect_prev THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id,
                format('prev_hash mismatch: expected %s, found %s '
                       '(a preceding entry was altered or removed)',
                       v_expect_prev, r.prev_hash);
              RETURN;
            END IF;

            v_recomputed := audit_log_compute_hash(
              r.audit_id, r.event_type, r.actor_type, r.actor_id,
              r.venture_id, r.subject, r.trace_id, r.ts, r.prev_hash);

            IF v_recomputed <> r.entry_hash THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id,
                format('entry_hash mismatch: stored %s, recomputed %s '
                       '(this entry''s contents were altered)',
                       r.entry_hash, v_recomputed);
              RETURN;
            END IF;

            -- A gap in audit_id means a row was deleted. The chain would still
            -- link, because the surviving neighbours were never re-hashed, so the
            -- link check alone cannot see a deletion at the tail of a run.
            IF v_expect_id IS NOT NULL AND r.audit_id <> v_expect_id THEN
              RETURN QUERY SELECT FALSE, v_count, r.audit_id,
                format('audit_id gap: expected %s, found %s (an entry was deleted)',
                       v_expect_id, r.audit_id);
              RETURN;
            END IF;

            v_expect_prev := r.entry_hash;
            v_expect_id   := r.audit_id + 1;
            v_count       := v_count + 1;
          END LOOP;

          RETURN QUERY SELECT TRUE, v_count, NULL::BIGINT,
            format('chain verified over %s entries', v_count);
        END $$
    """)
    op.execute("""
        COMMENT ON FUNCTION audit_log_verify_chain() IS
        'Walks the chain in audit_id order. Detects content tampering (entry_hash), '
        'link tampering (prev_hash), and deletion (audit_id gap). Reports the count '
        'checked so a verified result is distinguishable from an empty table.'
    """)

    op.execute("GRANT EXECUTE ON FUNCTION audit_log_verify_chain() TO office_app")
    op.execute("GRANT EXECUTE ON FUNCTION audit_log_compute_hash TO office_app")
    op.execute("GRANT EXECUTE ON FUNCTION audit_log_genesis_hash() TO office_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_chain_before_insert ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_verify_chain()")
    op.execute("DROP FUNCTION IF EXISTS audit_log_chain()")
    op.execute("DROP FUNCTION IF EXISTS audit_log_compute_hash")
    op.execute("DROP FUNCTION IF EXISTS audit_log_genesis_hash()")
