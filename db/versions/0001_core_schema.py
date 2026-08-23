"""Core schema: identity, forge registry, grants, shifts, ledger, audit.

Implements blueprint section 2. One deliberate divergence, recorded in
docs/plans/phase0-schema-ledger-PLAN.md: agent_call_ledger uses a composite
primary key (call_id, ts_start) because PostgreSQL requires every partitioning
column to appear in a unique constraint. The blueprint's `call_id UUID PRIMARY KEY`
on a RANGE-partitioned table is not valid PostgreSQL and will not run.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- IDENTITY
    op.execute("""
        CREATE TABLE office_agent_identity (
          office_agent_id      UUID PRIMARY KEY,
          village_agent_ref    TEXT NOT NULL UNIQUE,
          agent_name           TEXT NOT NULL,
          department           TEXT NOT NULL,
          status               TEXT NOT NULL CHECK (status IN
                                 ('active','suspended','revoked','retired')),
          created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
          revoked_at           TIMESTAMPTZ,
          revoked_by           UUID,
          revocation_reason    TEXT,
          CONSTRAINT revocation_is_complete CHECK (
            (status <> 'revoked')
            OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL
                AND revocation_reason IS NOT NULL)
          )
        )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT revocation_is_complete ON office_agent_identity IS
        'Revocation is the kill switch. A revoked identity must name when, by whom, and why.'
    """)
    op.execute("CREATE INDEX ix_agent_identity_department ON office_agent_identity (department)")
    op.execute(
        "CREATE INDEX ix_agent_identity_active ON office_agent_identity (status) "
        "WHERE status = 'active'"
    )

    op.execute("""
        CREATE TABLE forge_registry (
          forge_id             TEXT PRIMARY KEY,
          display_name         TEXT NOT NULL,
          base_url             TEXT NOT NULL,
          api_version          TEXT NOT NULL,
          auth_model           TEXT NOT NULL,
          credential_mode      TEXT NOT NULL CHECK (credential_mode IN ('brokered','native')),
          health_status        TEXT NOT NULL,
          last_health_check    TIMESTAMPTZ,
          deprecation_date     DATE,
          CONSTRAINT api_version_pinned CHECK (api_version <> 'latest')
        )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT api_version_pinned ON forge_registry IS
        'Validator rule V7: api_version must be pinned. "latest" FAILS.'
    """)

    op.execute("""
        CREATE TABLE forge_module_registry (
          forge_id                 TEXT NOT NULL REFERENCES forge_registry,
          module_id                TEXT NOT NULL,
          module_name              TEXT NOT NULL,
          api_version_introduced   TEXT,
          api_version_deprecated   TEXT,
          compliance_flags_implied TEXT[] NOT NULL DEFAULT '{}',
          idempotency_support      TEXT NOT NULL CHECK (idempotency_support IN
                                     ('key','natural','at_most_once')),
          is_mutating              BOOLEAN NOT NULL,
          PRIMARY KEY (forge_id, module_id)
        )
    """)

    op.execute("""
        CREATE TABLE forge_tenant_credential (
          forge_id             TEXT PRIMARY KEY REFERENCES forge_registry,
          credential_ref       TEXT NOT NULL,
          scope                TEXT NOT NULL CHECK (scope IN ('tenant','agent')),
          rotation_due         DATE NOT NULL,
          last_rotated         TIMESTAMPTZ,
          break_glass_holders  UUID[] NOT NULL,
          CONSTRAINT break_glass_min_two CHECK (
            array_length(break_glass_holders, 1) >= 2
          )
        )
    """)
    op.execute("""
        COMMENT ON COLUMN forge_tenant_credential.credential_ref IS
        'Vault path. NEVER the secret value itself.'
    """)
    op.execute("""
        COMMENT ON CONSTRAINT break_glass_min_two ON forge_tenant_credential IS
        'Two-human break-glass. A single holder is not break-glass, it is a key under a mat.'
    """)

    # ------------------------------------------------------------------ GRANTS
    op.execute("""
        CREATE TABLE agent_forge_grant (
          grant_id              UUID PRIMARY KEY,
          office_agent_id       UUID NOT NULL REFERENCES office_agent_identity,
          forge_id              TEXT NOT NULL,
          module_id             TEXT NOT NULL,
          venture_id            TEXT NOT NULL,
          trust_tier            TEXT NOT NULL CHECK (trust_tier IN
                                  ('auto_execute','propose','suggest')),
          operation_cert_ref    TEXT,
          dept_context_cert_ref TEXT,
          granted_by            UUID NOT NULL,
          granted_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
          revoked_at            TIMESTAMPTZ,
          FOREIGN KEY (forge_id, module_id) REFERENCES forge_module_registry
        )
    """)
    op.execute("""
        CREATE INDEX ix_grant_lookup ON agent_forge_grant
          (office_agent_id, forge_id, module_id) WHERE revoked_at IS NULL
    """)
    op.execute("CREATE INDEX ix_grant_venture ON agent_forge_grant (venture_id)")
    # Invariant 6: either cert reference NULL means not assignable. Expressed as a
    # generated column so "assignable" is one definition in one place, not a
    # predicate every caller re-derives and eventually gets wrong.
    op.execute("""
        ALTER TABLE agent_forge_grant
          ADD COLUMN is_assignable BOOLEAN NOT NULL
          GENERATED ALWAYS AS (
            operation_cert_ref IS NOT NULL
            AND dept_context_cert_ref IS NOT NULL
            AND revoked_at IS NULL
          ) STORED
    """)
    op.execute("""
        COMMENT ON COLUMN agent_forge_grant.is_assignable IS
        'Invariant 6: certification is the grant condition, not advisory metadata. '
        'A grant with either cert ref NULL is not assignable.'
    """)

    # ------------------------------------------------------------------ SHIFTS
    op.execute("""
        CREATE TABLE shift_assignment (
          shift_id             UUID PRIMARY KEY,
          office_agent_id      UUID NOT NULL REFERENCES office_agent_identity,
          venture_id           TEXT NOT NULL,
          shift_start          TIMESTAMPTZ NOT NULL,
          shift_end            TIMESTAMPTZ NOT NULL,
          flush_completed_at   TIMESTAMPTZ,
          flush_verified       BOOLEAN NOT NULL DEFAULT FALSE,
          assigned_by          UUID NOT NULL,
          CONSTRAINT shift_ends_after_start CHECK (shift_end > shift_start),
          CONSTRAINT flush_verified_implies_completed CHECK (
            NOT flush_verified OR flush_completed_at IS NOT NULL
          )
        )
    """)
    op.execute("""
        COMMENT ON COLUMN shift_assignment.flush_completed_at IS
        'Invariant 8: NULL blocks the next assignment for this agent. '
        'A failed PHI flush blocks; it does not log and continue.'
    """)
    op.execute("""
        CREATE INDEX ix_shift_agent_window ON shift_assignment
          (office_agent_id, shift_start DESC)
    """)
    # One venture per agent per shift (invariant 7): overlapping shifts for the
    # same agent are what would make two ventures concurrent. Forbid the overlap.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
        ALTER TABLE shift_assignment
          ADD CONSTRAINT no_overlapping_shifts_per_agent
          EXCLUDE USING gist (
            office_agent_id WITH =,
            tstzrange(shift_start, shift_end) WITH &&
          )
    """)
    op.execute("""
        COMMENT ON CONSTRAINT no_overlapping_shifts_per_agent ON shift_assignment IS
        'Invariant 7: one venture per agent per shift, locked. Overlapping shifts '
        'are the mechanism by which an agent could hold two ventures at once.'
    """)

    # ------------------------------------------------------- LEDGER (append-only)
    # Composite PK: PostgreSQL requires the partition key in every unique
    # constraint. See module docstring.
    op.execute("""
        CREATE TABLE agent_call_ledger (
          call_id                 UUID NOT NULL,
          trace_id                UUID NOT NULL,
          office_agent_id         UUID NOT NULL,
          venture_id              TEXT NOT NULL,
          shift_id                UUID,
          forge_id                TEXT NOT NULL,
          module_id               TEXT NOT NULL,
          api_version             TEXT NOT NULL,
          ts_start                TIMESTAMPTZ NOT NULL,
          ts_end                  TIMESTAMPTZ,
          latency_ms              INT,
          status_code             INT,
          tokens_in               INT,
          tokens_out              INT,
          usd_cost                NUMERIC(12,6),
          trust_tier_at_call      TEXT NOT NULL CHECK (trust_tier_at_call IN
                                    ('auto_execute','propose','suggest')),
          compliance_flags_active TEXT[] NOT NULL DEFAULT '{}',
          data_types_touched      TEXT[] NOT NULL DEFAULT '{}',
          idempotency_key         TEXT,
          manifest_match          TEXT NOT NULL CHECK (manifest_match IN
                                    ('required','declared_only','UNDECLARED')),
          forge_side_ref          TEXT,
          payload_hash            TEXT NOT NULL,
          PRIMARY KEY (call_id, ts_start)
        ) PARTITION BY RANGE (ts_start)
    """)
    op.execute("""
        COMMENT ON TABLE agent_call_ledger IS
        'APPEND-ONLY. Until Forges support per-principal identity, this is the ONLY '
        'per-agent record of Forge activity - Forge-side logs attribute every call to '
        'the tenant. Integrity is load-bearing.'
    """)
    # A DEFAULT partition means a row is never silently rejected for falling
    # outside a provisioned range. Losing a ledger row is worse than an untidy
    # partition; monthly partitions are created ahead of time by ensure_partition.
    op.execute("CREATE TABLE agent_call_ledger_default PARTITION OF agent_call_ledger DEFAULT")
    op.execute("""
        CREATE INDEX ix_ledger_agent_time ON agent_call_ledger (office_agent_id, ts_start DESC)
    """)
    op.execute("CREATE INDEX ix_ledger_trace ON agent_call_ledger (trace_id)")
    op.execute(
        "CREATE INDEX ix_ledger_venture_time ON agent_call_ledger "
        "(venture_id, ts_start DESC)"
    )
    op.execute("""
        CREATE INDEX ix_ledger_undeclared ON agent_call_ledger (ts_start DESC)
          WHERE manifest_match = 'UNDECLARED'
    """)

    op.execute("""
        CREATE FUNCTION ensure_ledger_partition(p_month DATE)
        RETURNS TEXT LANGUAGE plpgsql AS $$
        DECLARE
          v_start DATE := date_trunc('month', p_month)::date;
          v_end   DATE := (date_trunc('month', p_month) + INTERVAL '1 month')::date;
          v_name  TEXT := 'agent_call_ledger_' || to_char(v_start, 'YYYY_MM');
        BEGIN
          IF to_regclass(v_name) IS NOT NULL THEN
            RETURN v_name;
          END IF;
          EXECUTE format(
            'CREATE TABLE %I PARTITION OF agent_call_ledger FOR VALUES FROM (%L) TO (%L)',
            v_name, v_start, v_end);
          RETURN v_name;
        END $$
    """)
    op.execute("""
        COMMENT ON FUNCTION ensure_ledger_partition(DATE) IS
        'Idempotent. Safe to call on every deploy and from a scheduled job.'
    """)

    op.execute("""
        CREATE TABLE audit_log (
          audit_id             BIGINT PRIMARY KEY,
          event_type           TEXT NOT NULL,
          actor_type           TEXT NOT NULL CHECK (actor_type IN ('agent','human','system')),
          actor_id             UUID NOT NULL,
          venture_id           TEXT,
          subject              JSONB NOT NULL,
          trace_id             UUID,
          ts                   TIMESTAMPTZ NOT NULL DEFAULT now(),
          prev_hash            TEXT NOT NULL UNIQUE,
          entry_hash           TEXT NOT NULL UNIQUE
        )
    """)
    # audit_id is assigned inside the chain trigger under an advisory lock, not by
    # a column DEFAULT. If the sequence were consumed before the lock, two writers
    # could acquire ids in one order and the lock in another, making chain order
    # disagree with audit_id order.
    op.execute("CREATE SEQUENCE audit_log_audit_id_seq OWNED BY audit_log.audit_id")
    op.execute("""
        COMMENT ON TABLE audit_log IS
        'APPEND-ONLY, hash-chained, tamper-evident. prev_hash and entry_hash are UNIQUE: '
        'a fork or a replay is a constraint violation, not a silent corruption.'
    """)
    op.execute("CREATE INDEX ix_audit_event_type ON audit_log (event_type, ts DESC)")
    op.execute("CREATE INDEX ix_audit_actor ON audit_log (actor_id, ts DESC)")
    op.execute("CREATE INDEX ix_audit_trace ON audit_log (trace_id)")
    op.execute("CREATE INDEX ix_audit_venture ON audit_log (venture_id, ts DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP SEQUENCE IF EXISTS audit_log_audit_id_seq CASCADE")
    op.execute("DROP FUNCTION IF EXISTS ensure_ledger_partition(DATE)")
    op.execute("DROP TABLE IF EXISTS agent_call_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS shift_assignment CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_forge_grant CASCADE")
    op.execute("DROP TABLE IF EXISTS forge_tenant_credential CASCADE")
    op.execute("DROP TABLE IF EXISTS forge_module_registry CASCADE")
    op.execute("DROP TABLE IF EXISTS forge_registry CASCADE")
    op.execute("DROP TABLE IF EXISTS office_agent_identity CASCADE")
