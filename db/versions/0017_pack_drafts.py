"""A Pack can be a draft.

The store has had two states since it was built - live, and superseded - because a Pack
arrived by being published and there was no way to have one that was not yet in force.
That is the wrong shape for authoring: a new Pack starts incomplete, fails most of the
validator, and must not be reachable by a provisioning run while somebody is still
writing it.

`status` makes the third state explicit rather than implied by a NULL:

  draft       being written. Never returned by `packs.live`, so Gate 1 cannot find it
              and nothing downstream can generate from it. The inability to provision
              is structural rather than a flag somebody checks.
  live        in force. Exactly one per venture, which the partial unique index has
              enforced since the store was built and continues to.
  superseded  replaced by a later publish, and kept - a provisioning run records the
              version it started from, and that record is worthless if the version
              disappears the moment somebody edits.

One draft per venture, for the same reason there is one live Pack: "the current draft"
cannot be a question with two answers.

Existing rows are backfilled from the column they already had. `superseded_at IS NULL`
meant live and still does; the column now says so instead of leaving it to be inferred
by every reader.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE business_pack
          ADD COLUMN status TEXT NOT NULL DEFAULT 'live'
            CHECK (status IN ('draft', 'live', 'superseded'))
    """)
    op.execute("""
        UPDATE business_pack
        SET status = CASE WHEN superseded_at IS NULL THEN 'live' ELSE 'superseded' END
    """)
    op.execute("""
        COMMENT ON COLUMN business_pack.status IS
        'draft is never returned by packs.live, so Gate 1 cannot find it and nothing '
        'downstream can generate from it - a draft cannot provision by construction '
        'rather than by a check somebody remembers to write.'
    """)

    # The live index already existed and is unchanged in meaning; it is recreated
    # against `status` so the two cannot disagree about which row is live.
    op.execute("DROP INDEX IF EXISTS ux_pack_live")
    op.execute("""
        CREATE UNIQUE INDEX ux_pack_live ON business_pack (venture_id)
          WHERE status = 'live'
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_pack_draft ON business_pack (venture_id)
          WHERE status = 'draft'
    """)


def downgrade() -> None:
    # A draft has no representation in the old shape. Collapsing one into a live Pack
    # would put an unfinished document in force, so drafts are dropped rather than
    # silently promoted.
    op.execute("DELETE FROM business_pack WHERE status = 'draft'")
    op.execute("DROP INDEX IF EXISTS ux_pack_draft")
    op.execute("DROP INDEX IF EXISTS ux_pack_live")
    op.execute("ALTER TABLE business_pack DROP COLUMN status")
    op.execute("""
        CREATE UNIQUE INDEX ux_pack_live ON business_pack (venture_id)
          WHERE superseded_at IS NULL
    """)
