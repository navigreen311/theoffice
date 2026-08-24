"""Incident resolution, as an append rather than an edit.

`historical_record.record_type` has included `incident_resolved` since the knowledge
bases landed, and nothing has ever written it - an enum value with no producer, which is
a smaller version of the hardcoded list Gate 6 used to carry. Closing that meant adding
a way to resolve an incident, and the obvious way was wrong.

The obvious way was `UPDATE incident SET resolved_at = now()`. The `incident` table's own
comment forbids it:

    'Append-only. Incidents are detections, not workflow - triage, containment and
     disclosure live in the console (Part 9). An incident is never edited; a later
     finding is a new incident referencing the trace.'

That decision is right and predates me by several phases: a detection that can be edited
is a detection whose record depends on who edited it last, and severity in particular is
the field somebody under pressure would want to lower. So resolution is a separate row,
the incident is untouched, and "resolved" is the presence of a resolution rather than a
column somebody set.

One resolution per incident, by primary key. An incident resolved twice is either a
double-click or a disagreement, and both deserve a refusal rather than a silent
overwrite of who closed it and why.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE incident_resolution (
          incident_id UUID PRIMARY KEY REFERENCES incident,
          resolution  TEXT NOT NULL CHECK (length(trim(resolution)) > 0),
          resolved_by UUID NOT NULL,
          resolved_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        COMMENT ON TABLE incident_resolution IS
        'Resolution is an append, not an edit: incident is append-only by design and a '
        'detection that can be rewritten is a detection worth less than the row it sits '
        'in. Primary key on incident_id, so resolving twice is refused rather than '
        'quietly replacing who closed it and why.'
    """)
    op.execute("""
        COMMENT ON COLUMN incident_resolution.resolution IS
        'What was actually done. Non-blank at the database: "resolved" with nothing '
        'attached is a status change, and the point of closing an incident is the '
        'account of what happened.'
    """)
    op.execute("GRANT SELECT, INSERT ON incident_resolution TO office_app")
    # An UPDATE would let somebody rewrite the account after the fact, and a DELETE
    # would make a resolved incident indistinguishable from one nobody ever looked at.
    op.execute("""
        CREATE TRIGGER incident_resolution_append_only
          BEFORE UPDATE OR DELETE ON incident_resolution
          FOR EACH ROW EXECUTE FUNCTION ledger_append_only_guard()
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS incident_resolution_append_only ON incident_resolution"
    )
    op.execute("DROP TABLE IF EXISTS incident_resolution")
