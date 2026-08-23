"""Shared test fixtures.

Two connections, deliberately:

  admin  - superuser. Used to set up fixtures and to SIMULATE AN ATTACKER for the
           tamper tests. Never the subject of an append-only assertion; a
           superuser bypasses role grants, so asserting against it would prove
           nothing.

  app    - the office_app role. This is the one the broker uses at runtime, and
           the only one whose permissions are worth asserting.

Tests that mix them up are the easy way to ship a false green here.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
import pytest_asyncio

from broker.db import close_pool

ADMIN_DSN = os.environ.get("OFFICE_ADMIN_DSN")
APP_DSN = os.environ.get("OFFICE_APP_DSN")

# Every table that references a Forge or one of its modules, in deletion order.
# One list, because this has bitten four times: each phase adds another referencing
# table, and a fixture that hard-codes its own list silently goes stale.
FORGE_DEPENDENTS = (
    "certification",
    "forge_operating_instruction",
    "curriculum_submission",
    "venture_forge_manifest",
    "manifest_disposition",
    "proposal",
    "agent_forge_grant",
    "forge_tenant_credential",
    "forge_module_registry",
)


def drop_forge(conn: psycopg.Connection, forge_id: str) -> None:
    """Delete a Forge and everything that references it, in order."""
    with conn.cursor() as cur:
        for table in FORGE_DEPENDENTS:
            cur.execute(
                f"DELETE FROM {table} WHERE forge_id = %s",
                (forge_id,),
            )
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    conn.commit()


requires_db = pytest.mark.skipif(
    not ADMIN_DSN or not APP_DSN,
    reason="OFFICE_ADMIN_DSN and OFFICE_APP_DSN must be set (see .env.example)",
)


@pytest.fixture(scope="session")
def admin_dsn() -> str:
    assert ADMIN_DSN, "OFFICE_ADMIN_DSN not set"
    return ADMIN_DSN


@pytest.fixture(scope="session")
def app_dsn() -> str:
    assert APP_DSN, "OFFICE_APP_DSN not set"
    return APP_DSN


@pytest.fixture
def admin(admin_dsn: str) -> Iterator[psycopg.Connection]:
    """Superuser connection. Autocommit off; rolled back after each test."""
    with psycopg.connect(admin_dsn) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def app(app_dsn: str) -> Iterator[psycopg.Connection]:
    """The runtime role. Its privileges are the thing under test."""
    with psycopg.connect(app_dsn) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def clean_audit(admin: psycopg.Connection) -> Iterator[None]:
    """Empty audit_log and reset the sequence, so chain assertions start at genesis.

    Uses ALTER TABLE ... DISABLE TRIGGER because the append-only guard is doing
    exactly its job here. Superuser-only; never available to office_app.
    """
    _truncate_audit(admin)
    yield
    _truncate_audit(admin)


def _truncate_audit(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
        cur.execute("ALTER SEQUENCE audit_log_audit_id_seq RESTART WITH 1")
    conn.commit()


@pytest.fixture
def seed_forge(admin: psycopg.Connection) -> Iterator[tuple[str, str]]:
    """A registered Forge and module, for grant and ledger tests."""
    forge_id = f"test-forge-{uuid.uuid4().hex[:8]}"
    module_id = "parse_document"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'Test Forge', 'https://example.invalid', '1.2.0',
                    'bearer', 'brokered', 'GREEN')
            """,
            (forge_id,),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating)
            VALUES (%s, %s, 'Parse Document', 'key', TRUE)
            """,
            (forge_id, module_id),
        )
    admin.commit()
    yield forge_id, module_id
    drop_forge(admin, forge_id)


@pytest.fixture
def seed_agent(admin: psycopg.Connection) -> Iterator[uuid.UUID]:
    """An active agent identity."""
    agent_id = uuid.uuid4()
    ref = f"test-agent-{agent_id.hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO office_agent_identity
              (office_agent_id, village_agent_ref, agent_name, department, status)
            VALUES (%s, %s, 'Test Agent', 'AI & Data Science', 'active')
            """,
            (agent_id, ref),
        )
    admin.commit()
    yield agent_id
    with admin.cursor() as cur:
        # Everything that references the identity, before the identity itself.
        cur.execute("DELETE FROM agent_forge_grant WHERE office_agent_id = %s", (agent_id,))
        # Working memory references the shift, so it must go before the shift does.
        cur.execute(
            "DELETE FROM agent_working_memory WHERE office_agent_id = %s", (agent_id,)
        )
        cur.execute("DELETE FROM shift_assignment WHERE office_agent_id = %s", (agent_id,))
        for table in ("revocation", "proposal"):
            cur.execute(
                f"DELETE FROM {table} WHERE office_agent_id = %s",
                (agent_id,),
            )
        cur.execute("DELETE FROM office_agent_identity WHERE office_agent_id = %s", (agent_id,))
    admin.commit()


def insert_audit(
    conn: psycopg.Connection,
    event_type: str = "test_event",
    actor_type: str = "system",
    subject: str = '{"k": "v"}',
) -> int:
    """Insert one audit entry and return its assigned audit_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (event_type, actor_type, actor_id, venture_id, subject)
            VALUES (%s, %s, %s, 'test-venture', %s::jsonb)
            RETURNING audit_id
            """,
            (event_type, actor_type, str(uuid.uuid4()), subject),
        )
        row = cur.fetchone()
    assert row is not None
    conn.commit()
    return int(row[0])


def verify_chain(conn: psycopg.Connection) -> tuple[bool, int, int | None, str]:
    """Chain verdict: (ok, checked_count, first_break_audit_id, reason)."""
    with conn.cursor() as cur:
        cur.execute("SELECT ok, checked_count, first_break_audit_id, reason "
                    "FROM audit_log_verify_chain()")
        row = cur.fetchone()
    assert row is not None
    return bool(row[0]), int(row[1]), row[2], str(row[3])


def tail_gap(conn: psycopg.Connection) -> int:
    """How far the sequence has advanced beyond max(audit_id).

    Nonzero means the newest entries were deleted, or that many inserts rolled
    back. Advisory, never a verdict on its own.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT tail_gap FROM audit_log_verify_chain()")
        row = cur.fetchone()
    assert row is not None
    return int(row[0])


@pytest_asyncio.fixture(autouse=True)
async def _reset_connection_pool() -> AsyncIterator[None]:
    """Close the broker connection pool after every test, everywhere.

    The pool is a process-level global, and pytest-asyncio gives each test its own
    event loop - so a pooled connection created in one test's loop is invalid in the
    next. Resetting it per test is the only reliable answer.

    This lives in the ROOT conftest rather than per-directory because it has to apply
    to *every* suite. It was originally per-directory, and `tests/validator` and
    `tests/golden` use the pool without one: they left a pool bound to a dead loop,
    and the first test of the next suite failed with an error about a closed loop that
    had nothing to do with it. A cleanup that only some directories perform is worse
    than none, because the failure lands somewhere else.
    """
    yield
    await close_pool()
