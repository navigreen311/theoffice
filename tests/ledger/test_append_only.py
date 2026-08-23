"""Invariant 1 - the ledger is append-only.

Every assertion here runs as office_app, the role the broker actually uses.
Asserting against the superuser connection would pass trivially and prove nothing.
"""

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from tests.conftest import insert_audit, requires_db

pytestmark = [requires_db, pytest.mark.db]


def _insert_ledger_row(conn: psycopg.Connection, agent_id: uuid.UUID,
                       forge_id: str, module_id: str) -> uuid.UUID:
    call_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_call_ledger
              (call_id, trace_id, office_agent_id, venture_id, forge_id, module_id,
               api_version, ts_start, trust_tier_at_call, manifest_match, payload_hash)
            VALUES (%s, %s, %s, 'greenstone', %s, %s, '1.2.0', %s,
                    'auto_execute', 'required', 'deadbeef')
            """,
            (call_id, uuid.uuid4(), agent_id, forge_id, module_id, datetime.now(UTC)),
        )
    conn.commit()
    return call_id


def test_app_role_can_insert_ledger(app, seed_agent, seed_forge):
    """Writers must work. An append-only table nobody can append to is just broken."""
    forge_id, module_id = seed_forge
    call_id = _insert_ledger_row(app, seed_agent, forge_id, module_id)

    with app.cursor() as cur:
        cur.execute("SELECT count(*) FROM agent_call_ledger WHERE call_id = %s", (call_id,))
        row = cur.fetchone()
    assert row is not None and row[0] == 1


def test_app_role_cannot_update_ledger(app, seed_agent, seed_forge):
    forge_id, module_id = seed_forge
    call_id = _insert_ledger_row(app, seed_agent, forge_id, module_id)

    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            "UPDATE agent_call_ledger SET usd_cost = 0 WHERE call_id = %s", (call_id,)
        )
    app.rollback()
    assert "permission denied" in str(exc.value).lower() or "append-only" in str(exc.value).lower()


def test_app_role_cannot_delete_ledger(app, seed_agent, seed_forge):
    forge_id, module_id = seed_forge
    call_id = _insert_ledger_row(app, seed_agent, forge_id, module_id)

    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute("DELETE FROM agent_call_ledger WHERE call_id = %s", (call_id,))
    app.rollback()
    assert "permission denied" in str(exc.value).lower() or "append-only" in str(exc.value).lower()


def test_app_role_cannot_truncate_ledger(app):
    with pytest.raises(psycopg.Error), app.cursor() as cur:
        cur.execute("TRUNCATE agent_call_ledger")
    app.rollback()


def test_app_role_can_insert_audit(app, clean_audit):
    audit_id = insert_audit(app)
    assert audit_id >= 1


def test_app_role_cannot_update_audit(app, clean_audit):
    audit_id = insert_audit(app)

    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET event_type = 'tampered' WHERE audit_id = %s", (audit_id,)
        )
    app.rollback()
    assert "permission denied" in str(exc.value).lower() or "append-only" in str(exc.value).lower()


def test_app_role_cannot_delete_audit(app, clean_audit):
    audit_id = insert_audit(app)

    with pytest.raises(psycopg.Error) as exc, app.cursor() as cur:
        cur.execute("DELETE FROM audit_log WHERE audit_id = %s", (audit_id,))
    app.rollback()
    assert "permission denied" in str(exc.value).lower() or "append-only" in str(exc.value).lower()


def test_guard_trigger_fires_even_for_owner(admin, clean_audit):
    """Defense in depth: the trigger stops an UPDATE that role grants would allow.

    The owner has UPDATE privilege. The trigger is what stops it, which is the
    point - it catches the case where grants are later misconfigured.
    """
    audit_id = insert_audit(admin)

    with pytest.raises(psycopg.Error) as exc, admin.cursor() as cur:
        cur.execute(
            "UPDATE audit_log SET event_type = 'tampered' WHERE audit_id = %s", (audit_id,)
        )
    admin.rollback()
    assert "append-only violation" in str(exc.value).lower()


def test_app_role_has_no_update_privilege_recorded(app):
    """Assert the grant itself, not just the observed behaviour.

    Behaviour could be produced by the trigger alone. This checks the control -
    role grants - is genuinely absent, so the trigger is redundancy rather than
    the only thing standing there.
    """
    with app.cursor() as cur:
        cur.execute(
            """
            SELECT has_table_privilege('office_app', 'agent_call_ledger', 'UPDATE'),
                   has_table_privilege('office_app', 'agent_call_ledger', 'DELETE'),
                   has_table_privilege('office_app', 'audit_log', 'UPDATE'),
                   has_table_privilege('office_app', 'audit_log', 'DELETE'),
                   has_table_privilege('office_app', 'agent_call_ledger', 'INSERT'),
                   has_table_privilege('office_app', 'audit_log', 'INSERT')
            """
        )
        row = cur.fetchone()
    assert row is not None
    can_update_ledger, can_delete_ledger, can_update_audit, can_delete_audit, \
        can_insert_ledger, can_insert_audit = row

    assert can_update_ledger is False
    assert can_delete_ledger is False
    assert can_update_audit is False
    assert can_delete_audit is False
    assert can_insert_ledger is True
    assert can_insert_audit is True
