"""A fixture is declared, never guessed

Revision ID: 0053
Revises: 0052

Ruled 21 September 2026 (Ivan Green):

    *"A fixture is declared, never guessed. `origin` is set explicitly at creation.
    Reclassify `dev-all build check` as `test_fixture`. Measured: it read
    `origin='human'`, so `assert_named_human` would not have refused it."*

WHAT THE GUESS GOT WRONG, AND WHY THE COLUMN AGREED WITH IT
===========================================================

    `account_origin.origin_of` classified an account from two patterns: a display name
    like `smoke-1a2b3c4d`, or an email under a `.invalid` domain. `dev-all build check`
    matches neither. Its address is `dev-all@localhost`, which is not `.invalid`, so it
    read as a person.

    0027 stored the column and backfilled it *with the same rule*. Measured on the
    development database before this migration: **242 accounts, and the stored column
    disagrees with the read-time guess on none of them.** The column did not contradict
    the guess; it inherited its one error and made it durable.

    That is what made the finding hard to see. A stored value and a derived value that
    always agree look like corroboration, and they were the same claim twice.

WHAT IT COST
============

    `assert_named_human` (entry 148) refuses an act attempted by `origin='test_fixture'`.
    It is the control that stops a fixture deciding a proposal, receiving an escalation
    or attesting a department. `dev-all build check` held the `ivan` role from
    17 September to 21 September and that check would have let it through, because as
    far as the column was concerned it was a person.

    Measured, and this is the part worth recording plainly: **in that window it signed
    nothing, attested nothing, decided no proposal and wrote no audit event.** Nothing
    happened. The reclassification is not a repair of damage, it is the removal of a
    permission nobody should have had.

WHY THE DEFAULT GOES
====================

    `origin` was `NOT NULL DEFAULT 'human'`. An `INSERT` that omitted it produced a
    person silently, and the tests in this repository insert into `office_human`
    directly in fourteen places. Dropping the default turns every such insert into a
    loud failure until it says what it is creating, which is the whole of the ruling:
    declared, never guessed.

    The column keeps its `NOT NULL` and its three-value CHECK. What changes is that
    there is no longer an answer for a caller who did not give one.

WHAT THIS MIGRATION DOES NOT DO
===============================

    It does not reclassify the other 239. They are already `test_fixture` and the
    backfill that made them so agreed with the evidence in every case. Re-deriving them
    here would be the guess running one more time.
"""
from __future__ import annotations

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. NO DEFAULT. A caller that does not declare an origin now fails.
    op.execute("ALTER TABLE office_human ALTER COLUMN origin DROP DEFAULT")

    # 2. The one account the guess got wrong. Named by email rather than by display
    #    name because the address is the durable identifier - a rename would not move
    #    it - and asserted as a single row so a second `dev-all@localhost` could not be
    #    caught up in a reclassification nobody reviewed.
    op.execute("""
        UPDATE office_human
           SET origin = 'test_fixture'
         WHERE email = 'dev-all@localhost'
           AND origin = 'human'
    """)

    op.execute("""
        COMMENT ON COLUMN office_human.origin IS
        'human, test_fixture or service. DECLARED AT CREATION, never derived from the '
        'display name or the email domain (ruled 21 September 2026, entry 151). It was '
        'derived, and dev-all@localhost read as a person for four days because '
        '@localhost is not .invalid - so assert_named_human would not have refused it. '
        'There is no DEFAULT: an INSERT that omits this fails rather than guessing.'
    """)


def downgrade() -> None:
    # The default comes back, because a schema without one is not what 0052 described.
    # The reclassification does NOT: putting `dev-all build check` back to `human` would
    # re-grant the permission this migration exists to remove, and a downgrade that
    # restores a finding is worse than one that leaves a column stricter than it found
    # it. `origin` is a declaration now; nothing here can honestly un-declare it.
    op.execute("ALTER TABLE office_human ALTER COLUMN origin SET DEFAULT 'human'")
