"""Pack store, provisioning runs, and grant activation.

Master prompt Part 11. Two things here are controls rather than storage:

**`agent_forge_grant.activated_at`, and `is_assignable` requiring it.**

Part 11 Gate 7 says "agents appointed but **grants inactive**", and Gate 11 says
"production grants activated". Until now there was no such distinction - a grant written
during sandbox provisioning at Gate 5 was live immediately, so "sandbox" would have
handed agents production authority nine gates early.

Making `is_assignable` depend on it means an inactive grant is refused by the call path
itself, not by a flag somebody checks. Existing grants are backfilled as activated,
because they were issued under the old semantics and silently deactivating live grants
would be a worse surprise than the gap this closes.

**`business_pack.content_hash`, computed by trigger.**

Same rule as instruction hashes: a supplied hash is a claim, a computed one is a fact.
The hash is what a Gate 10 signature binds to, so a caller able to choose it could sign
one Pack and provision another.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GATES = (
    "0", "1", "2", "3", "3.5", "4", "4.5", "5", "6", "7", "8", "9", "9.5",
    "10", "11", "12",
)


def upgrade() -> None:
    # ----------------------------------------------------------------- PACK STORE
    op.execute("""
        CREATE TABLE business_pack (
          venture_id     TEXT NOT NULL,
          pack_version   TEXT NOT NULL,
          schema_version INT NOT NULL,
          yaml_source    TEXT NOT NULL,
          parsed         JSONB NOT NULL,
          content_hash   TEXT NOT NULL,
          authored_by    UUID NOT NULL,
          authored_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          superseded_at  TIMESTAMPTZ,
          PRIMARY KEY (venture_id, pack_version)
        )
    """)
    op.execute("""
        COMMENT ON COLUMN business_pack.content_hash IS
        'Computed by trigger from the YAML source. A Gate 10 signature binds to this, so '
        'a caller able to choose it could sign one Pack and provision another.'
    """)
    op.execute("""
        CREATE UNIQUE INDEX ux_pack_live ON business_pack (venture_id)
          WHERE superseded_at IS NULL
    """)
    op.execute("""
        CREATE FUNCTION set_pack_hash() RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          NEW.content_hash := encode(sha256(convert_to(NEW.yaml_source, 'UTF8')), 'hex');
          RETURN NEW;
        END $$
    """)
    op.execute("""
        CREATE TRIGGER business_pack_hash
          BEFORE INSERT OR UPDATE ON business_pack
          FOR EACH ROW EXECUTE FUNCTION set_pack_hash()
    """)

    # ------------------------------------------------------------ PROVISIONING RUN
    gates_sql = ",".join(f"'{g}'" for g in GATES)
    op.execute(f"""
        CREATE TABLE provisioning_run (
          run_id         UUID PRIMARY KEY,
          venture_id     TEXT NOT NULL,
          pack_version   TEXT NOT NULL,
          pack_hash      TEXT NOT NULL,
          status         TEXT NOT NULL CHECK (status IN
                           ('running','blocked','awaiting_human','complete','aborted')),
          current_gate   TEXT NOT NULL CHECK (current_gate IN ({gates_sql})),
          artifacts_hash TEXT,
          started_by     UUID NOT NULL,
          started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          completed_at   TIMESTAMPTZ,
          FOREIGN KEY (venture_id, pack_version) REFERENCES business_pack
        )
    """)
    op.execute("""
        COMMENT ON COLUMN provisioning_run.pack_hash IS
        'The Pack hash as it was when the run started. A run provisions the Pack it '
        'began with; editing the Pack mid-run does not silently change what is being '
        'provisioned - it invalidates the run''s signatures.'
    """)
    op.execute("""
        COMMENT ON COLUMN provisioning_run.artifacts_hash IS
        'Hash of the generated artifacts. This is what a Gate 10 signature binds to, so '
        'regenerating from an edited Pack voids the signature by comparison.'
    """)
    op.execute("CREATE INDEX ix_run_venture ON provisioning_run (venture_id, started_at DESC)")
    # One run at a time per venture. Two concurrent runs would both issue grants for the
    # same engagement and each would be unaware of the other's gate state.
    op.execute("""
        CREATE UNIQUE INDEX ux_run_active ON provisioning_run (venture_id)
          WHERE status IN ('running','blocked','awaiting_human')
    """)

    op.execute(f"""
        CREATE TABLE provisioning_gate_result (
          gate_result_id UUID PRIMARY KEY,
          run_id         UUID NOT NULL REFERENCES provisioning_run,
          gate           TEXT NOT NULL CHECK (gate IN ({gates_sql})),
          verdict        TEXT NOT NULL CHECK (verdict IN
                           ('passed','blocked','awaiting_human')),
          reason         TEXT NOT NULL,
          evidence       JSONB NOT NULL DEFAULT '{{}}',
          recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        COMMENT ON COLUMN provisioning_gate_result.verdict IS
        'awaiting_human is neither passed nor blocked. A pipeline that auto-advances '
        'through a human review gate is a pipeline without human review, and the tell '
        'is that it still reports having one.'
    """)
    op.execute("""
        CREATE INDEX ix_gate_result_run ON provisioning_gate_result (run_id, recorded_at)
    """)

    # ------------------------------------------------------------ GRANT ACTIVATION
    op.execute("ALTER TABLE agent_forge_grant ADD COLUMN activated_at TIMESTAMPTZ")
    op.execute("ALTER TABLE agent_forge_grant ADD COLUMN activated_by UUID")
    # Backfill: grants that already exist were issued under the old semantics, where a
    # written grant was a live grant. Deactivating them here would be a worse surprise
    # than the gap this closes.
    op.execute("UPDATE agent_forge_grant SET activated_at = granted_at")
    op.execute("""
        COMMENT ON COLUMN agent_forge_grant.activated_at IS
        'NULL until Gate 11. Part 11 Gate 7 issues grants inactive; Gate 11 activates '
        'them against a valid, unvoided Gate 10 signature.'
    """)

    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN is_assignable")
    op.execute("""
        ALTER TABLE agent_forge_grant
          ADD COLUMN is_assignable BOOLEAN NOT NULL
          GENERATED ALWAYS AS (
            operation_cert_ref IS NOT NULL
            AND dept_context_cert_ref IS NOT NULL
            AND revoked_at IS NULL
            AND activated_at IS NOT NULL
          ) STORED
    """)
    op.execute("""
        COMMENT ON COLUMN agent_forge_grant.is_assignable IS
        'Invariant 6 plus Gate 11. An inactive grant is refused by the call path itself, '
        'not by a flag somebody remembers to check.'
    """)
    op.execute("""
        CREATE INDEX ix_grant_lookup_active ON agent_forge_grant
          (office_agent_id, forge_id, module_id)
          WHERE revoked_at IS NULL AND activated_at IS NOT NULL
    """)

    for table in ("business_pack", "provisioning_run", "provisioning_gate_result"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE ON {table} TO office_app")
    # A gate result is evidence of what a run decided. Deleting one would make a gate
    # that blocked indistinguishable from a gate that never ran.
    op.execute("REVOKE DELETE ON provisioning_gate_result FROM office_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS provisioning_gate_result CASCADE")
    op.execute("DROP TABLE IF EXISTS provisioning_run CASCADE")
    op.execute("DROP TRIGGER IF EXISTS business_pack_hash ON business_pack")
    op.execute("DROP TABLE IF EXISTS business_pack CASCADE")
    op.execute("DROP FUNCTION IF EXISTS set_pack_hash()")
    op.execute("DROP INDEX IF EXISTS ix_grant_lookup_active")
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN IF EXISTS is_assignable")
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN IF EXISTS activated_at")
    op.execute("ALTER TABLE agent_forge_grant DROP COLUMN IF EXISTS activated_by")
    op.execute("""
        ALTER TABLE agent_forge_grant
          ADD COLUMN is_assignable BOOLEAN NOT NULL
          GENERATED ALWAYS AS (
            operation_cert_ref IS NOT NULL
            AND dept_context_cert_ref IS NOT NULL
            AND revoked_at IS NULL
          ) STORED
    """)
