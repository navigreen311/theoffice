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

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from broker import (
    audit,
    budget,
    certification,
    humans,
    incidents,
    instructions,
    knowledge,
    packs,
    proposals,
    provisioning,
    revocation,
    sweeps,
)
from broker.db import close_pool, connection
from broker.errors import NotAuthorized, OfficeError
from broker.humans import Human
from generators.validator import validate as validate_pack

# The migration this build expects. `/api/ready` compares it to what the database
# actually reports, so a container cannot serve traffic against a schema its code was
# never written for. Bump it in the same commit as the migration - the two disagreeing
# is the condition this exists to detect.
EXPECTED_SCHEMA_REVISION = "0015"


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


# ================================================ unauthenticated: liveness

# THE ONLY TWO ROUTES ON THIS API THAT DO NOT REQUIRE A TOKEN.
#
# Docker's healthcheck and Caddy's upstream check cannot hold a bearer token, so the
# alternative to these is no health checking at all - which means a container that has
# lost its database keeps receiving traffic.
#
# Adding a third is a reviewable act:
# `test_the_unauthenticated_surface_is_exactly_these_two` pins the set. Neither returns
# anything an unauthenticated caller could learn from - no version, no counts, no error
# text, no schema revision. `/api/health` stays authenticated, because control freshness
# is exactly what an attacker would like to know is stale.

@app.get("/api/live")
async def live() -> dict[str, str]:
    """The process is up. No database, no auth, no information.

    Deliberately does not touch the database. A liveness probe that fails when the
    database is unreachable makes the orchestrator restart a perfectly healthy process
    in a loop, which turns a database outage into an application outage as well.
    """
    return {"status": "live"}


@app.get("/api/ready")
async def ready(response: Response) -> dict[str, str]:
    """The database answers and the schema is at head.

    Both halves matter. A container serving traffic against a half-migrated database is
    worse than one that is down: it answers, and it answers wrong. This is the check
    that keeps a deploy from switching traffic onto a version whose migration has not
    finished.

    Returns 503 rather than raising, so the body stays this small on both paths. The
    reason a readiness check failed is operational detail, and it belongs in the
    container's logs rather than in an unauthenticated response.
    """
    try:
        async with connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT version_num FROM alembic_version")
            row = await cur.fetchone()
    except Exception:
        response.status_code = 503
        return {"status": "not_ready"}

    if row is None or row[0] != EXPECTED_SCHEMA_REVISION:
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ready"}



# ================================================================= pagination

class Page(BaseModel):
    """A page of results that says what it did not show.

    This project's rule is *report the denominator; no green check without a coverage
    count*, and the screen that broke it hardest was the audit explorer - which capped
    at 100 rows and said nothing about the rest. "I looked and found nothing" is the
    entire value of an audit search, and it is a different sentence from "I looked at
    the most recent hundred".

    `total` is a second query. Worth it: a page without one is a list that looks
    complete, which is the same failure as a sweep that never ran looking green.
    """

    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int

    @property
    def shown(self) -> int:
        return len(self.items)


async def paginate(
    conn: AsyncConnection,
    *,
    select: str,
    count: str,
    params: dict[str, Any],
    limit: int,
    offset: int,
) -> Page:
    """Run the page and its denominator against the same parameters.

    `select` must end in its ORDER BY; LIMIT and OFFSET are appended here so a caller
    cannot forget them and return the whole table by accident.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(count, params)
        row = await cur.fetchone()
        total = int(next(iter(row.values()))) if row else 0

        await cur.execute(
            f"{select} LIMIT %(limit)s OFFSET %(offset)s",
            {**params, "limit": limit, "offset": offset},
        )
        items = [dict(r) for r in await cur.fetchall()]

    return Page(items=items, total=total, limit=limit, offset=offset)


LimitParam = Annotated[int, Query(ge=1, le=500)]
OffsetParam = Annotated[int, Query(ge=0)]


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
    limit: LimitParam = 100,
    offset: OffsetParam = 0,
) -> Page:
    """Audit Log Explorer. Read-only, and there is no route that writes here.

    Paginated with a total, because the previous version capped at 100 and said nothing
    about the rest. "I searched the audit log and found nothing" is the entire value of
    this screen and it is a different sentence from "I looked at the most recent
    hundred" - and the two were indistinguishable in the response.
    """
    where = """
        WHERE (%(event_type)s::text IS NULL OR event_type = %(event_type)s)
          AND (%(actor_id)s::uuid IS NULL OR actor_id = %(actor_id)s)
          AND (%(venture_id)s::text IS NULL OR venture_id = %(venture_id)s)
          AND (%(trace_id)s::uuid IS NULL OR trace_id = %(trace_id)s)
    """
    return await paginate(
        conn,
        select=f"""
            SELECT audit_id, event_type, actor_type, actor_id, venture_id, subject,
                   trace_id, ts, entry_hash
            FROM audit_log {where} ORDER BY audit_id DESC
        """,
        count=f"SELECT count(*) FROM audit_log {where}",
        params={
            "event_type": event_type, "actor_id": actor_id,
            "venture_id": venture_id, "trace_id": trace_id,
        },
        limit=limit,
        offset=offset,
    )


@app.get("/api/incidents")
async def list_incidents(
    conn: DB,
    _me: ME,
    severity: Annotated[str | None, Query()] = None,
    include_resolved: bool = Query(default=False),
    limit: LimitParam = 100,
    offset: OffsetParam = 0,
) -> Page:
    """Incidents, with whether each has been resolved and by whom.

    Resolution is a joined row rather than a column: `incident` is append-only by
    design, so an incident is never edited and "resolved" is the presence of an
    `incident_resolution` rather than a flag somebody set.
    """
    where = """
        WHERE (%(severity)s::text IS NULL OR i.severity = %(severity)s)
          AND (%(include_resolved)s OR r.incident_id IS NULL)
    """
    join = "FROM incident i LEFT JOIN incident_resolution r ON r.incident_id = i.incident_id"
    return await paginate(
        conn,
        select=f"""
            SELECT i.incident_id::text AS incident_id, i.severity, i.kind, i.venture_id,
                   i.office_agent_id::text AS office_agent_id, i.forge_id, i.module_id,
                   i.trace_id::text AS trace_id, i.detail, i.raised_at,
                   r.resolution, r.resolved_at, r.resolved_by::text AS resolved_by
            {join} {where}
            ORDER BY
              CASE i.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                              WHEN 'MEDIUM' THEN 2 ELSE 3 END,
              i.raised_at DESC
        """,
        count=f"SELECT count(*) {join} {where}",
        params={"severity": severity, "include_resolved": include_resolved},
        limit=limit,
        offset=offset,
    )


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


@app.get("/api/forges")
async def list_forges(conn: DB, _me: ME) -> list[dict[str, Any]]:
    """Forge registry with modules, and whether each has authored instructions.

    The instruction-authoring screen has no other way to know what it can author for,
    and "which modules are missing instructions" is the question that screen exists to
    answer - a module with none can never be certified, so its position can never be
    filled.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.forge_id, r.display_name, r.api_version, r.credential_mode,
                   r.health_status,
                   COALESCE(
                     json_agg(
                       json_build_object(
                         'module_id', m.module_id,
                         'is_mutating', m.is_mutating,
                         'idempotency_support', m.idempotency_support,
                         'compliance_flags_implied', m.compliance_flags_implied,
                         'has_instructions', i.module_id IS NOT NULL,
                         'instruction_version', i.instruction_version,
                         'version_sensitivity', i.version_sensitivity
                       ) ORDER BY m.module_id
                     ) FILTER (WHERE m.module_id IS NOT NULL),
                     '[]'
                   ) AS modules
            FROM forge_registry r
            LEFT JOIN forge_module_registry m ON m.forge_id = r.forge_id
            LEFT JOIN forge_operating_instruction i
                   ON i.forge_id = m.forge_id AND i.module_id = m.module_id
                  AND i.superseded_at IS NULL
            GROUP BY r.forge_id, r.display_name, r.api_version, r.credential_mode,
                     r.health_status
            ORDER BY r.forge_id
            """
        )
        return [dict(r) for r in await cur.fetchall()]


@app.get("/api/instructions/{forge_id}/{module_id}/diff")
async def instruction_diff(
    forge_id: str,
    module_id: str,
    from_version: str,
    to_version: str,
    conn: DB,
    _me: ME,
) -> dict[str, Any]:
    """Section-level diff between two instruction versions.

    Section-level rather than line-level because the question an author and a reviewer
    actually ask is "did the never-do list change", and a line diff buries that answer
    in reformatting.
    """
    try:
        result = await instructions.diff(
            conn, forge_id=forge_id, module_id=module_id,
            from_version=from_version, to_version=to_version,
        )
    except instructions.InstructionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"forge_id": forge_id, "module_id": module_id,
            "from_version": from_version, "to_version": to_version, **result}


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


# ====================================================== read: packs and runs

def _rule_rows(report: Any) -> list[dict[str, str]]:
    return [
        {"rule_id": r.rule_id, "severity": r.severity.value,
         "verdict": r.verdict.value, "message": r.message}
        for r in report.results
    ]


@app.get("/api/packs")
async def list_packs(conn: DB, _me: ME) -> list[dict[str, Any]]:
    """The live Pack of every venture that has one."""
    return await packs.list_ventures(conn)


@app.get("/api/packs/{venture_id}")
async def pack_detail(venture_id: str, conn: DB, _me: ME) -> dict[str, Any]:
    """Version history and the live source.

    Superseded versions stay listed. A run records the version it started from, and an
    editor that only showed the current text would make that record unreadable.
    """
    live = await packs.live(conn, venture_id)
    return {
        "venture_id": venture_id,
        "live": None if live is None else {
            "pack_version": live.pack_version,
            "content_hash": live.content_hash,
            "yaml_source": live.yaml_source,
        },
        "versions": await packs.list_versions(conn, venture_id),
    }


@app.get("/api/packs/{venture_id}/versions/{pack_version}")
async def pack_version(
    venture_id: str, pack_version: str, conn: DB, _me: ME
) -> dict[str, Any]:
    stored = await packs.get_version(conn, venture_id, pack_version)
    if stored is None:
        raise HTTPException(status_code=404, detail="no such Pack version")
    return {
        "venture_id": stored.venture_id,
        "pack_version": stored.pack_version,
        "content_hash": stored.content_hash,
        "yaml_source": stored.yaml_source,
    }


@app.get("/api/provisioning/runs")
async def list_provisioning_runs(
    conn: DB, _me: ME, venture_id: str | None = Query(default=None)
) -> list[dict[str, Any]]:
    return await provisioning.list_runs(conn, venture_id=venture_id)


@app.get("/api/provisioning/runs/{run_id}")
async def provisioning_run(run_id: uuid.UUID, conn: DB, _me: ME) -> dict[str, Any]:
    """A run, its gate ladder, and every gate's evidence.

    The full sequence is returned, including the gates that have not run - the console
    renders sixteen rows either way, because a gate ladder that only lists what has
    happened cannot show what is still ahead of a blocked run.
    """
    state = await provisioning.get_run(conn, run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="no such run")
    results = await provisioning.gate_results(conn, run_id)

    latest: dict[str, dict[str, Any]] = {}
    for row in results:
        latest[row["gate"]] = row

    ladder = [
        {
            "gate": gate,
            "title": provisioning.GATE_TITLES[gate],
            "verdict": latest.get(gate, {}).get("verdict"),
            "reason": latest.get(gate, {}).get("reason"),
            "evidence": latest.get(gate, {}).get("evidence", {}),
            "recorded_at": latest.get(gate, {}).get("recorded_at"),
            "is_current": gate == state.current_gate,
        }
        for gate in provisioning.GATE_SEQUENCE
    ]
    return {
        "run_id": str(state.run_id),
        "venture_id": state.venture_id,
        "pack_version": state.pack_version,
        "status": state.status,
        "current_gate": state.current_gate,
        "artifacts_hash": state.artifacts_hash,
        "ladder": ladder,
        "history": results,
    }


# ================================================= write: packs and runs

class PackValidateRequest(BaseModel):
    yaml_source: str = Field(min_length=1)


@app.post("/api/packs/validate")
async def validate_pack_source(
    body: PackValidateRequest, conn: DB, _me: ME
) -> dict[str, Any]:
    """Run all 27 rules against a draft. **Stores nothing.**

    A POST because the body is a document, not because anything is written. The editor
    needs this: publishing a Pack that fails Gate 2 wastes a run, and finding out at
    Gate 2 means finding out after Gates 0 and 1 have already reported healthy.

    FAIL, WARN and NOT_RUN are reported separately. Collapsing NOT_RUN into "no problem"
    is how a Pack whose bridge check never ran gets read as validated.
    """
    try:
        parsed = packs.parse_only(body.yaml_source)
    except packs.PackStoreError as exc:
        return {"parsed": False, "error": str(exc), "results": [],
                "failures": [], "warnings": [], "not_run": [], "passed": False}

    report = await validate_pack(parsed, conn)
    return {
        "parsed": True,
        "venture_id": parsed.venture_id,
        "passed": report.passed,
        "results": _rule_rows(report),
        "failures": [r.rule_id for r in report.failures],
        "warnings": [r.rule_id for r in report.warnings],
        "not_run": [r.rule_id for r in report.not_run],
        "rules_checked": len(report.results),
    }


class PackPublishRequest(BaseModel):
    yaml_source: str = Field(min_length=1)
    pack_version: str = Field(min_length=1)


@app.post("/api/packs", status_code=201)
async def publish_pack(body: PackPublishRequest, conn: DB, me: ME) -> dict[str, Any]:
    """Publish a Pack version. Supersedes the live one; does **not** start a run.

    Two acts, two routes, two audit events. A save button that quietly begins
    provisioning is a save button that issues grants.

    The venture is not a parameter - it comes from the document - so authorisation is
    checked against the venture the Pack names rather than one the caller chose.
    """
    try:
        parsed = packs.parse_only(body.yaml_source)
    except packs.PackStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    humans.authorize(me, required_role="venture_operator", venture_id=parsed.venture_id)
    stored = await packs.store(
        conn, yaml_source=body.yaml_source, pack_version=body.pack_version,
        authored_by=me.human_id,
    )
    await _audit_human_action(
        me, "console_pack_published",
        {"pack_version": stored.pack_version, "content_hash": stored.content_hash},
        stored.venture_id,
    )
    return {
        "venture_id": stored.venture_id,
        "pack_version": stored.pack_version,
        "content_hash": stored.content_hash,
        "note": (
            "Published. Any existing Gate 10 signature is void against the artifacts "
            "this Pack generates, and no run has been started."
        ),
    }


class StartRunRequest(BaseModel):
    venture_id: str = Field(min_length=1)


@app.post("/api/provisioning/runs", status_code=201)
async def start_provisioning_run(
    body: StartRunRequest, conn: DB, me: ME
) -> dict[str, str]:
    humans.authorize(me, required_role="venture_operator", venture_id=body.venture_id)
    try:
        run_id = await provisioning.start_run(
            conn, venture_id=body.venture_id, started_by=me.human_id
        )
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": str(run_id)}


@app.post("/api/provisioning/runs/{run_id}/advance")
async def advance_provisioning_run(
    run_id: uuid.UUID, conn: DB, me: ME
) -> dict[str, Any]:
    """Run gates from the current one until something stops the run.

    This is the only route that can lead to a grant becoming active, and it cannot skip
    a gate to get there: Gate 11 refuses without a Gate 10 signature bound to the
    current artifacts, and it re-checks rather than trusting Gate 10's recorded verdict.
    There is no route that activates a grant directly, and there must never be.

    `held_out` is left at its default, so a run started here stops at Gate 9.5. The
    partition does not exist in this deployment and the console says so rather than
    offering an override.
    """
    state = await provisioning.get_run(conn, run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="no such run")
    humans.authorize(me, required_role="venture_operator", venture_id=state.venture_id)
    try:
        outcomes = await provisioning.advance(conn, run_id=run_id, actor=me.human_id)
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    after = await provisioning.get_run(conn, run_id)
    assert after is not None
    return {
        "run_id": str(run_id),
        "status": after.status,
        "current_gate": after.current_gate,
        "outcomes": [
            {"gate": o.gate, "verdict": o.verdict, "reason": o.reason,
             "evidence": o.evidence}
            for o in outcomes
        ],
    }


class RunNoteRequest(BaseModel):
    note: str = Field(min_length=1)


@app.post("/api/provisioning/runs/{run_id}/review")
async def review_provisioning_run(
    run_id: uuid.UUID, body: RunNoteRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Gate 4. A named human states they reviewed the artifacts, and says what.

    The note is required by the domain function, not by this route - re-checking it here
    would just be a second opinion that eventually disagrees with the first.
    """
    try:
        await provisioning.record_human_review(
            conn, run_id=run_id, human=me, note=body.note
        )
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "reviewed"}


@app.post("/api/provisioning/runs/{run_id}/abort")
async def abort_provisioning_run(
    run_id: uuid.UUID, body: RunNoteRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Abandon a run. Not a revocation - grants are deliberately untouched."""
    try:
        await provisioning.abort_run(
            conn, run_id=run_id, human=me, reason=body.note
        )
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "aborted"}


class RunSignoffRequest(BaseModel):
    artifacts_hash: str = Field(min_length=64, max_length=64)
    note: str | None = None


@app.post("/api/provisioning/runs/{run_id}/signoff", status_code=201)
async def sign_off_provisioning_run(
    run_id: uuid.UUID, body: RunSignoffRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Gate 10, bound to the artifacts the signer was shown.

    `POST /api/signoffs` takes whatever hash its caller passes. That was harmless while
    nothing consumed it and is not harmless now that Gate 11 activates production grants
    against it. Here the caller sends the hash **it displayed**, the server regenerates
    the artifacts, and a mismatch is refused - so a signature is a confirmation of what
    was on screen rather than an assertion about what is in the database.
    """
    try:
        signoff_id, hash_value = await provisioning.sign_off_run(
            conn, run_id=run_id, human=me,
            displayed_artifacts_hash=body.artifacts_hash, note=body.note,
        )
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"signoff_id": str(signoff_id), "artifacts_hash": hash_value}

# ======================================================= read: knowledge bases

@app.get("/api/knowledge/coverage")
async def knowledge_coverage(conn: DB, _me: ME) -> dict[str, Any]:
    """The Manager's whole reason to exist: what is missing, out of how many.

    Part 6 names five knowledge bases. A screen listing forty entries and no denominator
    is a filing cabinet with search; the question an operator has is which of the five
    is thin, and where.

    Every denominator here is drawn from something the system already needs - modules in
    the registry, compliance flags carried by live grants, lifecycle stages the Packs
    declare, target personas the Packs name. A denominator invented for the display
    would make the coverage number unfalsifiable.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
              (SELECT count(*) FROM forge_module_registry) AS modules,
              (SELECT count(*) FROM forge_operating_instruction
                WHERE superseded_at IS NULL) AS instructions,
              (SELECT count(*) FROM business_playbook
                WHERE superseded_at IS NULL) AS playbooks,
              (SELECT count(*) FROM playbook_share WHERE revoked_at IS NULL) AS shares,
              (SELECT count(*) FROM compliance_library_entry) AS compliance_entries,
              (SELECT count(*) FROM persona WHERE superseded_at IS NULL) AS personas,
              (SELECT count(*) FROM historical_record) AS records
            """
        )
        counts = await cur.fetchone()

        # Modules with no instructions. A module here can never be certified, so its
        # position can never be filled - this is a staffing gap wearing a docs label.
        await cur.execute(
            """
            SELECT m.forge_id, m.module_id
            FROM forge_module_registry m
            LEFT JOIN forge_operating_instruction i
              ON i.forge_id = m.forge_id AND i.module_id = m.module_id
             AND i.superseded_at IS NULL
            WHERE i.module_id IS NULL
            ORDER BY m.forge_id, m.module_id
            """
        )
        modules_without_instructions = [dict(r) for r in await cur.fetchall()]

        # Compliance flags in use with nothing in the library to explain them. "In use"
        # means implied by a registered module, not merely mentioned somewhere.
        await cur.execute(
            """
            SELECT DISTINCT f AS runtime_flag
            FROM forge_module_registry m,
                 unnest(m.compliance_flags_implied) AS f
            WHERE NOT EXISTS (
              SELECT 1 FROM compliance_library_entry e WHERE e.runtime_flag = f
            )
            ORDER BY 1
            """
        )
        unexplained_flags = [r["runtime_flag"] for r in await cur.fetchall()]

        await cur.execute(
            "SELECT DISTINCT unnest(compliance_flags_implied) AS f "
            "FROM forge_module_registry"
        )
        flags_in_use = {r["f"] for r in await cur.fetchall()}

    assert counts is not None
    return {
        "forge_operating_instructions": {
            "covered": int(counts["instructions"]),
            "denominator": int(counts["modules"]),
            "uncovered": [
                f"{r['forge_id']}/{r['module_id']}" for r in modules_without_instructions
            ],
            "blocking": True,
            "note": "A module with no instructions can never be certified.",
        },
        "compliance_library": {
            "covered": len(flags_in_use) - len(unexplained_flags),
            "denominator": len(flags_in_use),
            "uncovered": unexplained_flags,
            "entries": int(counts["compliance_entries"]),
            "blocking": True,
            "note": (
                "A flag with no entry reaches the agent as a label, not a constraint."
            ),
        },
        "business_playbooks": {
            "count": int(counts["playbooks"]),
            "shares": int(counts["shares"]),
            "blocking": False,
            "note": "Cross-venture sharing is opt-in only; absence is a refusal.",
        },
        "persona_library": {
            "count": int(counts["personas"]),
            "blocking": False,
            # Deliberately does not name the column. `test_no_module_reads_a_persona_body`
            # forbids a string literal that pairs SELECT with it anywhere in the runtime,
            # and loosening that check so prose can mention it is the wrong direction -
            # the exact column name is also not something a browser response needs.
            "note": (
                "SimForge only. The runtime role holds no read privilege on a persona "
                "body, so this console cannot render one - reviewing one is out of band."
            ),
        },
        "historical_records": {
            "count": int(counts["records"]),
            "blocking": False,
            "note": "Append-only. Written by the system and by named humans.",
        },
    }


@app.get("/api/knowledge/playbooks")
async def list_playbooks(
    conn: DB, _me: ME, venture_id: str | None = Query(default=None)
) -> dict[str, Any]:
    """Scoped to a venture, because that is the only correct way to read them.

    Without `venture_id` this returns shares and nothing else. There is deliberately no
    "all playbooks" read: a caller that got one would be one forgotten filter away from
    showing a venture another venture's SOPs.
    """
    playbooks = (
        [] if venture_id is None else await knowledge.playbooks_for(conn, venture_id)
    )
    return {
        "venture_id": venture_id,
        "playbooks": [
            {
                "playbook_id": str(p.playbook_id),
                "venture_id": p.venture_id,
                "title": p.title,
                "lifecycle_stage": p.lifecycle_stage,
                "playbook_version": p.playbook_version,
                "content_hash": p.content_hash,
                "content": p.content,
                "shared_from": p.shared_from,
            }
            for p in playbooks
        ],
        "shares": await knowledge.list_shares(conn),
    }


@app.get("/api/knowledge/compliance")
async def list_compliance_entries(conn: DB, _me: ME) -> list[dict[str, Any]]:
    return await knowledge.compliance_entries(conn)


@app.get("/api/knowledge/personas")
async def list_personas(
    conn: DB, _me: ME, venture_id: str | None = Query(default=None)
) -> list[dict[str, Any]]:
    """Names, targets and hashes. Never bodies - the role cannot read them."""
    return await knowledge.persona_index(conn, venture_id)


@app.get("/api/knowledge/history")
async def list_history(
    conn: DB, _me: ME, venture_id: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
) -> list[dict[str, Any]]:
    return await knowledge.history(conn, venture_id=venture_id, limit=limit)


# ====================================================== write: knowledge bases

class PlaybookRequest(BaseModel):
    venture_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    playbook_version: str = Field(min_length=1)
    content: dict[str, Any]
    lifecycle_stage: str | None = None


@app.post("/api/knowledge/playbooks", status_code=201)
async def author_playbook_route(
    body: PlaybookRequest, conn: DB, me: ME
) -> dict[str, str]:
    humans.authorize(me, required_role="venture_operator", venture_id=body.venture_id)
    try:
        written = await knowledge.author_playbook(
            conn, venture_id=body.venture_id, title=body.title,
            playbook_version=body.playbook_version, content=body.content,
            lifecycle_stage=body.lifecycle_stage, authored_by=me.human_id,
        )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_playbook_authored",
        {"title": body.title, "content_hash": written.content_hash}, body.venture_id,
    )
    return {"playbook_id": str(written.playbook_id),
            "content_hash": written.content_hash}


class ShareRequest(BaseModel):
    playbook_id: uuid.UUID
    to_venture_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    revoke: bool = False


@app.post("/api/knowledge/playbooks/share")
async def share_playbook_route(body: ShareRequest, conn: DB, me: ME) -> dict[str, str]:
    """Part 6.2: opt-in only, and the opt-in is a named human with a reason.

    Authority is checked against the venture that **owns** the playbook, not the one
    receiving it. The owner consents to disclosure; the recipient has nothing to consent
    to, and checking the recipient's operator would let a venture help itself.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT venture_id FROM business_playbook WHERE playbook_id = %s",
            (body.playbook_id,),
        )
        owner = await cur.fetchone()
    if owner is None:
        raise HTTPException(status_code=404, detail="no such playbook")
    humans.authorize(me, required_role="venture_operator", venture_id=owner[0])

    try:
        if body.revoke:
            await knowledge.revoke_share(
                conn, playbook_id=body.playbook_id, to_venture_id=body.to_venture_id
            )
        else:
            await knowledge.share_playbook(
                conn, playbook_id=body.playbook_id, to_venture_id=body.to_venture_id,
                shared_by=me.human_id, reason=body.reason,
            )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_playbook_share_revoked" if body.revoke else "console_playbook_shared",
        {"playbook_id": str(body.playbook_id), "to_venture_id": body.to_venture_id,
         "reason": body.reason},
        owner[0],
    )
    return {"status": "revoked" if body.revoke else "shared"}


class ComplianceEntryRequest(BaseModel):
    entry_ref: str = Field(min_length=1)
    framework: str = Field(min_length=1)
    jurisdiction: list[str] = Field(min_length=1)
    applicability_rule: str = Field(min_length=1)
    agent_behavior_implication: str = Field(min_length=1)
    escalation_trigger: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    runtime_flag: str | None = None


@app.post("/api/knowledge/compliance", status_code=201)
async def author_compliance_entry_route(
    body: ComplianceEntryRequest, conn: DB, me: ME
) -> dict[str, Any]:
    """Part 6.3's six fields. The library is portfolio-wide, so authority is too.

    Writing an entry changes what every Pack's `library_entry_ref` resolves against and
    what Gate 6 considers explained, which is not a per-venture decision.
    """
    humans.authorize(me, required_role="compliance_officer")
    try:
        await knowledge.author_compliance_entry(
            conn, entry_ref=body.entry_ref, framework=body.framework,
            jurisdiction=body.jurisdiction,
            applicability_rule=body.applicability_rule,
            agent_behavior_implication=body.agent_behavior_implication,
            escalation_trigger=body.escalation_trigger, citation=body.citation,
            runtime_flag=body.runtime_flag, authored_by=me.human_id,
        )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_compliance_entry_authored",
        {"entry_ref": body.entry_ref, "runtime_flag": body.runtime_flag},
    )
    return {
        "entry_ref": body.entry_ref,
        "note": (
            "Packs naming this ref now resolve it, and any Gate 6 that blocked on this "
            "runtime flag will pass on its next run."
        ),
    }


class PersonaRequest(BaseModel):
    venture_id: str = Field(min_length=1)
    persona_name: str = Field(min_length=1)
    target_persona: str = Field(min_length=1)
    persona_version: str = Field(min_length=1)
    persona_body: dict[str, Any]


@app.post("/api/knowledge/personas", status_code=201)
async def author_persona_route(
    body: PersonaRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Write a persona. There is no route that reads one back, and there cannot be.

    Part 6.4 is SimForge only. `office_app` holds no SELECT on `persona_body`, so a read
    route would be a privilege error rather than a leak - and this console runs as that
    role, which is why authoring here is a one-way act.
    """
    humans.authorize(me, required_role="venture_operator", venture_id=body.venture_id)
    try:
        persona_id = await knowledge.author_persona(
            conn, venture_id=body.venture_id, persona_name=body.persona_name,
            target_persona=body.target_persona,
            persona_version=body.persona_version, persona_body=body.persona_body,
            authored_by=me.human_id,
        )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_persona_authored",
        {"persona_name": body.persona_name, "target_persona": body.target_persona},
        body.venture_id,
    )
    return {
        "persona_id": str(persona_id),
        "note": (
            "Written. This console cannot read the body back - Part 6.4 is SimForge "
            "only, enforced by a column privilege rather than by a missing route."
        ),
    }


class HistoryNoteRequest(BaseModel):
    summary: str = Field(min_length=1)
    venture_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/knowledge/history", status_code=201)
async def record_history_route(
    body: HistoryNoteRequest, conn: DB, me: ME
) -> dict[str, int]:
    """Append one institutional fact. Append-only, so there is no way back out."""
    humans.authorize(me, required_role="venture_operator", venture_id=body.venture_id)
    try:
        record_id = await knowledge.record(
            conn, record_type="note", venture_id=body.venture_id,
            summary=body.summary, detail=body.detail, actor_type="human",
            recorded_by=me.human_id,
        )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"record_id": record_id}

# ======================================================= read: humans and access

@app.get("/api/humans")
async def list_humans(conn: DB, me: ME) -> list[dict[str, Any]]:
    """Everyone with access, and what they hold.

    Requires `compliance_officer`: the roster of who can act on this system, and which
    of them holds `ivan`, is a map of whom to compromise. It is not a secret from the
    people who operate the Office, and it is not a read for a venture operator either.
    """
    humans.authorize(me, required_role="compliance_officer")
    return await humans.list_humans(conn)


@app.get("/api/revocations")
async def list_revocations(
    conn: DB, _me: ME, include_lifted: bool = Query(default=False)
) -> list[dict[str, Any]]:
    """What is currently revoked.

    There was no way to see this. `POST /api/revocations/{id}/reinstate` existed and was
    pinned, so lifting a revocation required getting the id out of the database by hand
    - a write-only loop, and the write was the kill switch.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.revocation_id::text AS revocation_id, r.scope, r.reason,
                   r.office_agent_id::text AS office_agent_id, r.forge_id, r.module_id,
                   r.venture_id, r.revoked_by::text AS revoked_by, r.revoked_by_role,
                   r.revoked_at, r.reinstated_at,
                   r.reinstated_by::text AS reinstated_by,
                   i.agent_name
            FROM revocation r
            LEFT JOIN office_agent_identity i ON i.office_agent_id = r.office_agent_id
            WHERE %s OR r.reinstated_at IS NULL
            ORDER BY r.revoked_at DESC
            """,
            (include_lifted,),
        )
        return [dict(r) for r in await cur.fetchall()]


# ====================================================== write: humans and access

class HumanRequest(BaseModel):
    display_name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    auth_method: str = "sso_mfa"
    role: str | None = None
    venture_id: str | None = None


@app.post("/api/humans", status_code=201)
async def create_human_route(body: HumanRequest, conn: DB, me: ME) -> dict[str, Any]:
    """Create a human, and return their token exactly once.

    Creating a human creates a credential, so this needs `compliance_officer` at least -
    and if an initial role is requested, the strictly-stronger rule applies to that role
    on top. A `compliance_officer` can therefore create a `venture_operator` and cannot
    create a peer.

    The plaintext is in this response and nowhere else, ever. A system that can show it
    again is a system where hashing it was pointless.
    """
    humans.authorize(me, required_role="compliance_officer")
    if body.role is not None:
        humans.assert_may_grant(me, role=body.role)

    human_id, token = await humans.create_human(
        conn, display_name=body.display_name, email=body.email,
        auth_method=body.auth_method,
    )
    if body.role is not None:
        await humans.grant_role(
            conn, human_id=human_id, role=body.role,
            venture_id=body.venture_id, granted_by=me.human_id,
        )

    await _audit_human_action(
        me, "console_human_created",
        {"human_id": str(human_id), "email": body.email, "initial_role": body.role},
        body.venture_id,
    )
    return {
        "human_id": str(human_id),
        "token": token,
        "note": (
            "This token is shown once and is not recoverable. If it is lost, reissue - "
            "which invalidates this one."
        ),
    }


class RoleRequest(BaseModel):
    role: str
    venture_id: str | None = None
    revoke: bool = False


@app.post("/api/humans/{human_id}/roles")
async def set_role(
    human_id: uuid.UUID, body: RoleRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Grant or remove a role.

    Two rules, both in `humans.assert_may_grant`: strictly stronger than the role being
    handed out, and never to yourself. Removing is guarded the same way - being unable
    to grant `ivan` and able to remove it would be the same power with an extra step.
    """
    target = await humans.get_human(conn, human_id)
    if target is None:
        raise HTTPException(status_code=404, detail="no such human")
    humans.assert_may_grant(
        me, role=body.role, target=target, revoking=body.revoke
    )

    if body.revoke:
        if body.role == "ivan":
            await humans.assert_not_the_last_administrator(
                conn, human_id=human_id, action="remove the ivan role"
            )
        removed = await humans.revoke_role(
            conn, human_id=human_id, role=body.role, venture_id=body.venture_id,
            revoked_by=me.human_id,
        )
        await _audit_human_action(
            me, "console_role_revoked",
            {"human_id": str(human_id), "role": body.role, "existed": removed},
            body.venture_id,
        )
        return {"status": "revoked" if removed else "no_such_role"}

    await humans.grant_role(
        conn, human_id=human_id, role=body.role,
        venture_id=body.venture_id, granted_by=me.human_id,
    )
    await _audit_human_action(
        me, "console_role_granted",
        {"human_id": str(human_id), "role": body.role}, body.venture_id,
    )
    return {"status": "granted"}


class StatusRequest(BaseModel):
    status: str
    reason: str = Field(min_length=1)


@app.post("/api/humans/{human_id}/status")
async def set_human_status(
    human_id: uuid.UUID, body: StatusRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Suspend or reactivate. Takes effect on their next request, not their next session."""
    humans.authorize(me, required_role="compliance_officer")
    target = await humans.get_human(conn, human_id)
    if target is None:
        raise HTTPException(status_code=404, detail="no such human")

    if body.status == "suspended":
        # Both guards. The first stops the system becoming unadministrable; the second
        # stops an operator locking themselves out with one click and needing somebody
        # else to let them back in.
        await humans.assert_not_the_last_administrator(
            conn, human_id=human_id, action="suspend this human"
        )
        if human_id == me.human_id:
            raise HTTPException(
                status_code=400,
                detail="suspending yourself would lock you out; ask another operator",
            )

    await humans.set_status(
        conn, human_id=human_id, status=body.status, actor=me.human_id
    )
    await _audit_human_action(
        me, "console_human_status_changed",
        {"human_id": str(human_id), "status": body.status, "reason": body.reason},
    )
    return {"status": body.status}


@app.post("/api/humans/{human_id}/token")
async def reissue_human_token(
    human_id: uuid.UUID, conn: DB, me: ME
) -> dict[str, str]:
    """Rotate a token. The old one stops working immediately.

    Your own, or anyone's with `ivan`. Rotation has never existed here - a token was
    valid until its human was suspended, which made a leaked token a permanent one.
    """
    if human_id != me.human_id:
        humans.authorize(me, required_role="ivan")

    token = await humans.reissue_token(conn, human_id=human_id)
    await _audit_human_action(
        me, "console_token_reissued", {"human_id": str(human_id)}
    )
    return {
        "token": token,
        "note": "Shown once. The previous token stopped working when this was issued.",
    }


class ResolveIncidentRequest(BaseModel):
    resolution: str = Field(min_length=1)


@app.post("/api/incidents/{incident_id}/resolve", status_code=201)
async def resolve_incident(
    incident_id: uuid.UUID, body: ResolveIncidentRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Close an incident, with an account of what was done.

    An append, not an edit - `incidents.resolve` explains why. Authority is checked
    against the incident's own venture rather than one the request named, because a
    request body is a claim and the row is the fact.

    Also what finally writes `historical_record.incident_resolved`, which has been an
    enum value with no producer since the knowledge bases landed.
    """
    # Read first, so the venture used for authorisation comes from the database.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id FROM incident WHERE incident_id = %s", (incident_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such incident")
    humans.authorize(
        me, required_role="compliance_officer", venture_id=row["venture_id"]
    )

    try:
        incident = await incidents.resolve(
            conn, incident_id=incident_id, resolution=body.resolution,
            resolved_by=me.human_id,
        )
    except incidents.IncidentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await knowledge.record(
        conn, record_type="incident_resolved", venture_id=incident["venture_id"],
        summary=(
            f"{incident['severity']} {incident['kind']} resolved: {body.resolution}"
        ),
        detail={"incident_id": str(incident_id), "severity": incident["severity"],
                "kind": incident["kind"]},
        actor_type="human", recorded_by=me.human_id,
    )
    await _audit_human_action(
        me, "console_incident_resolved",
        {"incident_id": str(incident_id), "resolution": body.resolution},
        incident["venture_id"],
    )
    return {"status": "resolved"}


__all__ = ["NotAuthorized", "app"]
