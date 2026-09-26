"""A proposal carries its outcome.

RULED 25 SEPTEMBER 2026 (decisions entry 195)
=============================================

    *"An approved proposal executes, once, on the agent's own re-call. And: a proposal
    carries its outcome. Add `failed`, with an attempt count and last error. A refusal
    before the Forge sets failed and does not retry."*

WHAT THE STATUS SET COULD NOT SAY
=================================

    `pending | approved | rejected | expired | executed`. An approved proposal whose
    execution was refused before the Forge - revoked, off shift, over budget, grant
    superseded, certification withdrawn - had nowhere to go. It stayed `approved`, which
    is indistinguishable from one nobody has acted on yet, and any runner reading that
    set would retry it for ever.

    `failed` is that state. It is terminal: nothing here re-opens it, and the ruling is
    that a refusal does not retry.

ATTEMPT_COUNT IS FOR A RULE THAT SHOULD NEVER FIRE
==================================================

    The ruling allows exactly one execution, so this column should read 0 or 1 and never
    more. It exists because "should" is not a control: a second attempt has to be
    VISIBLE, and a boolean would hide the difference between the rule holding and the
    rule being broken once.

    Incremented on each terminal write - `mark_executed` or `mark_failed` - rather than
    when an attempt begins. An attempt that crashes between the two is not counted, and
    that is stated rather than hidden: the counter records outcomes it saw, and a crash
    is the case `executed_call_id` and the ledger answer instead.

LAST_ERROR IS THE TYPE AND THE MESSAGE, NOT A TRACE
===================================================

    What an operator needs from an approvals page is which gate refused. The audit log
    already carries the full refusal event with its own subject; this column is so the
    proposal itself reads correctly without a join.
"""

from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE proposal DROP CONSTRAINT proposal_status_check")
    op.execute(
        "ALTER TABLE proposal ADD CONSTRAINT proposal_status_check "
        "CHECK (status IN ('pending','approved','rejected','expired','executed','failed'))"
    )
    # `decision_names_a_human` already covers `failed`: it exempts only `pending` and
    # `expired`, and a failed proposal was approved first, so it has both columns.
    op.execute(
        "ALTER TABLE proposal ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE proposal ADD COLUMN last_error TEXT")
    op.execute(
        "COMMENT ON COLUMN proposal.attempt_count IS "
        "'Entry 195. Terminal execution outcomes seen for this proposal. The ruling "
        "allows one, so 2 or more is a rule broken rather than a busy queue.'"
    )
    op.execute(
        "COMMENT ON COLUMN proposal.last_error IS "
        "'Entry 195. The gate that refused, as type and message. The audit log carries "
        "the full event; this is so the row reads correctly on its own.'"
    )
    # AN EXECUTION IS LOOKED UP BY THE KEY THE AGENT RE-DERIVES, so that lookup runs on
    # every below-auto_execute call and must not be a scan. The agent and the key
    # together are the natural key of the question "has this act been approved".
    op.execute(
        "CREATE INDEX proposal_approved_by_key "
        "ON proposal (office_agent_id, idempotency_key) "
        "WHERE status = 'approved'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX proposal_approved_by_key")
    op.execute("ALTER TABLE proposal DROP COLUMN last_error")
    op.execute("ALTER TABLE proposal DROP COLUMN attempt_count")
    op.execute("UPDATE proposal SET status = 'rejected' WHERE status = 'failed'")
    op.execute("ALTER TABLE proposal DROP CONSTRAINT proposal_status_check")
    op.execute(
        "ALTER TABLE proposal ADD CONSTRAINT proposal_status_check "
        "CHECK (status IN ('pending','approved','rejected','expired','executed'))"
    )
