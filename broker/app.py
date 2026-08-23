"""The Operations API — what the console is a view over.

Master prompt Part 17. The console's fourteen screens are views over these routes.

**This is the most dangerous file in the repository to write carelessly**, and the
danger is not obvious: every control built so far lives in a guarded function.
Revocation checks authority. A disposition demands a reason. `assign_shift` refuses an
unflushed predecessor. Certification is a live state, not a column somebody sets.

An API that reached past those functions to the tables would undo all of it — and it
would look like a feature while doing so. "Let the operator fix the certification state"
is a reasonable-sounding request that removes the entire certification gate.

So two rules, and both are tested:

  1. **Every write calls the same guarded function the domain uses.** There is no raw
     `UPDATE` in this file. No second path to a table.
  2. **Routes that must not exist, do not exist.** Nothing writes a certification state,
     clears a flush, assigns a shift past the flush check, edits the ledger or the audit
     log, or grants a tier above its certified ceiling.
     `test_the_api_is_not_a_bypass` enumerates them and fails if one appears.

The console is a client of The Office, not a back door into it.

Authorisation asks two questions on every write, because a role string alone can only
answer the first: is this role strong enough, and is this person an operator of *this
venture*. See `broker/humans.authorize`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from broker import (
    audit,
    budget,
    certification,
    humans,
    instructions,
    proposals,
    revocation,
    sweeps,
)
from broker.db import close_pool, connection
from broker.errors import NotAuthorized, OfficeError
from broker.humans import Human


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_pool()


app = FastAPI(
    title="The Office — Operations API",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "The console is a view over these routes. Every write delegates to a guarded "
        "domain function; nothing here reaches past one to a table."
    ),
)


@app.exception_handler(OfficeError)
async def _office_error(_request: Request, exc: OfficeError) -> JSONResponse:
    """Domain refusals keep their own status and their own reason.

    Flattening every refusal to 403 would erase the difference between "you lack the
    role", "the budget is spent" and "the agent is on shift for another venture" -
    three different things for an operator to do next.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": type(exc).__name__, "message": exc.message, **exc.context},
    )


async def db() -> AsyncIterator[AsyncConnection]:
    async with connection() as conn:
        yield conn


DB = Annotated[AsyncConnection, Depends(db)]


async def current_human(
    conn: DB, authorization: Annotated[str | None, Header()] = None
) -> Human:
    """Resolve the bearer token. Status is read live, never trusted from the token.

    A suspended human is refused on their next request rather than their next session -
    the same rule agent revocation follows, for the same reason.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="bearer token required")
    human = await humans.authenticate(conn, authorization.split(" ", 1)[1])
    if human is None:
        raise HTTPException(status_code=401, detail="unknown token")
    if not human.is_active:
        raise HTTPException(status_code=403, detail=f"human is {human.status}")
    return human


ME = Annotated[Human, Depends(current_human)]


async def _audit_human_action(
    human: Human, event_type: str, subject: dict[str, Any], venture_id: str | None = None
) -> None:
    """Part 9: humans sign, not agents. Every write records who did it."""
    await audit.write_event(
        event_type=event_type,
        actor_type="human",
        actor_id=human.human_id,
        venture_id=venture_id,
        subject={"human": human.display_name, **subject},
    )


# =============================================================== read: health

@app.get("/api/health")
async def health(conn: DB, _me: ME) -> dict[str, Any]:
    """Control freshness. `never_run` and `stale` are not healthy."""
    report = await sweeps.freshness(conn)
    return {
        "controls": report,
        "healthy": all(v["healthy"] for v in report.values()),
        "unhealthy": sorted(k for k, v in report.items() if not v["healthy"]),
    }


@app.get("/api/audit/chain")
async def audit_chain(conn: DB, _me: ME) -> dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT ok, checked_count, first_break_audit_id, tail_gap, reason "
            "FROM audit_log_verify_chain()"
        )
        row = await cur.fetchone()
    assert row is not None
    return dict(row)


# =============================================================== read: agents

@app.get("/api/agents")
async def list_agents(conn: DB, _me: ME) -> list[dict[str, Any]]:
    """Agent Registry — certified tier beside declared tier (Part 17).

    Shown side by side because Part 10.1 says the certified tier caps the declared one,
    and a screen that showed only one of them would hide every place they disagree.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT i.office_agent_id, i.agent_name, i.department, i.status,
                   count(DISTINCT g.grant_id) FILTER (WHERE g.revoked_at IS NULL)
                     AS live_grants,
                   count(DISTINCT c.cert_id) FILTER (WHERE c.state = 'certified')
                     AS certifications,
                   array_remove(array_agg(DISTINCT c.state), NULL) AS cert_states,
                   min(g.trust_tier)  AS declared_tier_floor,
                   min(c.certified_tier) FILTER (WHERE c.state = 'certified')
                     AS certified_tier_floor
            FROM office_agent_identity i
            LEFT JOIN agent_forge_grant g ON g.office_agent_id = i.office_agent_id
            LEFT JOIN certification c
                   ON c.unit = 'A' AND c.office_agent_id = i.office_agent_id
            GROUP BY i.office_agent_id, i.agent_name, i.department, i.status
            ORDER BY i.agent_name
            """
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/agents/{office_agent_id}")
async def agent_detail(office_agent_id: uuid.UUID, conn: DB, _me: ME) -> dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM office_agent_identity WHERE office_agent_id = %s",
            (office_agent_id,),
        )
        identity = await cur.fetchone()
        if identity is None:
            raise HTTPException(status_code=404, detail="no such agent")

        await cur.execute(
            """
            SELECT g.grant_id, g.forge_id, g.module_id, g.venture_id, g.trust_tier,
                   g.is_assignable, g.revoked_at,
                   ca.state AS unit_a_state, ca.certified_tier
            FROM agent_forge_grant g
            LEFT JOIN certification ca
                   ON ca.unit = 'A' AND ca.office_agent_id = g.office_agent_id
                  AND ca.forge_id = g.forge_id AND ca.module_id = g.module_id
            WHERE g.office_agent_id = %s
            ORDER BY g.forge_id, g.module_id
            """,
            (office_agent_id,),
        )
        grants = [dict(r) for r in await cur.fetchall()]

        # Migration status per Forge (§1.6). It changes the strength of the audit
        # guarantee for that Forge, so an operator has to be able to see it.
        await cur.execute(
            "SELECT forge_id, credential_mode, health_status FROM forge_registry "
            "ORDER BY forge_id"
        )
        forges = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            "SELECT shift_id, venture_id, shift_start, shift_end, flush_verified "
            "FROM shift_assignment WHERE office_agent_id = %s "
            "ORDER BY shift_start DESC LIMIT 5",
            (office_agent_id,),
        )
        shifts_recent = [dict(r) for r in await cur.fetchall()]

    return {
        "identity": dict(identity),
        "grants": grants,
        "forge_migration_status": forges,
        "recent_shifts": shifts_recent,
    }


# ============================================================== read: ventures

@app.get("/api/ventures")
async def list_ventures(conn: DB, _me: ME) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT v.venture_id,
                   count(DISTINCT g.office_agent_id) AS agents,
                   count(DISTINCT g.grant_id) FILTER (WHERE g.revoked_at IS NULL)
                     AS live_grants,
                   b.monthly_usd_cap, b.hard_cap_reversed_at
            FROM (SELECT DISTINCT venture_id FROM agent_forge_grant
                  UNION SELECT DISTINCT venture_id FROM venture_forge_manifest
                  UNION SELECT venture_id FROM venture_budget) v
            LEFT JOIN agent_forge_grant g ON g.venture_id = v.venture_id
            LEFT JOIN venture_budget b ON b.venture_id = v.venture_id
            GROUP BY v.venture_id, b.monthly_usd_cap, b.hard_cap_reversed_at
            ORDER BY v.venture_id
            """
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/ventures/{venture_id}/capacity")
async def venture_capacity(venture_id: str, conn: DB, _me: ME) -> dict[str, Any]:
    """The three numbers (§7.2). All three, always — one hides the state."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
              count(*) FILTER (WHERE certified AND NOT allocated) AS certified_and_free,
              count(*) FILTER (WHERE certified AND allocated)     AS certified_but_allocated,
              count(*) FILTER (WHERE NOT certified)               AS produced_not_yet_certified
            FROM (
              SELECT i.office_agent_id,
                     bool_or(c.state = 'certified')                       AS certified,
                     bool_or(s.venture_id IS NOT NULL
                             AND s.venture_id <> %(venture)s)             AS allocated
              FROM office_agent_identity i
              LEFT JOIN certification c
                     ON c.unit = 'A' AND c.office_agent_id = i.office_agent_id
              LEFT JOIN shift_assignment s
                     ON s.office_agent_id = i.office_agent_id
                    AND s.shift_start <= now() AND s.shift_end > now()
              WHERE i.status = 'active'
              GROUP BY i.office_agent_id
            ) x
            """,
            {"venture": venture_id},
        )
        row = await cur.fetchone()
    assert row is not None
    numbers = dict(row)
    return {
        "venture_id": venture_id,
        **numbers,
        "total_considered": sum(int(v) for v in numbers.values()),
        "note": (
            "All three are reported because one hides the state: free alone looks like "
            "a hiring problem, allocated makes it a scheduling problem, uncertified "
            "makes it a SimForge backlog."
        ),
    }


@app.get("/api/ventures/{venture_id}/forge-map")
async def forge_map(venture_id: str, conn: DB, _me: ME) -> dict[str, Any]:
    """Forge Map (Part 15): Declared, Required, In-Use, and the reconciliation diff."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT m.forge_id, m.module_id, m.is_required, m.criticality, m.module_gap,
                   COALESCE(u.calls, 0) AS calls_30d
            FROM venture_forge_manifest m
            LEFT JOIN (
              SELECT forge_id, module_id, count(*) AS calls
              FROM agent_call_ledger
              WHERE venture_id = %(venture)s AND ts_start > now() - interval '30 days'
              GROUP BY forge_id, module_id
            ) u ON u.forge_id = m.forge_id AND u.module_id = m.module_id
            WHERE m.venture_id = %(venture)s
            ORDER BY m.forge_id, m.module_id
            """,
            {"venture": venture_id},
        )
        declared = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            "SELECT forge_id, module_id, disposition, call_count, reason "
            "FROM manifest_disposition WHERE venture_id = %s "
            "ORDER BY disposition, forge_id, module_id",
            (venture_id,),
        )
        dispositions = [dict(r) for r in await cur.fetchall()]

    return {
        "venture_id": venture_id,
        "declared": declared,
        "declared_not_used": [d for d in declared if d["calls_30d"] == 0],
        "dispositions": dispositions,
        "pending_dispositions": [
            d for d in dispositions if d["disposition"] == "pending"
        ],
    }


@app.get("/api/ventures/{venture_id}/gates")
async def gates(venture_id: str, conn: DB, _me: ME) -> dict[str, Any]:
    """Readiness Gate view — what stands between this venture and production."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT count(*) AS pending FROM manifest_disposition "
            "WHERE venture_id = %s AND disposition = 'pending'",
            (venture_id,),
        )
        pending = await cur.fetchone()
        await cur.execute(
            "SELECT gate, count(*) AS signatures FROM signoff_record "
            "WHERE venture_id = %s GROUP BY gate ORDER BY gate",
            (venture_id,),
        )
        signoffs = [dict(r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT count(*) AS unassignable FROM agent_forge_grant "
            "WHERE venture_id = %s AND revoked_at IS NULL AND NOT is_assignable",
            (venture_id,),
        )
        unassignable = await cur.fetchone()

    return {
        "venture_id": venture_id,
        "gate_15_pending_dispositions": int(pending["pending"]) if pending else 0,
        "signoffs": signoffs,
        "unassignable_grants": int(unassignable["unassignable"]) if unassignable else 0,
    }


# ================================================================ read: audit

@app.get("/api/audit")
async def audit_explorer(
    conn: DB,
    _me: ME,
    event_type: Annotated[str | None, Query()] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    venture_id: Annotated[str | None, Query()] = None,
    trace_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    """Audit Log Explorer. Read-only, and there is no route that writes here."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT audit_id, event_type, actor_type, actor_id, venture_id, subject,
                   trace_id, ts, entry_hash
            FROM audit_log
            WHERE (%(event_type)s::text IS NULL OR event_type = %(event_type)s)
              AND (%(actor_id)s::uuid IS NULL OR actor_id = %(actor_id)s)
              AND (%(venture_id)s::text IS NULL OR venture_id = %(venture_id)s)
              AND (%(trace_id)s::uuid IS NULL OR trace_id = %(trace_id)s)
            ORDER BY audit_id DESC LIMIT %(limit)s
            """,
            {
                "event_type": event_type, "actor_id": actor_id,
                "venture_id": venture_id, "trace_id": trace_id, "limit": limit,
            },
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/incidents")
async def list_incidents(
    conn: DB,
    _me: ME,
    severity: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM incident "
            "WHERE (%s::text IS NULL OR severity = %s) "
            "ORDER BY raised_at DESC LIMIT %s",
            (severity, severity, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/proposals")
async def list_proposals(
    conn: DB,
    _me: ME,
    status: Annotated[str, Query()] = "pending",
    venture_id: Annotated[str | None, Query()] = None,
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT proposal_id, office_agent_id, venture_id, forge_id, module_id, "
            "       task_id, trust_tier, payload, status, created_at, review_seconds "
            "FROM proposal WHERE status = %s "
            "  AND (%s::text IS NULL OR venture_id = %s) "
            "ORDER BY created_at",
            (status, venture_id, venture_id),
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/dispositions")
async def list_dispositions(conn: DB, _me: ME) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM manifest_disposition ORDER BY disposition, venture_id"
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/instructions/{forge_id}/{module_id}")
async def instruction_detail(
    forge_id: str, module_id: str, conn: DB, _me: ME
) -> dict[str, Any]:
    """Forge Operating Instructions authoring view: current, versions, staleness."""
    live = await instructions.live(conn, forge_id=forge_id, module_id=module_id)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT instruction_version, forge_api_version, version_sensitivity, "
            "       content_hash, authored_by, authored_at, superseded_at "
            "FROM forge_operating_instruction WHERE forge_id = %s AND module_id = %s "
            "ORDER BY authored_at DESC",
            (forge_id, module_id),
        )
        versions = [dict(r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT state, count(*) FROM certification "
            "WHERE forge_id = %s AND module_id = %s GROUP BY state",
            (forge_id, module_id),
        )
        cert_states = {r["state"]: int(r["count"]) for r in await cur.fetchall()}

    return {
        "forge_id": forge_id,
        "module_id": module_id,
        "live": None if live is None else {
            "instruction_version": live.instruction_version,
            "forge_api_version": live.forge_api_version,
            "version_sensitivity": live.version_sensitivity,
            "content_hash": live.content_hash,
            "content": live.content,
        },
        "versions": versions,
        "certification_states": cert_states,
    }


# ============================================================== write: actions

class RevokeRequest(BaseModel):
    scope: str
    reason: str = Field(min_length=1)
    office_agent_id: uuid.UUID | None = None
    forge_id: str | None = None
    module_id: str | None = None
    venture_id: str | None = None


@app.post("/api/revocations", status_code=201)
async def create_revocation(body: RevokeRequest, conn: DB, me: ME) -> dict[str, str]:
    """The kill switch. Authority is checked twice, and both checks matter.

    `revocation.assert_authority` (inside `revoke`) answers "is this role strong enough
    for this scope". `humans.authorize` answers "is this person an operator of this
    venture". A role string alone cannot answer the second.
    """
    required = revocation.SCOPE_MIN_ROLE.get(body.scope)
    if required is None:
        raise HTTPException(status_code=400, detail=f"unknown scope {body.scope!r}")

    role = humans.authorize(me, required_role=required, venture_id=body.venture_id)

    revocation_id = await revocation.revoke(
        conn,
        scope=body.scope,
        reason=body.reason,
        revoked_by=me.human_id,
        revoked_by_role=role,
        office_agent_id=body.office_agent_id,
        forge_id=body.forge_id,
        module_id=body.module_id,
        venture_id=body.venture_id,
    )
    await _audit_human_action(
        me, "console_revocation_created",
        {"revocation_id": str(revocation_id), "scope": body.scope, "reason": body.reason},
        body.venture_id,
    )
    return {"revocation_id": str(revocation_id)}


class ReinstateRequest(BaseModel):
    reason: str = Field(min_length=1)


@app.post("/api/revocations/{revocation_id}/reinstate")
async def reinstate(
    revocation_id: uuid.UUID, body: ReinstateRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Reinstatement needs the same authority as the revocation it lifts.

    Otherwise a venture operator could undo a compliance officer's venture-wide stop,
    which would make the authority matrix decorative.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT scope, venture_id FROM revocation WHERE revocation_id = %s",
            (revocation_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such revocation")

    required = revocation.SCOPE_MIN_ROLE[row["scope"]]
    role = humans.authorize(me, required_role=required, venture_id=row["venture_id"])

    await revocation.reinstate(
        conn, revocation_id=revocation_id, reinstated_by=me.human_id,
        reinstated_by_role=role, reason=body.reason,
    )
    await _audit_human_action(
        me, "console_revocation_reinstated",
        {"revocation_id": str(revocation_id), "reason": body.reason}, row["venture_id"],
    )
    return {"status": "reinstated"}


class DecideRequest(BaseModel):
    approve: bool
    reason: str | None = None


@app.post("/api/proposals/{proposal_id}/decide")
async def decide_proposal(
    proposal_id: uuid.UUID, body: DecideRequest, conn: DB, me: ME
) -> dict[str, str]:
    row = await proposals.get(conn, proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no such proposal")
    humans.authorize(me, required_role="venture_operator", venture_id=row["venture_id"])

    try:
        decided = await proposals.decide(
            conn, proposal_id=proposal_id, approve=body.approve,
            decided_by=me.human_id, reason=body.reason,
        )
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_proposal_decided",
        {"proposal_id": str(proposal_id), "status": decided.status},
        row["venture_id"],
    )
    return {"status": decided.status}


class DispositionRequest(BaseModel):
    venture_id: str
    forge_id: str
    module_id: str
    resolution: str
    reason: str = Field(min_length=1)


@app.post("/api/dispositions/resolve")
async def resolve_disposition(
    body: DispositionRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Gate 15. Requires compliance_officer: an undeclared Forge call is a compliance
    finding, not an operational preference."""
    humans.authorize(me, required_role="compliance_officer", venture_id=body.venture_id)
    try:
        await sweeps.disposition(
            conn, venture_id=body.venture_id, forge_id=body.forge_id,
            module_id=body.module_id, resolution=body.resolution,
            resolved_by=me.human_id, reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_disposition_resolved",
        {"module_id": body.module_id, "resolution": body.resolution,
         "reason": body.reason},
        body.venture_id,
    )
    return {"status": body.resolution}


class InstructionRequest(BaseModel):
    forge_id: str
    module_id: str
    instruction_version: str
    forge_api_version: str
    content: dict[str, Any]
    version_sensitivity: str = "major.minor"
    sensitivity_rationale: str | None = None


@app.post("/api/instructions", status_code=201)
async def author_instruction(
    body: InstructionRequest, conn: DB, me: ME
) -> dict[str, Any]:
    """Authoring supersedes the live set, which flips affected certifications stale.

    That is not a side effect to hide from the author - it is the consequence, and the
    response says how many certifications it just invalidated.
    """
    humans.authorize(me, required_role="venture_operator")
    try:
        written = await instructions.author(
            conn, forge_id=body.forge_id, module_id=body.module_id,
            instruction_version=body.instruction_version,
            forge_api_version=body.forge_api_version,
            content=body.content, authored_by=me.human_id,
            version_sensitivity=body.version_sensitivity,
            sensitivity_rationale=body.sensitivity_rationale,
        )
    except instructions.InstructionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stale = await certification.recompute_staleness(
        conn, forge_id=body.forge_id, module_id=body.module_id
    )
    await _audit_human_action(
        me, "console_instruction_authored",
        {"forge_id": body.forge_id, "module_id": body.module_id,
         "content_hash": written.content_hash, "certifications_invalidated": len(stale)},
    )
    return {
        "content_hash": written.content_hash,
        "certifications_invalidated": len(stale),
        "note": (
            "Certifications earned against the previous text are now stale_instructions "
            "and their agents are no longer assignable for this module."
        ),
    }


class ReverseCapRequest(BaseModel):
    reason: str = Field(min_length=1)


@app.post("/api/ventures/{venture_id}/reverse-hard-cap")
async def reverse_hard_cap(
    venture_id: str, body: ReverseCapRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Part 12: hard-cap reversal is Ivan-only."""
    role = humans.authorize(me, required_role="ivan", venture_id=venture_id)
    await budget.reverse_hard_cap(
        conn, venture_id=venture_id, actor_id=me.human_id, actor_role=role
    )
    await _audit_human_action(
        me, "console_hard_cap_reversed", {"reason": body.reason}, venture_id
    )
    return {"status": "reversed"}


class SignoffRequest(BaseModel):
    gate: str
    venture_id: str
    artifact_kind: str
    artifact_hash: str
    required_role: str = "venture_operator"
    distinct_humans: bool = True
    note: str | None = None


@app.post("/api/signoffs", status_code=201)
async def create_signoff(body: SignoffRequest, conn: DB, me: ME) -> dict[str, str]:
    """Gate sign-off, bound to the artifact hash. Part 14."""
    signoff_id = await humans.sign_off(
        conn, gate=body.gate, venture_id=body.venture_id, human=me,
        artifact_kind=body.artifact_kind, artifact_hash_value=body.artifact_hash,
        required_role=body.required_role, distinct_humans=body.distinct_humans,
        note=body.note,
    )
    await _audit_human_action(
        me, "console_gate_signed",
        {"gate": body.gate, "artifact_hash": body.artifact_hash}, body.venture_id,
    )
    return {"signoff_id": str(signoff_id)}


@app.get("/api/signoffs/{venture_id}/{gate}")
async def signoff_status(
    venture_id: str, gate: str, current_artifact_hash: str, conn: DB, _me: ME
) -> dict[str, Any]:
    """Which signatures still stand against the artifact as it is now.

    Part 14: artifact change voids signature. Void by comparison, so nothing has to
    remember to revoke anything when a Pack is edited.
    """
    status = await humans.signoff_status(
        conn, gate=gate, venture_id=venture_id,
        current_artifact_hash=current_artifact_hash,
    )
    return {
        "gate": status.gate,
        "venture_id": status.venture_id,
        "is_signed": status.is_signed,
        "valid": status.valid,
        "voided": status.voided,
    }


__all__ = ["NotAuthorized", "app"]
