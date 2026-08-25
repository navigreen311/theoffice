"""Incidents get a published kind, a detection source, and a stage timeline.

`severity` has always had a CHECK constraint. `kind` had none, so any string was a kind
and a column with a schema-shaped name was a free-text field. Two call sites could raise
the same condition under different spellings and nothing would notice.

The list comes from `broker/incident_taxonomy.py`, which is derived from the call sites
that actually raise incidents plus the three a human can file. It is imported here rather
than retyped, so a kind added to one and not the other fails at migration time instead of
at the first attempt to raise it.

`incident_account` is new. An incident is a detection and is never edited; the response -
Part 9's detection, triage, containment, disclosure, post-mortem - happened somewhere off
the record entirely. Accounts are appended, one per stage per writer, and the table gets
the same append-only trigger the other ledgers carry: the point of a response timeline is
that it cannot be tidied afterwards.

`detection_source` and `reported_by` are on the incident itself because they are part of
the detection, not part of the response. A regulator inquiry filed by a named human must
never be indistinguishable from something a control caught.
"""

from collections.abc import Sequence

from alembic import op

from broker.incident_taxonomy import DETECTION_SOURCES, KIND_NAMES, STAGE_NAMES

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _values(items: Sequence[str]) -> str:
    return ", ".join(f"'{item}'" for item in items)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE incident ADD CONSTRAINT incident_kind_check "
        f"CHECK (kind IN ({_values(KIND_NAMES)}))"
    )
    op.execute("""
        COMMENT ON COLUMN incident.kind IS
        'One of the published kinds in broker/incident_taxonomy.py. Constrained here so '
        'the column cannot quietly become free text again; the taxonomy is derived from '
        'the call sites that raise incidents, and a test walks the source to keep them '
        'from drifting.'
    """)

    # How the detection arrived. Defaulted for the automatic path, because every
    # existing raiser is a control or the broker itself.
    op.execute(
        "ALTER TABLE incident ADD COLUMN detection_source TEXT NOT NULL "
        "DEFAULT 'control_sweep' "
        f"CHECK (detection_source IN ({_values(DETECTION_SOURCES)}))"
    )
    op.execute("ALTER TABLE incident ADD COLUMN reported_by UUID REFERENCES office_human(human_id)")
    op.execute("""
        ALTER TABLE incident ADD CONSTRAINT incident_human_source_is_attributed CHECK (
          detection_source IN ('agent_flag', 'control_sweep') OR reported_by IS NOT NULL
        )
    """)
    op.execute("""
        COMMENT ON COLUMN incident.reported_by IS
        'The human who filed this, for an external report or a regulator inquiry. '
        'Required for those sources: an incident a person raised must never be '
        'indistinguishable from one a control caught.'
    """)

    op.execute(f"""
        CREATE TABLE incident_account (
          account_id   BIGSERIAL PRIMARY KEY,
          incident_id  UUID NOT NULL REFERENCES incident(incident_id),
          stage        TEXT NOT NULL CHECK (stage IN ({_values(STAGE_NAMES)})),
          account      TEXT NOT NULL CHECK (length(btrim(account)) > 0),
          written_by   UUID NOT NULL REFERENCES office_human(human_id),
          written_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX ix_incident_account_incident "
        "ON incident_account (incident_id, written_at)"
    )
    op.execute("""
        COMMENT ON TABLE incident_account IS
        'The response to an incident, appended one stage at a time. Append-only: a '
        'response timeline that can be edited afterwards is a draft of what somebody '
        'wishes had happened. Correcting an account means appending a later one.'
    """)

    # The same guard the other ledgers carry, and for the same reason.
    op.execute("""
        CREATE TRIGGER incident_account_append_only
        BEFORE DELETE OR UPDATE ON incident_account
        FOR EACH ROW EXECUTE FUNCTION ledger_append_only_guard()
    """)
    op.execute("GRANT SELECT, INSERT ON incident_account TO office_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE incident_account_account_id_seq TO office_app")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS incident_account_append_only ON incident_account")
    op.execute("DROP TABLE IF EXISTS incident_account")
    op.execute(
        "ALTER TABLE incident DROP CONSTRAINT IF EXISTS "
        "incident_human_source_is_attributed"
    )
    op.execute("ALTER TABLE incident DROP COLUMN IF EXISTS reported_by")
    op.execute("ALTER TABLE incident DROP COLUMN IF EXISTS detection_source")
    op.execute("ALTER TABLE incident DROP CONSTRAINT IF EXISTS incident_kind_check")
