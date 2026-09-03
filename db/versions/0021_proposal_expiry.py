"""A proposal nobody decides expires. It is never approved.

`expired` has been a valid proposal status since the schema was written, and nothing
could ever set it: there was no deadline to pass. So a proposal nobody looked at stayed
`pending` for ever, and the queue had no way to distinguish "waiting for a reviewer" from
"waiting since March".

The deadline is a column rather than a config value read at display time, because the
question a regulator asks is "when was this due", and a deadline computed from a setting
that has since changed cannot answer it.

**Expiry never approves.** The task fails and both facts are audited. This is written
here as well as in the code because the alternative is the single most attractive
shortcut on the approvals page - a queue that drains itself looks like a queue being
worked - and it converts the whole control into a formality. An agent below
`auto_execute` asked to act; nobody answered; it did not act. That is the correct
outcome, and a timeout that approved would make the trust tier a delay rather than a
decision.

There is deliberately no `auto_approve_on_expiry` setting, and no per-venture override.
A control that can be configured away is a control somebody will configure away.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Long enough that a reviewer on a normal coverage window can get to it, short enough
# that a stale queue is visibly stale. Applied at submission so each proposal carries
# the deadline it was created under.
DEFAULT_SLA_HOURS = 8


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE proposal
          ADD COLUMN expires_at TIMESTAMPTZ
            NOT NULL DEFAULT (now() + interval '{DEFAULT_SLA_HOURS} hours')
    """)
    op.execute("""
        COMMENT ON COLUMN proposal.expires_at IS
        'When this proposal stops being decidable. Stored per proposal rather than '
        'computed from a setting, so the deadline a reviewer missed is still the '
        'deadline that applied. Expiry fails the task; it never approves it.'
    """)
    op.execute("""
        CREATE INDEX ix_proposal_pending_expiry ON proposal (expires_at)
          WHERE status = 'pending'
    """)

    # An expired proposal has a deadline that passed and no decider, which the existing
    # status constraint already allows - `pending` and `expired` are the two statuses
    # that do not require `decided_by`. Nothing to change; recorded because it is the
    # reason expiry can be honest about having no actor.


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_proposal_pending_expiry")
    op.execute("ALTER TABLE proposal DROP COLUMN expires_at")
