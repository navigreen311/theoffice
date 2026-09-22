"""An escalation routes to a named human

Revision ID: 0052
Revises: 0051

Ruled 21 September 2026 (Ivan Green):

    *"A governance escalation routes to the human named for its venture and department.
    Account age never decides. Greenstone: operations to Ira Green, research to Ivan
    Green. Measured: routing picks the oldest account holding the `ivan` role, so
    nothing can reach Ira."*

WHAT DECIDED IT BEFORE
======================

    `humans.attributable_actor`, whose query ends `ORDER BY h.created_at LIMIT 1`. It
    answers a different question well - *who do we attribute an unattended action to* -
    and it was never a routing rule. On this database it resolves to Ivan Green because
    his account is the oldest, and there is no argument that would have reached Ira.

    It also ignored `revoked_at`, so a role somebody had taken away still counted. Fixed
    in the same change, and it is a fact about that function rather than about this
    table.

WHY A TABLE AND NOT THE PACK
============================

    The Pack is authored YAML, republished as a version, and signed at Gate 10. Naming
    who receives an escalation is an access decision - closer to a role grant than to a
    position definition - and putting it in the Pack would mean a new Pack version, a
    new artifacts hash and a fresh Gate 4 review every time somebody went on leave.

    So it is a table with an audited writer, the shape `department_attestation` already
    uses. The venture and department are the key; the human is the value; the person who
    named them and when are recorded beside it.

DEPARTMENT NULL IS THE VENTURE'S DEFAULT, AND IT IS NOT A FALLBACK FOR A NAMED ONE
==================================================================================

    A capacity shortfall is about the venture and carries no department; it needs
    somewhere to go. So a row with `department IS NULL` is the venture's default
    recipient, and `recipient_for` reads an exact department match FIRST.

    **What it does not do is fall back when a department is named and unrouted.** An
    escalation for banking, with nobody named for banking, is refused - because the
    alternative is delivering a banking decision to whoever happens to hold the
    venture's default and recording that as though banking's path worked.

NOTHING IS SEEDED HERE
======================

    The two pairs Ivan named are written by `escalation.name_recipient`, which requires
    a named human with founder authority and writes an audit event. A migration that
    inserted them would record the decision as having been made by a schema change.
"""

from __future__ import annotations

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE escalation_recipient (
          venture_id   TEXT NOT NULL,
          -- NULL is the venture's default, for an escalation that names no department.
          -- `COALESCE` in the key so "the default" is one row rather than a row per
          -- department somebody has to remember to add - the same shape
          -- `ux_human_role` uses.
          department   TEXT,
          human_id     UUID NOT NULL,
          named_by     UUID NOT NULL,
          named_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          reason       TEXT NOT NULL,

          CONSTRAINT naming_a_recipient_says_why CHECK (
            length(btrim(reason)) > 0
          )
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_escalation_recipient
          ON escalation_recipient (venture_id, COALESCE(department, '*'))
    """)
    op.execute("""
        COMMENT ON TABLE escalation_recipient IS
        'Who a governance escalation reaches, per venture and department. Ruled 21 '
        'September 2026: account age never decides. A row with department NULL is the '
        'venture default and is NOT a fallback for a department nobody has named '
        '(entry 150).'
    """)
    op.execute("GRANT SELECT, INSERT, UPDATE ON escalation_recipient TO office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS escalation_recipient")
