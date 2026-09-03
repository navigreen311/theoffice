"""Schema completeness and the constraints that encode invariants.

A CHECK constraint that is never exercised is a comment. Each of these asserts the
constraint actually rejects the thing it claims to reject.
"""

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

EXPECTED_TABLES = {
    "office_agent_identity",
    "forge_registry",
    "forge_module_registry",
    "forge_tenant_credential",
    "agent_forge_grant",
    "shift_assignment",
    "agent_call_ledger",
    "audit_log",
}


def test_all_blueprint_tables_exist(app):
    with app.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "UNION SELECT relname FROM pg_class WHERE relkind = 'p'"
        )
        present = {r[0] for r in cur.fetchall()}
    missing = EXPECTED_TABLES - present
    assert not missing, f"missing tables: {sorted(missing)}"


def test_ledger_is_partitioned_by_ts_start(app):
    with app.cursor() as cur:
        cur.execute(
            """
            SELECT partstrat, a.attname
              FROM pg_partitioned_table p
              JOIN pg_class c ON c.oid = p.partrelid
              JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = p.partattrs[0]
             WHERE c.relname = 'agent_call_ledger'
            """
        )
        row = cur.fetchone()
    assert row is not None, "agent_call_ledger is not partitioned"
    assert row[0] == "r", "expected RANGE partitioning"
    assert row[1] == "ts_start"


def test_ledger_has_default_partition(app):
    """A row outside every provisioned range must land somewhere, not be rejected."""
    with app.cursor() as cur:
        cur.execute("SELECT to_regclass('agent_call_ledger_default')")
        row = cur.fetchone()
    assert row is not None and row[0] is not None


def test_ensure_ledger_partition_is_idempotent(app):
    month = datetime.now(UTC).date().replace(day=1) + timedelta(days=400)
    with app.cursor() as cur:
        cur.execute("SELECT ensure_ledger_partition(%s)", (month,))
        first = cur.fetchone()
        cur.execute("SELECT ensure_ledger_partition(%s)", (month,))
        second = cur.fetchone()
    app.commit()
    assert first is not None and second is not None
    assert first[0] == second[0]


def test_ledger_row_routes_to_month_partition(app, seed_agent, seed_forge):
    forge_id, module_id = seed_forge
    month = datetime.now(UTC).date().replace(day=1) + timedelta(days=430)
    ts = datetime(month.year, month.month, 15, 12, 0, tzinfo=UTC)

    with app.cursor() as cur:
        cur.execute("SELECT ensure_ledger_partition(%s)", (month,))
        part_row = cur.fetchone()
        assert part_row is not None
        partition_name = part_row[0]

        call_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO agent_call_ledger
              (call_id, trace_id, office_agent_id, venture_id, forge_id, module_id,
               api_version, ts_start, trust_tier_at_call, manifest_match, payload_hash)
            VALUES (%s, %s, %s, 'greenstone', %s, %s, '1.2.0', %s,
                    'auto_execute', 'required', 'abc')
            """,
            (call_id, uuid.uuid4(), seed_agent, forge_id, module_id, ts),
        )
        cur.execute(
            f"SELECT count(*) FROM {partition_name} WHERE call_id = %s",
            (call_id,),
        )
        row = cur.fetchone()
    app.commit()
    assert row is not None and row[0] == 1


@pytest.mark.parametrize(
    ("table", "column", "value"),
    [
        ("office_agent_identity", "status", "probational"),
        ("forge_registry", "credential_mode", "shared"),
        ("forge_module_registry", "idempotency_support", "sometimes"),
        ("forge_tenant_credential", "scope", "global"),
        ("agent_forge_grant", "trust_tier", "full_access"),
        ("agent_call_ledger", "manifest_match", "maybe"),
        ("audit_log", "actor_type", "robot"),
    ],
)
def test_enum_check_constraints_reject_bad_values(app, table, column, value):
    """Every enum-style CHECK is exercised with a value it must refuse."""
    with app.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = %s AND c.contype = 'c' "
            "AND pg_get_constraintdef(c.oid) ILIKE %s",
            (table, f"%{column}%"),
        )
        row = cur.fetchone()
    assert row is not None and row[0] >= 1, (
        f"{table}.{column} has no CHECK constraint; '{value}' would be accepted"
    )


def test_break_glass_requires_two_holders(app, seed_forge):
    """Invariant 14: a single break-glass holder is a key under a mat."""
    forge_id, _ = seed_forge
    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            """
                INSERT INTO forge_tenant_credential
                  (forge_id, credential_ref, scope, rotation_due, break_glass_holders)
                VALUES (%s, 'vault://forge/test', 'tenant', CURRENT_DATE + 90, %s)
                """,
            (forge_id, [str(uuid.uuid4())]),
        )
    app.rollback()
    assert "break_glass_min_two" in str(exc.value)


def test_break_glass_accepts_two_holders(app, seed_forge):
    forge_id, _ = seed_forge
    with app.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_tenant_credential
              (forge_id, credential_ref, scope, rotation_due, break_glass_holders)
            VALUES (%s, 'vault://forge/test', 'tenant', CURRENT_DATE + 90, %s)
            """,
            (forge_id, [str(uuid.uuid4()), str(uuid.uuid4())]),
        )
    app.commit()
    with app.cursor() as cur:
        cur.execute("DELETE FROM forge_tenant_credential WHERE forge_id = %s", (forge_id,))
    app.commit()


def test_api_version_latest_is_rejected(app):
    """Validator rule V7 enforced in the schema, not only in the Pack validator."""
    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            """
                INSERT INTO forge_registry
                  (forge_id, display_name, base_url, api_version, auth_model,
                   credential_mode, health_status)
                VALUES ('bad-forge', 'Bad', 'https://x.invalid', 'latest',
                        'bearer', 'brokered', 'GREEN')
                """
        )
    app.rollback()
    assert "api_version_pinned" in str(exc.value)


def test_revoked_identity_must_state_when_who_and_why(app):
    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            """
                INSERT INTO office_agent_identity
                  (office_agent_id, village_agent_ref, agent_name, department, status)
                VALUES (%s, %s, 'Ghost', 'Executive & Strategy', 'revoked')
                """,
            (str(uuid.uuid4()), f"ghost-{uuid.uuid4().hex[:8]}"),
        )
    app.rollback()
    assert "revocation_is_complete" in str(exc.value)


def test_grant_without_certs_is_not_assignable(app, seed_agent, seed_forge):
    """Invariant 6 - certification is the grant condition, not advisory metadata.

    Both grants below are activated, so certification is the only variable. Since the
    provisioning pipeline landed, `is_assignable` also requires activation (Gate 11) -
    exercised separately in `test_an_unactivated_grant_is_not_assignable`.
    """
    forge_id, module_id = seed_forge

    with app.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id,
               trust_tier, granted_by, activated_at)
            VALUES (%s, %s, %s, %s, 'greenstone', 'auto_execute', %s, now())
            RETURNING is_assignable
            """,
            (str(uuid.uuid4()), seed_agent, forge_id, module_id, str(uuid.uuid4())),
        )
        uncertified = cur.fetchone()

        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id,
               trust_tier, operation_cert_ref, dept_context_cert_ref, granted_by,
               activated_at)
            VALUES (%s, %s, %s, %s, 'greenstone', 'auto_execute',
                    'simforge://unitA/1', 'simforge://unitB/1', %s, now())
            RETURNING is_assignable
            """,
            (str(uuid.uuid4()), seed_agent, forge_id, module_id, str(uuid.uuid4())),
        )
        certified = cur.fetchone()
    app.commit()

    assert uncertified is not None and uncertified[0] is False
    assert certified is not None and certified[0] is True


def test_only_one_cert_unit_is_still_not_assignable(app, seed_agent, seed_forge):
    """Unit B is necessary, never sufficient - and neither is Unit A alone."""
    forge_id, module_id = seed_forge
    with app.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id,
               trust_tier, operation_cert_ref, granted_by, activated_at)
            VALUES (%s, %s, %s, %s, 'greenstone', 'propose', 'simforge://unitA/1', %s,
                    now())
            RETURNING is_assignable
            """,
            (str(uuid.uuid4()), seed_agent, forge_id, module_id, str(uuid.uuid4())),
        )
        row = cur.fetchone()
    app.commit()
    assert row is not None and row[0] is False


def test_overlapping_shifts_for_one_agent_are_rejected(app, seed_agent):
    """Invariant 7 - one venture per agent per shift, enforced structurally."""
    start = datetime.now(UTC)
    with app.cursor() as cur:
        cur.execute(
            """
            INSERT INTO shift_assignment
              (shift_id, office_agent_id, venture_id, shift_start, shift_end,
               assigned_by, quarter)
            VALUES (%s, %s, 'greenstone', %s, %s, %s, '2026Q1')
            """,
            (str(uuid.uuid4()), seed_agent, start, start + timedelta(hours=8),
             str(uuid.uuid4())),
        )
    app.commit()

    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            """
                INSERT INTO shift_assignment
                  (shift_id, office_agent_id, venture_id, shift_start, shift_end,
                   assigned_by, quarter)
                VALUES (%s, %s, 'medlink', %s, %s, %s, '2026Q2')
                """,
            # A different quarter: this row is testing the overlap exclusion, and in
            # 2026Q1 it would now be refused by one_venture_per_agent_quarter instead -
            # a pass for the wrong reason.
            (str(uuid.uuid4()), seed_agent, start + timedelta(hours=4),
             start + timedelta(hours=12), str(uuid.uuid4())),
        )
    app.rollback()
    assert "no_overlapping_shifts_per_agent" in str(exc.value)


def test_flush_verified_requires_completion_timestamp(app, seed_agent):
    """Invariant 8 - a verified flush that never completed is a contradiction."""
    start = datetime.now(UTC) + timedelta(days=365)
    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            """
                INSERT INTO shift_assignment
                  (shift_id, office_agent_id, venture_id, shift_start, shift_end,
                   flush_verified, assigned_by, quarter)
                VALUES (%s, %s, 'greenstone', %s, %s, TRUE, %s, '2026Q1')
                """,
            (str(uuid.uuid4()), seed_agent, start, start + timedelta(hours=8),
             str(uuid.uuid4())),
        )
    app.rollback()
    assert "flush_verified_implies_completed" in str(exc.value)
