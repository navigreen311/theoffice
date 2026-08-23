"""Fixtures for the call-path contract tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import pytest
import pytest_asyncio

from broker.config import get_settings
from broker.credentials import Credential
from broker.db import close_pool
from client.office_client import AgentContext, OfficeClient
from tests.contract.stub_forge import StubForge

STUB_BASE_URL = "http://stub-forge.invalid"
STUB_CREDENTIAL_REF = "env://STUB_FORGE_TOKEN"
STUB_CREDENTIAL_VALUE = "s3cr3t-tenant-key-do-not-log"


class RecordingResolver:
    """Wraps a resolver so tests can assert the credential value never escapes."""

    def __init__(self) -> None:
        self.resolved: list[str] = []

    async def resolve(self, credential_ref: str) -> Credential:
        self.resolved.append(credential_ref)
        return Credential(credential_ref, STUB_CREDENTIAL_VALUE)


class FailingAudit:
    """Sentinel used to simulate an audit store outage."""


@pytest.fixture(scope="session", autouse=True)
def _configure_broker_env() -> Iterator[None]:
    """Point the broker at the test database before settings are cached."""
    app_dsn = os.environ.get("OFFICE_APP_DSN")
    if app_dsn:
        os.environ["OFFICE_APP_DSN"] = app_dsn
    os.environ.setdefault("STUB_FORGE_TOKEN", STUB_CREDENTIAL_VALUE)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _reset_pool() -> AsyncIterator[None]:
    """Close the pool between tests so a cached connection never spans one."""
    yield
    await close_pool()


@pytest.fixture
def stub_forge() -> StubForge:
    return StubForge()


@pytest_asyncio.fixture
async def http_to_stub(stub_forge: StubForge) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=stub_forge.build_app())
    async with httpx.AsyncClient(transport=transport) as client:
        yield client


@pytest.fixture
def resolver() -> RecordingResolver:
    return RecordingResolver()


@pytest_asyncio.fixture
async def office(
    http_to_stub: httpx.AsyncClient, resolver: RecordingResolver
) -> AsyncIterator[OfficeClient]:
    client = OfficeClient(http=http_to_stub, resolver=resolver)
    yield client
    # The httpx client is owned by its own fixture; do not close it twice.


@pytest.fixture
def registered_forge(admin: psycopg.Connection) -> Iterator[tuple[str, str]]:
    """A Forge, a module, and a tenant credential — all rows, nothing hardcoded."""
    forge_id = f"stub-forge-{uuid.uuid4().hex[:8]}"
    module_id = "parse_bank_statement"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'Stub Forge', %s, '2.1.0', 'bearer', 'brokered', 'GREEN')
            """,
            (forge_id, STUB_BASE_URL),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating,
               compliance_flags_implied)
            VALUES (%s, %s, 'Parse Bank Statement', 'key', TRUE, '{}')
            """,
            (forge_id, module_id),
        )
        cur.execute(
            """
            INSERT INTO forge_tenant_credential
              (forge_id, credential_ref, scope, rotation_due, break_glass_holders)
            VALUES (%s, %s, 'tenant', CURRENT_DATE + 90, %s)
            """,
            (forge_id, STUB_CREDENTIAL_REF, [str(uuid.uuid4()), str(uuid.uuid4())]),
        )
    admin.commit()
    yield forge_id, module_id
    _drop_forge(admin, forge_id)


def _drop_forge(conn: psycopg.Connection, forge_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM agent_forge_grant WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM forge_tenant_credential WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM forge_module_registry WHERE forge_id = %s", (forge_id,))
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    conn.commit()


@pytest.fixture
def granted_agent(
    admin: psycopg.Connection, seed_agent: uuid.UUID, registered_forge: tuple[str, str]
) -> Iterator[tuple[uuid.UUID, str, str]]:
    """An active agent holding a fully certified, un-revoked grant."""
    forge_id, module_id = registered_forge
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id,
               trust_tier, operation_cert_ref, dept_context_cert_ref, granted_by)
            VALUES (%s, %s, %s, %s, 'burkham-wickmont', 'auto_execute',
                    'simforge://unitA/parse_bank_statement/1.0.0',
                    'simforge://unitB/finance/1.0.0', %s)
            """,
            (str(uuid.uuid4()), seed_agent, forge_id, module_id, str(uuid.uuid4())),
        )
    admin.commit()
    yield seed_agent, forge_id, module_id


@pytest.fixture
def agent_ctx(granted_agent: tuple[uuid.UUID, str, str]) -> AgentContext:
    agent_id, _, _ = granted_agent
    return AgentContext(
        office_agent_id=agent_id,
        venture_id="burkham-wickmont",
        task_id=f"task-{uuid.uuid4().hex[:8]}",
    )


def count_audit_rows(dsn: str) -> int:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log")
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def ledger_rows(dsn: str, call_id: uuid.UUID) -> list[dict[str, object]]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT office_agent_id, forge_id, module_id, status_code, "
            "       trust_tier_at_call, idempotency_key, payload_hash, forge_side_ref, "
            "       venture_id, api_version "
            "FROM agent_call_ledger WHERE call_id = %s",
            (call_id,),
        )
        cols = [d.name for d in cur.description or []]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def audit_events(dsn: str, trace_id: uuid.UUID) -> list[str]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT event_type FROM audit_log WHERE trace_id = %s ORDER BY audit_id",
            (trace_id,),
        )
        return [r[0] for r in cur.fetchall()]
