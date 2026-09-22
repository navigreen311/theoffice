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

from broker import (
    attestation,
    audit,
    build,
    humans,
    instructions,
    knowledge,
    packs,
    revocation,
    simulation,
)
from broker.simforge import (
    CurriculumRejectedError,
    ResponseRefusedError,
    SimForgeClient,
    SimForgeError,
    declared_absent,
    department_basis_hash,
    mint_run_ref,
    operation_scenario_rows,
    scenario_set_hash,
    submission_unit,
    supersede_run_submissions,
)
from generators import pipeline as generator_pipeline
from generators import runtime_config as runtime_gen
from generators import scenario_content
from generators.artifacts import GeneratedArtifacts
from generators.validator import (
    DEFERRED_RULES,
    Verdict,
    validate,
    validate_gate_4_5,
    validate_gate_12,
)

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
    # NOT_RUN is not a pass. The deferred sets are legitimately evaluated later - V24 at
    # Gate 4.5 against appointment output, V38 at Gate 12 against issued grants - and
    # anything else unrun means this Pack has not been validated.
    #
    # Read from `validator.DEFERRED_RULES` rather than spelled here. The literal `"V24"`
    # that used to sit in this line was a second place the deferral was declared, and the
    # first rule added to the other set blocked every run until somebody noticed.
    unrun = [r.rule_id for r in report.not_run if r.rule_id not in DEFERRED_RULES]
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
        # `error` marks this as a fault rather than a policy decision. The gate
        # already knows it caught an exception; without recording that, the console
        # has to guess from the reason string, and "failed" and "stopped" are
        # different outcomes to whoever has to act on them.
        return GateOutcome("3", BLOCKED, f"generator error: {exc}", {"error": True})
    ctx.artifacts = artifacts
    return GateOutcome(
        "3", PASSED,
        f"{len(artifacts.workflow.steps)} workflow step(s), "
        f"{sum(artifacts.approval_projection.projected_daily_approvals.values())} "
        f"projected daily approval(s)",
        {
            "artifacts_hash": artifacts_hash(artifacts),
            "positions": len(artifacts.roles.positions),
            "advisories": [
                {
                    "severity": advisory.severity,
                    "message": advisory.message,
                    "source": advisory.source,
                    "rule_id": advisory.rule_id,
                    "blocks_at": advisory.blocks_at,
                    "blocks": list(advisory.blocks),
                }
                for advisory in artifacts.advisories
            ],
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
            # Separated at the source. A rule that FAILS at Gate 4.5 is a known halt one
            # gate after the one this human is being asked to clear - filing it under
            # "warnings" alongside a genuine advisory is how a reviewer comes to write a
            # review, advance, and discover the run stops anyway.
            "advisories": [
                {
                    "severity": advisory.severity,
                    "message": advisory.message,
                    "source": advisory.source,
                    "rule_id": advisory.rule_id,
                    "blocks_at": advisory.blocks_at,
                    "blocks": list(advisory.blocks),
                }
                for advisory in artifacts.advisories
            ],
            "warnings": artifacts.warnings,
        },
    )


async def _gate_4_5(ctx: _Context) -> GateOutcome:
    artifacts = ctx.require_artifacts()
    report = await validate_gate_4_5(
        ctx.pack.pack, artifacts.approval_projection, artifacts.appointment
    )
    failures = report.failures
    evidence: dict[str, Any] = {r.rule_id: r.message for r in report.results}

    # A rule's basis, where it supplies one, under its own key rather than inside the message.
    # `evidence` is what the Provisioning Console renders and what a Gate 4 reviewer reads, and
    # the point of the separate key is that a shortfall and what it was computed from arrive as
    # two facts. See decisions.md entry 46 and `RuleResult.evidence_basis`.
    for result in report.results:
        if result.evidence_basis:
            evidence[f"{result.rule_id}_basis"] = result.evidence_basis
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
        return GateOutcome("5", BLOCKED, str(exc), {"error": True})
    blocked_modules = written.get("grants_excluded") or []
    tail = (
        f"; {len(blocked_modules)} grant(s) refused by exclusion"
        if blocked_modules else ""
    )
    return GateOutcome(
        "5", PASSED,
        f"{written['grants']} grant(s) issued INACTIVE, {written['manifest_rows']} "
        f"manifest row(s){tail}",
        {**written, "grants_active": False},
    )


async def _gate_6(ctx: _Context) -> GateOutcome:
    """Knowledge bases seeded, instructions indexed - counted, not asserted.

    This gate used to carry a hardcoded list of the four knowledge bases that did not
    exist. A hardcoded list is right exactly once and then rots: the four were built,
    and the gate would have gone on reporting them missing while a venture provisioned
    against a library it was being told was absent.

    So every store is counted against a denominator drawn from what this venture
    actually needs. Two of them block, and only two:

      * a module with no Forge Operating Instructions - SimForge has nothing to test
        against, so no agent can be certified for it and the position cannot be filled;
      * a compliance flag in use with no Compliance Library entry - the agent carries a
        flag that nothing in the system can explain, which means no behavioural
        implication and no escalation trigger reach the agent operating under it.

    Playbooks, personas and history are reported and do not block. A venture can operate
    without an SOP written down; it cannot operate under a compliance flag nobody has
    defined. Saying which is which is the whole content of this gate.
    """
    artifacts = ctx.require_artifacts()
    modules = {m for p in artifacts.roles.positions for m in p.module_ids}
    # EVERY FLAG THE VENTURE IS UNDER, NOT ONLY THE ONES AN AGENT CARRIES.
    #
    # This read `roles.positions` alone until 2026-09-16, and item F is what showed the
    # gap: declaring an obligation human-held takes its flag off every position, and the
    # whole of Gate 6's compliance-library check went quiet with it. Greenstone's TSR
    # entry had no library row, this gate blocked on exactly that, and after the edit it
    # passed - with the library still missing and the obligation still real.
    #
    # **A human-held obligation needs its library entry MORE, not less.** The flag means a
    # person performs the duty, and the library entry is what they read to perform it. An
    # agent at least has an operating instruction; a founder has this.
    #
    # `market.compliance_surface` is where the venture declares what it is under, and it
    # is the same set V22 and V34 reason about. Gate 6 now reads it too, so the three
    # rules and this gate cannot disagree about which flags exist.
    flags = {f for p in artifacts.roles.positions for f in p.effective_compliance_flags}
    flags |= {
        entry.runtime_flag
        for entry in ctx.pack.pack.market.compliance_surface
        if entry.runtime_flag.strip()
    }
    stages = {
        stage
        for line in ctx.pack.pack.engagement_model.service_lines
        for stage in line.lifecycle_stages
    }
    target_personas = set(ctx.pack.pack.market.target_personas)

    async with ctx.conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT module_id FROM forge_operating_instruction WHERE superseded_at IS NULL"
        )
        authored = {r["module_id"] for r in await cur.fetchall()}

        # Scoped to this venture since migration 0039, and this is a TIGHTENING. The
        # query had no venture term while the table had no venture column, so any
        # venture's entry explained any venture's flag: Greenstone's NV consent entry
        # answered for Burkham's `recording_consent_required` and Gate 6 passed on it.
        # That is a gate reading a name rather than a library.
        # RELIED ON, not merely present. Ruled 22 September 2026, entry 165: *"An entry
        # is relied on only when approved and counsel-reviewed. Anything treating a
        # draft as authoritative refuses."*
        #
        # This is the second tightening of this one query. 0039 added the venture term,
        # because a gate that read any venture's entry was reading a name rather than a
        # library. This adds the standing term, for the same kind of reason: a flag is
        # "explained" when an agent carrying it can be told what to do, and a draft
        # nobody approved and no lawyer read does not tell anybody anything.
        #
        # Measured when this was written: every one of the 21 entries is a draft, so
        # this set is empty for every venture and Gate 6 blocks on every declared flag.
        # That is the work reported, not a regression - and it is the reason the rule
        # is worth having, since the gate passed on those drafts yesterday.
        # DEFERRED, NOT VERIFIED. Ruled 22 September 2026, entry 166: in simulation an
        # unreviewed entry is recorded as deliberately deferred and does not fail a
        # gate. The `OR` is in the SQL rather than around it so the two states are one
        # query - a Python branch choosing between two queries is two rules.
        #
        # `explained_deferred` is kept separately because the gate's evidence has to say
        # WHICH flags are covered by a deferral rather than by an entry. A reader who
        # sees only "explained" cannot tell a library from a decision to wait.
        await cur.execute(
            "SELECT DISTINCT runtime_flag, "
            f"       NOT ({knowledge.RELIED_ON_SQL}) AS deferred "
            "  FROM compliance_library_entry "
            " WHERE runtime_flag IS NOT NULL AND venture_id = %(venture_id)s "
            f"   AND ({knowledge.RELIED_ON_SQL} OR {simulation.IN_SIMULATION_SQL})",
            {"venture_id": ctx.venture_id},
        )
        explained_rows = [dict(r) for r in await cur.fetchall()]
        explained_flags = {r["runtime_flag"] for r in explained_rows}
        explained_deferred = sorted(
            {r["runtime_flag"] for r in explained_rows if r["deferred"]}
        )
        deferral = await simulation.current(ctx.conn, ctx.venture_id)

        await cur.execute(
            "SELECT lifecycle_stage FROM business_playbook "
            "WHERE venture_id = %s AND superseded_at IS NULL",
            (ctx.venture_id,),
        )
        playbook_stages = {
            r["lifecycle_stage"] for r in await cur.fetchall() if r["lifecycle_stage"]
        }

        # `persona_body` is deliberately not selected. office_app holds no SELECT on it
        # (Part 6.4), so naming it here would be a privilege error rather than a leak -
        # which is the point of enforcing the boundary with a column grant.
        await cur.execute(
            "SELECT target_persona FROM persona "
            "WHERE venture_id = %s AND superseded_at IS NULL",
            (ctx.venture_id,),
        )
        covered_personas = {r["target_persona"] for r in await cur.fetchall()}

        await cur.execute(
            "SELECT count(*) AS records FROM historical_record WHERE venture_id = %s",
            (ctx.venture_id,),
        )
        history_row = await cur.fetchone()

    missing_instructions = sorted(modules - authored)
    unexplained_flags = sorted(flags - explained_flags)

    def coverage(covered: set[str], needed: set[str]) -> dict[str, Any]:
        return {
            "covered": len(covered & needed),
            "denominator": len(needed),
            "uncovered": sorted(needed - covered),
        }

    playbooks = coverage(playbook_stages, stages)
    personas = coverage(covered_personas, target_personas)
    evidence: dict[str, Any] = {
        "forge_operating_instructions": coverage(authored, modules),
        "compliance_library": {
            **coverage(explained_flags, flags),
            # Entry 166. WHICH of the covered flags are covered by a deferral rather
            # than by an entry somebody approved and a lawyer read. A reader who sees
            # only "covered" cannot tell a library from a decision to wait, and this
            # gate's evidence is what a Gate 4 reviewer reads.
            "deferred_under_simulation": sorted(
                set(explained_deferred) & set(flags)
            ),
            "simulation": deferral.as_evidence() if deferral else None,
        },
        "business_playbooks": playbooks,
        "persona_library": personas,
        "historical_records": {
            "records": int(history_row["records"]) if history_row else 0
        },
        "blocking": ["forge_operating_instructions", "compliance_library"],
    }

    if missing_instructions:
        return GateOutcome(
            "6", BLOCKED,
            f"no Forge Operating Instructions for {len(missing_instructions)} of "
            f"{len(modules)} module(s): {', '.join(missing_instructions)}. SimForge has "
            "nothing to test against, so no agent can be certified for them.",
            evidence,
        )
    if unexplained_flags:
        return GateOutcome(
            "6", BLOCKED,
            f"{len(unexplained_flags)} compliance flag(s) in use with no Compliance "
            f"Library entry: {', '.join(unexplained_flags)}. The agents carrying these "
            "have no behavioural implication and no escalation trigger to act on.",
            evidence,
        )

    advisory = []
    if playbooks["covered"] < playbooks["denominator"]:
        advisory.append(
            f"{playbooks['denominator'] - playbooks['covered']} lifecycle stage(s) have "
            "no playbook"
        )
    if personas["covered"] < personas["denominator"]:
        advisory.append(
            f"{personas['denominator'] - personas['covered']} target persona(s) have no "
            "persona authored"
        )

    deferred_here = sorted(set(explained_deferred) & set(flags))
    deferral_note = ""
    if deferred_here and deferral is not None:
        # NAMED IN THE VERDICT, not only in the evidence. A gate that passes partly on a
        # deferral and says so only in a JSON field has passed quietly, and the whole
        # point of entry 166's wording - *recorded as deliberately deferred* - is that
        # the record reads as a decision somebody took.
        deferral_note = (
            f" {len(deferred_here)} of them DELIBERATELY DEFERRED, not verified: "
            f"{', '.join(deferred_here)} - {ctx.venture_id} is in simulation, declared "
            f"by {deferral.declared_by_name} on {deferral.declared_at.date()}: "
            f"{deferral.reason}"
        )

    return GateOutcome(
        "6", PASSED,
        f"instructions for {len(modules)} module(s), {len(flags)} compliance flag(s) "
        f"explained"
        + (f". Advisory: {'; '.join(advisory)}." if advisory else ".")
        + deferral_note,
        evidence,
    )


async def _gate_7(ctx: _Context) -> GateOutcome:
    """Engagement registered, grants inactive. Verified, not assumed.

    THE GATE ASKS THE REVOCATION TABLE, NOT A COLUMN NOTHING WRITES
    ==============================================================

        This counted `WHERE revoked_at IS NULL`, which reads as "grants still live" and
        was not. **Nothing in the broker ever wrote `agent_forge_grant.revoked_at`** -
        the only writers in the repository were two test fixtures, and the single
        production `UPDATE agent_forge_grant` sets `activated_at`. So the filter removed
        nothing a revocation put there, and the gate counted every grant ever issued,
        forever.

        `burkham-wickmont` is where that landed: two grants, both activated by Phase
        0's bootstrap, which is the record of the first real brokered call. A run that
        cleared Gate 4.5 blocked here on them - one gate past the furthest any run has
        ever reached - and the two candidate fixes were to revoke the record of the
        first call, or to fix the gate. **Ivan's ruling: the gate is reading the wrong
        source.**

        Revocation in this system is a separate table, consulted per call, never
        cached - four scopes, broadest wins, `broker/revocation.py`. That is what
        `client/office_client.py` asks before every call, and it is now what this gate
        asks, through the same predicate rather than a second spelling of it.

    WHAT DID NOT CHANGE
    ===================

        The demand. Gate 7 exists so grants are *issued inactive and activated only
        against a valid sign-off*, and an active grant with no revocation over it still
        blocks the run. Only the set of rows the question is asked of moved. The test
        that matters here is the one asserting a live active grant still BLOCKS:
        without it this is a gate that passes.

    **The `revoked_at IS NULL` term that used to sit in the SQL below is gone.** This
    docstring deferred removing it - *"a wider change than this gate"*, and the column
    was not empty at the time. Both reasons expired: the two hand-written
    `burkham-wickmont` values were cleared, and migration 0036 is that wider change.
    The column no longer exists. B37.
    """
    async with ctx.conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            # RETIRED GRANTS ARE NOT AUTHORITY, AND THIS GATE IS ABOUT AUTHORITY.
            #
            # A Phase 0 grant the ladder has replaced is kept as history and refused at
            # call time; counting it here would block a run on a row that grants nothing.
            # That is what stopped cb3a47f6: three active bootstrap grants, each already
            # superseded in fact by Gate 5's own, with no way to say so.
            #
            # `superseded_at IS NULL` and not `origin <> 'bootstrap'`: the question is
            # whether this grant still confers authority, not who wrote it. A bootstrap
            # grant with no replacement still blocks, which is correct - it is live.
            "SELECT grant_id, activated_at IS NOT NULL AS active "
            "FROM agent_forge_grant "
            "WHERE venture_id = %s AND superseded_at IS NULL",
            (ctx.venture_id,),
        )
        rows = await cur.fetchall()

    covered = await revocation.covered_grants(ctx.conn, venture_id=ctx.venture_id)
    live = [row for row in rows if row["grant_id"] not in covered]
    active = [row for row in live if row["active"]]
    revoked_active = [row for row in rows if row["active"] and row["grant_id"] in covered]

    scopes = sorted({covered[row["grant_id"]].scope for row in revoked_active})
    evidence: dict[str, Any] = {
        "grants": len(live),
        "already_active": len(active),
        # Named, because "0 active" on a venture holding activated grants is a claim
        # that has to say why it is true.
        "revoked": len(rows) - len(live),
        "active_but_revoked": len(revoked_active),
        "revocation_scopes": scopes,
    }
    if active:
        return GateOutcome(
            "7", BLOCKED,
            f"{len(active)} grant(s) are already active before Gate 11. Grants are "
            "issued inactive and activated only against a valid sign-off.",
            evidence,
        )
    covered_note = (
        f"; {len(revoked_active)} activated grant(s) discounted by a live "
        f"{'/'.join(scopes)} revocation"
        if revoked_active else ""
    )
    return GateOutcome(
        "7", PASSED,
        f"{len(live)} grant(s) registered, none active{covered_note}",
        evidence,
    )


async def _gate_8(ctx: _Context) -> GateOutcome:
    """Hand the curriculum to SimForge, one submission per module.

    THE GATE NAMES ITS OWN BUILD, AND REFUSES TO SUBMIT ON A STALE ONE
    ==================================================================

        This gate's output is generated from FILES BESIDE THIS CODE - the Pack, the
        instructions, and `scenarios/*.yaml`. Every other gate reads the database,
        where a stale process and a current one see the same rows. Gate 8 is the one
        that can send a curriculum nobody has approved and be right about every number
        it reports, because it is reporting truthfully about the wrong tree.

        It happened twice in two days, and both took forensics:

            17 Sep 17:00  run c4edc85a, Gate 8 "41 scenario(s) ... across 4 module(s)"
            18 Sep 15:52  run b8ca7dec, Gate 8 "41 scenario(s) ... across 4 module(s)"

        The same sentence, hours after the answer keys those numbers predate were
        approved and merged. The API was serving from a worktree detached at 7ac49b9,
        and nothing in either gate result said so. What found it was noticing that
        `scenario_count` was 7 on every module when the approved keys carry 8, 8, 5,
        10 and 13 - a coincidence of arithmetic, not a control.

        So: `submitting_build` is recorded on every outcome including the refusals, and
        `broker.build.refusal` decides whether anything may be sent. The check runs
        BEFORE the client is built and before the first submission, because a gate that
        refuses after sending four modules has not refused.

    AND THE OTHER END OF THE WIRE: `forge_build` WARNS, AND DELIBERATELY DOES NOT BLOCK
    ====================================================================================

        Ruled 18 September 2026 (entry 131): *"A submitter that vouches for its own
        build and not its counterpart has checked one end of the wire."* So Gate 8 asks
        SimForge's `/api/version` once, before submitting, and records the answer.

        **It warns. Four reasons, and the last is the one that decides it.**

        1.  A stale Forge does not change WHAT IS SENT. The block above exists because
            this gate's output is generated from files beside the submitting code, so a
            stale Office build sends the wrong curriculum - a fact about us, which we
            can fix. A stale Forge changes what is done with a correct submission.

        2.  This gate's settled rule is that it does not block on facts about the
            Forge. It does not block on an outage, and it does not block on a refused
            response, both on the same ground: *"blocking the ladder on a service that
            is allowed to be down would be worse."* CI runs no SimForge at all, so a
            block here would stop every run on every machine that has not got one.

        3.  `differs` CANNOT DECIDE COMPATIBILITY. It answers "has SimForge's checkout
            moved past its process", which is not "will this payload be understood".
            A Forge whose two numbers agree can still be a version this curriculum does
            not fit, and one whose numbers differ can be perfectly able to accept it.
            Blocking on it would stop the ladder on an inference this side cannot make.

        4.  **The right instrument against a stale GRADER already exists and is a
            different one.** Entry 129 put the answer key into the exam's identity and
            entry 128 refused to ingest six verdicts earned under a superseded one. The
            answer to "this verdict may not be trustworthy" is to not trust the
            verdict, not to refuse to set the exam. Refusing here would deny an agent
            an exam over a doubt about the marking.

        **What makes warning load-bearing rather than lazy is the record.** The six
        verdicts of entry 128 were graded by a build sixteen commits old that discarded
        every scenario on arrival, and nothing anywhere said so - it took reading a
        commit SHA out of `openapi.json` by hand, days later. `forge_build` on the gate
        result is what makes that a lookup instead of an investigation, and the warning
        in the sentence is what gives somebody the chance to stop before the battery
        runs.

    ONE SUBMISSION PER MODULE, NOT ONE PER VENTURE
    ==============================================

        `ForgeOperationCurriculum.instruction_set_ref` is singular, and SimForge's
        router reads `module_never_do.get(ref.module_id)` and upserts one instruction
        set from it. A venture-wide submission would bind one module's instruction set
        and silently drop the never-do lists of every other. So this is N submissions
        and N `run_ref`s, and `curriculum_submission.module_id` - a column that has
        existed since 0007 and that nothing populated - now carries which.

    WHAT IS SENT, AND WHAT IS NOT
    =============================

        SimForge's shape wins. It has a validator behind it, and a count is not
        something an agent can be certified against.

        `functions_in_module` and `functions_covered` are sent as 0. **The Office has no
        concept of a function inside a module** - a module is the smallest unit anything
        here names, in the registry, in the grants, in the instructions and in the
        Pack. Sending a guess would put a denominator in a coverage declaration that no
        Office artifact can support, which is the exact failure "report the denominator"
        exists to prevent. Zero is the honest value and it is visible as one.

        The never-do list IS declared, from the instruction's own `never_do` section,
        and it is expected to be refused - see docs/blocking.md B9. Declaring it
        honestly and being refused is a true statement; omitting it to pass would erase
        the distinction SimForge added that field to keep.

    THE REJECTION IS THE ANSWER
    ===========================

        `curriculum.generate` emits one scenario per (position, module) and SimForge
        requires classed scenarios - at minimum `escalation_required`, plus
        `recovery_after_failure` where the rubric carries that dimension. So every
        module is expected to 422, naming the classes it lacks.

        That is recorded rather than worked around. Manufacturing scenario classes to
        satisfy a counter would produce boilerplate that is then GRADED against, and a
        certification earned on it would be evidence of nothing. A 422 naming missing
        classes is a true statement about where the work is.

    AND THEN THE OTHER UNIT, WHICH THIS GATE HAS NEVER PRODUCED
    ===========================================================

        Certification has two units and one submission is one or the other, keyed on
        `module_id` - `submission_unit` is the rule and it is called, never restated.
        One curriculum per module makes every submission this gate has ever written a
        unit A: ten rows with a module, none with a department.

        `generators/appointment.py` requires BOTH. It refuses any candidate whose
        position touches a Forge the candidate's department holds no certified unit-B
        row for, and reports it as `missing_unit_b`. So the unit-A half being perfect
        appoints nobody.

        `_open_department_units` runs after the per-module loop and opens one unit-B run
        per (department, forge) - the same two keys `appointment._unit_b_certs` queries
        on. **It submits no curriculum**, because there is nothing on the receiving side
        to submit one to: SimForge's `ForgeOperationCurriculum.instruction_set_ref`
        requires a `module_id`, and the `unit_type="department_context"` entry its
        `CertificationUnitRequest` accepts is read by nothing in
        `routers/operation.py::submit_curriculum`, which takes `module_id` out of that
        list and ignores every other field on it. A unit B is `run_start` and the
        correlation row, and `docs/decisions.md` entry 28 already ruled why: a unit-B
        run closes on department certification STATES, not on execution of
        Office-submitted content.
    """
    artifacts = ctx.require_artifacts()
    curriculum = artifacts.curriculum
    total = len(curriculum.domain_scenarios) + len(curriculum.operation_scenarios)
    pack_ref = f"run:{ctx.run_id}"

    # WHICH BUILD IS SUBMITTING - RECORDED ALWAYS, AND CHECKED BEFORE ANYTHING IS SENT.
    #
    # Twice in two days a provisioning run reached this gate on code older than the
    # checkout, submitted a superseded curriculum, and reported success. Both took
    # forensics to find, days later, for one reason: **the gate recorded what it sent
    # and never what sent it.** The evidence answered "35 operation scenarios" and had
    # no field that could answer "generated by what".
    #
    # So the identity goes in `detail` whatever the verdict, and the scenario root goes
    # beside it. `default_root()` anchors on the code's own directory, so a process
    # cannot read one checkout's code and another's answer keys - which makes these two
    # fields together the whole of the 17 September finding, on the row itself.
    build_block = ctx.build.as_evidence(
        scenario_root=str(scenario_content.default_root())
    )
    refusal = build.refusal(ctx.build)
    if refusal is not None:
        # NOTHING IS SENT. Not one module, not one department unit, no
        # `curriculum_submission` row - so there is nothing to withdraw and no verdict
        # is owed on content this build should not have produced.
        #
        # BLOCKED rather than PASSED-with-a-note, and that is the difference between
        # this and an outage. A Forge being down is a fact about the world and the
        # ladder is allowed to carry on past it; a submitter that cannot say what it is
        # running is a fact about US, and the run has no business writing an exam
        # somebody will be certified against.
        return GateOutcome(
            "8", BLOCKED,
            f"Refusing to submit: {refusal}",
            {"scenario_count": total, "submitting_build": build_block,
             "submitted": False},
        )

    by_module: dict[str, list[Any]] = {}
    for scenario in curriculum.operation_scenarios:
        if scenario.module_id:
            by_module.setdefault(scenario.module_id, []).append(scenario)

    # A position operates modules across Forges - Greenstone's roles reach cre-forge
    # and voiceforge - so each module's Forge is resolved from the registry rather than
    # assumed to be the venture's operating one. Assuming it looked up voiceforge's
    # instructions under cre-forge, found nothing, and reported two modules as having
    # no instruction when they have one.
    module_forge = await _module_forges(ctx.conn, set(by_module))
    coverage_by_forge = await _module_coverage(ctx.conn, set(module_forge.values()))
    candidates = _certification_candidates(artifacts)

    client = ctx.simforge
    owns_client = client is None
    if client is None:
        # Imported here, not at module scope: `client` imports `broker`, and a broker
        # module importing it back at import time is a cycle waiting for the first
        # person who adds a second edge.
        from client.office_client import OfficeClient

        client = SimForgeClient(OfficeClient())

    submitted: list[dict[str, Any]] = []
    try:
        # WHICH BUILD IS ON THE OTHER END. Ruled 18 September 2026, entry 131: *"The
        # Office asks whether the Forge it submits to is current, as it already asks of
        # itself."*
        #
        # ASKED ONCE, BEFORE THE FIRST SUBMISSION, and recorded whatever it says. A
        # second probe per module would answer the same question five times and could
        # report two different builds for one run, which is a worse record than one
        # answer taken at a known moment.
        #
        # **RECORDED, NOT ENFORCED - see the `forge_build` section of this gate's
        # docstring for why a stale Forge warns and does not block.**
        forge_build = await _forge_build(client, ctx.conn)
        for module_id in sorted(by_module):
            module_forge_id = module_forge.get(module_id)
            if module_forge_id is None:
                # In the curriculum and in no Forge's registry. Not a skip for a missing
                # instruction - a module nothing dispatches, which is V32's finding and
                # not this gate's to restate as an instruction gap.
                submitted.append({
                    "module_id": module_id,
                    "scenario_count": len(by_module[module_id]),
                    "run_ref": None,
                    "skipped": "no Forge registers this module",
                })
                continue
            in_forge, uncovered = coverage_by_forge[module_forge_id]
            outcome = await _submit_one_module(
                ctx, client,
                forge_id=module_forge_id, module_id=module_id,
                scenarios=by_module[module_id],
                candidates=candidates.get(module_id, []),
                modules_in_forge=in_forge,
                modules_uncovered=uncovered,
                pack_ref=pack_ref,
                # READ ONCE, BEFORE THE FIRST SUBMISSION, and carried in rather than
                # re-probed per module. Entry 131's reason for asking once holds twice
                # over here: two modules of one run must not mint refs naming two
                # different rubric versions because the Forge was restarted mid-gate.
                forge_build=forge_build,
            )
            submitted.append(outcome)

        department_units = await _open_department_units(
            ctx, client,
            submitted=submitted,
            positions=artifacts.roles.positions,
            module_forge=module_forge,
            pack_ref=pack_ref,
            forge_build=forge_build,
        )
    finally:
        if owns_client:
            await client.aclose()

    attempted = [o for o in submitted if "skipped" not in o]
    # ACCEPTED MEANS SIMFORGE SAID YES TO THE CURRICULUM, not that a run was opened.
    # The two were one number until 17 September 2026 and they answer different
    # questions: a refused curriculum is scenarios somebody has to write, an accepted
    # curriculum with no run is a module no agent holds a grant for.
    accepted = [o for o in attempted if o.get("curriculum_accepted")]
    handed_over = [o for o in attempted if o["run_ref"]]
    skipped = [o for o in submitted if "skipped" in o]
    units_opened = [u for u in department_units if u.get("run_ref")]
    await ctx.conn.commit()

    detail: dict[str, Any] = {
        "scenario_count": total,
        # First, and on every outcome. See the block at the top of this function.
        "submitting_build": build_block,
        # Both ends of the wire, side by side and named the same way. A reader
        # investigating a verdict months later needs one question answered - "what was
        # running when this exam was set" - and it has two halves.
        "forge_build": forge_build,
        "submitted": True,
        # True only when every module SimForge was asked about answered with a ref. A
        # row being written is not a hand-over, and neither is three of five landing.
        # HANDED OVER MEANS THE CURRICULUM LANDED, not that a run opened. Those were
        # one number until 18 September, when a module with no exam taker started
        # submitting its instruction set anyway - `underwrite_deal` hands over
        # completely and opens nothing, and reporting that as a failed hand-over would
        # say SimForge never got the module it now holds.
        #
        # `accepted` is `error is None`, and a `run_start` that throws sets `error` - so
        # this still goes False when a run that SHOULD have opened did not.
        "handed_over_to_simforge": bool(attempted) and len(accepted) == len(attempted),
        "modules_submitted": len(attempted),
        "modules_accepted": len(accepted),
        "modules_handed_over": len(handed_over),
        "exams_opened": sum(len(o.get("exam_takers", [])) for o in attempted),
        # Kept apart because the responses differ: a refusal is scenarios somebody has
        # to write, an outage is a service to restart - and only the first can block.
        "modules_refused": sorted(
            o["module_id"] for o in attempted if o.get("violations")
        ),
        # THREE OUTCOMES, NOT TWO. A refused response is neither a rejection nor an
        # outage: SimForge accepted the submission and the reply broke the manifest on
        # the way back. Folding it into `unreachable` said the Forge was down when it
        # had just answered.
        "modules_unreachable": sorted(
            o["module_id"] for o in attempted
            if not o.get("curriculum_accepted") and not o.get("violations")
            and not o.get("response_refused")
        ),
        "modules_response_refused": sorted(
            o["module_id"] for o in attempted if o.get("response_refused")
        ),
        # Kept, and kept SEPARATE from the takers. `requires_certification` is who
        # could fill a seat and holds no certification; the takers are who holds the
        # grant. They were one number until 17 September and the difference is the
        # whole reason no exam was ever named: greenstone reported ten candidates on
        # two modules and none on the other two, and not one of the ten held a grant.
        "certification_candidates": {
            m: [c["agent_name"] for c in cs] for m, cs in sorted(candidates.items())
        },
        # Named, never folded into the submitted count. A module with no live
        # instruction was not refused and was not lost - nothing was sent for it, and
        # the fix is to author the instruction rather than to look at SimForge.
        "modules_skipped": [o["module_id"] for o in skipped],
        "submissions": submitted,
        # Kept OUT of `submissions`, which means "one module's curriculum went over".
        # A unit-B entry has no module and carried no curriculum, and folding the two
        # lists together would make `modules_submitted` count something that is not a
        # module submission - the same collapse B30 says hid unit B in the first place.
        "department_units": department_units,
        "department_units_opened": len(units_opened),
        "coverage": [
            {"dimension": c.dimension, "covered": c.covered,
             "denominator": c.denominator, "uncovered": c.uncovered}
            for c in curriculum.coverage
        ],
    }

    echoed = [o for o in attempted if o.get("response_refused")]
    tail = f"; {len(skipped)} module(s) have no live instruction" if skipped else ""
    if echoed:
        # Named in the sentence. A reader who sees only "0 accepted" will restart
        # SimForge, and SimForge is not the problem.
        tail += (
            f"; {len(echoed)} accepted by SimForge and refused by The Office reading "
            "the reply back"
        )
    forge_warning = _forge_build_warning(forge_build)
    if forge_warning:
        # IN THE SENTENCE, not only in the evidence. A verdict graded by a stale Forge
        # is indistinguishable from any other once it is written down - which is
        # exactly what the six verdicts of entry 128 proved - so the moment to say so
        # is the moment the exam is set, where somebody is reading.
        tail += f"; WARNING: {forge_warning}"
    if department_units:
        # Named in the sentence rather than only in the evidence: unit B gates
        # appointment on its own, and a reader who sees only a module count cannot tell
        # a venture that opened department runs from one that opened none.
        tail += (
            f"; {len(units_opened)} of {len(department_units)} department unit(s) opened"
        )
    exams = detail["exams_opened"]
    if not attempted:
        reason = f"{total} scenario(s) generated; no module to submit{tail}"
    elif len(handed_over) == len(attempted):
        reason = (
            f"{total} scenario(s) submitted "
            f"({len(curriculum.domain_scenarios)} domain, "
            f"{len(curriculum.operation_scenarios)} operation) "
            f"across {len(attempted)} module(s); {exams} exam(s) opened{tail}"
        )
    else:
        reason = (
            f"{total} scenario(s) generated; "
            f"{len(accepted)} of {len(attempted)} module(s) accepted by SimForge; "
            f"{exams} exam(s) opened{tail}"
        )

    # ZERO ACCEPTED IS A BLOCK - WHEN SIMFORGE ANSWERED. Ruled 17 September 2026.
    #
    # This gate passed on everything for its whole life, deliberately: a rejection is an
    # answer, the evidence records it, and blocking the ladder on a service that is
    # allowed to be down would be worse. That argument holds for SOME modules refused.
    # It does not hold for all of them. A venture whose every curriculum was refused has
    # no answer key, and the four gates above this one are being run against a
    # certification story that cannot start. Run cb3a47f6 passed this gate on
    # "0 of 5 module(s) accepted by SimForge" and stopped at 9 with twelve
    # certifications nothing external had attested - three gates later, for a reason
    # this gate already knew.
    #
    # **A SERVICE THAT IS DOWN HAS NOT REFUSED ANYTHING.** "SimForge accepts zero
    # modules" presupposes SimForge answered. An unreachable Forge produces the same
    # `accepted == 0` and means something completely different - and CI runs no
    # SimForge at all, so a block that could not tell the two apart would stop every run
    # on every machine that has not got one. `violations` is the tell: it exists only on
    # a 422 the validator produced.
    #
    # `accepted` and not `handed_over`: the block is about SimForge refusing the
    # content. A module accepted with no exam taker never reaches here - it is skipped
    # earlier, as a roster finding.
    refused = [o for o in attempted if o.get("violations")]
    # A refused RESPONSE counts with the outages for the purpose of the block, and for
    # the same reason: SimForge did not refuse the content, so blocking would report
    # scenarios as wrong when they were accepted. It is reported separately because the
    # fix is different - shorten what The Office sends, rather than restart anything.
    unreachable = [
        o for o in attempted
        if not o.get("curriculum_accepted") and not o.get("violations")
    ]
    if attempted and not accepted and refused and not unreachable:
        names = sorted(o["module_id"] for o in refused)
        quoted = " First: " + "; ".join(refused[0]["violations"][:2])
        return GateOutcome(
            "8", BLOCKED,
            f"SimForge accepted none of the {len(attempted)} module(s) submitted "
            f"({', '.join(names)}). Nothing here can be certified: every scenario was "
            f"refused, so no exam exists to sit and Gate 9 has nothing external to "
            f"read.{quoted}",
            detail,
        )

    return GateOutcome("8", PASSED, reason, detail)


async def _forge_build(client: Any, conn: AsyncConnection) -> dict[str, Any]:
    """Ask the Forge which build it is running. Never raises, never blocks the gate.

    Wrapped rather than called directly because `ctx.simforge` is injectable and a
    caller's fake - every one in the suite predates this - has no `build` method. A
    missing method is recorded as "this client could not be asked", which is true, and
    is not the same finding as a Forge that would not answer.
    """
    probe = getattr(client, "build", None)
    if probe is None:
        return {"reachable": False, "reason": "this SimForge client cannot be asked"}
    try:
        answer = await probe(conn)
    except Exception as exc:  # the probe owns its failures; this is belt and braces
        return {"reachable": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    return answer if isinstance(answer, dict) else {
        "reachable": False, "reason": "the client returned no build record"
    }


def _forge_build_warning(forge_build: dict[str, Any]) -> str | None:
    """The sentence a reader needs, or None when there is nothing to say.

    Findings kept apart because the responses differ: a Forge that would not say is a
    route to add or a service to look at, a Forge whose checkout has moved past its
    process is a restart, and a Forge that does not publish the versions it grades
    under is a field for its `/api/version` body.

    **JOINED RATHER THAN RETURNED FIRST-MATCH.** A stale Forge that also publishes
    neither version has two things wrong with it, and reporting one would send somebody
    to restart a service and conclude the gate was then clean.
    """
    findings: list[str] = []
    if not forge_build.get("reachable"):
        # The only early return. Nothing else can be said about a Forge that did not
        # answer, and listing every field it did not send would read as four faults.
        return "the Forge did not say which build it is running"
    if forge_build.get("differs") is True:
        started = str(forge_build.get("started_commit") or "?")[:12]
        checkout = str(forge_build.get("checkout_commit") or "?")[:12]
        findings.append(
            f"the Forge is running {started} and its checkout is at {checkout} - it "
            "is grading on code its own tree has moved past"
        )

    # WHAT HAPPENS WHEN THE TWO VERSIONS CANNOT BE LEARNED. Ruled 21 September 2026,
    # entry 143, and answered by entry 131's reasoning rather than beside it.
    #
    # **It warns; it does not block.** A Forge that does not publish a field is a fact
    # about the counterpart, and this gate's settled rule is that it does not block on
    # those - it blocks only on facts about us, which is why a build The Office cannot
    # vouch for refuses in the same function. The same ruling's second half says the
    # same thing about the live-run case: the finding tells the operator, and the
    # authored act is the operator's.
    #
    # The consequence is real and is stated rather than hidden: the ref omits the
    # segment, so two exams set under different rubrics mint the same ref and
    # `open_run` returns the first - which is precisely `assign_contract`'s defect,
    # still open until SimForge declares the fields.
    missing = [
        name for name, key in (
            ("protocol", "response_protocol_version"),
            ("rubric", "operation_rubric_version"),
        )
        if not forge_build.get(key)
    ]
    if missing:
        findings.append(
            f"the Forge does not publish its {' or its '.join(missing)} version, so "
            "the exam's identity cannot name what it is graded under and a rubric "
            "change will land on the run already open (entry 143)"
        )
    return "; ".join(findings) or None


async def _exam_takers(
    conn: AsyncConnection, *, venture_id: str, forge_id: str, module_id: str
) -> list[dict[str, Any]]:
    """Who takes this module's exam: the holders of a live grant for it.

    RULED 17 SEPTEMBER 2026, AND MEASURED BEFORE IT WAS BUILT
    =========================================================

        The gate used to name an agent only when `_certification_candidates` returned
        exactly one, and that never happened. Measured on greenstone: ten candidates
        for `assign_contract` and `buyer_match`, **none** for `comp_analysis` and
        `property_lookup`. So `agent_id` was NULL on every run ever opened and SimForge
        skipped all of them - `battery.py` requires `run.agentId`.

        It was also the wrong population. `_certification_candidates` reads
        `requires_certification`, whose own docstring says it deliberately excludes the
        appointed agent: it is the pool of people who could fill a seat and do not hold
        the certification yet. None of greenstone's ten holds a grant for the module.

    THE SAME POPULATION THE VERDICT WILL BE WRITTEN FOR
    ===================================================

        `sweeps._grant_holders` resolves a returning verdict against `agent_forge_grant`
        and `grants.py` joins `certification` on `(office_agent_id, forge_id,
        module_id)`. Gate 9 reads certification through grants. If the exam named a
        population the verdict could not be written for, the ladder would be testing one
        set of agents and certifying another.

        So this asks the question in the same table, with the same key - and excludes
        retired and revoked grants, because neither confers the authority the exam is
        about.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT g.grant_id, g.office_agent_id, i.agent_name, "
            "       i.village_agent_ref "
            "FROM agent_forge_grant g "
            "  JOIN office_agent_identity i ON i.office_agent_id = g.office_agent_id "
            " WHERE g.venture_id = %s AND g.forge_id = %s AND g.module_id = %s "
            "   AND g.superseded_at IS NULL "
            " ORDER BY i.agent_name, g.office_agent_id",
            (venture_id, forge_id, module_id),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    covered = await revocation.covered_grants(conn, venture_id=venture_id)
    seen: set[Any] = set()
    takers: list[dict[str, Any]] = []
    for row in rows:
        if row["grant_id"] in covered or row["office_agent_id"] in seen:
            continue
        seen.add(row["office_agent_id"])
        takers.append({
            "office_agent_id": row["office_agent_id"],
            "agent_name": row["agent_name"],
            "village_agent_ref": row["village_agent_ref"],
        })
    return takers


async def _submit_one_module(
    ctx: _Context, client: Any, *, forge_id: str, module_id: str,
    scenarios: list[Any], candidates: list[dict[str, str]],
    modules_in_forge: int, modules_uncovered: list[str], pack_ref: str,
    forge_build: dict[str, Any],
) -> dict[str, Any]:
    """One module's curriculum, its outcome, and the row that records both."""
    instruction = await instructions.live(ctx.conn, forge_id=forge_id, module_id=module_id)

    run_ref: str | None = None
    error: str | None = None
    response_refused = False
    violations: list[str] | None = None
    module_level: str | None = None
    gate_9_5_flag: Any = None
    already_open: bool | None = None

    if instruction is None:
        # Not an error and NOT A SUBMISSION. SimForge binds a certification to an
        # instruction content hash; there is nothing to bind to and nothing to teach.
        #
        # No `curriculum_submission` row either. That table means "something was handed
        # over", and a row for a module nothing was sent for is the same lie as a true
        # `handed_over_to_simforge` - it would sit in the sweep's queue for a verdict
        # that can never arrive because no run was ever asked for.
        return {
            "module_id": module_id,
            "scenario_count": len(scenarios),
            "run_ref": None,
            "skipped": "no live operating instruction for this module",
        }

    # WHO TAKES THIS EXAM. Ruled 17 September 2026: every submission names the agent.
    # One run per taker, because SimForge's battery scores `run.agentId` - one agent -
    # so a module two agents hold is two exams and not one exam about two people.
    takers = await _exam_takers(
        ctx.conn, venture_id=ctx.venture_id, forge_id=forge_id, module_id=module_id
    )

    # NO TAKER IS NOT NO SUBMISSION - corrected 18 September 2026.
    #
    # This used to return early and submit nothing, on the argument that "an exam nobody
    # sits owes a verdict that can never be read." That argument is sound about the RUN
    # and wrong about the CURRICULUM, and the two were collapsed.
    #
    # Submitting the curriculum teaches SimForge the module's instruction set, which is
    # what its scenarios BIND to. `underwrite_deal` is the live case: SimForge holds no
    # instruction set for it, so 13 of the 44 drafted split-key scenarios have nothing
    # to bind to - and they would keep having nothing for as long as Deal Underwriter
    # stays unfilled, because the seat gates the exam and the exam was gating the
    # hand-over.
    #
    # So the curriculum goes over whether or not anyone can sit it, and the run is what
    # stays conditional on a taker. Nothing is owed a verdict that cannot arrive: the
    # loop below opens a run per taker, and with none it opens none.
    payload = _curriculum_payload(
        instruction=instruction, scenarios=scenarios, candidates=takers,
        modules_in_forge=modules_in_forge, modules_uncovered=modules_uncovered,
        venture_id=ctx.venture_id,
    )

    # THE ANSWER KEY'S IDENTITY, taken over the payload that is about to go on the
    # wire rather than re-derived from the generator - so it cannot describe anything
    # other than what was sent. Ruled 18 September 2026, entry 129.
    scenario_hash = scenario_set_hash(payload)

    unit, rubric_kind = submission_unit(module_id)
    opened: list[dict[str, Any]] = []
    try:
        acceptance = await client.submit_curriculum(
            ctx.conn, scenario_pack_ref=f"{pack_ref}/{module_id}",
            payload=payload, actor=ctx.actor, venture_id=ctx.venture_id,
        )
        # The per-module certification level SimForge just assigned - `certified`,
        # `certified_with_declared_absence` or `demonstrated`. Kept because it is what
        # the certification run needs and the old contract threw it away: this method
        # read one field off the body, and it was the one field that was never there.
        levels = acceptance.get("module_levels")
        if isinstance(levels, dict):
            module_level = levels.get(module_id)
        gate_9_5_flag = acceptance.get("gate_9_5_flag")

        # A' - the call that was declared, documented and never made. Without it
        # SimForge holds no row between the curriculum and the verdict, so a hung
        # battery produces nothing at all and TIMEOUT is unreachable from either side.
        #
        # The curriculum above went over ONCE - it is the same text for every taker and
        # SimForge upserts one instruction set per module. The run is what is per agent.
        for taker in takers:
            # Minted HERE, before anything is sent. `OperationRunStartRequest.run_ref`
            # is an input field, so this side owns the ref; deriving it from the
            # submission's natural key is what makes a retry land on the run that is
            # already open instead of opening a second one with a fresh window. The
            # agent is part of that key now. See `mint_run_ref`.
            minted_ref = mint_run_ref(
                venture_id=ctx.venture_id, forge_id=forge_id, module_id=module_id,
                content_hash=instruction.content_hash,
                office_agent_id=taker["office_agent_id"],
                # THE EXAM NAMES ITS ANSWER KEY. A rewritten key mints a different ref,
                # so `open_run` opens a new run instead of returning the old one with
                # the old verdict on it - which is what let six verdicts earned on
                # superseded scenarios be indistinguishable from the approved 44
                # (entries 128, 129). Nothing is sent that SimForge has not declared:
                # this changes the ref STRING, and `runRef` is already the whole of a
                # run's identity over there.
                scenario_hash=scenario_hash,
                # AND THE TWO VERSIONS IT IS GRADED UNDER. Entry 143. Both are None
                # until SimForge publishes them on `/api/version`, and `mint_run_ref`
                # omits an absent segment rather than defaulting it.
                protocol_version=forge_build.get("response_protocol_version"),
                rubric_version=forge_build.get("operation_rubric_version"),
            )
            started = await client.run_start(
                ctx.conn,
                run_ref=minted_ref,
                unit=unit,
                forge_id=forge_id,
                instruction_content_hash=instruction.content_hash,
                rubric_kind=rubric_kind,
                module_id=module_id,
                agent_id=str(taker["office_agent_id"]),
                # BESIDE the office id, never instead of it. The two name the same
                # agent to two different systems: `agent_id` is The Office's primary
                # key and means nothing to the Village, and `village_agent_ref` is what
                # the Village calls the same person - `victor_serath`, `ronan_valek`.
                # SimForge needs the second to resolve an identity out of village.db
                # (its ADR-0065); it cannot do that from a uuid.
                #
                # WHAT HAPPENS WHEN AN AGENT HAS NONE: it cannot. The column is NOT
                # NULL on `office_agent_identity`, measured - 0 of 55 identities lack
                # one - so there is no branch here and none is written. An identity
                # without a Village ref is not a state this system can be in, because
                # `sync-roster` is the only writer and it reads the ref first.
                #
                # A ref that no longer RESOLVES in the Village is a different thing and
                # is not The Office's to detect: the ref travels, and SimForge reports
                # what it found. Guessing here would put an Office opinion in front of
                # the Village's own answer.
                village_agent_ref=taker["village_agent_ref"],
                # Gate 8 submits per module, so every run it opens is unit A. A
                # department id here would be a unit B assertion on a unit A run.
                department_id=None,
                scenario_count=len(scenarios),
                coverage_denominator=max(modules_in_forge, 1),
                # Omitted, not guessed. The window is SimForge's policy and The Office
                # holds no opinion about how long an operation battery may take;
                # sending a number would put an Office default in front of the Forge's.
                window_minutes=None,
            )
            opened.append({
                "office_agent_id": taker["office_agent_id"],
                "agent_name": taker["agent_name"],
                # Set only once BOTH halves landed. A ref stored after a failed
                # `run_start` names a run SimForge has never heard of: the sweep would
                # poll `gate_result` and take a 404 forever, which is worse than the
                # NULL it replaced because it looks like a hand-over that worked.
                "run_ref": minted_ref,
                "already_open": bool(started.get("already_open")),
            })
        already_open = any(o["already_open"] for o in opened) if opened else None
        run_ref = opened[0]["run_ref"] if opened else None
    except CurriculumRejectedError as exc:
        # An answer, not an outage. Kept apart in the evidence because the response to
        # each is different: a rejection is scenarios somebody has to write, an outage
        # is a service to restart.
        violations = exc.violations
        error = str(exc)
    except ResponseRefusedError as exc:
        # SIMFORGE ANSWERED AND THE OFFICE REFUSED THE ANSWER. Not an outage, and not a
        # rejection either - the submission was accepted and the reply broke the
        # response manifest coming back.
        #
        # Kept apart because the three have three different responses: restart a
        # service, write scenarios, or shorten what we send. Reporting this as
        # `unreachable` cost an afternoon on 17 September 2026, when four modules
        # SimForge had accepted were recorded as a Forge that could not be reached.
        error = str(exc)
        response_refused = True
    except SimForgeError as exc:
        # Not fatal. The Office's half - the curriculum, the counts, the row - is
        # complete and reproducible; what failed is the other side receiving it.
        # Blocking the ladder here would make provisioning depend on a service that is
        # allowed to be down.
        error = str(exc)

    # `simforge_run_ref` is the whole point of this package: B8's retirement condition
    # is a stored ref, not a call that returned one. It is NULL unless the curriculum
    # was accepted AND the run was opened, which is what "handed over" now means.
    #
    # ONE ROW PER TAKER, each naming its own agent and carrying its own ref. A single
    # row for a module two agents sat would be the shape the sweep had to guess its way
    # out of, and 0044 exists so it no longer has to.
    if opened:
        for entry in opened:
            await _record_submission(
                ctx,
                forge_id=forge_id,
                module_id=module_id,
                department=None,
                office_agent_id=entry["office_agent_id"],
                scenario_pack_ref=f"{pack_ref}/{module_id}",
                scenario_count=len(scenarios),
                coverage_denominator=max(modules_in_forge, 1),
                instruction_content_hash=instruction.content_hash,
                run_ref=entry["run_ref"],
                scenario_hash=scenario_hash,
                protocol_version=forge_build.get("response_protocol_version"),
                rubric_version=forge_build.get("operation_rubric_version"),
            )
    elif not takers and error is None:
        # ACCEPTED, AND NOBODY CAN SIT IT. No `curriculum_submission` row, and that is
        # the original argument kept rather than abandoned: that table means "a verdict
        # is owed", `overdue_submissions` selects every row whose `result_received_at`
        # is NULL regardless of its ref, and a row for an exam nobody sat would sit in
        # the sweep's queue for ever being reported as `no_grant_holders`.
        #
        # The instruction set still reached SimForge, which is the whole point of
        # submitting a module with no taker. What did not happen is a run, so there is
        # nothing to correlate and nothing to poll.
        pass
    else:
        # No run was opened and something went wrong: the curriculum was refused, or
        # SimForge was unreachable. The row IS written, with a NULL ref, because a
        # verdict was owed and did not open - the shape
        # `test_a_run_that_did_not_open_stores_no_ref` pins. It names no agent because
        # no agent sat it.
        await _record_submission(
            ctx,
            forge_id=forge_id,
            module_id=module_id,
            department=None,
            office_agent_id=None,
            scenario_pack_ref=f"{pack_ref}/{module_id}",
            scenario_count=len(scenarios),
            coverage_denominator=max(modules_in_forge, 1),
            instruction_content_hash=instruction.content_hash,
            run_ref=None,
            # Recorded even though no run opened: the row says which key WOULD have
            # been sat, which is what makes a refused submission comparable with the
            # one that replaces it.
            scenario_hash=scenario_hash,
            protocol_version=forge_build.get("response_protocol_version"),
            rubric_version=forge_build.get("operation_rubric_version"),
        )

    outcome: dict[str, Any] = {
        "module_id": module_id,
        "scenario_count": len(scenarios),
        "run_ref": run_ref,
        # SimForge said yes to the curriculum. NOT the same as a run being opened: a
        # module whose curriculum is accepted and whose exam nobody sits is a finding
        # about the roster, not about the curriculum, and the two must not be one
        # number. This is what the zero-accepted block below reads.
        "curriculum_accepted": error is None,
        # Who sat it. EMPTY AND ACCEPTED is a real, reportable state, not a failure:
        # the instruction set reached SimForge and no agent holds a grant to be examined
        # on it. `underwrite_deal` is that today.
        "exam_takers": [
            {"office_agent_id": str(o["office_agent_id"]),
             "agent_name": o["agent_name"], "run_ref": o["run_ref"]}
            for o in opened
        ],
        # Carried out of here because the unit-B pass needs the basis this module was
        # actually handed over under, and re-reading `instructions.live` after the fact
        # would answer a question about now rather than about the submission.
        "instruction_content_hash": instruction.content_hash,
    }
    if module_level is not None:
        # The certification level SimForge assigned this module, carried into the
        # gate's evidence so a reader of a provisioning run can see it without going
        # back to SimForge for something it already said.
        outcome["module_level"] = module_level
    if gate_9_5_flag is not None:
        outcome["gate_9_5_flag"] = gate_9_5_flag
    if already_open is not None:
        # True means the run was already open and its clock was NOT restarted - a
        # re-run of Gate 8 against an unchanged instruction. Worth seeing: it is the
        # difference between "opened a run" and "found the one that was hanging".
        outcome["already_open"] = already_open
    if error is not None:
        outcome["error"] = error
    if response_refused:
        # The distinguishing mark, on the row rather than inferred from the message.
        outcome["response_refused"] = True
    if violations is not None:
        outcome["violations"] = violations
    return outcome


async def _record_submission(
    ctx: _Context, *, forge_id: str, module_id: str | None, department: str | None,
    scenario_pack_ref: str, scenario_count: int, coverage_denominator: int,
    instruction_content_hash: str, run_ref: str | None,
    office_agent_id: Any | None = None,
    members: dict[str, str] | None = None,
    scenario_hash: str | None = None,
    protocol_version: str | None = None,
    rubric_version: str | None = None,
    attestation_id: Any | None = None,
) -> None:
    """The one place Gate 8 writes a `curriculum_submission` row, for either unit.

    One site, because the two units differ in exactly two columns and everything else
    about the row - what a NULL `simforge_run_ref` means, which columns are NOT NULL,
    what the sweep will do with it - is identical. Two INSERTs into one table would be
    two places to keep in step, and they would disagree the first time a column was
    added, silently, because each would look right beside its own caller.

    **`module_id` and `department` are the unit**, and nothing here enforces that: the
    `unit_targets_match` and `rubric_matches_unit` CHECK constraints are on
    `certification`, NOT on this table - `curriculum_submission` has no unit constraint
    at all and both columns are nullable. So the rule lives where it always did, in
    `submission_unit`, and this function's callers pass exactly one of the two.

    `members` is `{module_id: instruction_content_hash}` and is **unit B's only**, for
    the same reason: a unit-A submission already names its one module in a column, and
    writing it here as well would be a second spelling of the same fact. A unit-B
    submission's `instruction_content_hash` is a composite over this set
    (`simforge.department_basis_hash`) and the composite is one-way, so without these
    rows nothing downstream can recover which instructions the department was judged
    against - which is B36 half two, and the reason the sweep could not record a
    unit-B PASS. Written in the SAME transaction as the parent row: a submission whose
    members are missing is a basis that cannot be recovered, and two statements that can
    half-succeed would produce exactly that.
    """
    submission_id = uuid.uuid4()
    async with ctx.conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO curriculum_submission
              (submission_id, venture_id, forge_id, module_id, department,
               scenario_pack_ref, scenario_count, coverage_denominator,
               instruction_content_hash, submitted_by, simforge_run_ref,
               office_agent_id, scenario_set_hash, run_id,
               protocol_version, rubric_version, attestation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                submission_id, ctx.venture_id, forge_id, module_id, department,
                scenario_pack_ref, scenario_count, coverage_denominator,
                instruction_content_hash, ctx.actor, run_ref, office_agent_id,
                scenario_hash,
                # WHICH RUN SET THIS EXAM. Gate 8 has always known - `_Context` holds
                # it, and `scenario_pack_ref` spells it as `run:<uuid>` text - and the
                # row threw it away. Entry 142: abandoning a run supersedes its open
                # submissions, and that cannot be done on a prefix of a free-text
                # column.
                ctx.run_id,
                # THE VERSIONS THIS EXAM WAS SET UNDER, in full beside the ref's copy.
                # `certification.rubric_version` answers which rubric the verdict was
                # GRADED under; this answers which one it was SET under, and a
                # difference between them is a run that was already open when the
                # rubric moved (entry 143). NULL until SimForge publishes them.
                protocol_version,
                rubric_version,
                attestation_id,
            ),
        )
        if members:
            await cur.executemany(
                """
                INSERT INTO curriculum_submission_module
                  (submission_id, module_id, instruction_content_hash)
                VALUES (%s, %s, %s)
                """,
                [(submission_id, m, h) for m, h in sorted(members.items())],
            )


def _department_forge_modules(
    positions: list[Any], module_forge: dict[str, str]
) -> dict[tuple[str, str], list[str]]:
    """(department, forge) -> the modules that department's positions operate there.

    **The two keys are `appointment._unit_b_certs`' two keys**, and that is the whole
    reason the grouping is shaped this way rather than around the venture's operating
    Forge. A position spans Forges - Greenstone's Acquisition Analyst reaches cre-forge
    and voiceforge - and unit B is required for EVERY Forge a position touches, so a
    department needs one certification per Forge and not one certification.

    `source_department` is used verbatim. It is a Village department name, validated
    against the live list by V29/V30, and `appointment.generate` passes exactly this
    string to the certification lookup - so any normalisation here would produce rows
    the gate that needs them cannot find.

    A module no Forge registers is dropped, not guessed at. V32 is the finding for
    that, and `appointment.generate` reports it separately as `module_not_registered`.
    """
    grouped: dict[tuple[str, str], set[str]] = {}
    for position in positions:
        for module_id in position.module_ids:
            forge_id = module_forge.get(module_id)
            if forge_id is None:
                continue
            grouped.setdefault((position.source_department, forge_id), set()).add(module_id)
    return {key: sorted(modules) for key, modules in sorted(grouped.items())}


async def _open_department_units(
    ctx: _Context, client: Any, *, submitted: list[dict[str, Any]],
    positions: list[Any], module_forge: dict[str, str], pack_ref: str,
    forge_build: dict[str, Any],
) -> list[dict[str, Any]]:
    """The unit-B half. One run per (department, forge). **No curriculum is submitted.**

    WHY THERE IS NOTHING TO SUBMIT, READ OFF THE RECEIVING SIDE
    ===========================================================

        `ForgeOperationCurriculum.instruction_set_ref.module_id` is a required, non
        optional `str`, so a department-scoped curriculum is not expressible in
        SimForge's payload. The one field that looks like it is - a
        `CertificationUnitRequest` with `unit_type="department_context"` and a
        `department_id` - is read by nothing: `routers/operation.py::submit_curriculum`
        takes `{u.module_id for u in body.certification_units_requested if u.module_id}`
        out of that list and consumes no other field on it, then upserts a
        `ForgeInstructionSet` keyed `(forgeId, moduleId, contentHash)`.

        Calling `submit_curriculum` for a department would therefore either 422 on the
        missing module or upsert an instruction set under an invented module name. So
        the unit-B path is `run_start` and the correlation row, which is what
        `OperationRunStartRequest` was already shaped for: `unit`, `rubric_kind` and
        `department_id` are all on it, and `module_id` is optional.

    WHAT A DEPARTMENT RUN IS OPENED AGAINST
    =======================================

        Only the modules whose curriculum SimForge ACCEPTED and whose run opened. A
        department's context on a Forge is cleared against the instructions SimForge
        actually holds for it; a module that 422'd or never reached the Forge is not
        part of a basis SimForge could judge, and including it would put a hash in the
        column that names material the other side does not have.

        A (department, forge) pair with no accepted module is **reported and not
        opened** - it appears in the evidence carrying `skipped` and the department it
        names. That is the pair `appointment.generate` will refuse as
        `missing_unit_b`, said out loud at the gate that could have produced it,
        instead of surfacing four gates later as "zero certified candidates".

    THE COUNTS ARE THE DEPARTMENT'S, AND THEY ARE NOT INVENTED
    ==========================================================

        `scenario_count` is the sum of the scenarios The Office actually submitted for
        that department's accepted modules on that Forge - the same quantity the unit-A
        path sends, aggregated over the unit's own key. It is not a count of scenarios
        this run carries, because it carries none, and it is not a guess:
        `curriculum_submission.scenario_count` is `CHECK (scenario_count > 0)`, and
        rather than clamp a zero to 1 the way a placeholder would, a department with
        nothing submitted gets no run at all.

        `coverage_denominator` is how many modules that department operates on that
        Forge, against a numerator of how many were accepted. Both are named in the
        evidence so the denominator is visible rather than implied - "a scenario count
        without one is not coverage."
    """
    accepted = {
        o["module_id"]: o
        for o in submitted
        if o.get("run_ref") and o.get("instruction_content_hash")
    }
    units: list[dict[str, Any]] = []

    for (department, forge_id), modules in _department_forge_modules(
        positions, module_forge
    ).items():
        covered = [m for m in modules if m in accepted]
        entry: dict[str, Any] = {
            "department": department,
            "forge_id": forge_id,
            "modules_operated": len(modules),
            "modules_accepted": len(covered),
            "run_ref": None,
        }
        if not covered:
            # Not an error and NOT A RUN. Same rule as a module with no live
            # instruction: a correlation row for a run nobody opened would sit in the
            # sweep's queue waiting for a verdict that cannot arrive.
            entry["skipped"] = (
                "no module of this department was accepted by this Forge, so there is "
                "no basis a department context could be cleared against"
            )
            units.append(entry)
            continue

        basis = department_basis_hash(
            {m: accepted[m]["instruction_content_hash"] for m in covered}
        )
        scenario_count = sum(int(accepted[m]["scenario_count"]) for m in covered)
        # One rule, one place. `submission_unit(None)` is what makes this a B, exactly
        # as `submission_unit(module_id)` makes the per-module path an A.
        unit, rubric_kind = submission_unit(None)
        minted_ref = mint_run_ref(
            venture_id=ctx.venture_id, forge_id=forge_id, module_id=None,
            department=department, content_hash=basis,
            # ON UNIT B TOO, unlike the scenario hash. A department run submits no
            # curriculum and so names no answer key, but it is graded under a rubric
            # exactly as unit A is - `rubric_kind` is `domain` - and the collision this
            # closes does not care which unit it happens on.
            protocol_version=forge_build.get("response_protocol_version"),
            rubric_version=forge_build.get("operation_rubric_version"),
        )
        entry["instruction_content_hash"] = basis
        entry["scenario_count"] = scenario_count

        run_ref: str | None = None
        try:
            started = await client.run_start(
                ctx.conn,
                run_ref=minted_ref,
                unit=unit,
                forge_id=forge_id,
                instruction_content_hash=basis,
                rubric_kind=rubric_kind,
                # NULL, and it is the unit. `unit_targets_match` reads
                # `B -> department NOT NULL`, and a module id on a unit-B run would be
                # a unit-A assertion on it.
                module_id=None,
                # A department certification is about the department, not about one of
                # its agents. Naming one would be a claim about which agent the run is
                # for, decided by a sort order.
                agent_id=None,
                department_id=department,
                scenario_count=scenario_count,
                coverage_denominator=len(modules),
                # Omitted, not guessed. The window is SimForge's policy, same as the
                # per-module path.
                window_minutes=None,
            )
            entry["already_open"] = bool(started.get("already_open"))
            run_ref = minted_ref
        except SimForgeError as exc:
            # Non-fatal, for the reason the per-module path gives: The Office's half is
            # complete and reproducible, and provisioning must not depend on a service
            # that is allowed to be down.
            entry["error"] = str(exc)

        # THE ATTESTATION IN FORCE, OR NONE. Ruled 21 September 2026, entry 147.
        #
        # A department run submits no curriculum, so nothing runs and no verdict is ever
        # earned. Until a hand-over test exists, a named human with founder authority
        # says whether the escalation path and the compliance coupling are verified, and
        # THIS is where that reaches SimForge - as a `department_outcomes` entry on the
        # gate-result callback, which is what writes the unit-B certification Gate 9
        # reads.
        #
        # NOTHING IS POSTED FOR A DEPARTMENT NOBODY HAS ATTESTED, and the gate reports
        # which. An outcome with `passed` defaulted true over two unanswered questions is
        # exactly the certification-by-assertion this exists to avoid.
        attested = await attestation.current_attestation(
            ctx.conn, venture_id=ctx.venture_id, department=department,
            forge_id=forge_id,
        )
        if attested is None:
            entry["attestation"] = None
        elif run_ref is None:
            # No run to post an outcome against. The attestation stands and is recorded
            # on the row; there is simply nowhere to send it yet.
            entry["attestation"] = {"posted": False, "reason": "no run was opened"}
        else:
            entry["attestation"] = {
                "attestation_id": str(attested.attestation_id),
                "attested_by": attested.attested_by_name,
                "escalation_path_verified": attested.escalation_path_verified,
                "compliance_coupling_verified": attested.compliance_coupling_verified,
                "passed": attested.passed,
                "posted": False,
            }
            try:
                await client.post_gate_result(
                    ctx.conn,
                    run_ref=run_ref,
                    instruction_set_ref={
                        # The department's composite basis, named the way a unit-A
                        # submission names its module's instruction. `module_id` is
                        # required by the schema and a department has none, so the
                        # first member module stands for the set the composite was
                        # taken over - and `members` on the submission row is what
                        # recovers the whole of it.
                        "forge_id": forge_id,
                        "module_id": covered[0] if covered else None,
                        "content_hash": basis,
                        "instruction_version": None,
                        "forge_api_version": None,
                        "authored_by": None,
                    },
                    run_content_hash=basis,
                    department_outcomes=[{
                        "department_id": department,
                        "forge_id": forge_id,
                        # DERIVED FROM THE TWO FACTS, never sent as a bare `passed`.
                        # The schema defaults `passed` to true and both verified flags
                        # to false, so a caller sending only the first would assert a
                        # pass over two questions nobody answered.
                        "passed": attested.passed,
                        "escalation_path_verified": attested.escalation_path_verified,
                        "compliance_coupling_verified":
                            attested.compliance_coupling_verified,
                    }],
                    actor=ctx.actor,
                    venture_id=ctx.venture_id,
                )
                entry["attestation"]["posted"] = True
            except SimForgeError as exc:
                # Non-fatal, same as `run_start` above and for the same reason.
                entry["attestation"]["error"] = str(exc)

        await _record_submission(
            ctx,
            forge_id=forge_id,
            module_id=None,
            department=department,
            scenario_pack_ref=f"{pack_ref}/dept:{department}@{forge_id}",
            scenario_count=scenario_count,
            coverage_denominator=len(modules),
            instruction_content_hash=basis,
            run_ref=run_ref,
            # The same mapping `basis` was computed from, stored rather than re-derived.
            # `department_basis_hash` is one-way, so this is the only record of what the
            # composite was composed of.
            members={m: accepted[m]["instruction_content_hash"] for m in covered},
            protocol_version=forge_build.get("response_protocol_version"),
            rubric_version=forge_build.get("operation_rubric_version"),
            # WHICH ATTESTATION THIS UNIT WAS POSTED WITH, and it is the only thing that
            # will distinguish the verdict when it comes back. SimForge returns a PASS
            # that is byte-identical whether a battery earned it or a person attested it,
            # so the sweep reads this column to know which it is holding (entry 147).
            #
            # Written only when the outcome actually went over the wire. An attestation
            # that existed and was not posted did not produce the verdict, and a row
            # saying otherwise would be the false provenance this whole change is about.
            attestation_id=(
                attested.attestation_id
                if attested is not None and (entry.get("attestation") or {}).get("posted")
                else None
            ),
        )
        entry["run_ref"] = run_ref
        units.append(entry)

    return units


def _curriculum_payload(
    *, instruction: Any, scenarios: list[Any], candidates: list[dict[str, str]],
    modules_in_forge: int, modules_uncovered: list[str], venture_id: str,
) -> dict[str, Any]:
    """A `ForgeOperationCurriculum`, in SimForge's shape.

    `functions_in_module` / `functions_covered` are 0 because The Office does not model
    functions inside a module. Zero, visibly, rather than a guess.

    `scenario_class` and `instruction_section` ARE SENT, as of P-05 and contract A1.2's
    third named purpose. They were absent for as long as `curriculum.generate` produced
    one summary per (position, module) rather than a classed probe of one instruction
    section, and the code said so at the site. It produces the classed probe now.

    **This is the change that lets a submission reach `validate_curriculum_submission`
    at all.** Both fields are required by `OperationScenarioSubmission`, so every
    submission until now has been refused by Pydantic before the validator ran - which
    is why `docs/scenario-contract.md` opens by pointing out that the validator has
    never once executed against a real Office payload. Sending them moves the refusal
    from the schema to the validator. **That is one layer, not acceptance:** the
    validator will still refuse an unauthored scenario for an empty `expected_behavior`
    or `expected_escalation`, and filling those is B4's authorship, not this file's.
    """
    never_do = instruction.content.get("never_do") or []
    if isinstance(never_do, str):
        never_do = [never_do]

    # A declared `not_applicable` is a statement about a (module, class) pair, not a
    # scenario, and contract A1.1 gives it a curriculum-level map rather than a row -
    # structurally parallel to `module_never_do` below. So the rows carrying one are
    # lifted out of `operation_scenarios` here rather than submitted as scenarios that
    # declare they are not scenarios.
    absent = declared_absent(scenarios)

    return {
        "instruction_set_ref": {
            "forge_id": instruction.forge_id,
            "module_id": instruction.module_id,
            "instruction_version": instruction.instruction_version,
            "forge_api_version": instruction.forge_api_version,
            "content_hash": instruction.content_hash,
            # Nullable on SimForge's side and defaulted to "office" there. The Office
            # authors instructions under a human's id, and sending it would put a
            # person's uuid in another system for no purpose this call has.
            "authored_by": None,
        },
        "certification_units_requested": [
            {
                "unit_type": "agent_operation",
                "forge_id": instruction.forge_id,
                # THE AGENTS WHO WILL SIT THE EXAM - the holders of a live grant for
                # this module, which is the population `_exam_takers` returns and the
                # population the verdict will be written for. It used to be
                # `requires_certification`, the pool of people who could fill a seat
                # and hold no grant: a certification requested for an agent Gate 9
                # cannot read through a grant is a request nothing can satisfy.
                #
                # SimForge consumes only `module_id` from this list, so this is a
                # declaration rather than an instruction - which is exactly why it has
                # to be a true one. Nothing on the far side would have complained.
                "agent_id": str(c["office_agent_id"]),
                "module_id": instruction.module_id,
            }
            for c in candidates
        ],
        # THE ROWS, BUILT BY `simforge.operation_scenario_rows`. They were spelled
        # inline here until entry 142, which needs the identical rows derived from the
        # approved key alone so a verdict can be refused when the two disagree. Two
        # spellings would have made that check refuse over its own drift.
        #
        # What each field carries, and why `situation` and `expected_answer` are
        # omitted rather than blanked, is documented on that function.
        "operation_scenarios": operation_scenario_rows(scenarios),
        "coverage_declaration": {
            "modules_in_forge": modules_in_forge,
            "modules_covered": modules_in_forge - len(modules_uncovered),
            "modules_uncovered": modules_uncovered,
            # The Office has no concept of a function inside a module. A module is the
            # smallest unit named anywhere here. Zero, visibly, rather than a guess.
            "functions_in_module": 0,
            "functions_covered": 0,
        },
        "module_never_do": {instruction.module_id: list(never_do)},
        # module -> class -> reason. ADR-0049 and contract A1.1: the absence is
        # stated, never inferred, and never a pass - it carries VERDICT_NOT_APPLICABLE
        # to the cert rather than a zero. An empty map means no class was declared
        # absent for this module, which is a different statement from a class being
        # absent with nothing said about it, and that is the whole point.
        "module_not_applicable": {instruction.module_id: absent},
    }


def _certification_candidates(artifacts: Any) -> dict[str, list[dict[str, str]]]:
    """Which agents a Unit A certification would be requested for, per module.

    `requires_certification` and not `appointed`: an appointed agent already holds the
    certification, and the population worth certifying is the candidates who exist and
    do not. For Greenstone today that is every one of them.
    """
    by_module: dict[str, list[dict[str, str]]] = {}
    positions = {p.position_title: p for p in artifacts.roles.positions}
    for appointment in artifacts.appointment.appointments:
        position = positions.get(appointment.position_title)
        if position is None:
            continue
        for module_id in position.module_ids:
            by_module.setdefault(module_id, []).extend(
                {"office_agent_id": c.office_agent_id, "agent_name": c.agent_name}
                for c in appointment.requires_certification
            )
    return by_module


async def _module_forges(
    conn: AsyncConnection, modules: set[str]
) -> dict[str, str]:
    """Which Forge dispatches each module.

    A position's `forge_modules_operated` is a list of bare module ids, and they are not
    all on the venture's operating Forge - Greenstone's roles operate `place_call` and
    `transcribe_call`, which belong to voiceforge. Resolving them against the operating
    Forge finds no instruction and reports a module that has one as having none.

    A module id registered by two Forges would be ambiguous here. The registry's primary
    key does not prevent it, so the first by forge_id wins and it is deterministic
    rather than correct - if that ever happens the module id is the thing to fix, since
    `forge_modules_operated` cannot express which was meant.
    """
    if not modules:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, forge_id FROM forge_module_registry "
            "WHERE module_id = ANY(%s) ORDER BY module_id, forge_id",
            (sorted(modules),),
        )
        rows = await cur.fetchall()
    resolved: dict[str, str] = {}
    for module_id, forge_id in rows:
        resolved.setdefault(module_id, forge_id)
    return resolved


async def _module_coverage(
    conn: AsyncConnection, forge_ids: set[str]
) -> dict[str, tuple[int, list[str]]]:
    """Per Forge: how many modules it has, and which the curriculum does not reach.

    Read from `forge_module_registry` rather than from the Pack: the denominator is how
    many modules exist, and a Pack that forgot to declare one would otherwise report
    full coverage of what it remembered.
    """
    if not forge_ids:
        return {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT forge_id, module_id FROM forge_module_registry "
            "WHERE forge_id = ANY(%s)",
            (sorted(forge_ids),),
        )
        rows = await cur.fetchall()
    by_forge: dict[str, set[str]] = {f: set() for f in forge_ids}
    for forge_id, module_id in rows:
        by_forge.setdefault(forge_id, set()).add(module_id)

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT forge_id, module_id FROM forge_operating_instruction "
            "WHERE superseded_at IS NULL AND forge_id = ANY(%s)",
            (sorted(forge_ids),),
        )
        taught = {(r[0], r[1]) for r in await cur.fetchall()}

    return {
        forge_id: (
            len(modules),
            # Uncovered means "this Forge has a module the curriculum does not teach",
            # measured against what has an instruction rather than against what this
            # venture happens to use. A module nobody wrote an instruction for is the
            # honest uncovered case.
            sorted(m for m in modules if (forge_id, m) not in taught),
        )
        for forge_id, modules in by_forge.items()
    }


async def _recorded_forge_build(ctx: _Context) -> dict[str, Any] | None:
    """What Gate 8 recorded about the Forge on THIS run, or None if it never ran.

    Gate 9 does not call SimForge - its own docstring says why, and the reason holds
    doubly here: whether a department hand-over test exists is a fact about the build
    that SET these exams, not about whatever is answering the port now. A live probe
    would let a Forge restarted between Gate 8 and Gate 9 change what this run's
    certifications are worth.

    `None` when Gate 8 has no result on this run - a venture whose grants were bootstrapped
    is the case - and `handover_test_available` reads that as "nobody said", which leaves
    attested units counting and says so.
    """
    async with ctx.conn.cursor() as cur:
        await cur.execute(
            "SELECT evidence FROM provisioning_gate_result "
            " WHERE run_id = %s AND gate = '8' ORDER BY recorded_at DESC LIMIT 1",
            (ctx.run_id,),
        )
        row = await cur.fetchone()
    if row is None or not isinstance(row[0], dict):
        return None
    found = row[0].get("forge_build")
    return found if isinstance(found, dict) else None


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
                   cb.simforge_verdict AS unit_b_verdict,
                   ca.model_digest AS unit_a_digest,
                   cb.model_digest AS unit_b_digest,
                   cb.basis AS unit_b_basis,
                   at.attested_by AS unit_b_attested_by,
                   at.attested_by_name AS unit_b_attester,
                   -- Entry 167, read from the certification and its declaration.
                   -- `simulation_void` is a join and not a column: a simulation
                   -- certification is void the moment its venture leaves, and a stored
                   -- flag would read valid until somebody ran a job.
                   (cb.basis = 'simulation') AS unit_b_simulation,
                   (vs.left_at IS NOT NULL) AS unit_b_simulation_void,
                   vs.reason AS unit_b_simulation_reason,
                   sh.display_name AS unit_b_simulation_declared_by
            FROM agent_forge_grant g
            LEFT JOIN certification ca
              ON ca.unit = 'A' AND ca.cert_id::text = g.operation_cert_ref
            LEFT JOIN certification cb
              ON cb.unit = 'B' AND cb.cert_id::text = g.dept_context_cert_ref
            LEFT JOIN department_attestation at
              ON at.attestation_id = cb.attestation_ref
            LEFT JOIN venture_simulation vs
              ON vs.simulation_id = cb.simulation_ref
            LEFT JOIN office_human sh ON sh.human_id = vs.declared_by
            WHERE g.venture_id = %s AND g.superseded_at IS NULL
            ORDER BY g.grant_id
            """,
            (ctx.venture_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    # A RETIRED GRANT IS NOT ASKED FOR A CERTIFICATION EITHER, for the same reason as
    # the paragraph below and by the same argument. The predicate is in the SQL rather
    # than here because a retired grant is not a finding this gate reports - it confers
    # nothing, so there is nothing to say about it. This was not in the sizing: the
    # symptom was Gate 7, but Gate 9 reads the venture's grants with exactly the same
    # premise, and a bootstrap grant the ladder replaced would still have demanded Unit A
    # on its module and Unit B on its department - certifiable, but certified for a row
    # that grants nothing. Measured, not reasoned: with one retired grant present this
    # gate reported "2 of 22 certification unit(s) are not certified" and held the run at
    # 9; without it, "20 certification unit(s) certified across 10 grant(s)".
    #
    # REVOKED GRANTS ARE NOT ASKED FOR A CERTIFICATION - decisions entry 91, B53's shape.
    #
    # Gate 11 learned in B53 that a grant a live revocation covers is not one it may
    # activate. This gate had the same blind spot from the other side: it counted every
    # grant on the venture, so a grant revoked BECAUSE it should never have existed still
    # demanded Unit A and Unit B, and burkham-wickmont's four Phase 0 engineering grants -
    # revoked 14 September, certifiable by nobody - held the whole venture at Gate 9 (entry
    # 75). Neither deactivation nor revocation could clear it, because neither is a thing
    # this query read. `covered_grants` is reused rather than restated, as it is in Gate 11.
    covered = await revocation.covered_grants(ctx.conn, venture_id=ctx.venture_id)
    withheld = [r for r in rows if uuid.UUID(r["grant_id"]) in covered]
    rows = [r for r in rows if uuid.UUID(r["grant_id"]) not in covered]
    withheld_scopes = sorted({covered[uuid.UUID(r["grant_id"])].scope for r in withheld})
    withheld_note = (
        f" {len(withheld)} revoked grant(s) not counted ({'/'.join(withheld_scopes)})."
        if withheld else ""
    )

    if not rows:
        return GateOutcome(
            "9", BLOCKED,
            "no grants to certify. A venture with nothing granted has passed no "
            f"Readiness Gate; it has simply not been asked one.{withheld_note}",
            {"grants": 0, "withheld_revoked": len(withheld)},
        )

    # WHAT ENDS THE STOP-GAP. Ruled 21 September 2026, entry 147: when a real
    # hand-over test ships, attested unit-B certifications stop counting here and must
    # be re-earned.
    #
    # Read off the `forge_build` THIS RUN's Gate 8 recorded, never by a live call. That
    # is this gate's own rule - "a Readiness Gate verdict reaches The Office by being
    # recorded" - and it is also the right answer: the build that set the exams is the
    # build whose capabilities decide what those exams were worth.
    handover = attestation.handover_test_available(await _recorded_forge_build(ctx))
    by_state: dict[str, int] = {}
    unattested: list[str] = []
    unpinned: list[str] = []
    failing: list[dict[str, str]] = []
    attested_units: list[str] = []
    simulation_units: list[str] = []
    voided_units: list[str] = []
    for row in rows:
        for unit in ("a", "b"):
            state = row[f"unit_{unit}_state"]
            if unit == "b" and row.get("unit_b_simulation"):
                # ACCEPTED WHILE THE VENTURE IS IN SIMULATION, REFUSED THE MOMENT IT
                # LEAVES. Ruled 22 September 2026, entry 167.
                #
                # The row is untouched either way - nothing in this gate edits a
                # certification, the same discipline the attested branch below keeps.
                # What changes is whether this gate counts it.
                if row["unit_b_simulation_void"]:
                    voided_units.append(
                        f"{row['grant_id'][:8]}/unitB certified for a simulation "
                        f"{row['unit_b_simulation_declared_by'] or 'somebody'} has "
                        "since left"
                    )
                    state = "simulation_certification_void"
                else:
                    declarer = (
                        row["unit_b_simulation_declared_by"]
                        or "somebody no longer on file"
                    )
                    simulation_units.append(
                        f"{row['grant_id'][:8]}/unitB SIMULATION ONLY - declared by "
                        f"{declarer}: {row['unit_b_simulation_reason']}"
                    )
            if unit == "b" and row.get("unit_b_basis") == "attested":
                # NAMED WHEREVER IT COUNTS, which is the whole of the first ruling: a
                # reader of this gate can always tell an attested unit from a tested
                # one, and the name of the person who attested it is on the line.
                attested_units.append(
                    f"{row['grant_id'][:8]}/unitB attested by "
                    f"{row['unit_b_attester'] or 'somebody no longer on file'}"
                )
                if handover is True:
                    # RE-EARNED, not demoted. The row is untouched - nothing here edits
                    # a certification - and this gate refuses to count it, so a run has
                    # to go and get a real one.
                    state = "attested_but_a_test_now_exists"
            by_state[state] = by_state.get(state, 0) + 1
            if state != "certified":
                failing.append({
                    "grant_id": row["grant_id"], "module_id": row["module_id"],
                    "unit": unit.upper(), "state": state,
                })
            elif unit == "b" and row.get("unit_b_simulation"):
                # NOT `unattested`. A simulation certification carries no SimForge
                # verdict BY CONSTRUCTION - migration 0059 refuses one - so reporting it
                # as "certified but carries no SimForge PASS" would be true and useless:
                # it is already named, in its own list, with the declaration behind it.
                pass
            elif row[f"unit_{unit}_verdict"] != "PASS":
                # A certification carrying no SimForge PASS was not produced by a
                # Readiness Gate, whatever its state column says.
                unattested.append(f"{row['grant_id'][:8]}/unit{unit.upper()}")
            elif not row[f"unit_{unit}_digest"]:
                # It passed, SimForge said so, and nothing can say WHICH MODEL passed.
                # Separate from `unattested` because the responses differ: that one is
                # a certification to go and earn, this one is a row to re-certify.
                unpinned.append(f"{row['grant_id'][:8]}/unit{unit.upper()}")

    evidence = {
        "grants": len(rows),
        "units_checked": len(rows) * 2,
        "states": dict(sorted(by_state.items())),
        "not_certified": failing[:20],
        "not_certified_total": len(failing),
        "certified_without_simforge_verdict": unattested[:20],
        "certified_without_a_model_digest": unpinned[:20],
        "withheld_revoked": len(withheld),
        "withheld_revoked_grants": [r["grant_id"] for r in withheld][:20],
        "revocation_scopes": withheld_scopes,
        # ENTRY 147, ON THE ROW WHETHER OR NOT IT CHANGED THE VERDICT. A reader asking
        # "what is this venture's readiness resting on" gets the count and the names
        # without going to another table, and gets it on a PASS as well as a block.
        "attested_units": attested_units,
        # ENTRY 167. WHICH UNITS ARE SIMULATION-ONLY, on the pass as well as the block,
        # for the reason `attested_units` is here: a reader asking what this venture's
        # readiness rests on gets the answer without going to another table.
        "simulation_units": simulation_units,
        "simulation_only_units": len(simulation_units),
        "voided_simulation_units": voided_units,
        "handover_test_available": handover,
        # The key that was looked for, named. Entry 144's lesson: a guess about another
        # system's shape reads as that system's silence, so the guess is on the record
        # rather than in somebody's head.
        "handover_test_key": attestation.HANDOVER_TEST_KEY,
    }
    attested_note = (
        f" {len(attested_units)} unit(s) rest on a named human's attestation rather "
        "than a test"
        + (
            "; a hand-over test now exists, so they no longer count and must be "
            "re-earned." if handover is True else "."
        )
        if attested_units else ""
    )
    # NAMED IN THE VERDICT, not only in the evidence. Entry 167: any surface showing a
    # gate says which of its certifications are simulation-only, and a gate that passed
    # partly on a declaration and said so only in a JSON field has passed quietly.
    simulation_note = (
        f" {len(simulation_units)} unit(s) are SIMULATION-ONLY - certified on a "
        "declaration, not an exam, and void the moment the venture leaves simulation."
        if simulation_units else ""
    )
    if voided_units:
        simulation_note += (
            f" {len(voided_units)} simulation certification(s) are VOID: the venture "
            "has left simulation and they must be re-earned."
        )

    if failing:
        summary = "; ".join(
            f"{count} x {state}" for state, count in sorted(by_state.items())
            if state != "certified"
        )
        return GateOutcome(
            "9", BLOCKED,
            f"{len(failing)} of {len(rows) * 2} certification unit(s) are not certified "
            f"({summary}). Every grant needs Unit A on its module and Unit B on its "
            f"department before the Readiness Gate is passed."
            f"{withheld_note}{attested_note}{simulation_note}",
            evidence,
        )
    if unattested:
        return GateOutcome(
            "9", BLOCKED,
            f"{len(unattested)} certification(s) read as certified but carry no SimForge "
            "PASS. A certification nothing external attested is a certification The "
            f"Office wrote for itself.{withheld_note}{attested_note}{simulation_note}",
            evidence,
        )
    # A CERTIFICATION THAT CANNOT NAME THE MODEL CANNOT EXPIRE WHEN THE MODEL MOVES.
    # Ruled 17 September 2026.
    #
    # Third in the sequence and narrower each time: not certified, then certified by
    # nobody external, then attested by SimForge and unattributable to a model file.
    # `agent_model` does not close this - it is a LABEL, and the same tag re-pulled at
    # a different quantization produces the identical string.
    #
    # 0044's `certification_names_its_model` makes this unreachable for any row written
    # after it, which is the point: the constraint is the control and this is the gate
    # saying so where a run can see it. What it does catch is a row that predates 0044,
    # and it will keep catching it until somebody re-certifies.
    if unpinned:
        return GateOutcome(
            "9", BLOCKED,
            f"{len(unpinned)} certification(s) carry a SimForge verdict and no model "
            "digest. A certification that cannot name the model it was earned on cannot "
            "be re-certified when the model changes - `agent_model` is a label and the "
            f"same label describes different weights."
            f"{withheld_note}{attested_note}{simulation_note}",
            evidence,
        )
    # ON THE PASS TOO, and that is the sentence that matters most. A Readiness Gate that
    # passes without saying what part of it rests on somebody's word is the note-in-a-
    # document this replaced.
    return GateOutcome(
        "9", PASSED,
        f"{len(rows) * 2} certification unit(s) certified across {len(rows)} grant(s)"
        f"{withheld_note}{attested_note}{simulation_note}",
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
    """Activate production grants - only against a valid, unvoided signature, and never
    one a live revocation covers.

    Gate 10 already checked the signature, but it is checked again here rather than
    trusted from the previous step. Activation is the moment agents gain production
    authority, and a gate that trusts its predecessor's verdict is a gate that can be
    reached by any path that sets the predecessor's state.

    B53 - THE UPDATE DID NOT KNOW ABOUT REVOCATION
    ==============================================

        The predicate was `WHERE venture_id = %s AND activated_at IS NULL`, and that is
        every grant the venture has, revoked ones included. **Two controls over one
        invariant, and the second did not know about the first:** `resolve_grant` refuses
        a revoked grant on every call, and this gate handed it `activated_at = now()` and
        `activated_by = <the signer>` without asking.

        Not a hole in the authority - the call path still refuses, and `check_revocations`
        runs before anything else in `resolve_grant`. **A hole in the record.** Four
        `burkham-wickmont` grants were revoked on 14 September with a documented reason;
        this gate would have stamped the same human as their activator hours later, and
        the row would then assert both, with no ordering visible in either.

        **It had never fired.** No run has reached Gate 11, so the UPDATE has never
        executed against a venture holding a revocation. Same shape as entry 63's Gate 7
        passing on an empty set, and found the same way - by asking what the next gate
        does before letting it run, rather than by watching it do it.

        `revocation.covered_grants()` is the predicate, reused rather than restated. A
        second spelling of "covered" is a second thing to keep in step, and the module's
        own docstring says why it cannot be a column: a venture-scope revocation must
        cover grants issued after it was declared.

    CERTIFIED, ON BOTH UNITS - ENTRY 145
    ====================================

        *"Certification is required at Gate 11, where authority is granted."*

        This gate did not check it, and until 21 September nothing needed it to: Gate
        4.5 seated only certified agents, so an uncertified grant could not exist by the
        time a run got here, and Gate 9 blocks a run whose units are not certified
        anyway.

        **Entry 145 made uncertified grants reachable.** 4.5 now seats a candidate who
        can sit the exam, Gate 5 issues its grant inactive, and that grant arrives here
        pointing at a certification reading `in_training` or `failed`. The predicate
        above would have stamped `activated_at` and `activated_by` on it.

        Not a hole in the authority - `resolve_grant` refuses every call on
        certification state, and Gate 9 still blocks the run. **A hole in the record**,
        and the same shape as B53's: a grant asserting a named human activated it, when
        nothing it rests on was ever earned. So the test moved to where the ruling puts
        it, rather than being left to two gates either side.

        Both units, and `state = 'certified'` rather than "a ref exists". A ref is
        written by `runtime_config.apply` as a POINTER at whatever certification exists
        - a `failed` one included - so a NOT NULL test would pass on a recorded failure.
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

    covered = await revocation.covered_grants(ctx.conn, venture_id=ctx.venture_id)
    async with ctx.conn.cursor() as cur:
        await cur.execute(
            "UPDATE agent_forge_grant g SET activated_at = now(), activated_by = %s "
            "  FROM office_agent_identity i "
            " WHERE i.office_agent_id = g.office_agent_id AND i.status = 'active' "
            "   AND g.venture_id = %s AND g.activated_at IS NULL "
            # Belt and braces, and cheap. Today a retired grant is always an activated
            # bootstrap one, so `activated_at IS NULL` already excludes it - but that is
            # a fact about who writes what, not a rule. Activating history would be the
            # worst thing this gate could do.
            "   AND g.superseded_at IS NULL "
            # THE MODEL, at the last point before production authority. Ruled 17
            # September 2026. A grant whose unit-A certification carries a SimForge
            # verdict and no model digest is a grant nobody could re-certify when the
            # model moves, and this gate is the last thing between a signature and an
            # agent that can act. Gate 9 refuses the run for the same reason; this is
            # the same rule at the moment it becomes irreversible.
            #
            # `simforge_verdict IS NOT NULL` scopes it: a bootstrap certification has
            # no model by design and Gate 11 has always activated grants that rest on
            # one.
            "   AND NOT EXISTS ("
            "       SELECT 1 FROM certification ca "
            "        WHERE ca.cert_id::text = g.operation_cert_ref "
            "          AND ca.simforge_verdict IS NOT NULL "
            "          AND ca.model_digest IS NULL) "
            # CERTIFIED, ON BOTH UNITS, AT THE MOMENT AUTHORITY IS GRANTED.
            # Ruled 21 September 2026, entry 145. See this gate's docstring.
            "   AND EXISTS ("
            "       SELECT 1 FROM certification ca "
            "        WHERE ca.unit = 'A' AND ca.cert_id::text = g.operation_cert_ref "
            "          AND ca.state = 'certified') "
            "   AND EXISTS ("
            "       SELECT 1 FROM certification cb "
            "        WHERE cb.unit = 'B' AND cb.cert_id::text = g.dept_context_cert_ref "
            "          AND cb.state = 'certified') "
            # A GRANT WITH NO PLANNED TIER CONFERS NOTHING, so there is nothing here to
            # switch on. Ruled 21 September 2026 and carried by 0049. Behind the
            # certification test rather than instead of it: a tierless grant is also an
            # uncertified one today, and a control that rests on that staying true is a
            # control that expires without saying so.
            "   AND g.trust_tier IS NOT NULL "
            "   AND NOT (g.grant_id = ANY(%s))",
            (ctx.actor, ctx.venture_id, list(covered)),
        )
        activated = cur.rowcount
        # Counted after the UPDATE, from the same predicates, so the figures are what this
        # gate actually declined rather than what it would decline if asked again. Each
        # withheld grant is counted once, revocation first: a revoked grant held by an
        # inactive agent is withheld for the reason somebody documented.
        await cur.execute(
            "SELECT count(*) FROM agent_forge_grant "
            " WHERE venture_id = %s AND activated_at IS NULL "
            "   AND grant_id = ANY(%s)",
            (ctx.venture_id, list(covered)),
        )
        row = await cur.fetchone()
        skipped = int(row[0]) if row else 0
        await cur.execute(
            "SELECT i.status, count(*) FROM agent_forge_grant g "
            "  JOIN office_agent_identity i ON i.office_agent_id = g.office_agent_id "
            " WHERE g.venture_id = %s AND g.activated_at IS NULL "
            "   AND i.status <> 'active' AND NOT (g.grant_id = ANY(%s)) "
            " GROUP BY i.status ORDER BY i.status",
            (ctx.venture_id, list(covered)),
        )
        inactive_by_status = {str(r[0]): int(r[1]) for r in await cur.fetchall()}
    await ctx.conn.commit()
    inactive = sum(inactive_by_status.values())

    scopes = sorted({c.scope for c in covered.values()})
    # Named in the reason, not only in the evidence. "49 activated" and "45 activated"
    # are the same sentence to a reader who does not already know four were withheld,
    # and this gate is the last thing between a signature and production authority.
    withheld = (
        f"; {skipped} grant(s) NOT activated - covered by a live "
        f"{'/'.join(scopes)} revocation"
        if skipped else ""
    )
    # IDENTITY STATUS - the second condition (decisions entry 85). The foreign key on
    # `office_agent_id` guarantees the identity EXISTS, not that it is active, and
    # `resolve_grant` refuses a non-active identity on every call. So, as with B53, this is
    # the record and not the authority: without it a suspended or departed agent's grant
    # carries `activated_by = <the signer>` for authority nobody could exercise.
    if inactive:
        statuses = ", ".join(f"{n} {s}" for s, n in inactive_by_status.items())
        withheld += (
            f"; {inactive} grant(s) NOT activated - agent identity not active ({statuses})"
        )
    return GateOutcome(
        "11", PASSED,
        f"{activated} grant(s) activated against signature(s) "
        f"{[s['signoff_id'][:8] for s in status.valid]}{withheld}",
        {
            "activated": activated,
            "withheld_revoked": skipped,
            "revocation_scopes": scopes,
            "withheld_inactive_identity": inactive,
            "inactive_identity_statuses": inactive_by_status,
            "artifacts_hash": current,
        },
    )


async def _gate_12(ctx: _Context) -> GateOutcome:
    async with ctx.conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            # `total` counts live grants only, so the two figures are drawn from the same
            # population. `is_assignable` is GENERATED and 0043 added `superseded_at IS
            # NULL` to it; counting retired rows in `total` alone would report them as
            # unreachable grants, which is true but is not the warning V38 is making.
            "SELECT count(*) FILTER (WHERE is_assignable) AS assignable, "
            "       count(*) AS total, "
            # Reported, not enforced. Gate 12 is a warning gate and this is a figure a
            # reader needs to interpret the other two: "10 of 10 assignable" says
            # nothing about whether those ten can be expired when the model changes.
            # `is_assignable` is GENERATED and deliberately not touched here - it
            # answers "can `resolve_grant` return this row", and the call path already
            # refuses an unattributable certification with its own error.
            "       count(*) FILTER (WHERE "
            "         EXISTS (SELECT 1 FROM certification ca "
            "                  WHERE ca.cert_id::text = g.operation_cert_ref "
            "                    AND ca.model_digest IS NOT NULL)) AS model_named "
            "FROM agent_forge_grant g "
            "WHERE venture_id = %s AND superseded_at IS NULL",
            (ctx.venture_id,),
        )
        row = await cur.fetchone()
    assert row is not None

    # V38, here rather than at Gate 2: it asks whether every grant this venture holds can
    # actually be SELECTED, and `resolve_grant` answers one row per (agent, forge,
    # module). The line below is the one it qualifies - `assignable` counts rows, and a
    # triple carrying three grants contributes three to it while exactly one is
    # reachable. A warning, not a block: nothing acts on the unreachable rows and no
    # authority changes, but the count describes more than the code can select.
    report = await validate_gate_12(ctx.pack.pack, ctx.conn)
    evidence: dict[str, Any] = {
        "assignable": int(row["assignable"]),
        "total": int(row["total"]),
        "model_named": int(row["model_named"]),
        "warnings": [r.rule_id for r in report.warnings],
        **{r.rule_id: r.message for r in report.results},
    }
    advisory = "".join(
        f" Advisory {r.rule_id}: {r.message}" for r in report.warnings
    )
    return GateOutcome(
        "12", PASSED,
        f"live: {row['assignable']} of {row['total']} grant(s) assignable, "
        f"{row['model_named']} naming the model certified; trust tiers "
        f"active, revocation armed.{advisory}",
        evidence,
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
        simforge: SimForgeClient | None = None,
        build_identity: build.BuildIdentity | None = None,
    ) -> None:
        self.conn = conn
        self.run_id = run_id
        self.venture_id = venture_id
        self.pack = pack
        self.actor = actor
        self.human_review_recorded = human_review_recorded
        self.held_out = held_out
        #: WHICH BUILD IS DOING THE SUBMITTING. Resolved once per run rather than per
        #: gate, so every gate in one pass reports the same answer, and injectable for
        #: the same reason `simforge` is: a test must be able to state a stale build
        #: without arranging a second checkout.
        self.build = build_identity if build_identity is not None else build.identity()
        #: Injected by tests and by any caller holding an open client. Gate 8 builds
        #: one on demand when this is None, so nothing above has to know the gate
        #: talks to SimForge.
        self.simforge = simforge
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
    """Begin a run against the venture's live Pack.

    One run at a time per venture, enforced by `ux_run_active`. Two concurrent runs
    would both issue grants for the same engagement, each unaware of the other's gate
    state - so the constraint is right and stays. What it must not do is surface as a
    500: a deliberate rule reported as an internal error teaches the operator that the
    system is broken when it is working.
    """
    pack = await packs.live(conn, venture_id)
    if pack is None:
        raise ProvisioningError(f"no live Pack for {venture_id}")

    active = await active_run(conn, venture_id)
    if active is not None:
        raise ProvisioningError(
            f"{venture_id} already has an active run ({str(active.run_id)[:8]}) at gate "
            f"{active.current_gate}. One run at a time per venture: two would both issue "
            "grants for this engagement, each unaware of the other. Advance it, or "
            "abandon it first."
        )

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
    simforge: SimForgeClient | None = None,
    build_identity: build.BuildIdentity | None = None,
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
        held_out or PartitionAbsent(), simforge, build_identity,
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
            # Part 6.5. A venture going live is the institutional fact a history is
            # made of, and a store nothing writes to is an inert control with a nicer
            # name - which this codebase has shipped once already.
            await knowledge.record(
                conn, record_type="venture_provisioned", venture_id=state.venture_id,
                summary=(
                    f"{state.venture_id} provisioned live from Pack "
                    f"{state.pack_version} (run {str(run_id)[:8]})."
                ),
                detail={"run_id": str(run_id), "pack_version": state.pack_version,
                        "artifacts_hash": ctx.artifacts_hash_value},
                actor_type="human", recorded_by=actor,
            )
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

    IT DOES SUPERSEDE THE RUN'S OPEN SUBMISSIONS - ruled 21 September 2026, entry 142.
    ================================================================================

        That is not the same concession. A grant is authority somebody holds and an
        abort has no standing to withdraw it. An open submission is an exam THIS RUN
        set, on a curriculum this run handed over, and abandoning the run withdraws the
        curriculum - so a verdict against it is a verdict on text nobody stands behind.

        The case that made it a ruling: 50d933e8 was abandoned for a Gate 8 that
        predated the corrected keys, its nine rows were not touched, and the verdict
        sweep ingested four PASS verdicts off them the next day. Nothing was wrong with
        the sweep. The abort had simply left the exams standing.
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

    # AFTER the status is committed, so a failure here cannot leave a run that reads
    # active with its exams already retired - the direction that produces a run nobody
    # can advance and submissions nobody will ingest.
    superseded = await supersede_run_submissions(
        conn,
        run_id=run_id,
        reason=(
            f"Provisioning run {str(run_id)[:8]} was abandoned at gate "
            f"{state.current_gate} by {human.display_name}: {reason}"
        ),
    )

    await audit.write_event(
        event_type="provisioning_run_aborted",
        actor_type="human", actor_id=human.human_id, venture_id=state.venture_id,
        subject={"run_id": str(run_id), "at_gate": state.current_gate,
                 "reason": reason,
                 # On the event, because this is the fact a later reader needs when they
                 # ask why the sweep stopped being owed a verdict on nine exams.
                 "submissions_superseded": superseded},
    )
    # An abandoned attempt is institutional memory too - arguably more of it than a
    # successful one, because the next person to provision this venture wants to know
    # what stopped the last attempt and where.
    await knowledge.record(
        conn, record_type="provisioning_abandoned", venture_id=state.venture_id,
        summary=(
            f"Provisioning run {str(run_id)[:8]} abandoned at gate "
            f"{state.current_gate}: {reason}"
        ),
        detail={"run_id": str(run_id), "at_gate": state.current_gate,
                "pack_version": state.pack_version},
        actor_type="human", recorded_by=human.human_id,
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


async def active_run(
    conn: AsyncConnection, venture_id: str
) -> RunState | None:
    """The venture's open run, if it has one. `ux_run_active` guarantees at most one."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT run_id FROM provisioning_run WHERE venture_id = %s "
            "AND status IN ('running', 'blocked', 'awaiting_human')",
            (venture_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return await get_run(conn, row["run_id"])


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


async def list_runs(
    conn: AsyncConnection,
    *,
    venture_id: str | None = None,
    include_fixtures: bool = False,
) -> dict[str, Any]:
    """Runs, newest first, with how far each got and who started it.

    104 of the 108 runs in the development database are smoke-test loops: every run of
    `scripts/console-smoke.sh` starts one, drives it to gate 4 and aborts it. A history
    that lists them alongside real runs makes "83 runs stopped at gate 4" read as a
    system in trouble rather than as a test fixture doing its job.

    Marked by the account that started the run, not by guessing at the shape - the smoke
    loop does have a shape, but a shape can be coincidental and an actor cannot. Nothing
    is deleted: a provisioning run is a record of an attempt, and filtering changes the
    view rather than the record.
    """
    from broker import account_origin

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.run_id::text AS run_id, r.venture_id, r.pack_version, r.pack_hash,
                   r.status, r.current_gate, r.artifacts_hash, r.started_at,
                   r.completed_at, r.started_by::text AS started_by,
                   h.display_name AS started_by_name, h.email AS started_by_email,
                   -- DECLARED (entry 151). This was inferred from the two columns
                   -- above until `dev-all build check` showed what that costs.
                   h.origin AS started_by_origin,
                   (SELECT count(*) FROM provisioning_gate_result g
                     WHERE g.run_id = r.run_id AND g.verdict = 'passed') AS gates_passed
            FROM provisioning_run r
            LEFT JOIN office_human h ON h.human_id = r.started_by
            WHERE (%s::text IS NULL OR r.venture_id = %s)
            ORDER BY r.started_at DESC
            """,
            (venture_id, venture_id),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    for row in rows:
        # A run whose starter is no longer an account is not a fixture run. The join is
        # a LEFT one because `started_by` outlives the row it names, and treating an
        # absent account as a fixture would hide a real run rather than a test one.
        row["fixture"] = (
            row.get("started_by_origin") is not None
            and account_origin.origin_of({"origin": row["started_by_origin"]})
            == account_origin.TEST_FIXTURE
        )

    excluded = 0
    if not include_fixtures:
        before = len(rows)
        rows = [row for row in rows if not row["fixture"]]
        excluded = before - len(rows)

    return {
        "runs": rows,
        "total": len(rows),
        "excluded_fixtures": excluded,
    }


async def sign_off_run(
    conn: AsyncConnection,
    *,
    run_id: uuid.UUID,
    human: humans.Human,
    displayed_artifacts_hash: str,
    note: str | None = None,
) -> tuple[uuid.UUID, str]:
    """Gate 10, signed against the artifacts the signer was shown.

    `humans.sign_off` takes whatever hash its caller passes, which was harmless while
    nothing consumed it. It is not harmless now: Gate 11 activates production grants
    against that hash, so a client able to choose it can sign artifacts it never
    displayed.

    So this regenerates the artifacts here and refuses unless they match what the caller
    says was on screen. The check runs in that direction deliberately - the server does
    not silently sign its own freshly computed hash, because that would be a signature
    on something the human never saw. A mismatch means the world moved between render
    and click, and the answer is to look again, not to sign harder.
    """
    state = await get_run(conn, run_id)
    if state is None:
        raise ProvisioningError(f"no such run {run_id}")
    if state.status in ("complete", "aborted"):
        raise ProvisioningError(f"run is {state.status}")

    pack = await packs.get_version(conn, state.venture_id, state.pack_version)
    if pack is None:
        raise ProvisioningError("the Pack version this run started from is gone")

    artifacts = await generator_pipeline.run_all(pack.pack, conn)
    current = artifacts_hash(artifacts)
    if current != displayed_artifacts_hash:
        raise ProvisioningError(
            "the artifacts changed since this page was rendered, so signing now would "
            f"sign something you have not seen (shown {displayed_artifacts_hash[:12]}…, "
            f"now {current[:12]}…). Reload the run and review it again."
        )

    signoff_id = await humans.sign_off(
        conn, gate="gate_10", venture_id=state.venture_id, human=human,
        artifact_kind="provisioning_artifacts", artifact_hash_value=current, note=note,
    )
    await audit.write_event(
        event_type="provisioning_gate_10_signed",
        actor_type="human", actor_id=human.human_id, venture_id=state.venture_id,
        subject={"run_id": str(run_id), "signoff_id": str(signoff_id),
                 "artifacts_hash": current},
    )
    return signoff_id, current


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


async def reject_run(
    conn: AsyncConnection, *, run_id: uuid.UUID, human: humans.Human, reason: str
) -> None:
    """A named human declines at a gate that was waiting for their decision.

    Distinct from `abort_run`, and the distinction is the point. Aborting abandons a run
    and says nothing about the artifacts; rejecting is a judgement about them. The next
    person to provision this venture wants to know which one happened, and a single
    `aborted` status cannot tell them.

    Only possible while a gate is `awaiting_human`. Rejecting a run that no gate has
    handed to a human would be a way to stop it mid-flight while dressing it as a review
    - and stopping a run mid-flight is what `abort_run` is for.

    Does **not** deactivate grants, for the same reason an abort does not: Gate 11 may
    already have activated them, and a rejection is not a revocation.
    """
    if not reason.strip():
        raise ProvisioningError("rejecting a run requires a reason")

    state = await get_run(conn, run_id)
    if state is None:
        raise ProvisioningError(f"no such run {run_id}")
    if state.status != AWAITING_HUMAN:
        raise ProvisioningError(
            f"run is {state.status}, not awaiting a human decision. Nothing has been "
            "put to a human to accept or decline; abandon the run instead."
        )
    humans.authorize(human, required_role="venture_operator", venture_id=state.venture_id)

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET status = 'rejected', completed_at = now() "
            "WHERE run_id = %s",
            (run_id,),
        )
    await conn.commit()

    await audit.write_event(
        event_type="provisioning_run_rejected",
        actor_type="human", actor_id=human.human_id, venture_id=state.venture_id,
        subject={"run_id": str(run_id), "at_gate": state.current_gate,
                 "reason": reason},
    )
    await knowledge.record(
        conn, record_type="provisioning_rejected", venture_id=state.venture_id,
        summary=(
            f"Provisioning run {str(run_id)[:8]} rejected at gate "
            f"{state.current_gate}: {reason}"
        ),
        detail={"run_id": str(run_id), "at_gate": state.current_gate,
                "reason": reason},
        actor_type="human", recorded_by=human.human_id,
    )


# ----------------------------------------------------------------- the directory

# The plain-language name of each gate. `GATE_TITLES` describes what the gate *checks*,
# in the vocabulary of the spec that defined it - "Human review of artifacts, BOM and
# appointment gap report". That belongs on the gate row where there is room for it; a
# sixteen-row ladder needs a name a reader can scan.
GATE_NAMES = {
    "0": "Bridge operational",
    "1": "Pack authored",
    "2": "Pack validated",
    "3": "Generators ran",
    "3.5": "Manifest reconciled",
    "4": "Human review",
    "4.5": "Capacity and budget check",
    "5": "Sandbox grants issued",
    "6": "Knowledge bases seeded",
    "7": "Agents appointed, paused",
    "8": "Curriculum to SimForge",
    "9": "Readiness Gate",
    "9.5": "Held-out set",
    "10": "Named-human sign-off",
    "11": "Production grants",
    "12": "Live",
}

# One line per gate on what it does. A pending gate that shows only a name tells a
# reader nothing about what is still ahead of the run; with these the ladder doubles as
# documentation of the pipeline, which is what makes it worth rendering on a venture that
# has never been provisioned at all.
GATE_DESCRIPTIONS = {
    "0": "Checks the bridge reaches every Forge the Pack depends on.",
    "1": "Confirms a Pack is authored and live for this venture.",
    "2": "Runs the full validator. Any FAIL stops the run here.",
    "3": "Generates positions, workflow, task ledger, curriculum and manifest.",
    "3.5": "Reconciles the generated manifest against what each Forge declares.",
    "4": "Waits for a named human to review the artifacts and record what they read.",
    "4.5": "Re-checks capacity and budget against the generated ledger.",
    "5": "Issues sandbox grants, scoped to the modules each position operates.",
    "6": "Seeds knowledge bases and indexes the operating instructions.",
    "7": "Registers the engagement and appoints agents with grants still inactive.",
    "8": "Submits the curriculum to SimForge for scenario training.",
    "9": "Runs the readiness gate per role per domain.",
    "9.5": "Runs the held-out adversarial set. No deployment can pass this yet.",
    "10": "Takes a named human signature bound to the artifact hashes.",
    "11": "Activates production grants against the signed artifacts.",
    "12": "Venture is live, tiers active, revocation armed.",
}

# The gate this deployment cannot pass, and the evidence that says so. A block at 9.5 is
# only the ceiling when the partition does not exist; a held-out verdict of FAIL is a
# real failure at the same gate, and reading the two the same way would report a venture
# that failed adversarial testing as merely waiting for infrastructure.
CEILING_GATE = "9.5"
CEILING_EVIDENCE = "held_out_partition_not_created"


def display_status(
    status: str, current_gate: str, blocking: dict[str, Any] | None
) -> str:
    """What actually happened, in words a reader can act on.

    `aborted` reads as though somebody cancelled it - which is what it means, and what it
    fails to distinguish from a gate refusing. The stored status is the machine's
    vocabulary; this is the reader's.
    """
    if status == "complete":
        return "complete"
    if status == "running":
        return f"running at gate {current_gate}"
    if status == AWAITING_HUMAN:
        return f"awaiting review at gate {current_gate}"
    if status == "aborted":
        return "cancelled"
    if status == "rejected":
        return f"rejected at gate {current_gate}"

    evidence = (blocking or {}).get("evidence") or {}
    if current_gate == CEILING_GATE and evidence.get("blocked_by") == CEILING_EVIDENCE:
        # Not a failure. A run here has done everything this deployment can do, and
        # rendering it as broken would misreport a successful run.
        return "at ceiling"
    if evidence.get("error"):
        return f"failed at gate {current_gate}"
    return f"stopped at gate {current_gate}"


def ladder_for(
    results: list[dict[str, Any]], current_gate: str | None, status: str | None
) -> list[dict[str, Any]]:
    """Every gate, in order, whether or not it ran.

    A ladder that lists only what has happened cannot show what is still ahead of a
    stopped run - which is most of the reason to draw one.
    """
    latest: dict[str, dict[str, Any]] = {}
    for row in results:
        latest[row["gate"]] = row

    # Elapsed per gate, measured from the previous gate's record, so a slow gate is
    # visible rather than inferred from a total.
    ordered = sorted(
        (r for r in results if r.get("recorded_at")), key=lambda r: r["recorded_at"]
    )
    previous: dict[str, Any] = {}
    seconds: dict[str, float] = {}
    for row in ordered:
        prior = previous.get("recorded_at")
        if prior is not None:
            seconds[row["gate"]] = (row["recorded_at"] - prior).total_seconds()
        previous = row

    live = status in ("running", AWAITING_HUMAN)
    reached = False
    ladder: list[dict[str, Any]] = []
    for gate in GATE_SEQUENCE:
        record = latest.get(gate)
        is_current = gate == current_gate
        if is_current:
            reached = True

        if record and record["verdict"] == PASSED:
            state = "passed"
        elif record and record["verdict"] == BLOCKED:
            state = "blocked"
        elif record and record["verdict"] == AWAITING_HUMAN:
            state = "awaiting"
        elif is_current and live:
            state = "running"
        else:
            state = "pending"

        ladder.append({
            "gate": gate,
            "name": GATE_NAMES[gate],
            "title": GATE_TITLES[gate],
            "description": GATE_DESCRIPTIONS[gate],
            "state": state,
            "reason": None if record is None else record["reason"],
            "evidence": {} if record is None else (record["evidence"] or {}),
            "recorded_at": None if record is None
                           else record["recorded_at"].isoformat(),
            "seconds": seconds.get(gate),
            "is_current": is_current,
            "is_ceiling": gate == CEILING_GATE,
            # Everything past the gate a run stopped at never ran, and saying so is the
            # difference between "not yet" and "we do not know".
            "downstream_of_stop": reached and not is_current and not live,
        })
    return ladder


# A run a human ended does not have its reason in `provisioning_gate_result`. The gate
# recorded why it was *waiting*; the human recorded why they stopped it, and that went to
# the audit log. Rendering the gate's message for a cancelled run answers "why did this
# stop" with the generic sentence the gate says to everybody - which is exactly what the
# stop block exists not to do.
_TERMINAL_EVENTS = {
    "aborted": "provisioning_run_aborted",
    "rejected": "provisioning_run_rejected",
}


async def human_disposition(
    conn: AsyncConnection, run_id: str, status: str
) -> dict[str, Any] | None:
    """Who ended this run, when, and why they said they did."""
    event_type = _TERMINAL_EVENTS.get(status)
    if event_type is None:
        return None

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT a.subject, a.ts, h.display_name AS actor
            FROM audit_log a
            LEFT JOIN office_human h ON h.human_id = a.actor_id
            WHERE a.event_type = %s AND a.subject->>'run_id' = %s
            ORDER BY a.ts DESC
            LIMIT 1
            """,
            (event_type, run_id),
        )
        row = await cur.fetchone()

    if row is None:
        return None
    subject = row["subject"] or {}
    return {
        "actor": row["actor"],
        "at": row["ts"].isoformat(),
        "reason": subject.get("reason"),
        "gate": subject.get("at_gate"),
    }


async def directory(conn: AsyncConnection) -> dict[str, Any]:
    """Every venture that could be provisioned, and exactly how far it got.

    The old index rendered `5 of 16` - a number with no map. A fraction cannot say which
    gate stopped the run, what happened there, or what is still ahead, and those are the
    three things a reader opens this page to find out.
    """
    from broker import ventures as ventures_mod

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT DISTINCT ON (r.venture_id)
                   r.run_id::text AS run_id, r.venture_id, r.pack_version, r.pack_hash,
                   r.status, r.current_gate, r.artifacts_hash, r.started_at,
                   r.completed_at, r.started_by::text AS started_by
            FROM provisioning_run r
            ORDER BY r.venture_id, r.started_at DESC
            """
        )
        latest_runs = {r["venture_id"]: dict(r) for r in await cur.fetchall()}

        await cur.execute(
            "SELECT venture_id, count(*) AS runs FROM provisioning_run "
            "GROUP BY venture_id"
        )
        run_counts = {r["venture_id"]: int(r["runs"]) for r in await cur.fetchall()}

        await cur.execute(
            "SELECT venture_id, pack_version, content_hash, parsed "
            "FROM business_pack WHERE status = 'live' ORDER BY venture_id"
        )
        live_packs = {r["venture_id"]: dict(r) for r in await cur.fetchall()}

        await cur.execute("SELECT slug, display_name FROM venture")
        registered = {r["slug"]: r["display_name"] for r in await cur.fetchall()}

        await cur.execute(
            "SELECT human_id::text AS human_id, display_name FROM office_human"
        )
        actors = {r["human_id"]: r["display_name"] for r in await cur.fetchall()}

    out: list[dict[str, Any]] = []
    for venture_id in sorted(set(latest_runs) | set(live_packs)):
        run = latest_runs.get(venture_id)
        pack = live_packs.get(venture_id)

        results = (
            [] if run is None else await gate_results(conn, uuid.UUID(run["run_id"]))
        )
        blocking = None
        if run is not None:
            for row in results:
                if row["gate"] == run["current_gate"] and row["verdict"] != PASSED:
                    blocking = row

        display = (
            None if run is None
            else display_status(run["status"], run["current_gate"], blocking)
        )
        disposition = (
            None if run is None
            else await human_disposition(conn, run["run_id"], run["status"])
        )
        ladder = ladder_for(
            results,
            None if run is None else run["current_gate"],
            None if run is None else run["status"],
        )

        # Resume is `advance` from where the run stopped. It is unavailable when the
        # document changed underneath it: the run holds the Pack hash it began with, and
        # resuming against different content would provision something nobody started.
        pack_changed = bool(
            run is not None and pack is not None
            and run["pack_version"] == pack["pack_version"]
            and run["pack_hash"] != pack["content_hash"]
        )
        superseded = bool(
            run is not None and pack is not None
            and run["pack_version"] != pack["pack_version"]
        )
        resumable = bool(run is not None and run["status"] == BLOCKED)
        because = None
        if run is not None and run["status"] in ("complete", "aborted", "rejected"):
            because = f"This run is {display}. Start a fresh run."
        elif pack_changed:
            resumable = False
            because = "Pack has changed since this run. Start a fresh run."
        elif superseded:
            resumable = False
            live_version = "" if pack is None else pack["pack_version"]
            ran_against = "" if run is None else run["pack_version"]
            because = (
                f"This run provisioned Pack {ran_against} and {live_version} is now "
                "live. Start a fresh run."
            )

        identity = ((pack or {}).get("parsed") or {}).get("identity") or {}
        out.append({
            "venture_id": venture_id,
            "display_name": (
                registered.get(venture_id)
                or identity.get("venture_name")
                or venture_id
            ),
            "has_live_pack": pack is not None,
            "live_pack_version": None if pack is None else pack["pack_version"],
            "run": None if run is None else {
                "run_id": run["run_id"],
                "status": run["status"],
                "display_status": display,
                "current_gate": run["current_gate"],
                "current_gate_name": GATE_NAMES[run["current_gate"]],
                "pack_version": run["pack_version"],
                "started_at": run["started_at"].isoformat(),
                "completed_at": (
                    None if run["completed_at"] is None
                    else run["completed_at"].isoformat()
                ),
                "started_by": actors.get(run["started_by"]),
                "gates_passed": sum(1 for g in ladder if g["state"] == "passed"),
                # A human ending a run overrides the gate's own message: the gate said
                # why it was waiting, the human said why they stopped it, and only the
                # second answers the question the block is asking.
                "stop": None if (blocking is None and disposition is None) else {
                    "gate": (
                        (disposition or {}).get("gate")
                        or (blocking or {})["gate"]
                    ),
                    "name": GATE_NAMES[
                        (disposition or {}).get("gate") or (blocking or {})["gate"]
                    ],
                    "reason": (
                        (disposition or {}).get("reason")
                        or (blocking or {}).get("reason")
                        or ""
                    ),
                    "evidence": (blocking or {}).get("evidence") or {},
                    "at": (
                        (disposition or {}).get("at")
                        or (
                            blocking["recorded_at"].isoformat()
                            if blocking is not None else None
                        )
                    ),
                    # Who acted at the gate. Not who started the run - for a run somebody
                    # ended, those are different people and the second is the wrong one.
                    "actor": (disposition or {}).get("actor"),
                },
            },
            "ladder": ladder,
            "runs_total": run_counts.get(venture_id, 0),
            "resumable": resumable,
            "resume_blocked_because": because,
            "pack_changed": pack_changed or superseded,
        })

    return {
        "ventures": out,
        "startable": [
            {"venture_id": row["venture_id"], "display_name": row["display_name"]}
            for row in out if row["has_live_pack"]
        ],
        "gates_total": len(GATE_SEQUENCE),
        "gate_names": GATE_NAMES,
        "ceiling_gate": CEILING_GATE,
        "portfolio_size": len(ventures_mod.PORTFOLIO),
        # The ladder as it looks before anything has run. The empty state renders this
        # rather than a blank card: what a run *will* do is more use than nothing.
        "empty_ladder": ladder_for([], None, None),
    }


async def venture_history(
    conn: AsyncConnection, venture_id: str
) -> list[dict[str, Any]]:
    """Every run for a venture, newest first.

    Provisioning is iterative. Showing only the latest run hides the pattern - the same
    gate failing four times is a different problem from four different gates failing
    once, and an index showing one run cannot tell them apart.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.run_id::text AS run_id, r.status, r.current_gate, r.pack_version,
                   r.started_at, r.completed_at, r.started_by::text AS started_by,
                   h.display_name AS actor,
                   (SELECT count(*) FROM provisioning_gate_result g
                     WHERE g.run_id = r.run_id AND g.verdict = 'passed') AS gates_passed
            FROM provisioning_run r
            LEFT JOIN office_human h ON h.human_id = r.started_by
            WHERE r.venture_id = %s
            ORDER BY r.started_at DESC
            """,
            (venture_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    out: list[dict[str, Any]] = []
    for row in rows:
        results = await gate_results(conn, uuid.UUID(row["run_id"]))
        blocking = next(
            (
                r for r in results
                if r["gate"] == row["current_gate"] and r["verdict"] != PASSED
            ),
            None,
        )
        out.append({
            **row,
            "started_at": row["started_at"].isoformat(),
            "completed_at": (
                None if row["completed_at"] is None
                else row["completed_at"].isoformat()
            ),
            "gates_passed": int(row["gates_passed"]),
            "current_gate_name": GATE_NAMES[row["current_gate"]],
            "display_status": display_status(
                row["status"], row["current_gate"], blocking
            ),
            "reason": None if blocking is None else blocking["reason"],
        })
    return out
