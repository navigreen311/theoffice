"""A deadline passes on its own

Revision ID: 0055
Revises: 0054

Ruled 22 September 2026 (Ivan Green):

    *"A deadline passes on its own. A scheduled job expires overdue proposals and
    escalations. Measured: e19ca4ce expired at 05:17:15 and stayed pending until
    10:07:23, when a page load triggered it."*

    *"An expiry records when the deadline passed, not when it was noticed. Measured: the
    entry reads 10:07:23, which is when I opened the page."*

WHAT THE SCHEMA HAS TO ADD, WHICH IS LESS THAN IT LOOKS
=======================================================

    Proposals already carry everything: `expires_at` since 0021, with an 8-hour default
    and an index over pending rows. Nothing about proposals changes here. What changed
    is that a job now reads that column instead of a page.

    Escalations carry nothing. There is no deadline column on `escalation_record`, and
    nothing in the Pack, the schema or the ledger says how long a named human has to
    receive one.

TWO COLUMNS, AND WHY NEITHER HAS A DEFAULT
==========================================

    `expires_at`  when this escalation stops being deliverable. NULLABLE, NO DEFAULT.
    `expired_at`  when that deadline passed, written by the job.

    **The absent default is the point.** Entry 158 says the job expires overdue
    escalations; it does not say what makes one overdue, and nothing else does either.
    A default of twenty-four hours here would be a number nobody chose, applied to every
    escalation this platform ever raises, arriving through a migration rather than
    through a ruling.

    So: the mechanism exists, it expires exactly the rows that carry a deadline, and
    today that is none of them. `broker/deadlines.py` counts the ones it cannot expire
    and reports them under `escalations_overdue_without_a_deadline`, so the gap is
    visible on every pass rather than quiet.

WHY `expired_at` IS A COLUMN AND NOT A STATUS
=============================================

    `escalation_record` has no status column - it has three timestamps, and whether an
    escalation travelled is derived from them (`received_before_answered`,
    `an_answer_says_something`). A fourth timestamp fits that shape; a status would be a
    second way to say what the timestamps already say, and the first time the two
    disagreed nobody would know which was right.

    It also makes entry 157 structural rather than remembered: the job writes
    `expired_at = expires_at`, so the row records the moment the deadline passed and
    cannot record the moment a job happened to notice.

    `an_expiry_is_the_deadline` enforces exactly that, and it is the constraint that
    would have caught the defect being fixed. A row whose `expired_at` is some later
    moment somebody observed is refused by the database.
"""
from __future__ import annotations

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE escalation_record ADD COLUMN expires_at TIMESTAMPTZ")
    op.execute("ALTER TABLE escalation_record ADD COLUMN expired_at TIMESTAMPTZ")

    op.execute("""
        COMMENT ON COLUMN escalation_record.expires_at IS
        'When this escalation stops being deliverable. NULLABLE WITH NO DEFAULT, and '
        'deliberately: entry 156 rules that a job expires overdue escalations and does '
        'not say what makes one overdue. Nothing in the Pack or the schema does either, '
        'so a default here would be a number nobody chose. Until a deadline is ruled, '
        'no escalation expires and the count of undeadlined ones is reported on every '
        'sweep.'
    """)
    op.execute("""
        COMMENT ON COLUMN escalation_record.expired_at IS
        'When the deadline passed - NOT when a job noticed. Ruled 22 September 2026, '
        'entry 157, because a proposal expiry recorded 10:07:23 for a deadline that had '
        'passed at 05:17:15. The job writes expired_at = expires_at and the CHECK '
        'refuses anything else.'
    """)

    # ENTRY 159, AS A CONSTRAINT. The job could write `now()` here and a reader would
    # never know; this makes that impossible rather than discouraged.
    op.execute("""
        ALTER TABLE escalation_record ADD CONSTRAINT an_expiry_is_the_deadline CHECK (
          expired_at IS NULL OR expired_at = expires_at
        )
    """)

    # AND AN EXPIRY NEEDS A DEADLINE TO BE. Implied by the CHECK above, stated because
    # the two say different things: that one says the times match, this says a row
    # cannot be expired without ever having had a deadline.
    op.execute("""
        ALTER TABLE escalation_record ADD CONSTRAINT an_expiry_has_a_deadline CHECK (
          expired_at IS NULL OR expires_at IS NOT NULL
        )
    """)

    # The job's WHERE clause, as an index. Partial for the same reason 0021's is: the
    # rows that matter are the few that are still open.
    op.execute("""
        CREATE INDEX ix_escalation_pending_expiry ON escalation_record (expires_at)
          WHERE expires_at IS NOT NULL AND received_at IS NULL AND expired_at IS NULL
    """)

    # THE SWEEP HAS TO BE NAMEABLE. `sweep_run.sweep_kind` is a closed list, which is
    # the right shape - it is how `health` knows which controls exist and can report one
    # that has never run. A new sweep joins the list rather than the list being dropped.
    op.execute("ALTER TABLE sweep_run DROP CONSTRAINT sweep_run_sweep_kind_check")
    op.execute("""
        ALTER TABLE sweep_run ADD CONSTRAINT sweep_run_sweep_kind_check CHECK (
          sweep_kind IN ('audit_chain', 'certification_staleness',
                         'manifest_reconciliation', 'restore_drill', 'verdict_ingest',
                         'deadline_expiry')
        )
    """)

    op.execute("GRANT UPDATE ON escalation_record TO office_app")


def downgrade() -> None:
    op.execute("DELETE FROM sweep_run WHERE sweep_kind = 'deadline_expiry'")
    op.execute("ALTER TABLE sweep_run DROP CONSTRAINT sweep_run_sweep_kind_check")
    op.execute("""
        ALTER TABLE sweep_run ADD CONSTRAINT sweep_run_sweep_kind_check CHECK (
          sweep_kind IN ('audit_chain', 'certification_staleness',
                         'manifest_reconciliation', 'restore_drill', 'verdict_ingest')
        )
    """)
    op.execute("DROP INDEX IF EXISTS ix_escalation_pending_expiry")
    op.execute(
        "ALTER TABLE escalation_record DROP CONSTRAINT IF EXISTS an_expiry_has_a_deadline"
    )
    op.execute(
        "ALTER TABLE escalation_record DROP CONSTRAINT IF EXISTS an_expiry_is_the_deadline"
    )
    op.execute("ALTER TABLE escalation_record DROP COLUMN IF EXISTS expired_at")
    op.execute("ALTER TABLE escalation_record DROP COLUMN IF EXISTS expires_at")
