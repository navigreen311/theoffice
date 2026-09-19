"""An exam names the answer key it was set from

Revision ID: 0046
Revises: 0045

Ruled 18 September 2026 (Ivan Green): **the exam's identity includes the scenarios it
was set from.** `mint_run_ref` now carries a scenario-set hash on unit A, and this adds
the two columns that make a submission row say the same thing the ref does.

WHY A REF ALONE WAS NOT ENOUGH
==============================

    The ref carries twelve characters of the hash, because its job is to be recognised
    in a log line. `instruction_content_hash` has sat in full on this table since 0007
    for exactly that reason, and the scenario-set hash needs the same treatment: the
    verdict-ingest sweep reads this row and must not have to parse a ref to learn which
    answer key a verdict belongs to.

SUPERSEDED, AND WHY IT IS NOT `result_received_at`
==================================================

    Entry 128 ruled that six verdicts earned on superseded scenarios are NOT ingested.
    Prose alone could not carry that: the rows were still in `sweep_verdict_ingest`'s
    candidate set, and one `python -m broker sweep` would have written all six.

    `result_received_at` was the tempting field and it is the wrong one. Its own
    docstring: *"`result_received_at` means 'a verdict SimForge stands behind was
    written into a certification', NOT 'we stopped asking'."* Stamping it here would
    record that a certification was written when the ruling is that none will be. The
    row would read as answered, `overdue_submissions` would drop it, and every later
    reader would conclude a verdict arrived.

    So this is a separate mark with its own reason beside it, and a CHECK that the two
    travel together. The shape is 0043's: a `superseded_at` the reader excludes, not a
    revocation and not a deletion. **The row keeps its verdict-shaped hole**, which is
    the true statement: an exam was set, an answer came back, and nobody will act on it.

THE ONE-OFF INVARIANT, AND EXACTLY WHICH ROWS IT TOUCHES
========================================================

    Every open submission carrying a `simforge_run_ref` is superseded here, because a
    ref minted before this revision names an exam whose identity does not include its
    answer key - which is the population entry 128's ruling covers, stated structurally
    rather than by listing six uuids.

    Measured on this database before writing it:

        47 open submissions, 0 closed
        18 carry a ref, over 9 distinct refs (each minted twice, by two runs)
        29 carry none - Burkham's 20 and 9 Greenstone rows from runs that never
           reached `run_start`

    **The 29 are deliberately untouched.** No ref means no run was ever opened, so
    there is no verdict to refuse; `_ingest_one` resolves them to TIMEOUT, which is
    `in_training` and not a certification anybody earned. Superseding them would claim
    a decision was made about exams that were never set.

    This is a one-off, in the 0043 sense: it states a fact true at the moment the
    identity scheme changed, and nothing recomputes it afterwards. Every ref minted
    from here on carries its answer key, so no later row can fall into this class.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None

_REASON = (
    "Superseded by migration 0046. This exam was set before a run reference named the "
    "answer key it was drawn from, so a verdict against it cannot be told from one "
    "earned on the scenarios approved on 18 September 2026. Ruled by Ivan Green, "
    "18 September 2026 - decisions entries 128 and 129. The verdict, if one exists, is "
    "recorded as history in entry 128 and is not ingested."
)


def upgrade() -> None:
    op.add_column(
        "curriculum_submission",
        sa.Column("scenario_set_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "curriculum_submission",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "curriculum_submission",
        sa.Column("superseded_reason", sa.Text(), nullable=True),
    )
    # A mark with no reason is the shape this codebase keeps refusing: the next reader
    # finds a row excluded from every sweep and no record of who decided or why.
    op.create_check_constraint(
        "superseding_a_submission_says_why",
        "curriculum_submission",
        "(superseded_at IS NULL) = (superseded_reason IS NULL)",
    )
    op.create_index(
        "ix_curriculum_submission_superseded",
        "curriculum_submission",
        ["superseded_at"],
    )

    # THE ONE-OFF INVARIANT. See the docstring for which rows and why not the others.
    op.execute(
        sa.text(
            "UPDATE curriculum_submission "
            "   SET superseded_at = now(), superseded_reason = :reason "
            " WHERE result_received_at IS NULL "
            "   AND simforge_run_ref IS NOT NULL "
            "   AND superseded_at IS NULL"
        ).bindparams(reason=_REASON)
    )

    op.execute("""
        COMMENT ON COLUMN curriculum_submission.scenario_set_hash IS
        'The answer key this exam was set from, in full. The run ref carries twelve '
        'characters of it; this is what the verdict-ingest sweep reads. NULL on a '
        'unit-B submission, which sends no curriculum, and on any row written before '
        '0046.'
    """)
    op.execute("""
        COMMENT ON COLUMN curriculum_submission.superseded_at IS
        'This exam will not be ingested. NOT result_received_at, which means a verdict '
        'was written into a certification - here no verdict will be acted on at all, '
        'and the row keeps its open shape on purpose.'
    """)


def downgrade() -> None:
    op.drop_index(
        "ix_curriculum_submission_superseded", table_name="curriculum_submission"
    )
    op.drop_constraint(
        "superseding_a_submission_says_why", "curriculum_submission", type_="check"
    )
    op.drop_column("curriculum_submission", "superseded_reason")
    op.drop_column("curriculum_submission", "superseded_at")
    op.drop_column("curriculum_submission", "scenario_set_hash")
