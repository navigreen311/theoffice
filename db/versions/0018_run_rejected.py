"""A human can decline at a human gate.

Gate 4 is *human review of artifacts, BOM and appointment gap report*. Until now the
only thing a human could record there was that they had reviewed it -
`record_human_review` writes a note and advances. There was no way to say no.

A review that can only approve is not a review. What a reviewer actually had was
`abort_run`, and that is a different act with a different meaning: abandoning a run
because it is stuck or superseded, not judging the artifacts and finding them wanting.
Collapsing the two loses the only signal that matters to whoever provisions this venture
next - whether the last attempt was dropped or refused.

So `rejected` becomes a terminal status of its own:

  cancelled (`aborted`)  the run was abandoned. Says nothing about the artifacts.
  rejected               a named human reviewed the artifacts and declined them, with
                         a reason, at a gate that was waiting for their decision.

Rejection is only possible at a gate that is `awaiting_human`. A human cannot reject a
run that no gate has handed to them - that would be a way to stop a run mid-flight
while dressing it as a judgement, and `abort_run` already exists for stopping a run.

Like an abort, rejecting does **not** deactivate grants. Gate 11 may already have
activated them, and a rejection is not a revocation; those are different acts with
different authority, and collapsing them here would make declining a review a silent way
to pull a venture's authority with no revocation record.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE provisioning_run DROP CONSTRAINT provisioning_run_status_check")
    op.execute("""
        ALTER TABLE provisioning_run ADD CONSTRAINT provisioning_run_status_check
          CHECK (status IN
            ('running','blocked','awaiting_human','complete','aborted','rejected'))
    """)
    op.execute("""
        COMMENT ON COLUMN provisioning_run.status IS
        'aborted means abandoned and says nothing about the artifacts; rejected means a '
        'named human reviewed them at a gate awaiting their decision and declined, with '
        'a reason. The console renders the two differently because the next person to '
        'provision this venture needs to know which one happened.'
    """)


def downgrade() -> None:
    # A rejected run has no representation in the old shape. `aborted` is the closest
    # available state and is where these rows would have gone before this migration -
    # the reason survives in the audit log either way.
    op.execute("UPDATE provisioning_run SET status = 'aborted' WHERE status = 'rejected'")
    op.execute("ALTER TABLE provisioning_run DROP CONSTRAINT provisioning_run_status_check")
    op.execute("""
        ALTER TABLE provisioning_run ADD CONSTRAINT provisioning_run_status_check
          CHECK (status IN ('running','blocked','awaiting_human','complete','aborted'))
    """)
