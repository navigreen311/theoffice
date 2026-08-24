"""Removing a human's role keeps the record of it.

The console needed a way to take a role away, and the obvious implementation was a
DELETE. `office_app` holds SELECT, INSERT and UPDATE on `office_human_role` and not
DELETE, so it failed - correctly, and for a reason worth more than the convenience.

Deleting the row destroys the answer to "who had this, who gave it to them, and who
took it away". That question is the entire justification for the rule that nobody may
grant themselves a role: every role anyone holds was granted by somebody else, and the
trail says who. A removal that erases the row erases half of that trail.

So removal is a soft delete, the same shape `playbook_share` uses - withdrawing consent
keeps the row so that who saw what survives the withdrawal.

The unique index becomes partial. Without that, a role granted, revoked and granted
again would collide with its own tombstone, and the operator would be told the role
already exists while holding nothing.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE office_human_role ADD COLUMN revoked_at TIMESTAMPTZ")
    op.execute("ALTER TABLE office_human_role ADD COLUMN revoked_by UUID")
    op.execute("""
        COMMENT ON COLUMN office_human_role.revoked_at IS
        'A removed role keeps its row. Deleting it would destroy the answer to "who had '
        'this, who gave it to them, and who took it away" - which is the whole reason '
        'nobody is permitted to grant themselves a role.'
    """)
    op.execute("""
        ALTER TABLE office_human_role
          ADD CONSTRAINT revocation_names_who CHECK (
            revoked_at IS NULL OR revoked_by IS NOT NULL
          )
    """)

    # Partial, so a role can be granted again after being revoked. The old index would
    # have collided with the tombstone and reported that the role already exists.
    op.execute("DROP INDEX IF EXISTS ux_human_role")
    op.execute("""
        CREATE UNIQUE INDEX ux_human_role_live ON office_human_role
          (human_id, role, COALESCE(venture_id, '*'))
          WHERE revoked_at IS NULL
    """)


def downgrade() -> None:
    # Live rows only: a tombstone cannot survive into a schema with no column for it,
    # and collapsing one into a live grant would silently restore an authority somebody
    # deliberately removed.
    op.execute("DELETE FROM office_human_role WHERE revoked_at IS NOT NULL")
    op.execute("DROP INDEX IF EXISTS ux_human_role_live")
    op.execute("""
        CREATE UNIQUE INDEX ux_human_role ON office_human_role
          (human_id, role, COALESCE(venture_id, '*'))
    """)
    op.execute(
        "ALTER TABLE office_human_role DROP CONSTRAINT IF EXISTS revocation_names_who"
    )
    op.execute("ALTER TABLE office_human_role DROP COLUMN IF EXISTS revoked_by")
    op.execute("ALTER TABLE office_human_role DROP COLUMN IF EXISTS revoked_at")
