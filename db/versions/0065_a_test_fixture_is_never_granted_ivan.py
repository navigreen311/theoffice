"""A test fixture is never granted ivan.

RULED 26 SEPTEMBER 2026 (decisions entry 206)
=============================================

    *"A test fixture is never granted `ivan`. `grant_role` refuses the role to an
    account whose origin is not human, and the 128 live fixture `ivan` rows are
    revoked."*

WHAT THE ROWS WERE
==================

    Measured that day: 130 accounts held a live `ivan` role and 128 of them were
    fixtures - 117 `smoke-*`, 5 `ui-*`, 2 `browse-*`, and a handful named for the test
    that made them, including one called `A real person` which is not one.

    `ivan` declares a venture in simulation, certifies a department on that declaration,
    retires a grant and rotates anybody's token. What stood between those rows and all
    of it was `assert_named_human` - a second check, applied per act. Entry 148 is what
    that costs when it is the only one.

REVOKED, NOT DELETED
====================

    `revoked_at` and `revoked_by`, which is what `revoke_role` writes and what every
    read of this table already filters on. Deleting them would erase that the grants
    were ever made, and the 128 rows are the evidence for the rule.

    `revoked_by` is the account that held the role, because no person did this: it was a
    migration, and naming a human would put a person's id on an act they did not
    perform. The `reason` lives here, in this file, which is where a reader of the row
    is sent.

WHAT IS NOT REVOKED
===================

    `venture_operator` and `compliance_officer` on fixtures. The suites need them and
    `assert_named_human` is unchanged - it still refuses a fixture any act that names a
    signer. `ivan` is the one role no test needs, because no test should be able to do
    what it permits.
"""

from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE office_human_role r
           SET revoked_at = now(),
               revoked_by = r.human_id
          FROM office_human h
         WHERE h.human_id = r.human_id
           AND r.role = 'ivan'
           AND r.revoked_at IS NULL
           AND h.origin <> 'human'
        """
    )


def downgrade() -> None:
    # NOT REVERSIBLE, and saying so is better than restoring the wrong rows. A blanket
    # un-revoke would also lift revocations a person made deliberately - `revoke_role`
    # writes the same two columns - and this migration cannot tell its own writes from
    # theirs once they are in the table.
    pass
