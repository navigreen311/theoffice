"""An abandoned run takes its exams with it

Revision ID: 0047
Revises: 0046

Ruled 21 September 2026 (Ivan Green): **abandoning a run supersedes its open
submissions.**

WHAT HAPPENED, AND WHY PROSE WOULD NOT HAVE CAUGHT IT
=====================================================

    Run 50d933e8 was abandoned on 20 September because its Gate 8 predated the
    corrected answer keys. Its nine `curriculum_submission` rows were not touched by
    that act - nothing linked them to it - so they stayed in
    `sweep_verdict_ingest`'s candidate set. The first run of that sweep, hours later,
    read four PASS verdicts off them and wrote four certifications, every one graded
    against keys entries 137 and 140 had since corrected. One of the four was
    `property_lookup`, on the exact text the first operation spec obliged a change to.

    All four were overwritten inside the same pass, because `overdue_submissions`
    orders by `submitted_at` and the live run's exams for the same three modules came
    back IN_PROGRESS afterwards. **That is loop order, not a control.** Had the live
    run not been open, or had its exams answered first, the four would have stood.

    0046 could not have covered this. Its one-off superseded every open submission
    carrying a ref *at that moment*, and 50d933e8's Gate 8 ran afterwards - a
    point-in-time statement cannot bind a row that does not exist yet.

WHY A COLUMN AND NOT A TIME WINDOW
==================================

    `curriculum_submission` has never named the run that wrote it. Gate 8 knows -
    `_record_submission` is called from a `_Context` holding `run_id` - and threw it
    away. Without it, "this run's submissions" can only be reconstructed by matching
    timestamps, which is exactly the kind of correlation the next person would have to
    re-derive and could get wrong quietly.

    So `run_id` goes on the row, `_record_submission` writes it, and `abort_run`
    supersedes on it.

THE BACKFILL, AND EXACTLY HOW EACH ROW IS ATTRIBUTED
====================================================

    Existing rows carry no run. They are attributed to the Gate 8 result of the same
    venture nearest in time, within five minutes, and only when that nearest result is
    unique. Measured on this database before writing it:

        8 Gate 8 results, 8 submission batches, one batch per result
        every batch's `submitted_at` within 1.1 seconds of its result's `recorded_at`
        no batch within five minutes of a second Gate 8 result

    A row that does not meet that test keeps a NULL `run_id` and is NOT superseded.
    **An unattributable row is left alone rather than assigned to the likeliest run**:
    superseding on a guess would retire an exam on the strength of a timestamp, and the
    row would read as a decision somebody made.

    The supersession that follows is then plain: every open submission whose run is
    `aborted`. On this database that is every batch from 13 September to 18 September;
    the live run 0c051b0a is `blocked`, not aborted, and keeps its open rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None

_REASON = (
    "The run that set this exam was abandoned. Ruled by Ivan Green, 21 September 2026 "
    "- decisions entry 142: abandoning a run supersedes its open submissions. A verdict "
    "earned for a run nobody is advancing is a verdict against a curriculum that was "
    "withdrawn, and the run reference cannot say so. Backfilled by migration 0047."
)

#: Attribution window. Wide enough for a Gate 8 that submits several modules slowly,
#: narrow enough that two runs of the same venture cannot both be candidates - the
#: closest pair on this database is seven hours apart.
_WINDOW = "5 minutes"

#: Every submission written by a run in this state. `blocked` is deliberately absent:
#: a blocked run is one somebody is still working on, and its exams are still owed.
_ABANDONED = "aborted"


def upgrade() -> None:
    op.add_column(
        "curriculum_submission",
        sa.Column("run_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_curriculum_submission_run",
        "curriculum_submission",
        "provisioning_run",
        ["run_id"],
        ["run_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_curriculum_submission_run", "curriculum_submission", ["run_id"]
    )

    # THE ATTRIBUTION. One Gate 8 result per submission or none: the correlated
    # subquery orders by distance and the `= 1` count makes a second candidate inside
    # the window leave the row NULL rather than pick a winner.
    op.execute(
        sa.text(
            f"""
            WITH gate8 AS (
                SELECT g.run_id, r.venture_id, g.recorded_at
                  FROM provisioning_gate_result g
                  JOIN provisioning_run r ON r.run_id = g.run_id
                 WHERE g.gate = '8'
            ),
            candidate AS (
                SELECT s.submission_id,
                       (SELECT count(*) FROM gate8 g
                         WHERE g.venture_id = s.venture_id
                           AND g.recorded_at
                               BETWEEN s.submitted_at - interval '{_WINDOW}'
                                   AND s.submitted_at + interval '{_WINDOW}'
                       ) AS n,
                       (SELECT g.run_id FROM gate8 g
                         WHERE g.venture_id = s.venture_id
                           AND g.recorded_at
                               BETWEEN s.submitted_at - interval '{_WINDOW}'
                                   AND s.submitted_at + interval '{_WINDOW}'
                         ORDER BY abs(extract(epoch FROM g.recorded_at - s.submitted_at))
                         LIMIT 1
                       ) AS run_id
                  FROM curriculum_submission s
            )
            UPDATE curriculum_submission s
               SET run_id = c.run_id
              FROM candidate c
             WHERE c.submission_id = s.submission_id
               AND c.n = 1
            """
        )
    )

    # THE RULING, applied to what the attribution could establish.
    op.execute(
        sa.text(
            """
            UPDATE curriculum_submission s
               SET superseded_at = now(), superseded_reason = :reason
              FROM provisioning_run r
             WHERE r.run_id = s.run_id
               AND r.status = :abandoned
               AND s.result_received_at IS NULL
               AND s.superseded_at IS NULL
            """
        ).bindparams(reason=_REASON, abandoned=_ABANDONED)
    )

    op.execute("""
        COMMENT ON COLUMN curriculum_submission.run_id IS
        'The provisioning run whose Gate 8 handed this curriculum over. NULL on a row '
        'written before 0047 that no single Gate 8 result could be attributed to. '
        'Abandoning that run supersedes every open submission naming it (entry 142).'
    """)


def downgrade() -> None:
    # The supersession is NOT undone. It records a decision about those exams, and the
    # column going away does not make the runs un-abandoned - the same argument 0043 and
    # 0046 make for leaving their marks in place.
    op.drop_index("ix_curriculum_submission_run", table_name="curriculum_submission")
    op.drop_constraint(
        "fk_curriculum_submission_run", "curriculum_submission", type_="foreignkey"
    )
    op.drop_column("curriculum_submission", "run_id")
