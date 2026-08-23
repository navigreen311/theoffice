"""The four missing knowledge bases.

Master prompt Part 6 names five. One existed - Forge Operating Instructions - and it is
the model for the other four: a table with a CRUD screen over it is a filing cabinet,
and 6.1 was "elevated from filing cabinet to curriculum" by exactly one property, that
`content_hash` binds certification so republishing decertifies.

Each of these four gets its own equivalent, and the property is why the store exists.

**Business Playbooks - sharing is opt-in, structurally.** Part 6.2: "cross-venture
patterns shareable by opt-in only." A playbook belongs to one venture and becomes
visible to another only through a `playbook_share` row naming both ventures and who
consented. The failure this prevents is one venture's SOP appearing in another's context
because a WHERE clause was forgotten - a tenancy breach that reads as a feature.

**Compliance Library - six fields, all NOT NULL.** An entry with a citation and no
agent-behaviour implication is a legal reference nobody can act on; one with no
escalation trigger tells an agent what to notice and not what to do about it. `entry_ref`
is unique because a Pack's `library_entry_ref` resolves against it - which is what turns
V4 from self-attestation into a check.

**Persona Library - a column privilege, not a convention.** Part 6.4 is one line:
"SimForge only, never production." The production call path runs as `office_app`, so
`office_app` gets INSERT on the whole table and SELECT on every column EXCEPT
`persona_body`. It can author a persona and cannot read one back. A `SELECT
persona_body` anywhere in the runtime - now or written later by someone who never read
this - is a privilege error rather than a leak.

The accepted cost is that the console cannot render a persona body either, because it
runs as the same role. Reviewing one is an out-of-band act on the admin connection. That
is the price of the boundary being real, and it is the same trade the held-out partition
makes.

**Historical Records - append-only, both layers.** Same as the ledger: the grant is the
control and the trigger is defense in depth against someone granting too much later.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Part 6.3, verbatim: "framework, jurisdiction, applicability rule, agent-behavior
# implication, escalation trigger, citation." Six, and a structured store that lets any
# of them be null is a prose store with column headings.
PERSONA_READABLE_COLUMNS = (
    "persona_id",
    "venture_id",
    "persona_name",
    "target_persona",
    "persona_version",
    "body_hash",
    "authored_by",
    "authored_at",
    "superseded_at",
)


def upgrade() -> None:
    # ------------------------------------------------------ 6.2 business playbooks
    op.execute("""
        CREATE TABLE business_playbook (
          playbook_id     UUID PRIMARY KEY,
          venture_id      TEXT NOT NULL,
          title           TEXT NOT NULL,
          lifecycle_stage TEXT,
          content         JSONB NOT NULL,
          content_hash    TEXT NOT NULL,
          playbook_version TEXT NOT NULL,
          authored_by     UUID NOT NULL,
          authored_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          superseded_at   TIMESTAMPTZ,
          UNIQUE (venture_id, title, playbook_version)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_playbook_live ON business_playbook (venture_id, title)
          WHERE superseded_at IS NULL
    """)
    op.execute("""
        CREATE FUNCTION set_playbook_hash() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          NEW.content_hash := encode(
            sha256(convert_to(NEW.content::text, 'UTF8')), 'hex');
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER business_playbook_hash
          BEFORE INSERT OR UPDATE ON business_playbook
          FOR EACH ROW EXECUTE FUNCTION set_playbook_hash()
    """)

    op.execute("""
        CREATE TABLE playbook_share (
          playbook_id     UUID NOT NULL REFERENCES business_playbook,
          to_venture_id   TEXT NOT NULL,
          shared_by       UUID NOT NULL,
          shared_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          revoked_at      TIMESTAMPTZ,
          reason          TEXT NOT NULL,
          PRIMARY KEY (playbook_id, to_venture_id)
        )
    """)
    op.execute("""
        COMMENT ON TABLE playbook_share IS
        'Part 6.2: cross-venture patterns are shareable BY OPT-IN ONLY. Absence of a '
        'row here is a refusal, not an oversight - a playbook is invisible outside its '
        'own venture until somebody named consents in writing.'
    """)

    # ----------------------------------------------------- 6.3 compliance library
    op.execute("""
        CREATE TABLE compliance_library_entry (
          entry_ref            TEXT PRIMARY KEY,
          framework            TEXT NOT NULL CHECK (length(trim(framework)) > 0),
          jurisdiction         TEXT[] NOT NULL CHECK (cardinality(jurisdiction) > 0),
          applicability_rule   TEXT NOT NULL CHECK (length(trim(applicability_rule)) > 0),
          agent_behavior_implication TEXT NOT NULL
                                 CHECK (length(trim(agent_behavior_implication)) > 0),
          escalation_trigger   TEXT NOT NULL CHECK (length(trim(escalation_trigger)) > 0),
          citation             TEXT NOT NULL CHECK (length(trim(citation)) > 0),
          runtime_flag         TEXT,
          authored_by          UUID NOT NULL,
          authored_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        COMMENT ON TABLE compliance_library_entry IS
        'Part 6.3. All six fields NOT NULL and non-blank: an entry with a citation and '
        'no agent-behaviour implication is a legal reference nobody can act on, and one '
        'with no escalation trigger says what to notice and not what to do about it.'
    """)
    op.execute("""
        COMMENT ON COLUMN compliance_library_entry.runtime_flag IS
        'The flag a module or position carries when this entry applies. Nullable: an '
        'entry can exist before anything is flagged for it, which is the direction that '
        'is safe. The reverse - a flag in use with no entry - is what Gate 6 blocks on.'
    """)
    op.execute("""
        CREATE INDEX ix_compliance_flag ON compliance_library_entry (runtime_flag)
          WHERE runtime_flag IS NOT NULL
    """)

    # -------------------------------------------------------- 6.4 persona library
    op.execute("""
        CREATE TABLE persona (
          persona_id      UUID PRIMARY KEY,
          venture_id      TEXT NOT NULL,
          persona_name    TEXT NOT NULL,
          target_persona  TEXT NOT NULL,
          persona_version TEXT NOT NULL,
          persona_body    JSONB NOT NULL,
          body_hash       TEXT NOT NULL,
          authored_by     UUID NOT NULL,
          authored_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          superseded_at   TIMESTAMPTZ,
          UNIQUE (venture_id, persona_name, persona_version)
        )
    """)
    op.execute("""
        COMMENT ON COLUMN persona.persona_body IS
        'SimForge only, never production (Part 6.4). office_app holds INSERT on this '
        'column and NOT SELECT, so the runtime role can author a persona and cannot '
        'read one back. Reviewing a body is an out-of-band act on the admin connection.'
    """)
    op.execute("""
        COMMENT ON COLUMN persona.target_persona IS
        'Which of the Pack''s market.target_personas this stands in for. This is the '
        'join that makes persona coverage countable instead of a vibe.'
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_persona_live ON persona (venture_id, persona_name)
          WHERE superseded_at IS NULL
    """)
    op.execute("""
        CREATE FUNCTION set_persona_hash() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          NEW.body_hash := encode(
            sha256(convert_to(NEW.persona_body::text, 'UTF8')), 'hex');
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER persona_hash
          BEFORE INSERT OR UPDATE ON persona
          FOR EACH ROW EXECUTE FUNCTION set_persona_hash()
    """)

    # ------------------------------------------------------ 6.5 historical records
    op.execute("""
        CREATE TABLE historical_record (
          record_id    BIGSERIAL PRIMARY KEY,
          venture_id   TEXT,
          record_type  TEXT NOT NULL CHECK (record_type IN (
                         'venture_provisioned','provisioning_abandoned',
                         'engagement_closed','incident_resolved','decision','note')),
          summary      TEXT NOT NULL CHECK (length(trim(summary)) > 0),
          detail       JSONB NOT NULL DEFAULT '{}',
          actor_type   TEXT NOT NULL CHECK (actor_type IN ('human','system')),
          recorded_by  UUID,
          occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT a_human_record_names_the_human CHECK (
            actor_type <> 'human' OR recorded_by IS NOT NULL
          )
        )
    """)
    op.execute("""
        COMMENT ON TABLE historical_record IS
        'Part 6.5: append-only institutional memory. `venture_id` is nullable because '
        'some institutional facts are portfolio-wide; `summary` is not, because a '
        'record nobody can read at a glance is an archive rather than a memory.'
    """)
    op.execute("""
        CREATE INDEX ix_history_venture ON historical_record
          (venture_id, occurred_at DESC)
    """)

    # --------------------------------------------------------------------- grants
    for table in ("business_playbook", "playbook_share", "compliance_library_entry"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO office_app")

    # Part 6.4. INSERT on the table, SELECT on every column but the body. This is the
    # control; there is no route to remove and no convention to remember.
    op.execute("GRANT INSERT, UPDATE ON persona TO office_app")
    op.execute(
        "GRANT SELECT (" + ", ".join(PERSONA_READABLE_COLUMNS) + ") ON persona "
        "TO office_app"
    )

    op.execute("GRANT SELECT, INSERT ON historical_record TO office_app")
    op.execute("GRANT USAGE ON SEQUENCE historical_record_record_id_seq TO office_app")
    op.execute("""
        CREATE TRIGGER historical_record_append_only
          BEFORE UPDATE OR DELETE ON historical_record
          FOR EACH ROW EXECUTE FUNCTION ledger_append_only_guard()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS historical_record_append_only ON historical_record")
    op.execute("DROP TABLE IF EXISTS historical_record CASCADE")
    op.execute("DROP TRIGGER IF EXISTS persona_hash ON persona")
    op.execute("DROP TABLE IF EXISTS persona CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_persona_hash()")
    op.execute("DROP TABLE IF EXISTS compliance_library_entry CASCADE")
    op.execute("DROP TABLE IF EXISTS playbook_share CASCADE")
    op.execute("DROP TRIGGER IF EXISTS business_playbook_hash ON business_playbook")
    op.execute("DROP TABLE IF EXISTS business_playbook CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_playbook_hash()")
