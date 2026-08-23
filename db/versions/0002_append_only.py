"""Append-only enforcement on the ledger tables.

Invariant 1. Two layers, deliberately:

  1. ROLE GRANTS are the control. office_app holds INSERT and SELECT on
     agent_call_ledger and audit_log, and nothing else. UPDATE and DELETE are
     not revoked-after-grant; they are never granted.

  2. A BEFORE UPDATE OR DELETE trigger is defense in depth. It does not stop a
     superuser and is not pretending to. It catches the realistic failure -
     someone grants office_app too much later, or a migration connects as owner
     and runs an UPDATE by mistake.

Layer 1 without layer 2 fails silently on misconfiguration. Layer 2 without
layer 1 is a convention. Both.

Revision ID: 0002
Revises: 0001
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEDGER_TABLES = ("agent_call_ledger", "audit_log")

OPERATIONAL_TABLES = (
    "office_agent_identity",
    "forge_registry",
    "forge_module_registry",
    "forge_tenant_credential",
    "agent_forge_grant",
    "shift_assignment",
)


def upgrade() -> None:
    password = os.environ.get("OFFICE_APP_PASSWORD")
    if not password:
        raise RuntimeError(
            "OFFICE_APP_PASSWORD is not set. Set it in the environment before "
            "running migrations. See .env.example."
        )
    if "'" in password:
        raise RuntimeError("OFFICE_APP_PASSWORD must not contain a single quote.")

    op.execute("""
        CREATE FUNCTION ledger_append_only_guard()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION
            'append-only violation: % is not permitted on %',
            TG_OP, TG_TABLE_NAME
            USING ERRCODE = 'insufficient_privilege',
                  HINT = 'Ledger tables are append-only. Correct a bad entry by '
                         'appending a compensating entry, never by editing history.';
        END $$
    """)

    for table in LEDGER_TABLES:
        op.execute(f"""
            CREATE TRIGGER {table}_append_only
              BEFORE UPDATE OR DELETE ON {table}
              FOR EACH ROW EXECUTE FUNCTION ledger_append_only_guard()
        """)

    # The runtime role. NOSUPERUSER/NOCREATEDB are explicit rather than default-relied.
    op.execute(f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'office_app') THEN
            CREATE ROLE office_app LOGIN PASSWORD '{password}'
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          ELSE
            ALTER ROLE office_app WITH LOGIN PASSWORD '{password}'
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
          END IF;
        END $$
    """)

    op.execute("GRANT USAGE ON SCHEMA public TO office_app")

    for table in OPERATIONAL_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO office_app")

    # Ledger: INSERT and SELECT only. UPDATE and DELETE are never granted.
    for table in LEDGER_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {table} TO office_app")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM office_app")

    # Partitions inherit privileges only if granted; the DEFAULT partition and any
    # monthly partition must be granted explicitly.
    op.execute("GRANT SELECT, INSERT ON agent_call_ledger_default TO office_app")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON agent_call_ledger_default FROM office_app")

    op.execute("GRANT USAGE ON SEQUENCE audit_log_audit_id_seq TO office_app")
    op.execute("GRANT EXECUTE ON FUNCTION ensure_ledger_partition(DATE) TO office_app")

    # New monthly partitions must not silently arrive without the grant. Make the
    # grant part of partition creation itself.
    op.execute("""
        CREATE OR REPLACE FUNCTION ensure_ledger_partition(p_month DATE)
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
          EXECUTE format('GRANT SELECT, INSERT ON %I TO office_app', v_name);
          EXECUTE format(
            'REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM office_app', v_name);
          RETURN v_name;
        END $$
    """)

    # Nothing reaches the ledger except through a granted role.
    for table in LEDGER_TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM PUBLIC")
    op.execute("REVOKE ALL ON agent_call_ledger_default FROM PUBLIC")


def downgrade() -> None:
    for table in LEDGER_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS ledger_append_only_guard()")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM office_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM office_app")
    op.execute("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM office_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM office_app")
