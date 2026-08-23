"""Continuous verification — the sweeps that make the controls real.

Three controls shipped fully tested and completely inert, because nothing ran them:
the audit hash chain verifier (Phase 0.1), the certification staleness recompute
(Phase 2), and the manifest reconciliation (Phase 1). A control nobody runs exists in
the repository, not in the system.

Worse than inert: **indistinguishable from healthy.** An absence of incidents looks
identical whether the chain verified this morning or has not been checked since March.

So two rules shape everything here:

  **A stale pass is not a pass.** Every sweep kind declares a `max_age`, and freshness
  reports `never_run | fresh | stale | failing`. `never_run` and `stale` are not green,
  for the same reason the validator's `NOT_RUN` is not a pass: an absence of findings
  from a check that did not run is not evidence.

  **Evidence, not verdicts.** Every run records what it found *and how many things it
  looked at*. "Chain OK" is not a result. "Chain verified over 41,882 entries" is.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from broker import certification, incidents
from broker.db import connection

AUDIT_CHAIN = "audit_chain"
CERTIFICATION_STALENESS = "certification_staleness"
MANIFEST_RECONCILIATION = "manifest_reconciliation"
RESTORE_DRILL = "restore_drill"

# How long a passing result stays meaningful. Beyond this the sweep reports `stale`,
# which is not green. Intervals come from the source: Part 15 makes reconciliation
# monthly, Part 13 makes the restore drill quarterly. The two daily ones are ours -
# a chain that could have been tampered with 29 days ago and nobody looked is not a
# tamper-evident chain in any useful sense.
MAX_AGE = {
    AUDIT_CHAIN: timedelta(days=1),
    CERTIFICATION_STALENESS: timedelta(days=1),
    MANIFEST_RECONCILIATION: timedelta(days=31),
    RESTORE_DRILL: timedelta(days=92),
}


@dataclass(frozen=True, slots=True)
class SweepResult:
    sweep_run_id: uuid.UUID
    kind: str
    status: str
    denominator: int
    findings: dict[str, Any]

    @property
    def passed(self) -> bool:
        return self.status == "passed"


@asynccontextmanager
async def _sweep_lock(conn: AsyncConnection, kind: str) -> AsyncIterator[bool]:
    """Serialise one sweep kind. Yields False if another run holds the lock.

    Two concurrent reconciliation sweeps would both open a pending disposition for the
    same module, and a human would resolve one of them - leaving the other pending
    forever with no way to tell it apart from a real finding.
    """
    async with conn.cursor() as cur:
        await cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"sweep:{kind}",))
        row = await cur.fetchone()
        acquired = bool(row and row[0])
    try:
        yield acquired
    finally:
        if acquired:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))", (f"sweep:{kind}",)
                )


async def _start(conn: AsyncConnection, kind: str) -> uuid.UUID:
    sweep_run_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO sweep_run (sweep_run_id, sweep_kind, status) "
            "VALUES (%s, %s, 'running')",
            (sweep_run_id, kind),
        )
    await conn.commit()
    return sweep_run_id


async def _finish(
    conn: AsyncConnection,
    sweep_run_id: uuid.UUID,
    *,
    status: str,
    denominator: int,
    findings: dict[str, Any],
    incident_id: uuid.UUID | None = None,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE sweep_run SET status = %s, completed_at = now(), "
            "denominator = %s, findings = %s, incident_id = %s WHERE sweep_run_id = %s",
            (status, denominator, Jsonb(findings), incident_id, sweep_run_id),
        )
    await conn.commit()


# ------------------------------------------------------------------- audit chain

async def sweep_audit_chain(conn: AsyncConnection) -> SweepResult:
    """Verify the audit hash chain end to end.

    Phase 0.1 shipped this verifier and said plainly that it "must be run on a schedule
    or it proves nothing". This is the schedule.

    `tail_gap` stays advisory here exactly as it is in the verifier: a rolled-back
    insert produces one innocently, and a sweep that fails on every rollback is a sweep
    people learn to ignore. It is reported, not escalated.
    """
    run_id = await _start(conn, AUDIT_CHAIN)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT ok, checked_count, first_break_audit_id, tail_gap, reason "
            "FROM audit_log_verify_chain()"
        )
        row = await cur.fetchone()
    assert row is not None

    findings = {
        "ok": row["ok"],
        "checked_count": int(row["checked_count"]),
        "first_break_audit_id": row["first_break_audit_id"],
        "tail_gap": int(row["tail_gap"]),
        "reason": row["reason"],
    }

    incident_id = None
    if not row["ok"]:
        # CRITICAL, not HIGH. Until Forges support per-principal identity this ledger
        # is the only per-agent record anywhere, so a broken chain means the platform
        # has no audit trail rather than a degraded one.
        incident_id = await incidents.raise_incident(
            severity="CRITICAL", kind="audit_chain_broken", detail=findings
        )
    elif findings["tail_gap"] > 0:
        incident_id = await incidents.raise_incident(
            severity="MEDIUM", kind="audit_chain_tail_gap", detail=findings
        )

    status = "passed" if row["ok"] else "failed"
    await _finish(
        conn, run_id, status=status,
        denominator=findings["checked_count"], findings=findings, incident_id=incident_id,
    )
    return SweepResult(run_id, AUDIT_CHAIN, status, findings["checked_count"], findings)


# --------------------------------------------------------- certification staleness

async def sweep_certification_staleness(conn: AsyncConnection) -> SweepResult:
    """Recompute staleness across every Forge.

    Phase 2 made staleness a comparison rather than a flag, so nobody has to remember
    to invalidate anything - but somebody still has to run the comparison. Nothing did.

    A newly-stale cert that backs a live grant is a HIGH incident, because an agent
    just lost assignability and its next call will fail. A newly-stale cert backing no
    grant is bookkeeping.
    """
    run_id = await _start(conn, CERTIFICATION_STALENESS)

    async with conn.cursor() as cur:
        await cur.execute("SELECT forge_id FROM forge_registry ORDER BY forge_id")
        forges = [r[0] for r in await cur.fetchall()]
        await cur.execute("SELECT count(*) FROM certification WHERE state = 'certified'")
        row = await cur.fetchone()
        checked = int(row[0]) if row else 0

    newly_stale: list[str] = []
    for forge_id in forges:
        changed = await certification.recompute_staleness(conn, forge_id=forge_id)
        newly_stale.extend(str(c) for c in changed)

    affected_grants = 0
    if newly_stale:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT count(*) FROM agent_forge_grant g
                JOIN certification c
                  ON c.cert_id::text IN (g.operation_cert_ref, g.dept_context_cert_ref)
                WHERE c.cert_id = ANY(%s::uuid[]) AND g.revoked_at IS NULL
                """,
                (newly_stale,),
            )
            row = await cur.fetchone()
            affected_grants = int(row[0]) if row else 0

    findings = {
        "forges_checked": forges,
        "certified_before": checked,
        "newly_stale": newly_stale,
        "newly_stale_count": len(newly_stale),
        "live_grants_affected": affected_grants,
    }

    incident_id = None
    if affected_grants:
        incident_id = await incidents.raise_incident(
            severity="HIGH", kind="certification_went_stale", detail=findings
        )

    # Finding staleness is the sweep working, not the sweep failing. It fails only if
    # it could not run - otherwise every instruction rewrite would look like an outage.
    await _finish(
        conn, run_id, status="passed", denominator=checked,
        findings=findings, incident_id=incident_id,
    )
    return SweepResult(run_id, CERTIFICATION_STALENESS, "passed", checked, findings)


# ------------------------------------------------------- manifest reconciliation

async def sweep_manifest_reconciliation(conn: AsyncConnection) -> SweepResult:
    """Gate 15 — the monthly three-way sweep.

    Declared (a manifest row exists) x Required (`is_required`) x In-Use (it appears in
    `agent_call_ledger`). Runtime already blocks an UNDECLARED call, so anything found
    here got in before the manifest row was written, or the row was removed afterwards.
    Either way it needs a human.

    **Blocks while any UNDECLARED module is undispositioned.** Part 15. An undeclared
    call must not be absorbed by time passing.
    """
    run_id = await _start(conn, MANIFEST_RECONCILIATION)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT l.venture_id, l.forge_id, l.module_id,
                   count(*) AS call_count, max(l.ts_start) AS last_seen
            FROM agent_call_ledger l
            LEFT JOIN venture_forge_manifest m
                   ON m.venture_id = l.venture_id AND m.forge_id = l.forge_id
                  AND m.module_id = l.module_id
            WHERE m.module_id IS NULL
            GROUP BY l.venture_id, l.forge_id, l.module_id
            ORDER BY l.venture_id, l.forge_id, l.module_id
            """
        )
        undeclared = list(await cur.fetchall())

        await cur.execute("SELECT count(DISTINCT (venture_id, forge_id, module_id)) "
                          "FROM agent_call_ledger")
        row = await cur.fetchone()
        in_use_total = int(row["count"]) if row else 0

        await cur.execute(
            """
            SELECT m.venture_id, m.forge_id, m.module_id
            FROM venture_forge_manifest m
            LEFT JOIN agent_call_ledger l
                   ON l.venture_id = m.venture_id AND l.forge_id = m.forge_id
                  AND l.module_id = m.module_id
            WHERE l.module_id IS NULL AND m.is_required
            GROUP BY m.venture_id, m.forge_id, m.module_id
            ORDER BY m.venture_id, m.forge_id, m.module_id
            """
        )
        required_unused = [
            f"{r['venture_id']}/{r['forge_id']}/{r['module_id']}"
            for r in await cur.fetchall()
        ]

    for row in undeclared:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO manifest_disposition
                  (venture_id, forge_id, module_id, call_count, last_seen_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (venture_id, forge_id, module_id) DO UPDATE
                SET call_count = EXCLUDED.call_count, last_seen_at = EXCLUDED.last_seen_at
                """,
                (row["venture_id"], row["forge_id"], row["module_id"],
                 int(row["call_count"]), row["last_seen"]),
            )
    await conn.commit()

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, forge_id, module_id, call_count FROM manifest_disposition "
            "WHERE disposition = 'pending' ORDER BY venture_id, forge_id, module_id"
        )
        pending = [
            f"{r['venture_id']}/{r['forge_id']}/{r['module_id']} ({r['call_count']} calls)"
            for r in await cur.fetchall()
        ]

    findings = {
        "in_use_module_count": in_use_total,
        "undeclared_found": [
            f"{r['venture_id']}/{r['forge_id']}/{r['module_id']}" for r in undeclared
        ],
        "pending_dispositions": pending,
        "required_but_never_used": required_unused,
    }

    incident_id = None
    if undeclared:
        incident_id = await incidents.raise_incident(
            severity="HIGH", kind="manifest_sweep_undeclared_in_use", detail=findings
        )

    status = "failed" if pending else "passed"
    await _finish(
        conn, run_id, status=status, denominator=in_use_total,
        findings=findings, incident_id=incident_id,
    )
    return SweepResult(run_id, MANIFEST_RECONCILIATION, status, in_use_total, findings)


async def disposition(
    conn: AsyncConnection,
    *,
    venture_id: str,
    forge_id: str,
    module_id: str,
    resolution: str,
    resolved_by: uuid.UUID,
    reason: str,
) -> None:
    """Resolve an UNDECLARED finding. Requires a named human and a stated reason.

    `accepted_risk` is a real option on purpose. Without it the only way to clear a
    finding someone has decided to live with is to mislabel it `declared` - and a
    disposition vocabulary that forces a lie produces a register nobody trusts.
    """
    if resolution not in ("declared", "revoked", "accepted_risk"):
        raise ValueError(f"unknown disposition {resolution!r}")
    if not reason.strip():
        raise ValueError("a disposition requires a stated reason")

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE manifest_disposition SET disposition = %s, dispositioned_by = %s, "
            "dispositioned_at = now(), reason = %s "
            "WHERE venture_id = %s AND forge_id = %s AND module_id = %s",
            (resolution, resolved_by, reason, venture_id, forge_id, module_id),
        )
        if cur.rowcount == 0:
            raise LookupError(
                f"no disposition for {venture_id}/{forge_id}/{module_id}"
            )
    await conn.commit()


# ------------------------------------------------------------------ restore drill

async def sweep_restore_drill(conn: AsyncConnection, *, admin_dsn: str) -> SweepResult:
    """Gate 13 — dump, restore into a scratch database, verify the chain in the copy.

    Part 13 requires a "quarterly tested drill". A drill that mocks the restore tests
    the mock. This one actually runs `pg_dump` and `psql`, and then asserts
    `audit_log_verify_chain()` passes **in the restored copy** - which is the only
    property that matters, because the ledger is the sole per-agent record and a backup
    that restores a broken chain has restored nothing worth having.
    """
    run_id = await _start(conn, RESTORE_DRILL)

    scratch = f"theoffice_restore_drill_{uuid.uuid4().hex[:8]}"
    findings: dict[str, Any] = {"scratch_database": scratch}
    status = "failed"
    checked = 0

    try:
        checked = await _run_restore_drill(admin_dsn, scratch, findings)
        status = "passed" if findings.get("chain_ok") else "failed"
    except FileNotFoundError as exc:
        # Never silently passed. A drill that could not run is a drill that did not run.
        status = "error"
        findings["error"] = f"pg_dump/psql not available: {exc}"
    except subprocess.CalledProcessError as exc:
        status = "error"
        findings["error"] = f"{exc.cmd[0]} exited {exc.returncode}"

    incident_id = None
    if status != "passed":
        incident_id = await incidents.raise_incident(
            severity="HIGH", kind="restore_drill_failed", detail=findings
        )

    await _finish(
        conn, run_id, status=status,
        denominator=checked if status != "error" else 0,
        findings=findings, incident_id=incident_id,
    )
    return SweepResult(run_id, RESTORE_DRILL, status, checked, findings)


async def _run_restore_drill(
    admin_dsn: str, scratch: str, findings: dict[str, Any]
) -> int:
    import psycopg

    maintenance = _swap_database(admin_dsn, "postgres")
    scratch_dsn = _swap_database(admin_dsn, scratch)

    def _sh(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(args, check=True, capture_output=True, **kwargs)

    await asyncio.to_thread(
        _sh, "psql", maintenance, "-q", "-c", f'CREATE DATABASE "{scratch}"'
    )
    try:
        dump = await asyncio.to_thread(_sh, "pg_dump", "--no-owner", "--no-acl", admin_dsn)
        findings["dump_bytes"] = len(dump.stdout)

        await asyncio.to_thread(
            _sh, "psql", scratch_dsn, "-q", "-v", "ON_ERROR_STOP=1", "-f", "-",
            input=dump.stdout,
        )

        with psycopg.connect(scratch_dsn) as restored, restored.cursor() as cur:
            cur.execute("SELECT ok, checked_count, reason FROM audit_log_verify_chain()")
            row = cur.fetchone()
            assert row is not None
            findings["chain_ok"] = bool(row[0])
            findings["chain_entries_restored"] = int(row[1])
            findings["chain_reason"] = row[2]
            cur.execute("SELECT count(*) FROM agent_call_ledger")
            ledger_row = cur.fetchone()
            findings["ledger_rows_restored"] = int(ledger_row[0]) if ledger_row else 0
        return int(findings["chain_entries_restored"])
    finally:
        await asyncio.to_thread(
            _sh, "psql", maintenance, "-q", "-c",
            f'DROP DATABASE IF EXISTS "{scratch}" WITH (FORCE)',
        )


def _swap_database(dsn: str, database: str) -> str:
    head, _, _tail = dsn.rpartition("/")
    return f"{head}/{database}"


# ---------------------------------------------------------------------- freshness

async def freshness(conn: AsyncConnection) -> dict[str, dict[str, Any]]:
    """Per sweep kind: `never_run` | `fresh` | `stale` | `failing`.

    `never_run` and `stale` are **not** green. An absence of findings from a check that
    did not run is not evidence, and reporting it as healthy is how a broken sweep
    survives for a quarter.
    """
    out: dict[str, dict[str, Any]] = {}
    async with conn.cursor(row_factory=dict_row) as cur:
        for kind, max_age in MAX_AGE.items():
            await cur.execute(
                "SELECT status, started_at, completed_at, denominator, "
                "       now() - started_at AS age "
                "FROM sweep_run WHERE sweep_kind = %s AND status <> 'running' "
                "ORDER BY started_at DESC LIMIT 1",
                (kind,),
            )
            row = await cur.fetchone()
            if row is None:
                out[kind] = {
                    "state": "never_run",
                    "healthy": False,
                    "max_age_days": max_age.days,
                    "detail": "this control has never been verified",
                }
                continue

            age = row["age"]
            if row["status"] != "passed":
                state, healthy = "failing", False
            elif age > max_age:
                state, healthy = "stale", False
            else:
                state, healthy = "fresh", True

            out[kind] = {
                "state": state,
                "healthy": healthy,
                "status": row["status"],
                "age_hours": round(age.total_seconds() / 3600, 1),
                "max_age_days": max_age.days,
                "denominator": row["denominator"],
                "last_run": row["started_at"].isoformat(),
            }
    return out


# --------------------------------------------------------------------- entry point

async def run_all(*, include_restore_drill: bool = False) -> dict[str, SweepResult]:
    """Run every sweep, serialised per kind. Safe to invoke from cron."""
    results: dict[str, SweepResult] = {}
    async with connection() as conn:
        for kind, fn in (
            (AUDIT_CHAIN, sweep_audit_chain),
            (CERTIFICATION_STALENESS, sweep_certification_staleness),
            (MANIFEST_RECONCILIATION, sweep_manifest_reconciliation),
        ):
            async with _sweep_lock(conn, kind) as acquired:
                if acquired:
                    results[kind] = await fn(conn)

        if include_restore_drill:
            admin_dsn = os.environ.get("OFFICE_ADMIN_DSN")
            if admin_dsn:
                async with _sweep_lock(conn, RESTORE_DRILL) as acquired:
                    if acquired:
                        results[RESTORE_DRILL] = await sweep_restore_drill(
                            conn, admin_dsn=admin_dsn
                        )
    return results
