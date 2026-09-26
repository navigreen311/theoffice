"""A call started and not completed is surfaced.

RULED 25 SEPTEMBER 2026 (decisions entry 199)
=============================================

    *"A call started and not completed is surfaced. An intent written with no ledger
    row, or a ledger row with no outcome, is reported to a named human with what was
    attempted. Entry 198 rules the human checks; nothing shows them."*

TWO VOCABULARIES, BOTH CLOSED, BOTH WIDENED HERE
================================================

    `sweep_run.sweep_kind` and `incident.kind` are CHECK constraints rather than free
    text, which is why adding a sweep needs a migration. That is the design working: a
    kind nobody declared cannot be written, so the console's filter and the compliance
    export cannot be handed a value they have no label for.

THE INDEX, AND WHY IT IS PARTIAL
================================

    The intent half of the sweep asks for `audit_log` rows of one event type older than
    a cutoff. `audit_log` is the largest table here and grows with every call, refusal
    and human action; a full scan every hour would be the sweep costing more than the
    thing it watches. The index carries only `forge_call_intent` rows, which is a small
    fraction of the table and exactly the set this question is about.

    NOT indexed: the ledger half. `ts_end IS NULL` is already rare enough to be found
    without one, and an index on a column that is almost never NULL earns nothing.
"""

from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_SWEEP_KINDS = (
    "audit_chain", "certification_staleness", "manifest_reconciliation",
    "restore_drill", "verdict_ingest", "deadline_expiry",
)


def upgrade() -> None:
    op.execute("ALTER TABLE sweep_run DROP CONSTRAINT sweep_run_sweep_kind_check")
    kinds = ", ".join(f"'{k}'" for k in (*_SWEEP_KINDS, "incomplete_calls"))
    op.execute(
        "ALTER TABLE sweep_run ADD CONSTRAINT sweep_run_sweep_kind_check "
        f"CHECK (sweep_kind IN ({kinds}))"
    )
    # `incident.kind` is read out of the live constraint rather than re-listed, because
    # this migration has no business restating twenty values it does not change. The
    # one it adds is appended to whatever is there.
    op.execute(
        """
        DO $$
        DECLARE existing text;
        BEGIN
            SELECT pg_get_constraintdef(oid) INTO existing
              FROM pg_constraint
             WHERE conrelid = 'incident'::regclass AND conname = 'incident_kind_check';
            EXECUTE 'ALTER TABLE incident DROP CONSTRAINT incident_kind_check';
            EXECUTE format(
                'ALTER TABLE incident ADD CONSTRAINT incident_kind_check %s',
                replace(existing, ']))',
                        ', ''call_started_and_not_completed''::text]))')
            );
        END $$;
        """
    )
    op.execute(
        "CREATE INDEX audit_log_forge_call_intent_ts "
        "ON audit_log (ts) WHERE event_type = 'forge_call_intent'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX audit_log_forge_call_intent_ts")
    op.execute(
        "DELETE FROM incident WHERE kind = 'call_started_and_not_completed'"
    )
    op.execute(
        """
        DO $$
        DECLARE existing text;
        BEGIN
            SELECT pg_get_constraintdef(oid) INTO existing
              FROM pg_constraint
             WHERE conrelid = 'incident'::regclass AND conname = 'incident_kind_check';
            EXECUTE 'ALTER TABLE incident DROP CONSTRAINT incident_kind_check';
            EXECUTE format(
                'ALTER TABLE incident ADD CONSTRAINT incident_kind_check %s',
                replace(existing, ', ''call_started_and_not_completed''::text]))',
                        ']))')
            );
        END $$;
        """
    )
    op.execute("DELETE FROM sweep_run WHERE sweep_kind = 'incomplete_calls'")
    op.execute("ALTER TABLE sweep_run DROP CONSTRAINT sweep_run_sweep_kind_check")
    kinds = ", ".join(f"'{k}'" for k in _SWEEP_KINDS)
    op.execute(
        "ALTER TABLE sweep_run ADD CONSTRAINT sweep_run_sweep_kind_check "
        f"CHECK (sweep_kind IN ({kinds}))"
    )
