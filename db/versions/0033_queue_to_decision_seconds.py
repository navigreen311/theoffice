"""`review_seconds` measured how long a proposal waited, not how long a review took.

The column is well built and it is honest about its own arithmetic: `proposals.decide`
computes it in the database as `EXTRACT(EPOCH FROM (now() - created_at))` rather than
accepting it from the caller, so nobody can report a time they did not take. What it
measures is wall-clock from the moment the proposal was raised to the moment somebody
decided it - **queue latency plus review effort, with no seam between them.**

The name said "review". A proposal raised overnight and approved next morning records
~50,000 seconds of "review", of which the review was a minute.

WHY THAT NAME WAS DANGEROUS RATHER THAN MERELY LOOSE
====================================================
`blocking.md` B21 records the trap this sets: V13's capacity rule multiplies projected
approvals by `median_review_minutes`, which is **how long a review takes**. Once decided
proposals accumulate, `review_seconds` will be full, computed in the database, guarded
against caller-supplied values, and will look exactly like the measured answer to that
question. It is a trustworthy measurement of a different quantity.

**A number that is honest, well-built, full, and about something else is harder to catch
than a wrong one**, because everything about its construction argues for trusting it. The
name was the only thing pointing the wrong way, so the name is what changed.

`queue_to_decision_seconds` cannot be dropped into `median_review_minutes` by somebody
skimming for a field that looks like review time, because it no longer looks like one.

WHAT DOES NOT CHANGE
====================
Part 14 rubber-stamp detection reads the same column and still works: an approval landing
under five seconds of *wall clock from being raised* is a rubber stamp under either name,
and that check never needed the queue/effort distinction. Separating review effort from
queue latency is still unbuilt - see B21 - and this rename does not build it. It stops the
column claiming to be the half nobody has measured.

REVERSIBLE
==========
A rename in both directions, no data movement, no type change. `downgrade` restores the
old name and the old comment exactly.
"""

from __future__ import annotations

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE proposal RENAME COLUMN review_seconds TO queue_to_decision_seconds")
    op.execute("""
        COMMENT ON COLUMN proposal.queue_to_decision_seconds IS
        'Wall-clock seconds from created_at to the decision - queue latency INCLUDING '
        'review effort, not review effort alone. Part 14 rubber-stamp detection reads '
        'it: sub-5-second approval clusters raise a governance flag. It is NOT '
        'median_review_minutes and must not be used as it - see blocking.md B21.'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE proposal RENAME COLUMN queue_to_decision_seconds TO review_seconds")
    op.execute("""
        COMMENT ON COLUMN proposal.review_seconds IS
        'Part 14 rubber-stamp detection: sub-5-second approval clusters raise a '
        'governance flag.'
    """)
