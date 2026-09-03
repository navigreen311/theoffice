"""Revocation records what it cost, and re-enabling takes two people at the wide scopes.

Two gaps, both about the record rather than the act.

**Blast radius at the time.** A revocation's reach is a query against live state: how
many agents, how many grants, how many calls in flight. Asked six months later that query
returns today's answer, which is not what the revocation did - the grants it stopped have
since been re-issued or expired. So the numbers are computed once, at the moment of the
act, and stored with it. That is the figure a regulator export needs.

**A second named human.** §1.4 requires a documented ritual to re-enable. `reinstate`
already demanded a reason and a named human, which is most of it. What it did not have
was the thing that makes a ritual a ritual at the wide scopes: at `venture` and `forge`,
one person's judgement is what created a portfolio-wide stop, and one person's judgement
should not be enough to end it.

Neither column erases anything. A reinstated revocation stays in the table with both
accounts attached, because a history that looks cleaner than the truth is worse than no
history.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE revocation ADD COLUMN blast_radius JSONB NOT NULL DEFAULT '{}'")
    op.execute("""
        COMMENT ON COLUMN revocation.blast_radius IS
        'What this revocation stopped, counted when it was issued. Stored rather than '
        'recomputed: the same query run later answers about today''s grants, not the '
        'ones this stopped, and the difference is invisible in the number.'
    """)

    op.execute(
        "ALTER TABLE revocation ADD COLUMN reinstatement_second_human "
        "UUID REFERENCES office_human(human_id)"
    )
    op.execute("""
        COMMENT ON COLUMN revocation.reinstatement_second_human IS
        'The second named human required to lift a venture or forge revocation. One '
        'person''s judgement created a stop at that width; one person''s judgement is '
        'not enough to end it.'
    """)

    # Enforced in the schema as well as in `revocation.reinstate`, because this is the
    # control that undoes the kill switch and a rule that lives only in application code
    # is a rule a later route can forget to call.
    op.execute("""
        ALTER TABLE revocation ADD CONSTRAINT wide_reinstatement_needs_two_humans CHECK (
          reinstated_at IS NULL
          OR scope IN ('agent_module', 'agent')
          OR (reinstatement_second_human IS NOT NULL
              AND reinstatement_second_human <> reinstated_by)
        )
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE revocation DROP CONSTRAINT IF EXISTS wide_reinstatement_needs_two_humans"
    )
    op.execute("ALTER TABLE revocation DROP COLUMN IF EXISTS reinstatement_second_human")
    op.execute("ALTER TABLE revocation DROP COLUMN IF EXISTS blast_radius")
