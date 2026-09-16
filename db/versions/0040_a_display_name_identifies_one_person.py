"""A display name identifies one person, and changing it is an audited act

Revision ID: 0040
Revises: 0039

Two Packs name their reviewers by display name, and two joins read those names against
`office_human.display_name`: the access overview's missing-people list, and the approvals
page, which attaches a reviewer's decisions by name. **So a display name is a key in
practice, and nothing said so.**

WHY UNIQUE ON `lower(trim(display_name))`
=========================================

    Because that is how the code already compares them. `broker/access_overview.py`
    builds its set of known people as `{(row["display_name"] or "").strip().lower()}` and
    tests Pack names against it. A plain unique index would permit `Ivan` and `ivan` as
    two accounts that those joins cannot tell apart - which is the ambiguity this index
    exists to prevent, admitted through the door it left open.

    Measured before adding it: 233 rows, no duplicates under either rule. **Two real
    accounts and 231 test fixtures, every name distinct.**

WHAT THIS DOES NOT CLAIM
========================

    A display name is not an identity. `human_id` is, and every foreign key already uses
    it; `email` was already UNIQUE. This index says only that two accounts may not
    present the same name to a human reading a page - which is the confusion the Packs'
    name-matching turns into a wrong answer rather than a cosmetic one.

    It does not make renaming safe by itself. `humans.rename` writes an audit event, and
    the history a rename leaves behind - four Gate 4 reasons reading "reviewed by Ivan:",
    eighteen evidence blobs, frozen Pack versions - is deliberately not rewritten. See
    decisions entry 103.
"""

from __future__ import annotations

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX ux_human_display_name
          ON office_human (lower(trim(display_name)))
    """)
    op.execute("""
        COMMENT ON INDEX ux_human_display_name IS
        'A display name identifies one person. Two Packs name reviewers by display name '
        'and two joins match on it after strip+lower, so two accounts differing only in '
        'case or spacing are two accounts those joins cannot tell apart.'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX ux_human_display_name")
