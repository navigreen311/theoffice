"""Excluding smoke fixtures from a count is a decision, and gets a record type.

The persona library reported sixty entries and held none: every row was a `Smoke NNNNNN`
written by the console smoke script. Filtering those out of the counts is right, and it
is also a judgement - somebody decided which rows do not represent work. A judgement
nobody wrote down is indistinguishable from a filter nobody noticed, which is how sixty
fixtures came to read as a library in the first place.

Neither store can be purged, and neither should be. `persona` is write-only to the
runtime role - it holds no read privilege on a body, let alone DELETE - and
`historical_record` is append-only to everyone, refusing UPDATE and DELETE by trigger. So
the exclusion is a reading decision, and the only honest place to put it is the store
that cannot forget: this record type. The rows it describes stay exactly where they are.

It is deliberately its own type rather than a `note`. A regulator asking "why does this
count differ from the row count" needs to find the answer by its kind, not by reading
every note ever written.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RECORD_TYPES = (
    "venture_provisioned",
    "provisioning_abandoned",
    "engagement_closed",
    "incident_resolved",
    "decision",
    "note",
    "knowledge_fixture_exclusion",
)


def _values(types: Sequence[str]) -> str:
    return ", ".join(f"'{t}'" for t in types)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE historical_record DROP CONSTRAINT "
        "historical_record_record_type_check"
    )
    op.execute(
        "ALTER TABLE historical_record ADD CONSTRAINT "
        "historical_record_record_type_check "
        f"CHECK (record_type IN ({_values(RECORD_TYPES)}))"
    )
    op.execute("""
        COMMENT ON COLUMN historical_record.record_type IS
        'What kind of fact this is. `knowledge_fixture_exclusion` records that smoke '
        'fixtures were left out of the knowledge counts, and by whom - the rows it '
        'describes are never removed, because neither store permits it.'
    """)


def downgrade() -> None:
    # The rows have to go before the constraint can, and this is the one migration where
    # that is a problem worth naming: `historical_record` refuses DELETE by trigger, to
    # everyone, including this migration. Dropping the type means the constraint can no
    # longer describe rows that still exist, so the downgrade widens rather than narrows
    # - it leaves the type valid and only restores the comment. A reversible migration
    # that would have to delete history is not reversible; it is destructive with a
    # tidier name.
    op.execute("""
        COMMENT ON COLUMN historical_record.record_type IS NULL
    """)
