"""A draft that was replaced is abandoned, not superseded.

`status` gained three values in 0017: draft, live, superseded. Replacing a draft marked
the old one `superseded`, which put it in the same bucket as a released version that a
later publish replaced - and those are different events:

  superseded  was live, and a later publish took its place. Something provisioned from
              it, or could have.
  abandoned   was a draft, and was replaced before anybody published it. Nothing ever
              provisioned from it and nothing could have, because `packs.live` never
              returned it.

One word for both is why the editor's version history read as an unsorted list: an
abandoned draft sitting above the live version looks like a sorting bug when the only
thing wrong is that the label does not say what happened.

The first attempt at telling them apart guessed from the version string - anything
ending `-draft` was treated as a draft. That is a naming convention, not a fact: a draft
called `1.2.0` and a release called `2.0.0-draft` are both entirely possible, and the
guess is wrong for both. The store knows which one it was, so it records it.

Existing rows are backfilled on the only evidence available: a superseded version that
no provisioning run ever started from, and whose venture has a different version live,
cannot be shown to have been live itself. That is a guess too, and it is made once here
rather than on every read.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE business_pack DROP CONSTRAINT business_pack_status_check")
    op.execute("""
        ALTER TABLE business_pack ADD CONSTRAINT business_pack_status_check
          CHECK (status IN ('draft', 'live', 'superseded', 'abandoned'))
    """)
    op.execute("""
        COMMENT ON COLUMN business_pack.status IS
        'draft is never returned by packs.live, so Gate 1 cannot find it and nothing '
        'downstream can generate from it. superseded was live and was replaced by a '
        'later publish. abandoned was a draft replaced before anybody published it - '
        'nothing ever provisioned from it, and the two must not share a word.'
    """)

    # Backfill. A superseded version that no run ever used, and that is not the version
    # currently live, was most likely a draft nobody published.
    op.execute("""
        UPDATE business_pack b
        SET status = 'abandoned'
        WHERE b.status = 'superseded'
          AND NOT EXISTS (
            SELECT 1 FROM provisioning_run r
            WHERE r.venture_id = b.venture_id AND r.pack_version = b.pack_version
          )
    """)


def downgrade() -> None:
    op.execute("UPDATE business_pack SET status = 'superseded' WHERE status = 'abandoned'")
    op.execute("ALTER TABLE business_pack DROP CONSTRAINT business_pack_status_check")
    op.execute("""
        ALTER TABLE business_pack ADD CONSTRAINT business_pack_status_check
          CHECK (status IN ('draft', 'live', 'superseded'))
    """)
