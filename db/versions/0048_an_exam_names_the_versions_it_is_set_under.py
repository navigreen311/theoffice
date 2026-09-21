"""An exam names the versions it is set under

Revision ID: 0048
Revises: 0047

Ruled 21 September 2026 (Ivan Green): **an exam's identity carries the protocol version
and the rubric version it is set under, beside the instruction and scenario hashes.**

WHAT THE RULING MEASURED
========================

    `assign_contract`'s standing verdict was graded under protocol 4.0.0 and rubric
    0.2.0, two protocol majors behind SimForge's checkout, and **could not be
    re-examined because its ref never changed.** Its answer key did not move between 18
    and 20 September, so both runs minted `...:cacf28ef5ba0:k5c5e41247e52` - the
    identical ref - `open_run` is idempotent on it, and the 20 September exam landed on
    the run already open with its clock and its rubric untouched.

    Measured on this database before writing it:

        assign_contract   rubric 0.2.0   Gate 8 recorded `already_open: True`
        buyer_match       rubric 0.3.0   already_open False - re-minted ref
        comp_analysis     rubric 0.3.0   already_open False
        property_lookup   rubric 0.3.0   already_open False

    One module out of four, and the one whose ref did not change.

WHY THE COLUMNS, GIVEN THE REF ALREADY CARRIES THEM
===================================================

    0046's argument, restated for a different pair of fields. The ref's job is to be
    recognised in a log line; the row's job is to be read. And these two columns answer
    a question no other column can: **which rubric the exam was SET under**, beside
    `certification.rubric_version`, which is the one it was GRADED under. A difference
    between those two is exactly the defect above, visible without reconstructing
    anything.

NOT BACKFILLED, AND THERE IS NOTHING TO BACKFILL FROM
=====================================================

    Every existing row was written before The Office read either version, so no value
    for them exists anywhere on this side. A backfill would have to read SimForge's
    constants as they stand today and write them onto exams set weeks ago - which would
    record the opposite of the truth for `assign_contract`, the one row the ruling is
    about. NULL means "this exam was set before The Office read the versions", and that
    is the honest reading.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "curriculum_submission",
        sa.Column("protocol_version", sa.Text(), nullable=True),
    )
    op.add_column(
        "curriculum_submission",
        sa.Column("rubric_version", sa.Text(), nullable=True),
    )
    op.execute("""
        COMMENT ON COLUMN curriculum_submission.protocol_version IS
        'SimForge''s response-protocol version when this exam was set, as it published '
        'it on /api/version. NULL when the Forge did not publish one - which is every '
        'row today, because no SimForge route declares it (entry 143).'
    """)
    op.execute("""
        COMMENT ON COLUMN curriculum_submission.rubric_version IS
        'The operation rubric version this exam was SET under. Not the same question as '
        'certification.rubric_version, which is the one the verdict was GRADED under; a '
        'difference between the two is a run that was already open when the rubric '
        'moved (entry 143).'
    """)


def downgrade() -> None:
    op.drop_column("curriculum_submission", "rubric_version")
    op.drop_column("curriculum_submission", "protocol_version")
