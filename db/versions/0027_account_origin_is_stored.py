"""An account's origin is stored, because attribution depends on it.

`origin` arrived in 0025 holding only `service`, with person-versus-fixture derived at
read time by `broker/account_origin.py`. That was the right call for *filtering a view*:
the smoke script creates fixtures continuously, and a column backfilled once describes
the accounts that existed the day it ran.

It is the wrong call for *attribution*, which is what this migration changes.

WHY

    `sync-roster` attributes its audit entry to "the oldest active account holding
    `ivan`". 222 of the 223 accounts in this database are smoke fixtures, and the one
    real account only won that query by being the oldest. Every fixture holds `ivan`.
    The next time the ordering changed - a re-seed, a restore, a fixture created a
    second earlier - the audit entry for a change to the identity table would have been
    signed by `smoke-1a2b3c4d`.

    An audit entry signed by a fixture is worthless. Non-repudiation is the entire
    property this log exists to provide, and it does not survive an actor nobody can
    call.

    A derived check could have gated that too, but attribution is a decision made once
    and read for years: a query that resolves an actor has to be able to say *why* this
    account was eligible, and pointing at a regex evaluated at some point in the past is
    a worse answer than a column somebody set.

DERIVED STILL DOES THE MARKING

    `account_origin.origin_of` is what backfills this column and what stamps new rows.
    The classifier stays in one place; what changes is that its answer is written down
    at the moment an account is created rather than recomputed by every reader. A fixture
    created tomorrow is marked on insert.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TEST_NAME = r"^(smoke|browse|check|inc|mut|ui|api|e2e)-[0-9a-f]{6,12}$"


def upgrade() -> None:
    op.execute("ALTER TABLE office_human DROP CONSTRAINT IF EXISTS office_human_origin_check")

    # Backfill with the same rule `account_origin.origin_of` applies, written in SQL so
    # the migration does not import application code that may change under it.
    op.execute(f"""
        UPDATE office_human
           SET origin = CASE
               WHEN origin = 'service' THEN 'service'
               WHEN display_name ~ '{TEST_NAME}' THEN 'test_fixture'
               WHEN lower(email) LIKE '%%.invalid' THEN 'test_fixture'
               ELSE 'human'
           END
    """)

    op.execute("ALTER TABLE office_human ALTER COLUMN origin SET DEFAULT 'human'")
    op.execute("ALTER TABLE office_human ALTER COLUMN origin SET NOT NULL")
    op.execute("""
        ALTER TABLE office_human ADD CONSTRAINT office_human_origin_check
        CHECK (origin IN ('human', 'test_fixture', 'service'))
    """)
    op.execute("""
        COMMENT ON COLUMN office_human.origin IS
        'human, test_fixture or service. Attribution requires ''human'': an audit entry '
        'signed by a fixture is worthless, and 222 of 223 accounts here are fixtures '
        'that all hold ivan. Set from broker/account_origin.py on insert; the classifier '
        'stays in one place and its answer is written down rather than recomputed by '
        'every reader.'
    """)

    # The index attribution reads through. Small table, but the query runs on every write
    # that has to name a person, and a sequential scan for an actor is a sequential scan
    # in the path of every audited action.
    op.execute(
        "CREATE INDEX ix_office_human_real_actors ON office_human (origin, status) "
        "WHERE origin = 'human'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_office_human_real_actors")
    op.execute("ALTER TABLE office_human DROP CONSTRAINT IF EXISTS office_human_origin_check")
    op.execute("ALTER TABLE office_human ALTER COLUMN origin DROP NOT NULL")
    op.execute("ALTER TABLE office_human ALTER COLUMN origin DROP DEFAULT")
    # Back to 0025's narrower constraint: only `service` was ever stored then.
    op.execute("UPDATE office_human SET origin = NULL WHERE origin <> 'service'")
    op.execute("""
        ALTER TABLE office_human ADD CONSTRAINT office_human_origin_check
        CHECK (origin IS NULL OR origin IN ('service'))
    """)
