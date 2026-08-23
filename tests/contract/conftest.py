"""Fixtures for the call-path contract tests."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import psycopg
import psycopg.types.json
import pytest
import pytest_asyncio

from broker.config import get_settings
from broker.credentials import Credential
from client.office_client import AgentContext, OfficeClient
from tests.conftest import drop_forge
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
    drop_forge(admin, forge_id)


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


# ---------------------------------------------------------------- Phase 1 fixtures

@pytest.fixture(autouse=True)
def _clean_governance(admin: psycopg.Connection) -> Iterator[None]:
    """Governance tables are shared state; a leftover row silently changes a verdict.

    Truncated before AND after: before, so a previous failure cannot poison this
    test; after, so this test cannot poison the next one.
    """
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        # agent_call_ledger is the budget ladder's only input. A row left by an
        # earlier test is spend this test never made, and it silently changes which
        # rung fires - a test that passes for the wrong reason, or fails for one.
        cur.execute("ALTER TABLE agent_call_ledger DISABLE TRIGGER ALL")
        cur.execute("DELETE FROM agent_call_ledger")
        cur.execute("ALTER TABLE agent_call_ledger ENABLE TRIGGER ALL")
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM revocation")
        cur.execute("DELETE FROM venture_forge_manifest")
        cur.execute("DELETE FROM proposal")
        cur.execute("DELETE FROM rate_limit_bucket")
        cur.execute("DELETE FROM venture_budget")
        cur.execute("ALTER TABLE incident DISABLE TRIGGER ALL")
        cur.execute("DELETE FROM incident")
        cur.execute("ALTER TABLE incident ENABLE TRIGGER ALL")
    conn.commit()


@pytest.fixture
def declare_module(
    admin: psycopg.Connection, granted_agent: tuple[uuid.UUID, str, str],
    agent_ctx: AgentContext,
):
    """Declare the module in the venture manifest. Default is *not* declared.

    Undeclared-by-default is deliberate: a test that forgets to declare gets a
    ManifestViolation rather than a silent pass.
    """
    _, forge_id, module_id = granted_agent

    def _declare(*, required: bool = True, criticality: str = "soft") -> None:
        with admin.cursor() as cur:
            cur.execute(
                """
                INSERT INTO venture_forge_manifest
                  (venture_id, forge_id, module_id, is_required, criticality)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (venture_id, forge_id, module_id)
                DO UPDATE SET is_required = EXCLUDED.is_required
                """,
                (agent_ctx.venture_id, forge_id, module_id, required, criticality),
            )
        admin.commit()

    return _declare


@pytest.fixture
def set_bucket(admin: psycopg.Connection):
    """Pin a token bucket to an exact state, so rate-limit tests are not timing races."""

    def _set(key: str, *, tokens: float, max_tokens: float, rps: float) -> None:
        with admin.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rate_limit_bucket
                  (bucket_key, tokens, max_tokens, refill_per_second, last_refill)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (bucket_key) DO UPDATE
                SET tokens = EXCLUDED.tokens,
                    max_tokens = EXCLUDED.max_tokens,
                    refill_per_second = EXCLUDED.refill_per_second,
                    last_refill = now()
                """,
                (key, tokens, max_tokens, rps),
            )
        admin.commit()

    return _set


@pytest.fixture
def set_budget(admin: psycopg.Connection, agent_ctx: AgentContext):
    def _set(
        *, per_task, per_agent_daily, monthly, soft_pct: int = 80,
        hard_action: str = "pause",
    ) -> None:
        with admin.cursor() as cur:
            cur.execute(
                """
                INSERT INTO venture_budget
                  (venture_id, monthly_usd_cap, soft_cap_pct, hard_cap_action,
                   per_agent_usd_daily_cap, per_task_usd_ceiling)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (venture_id) DO UPDATE
                SET monthly_usd_cap = EXCLUDED.monthly_usd_cap,
                    soft_cap_pct = EXCLUDED.soft_cap_pct,
                    hard_cap_action = EXCLUDED.hard_cap_action,
                    per_agent_usd_daily_cap = EXCLUDED.per_agent_usd_daily_cap,
                    per_task_usd_ceiling = EXCLUDED.per_task_usd_ceiling,
                    hard_cap_reversed_at = NULL
                """,
                (agent_ctx.venture_id, monthly, soft_pct, hard_action,
                 per_agent_daily, per_task),
            )
        admin.commit()

    return _set


@pytest.fixture
def spend(
    admin: psycopg.Connection, granted_agent: tuple[uuid.UUID, str, str],
    agent_ctx: AgentContext,
):
    """Write a historical ledger row carrying cost, so the ladder has spend to read."""
    agent_id, forge_id, module_id = granted_agent

    def _spend(*, task_id: str, usd) -> None:
        with admin.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_call_ledger
                  (call_id, trace_id, office_agent_id, venture_id, forge_id, module_id,
                   api_version, task_id, ts_start, usd_cost, trust_tier_at_call,
                   manifest_match, payload_hash)
                VALUES (%s, %s, %s, %s, %s, %s, '2.1.0', %s, now(), %s,
                        'auto_execute', 'required', 'seed')
                """,
                (str(uuid.uuid4()), str(uuid.uuid4()), agent_id, agent_ctx.venture_id,
                 forge_id, module_id, task_id, usd),
            )
        admin.commit()

    return _spend


@pytest.fixture
def incidents_for(admin: psycopg.Connection):
    def _get(venture_id: str) -> list[tuple[str, str]]:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT severity, kind FROM incident WHERE venture_id = %s "
                "ORDER BY raised_at",
                (venture_id,),
            )
            return [(r[0], r[1]) for r in cur.fetchall()]

    return _get


@pytest.fixture
def audit_events_for(admin: psycopg.Connection):
    def _get(actor_id: uuid.UUID) -> list[str]:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT event_type FROM audit_log WHERE actor_id = %s ORDER BY audit_id",
                (actor_id,),
            )
            return [r[0] for r in cur.fetchall()]

    return _get


# ---------------------------------------------------------------- Phase 2 fixtures

@pytest.fixture(autouse=True)
def _clean_certification(admin: psycopg.Connection) -> Iterator[None]:
    _wipe_certs(admin)
    yield
    _wipe_certs(admin)


def _wipe_certs(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM curriculum_submission")
        cur.execute("DELETE FROM certification")
        cur.execute("DELETE FROM forge_operating_instruction")
    conn.commit()


@pytest.fixture
def certified_agent(
    admin: psycopg.Connection,
    granted_agent: tuple[uuid.UUID, str, str],
    _clean_certification: None,
) -> Iterator[tuple[uuid.UUID, str, str]]:
    # _clean_certification is requested explicitly, not left to autouse ordering.
    # Autouse fixtures order by definition, and this one ran first - so the wipe
    # deleted the certifications it had just created, and every downstream test
    # failed at a gate with no obvious cause.
    """An agent holding live instructions plus both certification units.

    Phase 2 turned the certification gate from a non-null string check into a live
    state check, so `granted_agent` alone no longer reaches a Forge. This fixture is
    what "assignable" now means.
    """
    agent_id, forge_id, module_id = granted_agent

    content = {
        "what_it_does": "Parses a bank statement PDF into structured transactions.",
        "what_it_does_not_do": "Does not judge creditworthiness.",
        "inputs": {"document_url": "signed URL"},
        "correct_sequence": ["upload", "parse", "return"],
        "failure_signatures": {"silent_partial": "200 with a short transactions[]"},
        "retry_vs_escalate": "Retry 5xx twice; escalate any 422.",
        "never_do": ["Never re-submit after a 200"],
        "compliance_coupling": ["TILA"],
    }

    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_operating_instruction
              (forge_id, module_id, instruction_version, forge_api_version,
               version_sensitivity, content, content_hash, authored_by)
            VALUES (%s, %s, '1.0.0', '2.1.0', 'major.minor', %s, '', %s)
            RETURNING content_hash
            """,
            (forge_id, module_id, psycopg.types.json.Jsonb(content), str(uuid.uuid4())),
        )
        row = cur.fetchone()
        assert row is not None
        content_hash = row[0]

        cur.execute("SELECT department FROM office_agent_identity WHERE office_agent_id = %s",
                    (agent_id,))
        dept_row = cur.fetchone()
        assert dept_row is not None
        department = dept_row[0]

        cur.execute(
            """
            INSERT INTO certification
              (cert_id, unit, office_agent_id, forge_id, module_id, state,
               certified_tier, instruction_content_hash, forge_api_version,
               rubric_kind, rubric_version, score, threshold, simforge_verdict)
            VALUES (%s, 'A', %s, %s, %s, 'certified', 'auto_execute', %s, '2.1.0',
                    'operation', '1.4.0', 0.91, 0.80, 'PASS')
            """,
            (str(uuid.uuid4()), agent_id, forge_id, module_id, content_hash),
        )
        cur.execute(
            """
            INSERT INTO certification
              (cert_id, unit, department, forge_id, state, certified_tier,
               instruction_content_hash, forge_api_version, rubric_kind,
               rubric_version, score, threshold, simforge_verdict)
            VALUES (%s, 'B', %s, %s, 'certified', 'auto_execute', %s, '2.1.0',
                    'domain', '3.2.0', 0.88, 0.80, 'PASS')
            """,
            (str(uuid.uuid4()), department, forge_id, content_hash),
        )
    admin.commit()
    yield agent_id, forge_id, module_id


@pytest.fixture(autouse=True)
def _certified_by_default(request):
    """Any test using `granted_agent` also gets both certification units.

    Phase 2 turned the certification gate from a non-null string check into a live
    state check, so a granted agent no longer reaches a Forge on its own. Earlier
    phases' tests are about the call path and the governance gates, not about
    certification - without this they would all stop at a gate they are not testing,
    and each would fail for the wrong reason.

    Tests that ARE about certification request `certified_agent` explicitly and then
    manipulate it. Fixture caching means they get the same instance, not a second one.
    """
    if "granted_agent" in request.fixturenames:
        request.getfixturevalue("certified_agent")


# ---------------------------------------------------------------- Phase 3.3 fixtures

@pytest.fixture(autouse=True)
def _clean_shifts(admin: psycopg.Connection) -> Iterator[None]:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM agent_working_memory")
        cur.execute("DELETE FROM shift_assignment")
    admin.commit()
    yield
    with admin.cursor() as cur:
        cur.execute("DELETE FROM agent_working_memory")
        cur.execute("DELETE FROM shift_assignment")
    admin.commit()


@pytest.fixture
def on_shift(admin: psycopg.Connection, _clean_shifts: None):
    """Put an agent on shift for a venture, from an hour ago to seven hours hence."""

    def _assign(agent_id: uuid.UUID, venture_id: str) -> uuid.UUID:
        shift_id = uuid.uuid4()
        with admin.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignment
                  (shift_id, office_agent_id, venture_id, shift_start, shift_end,
                   assigned_by)
                VALUES (%s, %s, %s, now() - interval '1 hour',
                        now() + interval '7 hours', %s)
                """,
                (str(shift_id), agent_id, venture_id, str(uuid.uuid4())),
            )
        admin.commit()
        return shift_id

    return _assign


@pytest.fixture(autouse=True)
def _on_shift_by_default(request):
    """Any test using `agent_ctx` also gets a matching shift assignment.

    Phase 3.3 made the call path require the call's venture to match the agent's open
    shift. Earlier phases' tests are about the other gates, not about shift boundaries
    - without this they would all stop at a gate they are not testing.

    Tests that ARE about the boundary assign their own shifts explicitly and are
    written to work whatever this fixture did.
    """
    if "agent_ctx" in request.fixturenames and "granted_agent" in request.fixturenames:
        ctx = request.getfixturevalue("agent_ctx")
        request.getfixturevalue("on_shift")(ctx.office_agent_id, ctx.venture_id)
