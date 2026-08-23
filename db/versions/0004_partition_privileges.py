"""Let office_app provision ledger partitions without holding CREATE on the schema.

Found by test: ensure_ledger_partition() ran as SECURITY INVOKER, so office_app hit
'permission denied for schema public'. Two ways to fix it:

  (a) GRANT CREATE ON SCHEMA public TO office_app
  (b) make the function SECURITY DEFINER

(a) hands the runtime role the ability to create *any* object in the schema -
including a table that shadows one the broker reads. (b) grants exactly one
capability, through one audited function, with a fixed body. Taking (b).

SECURITY DEFINER without a pinned search_path is a privilege-escalation vector:
the caller could point `format`/`to_regclass` resolution at their own schema. The
search_path is therefore set on the function itself, not inherited.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION ensure_ledger_partition(p_month DATE)
        RETURNS TEXT
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          v_start DATE := date_trunc('month', p_month)::date;
          v_end   DATE := (date_trunc('month', p_month) + INTERVAL '1 month')::date;
          v_name  TEXT := 'agent_call_ledger_' || to_char(v_start, 'YYYY_MM');
        BEGIN
          IF to_regclass('public.' || v_name) IS NOT NULL THEN
            RETURN v_name;
          END IF;
          EXECUTE format(
            'CREATE TABLE public.%I PARTITION OF public.agent_call_ledger '
            'FOR VALUES FROM (%L) TO (%L)', v_name, v_start, v_end);
          EXECUTE format('GRANT SELECT, INSERT ON public.%I TO office_app', v_name);
          EXECUTE format(
            'REVOKE UPDATE, DELETE, TRUNCATE ON public.%I FROM office_app', v_name);
          EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', v_name);
          RETURN v_name;
        END $$
    """)

    # A SECURITY DEFINER function is callable by PUBLIC unless told otherwise.
    op.execute("REVOKE ALL ON FUNCTION ensure_ledger_partition(DATE) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION ensure_ledger_partition(DATE) TO office_app")

    op.execute("""
        COMMENT ON FUNCTION ensure_ledger_partition(DATE) IS
        'SECURITY DEFINER with a pinned search_path. Grants office_app exactly one '
        'privileged capability - creating a ledger partition that is itself '
        'append-only - without granting CREATE on the schema.'
    """)


def downgrade() -> None:
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
          EXECUTE format('REVOKE UPDATE, DELETE, TRUNCATE ON %I FROM office_app', v_name);
          RETURN v_name;
        END $$
    """)
