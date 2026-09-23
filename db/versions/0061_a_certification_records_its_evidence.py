"""A certification records the evidence behind its verdict

Revision ID: 0061
Revises: 0060

Ruled 22 September 2026 (Ivan Green), decisions entry 173:

    *"A certification records the evidence behind its verdict, not the verdict alone.
    Enough to tell a wrong verdict from a right one without asking the examiner.
    Measured: three exams scored 1.0 on every attempt with no failure modes and were
    recorded FAILED; The Office held only the aggregate and could not have seen it."*

WHAT THE OFFICE HELD, AND WHAT IT COULD NOT SEE
===============================================

    `GateResult` carries `verdict`, `score`, `threshold`, `scenario_count` and
    `coverage_denominator`. That is the whole of it. For `comp_analysis` on 22
    September the record read:

        verdict FAIL, score 0.8, threshold 1.0

    SimForge's battery record for the same run, fetched by hand that evening, read:

        exam_attempts       1.0, 1.0, 1.0 - passed on every sitting
        failure_modes       none, on any attempt
        rubric dimensions   every one PASS at 1.0, on both channels
        withheld_because    empty

    **Three of five failing exams had this shape.** A fourth with the identical shape
    was certified. Nothing The Office stored could have shown that, because everything
    that would have shown it was discarded at the boundary.

ONE COLUMN, NOT A TABLE
=======================

    `verdict_evidence` is JSONB on the certification it belongs to. A side table would
    need a key, a lifecycle and a rule about what happens when a certification is
    re-earned - and the answer to all three is "the same as the certification", which
    is what being a column already means.

    The upsert in `record_result` replaces it along with the verdict, for the reason it
    replaces the model digest: a re-certification is a new exam, and evidence from the
    previous one beside a new verdict would describe a sitting that did not produce it.

NULLABLE, AND DELIBERATELY NOT BACKFILLED
=========================================

    Twenty-six certifications exist and none has evidence. There is nowhere to get it
    for the older ones - SimForge keys its battery record on a run ref, and the runs
    those certifications came from are closed.

    So NULL means *not asked for*, and it is honest about the twenty-six. A CHECK
    demanding evidence on every tested row would have to be NOT VALID from the day it
    was written, and a constraint that never holds is a comment with a `pg_constraint`
    row.

    **What is enforced instead:** evidence may only sit on a row that had an examiner.
    A bootstrap, an attestation and a simulation certification have no battery behind
    them by construction, so evidence on one of those would be a claim about an exam
    that did not happen.
"""
from __future__ import annotations

from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE certification ADD COLUMN verdict_evidence JSONB")
    op.execute("""
        COMMENT ON COLUMN certification.verdict_evidence IS
        'Entry 173. What SimForge''s battery observed beside the verdict it issued: '
        'per-attempt scores and failure modes, the rubric dimensions, the per-class '
        'verdicts, and what was withheld. NULL means nobody asked - not that nothing '
        'was found. Only a tested certification may carry one; nothing else had an '
        'examiner.'
    """)

    # ONLY A ROW THAT HAD AN EXAMINER. A bootstrap, an attestation and a simulation
    # certification have no battery behind them by construction (entries 147 and 167),
    # so evidence on one would be a claim about an exam that never ran.
    op.execute("""
        ALTER TABLE certification
          ADD CONSTRAINT only_a_tested_certification_has_evidence CHECK (
            verdict_evidence IS NULL OR basis = 'tested'
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT only_a_tested_certification_has_evidence
             ON certification IS
        'Entry 173. Evidence is what a battery observed. The other three bases have no '
        'battery, and a row claiming otherwise would read as an exam nobody sat.'
    """)

    # The disagreement is a derived fact, so the index is over the stored flag rather
    # than over a recomputation. Partial: almost every row will have no evidence at all
    # for a long time, and the query that matters asks only about the ones that do.
    op.execute("""
        CREATE INDEX ix_certification_verdict_disagreement
            ON certification ((verdict_evidence->>'disagrees_with_verdict'))
         WHERE verdict_evidence IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_certification_verdict_disagreement")
    op.execute(
        "ALTER TABLE certification "
        "DROP CONSTRAINT IF EXISTS only_a_tested_certification_has_evidence"
    )
    op.execute("ALTER TABLE certification DROP COLUMN IF EXISTS verdict_evidence")
