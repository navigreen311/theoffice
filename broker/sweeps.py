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

from broker import certification, incidents, simforge
from broker.db import connection
from broker.simforge import SimForgeError

AUDIT_CHAIN = "audit_chain"
CERTIFICATION_STALENESS = "certification_staleness"
MANIFEST_RECONCILIATION = "manifest_reconciliation"
RESTORE_DRILL = "restore_drill"
VERDICT_INGEST = "verdict_ingest"

# How long a passing result stays meaningful. Beyond this the sweep reports `stale`,
# which is not green. Intervals come from the source: Part 15 makes reconciliation
# monthly, Part 13 makes the restore drill quarterly. The two daily ones are ours -
# a chain that could have been tampered with 29 days ago and nobody looked is not a
# tamper-evident chain in any useful sense.
#
# `verdict_ingest` is daily, and the argument for it runs in the direction people do
# not expect. A missed PASS is loud: the agent stays uncertified, `resolve_grant`
# refuses every call it makes, and somebody asks why within a shift. **A missed REVOKED
# is silent** - SimForge withdrew a certification, The Office never read the verdict,
# and the agent goes on holding production authority it has lost, with the call path
# happily enforcing a `certified` row that is no longer true. That is the same failure
# shape as an unverified hash chain, so it gets the same interval as the two daily ones
# rather than the monthly reconciliation's.
MAX_AGE = {
    AUDIT_CHAIN: timedelta(days=1),
    CERTIFICATION_STALENESS: timedelta(days=1),
    MANIFEST_RECONCILIATION: timedelta(days=31),
    RESTORE_DRILL: timedelta(days=92),
    VERDICT_INGEST: timedelta(days=1),
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
                WHERE c.cert_id = ANY(%s::uuid[])
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


# ------------------------------------------------------------------ verdict ingest


async def _grant_holders(
    conn: AsyncConnection, *, venture_id: str, forge_id: str, module_id: str
) -> list[uuid.UUID]:
    """Which agents a unit-A verdict for this module is about.

    **Read off the receiving side, which is the only place this question has an
    answer.** `curriculum_submission` records a venture, a Forge and a module and names
    no agent; `GateResult` names none either. What The Office submitted was
    `certification_units_requested`, computed from the Pack at Gate 8 and never
    persisted.

    `agent_forge_grant` is where that population lives by the time a verdict comes back.
    Gate 7 blocks unless grants for the venture already exist, inactive
    (`broker/provisioning.py::_gate_7`), and Gate 8 runs after it - so every agent the
    curriculum was submitted for holds a grant row before the run is even opened.

    It is also the exact key the call path uses: `broker/grants.py` joins
    `certification` on `(office_agent_id, forge_id, module_id)`, so a row written for
    this population is a row the enforcement path will find. **Not** `operation_cert_ref`
    - that pointer is written at grant issuance and only tested for NULL there, and
    `_gate_9` reading certification through it rather than through the natural key is a
    second spelling of one question - see B30's closure note in docs/blocking.md.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT office_agent_id FROM agent_forge_grant "
            "WHERE venture_id = %s AND forge_id = %s AND module_id = %s "
            "ORDER BY office_agent_id",
            (venture_id, forge_id, module_id),
        )
        return [r[0] for r in await cur.fetchall()]


async def sweep_verdict_ingest(
    conn: AsyncConnection, *, client: Any | None = None
) -> SweepResult:
    """Poll SimForge for the verdicts it owes, and record them as certifications.

    **This is the writer that turns a SimForge verdict into a certification row**, and
    until it existed `record_result` had exactly one non-test caller - the Phase 0.8
    bootstrap, which issues grants nobody earned. Every `attested_by='simforge'` row in
    this system comes from here.

    A SWEEP, NOT AN INBOUND ROUTE
    =============================

        Ruled, and the reasoning is `overdue_submissions`' own: "a control that depends
        on the failing component to announce its own failure is not a control." An
        inbound route would have SimForge announcing the value that grants an agent
        production authority, on a path that goes silent exactly when SimForge is the
        thing that broke. The Office asks; nothing is accepted unasked.

    WHAT ONE PASS DOES
    ==================

        Every submission with no result yet is EXAMINED - that is the denominator, and
        it counts submissions looked at rather than certifications written, for the same
        reason Gate 8 sends `functions_in_module` as 0 rather than a guess.

        For each: read the verdict from SimForge; resolve it through `VERDICT_TO_STATE`;
        write one `certification` row per agent holding a live grant on that module.
        A run that cannot be read stays open until The Office's own deadline has passed,
        and only then resolves to TIMEOUT - which is `timeout_gate_result`'s existing
        path, unchanged, and reached now by a caller instead of only by a test.

    WHY A TIMEOUT DOES NOT CLOSE THE SUBMISSION
    ===========================================

        `result_received_at` is stamped only on a verdict SimForge has stored -
        `simforge.TERMINAL_VERDICTS`. TIMEOUT and IN_PROGRESS are computed by SimForge
        from the run window and are replaced the moment a result lands: its
        `run_registry` records a late verdict against an already-timed-out run because
        "a result that ARRIVED is better evidence than a deadline that passed."

        If The Office stamped on TIMEOUT it would stop asking while SimForge was still
        answering, and the certification would sit at `in_training` forever because a
        battery finished five minutes late. So a timed-out submission stays in the
        candidate set, the next pass reads the real verdict, and the upsert on
        `(office_agent_id, forge_id, module_id)` replaces the state rather than adding a
        row. **The arriving verdict wins.**

    WHAT IS REFUSED RATHER THAN GUESSED
    ===================================

        A `certified` row must record the instruction hash, the Forge api_version and
        the certified tier. The hash is on the submission; the api_version is recovered
        by `certification.forge_api_version_in_force`, which refuses when the hash
        matches no instruction or is ambiguous at the moment of submission. Nothing here
        supplies a placeholder to get past `record_result`: the refusal is caught,
        counted and reported as a finding, and the submission stays open. A
        certification whose basis is unknown is permanent by accident, which is the
        whole reason that guard exists.

        A unit-B submission is handled by the same code path and will hit the same
        refusal, because a department certification has no module and therefore no
        instruction row to recover an api_version from. That is the honest state today -
        `DeptCert` holds no rows for any department, so no unit-B verdict can be earned
        (docs/blocking.md B32) - and it is a refusal rather than a crash.
    """
    run_id = await _start(conn, VERDICT_INGEST)

    findings: dict[str, Any] = {
        "examined": 0,
        "ingested": 0,
        "rows_written": 0,
        "still_open": 0,
        "timed_out": 0,
        "by_verdict": {},
        # Two different findings, kept apart on purpose. `basis_unrecoverable` is a
        # verdict whose Forge api_version could not be recovered - which is fatal to a
        # PASS and irrelevant to a FAIL, so it is reported and does not decide the
        # sweep's status. `refused` is a write `record_result` actually rejected, and
        # that IS this sweep failing at its one job. Merging them would make every
        # recorded failure look like an outage.
        "basis_unrecoverable": [],
        "refused": [],
        "no_grant_holders": [],
        "unreadable": [],
    }

    # `deadline_hours=0` makes this "every submission still owed an answer", which is
    # the candidate set: a run that answers in five minutes must be ingested in five
    # minutes, not held until the timeout deadline it never reached.
    submissions = await simforge.overdue_submissions(conn, deadline_hours=0)
    findings["examined"] = len(submissions)

    owns_client = client is None
    if submissions and client is None:
        # Built only when there is something to ask about, and imported here rather
        # than at module scope: `broker.sweeps` is imported by the health probes, and
        # the call stack behind `OfficeClient` is a heavier import than a readiness
        # check needs on a system with no verdict outstanding.
        from client.office_client import OfficeClient

        client = simforge.SimForgeClient(OfficeClient())

    try:
        for sub in submissions:
            await _ingest_one(conn, client, sub, findings)
    finally:
        if owns_client and client is not None:
            await client.aclose()

    # A refusal is this sweep failing at its one job: a verdict arrived and no
    # certification could be written for it. Everything else - a run still in flight, a
    # module nobody holds a grant on, a FAIL whose basis was never recoverable - is the
    # sweep working and reporting.
    status = "failed" if findings["refused"] else "passed"
    examined = int(findings["examined"])
    await _finish(
        conn, run_id, status=status, denominator=examined, findings=findings,
    )
    return SweepResult(run_id, VERDICT_INGEST, status, examined, findings)


async def _ingest_one(
    conn: AsyncConnection, client: Any, sub: dict[str, Any], findings: dict[str, Any]
) -> None:
    """One submission. Mutates `findings` rather than returning a verdict about itself."""
    submission_id = sub["submission_id"]
    run_ref = sub.get("simforge_run_ref")
    hours_waiting = float(sub["hours_waiting"])
    result = None

    if run_ref:
        try:
            result = await client.office_gate_result(conn, run_ref=run_ref)
        except SimForgeError as exc:
            findings["unreadable"].append(
                {"submission_id": str(submission_id), "reason": str(exc)}
            )

    if result is None:
        if hours_waiting < simforge.DEFAULT_RUN_DEADLINE_HOURS:
            # Still inside the window. Not an answer and not a timeout; the run is
            # allowed to be running.
            findings["still_open"] += 1
            return
        # The Office's own deadline, held by the party that is waiting. Unchanged path.
        result = simforge.timeout_gate_result(
            sub, rubric_version=simforge.TIMEOUT_RUBRIC_VERSION
        )
        findings["timed_out"] += 1

    by_verdict = findings["by_verdict"]
    by_verdict[result.verdict] = by_verdict.get(result.verdict, 0) + 1

    unit, _rubric_kind = simforge.submission_unit(sub["module_id"])

    # Both units recover it, and they ask different questions. Unit A reconstructs the
    # instruction row in force at `submitted_at` from the module's own content hash.
    # Unit B has no single module: its hash is a composite over the department's member
    # instructions, so the members are read back and their api_versions must AGREE - the
    # set is the basis, and a basis with two answers is not one. This branch was gated on
    # `unit == "A"` until B36 half two; a unit-B result therefore reached `record_result`
    # with no api_version, `certified_records_its_basis` refused it, and the sweep
    # reported `failed` - a guard doing its job over an omission.
    api_version: str | None = None
    try:
        if unit == "A":
            api_version = await certification.forge_api_version_in_force(
                conn,
                forge_id=sub["forge_id"],
                module_id=sub["module_id"],
                content_hash=sub["instruction_content_hash"],
                at=sub["submitted_at"],
            )
        else:
            api_version = await certification.department_api_version(
                conn,
                submission_id=submission_id,
                forge_id=sub["forge_id"],
                at=sub["submitted_at"],
            )
    except certification.CertificationError as exc:
        # Not fatal here, and NOT substituted. A verdict whose basis cannot be
        # recovered may still be recordable - a FAIL records that an agent was
        # tested and did not pass, a claim that cannot go stale and therefore needs
        # no basis - so the write is attempted and `record_result`'s guard decides.
        findings["basis_unrecoverable"].append(
            {"submission_id": str(submission_id), "reason": str(exc)}
        )

    if unit == "A":
        holders = await _grant_holders(
            conn,
            venture_id=sub["venture_id"],
            forge_id=sub["forge_id"],
            module_id=sub["module_id"],
        )
        if not holders:
            # Nothing to certify. Gate 7 requires grants before Gate 8 submits, so this
            # is a provisioning-order finding rather than a verdict problem - and the
            # submission stays open, because the verdict is still owed to somebody.
            findings["no_grant_holders"].append(str(submission_id))
            return
        targets: list[dict[str, Any]] = [
            {"office_agent_id": h, "department": None} for h in holders
        ]
    else:
        targets = [{"office_agent_id": None, "department": sub["department"]}]

    written = 0
    for target in targets:
        try:
            await certification.record_result(
                conn,
                unit=unit,
                forge_id=sub["forge_id"],
                module_id=sub["module_id"],
                office_agent_id=target["office_agent_id"],
                department=target["department"],
                verdict=result.verdict,
                rubric_version=result.rubric_version,
                certified_tier=result.certified_tier,
                instruction_content_hash=sub["instruction_content_hash"],
                forge_api_version=api_version,
                score=result.score,
                threshold=result.threshold,
                scenario_pack_ref=sub["scenario_pack_ref"],
                # Straight from the verdict, never defaulted. A model this sweep chose
                # would be a guess about what answered, and `record_result` refuses an
                # empty one rather than storing a placeholder a later reader takes for
                # a fact - the same rule `functions_in_module` follows when The Office
                # sends 0 instead of inventing a denominator.
                agent_model=result.agent_model,
                attested_by="simforge",
            )
        except certification.CertificationError as exc:
            # The guard did its job. Reported, never worked around.
            findings["refused"].append(
                {
                    "submission_id": str(submission_id),
                    "office_agent_id": str(target["office_agent_id"]),
                    "verdict": result.verdict,
                    "reason": str(exc),
                }
            )
            continue
        written += 1

    findings["rows_written"] += written
    if not written:
        return

    findings["ingested"] += 1
    if result.verdict in simforge.TERMINAL_VERDICTS:
        # Only now. See the module docstring: a stamp on a TIMEOUT would close the
        # submission against a verdict SimForge is still holding open.
        await simforge.mark_result_received(conn, submission_id)


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
            (VERDICT_INGEST, sweep_verdict_ingest),
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
