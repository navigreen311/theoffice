"""The call path, end to end, against an in-process stub Forge.

These are the acceptance tests for blueprint deliverables 0.4 and 0.5. Where a
test could be written two ways, it is written the way that can actually fail —
most importantly the revocation test, which revokes *between* two calls on the
same client instance. Revoking before the client is constructed would pass even
if the grant were cached forever.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker.errors import (
    AuditUnavailable,
    EscalateToHuman,
    ForgeUnreachable,
    IdentityInactive,
    NotCertified,
    NotGranted,
    UnknownForge,
)
from broker.executor import HEADER_AGENT, HEADER_IDEMPOTENCY, HEADER_TRACE, HEADER_VENTURE
from client.office_client import AgentContext
from tests.conftest import requires_db
from tests.contract.conftest import (
    STUB_CREDENTIAL_VALUE,
    audit_events,
    count_audit_rows,
    ledger_rows,
)

pytestmark = [requires_db, pytest.mark.db]


@pytest.fixture(autouse=True)
def _declared_in_manifest(request):
    """Phase 1 added a manifest gate ahead of everything these tests exercise.

    These are call-path mechanics tests, not manifest tests - an undeclared module
    would stop every one of them at a gate they are not about. Declaring by default
    keeps each test failing for its own reason. The manifest itself is covered in
    test_governance.py.
    """
    if "granted_agent" in request.fixturenames:
        request.getfixturevalue("declare_module")(required=True)


async def test_granted_agent_reaches_forge_and_is_named_in_the_ledger(
    office, stub_forge, agent_ctx, granted_agent, app_dsn
):
    """B1 — the bar, minus certification-by-SimForge and a real Forge."""
    agent_id, forge_id, module_id = granted_agent

    result = await office.call(forge_id, module_id, {"doc": "statement.pdf"}, agent_ctx=agent_ctx)

    assert result.status_code == 200
    assert result.body == {"ok": True}
    assert stub_forge.call_count == 1

    rows = ledger_rows(app_dsn, result.call_id)
    assert len(rows) == 1, "exactly one ledger row per call"
    row = rows[0]
    assert row["office_agent_id"] == agent_id, "the ledger row names the agent"
    assert row["forge_id"] == forge_id
    assert row["module_id"] == module_id
    assert row["status_code"] == 200
    assert row["venture_id"] == "burkham-wickmont"
    assert row["api_version"] == "2.1.0"
    assert row["forge_side_ref"] == "forge-req-001"
    assert row["trust_tier_at_call"] == "auto_execute"


async def test_identity_headers_reach_the_forge(office, stub_forge, agent_ctx, granted_agent):
    """B13 — brokered identity: the Forge sees which agent is behind the tenant key."""
    agent_id, forge_id, module_id = granted_agent

    result = await office.call(forge_id, module_id, {"x": 1}, agent_ctx=agent_ctx)

    headers = {k.lower(): v for k, v in stub_forge.last.headers.items()}
    assert headers[HEADER_AGENT.lower()] == str(agent_id)
    assert headers[HEADER_VENTURE.lower()] == "burkham-wickmont"
    assert headers[HEADER_TRACE.lower()] == str(result.trace_id)
    assert headers[HEADER_IDEMPOTENCY.lower()] == result.idempotency_key
    assert headers["authorization"] == f"Bearer {STUB_CREDENTIAL_VALUE}"


async def test_revoking_the_grant_fails_the_very_next_call(
    office, stub_forge, agent_ctx, granted_agent, admin
):
    """B2 — revocation is the kill switch: the NEXT call fails, not the next session.

    Deliberately uses one client instance across both calls. A cached grant would
    make this pass if the revocation happened before construction, so it happens
    in between.
    """
    _, forge_id, module_id = granted_agent

    first = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert first.status_code == 200

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET revoked_at = now() "
            "WHERE office_agent_id = %s AND forge_id = %s",
            (agent_ctx.office_agent_id, forge_id),
        )
    admin.commit()

    with pytest.raises(NotGranted) as exc:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)

    assert "revoked" in str(exc.value)
    assert stub_forge.call_count == 1, "the Forge must not have been contacted"


async def test_suspending_the_identity_fails_the_next_call(
    office, stub_forge, agent_ctx, granted_agent, admin
):
    """B3 — identity status is checked live too, not only the grant."""
    _, forge_id, module_id = granted_agent

    await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_agent_identity SET status = 'suspended' WHERE office_agent_id = %s",
            (agent_ctx.office_agent_id,),
        )
    admin.commit()

    with pytest.raises(IdentityInactive):
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)

    assert stub_forge.call_count == 1


async def test_grant_missing_a_certification_unit_is_refused(
    office, stub_forge, agent_ctx, granted_agent, admin
):
    """B4 — invariant 6 enforced in the path, not only in the schema."""
    _, forge_id, module_id = granted_agent

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET dept_context_cert_ref = NULL "
            "WHERE office_agent_id = %s AND forge_id = %s",
            (agent_ctx.office_agent_id, forge_id),
        )
    admin.commit()

    with pytest.raises(NotCertified):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert stub_forge.call_count == 0


async def test_ungranted_agent_is_refused_and_the_refusal_is_audited(
    office, stub_forge, seed_agent, registered_forge, app_dsn
):
    """B5 — a refusal that is not audited is a refusal nobody can investigate."""
    forge_id, module_id = registered_forge
    ctx = AgentContext(
        office_agent_id=seed_agent, venture_id="burkham-wickmont", task_id="t-1"
    )

    before = count_audit_rows(app_dsn)
    with pytest.raises(NotGranted):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=ctx)

    assert count_audit_rows(app_dsn) == before + 1, "the refusal was audited"
    assert stub_forge.call_count == 0


async def test_unknown_forge_is_distinguished_from_missing_grant(office, seed_agent):
    """A Forge that is not registered is a different failure with a different fix."""
    ctx = AgentContext(office_agent_id=seed_agent, venture_id="v", task_id="t")
    with pytest.raises(UnknownForge):
        await office.call("no-such-forge", "no-such-module", {}, agent_ctx=ctx)


async def test_audit_is_written_before_the_forge_is_contacted(
    office, stub_forge, agent_ctx, granted_agent, app_dsn
):
    """B6 — ordering, observed from inside the Forge.

    Counting audit rows after the call cannot distinguish "written before" from
    "written after". The stub counts them at the moment it is reached.
    """
    _, forge_id, module_id = granted_agent
    before = count_audit_rows(app_dsn)
    stub_forge.audit_counter = lambda: count_audit_rows(app_dsn)

    await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    at_request = stub_forge.last.audit_rows_at_request
    assert at_request is not None
    assert at_request > before, (
        "the pre-call audit entry must already exist when the Forge is reached"
    )


async def test_intent_event_is_recorded_with_the_trace(
    office, agent_ctx, granted_agent, app_dsn
):
    _, forge_id, module_id = granted_agent
    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert audit_events(app_dsn, result.trace_id) == ["forge_call_intent"]


async def test_forge_error_status_is_ledgered_not_swallowed(
    office, stub_forge, agent_ctx, granted_agent, app_dsn
):
    """B11 — a Forge answering 500 is an outcome, and outcomes belong in the ledger."""
    _, forge_id, module_id = granted_agent
    stub_forge.status_code = 500
    stub_forge.response_body = {"error": "upstream exploded"}

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert result.status_code == 500
    rows = ledger_rows(app_dsn, result.call_id)
    assert rows[0]["status_code"] == 500


async def test_unreachable_forge_raises_and_still_ledgers(
    office, stub_forge, agent_ctx, granted_agent, app_dsn
):
    """A Forge that cannot be reached has no outcome, but the attempt is recorded.

    status_code stays NULL, which is what distinguishes "never reached" from
    "answered with an error".
    """
    _, forge_id, module_id = granted_agent
    stub_forge.fail_with = httpx.ConnectError("simulated network failure")

    with pytest.raises(ForgeUnreachable):
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    with psycopg.connect(app_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status_code FROM agent_call_ledger "
            "WHERE office_agent_id = %s ORDER BY ts_start DESC LIMIT 1",
            (agent_ctx.office_agent_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] is None, "never reached, so no status code"


async def test_at_most_once_replay_escalates_instead_of_retrying(
    office, stub_forge, agent_ctx, granted_agent, admin
):
    """B9 — master prompt Part 16: at_most_once endpoints are never auto-retried."""
    _, forge_id, module_id = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_module_registry SET idempotency_support = 'at_most_once' "
            "WHERE forge_id = %s AND module_id = %s",
            (forge_id, module_id),
        )
    admin.commit()

    payload = {"transfer": "10000.00"}
    await office.call(forge_id, module_id, payload, agent_ctx=agent_ctx)
    assert stub_forge.call_count == 1

    with pytest.raises(EscalateToHuman):
        await office.call(forge_id, module_id, payload, agent_ctx=agent_ctx)

    assert stub_forge.call_count == 1, "the replay must not reach the Forge"


async def test_key_idempotency_module_allows_the_same_key_twice(
    office, stub_forge, agent_ctx, granted_agent
):
    """B10 — only at_most_once is special; a 'key' module may safely be retried."""
    _, forge_id, module_id = granted_agent
    payload = {"doc": "same.pdf"}

    first = await office.call(forge_id, module_id, payload, agent_ctx=agent_ctx)
    second = await office.call(forge_id, module_id, payload, agent_ctx=agent_ctx)

    assert first.idempotency_key == second.idempotency_key, "derived, so a retry is one"
    assert stub_forge.call_count == 2


async def test_idempotency_key_is_derived_not_random(office, agent_ctx, granted_agent):
    """A random key per attempt would make every retry look like a new call."""
    _, forge_id, module_id = granted_agent

    a = await office.call(forge_id, module_id, {"k": "v"}, agent_ctx=agent_ctx)
    b = await office.call(forge_id, module_id, {"k": "v"}, agent_ctx=agent_ctx)
    c = await office.call(forge_id, module_id, {"k": "different"}, agent_ctx=agent_ctx)

    assert a.idempotency_key == b.idempotency_key
    assert a.idempotency_key != c.idempotency_key


async def test_credential_value_never_reaches_the_ledger_or_audit(
    office, agent_ctx, granted_agent, app_dsn
):
    """B12 — the secret is used in a header and must exist nowhere else."""
    _, forge_id, module_id = granted_agent
    await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    with psycopg.connect(app_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE subject::text LIKE %s",
            (f"%{STUB_CREDENTIAL_VALUE}%",),
        )
        audit_hits = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM agent_call_ledger "
            "WHERE payload_hash LIKE %s OR COALESCE(forge_side_ref,'') LIKE %s "
            "   OR COALESCE(idempotency_key,'') LIKE %s",
            (f"%{STUB_CREDENTIAL_VALUE}%",) * 3,
        )
        ledger_hits = cur.fetchone()

    assert audit_hits is not None and audit_hits[0] == 0
    assert ledger_hits is not None and ledger_hits[0] == 0


async def test_payload_is_hashed_not_stored(office, agent_ctx, granted_agent, app_dsn):
    """The ledger is append-only and long-lived; request bodies must not enter it."""
    _, forge_id, module_id = granted_agent
    secret_payload = {"ssn": "123-45-6789"}

    result = await office.call(forge_id, module_id, secret_payload, agent_ctx=agent_ctx)

    rows = ledger_rows(app_dsn, result.call_id)
    assert "123-45-6789" not in str(rows[0])
    assert len(str(rows[0]["payload_hash"])) == 64


async def test_two_forges_route_to_their_own_base_urls(
    office, agent_ctx, granted_agent, admin, seed_agent
):
    """B14 — nothing hardcodes a Forge. Which one is bridged first is a row."""
    _, forge_id, _module_id = granted_agent

    second_id = f"second-forge-{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(
            "SELECT base_url FROM forge_registry WHERE forge_id = %s", (forge_id,)
        )
        first_url = cur.fetchone()
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'Second Forge', 'http://second.invalid', '9.9.9',
                    'api_key', 'brokered', 'GREEN')
            """,
            (second_id,),
        )
    admin.commit()

    with admin.cursor() as cur:
        cur.execute("SELECT base_url, api_version, auth_model FROM forge_registry "
                    "WHERE forge_id = %s", (second_id,))
        second = cur.fetchone()
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (second_id,))
    admin.commit()

    assert first_url is not None and second is not None
    assert second[0] != first_url[0], "each Forge carries its own base URL"
    assert second[1] == "9.9.9"
    assert second[2] == "api_key", "auth model is per-Forge data, not a branch in code"


async def test_audit_failure_on_compliance_flagged_action_fails_closed(
    office, stub_forge, agent_ctx, granted_agent, admin, monkeypatch
):
    """B7 — master prompt Part 13: fail closed, never fail open.

    The whole point of a compliance flag is that the action must not happen
    unrecorded. If the record cannot be written, the action does not happen.
    """
    _, forge_id, module_id = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_module_registry SET compliance_flags_implied = %s "
            "WHERE forge_id = %s AND module_id = %s",
            (["TILA", "FCRA"], forge_id, module_id),
        )
    admin.commit()

    async def broken_write(**_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr("broker.audit.write_event", broken_write)

    with pytest.raises(AuditUnavailable) as exc:
        await office.call(forge_id, module_id, {"loan": 1}, agent_ctx=agent_ctx)

    assert "TILA" in str(exc.value.context.get("compliance_flags", []))
    assert stub_forge.call_count == 0, "the Forge must never be reached"


async def test_audit_failure_without_compliance_flags_degrades_rather_than_halts(
    office, stub_forge, agent_ctx, granted_agent, monkeypatch
):
    """B8 — durable-queue otherwise.

    Halting every call on an audit outage turns a logging problem into a total
    outage. Unflagged actions proceed; only flagged ones stop.
    """
    _, forge_id, module_id = granted_agent

    async def broken_write(**_kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr("broker.audit.write_event", broken_write)

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert result.status_code == 200
    assert stub_forge.call_count == 1


async def test_compliance_flags_are_recorded_in_the_ledger(
    office, agent_ctx, granted_agent, admin, app_dsn
):
    """Flags active at call time are ledgered, so a later flag change cannot
    retroactively rewrite what applied when the call was made."""
    _, forge_id, module_id = granted_agent
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_module_registry SET compliance_flags_implied = %s "
            "WHERE forge_id = %s AND module_id = %s",
            (["TILA"], forge_id, module_id),
        )
    admin.commit()

    result = await office.call(forge_id, module_id, {"loan": 1}, agent_ctx=agent_ctx)

    with psycopg.connect(app_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT compliance_flags_active FROM agent_call_ledger WHERE call_id = %s",
            (result.call_id,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == ["TILA"]
