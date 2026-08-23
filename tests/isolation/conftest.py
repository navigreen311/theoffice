"""Fixtures for the isolation suite."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import psycopg
import pytest


@pytest.fixture(autouse=True)
def _clean_shifts(admin: psycopg.Connection) -> Iterator[None]:
    """Shifts and working memory are shared state across tests.

    A leftover unflushed shift blocks the next test's assignment for a reason that
    test has nothing to do with - and the failure looks exactly like the control
    working, which is the worst kind of false positive.
    """
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_working_memory")
        cur.execute("DELETE FROM shift_assignment")
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    conn.commit()


@pytest.fixture
def certified_forge(admin: psycopg.Connection, seed_agent):
    """A Forge with a module, live instructions, and one certified agent.

    Enough for the staleness sweep to have something real to invalidate.
    """
    import psycopg.types.json

    forge_id = f"sweep-forge-{uuid.uuid4().hex[:8]}"
    module_id = "sweep_module"
    cert_id = uuid.uuid4()
    content = {
        "what_it_does": "x", "what_it_does_not_do": "x", "inputs": {"a": "b"},
        "correct_sequence": ["a"], "failure_signatures": {"a": "b"},
        "retry_vs_escalate": "x", "never_do": ["x"], "compliance_coupling": ["x"],
    }

    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, %s, 'https://example.invalid', '1.4.0', 'bearer',
                    'brokered', 'GREEN')
            """,
            (forge_id, forge_id),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating)
            VALUES (%s, %s, 'Sweep Module', 'key', TRUE)
            """,
            (forge_id, module_id),
        )
        cur.execute(
            """
            INSERT INTO forge_operating_instruction
              (forge_id, module_id, instruction_version, forge_api_version,
               content, content_hash, authored_by)
            VALUES (%s, %s, '1.0.0', '1.4.0', %s, '', %s)
            RETURNING content_hash
            """,
            (forge_id, module_id, psycopg.types.json.Jsonb(content), str(uuid.uuid4())),
        )
        row = cur.fetchone()
        assert row is not None
        cur.execute(
            """
            INSERT INTO certification
              (cert_id, unit, office_agent_id, forge_id, module_id, state,
               certified_tier, instruction_content_hash, forge_api_version,
               rubric_kind, rubric_version, simforge_verdict)
            VALUES (%s, 'A', %s, %s, %s, 'certified', 'auto_execute', %s, '1.4.0',
                    'operation', '1.0.0', 'PASS')
            """,
            (str(cert_id), seed_agent, forge_id, module_id, row[0]),
        )
    admin.commit()
    yield forge_id, module_id, seed_agent, cert_id
    with admin.cursor() as cur:
        cur.execute("DELETE FROM agent_forge_grant WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM certification WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM forge_operating_instruction WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM forge_module_registry WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    admin.commit()
