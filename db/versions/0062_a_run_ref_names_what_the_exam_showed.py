"""A run ref names what the exam showed.

RULED 23 SEPTEMBER 2026 (decisions entry 176)
=============================================

    *"A run ref names what the exam showed. The instruction sections in the handover
    are part of the ref derivation, so a handover that shows the agent different text
    mints a different ref."*

`mint_run_ref` now carries an `s` segment on unit A, twelve characters of
`sections_shown_hash`. This is the full value beside it, for the reason 0046 put the
full scenario-set hash on the row: a truncated prefix in a ref is for recognising a
run in a log line, and a reader asking WHY a ref changed needs the whole digest.

NULLABLE, AND NOT BACKFILLED
============================

    NULL means the handover showed no sections - which is true of every submission
    written before 22 September 2026, because The Office did not send any. A backfill
    would have to invent what those exams were shown, and the honest answer is on the
    row already: nothing.

    So NULL is a fact here, not an absence of one, and this column never gets a NOT
    NULL. The same reading `protocol_version` and `rubric_version` carry from 0048.
"""

from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE curriculum_submission "
        "ADD COLUMN sections_shown_hash TEXT"
    )
    op.execute(
        "COMMENT ON COLUMN curriculum_submission.sections_shown_hash IS "
        "'Entry 176. sections_shown_hash over the instruction prose this handover "
        "showed the agent. NULL means it showed none, which is true of every "
        "submission before 22 September 2026.'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE curriculum_submission DROP COLUMN sections_shown_hash"
    )
