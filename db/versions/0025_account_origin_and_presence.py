"""Accounts record what cannot be inferred: a service origin, last presence, MFA.

Three columns, and one deliberate absence.

`origin` stores only `service`. Whether an account is a person or a leftover test fixture
is derived at read time by `broker/account_origin.py`, because the smoke script creates
more fixtures on every run and a column filled by one backfill describes the accounts that
existed the day it ran. Nothing about a service account is inferable from its name, so
that one is stored.

`last_seen_at` is the fact the roster could not show. 178 of 179 accounts had never signed
in, which is the single clearest signal that they are not colleagues - and the page had no
column for it.

`mfa_enrolled_at` is separate from `auth_method`. Every account already claims `sso_mfa`,
because that is the column's default and nothing has ever checked. A named signer at Gate
10 whose MFA is a default rather than an enrolment weakens exactly the non-repudiation the
signature exists to provide, so the claim and the evidence are kept apart.

No account is ever deleted, here or anywhere. Suspension is reversible and audited;
deletion destroys the record of who held what and who granted it, which is the property
the Access page's own copy exists to protect.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE office_human ADD COLUMN origin TEXT "
        "CHECK (origin IS NULL OR origin IN ('service'))"
    )
    op.execute("""
        COMMENT ON COLUMN office_human.origin IS
        'Set to ''service'' for a non-human account. Person versus test fixture is '
        'derived at read time by broker/account_origin.py rather than stored: the smoke '
        'script creates fixtures continuously, and a backfilled column would only ever '
        'describe the ones that existed when it ran.'
    """)

    op.execute("ALTER TABLE office_human ADD COLUMN last_seen_at TIMESTAMPTZ")
    op.execute("""
        COMMENT ON COLUMN office_human.last_seen_at IS
        'When this account last authenticated. Updated on token verification. An account '
        'that has never signed in is the clearest available signal that nobody is behind '
        'it.'
    """)

    op.execute("ALTER TABLE office_human ADD COLUMN mfa_enrolled_at TIMESTAMPTZ")
    op.execute("""
        COMMENT ON COLUMN office_human.mfa_enrolled_at IS
        'When a second factor was actually enrolled. Deliberately separate from '
        'auth_method, which every account claims by default and nothing verifies: a '
        'signer whose MFA is a claim rather than an enrolment weakens the '
        'non-repudiation the Gate 10 signature is meant to carry.'
    """)

    op.execute(
        "CREATE INDEX ix_office_human_last_seen ON office_human (last_seen_at NULLS FIRST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_office_human_last_seen")
    op.execute("ALTER TABLE office_human DROP COLUMN IF EXISTS mfa_enrolled_at")
    op.execute("ALTER TABLE office_human DROP COLUMN IF EXISTS last_seen_at")
    op.execute("ALTER TABLE office_human DROP COLUMN IF EXISTS origin")
