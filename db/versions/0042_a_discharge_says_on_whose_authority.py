"""A discharge says on whose authority, and the application may finally write one

Revision ID: 0042
Revises: 0041

Entry 110 stopped a filing rather than work around two gaps, and this closes both.

THE TABLE COULD NOT SAY "NOT COUNSEL-REVIEWED"
==============================================

`compliance_library_entry` carries `status`, `claim_provenance` and `counsel_reviewed_at` -
entry 102 added them so that *"a draft reads as a draft"*. This table never got the
equivalent, so the only place a caveat could go was prose inside `basis`, `citation` or
`artifact_kind`, **and V34 reads none of them.** A row saying "founder policy, not
counsel-reviewed" would have been indistinguishable from one a lawyer signed, and it would
have cleared Gate 2.

`status` makes the two distinguishable states rather than one row with a sentence in it:

    founder_policy     a named founder decided this, and no lawyer has read it. V34
                       PASSES on it - the obligation IS discharged, by somebody entitled
                       to decide - and V41 warns at Gate 2 for as long as it stands.
    counsel_reviewed   a lawyer read it. `counsel_reviewed_at` records when, and the
                       warning goes away.

**Neither value is a default.** The constraint below requires `counsel_reviewed_at` exactly
when the status claims a review, so "reviewed" cannot be asserted without saying when, and a
date cannot sit under a status that does not claim one.

NOTHING COULD WRITE THIS TABLE AT ALL
=====================================

Migration 0032 granted `office_app` SELECT and nothing more, on the reasoning that *"a
discharge is filed by a named human through an operator surface, never by a broker call"*.
That reasoning still holds and the surface did not exist, so the only remaining path was
hand-run SQL over the admin DSN - which writes no audit event, and is the act entry 103
refused for the rename.

The surface exists now: `POST /api/ventures/{id}/discharges`, `ivan` only, writing
`console_obligation_discharged`. INSERT is granted to `office_app` so that route can work,
and **UPDATE is deliberately NOT granted**: the table is append-only, a discharge is
superseded rather than edited, and superseding is `broker.discharges` setting
`superseded_at` - which is the one UPDATE this table needs and it goes through the same
route. See `GRANT` below.

BACKFILL IS `founder_policy`, WHICH IS THE SAFE DIRECTION
=========================================================

Any row written before this migration was written without anybody recording whether
counsel had read it. Calling those `counsel_reviewed` would be asserting a review nobody
performed. `founder_policy` says only "somebody entitled to decide, decided" - which is the
weaker claim and the true one. In this database there are zero rows, so the backfill is a
statement of intent rather than an operation; the test fixtures it does touch are seeded
worlds.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "obligation_discharge",
        sa.Column("status", sa.Text(), nullable=True),
    )
    op.add_column(
        "obligation_discharge",
        sa.Column("counsel_reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE obligation_discharge SET status = 'founder_policy' WHERE status IS NULL"
    )
    op.alter_column("obligation_discharge", "status", nullable=False)
    op.create_check_constraint(
        "ck_discharge_status",
        "obligation_discharge",
        "status IN ('founder_policy', 'counsel_reviewed')",
    )
    # The two fields cannot disagree. A status claiming a review must say when, and a
    # review date cannot sit under a status that claims no review.
    op.create_check_constraint(
        "ck_discharge_counsel_date_matches_status",
        "obligation_discharge",
        "(status = 'counsel_reviewed') = (counsel_reviewed_at IS NOT NULL)",
    )
    op.execute("""
        COMMENT ON COLUMN obligation_discharge.status IS
        'founder_policy: a named founder decided, no lawyer has read it - V34 passes and '
        'V41 warns at Gate 2. counsel_reviewed: a lawyer read it, counsel_reviewed_at '
        'says when, and the warning goes.'
    """)
    # INSERT so the route can file one. NOT UPDATE in general - the table is append-only -
    # but superseding needs to stamp `superseded_at` on the row it replaces, and that
    # write goes through the same route as the insert that replaces it.
    op.execute("GRANT INSERT ON obligation_discharge TO office_app")
    op.execute("GRANT UPDATE (superseded_at) ON obligation_discharge TO office_app")


def downgrade() -> None:
    op.execute("REVOKE INSERT ON obligation_discharge FROM office_app")
    op.execute("REVOKE UPDATE (superseded_at) ON obligation_discharge FROM office_app")
    op.drop_constraint(
        "ck_discharge_counsel_date_matches_status", "obligation_discharge", type_="check"
    )
    op.drop_constraint("ck_discharge_status", "obligation_discharge", type_="check")
    op.drop_column("obligation_discharge", "counsel_reviewed_at")
    op.drop_column("obligation_discharge", "status")
