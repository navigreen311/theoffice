"""Phase 4.1 acceptance — the sweeps that make inert controls real.

Three controls shipped fully tested and completely inert because nothing ran them. The
tests here are about the running, not about the checks themselves — those already have
their own suites. What is asserted is that a sweep records evidence, escalates a real
finding, and above all that **a check which never ran is not reported as healthy**.

That last one is the whole point. An absence of incidents looks identical whether the
chain verified this morning or has not been looked at since March, and a system that
cannot tell those apart has no controls, only code.
"""

from __future__ import annotations

import os
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from broker import sweeps
from broker.db import connection
from tests.conftest import insert_audit, requires_db

pytestmark = [requires_db, pytest.mark.db]

OPERATOR = uuid.uuid4()
VENTURE = "sweep-test-venture"


@pytest.fixture(autouse=True)
def _clean_sweeps(admin: psycopg.Connection):
    """Sweep state is global. A leftover pending disposition fails the next test's
    Gate 15 for a reason that test has nothing to do with."""
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM manifest_disposition")
        cur.execute("DELETE FROM sweep_run")
        cur.execute("DELETE FROM incident")
        cur.execute("ALTER TABLE agent_call_ledger DISABLE TRIGGER ALL")
        cur.execute("DELETE FROM agent_call_ledger")
        cur.execute("ALTER TABLE agent_call_ledger ENABLE TRIGGER ALL")
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
        cur.execute("ALTER SEQUENCE audit_log_audit_id_seq RESTART WITH 1")
    conn.commit()


def ledger_row(conn: psycopg.Connection, *, agent_id, forge_id, module_id, venture=VENTURE):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_call_ledger
              (call_id, trace_id, office_agent_id, venture_id, forge_id, module_id,
               api_version, ts_start, trust_tier_at_call, manifest_match, payload_hash)
            VALUES (%s, %s, %s, %s, %s, %s, '1.0.0', now(), 'auto_execute',
                    'UNDECLARED', 'x')
            """,
            (str(uuid.uuid4()), str(uuid.uuid4()), agent_id, venture, forge_id, module_id),
        )
    conn.commit()


def incidents_of(conn: psycopg.Connection, kind: str) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute("SELECT severity, kind FROM incident WHERE kind = %s", (kind,))
        return [(r[0], r[1]) for r in cur.fetchall()]


# ---------------------------------------------------------------- audit chain

async def test_chain_sweep_passes_and_reports_the_count(admin):
    """W1 — "chain OK" is not a result. "Verified over N entries" is."""
    for _ in range(6):
        insert_audit(admin)

    async with connection() as conn:
        result = await sweeps.sweep_audit_chain(conn)

    assert result.passed
    assert result.denominator == 6
    assert result.findings["checked_count"] == 6
    assert "6" in result.findings["reason"]


async def test_chain_sweep_raises_a_critical_incident_on_tampering(admin):
    """W2 — CRITICAL, not HIGH.

    Until Forges support per-principal identity this ledger is the only per-agent
    record anywhere, so a broken chain means the platform has no audit trail rather
    than a degraded one.
    """
    for _ in range(5):
        insert_audit(admin)
    with admin.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute(
            "UPDATE audit_log SET subject = '{\"k\":\"TAMPERED\"}'::jsonb WHERE audit_id = 3"
        )
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    admin.commit()

    async with connection() as conn:
        result = await sweeps.sweep_audit_chain(conn)

    assert not result.passed
    assert result.findings["first_break_audit_id"] == 3
    assert ("CRITICAL", "audit_chain_broken") in incidents_of(admin, "audit_chain_broken")


async def test_a_tail_gap_is_reported_without_failing_the_sweep(admin):
    """W3 — advisory stays advisory.

    A rolled-back insert produces a tail gap innocently. A sweep that fails on every
    rollback is a sweep people learn to ignore, and an ignored sweep is worse than
    none because it looks like coverage.
    """
    for _ in range(4):
        insert_audit(admin)
    with admin.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log WHERE audit_id = 4")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
    admin.commit()

    async with connection() as conn:
        result = await sweeps.sweep_audit_chain(conn)

    assert result.passed, "a tail gap must not fail the sweep"
    assert result.findings["tail_gap"] == 1
    assert ("MEDIUM", "audit_chain_tail_gap") in incidents_of(admin, "audit_chain_tail_gap")


# ------------------------------------------------------- certification staleness

async def test_staleness_sweep_is_a_noop_on_a_fresh_world(admin):
    """W5 — no false positives. A sweep that finds something every run gets muted."""
    async with connection() as conn:
        result = await sweeps.sweep_certification_staleness(conn)
    assert result.passed
    assert result.findings["newly_stale_count"] == 0


async def test_staleness_sweep_flips_certs_and_escalates_affected_grants(
    admin, certified_forge
):
    """W4 — the Phase 2 gap, closed.

    Phase 2 made staleness a comparison so nobody has to remember to invalidate
    anything. Somebody still had to run the comparison, and nothing did.
    """
    forge_id, module_id, agent_id, cert_id = certified_forge

    with admin.cursor() as cur:
        # A Forge bump at the module's declared sensitivity.
        cur.execute(
            "UPDATE forge_registry SET api_version = '2.0.0' WHERE forge_id = %s",
            (forge_id,),
        )
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id, trust_tier,
               operation_cert_ref, dept_context_cert_ref, granted_by, activated_at)
            VALUES (%s, %s, %s, %s, %s, 'auto_execute', %s, %s, %s, now())
            """,
            (str(uuid.uuid4()), agent_id, forge_id, module_id, VENTURE,
             str(cert_id), str(cert_id), str(OPERATOR)),
        )
    admin.commit()

    async with connection() as conn:
        result = await sweeps.sweep_certification_staleness(conn)

    assert result.findings["newly_stale_count"] >= 1
    assert result.findings["live_grants_affected"] >= 1
    assert ("HIGH", "certification_went_stale") in incidents_of(
        admin, "certification_went_stale"
    )

    with admin.cursor() as cur:
        cur.execute("SELECT state FROM certification WHERE cert_id = %s", (str(cert_id),))
        row = cur.fetchone()
    assert row is not None and row[0] == "stale_forge"


async def test_finding_staleness_is_the_sweep_working_not_failing(admin, certified_forge):
    """A sweep that reports `failed` every time instructions are rewritten would make
    an ordinary authoring action look like an outage."""
    forge_id, _module_id, _agent_id, _cert_id = certified_forge
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_registry SET api_version = '2.0.0' WHERE forge_id = %s",
            (forge_id,),
        )
    admin.commit()

    async with connection() as conn:
        result = await sweeps.sweep_certification_staleness(conn)
    assert result.status == "passed"


# --------------------------------------------------- manifest reconciliation (Gate 15)

async def test_sweep_opens_a_disposition_for_an_undeclared_in_use_module(
    admin, seed_agent, seed_forge
):
    """W6 — runtime already blocks an UNDECLARED call, so anything found here got in
    before the manifest row existed, or the row was removed afterwards."""
    forge_id, module_id = seed_forge
    ledger_row(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)

    async with connection() as conn:
        result = await sweeps.sweep_manifest_reconciliation(conn)

    assert f"{VENTURE}/{forge_id}/{module_id}" in result.findings["undeclared_found"]
    assert ("HIGH", "manifest_sweep_undeclared_in_use") in incidents_of(
        admin, "manifest_sweep_undeclared_in_use"
    )
    with admin.cursor() as cur:
        cur.execute(
            "SELECT disposition, call_count FROM manifest_disposition "
            "WHERE venture_id = %s AND module_id = %s", (VENTURE, module_id)
        )
        row = cur.fetchone()
    assert row == ("pending", 1)


async def test_gate_15_fails_while_a_disposition_is_pending(admin, seed_agent, seed_forge):
    """W7 — Part 15. An undeclared call must not be absorbed by time passing."""
    forge_id, module_id = seed_forge
    ledger_row(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)

    async with connection() as conn:
        first = await sweeps.sweep_manifest_reconciliation(conn)
        # Run again: the finding is not new, and it still blocks.
        second = await sweeps.sweep_manifest_reconciliation(conn)

    assert first.status == "failed"
    assert second.status == "failed", "a pending disposition keeps blocking"
    assert second.findings["pending_dispositions"]


async def test_gate_15_passes_once_dispositioned_and_records_the_reason(
    admin, seed_agent, seed_forge
):
    """W8."""
    forge_id, module_id = seed_forge
    ledger_row(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)

    async with connection() as conn:
        await sweeps.sweep_manifest_reconciliation(conn)
        await sweeps.disposition(
            conn, venture_id=VENTURE, forge_id=forge_id, module_id=module_id,
            resolution="accepted_risk", resolved_by=OPERATOR,
            reason="one-off during migration; module added to the Pack in v1.1",
        )
        after = await sweeps.sweep_manifest_reconciliation(conn)

    assert after.status == "passed"
    with admin.cursor() as cur:
        cur.execute(
            "SELECT disposition, reason, dispositioned_by IS NOT NULL "
            "FROM manifest_disposition WHERE module_id = %s", (module_id,)
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "accepted_risk"
    assert "migration" in row[1]
    assert row[2] is True


async def test_a_disposition_needs_a_reason_and_a_known_resolution(
    admin, seed_agent, seed_forge
):
    """W9 — resolving a finding is an act with an owner, not a status flip."""
    forge_id, module_id = seed_forge
    ledger_row(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)

    async with connection() as conn:
        await sweeps.sweep_manifest_reconciliation(conn)

        with pytest.raises(ValueError, match="reason"):
            await sweeps.disposition(
                conn, venture_id=VENTURE, forge_id=forge_id, module_id=module_id,
                resolution="declared", resolved_by=OPERATOR, reason="   ",
            )
        with pytest.raises(ValueError, match="unknown disposition"):
            await sweeps.disposition(
                conn, venture_id=VENTURE, forge_id=forge_id, module_id=module_id,
                resolution="ignore", resolved_by=OPERATOR, reason="because",
            )


async def test_accepted_risk_exists_so_nobody_has_to_lie(admin, seed_agent, seed_forge):
    """Without it the only way to clear a finding someone has decided to live with is
    to mislabel it `declared` - and a vocabulary that forces a lie produces a register
    nobody trusts."""
    forge_id, module_id = seed_forge
    ledger_row(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)
    async with connection() as conn:
        await sweeps.sweep_manifest_reconciliation(conn)
        await sweeps.disposition(
            conn, venture_id=VENTURE, forge_id=forge_id, module_id=module_id,
            resolution="accepted_risk", resolved_by=OPERATOR,
            reason="known, tolerated, revisit at Q3 review",
        )
        result = await sweeps.sweep_manifest_reconciliation(conn)
    assert result.passed


# ----------------------------------------------------------------------- freshness

async def test_never_run_is_not_healthy(admin):
    """W10 — the whole point.

    An absence of findings from a check that did not run is not evidence, and
    reporting it as healthy is how a broken sweep survives for a quarter.
    """
    async with connection() as conn:
        report = await sweeps.freshness(conn)

    for kind, state in report.items():
        assert state["state"] == "never_run", kind
        assert state["healthy"] is False, kind


async def test_a_sweep_older_than_its_max_age_reports_stale(admin):
    """W11 — a stale pass is not a pass."""
    async with connection() as conn:
        await sweeps.sweep_audit_chain(conn)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE sweep_run SET started_at = %s, completed_at = %s "
            "WHERE sweep_kind = 'audit_chain'",
            (datetime.now(UTC) - timedelta(days=9),) * 2,
        )
    admin.commit()

    async with connection() as conn:
        report = await sweeps.freshness(conn)

    assert report["audit_chain"]["status"] == "passed", "the run itself passed"
    assert report["audit_chain"]["state"] == "stale"
    assert report["audit_chain"]["healthy"] is False, (
        "a passing result that is nine days old is not evidence of anything today"
    )


async def test_a_failing_sweep_reports_failing_not_fresh(admin, seed_agent, seed_forge):
    forge_id, module_id = seed_forge
    ledger_row(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)

    async with connection() as conn:
        await sweeps.sweep_manifest_reconciliation(conn)
        report = await sweeps.freshness(conn)

    assert report["manifest_reconciliation"]["state"] == "failing"
    assert report["manifest_reconciliation"]["healthy"] is False


async def test_a_fresh_pass_is_healthy(admin):
    """The green path has to be reachable, or the health check is just an alarm."""
    async with connection() as conn:
        await sweeps.sweep_audit_chain(conn)
        report = await sweeps.freshness(conn)

    assert report["audit_chain"]["state"] == "fresh"
    assert report["audit_chain"]["healthy"] is True
    assert report["audit_chain"]["age_hours"] < 1


# ---------------------------------------------------------------------- concurrency

async def test_one_sweep_kind_runs_at_a_time(admin):
    """W12 — two concurrent reconciliation sweeps would both open a pending
    disposition for the same module, and a human would resolve one of them."""
    async with connection() as first, sweeps._sweep_lock(
        first, sweeps.AUDIT_CHAIN
    ) as got_first:
        assert got_first is True
        async with connection() as second, sweeps._sweep_lock(
            second, sweeps.AUDIT_CHAIN
        ) as got_second:
            assert got_second is False, "the lock must exclude a second runner"


async def test_run_all_records_a_run_per_kind(admin):
    results = await sweeps.run_all()
    assert set(results) == {
        sweeps.AUDIT_CHAIN,
        sweeps.CERTIFICATION_STALENESS,
        sweeps.MANIFEST_RECONCILIATION,
    }
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM sweep_run WHERE status <> 'running'")
        row = cur.fetchone()
    assert row is not None and row[0] == 3


# -------------------------------------------------------------- restore drill (Gate 13)

@pytest.mark.skipif(
    shutil.which("pg_dump") is None or shutil.which("psql") is None,
    reason="pg_dump/psql not on PATH; a drill that cannot run is not a drill that passed",
)
async def test_restore_drill_restores_and_verifies_the_chain_in_the_copy(admin):
    """W13 — Part 13's "quarterly tested drill", actually performed.

    A drill that mocks the restore tests the mock. This dumps, creates a scratch
    database, restores into it, and asserts the chain verifies **in the copy** - the
    only property that matters, because a backup that restores a broken chain has
    restored nothing worth having.
    """
    for _ in range(4):
        insert_audit(admin)

    admin_dsn = os.environ["OFFICE_ADMIN_DSN"]
    async with connection() as conn:
        result = await sweeps.sweep_restore_drill(conn, admin_dsn=admin_dsn)

    assert result.status == "passed", result.findings
    assert result.findings["chain_ok"] is True
    assert result.findings["chain_entries_restored"] == 4
    assert result.findings["dump_bytes"] > 0

    # The scratch database must be gone, whatever happened.
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_database WHERE datname = %s",
            (result.findings["scratch_database"],),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 0, "the drill must clean up after itself"
