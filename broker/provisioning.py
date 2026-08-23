"""The provisioning pipeline — Part 11's seventeen gates as a state machine.

A run is a state machine, not a script. Each gate has a blocking condition and the run
stops at the first one that blocks. Gates are neither skippable nor reorderable: Gate 5
issues grants and Gate 2 is the validator, so a run that could jump would issue grants
for a Pack nobody validated.

Three decisions carry the design.

**A human gate waits. It does not pass.** Gates 4 and 10 return `awaiting_human`, which
is neither a pass nor a failure. A pipeline that auto-advances through a human review
gate is a pipeline without human review, and the tell is that it still *reports* having
one. This is the same distinction as `NOT_RUN` everywhere else in this system.

**Gates 9 and 9.5 are BLOCKED, not skipped.** SimForge has no instance and the held-out
partition does not exist. A run reaches Gate 8, submits a curriculum, and stops -
reporting that certification cannot be verified rather than proceeding as if it had been.
That is Gate 0's philosophy applied to certification: no engagement provisions against a
capability that does not exist. Skipping them would produce a venture that reads fully
provisioned and has never been certified for anything.

**Grants are issued inactive.** Gate 5 writes them with `activated_at IS NULL`, which
makes them not assignable, which makes the call path refuse them. Gate 11 activates them
only against a Gate 10 signature bound to the current artifact hash - so editing the Pack
after signing voids the signature by comparison and Gate 11 refuses again. That is what
Part 14's artifact-hash binding is for, and this is the first place it does real work.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from broker import audit, humans, packs
from generators import pipeline as generator_pipeline
from generators import runtime_config as runtime_gen
from generators.artifacts import GeneratedArtifacts
from generators.validator import Verdict, validate, validate_gate_4_5

PASSED = "passed"
BLOCKED = "blocked"
AWAITING_HUMAN = "awaiting_human"

# In order. The list is the order; there is no reordering and no skipping.
GATE_SEQUENCE = (
    "0", "1", "2", "3", "3.5", "4", "4.5", "5", "6", "7", "8", "9", "9.5",
    "10", "11", "12",
)

GATE_TITLES = {
    "0": "Bridge operational for required Forges",
    "1": "Pack authored",
    "2": "Pack Validator",
    "3": "Generators 1-6 run",
    "3.5": "Forge Manifest reconciliation",
    "4": "Human review of artifacts, BOM and appointment gap report",
    "4.5": "Capacity and budget feasibility",
    "5": "Sandbox Forge grants issued",
    "6": "Knowledge bases seeded, instructions indexed",
    "7": "Engagement registered; agents appointed but grants inactive",
    "8": "Curriculum submitted to SimForge",
    "9": "Readiness Gate per role per domain",
    "9.5": "Held-out adversarial set",
    "10": "Named-human sign-off bound to artifact hashes",
    "11": "Production grants activated",
    "12": "Live; tiers active; revocation armed",
}


class ProvisioningError(Exception):
    """The run could not proceed as asked."""


class HeldOutSource(Protocol):
    """Where a held-out adversarial verdict comes from.

    Deliberately one method returning one string. The Office is entitled to learn
    whether an agent passed, never why: a rich enough explanation of a failure
    reconstructs the scenario that produced it, and this is the boundary that exists to
    prevent exactly that.
    """

    async def verdict(self, venture_id: str) -> str | None:
        """`None` when the partition does not exist. Otherwise the verdict verbatim."""
        ...


class PartitionAbsent:
    """The truthful implementation for this deployment: there is no partition."""

    async def verdict(self, venture_id: str) -> str | None:
        return None


@dataclass(frozen=True, slots=True)
class GateOutcome:
    gate: str
    verdict: str
    reason: str
    evidence: dict[str, Any]

    @property
    def advances(self) -> bool:
        return self.verdict == PASSED


@dataclass(frozen=True, slots=True)
class RunState:
    run_id: uuid.UUID
    venture_id: str
    pack_version: str
    status: str
    current_gate: str
    artifacts_hash: str | None


def artifacts_hash(artifacts: GeneratedArtifacts) -> str:
    """Hash of the generated artifacts.

    Taken over the canonical JSON the generators emit, which is deterministic by
    construction - so the same Pack produces the same hash, and a changed Pack does not.
    That is exactly the property a Gate 10 signature needs.
    """
    return hashlib.sha256(artifacts.to_json().encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------ the gates

async def _gate_0(ctx: _Context) -> GateOutcome:
    report = await validate(ctx.pack.pack, ctx.conn)
    result = report.get("V2")
    if result.verdict is Verdict.PASS:
        return GateOutcome("0", PASSED, result.message, {"rule": "V2"})
    return GateOutcome(
        "0", BLOCKED,
        f"{result.message} No engagement provisions against a Forge the bridge does "
        "not reach.",
        {"rule": "V2", "verdict": result.verdict.value},
    )


async def _gate_1(ctx: _Context) -> GateOutcome:
    return GateOutcome(
        "1", PASSED,
        f"Pack {ctx.pack.identity} authored, hash {ctx.pack.content_hash[:12]}…",
        {"pack_version": ctx.pack.pack_version, "content_hash": ctx.pack.content_hash},
    )


async def _gate_2(ctx: _Context) -> GateOutcome:
    report = await validate(ctx.pack.pack, ctx.conn)
    evidence = {
        "failures": [r.rule_id for r in report.failures],
        "warnings": [r.rule_id for r in report.warnings],
        "not_run": [r.rule_id for r in report.not_run],
        "rules_checked": len(report.results),
    }
    if report.failures:
        return GateOutcome(
            "2", BLOCKED,
            f"{len(report.failures)} FAIL rule(s): "
            + "; ".join(f"{r.rule_id}: {r.message}" for r in report.failures[:3]),
            evidence,
        )
    # NOT_RUN is not a pass. V24 is legitimately deferred to Gate 4.5; anything else
    # unrun means this Pack has not been validated.
    unrun = [r.rule_id for r in report.not_run if r.rule_id != "V24"]
    if unrun:
        return GateOutcome(
            "2", BLOCKED,
            f"rule(s) {unrun} did not run. NOT_RUN is not a pass - this Pack has not "
            "been validated.",
            evidence,
        )
    return GateOutcome("2", PASSED, f"{len(report.results)} rules, no failures", evidence)


async def _gate_3(ctx: _Context) -> GateOutcome:
    try:
        artifacts = await generator_pipeline.run_all(ctx.pack.pack, ctx.conn)
    except Exception as exc:
        return GateOutcome("3", BLOCKED, f"generator error: {exc}", {})
    ctx.artifacts = artifacts
    return GateOutcome(
        "3", PASSED,
        f"{len(artifacts.workflow.steps)} workflow step(s), "
        f"{len(artifacts.task_ledger.tasks)} task(s)",
        {
            "artifacts_hash": artifacts_hash(artifacts),
            "positions": len(artifacts.roles.positions),
            "warnings": artifacts.warnings,
        },
    )


async def _gate_3_5(ctx: _Context) -> GateOutcome:
    artifacts = ctx.require_artifacts()
    recon = artifacts.forge_manifest.reconciliation
    evidence = {
        "required_not_declared": recon.required_not_declared,
        "declared_not_required": recon.declared_not_required,
        "hard_dependency_on_gap": recon.hard_dependency_on_gap,
    }
    if recon.required_not_declared:
        return GateOutcome(
            "3.5", BLOCKED,
            f"REQUIRED_NOT_DECLARED: {', '.join(recon.required_not_declared)}. A "
            "workflow step requires a module the Pack never declared.",
            evidence,
        )
    if recon.hard_dependency_on_gap:
        return GateOutcome(
            "3.5", BLOCKED,
            f"hard dependency on a module gap: "
            f"{', '.join(recon.hard_dependency_on_gap)}",
            evidence,
        )
    return GateOutcome("3.5", PASSED, "reconciliation clean", evidence)


async def _gate_4(ctx: _Context) -> GateOutcome:
    """Human review. Waits - it does not pass.

    The evidence is everything the reviewer is being asked to look at, so the decision
    is made against the artifacts rather than against a summary of them.
    """
    artifacts = ctx.require_artifacts()
    if ctx.human_review_recorded:
        return GateOutcome(
            "4", PASSED, "operator recorded a review of the artifacts",
            {"artifacts_hash": artifacts_hash(artifacts)},
        )
    return GateOutcome(
        "4", AWAITING_HUMAN,
        "operator review required: artifacts, bill of materials and appointment gap "
        "report",
        {
            "artifacts_hash": artifacts_hash(artifacts),
            "unfilled_positions": [
                {"position": a.position_title, "unfilled": a.unfilled}
                for a in artifacts.appointment.appointments
                if a.unfilled
            ],
            "capacity": {
                "certified_and_free": artifacts.appointment.capacity.certified_and_free,
                "certified_but_allocated":
                    artifacts.appointment.capacity.certified_but_allocated,
                "produced_not_yet_certified":
                    artifacts.appointment.capacity.produced_not_yet_certified,
            },
            "warnings": artifacts.warnings,
        },
    )


async def _gate_4_5(ctx: _Context) -> GateOutcome:
    artifacts = ctx.require_artifacts()
    report = await validate_gate_4_5(
        ctx.pack.pack, artifacts.task_ledger, artifacts.appointment
    )
    failures = report.failures
    evidence = {r.rule_id: r.message for r in report.results}
    if failures:
        return GateOutcome(
            "4.5", BLOCKED,
            "; ".join(f"{r.rule_id}: {r.message}" for r in failures),
            evidence,
        )
    return GateOutcome("4.5", PASSED, "capacity and budget feasible", evidence)


async def _gate_5(ctx: _Context) -> GateOutcome:
    """Issue grants - inactive.

    `runtime_config.apply` writes them with `activated_at IS NULL`, so `is_assignable`
    is false and the call path refuses them. "Sandbox provisioning" that handed agents
    live authority would be production provisioning with a different label.
    """
    artifacts = ctx.require_artifacts()
    config = artifacts.runtime_config
    if config.blocked_reason:
        return GateOutcome("5", BLOCKED, config.blocked_reason, {})
    try:
        written = await runtime_gen.apply(
            config, ctx.conn, granted_by=str(ctx.actor)
        )
    except ValueError as exc:
        return GateOutcome("5", BLOCKED, str(exc), {})
    return GateOutcome(
        "5", PASSED,
        f"{written['grants']} grant(s) issued INACTIVE, {written['manifest_rows']} "
        "manifest row(s)",
        {**written, "grants_active": False},
    )


async def _gate_6(ctx: _Context) -> GateOutcome:
    """Instructions indexed, knowledge bases seeded.

    Part 6 names five knowledge bases. **One exists.** The gate reports that gap rather
    than passing over it - a venture told its knowledge bases are seeded when four of
    them do not exist has been told something false.
    """
    artifacts = ctx.require_artifacts()
    modules = {m for p in artifacts.roles.positions for m in p.forge_modules_operated}
    async with ctx.conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id FROM forge_operating_instruction WHERE superseded_at IS NULL"
        )
        authored = {r[0] for r in await cur.fetchall()}
    missing = sorted(modules - authored)
    evidence = {
        "modules_operated": sorted(modules),
        "instructions_authored": sorted(modules & authored),
        "missing_instructions": missing,
        "knowledge_bases_built": ["forge_operating_instructions"],
        "knowledge_bases_missing": [
            "business_playbooks", "compliance_library",
            "persona_library", "historical_records",
        ],
    }
    if missing:
        return GateOutcome(
            "6", BLOCKED,
            f"no Forge Operating Instructions for: {', '.join(missing)}. SimForge has "
            "nothing to test against, so no agent can be certified for them.",
            evidence,
        )
    return GateOutcome(
        "6", PASSED,
        f"instructions indexed for {len(modules)} module(s). 1 of 5 knowledge bases "
        "built - the other four are not implemented.",
        evidence,
    )


async def _gate_7(ctx: _Context) -> GateOutcome:
    """Engagement registered, grants inactive. Verified, not assumed."""
    async with ctx.conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT count(*) AS total, "
            "       count(*) FILTER (WHERE activated_at IS NOT NULL) AS active "
            "FROM agent_forge_grant WHERE venture_id = %s AND revoked_at IS NULL",
            (ctx.venture_id,),
        )
        row = await cur.fetchone()
    assert row is not None
    evidence = {"grants": int(row["total"]), "already_active": int(row["active"])}
    if row["active"]:
        return GateOutcome(
            "7", BLOCKED,
            f"{row['active']} grant(s) are already active before Gate 11. Grants are "
            "issued inactive and activated only against a valid sign-off.",
            evidence,
        )
    return GateOutcome(
        "7", PASSED,
        f"{row['total']} grant(s) registered, none active",
        evidence,
    )


async def _gate_8(ctx: _Context) -> GateOutcome:
    """Hand the curriculum to SimForge.

    The Office authors scenario content and records that it handed it over. It records
    refs and counts and no scenario bodies - a table on the Office side holding what was
    sent is a table holding scenario content.
    """
    artifacts = ctx.require_artifacts()
    curriculum = artifacts.curriculum
    total = len(curriculum.domain_scenarios) + len(curriculum.operation_scenarios)
    denominator = max(
        (c.denominator for c in curriculum.coverage), default=1
    )
    async with ctx.conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO curriculum_submission
              (submission_id, venture_id, forge_id, scenario_pack_ref, scenario_count,
               coverage_denominator, instruction_content_hash, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), ctx.venture_id,
                ctx.pack.pack.forge_dependencies.operating_forge,
                f"run:{ctx.run_id}", total, max(denominator, 1),
                ctx.artifacts_hash_value or "", ctx.actor,
            ),
        )
    await ctx.conn.commit()
    return GateOutcome(
        "8", PASSED,
        f"{total} scenario(s) submitted "
        f"({len(curriculum.domain_scenarios)} domain, "
        f"{len(curriculum.operation_scenarios)} operation)",
        {
            "scenario_count": total,
            # Recorded on the Office side. There is no SimForge instance to hand it
            # to, and a record that read as a handover would record a fiction.
            "handed_over_to_simforge": False,
            "coverage": [
                {"dimension": c.dimension, "covered": c.covered,
                 "denominator": c.denominator, "uncovered": c.uncovered}
                for c in curriculum.coverage
            ],
        },
    )


async def _gate_9(ctx: _Context) -> GateOutcome:
    """Readiness Gate per role per domain - read from the certification record.

    Not a live call to SimForge, deliberately. A Readiness Gate verdict reaches The
    Office by being recorded as a certification, and the certification is what the call
    path enforces on every single request. Checking the record rather than the wire
    means this gate asserts the thing that actually gates work - and it keeps asserting
    it when a verdict later goes stale, which a point-in-time call could not.

    An empty deployment blocks here naturally: no SimForge means no recorded verdicts,
    so every grant reports `never_certified` and the gate names the count. That is the
    same refusal the previous hardcoded version gave, arrived at from evidence.

    Seven states, never collapsed. A grant whose Unit A is `never_certified` is reported
    as never certified; one whose Unit A is `stale_instructions` is reported as stale.
    Merging them into "not certified" would hide the difference between an agent nobody
    has trained and an agent whose training no longer describes the module.
    """
    async with ctx.conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT g.grant_id::text AS grant_id, g.module_id, g.forge_id,
                   COALESCE(ca.state, 'never_certified') AS unit_a_state,
                   COALESCE(cb.state, 'never_certified') AS unit_b_state,
                   ca.simforge_verdict AS unit_a_verdict,
                   cb.simforge_verdict AS unit_b_verdict
            FROM agent_forge_grant g
            LEFT JOIN certification ca
              ON ca.unit = 'A' AND ca.cert_id::text = g.operation_cert_ref
            LEFT JOIN certification cb
              ON cb.unit = 'B' AND cb.cert_id::text = g.dept_context_cert_ref
            WHERE g.venture_id = %s AND g.revoked_at IS NULL
            ORDER BY g.grant_id
            """,
            (ctx.venture_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        return GateOutcome(
            "9", BLOCKED,
            "no grants to certify. A venture with nothing granted has passed no "
            "Readiness Gate; it has simply not been asked one.",
            {"grants": 0},
        )

    by_state: dict[str, int] = {}
    unattested: list[str] = []
    failing: list[dict[str, str]] = []
    for row in rows:
        for unit in ("a", "b"):
            state = row[f"unit_{unit}_state"]
            by_state[state] = by_state.get(state, 0) + 1
            if state != "certified":
                failing.append({
                    "grant_id": row["grant_id"], "module_id": row["module_id"],
                    "unit": unit.upper(), "state": state,
                })
            elif row[f"unit_{unit}_verdict"] != "PASS":
                # A certification carrying no SimForge PASS was not produced by a
                # Readiness Gate, whatever its state column says.
                unattested.append(f"{row['grant_id'][:8]}/unit{unit.upper()}")

    evidence = {
        "grants": len(rows),
        "units_checked": len(rows) * 2,
        "states": dict(sorted(by_state.items())),
        "not_certified": failing[:20],
        "not_certified_total": len(failing),
        "certified_without_simforge_verdict": unattested[:20],
    }

    if failing:
        summary = "; ".join(
            f"{count} x {state}" for state, count in sorted(by_state.items())
            if state != "certified"
        )
        return GateOutcome(
            "9", BLOCKED,
            f"{len(failing)} of {len(rows) * 2} certification unit(s) are not certified "
            f"({summary}). Every grant needs Unit A on its module and Unit B on its "
            "department before the Readiness Gate is passed.",
            evidence,
        )
    if unattested:
        return GateOutcome(
            "9", BLOCKED,
            f"{len(unattested)} certification(s) read as certified but carry no SimForge "
            "PASS. A certification nothing external attested is a certification The "
            "Office wrote for itself.",
            evidence,
        )
    return GateOutcome(
        "9", PASSED,
        f"{len(rows) * 2} certification unit(s) certified across {len(rows)} grant(s)",
        evidence,
    )


async def _gate_9_5(ctx: _Context) -> GateOutcome:
    """Held-out adversarial set. The one fact that is not in this database.

    Everything else a gate needs, The Office records. This it cannot: SimForge owns the
    held-out partition outright and The Office has no read path to it by construction
    (J8). What The Office is entitled to learn is a verdict - whether, not why - and
    even that has nowhere to come from until the partition exists.

    So this is a port with one honest implementation today. `PartitionAbsent` reports
    that the partition does not exist, which is the true state of the deployment and
    blocks the run. When SimForge Phase 2 stands the partition up, a real implementation
    replaces it and nothing else here changes.

    A verdict that is not PASS blocks and is named verbatim. `NOT_RUN` in particular is
    not a pass, and TIMEOUT is not a failure - the same rule the rest of the system
    follows about never collapsing states.
    """
    verdict = await ctx.held_out.verdict(ctx.venture_id)
    if verdict is None:
        return GateOutcome(
            "9.5", BLOCKED,
            "The held-out adversarial partition does not exist. SimForge owns it "
            "outright and The Office has no read path to it by construction - the "
            "partition itself still has to be stood up.",
            {"blocked_by": "held_out_partition_not_created"},
        )
    if verdict != "PASS":
        return GateOutcome(
            "9.5", BLOCKED,
            f"held-out adversarial verdict is {verdict}, not PASS. An agent that "
            "passes its rubric and fails the held-out set has learned the rubric.",
            {"verdict": verdict},
        )
    return GateOutcome(
        "9.5", PASSED, "held-out adversarial set: PASS", {"verdict": verdict}
    )


async def _gate_10(ctx: _Context) -> GateOutcome:
    """Named-human sign-off, bound to the artifact hash.

    A signature against a different artifact hash is *void*, not missing. The
    distinction matters: missing means nobody signed, void means somebody signed
    something else - and the second is the case that would otherwise pass unnoticed
    after a Pack edit.
    """
    artifacts = ctx.require_artifacts()
    current = artifacts_hash(artifacts)
    status = await humans.signoff_status(
        ctx.conn, gate="gate_10", venture_id=ctx.venture_id,
        current_artifact_hash=current,
    )
    evidence = {
        "artifacts_hash": current,
        "valid_signatures": len(status.valid),
        "voided_signatures": len(status.voided),
    }
    if status.valid:
        return GateOutcome(
            "10", PASSED,
            f"{len(status.valid)} valid signature(s) bound to the current artifacts",
            evidence,
        )
    if status.voided:
        return GateOutcome(
            "10", AWAITING_HUMAN,
            f"{len(status.voided)} signature(s) are VOID - they were made against "
            "different artifacts. The Pack changed after signing; it must be signed "
            "again.",
            evidence,
        )
    return GateOutcome(
        "10", AWAITING_HUMAN,
        "no sign-off recorded for gate_10 against these artifacts",
        evidence,
    )


async def _gate_11(ctx: _Context) -> GateOutcome:
    """Activate production grants - only against a valid, unvoided signature.

    Gate 10 already checked this, but it is checked again here rather than trusted from
    the previous step. Activation is the moment agents gain production authority, and a
    gate that trusts its predecessor's verdict is a gate that can be reached by any path
    that sets the predecessor's state.
    """
    artifacts = ctx.require_artifacts()
    current = artifacts_hash(artifacts)
    status = await humans.signoff_status(
        ctx.conn, gate="gate_10", venture_id=ctx.venture_id,
        current_artifact_hash=current,
    )
    if not status.valid:
        return GateOutcome(
            "11", BLOCKED,
            "refusing to activate grants without a Gate 10 signature bound to the "
            f"current artifacts ({len(status.voided)} void, 0 valid)",
            {"artifacts_hash": current, "voided": len(status.voided)},
        )

    async with ctx.conn.cursor() as cur:
        await cur.execute(
            "UPDATE agent_forge_grant SET activated_at = now(), activated_by = %s "
            "WHERE venture_id = %s AND revoked_at IS NULL AND activated_at IS NULL",
            (ctx.actor, ctx.venture_id),
        )
        activated = cur.rowcount
    await ctx.conn.commit()

    return GateOutcome(
        "11", PASSED,
        f"{activated} grant(s) activated against signature(s) "
        f"{[s['signoff_id'][:8] for s in status.valid]}",
        {"activated": activated, "artifacts_hash": current},
    )


async def _gate_12(ctx: _Context) -> GateOutcome:
    async with ctx.conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT count(*) FILTER (WHERE is_assignable) AS assignable, count(*) AS total "
            "FROM agent_forge_grant WHERE venture_id = %s AND revoked_at IS NULL",
            (ctx.venture_id,),
        )
        row = await cur.fetchone()
    assert row is not None
    return GateOutcome(
        "12", PASSED,
        f"live: {row['assignable']} of {row['total']} grant(s) assignable; trust tiers "
        "active, revocation armed",
        {"assignable": int(row["assignable"]), "total": int(row["total"])},
    )


GATE_FUNCTIONS: dict[str, Callable[[_Context], Awaitable[GateOutcome]]] = {
    "0": _gate_0, "1": _gate_1, "2": _gate_2, "3": _gate_3, "3.5": _gate_3_5,
    "4": _gate_4, "4.5": _gate_4_5, "5": _gate_5, "6": _gate_6, "7": _gate_7,
    "8": _gate_8, "9": _gate_9, "9.5": _gate_9_5, "10": _gate_10, "11": _gate_11,
    "12": _gate_12,
}


# ------------------------------------------------------------------- the machine

class _Context:
    def __init__(
        self,
        conn: AsyncConnection,
        run_id: uuid.UUID,
        venture_id: str,
        pack: packs.StoredPack,
        actor: uuid.UUID,
        human_review_recorded: bool,
        held_out: HeldOutSource,
    ) -> None:
        self.conn = conn
        self.run_id = run_id
        self.venture_id = venture_id
        self.pack = pack
        self.actor = actor
        self.human_review_recorded = human_review_recorded
        self.held_out = held_out
        self.artifacts: GeneratedArtifacts | None = None
        self.artifacts_hash_value: str | None = None

    def require_artifacts(self) -> GeneratedArtifacts:
        if self.artifacts is None:
            raise ProvisioningError(
                "artifacts are not available; Gate 3 must run in this pass. A run "
                "resumed from a later gate regenerates them rather than trusting a "
                "stored copy, so what is signed is what is provisioned."
            )
        return self.artifacts


async def start_run(
    conn: AsyncConnection, *, venture_id: str, started_by: uuid.UUID
) -> uuid.UUID:
    """Begin a run against the venture's live Pack."""
    pack = await packs.live(conn, venture_id)
    if pack is None:
        raise ProvisioningError(f"no live Pack for {venture_id}")

    run_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO provisioning_run
              (run_id, venture_id, pack_version, pack_hash, status, current_gate,
               started_by)
            VALUES (%s, %s, %s, %s, 'running', '0', %s)
            """,
            (run_id, venture_id, pack.pack_version, pack.content_hash, started_by),
        )
    await conn.commit()

    await audit.write_event(
        event_type="provisioning_run_started",
        actor_type="human", actor_id=started_by, venture_id=venture_id,
        subject={"run_id": str(run_id), "pack": pack.identity,
                 "pack_hash": pack.content_hash},
    )
    return run_id


async def advance(
    conn: AsyncConnection, *, run_id: uuid.UUID, actor: uuid.UUID,
    held_out: HeldOutSource | None = None,
) -> list[GateOutcome]:
    """Run gates from the current one until something stops the run.

    Every pass starts at Gate 0 conceptually - gates before the current one have already
    recorded their verdicts, and re-running them would re-issue grants. What it does not
    do is trust a stored copy of the artifacts: Gate 3 regenerates them, so what a human
    signs at Gate 10 is what Gate 11 activates.
    """
    state = await get_run(conn, run_id)
    if state is None:
        raise ProvisioningError(f"no such run {run_id}")
    if state.status in ("complete", "aborted"):
        raise ProvisioningError(f"run is {state.status}")

    pack = await packs.get_version(conn, state.venture_id, state.pack_version)
    if pack is None:
        raise ProvisioningError("the Pack version this run started from is gone")

    reviewed = await _human_review_recorded(conn, run_id)
    ctx = _Context(
        conn, run_id, state.venture_id, pack, actor, reviewed,
        held_out or PartitionAbsent(),
    )

    outcomes: list[GateOutcome] = []
    start_index = GATE_SEQUENCE.index(state.current_gate)

    for gate in GATE_SEQUENCE[start_index:]:
        # Gate 3 is re-run on every pass because later gates need the artifacts and
        # regenerating is what keeps signature, artifacts and grants describing the
        # same thing.
        if gate != "3" and ctx.artifacts is None and gate in ("3.5", "4", "4.5", "5",
                                                              "6", "8", "10", "11"):
            regenerated = await _gate_3(ctx)
            if not regenerated.advances:
                await _record(
                    conn, run_id, regenerated, venture_id=state.venture_id, actor=actor
                )
                outcomes.append(regenerated)
                await _set_status(conn, run_id, BLOCKED, gate)
                return outcomes

        outcome = await GATE_FUNCTIONS[gate](ctx)
        if ctx.artifacts is not None:
            ctx.artifacts_hash_value = artifacts_hash(ctx.artifacts)
            await _set_artifacts_hash(conn, run_id, ctx.artifacts_hash_value)
        await _record(conn, run_id, outcome, venture_id=state.venture_id, actor=actor)
        outcomes.append(outcome)

        if not outcome.advances:
            await _set_status(
                conn, run_id,
                BLOCKED if outcome.verdict == BLOCKED else AWAITING_HUMAN,
                gate,
            )
            return outcomes

        next_index = GATE_SEQUENCE.index(gate) + 1
        if next_index >= len(GATE_SEQUENCE):
            await _set_status(conn, run_id, "complete", gate, done=True)
            return outcomes
        await _set_status(conn, run_id, "running", GATE_SEQUENCE[next_index])

    return outcomes


async def record_human_review(
    conn: AsyncConnection, *, run_id: uuid.UUID, human: humans.Human, note: str
) -> None:
    """Gate 4. A named human states they reviewed the artifacts.

    Requires a note. "Reviewed" with nothing attached is a checkbox, and Gate 4 exists
    so that somebody looked at the bill of materials and the appointment gap report.
    """
    if not note.strip():
        raise ProvisioningError("a Gate 4 review requires a note saying what was reviewed")

    state = await get_run(conn, run_id)
    if state is None:
        raise ProvisioningError(f"no such run {run_id}")
    humans.authorize(human, required_role="venture_operator", venture_id=state.venture_id)

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO provisioning_gate_result
              (gate_result_id, run_id, gate, verdict, reason, evidence)
            VALUES (%s, %s, '4', 'passed', %s, %s)
            """,
            (uuid.uuid4(), run_id, f"reviewed by {human.display_name}: {note}",
             Jsonb({"human_id": str(human.human_id), "note": note})),
        )
    await conn.commit()

    await audit.write_event(
        event_type="provisioning_gate_4_reviewed",
        actor_type="human", actor_id=human.human_id, venture_id=state.venture_id,
        subject={"run_id": str(run_id), "note": note},
    )


async def abort_run(
    conn: AsyncConnection, *, run_id: uuid.UUID, human: humans.Human, reason: str
) -> None:
    """Abandon a run. A named human, with a reason.

    Needed because a venture may only have one active run: a run parked at Gate 10
    awaiting a signature that is never coming would otherwise block the venture
    permanently, and the workaround would be somebody editing `provisioning_run`
    directly - which is how a gate sequence stops meaning anything.

    Aborting does **not** deactivate grants. Gate 11 may already have activated them and
    an abort is not a revocation; the two are different acts with different authority,
    and collapsing them here would make abandoning a run a way to silently pull a
    venture's authority with no revocation record.
    """
    if not reason.strip():
        raise ProvisioningError("aborting a run requires a reason")

    state = await get_run(conn, run_id)
    if state is None:
        raise ProvisioningError(f"no such run {run_id}")
    if state.status in ("complete", "aborted"):
        raise ProvisioningError(f"run is already {state.status}")
    humans.authorize(human, required_role="venture_operator", venture_id=state.venture_id)

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET status = 'aborted', completed_at = now() "
            "WHERE run_id = %s",
            (run_id,),
        )
    await conn.commit()

    await audit.write_event(
        event_type="provisioning_run_aborted",
        actor_type="human", actor_id=human.human_id, venture_id=state.venture_id,
        subject={"run_id": str(run_id), "at_gate": state.current_gate,
                 "reason": reason},
    )


async def _human_review_recorded(conn: AsyncConnection, run_id: uuid.UUID) -> bool:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM provisioning_gate_result "
            "WHERE run_id = %s AND gate = '4' AND verdict = 'passed' LIMIT 1",
            (run_id,),
        )
        return await cur.fetchone() is not None


async def _record(
    conn: AsyncConnection, run_id: uuid.UUID, outcome: GateOutcome,
    *, venture_id: str, actor: uuid.UUID,
) -> None:
    """Write the gate result, then audit it.

    Both, not either. `provisioning_gate_result` is the run's own record and is what
    the Provisioning Console reads; `audit_log` is hash-chained and append-only and is
    what survives someone with write access to the first one. Gate 11 in particular
    hands agents production authority, which is exactly the class of event that must
    be recorded somewhere the recording process cannot quietly revise.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO provisioning_gate_result
              (gate_result_id, run_id, gate, verdict, reason, evidence)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (uuid.uuid4(), run_id, outcome.gate, outcome.verdict, outcome.reason,
             Jsonb(outcome.evidence)),
        )
    await conn.commit()

    await audit.write_event(
        event_type=f"provisioning_gate_{outcome.verdict}",
        actor_type="human", actor_id=actor, venture_id=venture_id,
        subject={
            "run_id": str(run_id), "gate": outcome.gate,
            "title": GATE_TITLES[outcome.gate], "verdict": outcome.verdict,
            "reason": outcome.reason,
        },
    )


async def _set_artifacts_hash(
    conn: AsyncConnection, run_id: uuid.UUID, value: str
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET artifacts_hash = %s WHERE run_id = %s",
            (value, run_id),
        )
    await conn.commit()


async def _set_status(
    conn: AsyncConnection, run_id: uuid.UUID, status: str, gate: str,
    *, done: bool = False,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET status = %s, current_gate = %s, "
            "completed_at = CASE WHEN %s THEN now() ELSE completed_at END "
            "WHERE run_id = %s",
            (status, gate, done, run_id),
        )
    await conn.commit()


async def get_run(conn: AsyncConnection, run_id: uuid.UUID) -> RunState | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT run_id, venture_id, pack_version, status, current_gate, "
            "       artifacts_hash FROM provisioning_run WHERE run_id = %s",
            (run_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return RunState(**row)


async def gate_results(
    conn: AsyncConnection, run_id: uuid.UUID
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT gate, verdict, reason, evidence, recorded_at "
            "FROM provisioning_gate_result WHERE run_id = %s "
            "ORDER BY recorded_at, gate_result_id",
            (run_id,),
        )
        return [dict(r) for r in await cur.fetchall()]
