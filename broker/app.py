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

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from broker import (
    access_overview,
    audit,
    audit_events,
    audit_view,
    budget,
    certification,
    curriculum_quality,
    departments,
    forge_map,
    humans,
    incidents,
    instructions,
    knowledge,
    knowledge_origin,
    pack_templates,
    packs,
    proposals,
    provisioning,
    revocation,
    roster,
    sweeps,
    ventures,
    village,
)
from broker import (
    incident_taxonomy as incident_taxonomy_module,
)
from broker.db import close_pool, connection
from broker.errors import NotAuthorized, OfficeError
from broker.humans import Human
from generators.validator import (
    GATE_45_RECHECKS,
    LATER_GATE_REASONS,
    all_rule_ids,
    rule_blocks,
)
from generators.validator import validate as validate_pack

# The migration this build expects. `/api/ready` compares it to what the database
# actually reports, so a container cannot serve traffic against a schema its code was
# never written for. Bump it in the same commit as the migration - the two disagreeing
# is the condition this exists to detect.
EXPECTED_SCHEMA_REVISION = "0031"


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
    """Chain integrity: the live check, and the recorded verification beside it.

    Both, because they answer different questions and the page used to conflate them.
    `audit_log_verify_chain()` says whether the chain is intact *right now*. The
    `sweep_run` row says what was last verified, when, and over how many entries - and
    that is the row the Compliance page reads, so reporting it here is what stops the two
    screens describing the same property and disagreeing.

    The live fields keep their published names: the dashboard reads them.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT ok, checked_count, first_break_audit_id, tail_gap, reason "
            "FROM audit_log_verify_chain()"
        )
        row = await cur.fetchone()
    assert row is not None

    return {
        **dict(row),
        "as_of": datetime.now(UTC).isoformat(),
        # The live check is real and is not evidence: nothing records it, so it cannot
        # be produced later and Compliance cannot see it.
        "live_check_is_recorded": False,
        "recorded_verification": await audit_view.chain_state(conn),
    }


@app.post("/api/controls/audit-chain", status_code=201)
async def audit_verify(conn: DB, me: ME) -> dict[str, Any]:
    """Run the chain verification and record the result as a control run.

    This is what makes the Audit page and the Compliance page agree by construction:
    there is one verification, it leaves one row, and both screens read it. Requires
    `compliance_officer` because it writes a control result - a sweep anybody could
    record on demand is a control whose freshness means nothing.
    """
    humans.authorize(me, required_role="compliance_officer")
    result = await sweeps.sweep_audit_chain(conn)
    await _audit_human_action(
        me, "console_controls_run",
        {"requested": "audit_chain", "ran": ["audit_chain"],
         "checked": result.denominator},
    )
    return {"recorded_verification": await audit_view.chain_state(conn)}


@app.get("/api/audit/events")
async def audit_event_glossary(_me: ME) -> dict[str, Any]:
    """Every event type, what it means, and what writes it.

    Event names reached the page as raw identifiers with no glossary, and the filter
    asked the reader to type one - usable only by somebody who already knew the answer.
    """
    return {"events": audit_events.published()}


@app.get("/api/audit/shape")
async def audit_shape(
    conn: DB,
    _me: ME,
    include_fixtures: bool = Query(default=False),
    since: Annotated[str | None, Query()] = None,
    until: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Counts by event type, actor and venture before anybody pages through."""
    return {
        "as_of": datetime.now(UTC).isoformat(),
        **await audit_view.shape(
            conn, include_fixtures=include_fixtures, since=since, until=until
        ),
    }


@app.get("/api/audit/export")
async def audit_export(
    conn: DB,
    me: ME,
    include_fixtures: bool = Query(default=False),
    event_type: Annotated[str | None, Query()] = None,
    venture_id: Annotated[str | None, Query()] = None,
    trace_id: Annotated[str | None, Query()] = None,
    actor_id: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query()] = None,
    until: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """A structured export that states its own limits.

    Part 9 requires record export on demand. An export that does not say which filters
    produced it, whether fixtures were in it, and how much of the log the chain
    verification actually covered is a document that looks like evidence and is not.
    """
    humans.authorize(me, required_role="compliance_officer", venture_id=venture_id)
    manifest = await audit_view.export_manifest(
        conn,
        filters={
            "event_type": event_type, "venture_id": venture_id, "trace_id": trace_id,
            "actor_id": actor_id, "since": since, "until": until,
        },
        include_fixtures=include_fixtures,
    )
    await _audit_human_action(
        me, "console_compliance_exported",
        {"kind": "audit_log", "entries": manifest["entries_included"],
         "fixtures_included": include_fixtures},
        venture_id,
    )
    return {"as_of": datetime.now(UTC).isoformat(), **manifest}


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


# Declared BEFORE `/api/agents/{office_agent_id}`. FastAPI matches in declaration order,
# so a literal segment registered after a parameterised one is unreachable.
@app.get("/api/agents/roster")
async def agent_roster(
    conn: DB,
    _me: ME,
    search: str | None = Query(default=None),
    department: str | None = Query(default=None),
    identity: str | None = Query(default=None),
    grants: str | None = Query(default=None),
) -> dict[str, Any]:
    """The Village roster, and how far each agent has got into The Office.

    The old list rendered the seven agents holding an identity, so a reader concluded
    the Village has seven people. The agents it *cannot* appoint are the most
    consequential rows here: they are the work that has not been done.
    """
    result = await roster.directory(
        conn, search=search, department=department, identity=identity, grants=grants,
    )
    return {"as_of": datetime.now(UTC).isoformat(), **result}


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
            "SELECT shift_id, venture_id, shift_start, shift_end, flush_verified, "
            "       quarter "
            "FROM shift_assignment WHERE office_agent_id = %s "
            "ORDER BY shift_start DESC LIMIT 5",
            (office_agent_id,),
        )
        shifts_recent = [dict(r) for r in await cur.fetchall()]

        # Both certification units, scoped. The page claimed a certified tier for this
        # agent and had no certifications section at all - and a bare "certified:
        # auto_execute" is the same failure as a green check with no denominator,
        # because a certification is always *for* a specific Forge and module.
        await cur.execute(
            """
            SELECT unit, forge_id, module_id, department, state, certified_tier,
                   instruction_content_hash, forge_api_version, rubric_kind,
                   rubric_version, score, threshold, simforge_verdict,
                   issued_at, updated_at
            FROM certification
            WHERE office_agent_id = %s
            ORDER BY unit, forge_id, module_id
            """,
            (office_agent_id,),
        )
        certifications = [dict(r) for r in await cur.fetchall()]

        # Recent activity. Under the brokered model the Office ledger is the only
        # record naming this agent, so "never called a Forge" is a fact worth stating
        # rather than an empty table.
        await cur.execute(
            """
            SELECT call_id::text AS call_id, forge_id, module_id, venture_id,
                   status_code, latency_ms, trust_tier_at_call, ts_start,
                   trace_id::text AS trace_id
            FROM agent_call_ledger
            WHERE office_agent_id = %s
            ORDER BY ts_start DESC
            LIMIT 10
            """,
            (office_agent_id,),
        )
        calls = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT count(*) AS calls,
                   coalesce(sum(usd_cost), 0) AS spend_total,
                   coalesce(sum(usd_cost) FILTER (
                     WHERE ts_start >= date_trunc('day', now())
                   ), 0) AS spend_today
            FROM agent_call_ledger
            WHERE office_agent_id = %s
            """,
            (office_agent_id,),
        )
        cost = dict(await cur.fetchone() or {})

    unit_a = [c for c in certifications if c["unit"] == "A"]
    unit_b = [c for c in certifications if c["unit"] == "B"]

    # Which Forges this agent can actually reach, as two separate facts. A Forge being
    # GREEN and this agent being unable to reach it are different statements, and the
    # old page put them in one column - "No grants. This agent cannot reach any Forge"
    # directly above three Forges marked GREEN.
    live_by_forge: dict[str, int] = {}
    for grant in grants:
        if grant["revoked_at"] is None:
            live_by_forge[grant["forge_id"]] = live_by_forge.get(grant["forge_id"], 0) + 1

    forge_access = [
        {
            **forge,
            "grants_here": live_by_forge.get(forge["forge_id"], 0),
            "reachable": live_by_forge.get(forge["forge_id"], 0) > 0,
        }
        for forge in forges
    ]

    # The Village's live view of this agent: mood, lifecycle stage, what they are doing
    # right now. Displayed, and acted on by nothing.
    #
    # This is the boundary the whole integration turns on. The Village is a simulation
    # with grief, exhaustion, ambition and death in it; The Office governs regulated
    # work. An agent who is grieving is still certified, still holds the grants somebody
    # granted them, and is still refused for exactly the reasons the call path already
    # refuses anybody. Wiring simulated mood into an authorization decision would mean a
    # patient record went unprocessed because an agent's friend died in a simulation,
    # and there would be no audit entry that could explain it.
    #
    # It is here because an operator looking at a strange call pattern should be able to
    # see that the agent has been on NIGHT shift for a week. That is context for a human,
    # not an input to a rule.
    #
    # Degrades. A Village that is down must not take the agent page with it - every
    # number above this line comes from The Office's own database and is still true.
    village_state: dict[str, Any] | None = None
    village_unreachable: str | None = None
    if identity.get("village_agent_ref"):
        try:
            answer = await village.agent_state(str(identity["village_agent_ref"]))
            village_state = {
                **answer.data,
                "fetched_at": answer.fetched_at.isoformat(),
                "stale": answer.stale,
            }
        except village.VillageUnreachableError as exc:
            village_unreachable = str(exc)

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "identity": dict(identity),
        "grants": grants,
        "forge_migration_status": forges,
        "forge_access": forge_access,
        "certifications": {"unit_a": unit_a, "unit_b": unit_b},
        "recent_calls": calls,
        "cost": cost,
        "recent_shifts": shifts_recent,
        "village_state": village_state,
        "village_unreachable": village_unreachable,
        # Stated in the payload rather than only in a comment, because the console
        # renders this section and the next person to read it should not have to infer
        # that it is inert.
        "village_state_gates": [],
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
    """The three numbers (§7.2). All three, always — one hides the state.

    And they must **sum to the active roster**. They did not: an agent with no
    certification row fell into none of the three, because `bool_or` over zero rows is
    NULL and `NOT NULL` is NULL rather than TRUE. Three numbers that quietly omit
    somebody are a worse version of the single number this exists to replace.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
              count(*) FILTER (WHERE certified AND NOT allocated) AS certified_and_free,
              count(*) FILTER (WHERE certified AND allocated)     AS certified_but_allocated,
              count(*) FILTER (WHERE NOT certified)               AS produced_not_yet_certified
            FROM (
              SELECT i.office_agent_id,
                     -- COALESCE, because `bool_or` over no rows is NULL and `NOT NULL`
                     -- is NULL rather than TRUE. An agent with no certification row at
                     -- all therefore matched none of the three filters and appeared in
                     -- none of the three numbers - so they silently stopped summing to
                     -- the roster, which is the exact failure the docstring above
                     -- claims to prevent. An agent nobody has certified is "produced,
                     -- not yet certified"; that is the state, not an absence of one.
                     COALESCE(bool_or(c.state = 'certified'), false)       AS certified,
                     COALESCE(bool_or(s.venture_id IS NOT NULL
                             AND s.venture_id <> %(venture)s), false)      AS allocated
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
async def venture_forge_map(venture_id: str, conn: DB, _me: ME) -> dict[str, Any]:
    """Forge Map (Part 15): Declared, Required, In-Use, and the reconciliation diff.

    The three states now come from the three places they actually live. They used to come
    from one - a `venture_forge_manifest` row was both the declaration and the
    requirement - so the diff the page promised could not exist, and with the manifest
    empty the table rendered nothing while the Pack declared nine modules.
    """
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

    # The three-way reconciliation, from the three places the states actually live.
    # `declared` above is the manifest, which is one of them; `forge_map.reconcile` reads
    # the Pack and the ledger too, which is what makes the diff a diff rather than one
    # table compared against itself.
    reconciliation = await forge_map.reconcile(conn, venture_id)

    return {
        "as_of": datetime.now(UTC).isoformat(),
        **reconciliation,
        "venture_id": venture_id,
        # Still `declared`, under its published name. Renaming it to `manifest_rows`
        # to make room for the reconciliation broke `/ventures/{venture}` with a 500 -
        # a field this route has always returned, read by a page that had no reason to
        # change. The reconciliation's own keys sit beside it rather than over it.
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

@app.get("/api/audit/entries")
async def audit_entries(
    conn: DB,
    _me: ME,
    event_type: Annotated[str | None, Query()] = None,
    venture_id: Annotated[str | None, Query()] = None,
    trace_id: Annotated[str | None, Query()] = None,
    actor_id: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query()] = None,
    until: Annotated[str | None, Query()] = None,
    include_fixtures: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
) -> dict[str, Any]:
    """The log, with the person who acted and the fixtures marked.

    Fixtures are filtered by default and counted, never removed: the store is append-only
    and a filter changes the view rather than the record.
    """
    return {
        "as_of": datetime.now(UTC).isoformat(),
        **await audit_view.entries(
            conn, event_type=event_type, venture_id=venture_id, trace_id=trace_id,
            actor_id=actor_id, since=since, until=until,
            include_fixtures=include_fixtures, page=page,
        ),
    }


@app.get("/api/audit/{audit_id}")
async def audit_entry_detail(audit_id: int, conn: DB, _me: ME) -> dict[str, Any]:
    """One entry: its payload, its trace, and both hashes with the link checked."""
    found = await audit_view.detail(conn, audit_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such audit entry")
    return found


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


@app.get("/api/incidents/taxonomy")
async def incident_taxonomy(_me: ME) -> dict[str, Any]:
    """The published severities, kinds and response stages.

    Served rather than duplicated in the console, because a taxonomy the screen keeps
    its own copy of is one that disagrees with the database the first time a kind is
    added.
    """
    return incident_taxonomy_module.published()


@app.get("/api/incidents/overview")
async def incidents_overview(conn: DB, _me: ME) -> dict[str, Any]:
    """Control freshness, open counts, and the cross-venture pattern by kind.

    The page told the reader to check control freshness elsewhere. It is computable
    here, and a screen that knows the answer and points at another screen is deferring,
    not reporting - especially when the answer is that the checks raising these have not
    run.
    """
    return {"as_of": datetime.now(UTC).isoformat(), **await incidents.overview(conn)}


@app.get("/api/incidents")
async def list_incidents(
    conn: DB,
    _me: ME,
    severity: Annotated[str | None, Query()] = None,
    kind: Annotated[str | None, Query()] = None,
    venture_id: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    since: Annotated[str | None, Query()] = None,
    include_resolved: bool = Query(default=False),
    limit: LimitParam = 100,
    offset: OffsetParam = 0,
) -> Page:
    """Incidents, with whether each has been resolved and by whom.

    Resolution is a joined row rather than a column: `incident` is append-only by
    design, so an incident is never edited and "resolved" is the presence of an
    `incident_resolution` rather than a flag somebody set.

    The filters exist because the empty state claimed them. "Nothing matches" implies
    something was excluded, and with no filter to exclude anything it meant "there are
    none" - two opposite readings of the same screen. The unfiltered total comes from
    `/api/incidents/overview`, which the page already reads, so it can say which of the
    two the reader is looking at without this route counting the same rows twice.

    `state` supersedes `include_resolved`, which stays because it is a published
    parameter and removing it would break a caller to tidy a signature.
    """
    if state == "all":
        include_resolved = True
    resolved_only = state == "resolved"

    where = """
        WHERE (%(severity)s::text IS NULL OR i.severity = %(severity)s)
          AND (%(kind)s::text IS NULL OR i.kind = %(kind)s)
          AND (%(venture_id)s::text IS NULL OR i.venture_id = %(venture_id)s)
          AND (%(since)s::date IS NULL OR i.raised_at >= %(since)s::date)
          AND (NOT %(resolved_only)s OR r.incident_id IS NOT NULL)
          AND (%(include_resolved)s OR %(resolved_only)s OR r.incident_id IS NULL)
    """
    join = "FROM incident i LEFT JOIN incident_resolution r ON r.incident_id = i.incident_id"
    return await paginate(
        conn,
        select=f"""
            SELECT i.incident_id::text AS incident_id, i.severity, i.kind, i.venture_id,
                   i.office_agent_id::text AS office_agent_id, i.forge_id, i.module_id,
                   i.trace_id::text AS trace_id, i.detail, i.raised_at,
                   i.detection_source, i.reported_by::text AS reported_by,
                   r.resolution, r.resolved_at, r.resolved_by::text AS resolved_by
            {join} {where}
            ORDER BY
              CASE i.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                              WHEN 'MEDIUM' THEN 2 ELSE 3 END,
              i.raised_at DESC
        """,
        count=f"SELECT count(*) {join} {where}",
        params={
            "severity": severity, "kind": kind, "venture_id": venture_id,
            "since": since, "resolved_only": resolved_only,
            "include_resolved": include_resolved,
        },
        limit=limit,
        offset=offset,
    )


# Declared BEFORE `/api/proposals/{proposal_id}`-shaped routes.
@app.get("/api/proposals/queue")
async def proposal_queue(conn: DB, _me: ME) -> dict[str, Any]:
    """Everything the approvals page needs, including why the queue is empty.

    The old empty state gave one explanation - that trust tiers might be set to
    `auto_execute` - which is a real cause and was not this cause. No agent held a grant
    to any Forge and none had ever made a call, so the queue was empty because nothing
    could act. The reason is derived here from what is actually true.
    """
    # Expire before reading, so the queue never shows an item whose deadline has passed
    # as though a reviewer could still take it. Expiry fails the task; it never approves.
    await proposals.expire_overdue(conn)
    result = await proposals.queue(conn)
    return {"as_of": datetime.now(UTC).isoformat(), **result}


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


# Declared BEFORE `/api/instructions/{forge_id}/{module_id}`. FastAPI matches in
# declaration order, so a literal segment registered after a parameterised one is
# unreachable - it would be handed "directory" as a forge id.
@app.get("/api/instructions/directory")
async def instructions_directory(conn: DB, _me: ME) -> dict[str, Any]:
    """Every instruction set, assessed by what it contains rather than by existing.

    `authored` meant a row exists, which the live cre-forge set satisfies with
    `"what_it_does": "Documented."` while 234 certifications rest on its hash.
    """
    result = await instructions.directory(conn)
    return {"as_of": datetime.now(UTC).isoformat(), **result}


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

    # Assessed, and the agents named. "2 agents are certified against a stub" is a
    # number; "Ada Sourcing and Bram Records are" is a list of people whose
    # certifications have to be redone.
    quality = curriculum_quality.assess(live.content if live else None)
    bound = (
        await instructions.certifications_on(
            conn, forge_id, module_id, live.content_hash
        )
        if live is not None else []
    )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT human_id::text AS human_id, display_name FROM office_human"
        )
        authors = {r["human_id"]: r["display_name"] for r in await cur.fetchall()}

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "forge_id": forge_id,
        "module_id": module_id,
        "live": None if live is None else {
            "instruction_version": live.instruction_version,
            "forge_api_version": live.forge_api_version,
            "version_sensitivity": live.version_sensitivity,
            "content_hash": live.content_hash,
            "content": live.content,
        },
        "quality": quality,
        "certifications_bound": bound,
        "versions": [
            {**row, "author": authors.get(str(row.get("authored_by")))}
            for row in versions
        ],
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
    #: Required at `venture` and `forge` scope. The domain function refuses without it,
    #: and so does a CHECK constraint - a ritual that lives only in a route is one the
    #: next route can forget.
    second_human: uuid.UUID | None = None


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
        second_human=body.second_human,
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


# ======================================================= read: pack directory

@app.get("/api/packs/templates")
async def list_pack_templates(_me: ME) -> dict[str, Any]:
    """The template catalogue, one entry per portfolio category."""
    return {"categories": pack_templates.categories()}


@app.get("/api/packs/template")
async def pack_template(
    category: str, _me: ME, venture_name: str | None = None,
) -> dict[str, Any]:
    """A starting document for `category`.

    Deliberately fails validation. Every field it leaves at `REPLACE_ME` or zero is a
    decision that depends on the venture, and a template that filled them in with
    plausible values would produce a Pack that passes the validator on numbers nobody
    chose.
    """
    known = {c["category"] for c in pack_templates.categories()}
    if category not in known:
        raise HTTPException(status_code=404, detail=f"no template for {category!r}")
    return {
        "category": category,
        "yaml_source": pack_templates.skeleton(
            category, venture_name=venture_name or pack_templates.PLACEHOLDER
        ),
        "note": (
            "A template fails validation on purpose. The failing rules are the list of "
            "what still needs a decision."
        ),
    }


# Declared BEFORE `/api/packs/{venture_id}`, and it has to be. FastAPI matches routes in
# declaration order, so a static segment registered after a parameterised one at the
# same depth is unreachable - this returned the Pack detail for a venture named
# "directory", with a 200 and a plausible-looking body.
@app.get("/api/packs/directory")
async def pack_directory(conn: DB, _me: ME) -> dict[str, Any]:
    """Every Pack, and whether it can provision.

    The old page showed that a Pack existed and gave its hash. It did not show whether
    the Pack **works** - and a Pack failing any FAIL rule cannot provision, cannot
    generate and cannot appoint, which makes "does it validate" the most important
    thing on the page and the one thing it did not say.
    """
    result = await packs.directory(conn)
    return {"as_of": datetime.now(UTC).isoformat(), **result}


@app.get("/api/packs/{venture_id}")
async def pack_detail(venture_id: str, conn: DB, _me: ME) -> dict[str, Any]:
    """Version history and the live source.

    Superseded versions stay listed. A run records the version it started from, and an
    editor that only showed the current text would make that record unreadable.
    """
    live = await packs.live(conn, venture_id)
    pending = await packs.draft(conn, venture_id)

    # The editor needs the draft as much as the live version, and until now the route
    # did not return it - so a draft saved from the directory was invisible on the one
    # screen built to work on it, and the editor loaded the live Pack over the top.
    report = None
    editing = pending or live
    if editing is not None:
        result = await validate_pack(editing.pack, conn)
        # Three states, never two. A rule that could not be evaluated has established
        # nothing, and counting it as "checked" produces a badge claiming the document
        # was examined more thoroughly than it was.
        rows = []
        for row in _rule_rows(result):
            gate, why = LATER_GATE_REASONS.get(row["rule_id"], (None, None))
            evaluable = row["verdict"] != "NOT_RUN"
            rows.append({
                **row,
                # Which Pack blocks the rule reads, so the editor's sidebar can mark the
                # block a failure lives in rather than only listing the failure.
                "blocks": list(rule_blocks().get(row["rule_id"], ())),
                "evaluable": evaluable,
                # Which gate settles it, and why not here. A bare NOT_RUN tells a reader
                # that something did not happen without telling them what would.
                "settled_at_gate": gate,
                "why_not_here": None if evaluable else why,
                # Passes here, re-checked later against real output. Not a failure and
                # not a clean bill either.
                "rechecked_later": (
                    row["rule_id"] in GATE_45_RECHECKS and evaluable
                ),
                "rechecked_reason": why if row["rule_id"] in GATE_45_RECHECKS else None,
            })

        passed = [r for r in rows if r["verdict"] == "PASS"]
        failed = [r for r in rows if r["verdict"] in ("FAIL", "WARN")]
        not_evaluable = [r for r in rows if not r["evaluable"]]

        report = {
            "state": packs.validation_state(result),
            "rules": rows,
            "passed": len(passed),
            "failed": len(failed),
            "not_evaluable": len(not_evaluable),
            "rechecked_later": len([r for r in rows if r["rechecked_later"]]),
            "rules_total": len(all_rule_ids()),
        }

    # What publishing would disturb, computed rather than described. The mechanism is
    # not the obvious one: a certification binds to a Forge Operating Instruction's
    # hash, not to the Pack, so publishing a Pack does not void certifications. What it
    # voids is Gate 10 signatures, which bind to the *artifacts* hash - and the
    # artifacts are generated from the Pack, so changing the Pack changes them and the
    # signature stops matching. Nothing revokes it.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT count(*) AS n FROM signoff_record "
            "WHERE venture_id = %s AND gate = 'gate_10'",
            (venture_id,),
        )
        counted = await cur.fetchone()
        signatures = int((counted or {}).get("n", 0))

        await cur.execute(
            "SELECT run_id::text AS run_id, pack_version, status, current_gate "
            "FROM provisioning_run "
            "WHERE venture_id = %s AND status IN ('running','blocked','awaiting_human')",
            (venture_id,),
        )
        open_runs = [dict(r) for r in await cur.fetchall()]

    # The schema's own block list, in document order. Presence is *not* computed here:
    # the editor's sidebar describes the buffer somebody is typing into, and a parsed
    # model cannot answer that - an optional field with a default reads as present even
    # when the document never mentions it. The client reads the text.
    every_block, required_blocks = packs.schema_blocks()

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "venture_id": venture_id,
        # In document order, with what is missing named. A block that is absent is
        # information - the sidebar is where "this Pack has no kpi_targets" belongs, and
        # it cannot say it from a list of the blocks that happen to exist.
        "schema": {
            "blocks": [
                {"name": name, "required": name in required_blocks}
                for name in every_block
            ],
            "total": len(every_block),
        },
        "bindings": {
            "gate_10_signatures": signatures,
            # Pinned to the version they started from, so publishing does not change
            # what they provision. Worth saying, because the opposite is assumed.
            "open_runs": open_runs,
        },
        "live": None if live is None else {
            "pack_version": live.pack_version,
            "content_hash": live.content_hash,
            "yaml_source": live.yaml_source,
        },
        "draft": None if pending is None else {
            "pack_version": pending.pack_version,
            "content_hash": pending.content_hash,
            "yaml_source": pending.yaml_source,
        },
        "validation": report,
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
    conn: DB,
    _me: ME,
    venture_id: str | None = Query(default=None),
    include_fixtures: bool = Query(default=False),
) -> dict[str, Any]:
    """Runs, with smoke-test loops filtered out by default and counted.

    104 of 108 runs here were started by `scripts/console-smoke.sh`, which drives one to
    gate 4 and aborts it on every invocation. Listed alongside real runs they read as a
    system that cannot get past gate 4. Nothing is deleted - the filter changes the view.
    """
    return await provisioning.list_runs(
        conn, venture_id=venture_id, include_fixtures=include_fixtures
    )


@app.get("/api/me")
async def whoami(me: ME) -> dict[str, Any]:
    """The signed-in human.

    Needed so a screen can say "awaiting you" rather than "awaiting_human". Which of
    those a reader sees decides whether they realise the run is waiting on them.
    """
    return {
        "human_id": str(me.human_id),
        "display_name": me.display_name,
        # (role, venture_id); the venture scope is not this route's business.
        "roles": sorted({role for role, _venture in me.roles}),
    }


# Declared BEFORE `/api/provisioning/runs/{run_id}`. A literal segment registered
# after a parameterised one at the same depth is unreachable - FastAPI hands it to the
# path parameter and answers 200 with the wrong body. `/api/packs/directory` shipped
# that way and nothing failed.
@app.get("/api/provisioning/directory")
async def provisioning_directory(conn: DB, _me: ME) -> dict[str, Any]:
    """Every venture, and exactly how far it got.

    The old index rendered `5 of 16` - a number with no map. A fraction cannot say which
    gate stopped the run, what happened there, or what is still ahead.
    """
    result = await provisioning.directory(conn)
    return {"as_of": datetime.now(UTC).isoformat(), **result}


@app.get("/api/provisioning/history/{venture_id}")
async def provisioning_history(
    venture_id: str, conn: DB, _me: ME
) -> dict[str, Any]:
    """Every run for a venture. Provisioning is iterative and the pattern is the point."""
    return {
        "venture_id": venture_id,
        "runs": await provisioning.venture_history(conn, venture_id),
    }


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

    # The same builder the index uses. Gate 9.5 read `not run` here and `blocked -
    # ceiling` there, because two screens each described the ladder in their own terms;
    # one gate cannot mean two things depending on which page you opened.
    ladder = provisioning.ladder_for(results, state.current_gate, state.status)

    blocking = next(
        (
            row for row in results
            if row["gate"] == state.current_gate and row["verdict"] != "passed"
        ),
        None,
    )
    disposition = await provisioning.human_disposition(
        conn, str(state.run_id), state.status
    )

    return {
        # Stamped by the server, like every other directory route. The page used to read
        # its own render clock, which produces one value during SSR and a different one
        # during hydration - the two renders then disagree about what time it is.
        "as_of": datetime.now(UTC).isoformat(),
        "run_id": str(state.run_id),
        "venture_id": state.venture_id,
        "pack_version": state.pack_version,
        "status": state.status,
        "display_status": provisioning.display_status(
            state.status, state.current_gate, blocking
        ),
        "disposition": disposition,
        "current_gate": state.current_gate,
        "current_gate_name": provisioning.GATE_NAMES[state.current_gate],
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


@app.post("/api/provisioning/runs/{run_id}/reject")
async def reject_provisioning_run(
    run_id: uuid.UUID, body: RunNoteRequest, conn: DB, me: ME
) -> dict[str, str]:
    """A named human declines at a gate awaiting their decision.

    Not the same act as abandoning the run. Aborting says nothing about the artifacts;
    this is a judgement about them, and the next person to provision this venture needs
    to know which one happened.

    Deliberately not an override in the other direction: there is no route that lets a
    human pass a gate the system blocked.
    """
    try:
        await provisioning.reject_run(conn, run_id=run_id, human=me, reason=body.note)
    except provisioning.ProvisioningError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "rejected"}


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


# Declared BEFORE any parameterised `/api/knowledge/...` route.
@app.get("/api/knowledge/overview")
async def knowledge_overview(conn: DB, _me: ME) -> dict[str, Any]:
    """The five knowledge bases, counted by substance rather than by row.

    The page reported 60 personas. All sixty are `Smoke NNNNNN` written by console smoke
    runs, standing in for the same broker — a library holding sixty copies of one fixture
    has zero personas.
    """
    result = await knowledge.overview(conn)
    return {"as_of": datetime.now(UTC).isoformat(), **result}


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
    conn: DB,
    _me: ME,
    venture_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    include_fixtures: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    """Names, targets and hashes. Never bodies - the role cannot read them.

    Fixtures are excluded by default. Sixty of the sixty personas here are `Smoke
    NNNNNN`, written by console smoke runs, and a page that lists them first buries the
    real ones - of which there are none, which is the fact worth seeing.
    """
    rows = await knowledge.persona_index(conn, venture_id)
    shaped = [
        {**row, "origin": knowledge_origin.persona_origin(row)} for row in rows
    ]
    return _paged_knowledge(
        shaped, search=search, origin=origin, include_fixtures=include_fixtures,
        page=page, page_size=page_size,
        matches=lambda row, term: term in str(row.get("persona_name", "")).lower()
        or term in str(row.get("target_persona", "")).lower(),
    )


@app.get("/api/knowledge/history")
async def list_history(
    conn: DB,
    _me: ME,
    venture_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    record_type: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    include_fixtures: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """The record. Fixtures are filtered out, never removed.

    This store is append-only by design - it refuses UPDATE and DELETE, and `office_app`
    holds only INSERT and SELECT. A bad entry is answered with a compensating entry, so
    excluding smoke fixtures from the default view is a reading decision rather than a
    deletion, and the exclusion itself is recorded when an operator makes it.
    """
    rows = await knowledge.history(conn, venture_id=venture_id, limit=500)
    shaped = [
        {**row, "origin": knowledge_origin.record_origin(row)} for row in rows
    ]
    if record_type:
        shaped = [row for row in shaped if row.get("record_type") == record_type]
    if actor_type:
        shaped = [row for row in shaped if row.get("actor_type") == actor_type]

    return _paged_knowledge(
        shaped, search=search, origin=origin, include_fixtures=include_fixtures,
        page=page, page_size=page_size,
        matches=lambda row, term: term in str(row.get("summary", "")).lower(),
    )


def _paged_knowledge(
    rows: list[dict[str, Any]],
    *,
    search: str | None,
    origin: str | None,
    include_fixtures: bool,
    page: int,
    page_size: int,
    matches: Any,
) -> dict[str, Any]:
    """Filter, then page, and say what was left out.

    `excluded_fixtures` is returned even when they are hidden. A list that silently drops
    120 of 132 rows and reports the remaining 12 as the total is the same failure as
    counting the fixtures as content - the reader has to be able to see that a decision
    was made.
    """
    total_before = len(rows)
    fixtures = len([row for row in rows if row.get("origin") == "test_fixture"])

    if not include_fixtures:
        rows = [row for row in rows if row.get("origin") != "test_fixture"]
    if origin:
        rows = [row for row in rows if row.get("origin") == origin]
    if search:
        term = search.strip().lower()
        rows = [row for row in rows if matches(row, term)]

    total = len(rows)
    start = (page - 1) * page_size
    return {
        "rows": rows[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
        "total_before_filters": total_before,
        "excluded_fixtures": 0 if include_fixtures else fixtures,
    }


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

    # The hash, returned once. The body is beyond this console's reach the moment it
    # lands, so this is the only thing the author can keep to verify against - and
    # `body_hash` is a column the role *can* read, unlike the body it describes.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT body_hash FROM persona WHERE persona_id = %s", (persona_id,)
        )
        hashed = await cur.fetchone()

    await _audit_human_action(
        me, "console_persona_authored",
        {"persona_name": body.persona_name, "target_persona": body.target_persona,
         "body_hash": (hashed or {}).get("body_hash")},
        body.venture_id,
    )
    return {
        "persona_id": str(persona_id),
        "body_hash": (hashed or {}).get("body_hash", ""),
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


@app.post("/api/knowledge/fixtures/exclude", status_code=201)
async def record_fixture_exclusion_route(conn: DB, me: ME) -> dict[str, int]:
    """Write down that the smoke fixtures are being left out of the counts.

    There is no purge route and there should not be. `persona` is write-only to this
    role and `historical_record` is append-only to everyone, so the honest action is the
    one the store allows: append a record saying what is being excluded and who decided
    it. Filtering rows out of a count without that is the silent version of the same
    act, and the silent version is what let sixty smoke personas read as a library.
    """
    humans.authorize(me, required_role="venture_operator")
    summary = await knowledge.overview(conn)
    fixtures = summary["fixtures"]
    try:
        record_id = await knowledge.record_fixture_exclusion(
            conn,
            recorded_by=me.human_id,
            counts={
                "personas": fixtures["personas"],
                "records": fixtures["records"],
            },
        )
    except knowledge.KnowledgeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"record_id": record_id}

# ======================================================= read: humans and access

@app.get("/api/access/overview")
async def access_overview_route(conn: DB, me: ME) -> dict[str, Any]:
    """What the Access page states before it lists anybody.

    Requires `compliance_officer`, like the roster it summarises: how concentrated the
    strongest role is, and who holds it, is the same map of whom to compromise.
    """
    humans.authorize(me, required_role="compliance_officer")
    return {
        "as_of": datetime.now(UTC).isoformat(),
        **await access_overview.overview(conn),
    }


@app.post("/api/access/suspend-test-fixtures")
async def suspend_test_fixtures_route(conn: DB, me: ME) -> dict[str, Any]:
    """Suspend every account this project's own test paths created.

    `ivan`, because this touches accounts holding `ivan`. Suspension only - there is no
    delete route here or anywhere, because deleting an account destroys the record of who
    held what and who granted it.
    """
    humans.authorize(me, required_role="ivan")
    result = await humans.suspend_test_fixtures(conn, actor=me.human_id)
    await _audit_human_action(
        me, "console_test_fixtures_suspended",
        {"suspended": result["suspended"]},
    )
    return result


@app.get("/api/forge-map/estate")
async def forge_estate_route(conn: DB, _me: ME) -> dict[str, Any]:
    """Every Forge the portfolio names, bridged or not.

    The map only ever showed the Forges one venture declared, so a Forge with no bridge
    was indistinguishable from one that does not exist.
    """
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "forges": await forge_map.estate(conn),
    }


@app.get("/api/forge-map/matrix")
async def forge_matrix_route(conn: DB, _me: ME) -> dict[str, Any]:
    """Ventures against Forges: which engagements halt if one goes down."""
    return {
        "as_of": datetime.now(UTC).isoformat(),
        **await forge_map.matrix(conn),
    }


@app.get("/api/humans")
async def list_humans(conn: DB, me: ME) -> list[dict[str, Any]]:
    """Everyone with access, and what they hold.

    Requires `compliance_officer`: the roster of who can act on this system, and which
    of them holds `ivan`, is a map of whom to compromise. It is not a secret from the
    people who operate the Office, and it is not a read for a venture operator either.
    """
    humans.authorize(me, required_role="compliance_officer")
    return await humans.list_humans(conn)


@app.get("/api/revocations/targets")
async def revocation_targets(conn: DB, _me: ME) -> dict[str, Any]:
    """What can be revoked, by name.

    The form asked for four UUIDs as free text. This is the emergency control: nobody
    recalls a UUID under pressure, and a typo either fails or stops the wrong thing.
    """
    return {"as_of": datetime.now(UTC).isoformat(), **await revocation.targets(conn)}


@app.get("/api/revocations/blast-radius")
async def revocation_blast_radius(
    conn: DB,
    _me: ME,
    scope: Annotated[str, Query()],
    office_agent_id: Annotated[uuid.UUID | None, Query()] = None,
    forge_id: Annotated[str | None, Query()] = None,
    module_id: Annotated[str | None, Query()] = None,
    venture_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """What a revocation would stop, before it is issued.

    A query against existing state, not an authorization decision - it says nothing
    about whether the caller may act, and the console still does no authority
    pre-checking. Showing somebody the size of what they are about to stop is not a
    second opinion about their permission to stop it.
    """
    try:
        return await revocation.blast_radius(
            conn, scope=scope, office_agent_id=office_agent_id,
            forge_id=forge_id, module_id=module_id, venture_id=venture_id,
        )
    except NotAuthorized as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/revocations/history")
async def revocation_history(conn: DB, _me: ME) -> list[dict[str, Any]]:
    """Every revocation ever issued, lifted or not, with what it stopped at the time.

    Regulator-export material: the reason field was always specified to surface there,
    and until now there was nowhere for it to surface from.
    """
    return await revocation.history(conn)


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


class RaiseIncidentRequest(BaseModel):
    severity: str
    kind: str
    detection_source: str
    summary: str = Field(min_length=1)
    venture_id: str | None = None


@app.post("/api/incidents", status_code=201)
async def raise_incident_route(
    body: RaiseIncidentRequest, conn: DB, me: ME
) -> dict[str, str]:
    """File an incident a person noticed.

    The blueprint names three detection sources and only agent flag arrives on its own.
    A regulator's question and a client's complaint had nowhere to go, so the list stayed
    empty and the empty list read as quiet.

    Hand-filed incidents carry the filer's id and a human detection source, so one is
    never mistaken for something a control caught. Like every other incident it cannot be
    edited afterwards - the response is appended.
    """
    humans.authorize(
        me, required_role="compliance_officer", venture_id=body.venture_id
    )
    try:
        incident_id = await incidents.file_by_hand(
            conn,
            severity=body.severity,
            kind=body.kind,
            detection_source=body.detection_source,
            summary=body.summary,
            reported_by=me.human_id,
            venture_id=body.venture_id,
        )
    except incidents.IncidentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_incident_raised",
        {"incident_id": str(incident_id), "kind": body.kind,
         "severity": body.severity, "detection_source": body.detection_source},
        body.venture_id,
    )
    return {"incident_id": str(incident_id)}


@app.get("/api/incidents/{incident_id}")
async def incident_detail(incident_id: uuid.UUID, conn: DB, _me: ME) -> dict[str, Any]:
    """One incident: the detection, and every account appended since."""
    found = await incidents.detail(conn, incident_id)
    if found is None:
        raise HTTPException(status_code=404, detail="no such incident")
    return {"as_of": datetime.now(UTC).isoformat(), **found}


class AccountRequest(BaseModel):
    stage: str
    account: str = Field(min_length=1)


@app.post("/api/incidents/{incident_id}/accounts", status_code=201)
async def append_incident_account(
    incident_id: uuid.UUID, body: AccountRequest, conn: DB, me: ME
) -> dict[str, int]:
    """Append one stage account to an incident's response.

    The only write an incident detail page offers. There is no edit and no delete, here
    or in the database: `incident_account` carries the same append-only trigger as the
    other ledgers, because a response timeline that can be tidied afterwards is a draft
    of what somebody wishes had happened.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id FROM incident WHERE incident_id = %s", (incident_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="no such incident")
    humans.authorize(
        me, required_role="venture_operator", venture_id=row["venture_id"]
    )

    try:
        account_id = await incidents.append_account(
            conn, incident_id=incident_id, stage=body.stage,
            account=body.account, written_by=me.human_id,
        )
    except incidents.IncidentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_incident_account_appended",
        {"incident_id": str(incident_id), "stage": body.stage},
        row["venture_id"],
    )
    return {"account_id": account_id}


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


# ========================================================= read: compliance

# What each control actually does, in a sentence a reader who does not know this system
# can act on. This lives beside the code that runs them rather than in the console,
# because a description that drifts from the check it describes is worse than none - and
# the console is the wrong place to notice the drift.
CONTROL_COPY: dict[str, dict[str, str]] = {
    "audit_chain": {
        "name": "Audit chain integrity",
        "cadence": "Expected daily",
        "checks": (
            "Re-hashes the ledger to prove no entry was altered or removed. Until "
            "Forges carry per-agent identity, this ledger is the only per-agent record "
            "anywhere - if it can be edited, you have nothing."
        ),
        "consequence": "blocks go-live sign-off",
        "blocking": "true",
    },
    "certification_staleness": {
        "name": "Certification staleness",
        "cadence": "Expected daily",
        "checks": (
            "Finds agents whose certification was earned under instructions or a Forge "
            "version that has since changed. A stale certification still reads as "
            "certified until this runs."
        ),
        "consequence": "agents may hold grants they no longer qualify for",
        "blocking": "true",
    },
    "manifest_reconciliation": {
        "name": "Forge manifest reconciliation",
        "cadence": "Expected monthly",
        "checks": (
            "Compares what each venture declared it needs, what its workflow actually "
            "calls, and what agents really hit. A call to an undeclared Forge is an "
            "unflagged compliance surface."
        ),
        "consequence": "undeclared Forge use goes unflagged",
        "blocking": "false",
    },
    "restore_drill": {
        "name": "Backup restore drill",
        "cadence": "Expected quarterly",
        "checks": (
            "Restores the ledger from backup into a scratch database and verifies it "
            "comes back whole. An untested restore is not a backup."
        ),
        "consequence": "due before first venture goes live",
        "blocking": "true",
    },
}

# The restore drill needs superuser credentials to create and drop a scratch database.
# The API deliberately does not hold them - it runs as office_app, which cannot even
# read a persona body - so this control cannot be triggered from a request. Saying so,
# with the command that does work, is more useful than a button that always fails.
RUNNABLE_FROM_THE_API = ("audit_chain", "certification_staleness", "manifest_reconciliation")


@app.get("/api/compliance")
async def compliance_overview(conn: DB, _me: ME) -> dict[str, Any]:
    """Everything the Compliance page needs, with every denominator computed here.

    One route rather than six, because the numbers have to agree with each other: a
    scorecard assembled from separate calls can show "0 of 5 ventures" beside a list of
    six, and the reader has no way to tell which is wrong.

    **No denominator is hardcoded.** The Village currently has 186 agents
    and a portfolio of several ventures; The Office knows about the agents and ventures
    that have actually reached it. Reporting "0 of 186" against a roster of seven would
    invent a denominator, on the page whose own copy insists on real ones - so the
    counts are what this database can support, and the roster gap is reported as its own
    fact.
    """
    freshness = await sweeps.freshness(conn)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
              (SELECT count(*) FROM office_agent_identity) AS agents_known,
              (SELECT count(DISTINCT office_agent_id) FROM agent_forge_grant
                WHERE is_assignable) AS agents_with_grants,
              (SELECT count(*) FROM agent_call_ledger) AS agent_calls,
              (SELECT max(ts_start) FROM agent_call_ledger) AS last_agent_call,
              (SELECT min(ts) FROM audit_log) AS oldest_entry,
              (SELECT count(*) FROM audit_log) AS audit_entries
            """
        )
        counts = await cur.fetchone()

        # A venture is an engagement, not a table. "Live" means it has at least one
        # assignable grant - an agent that could actually act - rather than a row
        # somewhere saying so.
        await cur.execute(
            """
            SELECT v.venture_id,
                   count(*) FILTER (WHERE g.is_assignable) AS assignable_grants
            FROM (SELECT DISTINCT venture_id FROM agent_forge_grant
                  UNION SELECT DISTINCT venture_id FROM venture_forge_manifest
                  UNION SELECT venture_id FROM venture_budget
                  UNION SELECT venture_id FROM business_pack) v
            LEFT JOIN agent_forge_grant g ON g.venture_id = v.venture_id
                   AND g.revoked_at IS NULL
            GROUP BY v.venture_id ORDER BY v.venture_id
            """
        )
        venture_rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            "SELECT venture_id, parsed FROM business_pack WHERE superseded_at IS NULL"
        )
        packs_rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            "SELECT entry_ref, runtime_flag FROM compliance_library_entry"
        )
        library = [dict(r) for r in await cur.fetchall()]

    assert counts is not None
    entry_refs = {e["entry_ref"] for e in library}
    library_flags = {e["runtime_flag"] for e in library if e["runtime_flag"]}

    # ------------------------------------------------- framework coverage per venture
    #
    # Part 6.3 and validator rule V28: a framework a Pack declares must resolve to a
    # runtime flag AND a Compliance Library entry. Missing either means the obligation
    # is named but not enforced - a flag with no entry reaches the agent as a label
    # rather than a constraint, and an entry with no flag is never applied to anything.
    ventures: list[dict[str, Any]] = []
    all_frameworks: set[str] = set()
    live_ventures = 0

    packs_by_venture = {r["venture_id"]: r["parsed"] for r in packs_rows}

    for row in venture_rows:
        venture_id = row["venture_id"]
        assignable = int(row["assignable_grants"])
        if assignable:
            live_ventures += 1

        parsed = packs_by_venture.get(venture_id)
        frameworks: list[dict[str, Any]] = []
        if parsed:
            for surface in parsed.get("market", {}).get("compliance_surface", []):
                framework = surface.get("framework", "")
                all_frameworks.add(framework)
                flag = surface.get("runtime_flag") or None
                ref = surface.get("library_entry_ref") or None
                frameworks.append({
                    "framework": framework,
                    "runtime_flag": flag,
                    "library_entry_ref": ref,
                    "declared_gap": bool(surface.get("library_gap")),
                    "has_flag": bool(flag),
                    "has_entry": bool(ref and ref in entry_refs)
                                 or bool(flag and flag in library_flags),
                })

        resolved = [f for f in frameworks if f["has_flag"] and f["has_entry"]]
        if not parsed:
            status, blocked_because = "blocked", "no Business Pack authored"
        elif not frameworks:
            status, blocked_because = "ready", None
        elif len(resolved) < len(frameworks):
            status, blocked_because = "gaps", None
        else:
            status, blocked_because = "ready", None

        ventures.append({
            "venture_id": venture_id,
            "frameworks": frameworks,
            "resolved": len(resolved),
            "declared": len(frameworks),
            "assignable_grants": assignable,
            "status": status,
            "blocked_because": blocked_because,
            "has_pack": parsed is not None,
        })

    verified = sum(1 for c in freshness.values() if c["healthy"])

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "controls": [
            {
                "id": kind,
                **CONTROL_COPY.get(kind, {}),
                "blocking": CONTROL_COPY.get(kind, {}).get("blocking") == "true",
                "runnable_from_here": kind in RUNNABLE_FROM_THE_API,
                "host_command": (
                    None if kind in RUNNABLE_FROM_THE_API
                    else "python -m broker sweep --restore-drill"
                ),
                **state,
            }
            for kind, state in sorted(freshness.items())
        ],
        "scorecard": {
            "ventures_live": {"value": live_ventures, "denominator": len(venture_rows)},
            "agents_with_grants": {
                "value": int(counts["agents_with_grants"]),
                "denominator": int(counts["agents_known"]),
                # The roster is the Village's, and it has not been imported. Stated as a
                # fact rather than folded into the denominator, because a denominator
                # nobody can verify is worse than a smaller true one.
                "note": (
                    "of the agents The Office knows. The Village roster has not been "
                    "imported (Phase 0.2)."
                ),
            },
            "frameworks_in_scope": {
                "value": len(all_frameworks),
                "denominator": len(all_frameworks),
                "note": "declared across every live Business Pack",
            },
            "controls_verified": {"value": verified, "denominator": len(freshness)},
        },
        "ventures": ventures,
        "chain_stats": {
            "audit_entries": int(counts["audit_entries"]),
            "oldest_entry": counts["oldest_entry"].isoformat()
                            if counts["oldest_entry"] else None,
            "agent_calls": int(counts["agent_calls"]),
            "last_agent_call": counts["last_agent_call"].isoformat()
                               if counts["last_agent_call"] else None,
        },
        "library_entries": len(library),
    }


# ======================================================== write: compliance

class RunControlsRequest(BaseModel):
    control: str | None = None
    """One control, or every runnable one when omitted."""


@app.post("/api/controls/run")
async def run_controls(body: RunControlsRequest, conn: DB, me: ME) -> dict[str, Any]:
    """Run the verification sweeps from the console.

    Until now these ran from a CLI and, in the deployment, from a container on a timer.
    A reader looking at four never-run controls had no way to act on what the page was
    telling them, which makes the warning decoration.

    Requires `compliance_officer`, because a sweep is not read-only: the certification
    sweep recomputes staleness and can move agents out of `certified`, and the manifest
    sweep can raise incidents. It reports what it did rather than a status word - a
    sweep that acquired no lock ran nothing, and that is a different outcome from one
    that ran and found nothing.
    """
    humans.authorize(me, required_role="compliance_officer")

    if body.control is not None and body.control not in RUNNABLE_FROM_THE_API:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{body.control!r} cannot be run from the API. The restore drill needs "
                "superuser credentials to create a scratch database, and the API "
                "deliberately does not hold them. Run it on the host: "
                "python -m broker sweep --restore-drill"
            ),
        )

    results = await sweeps.run_all(include_restore_drill=False)
    await _audit_human_action(
        me, "console_controls_run",
        {"requested": body.control or "all", "ran": sorted(results)},
    )

    return {
        "ran": [
            {
                "control": kind,
                "status": result.status,
                "passed": result.passed,
                "denominator": result.denominator,
            }
            for kind, result in sorted(results.items())
        ],
        "skipped": [k for k in RUNNABLE_FROM_THE_API if k not in results],
        "note": (
            "A control missing from `ran` held no lock - another process was already "
            "running it. That is not the same as running and finding nothing."
        ),
    }


class ExportRequest(BaseModel):
    venture_id: str | None = None
    framework: str | None = None
    since: str | None = None
    until: str | None = None


@app.post("/api/compliance/export", status_code=201)
async def export_compliance_record(
    body: ExportRequest, conn: DB, me: ME
) -> dict[str, Any]:
    """Part 9: structured record export on demand - CFPB, FTC, HHS OCR, state DFI.

    Two properties make this an evidence document rather than a data dump.

    **It states its own control freshness on its face.** An export produced while four
    controls have never run says so at the top, in the same document, so a recipient
    cannot mistake "no findings" for "checked and clean". An export that omitted this
    would be the strongest possible version of the failure this whole page exists to
    prevent.

    **It lists what it did not include.** Scope limits, records the requester cannot
    see, and stores that do not exist yet. A regulator reading a complete-looking
    document with silent omissions has been misled, whatever the intent.

    `content_hash` is a SHA-256 over the payload, not a signature. There is no key
    material in this deployment and inventing one would produce a signature that proves
    nothing while looking like it proves something. The hash detects alteration in
    transit; provenance needs a key, and that is named as a gap rather than faked.
    """
    humans.authorize(
        me, required_role="compliance_officer", venture_id=body.venture_id
    )

    overview = await compliance_overview(conn, me)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM audit_log_verify_chain()")
        chain_row = await cur.fetchone()

        await cur.execute(
            """
            SELECT count(*) AS entries, min(ts) AS first, max(ts) AS last
            FROM audit_log
            WHERE (%(venture)s::text IS NULL OR venture_id = %(venture)s)
              AND (%(since)s::timestamptz IS NULL OR ts >= %(since)s::timestamptz)
              AND (%(until)s::timestamptz IS NULL OR ts <= %(until)s::timestamptz)
            """,
            {"venture": body.venture_id, "since": body.since, "until": body.until},
        )
        audit_scope = await cur.fetchone()

        await cur.execute(
            """
            SELECT i.severity, count(*) AS n,
                   count(*) FILTER (WHERE r.incident_id IS NOT NULL) AS resolved
            FROM incident i
            LEFT JOIN incident_resolution r ON r.incident_id = i.incident_id
            WHERE (%(venture)s::text IS NULL OR i.venture_id = %(venture)s)
            GROUP BY i.severity ORDER BY i.severity
            """,
            {"venture": body.venture_id},
        )
        incident_summary = [dict(r) for r in await cur.fetchall()]

    unverified = [c["id"] for c in overview["controls"] if not c["healthy"]]

    document: dict[str, Any] = {
        "export": {
            "generated_at": datetime.now(UTC).isoformat(),
            "generated_by": me.display_name,
            "scope": {
                "venture_id": body.venture_id or "all ventures",
                "framework": body.framework or "all frameworks",
                "since": body.since,
                "until": body.until,
            },
        },
        # First, and deliberately. A recipient reads this before the contents.
        "control_freshness_at_export": {
            "verified": overview["scorecard"]["controls_verified"],
            "unverified": unverified,
            "statement": (
                "Every control was verified within its expected cadence at the time of "
                "this export."
                if not unverified
                else (
                    f"{len(unverified)} of "
                    f"{overview['scorecard']['controls_verified']['denominator']} "
                    "controls were NOT verified when this export was produced: "
                    + ", ".join(unverified)
                    + ". An absence of findings from a check that did not run is not "
                    "evidence. The contents below are not a clean record; they are an "
                    "unchecked one."
                )
            ),
        },
        "audit_chain": {
            "verified": bool(chain_row["ok"]) if chain_row else None,
            "entries_checked": int(chain_row["checked_count"]) if chain_row else 0,
            "reason": chain_row["reason"] if chain_row else None,
            "tail_gap": int(chain_row["tail_gap"]) if chain_row else 0,
        },
        "audit_records_in_scope": {
            "entries": int(audit_scope["entries"]) if audit_scope else 0,
            "first": audit_scope["first"].isoformat()
                     if audit_scope and audit_scope["first"] else None,
            "last": audit_scope["last"].isoformat()
                    if audit_scope and audit_scope["last"] else None,
        },
        "incidents": incident_summary,
        "framework_coverage": overview["ventures"],
        "not_included": [
            "Audit entry bodies. This is a manifest of what exists and whether it "
            "verifies; the entries themselves are served separately so that a request "
            "for them is its own audited act.",
            "SimForge certification evidence. SimForge has no instance in this "
            "deployment, so no Readiness Gate result exists to include.",
            "Held-out adversarial results. The Office has no read path to that "
            "partition by construction (J8) and cannot include what it cannot see.",
            "Per-agent Forge-side attribution. Forges see the tenant credential; until "
            "they carry per-agent identity, Forge logs attribute everything to the "
            "tenant and the Office ledger is the only per-agent record.",
        ],
        "integrity": {
            "method": "sha256-over-payload",
            "signed": False,
            "note": (
                "Hash-stamped, not signed. There is no key material in this "
                "deployment; a fabricated signature would prove nothing while "
                "appearing to prove provenance. The hash detects alteration in "
                "transit only."
            ),
        },
    }

    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str)
    document["integrity"]["content_hash"] = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()

    await _audit_human_action(
        me, "console_compliance_exported",
        {
            "scope": document["export"]["scope"],
            "content_hash": document["integrity"]["content_hash"],
            "unverified_controls": unverified,
        },
        body.venture_id,
    )
    return document

# ==================================================== read: venture directory

@app.get("/api/ventures/directory")
async def venture_directory(conn: DB, _me: ME) -> dict[str, Any]:
    """Where each venture is, what is blocking it, and what the portfolio is missing.

    The old `/api/ventures` answered five questions nobody was asking - agent count,
    grant count, cap, whether a hard cap had been reversed - and pipeline state, which
    is a venture's most important attribute, appeared nowhere. It stays, because the
    venture dashboard reads it; this is the one the directory uses.

    Status is derived, never stored, except the two states nothing can derive: a draft
    that exists before its Pack, and an archived venture that is indistinguishable from
    an empty one without somewhere to say so.
    """
    result = await ventures.directory(conn)
    return {"as_of": datetime.now(UTC).isoformat(), **result}


# =================================================== write: venture directory

class NewVentureRequest(BaseModel):
    display_name: str = Field(min_length=1)
    slug: str | None = None
    category: str = Field(min_length=1)
    environment: str = "sandbox"


@app.post("/api/ventures", status_code=201)
async def create_venture(body: NewVentureRequest, conn: DB, me: ME) -> dict[str, Any]:
    """Register a venture in draft.

    Requires `compliance_officer`. Creating a venture is not operating one: it commits
    a slug that every venture-scoped table will key on for the rest of its life, and a
    venture operator is scoped to a venture that does not exist yet.

    Draft means no Pack, and therefore no manifest, no runtime config and nothing to
    grant against. The inability to receive grants is structural rather than a flag.
    """
    humans.authorize(me, required_role="compliance_officer")
    try:
        slug = await ventures.create(
            conn,
            slug=body.slug or ventures.slugify(body.display_name),
            display_name=body.display_name,
            category=body.category,
            environment=body.environment,
            created_by=me.human_id,
        )
    except ventures.VentureError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_venture_created",
        {"slug": slug, "display_name": body.display_name,
         "category": body.category, "environment": body.environment},
        slug,
    )
    return {
        "slug": slug,
        "status": "draft",
        "note": (
            "Draft. Author a Business Pack before this venture can be validated, "
            "provisioned or granted anything."
        ),
    }


class LifecycleRequest(BaseModel):
    state: str
    reason: str = Field(min_length=1)


@app.post("/api/ventures/{slug}/lifecycle")
async def set_venture_lifecycle(
    slug: str, body: LifecycleRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Archive a venture, or bring one back.

    Archiving does not delete anything and does not revoke anything - a venture's grants
    and its ledger outlive the decision to stop operating it, and collapsing the two
    would make archiving a silent way to pull authority with no revocation record.
    """
    humans.authorize(me, required_role="compliance_officer", venture_id=slug)
    try:
        await ventures.set_lifecycle(
            conn, slug=slug, state=body.state, actor=me.human_id
        )
    except ventures.VentureError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_venture_lifecycle_changed",
        {"slug": slug, "state": body.state, "reason": body.reason}, slug,
    )
    return {"slug": slug, "state": body.state}

# ====================================================== write: pack directory

class DraftPackRequest(BaseModel):
    yaml_source: str = Field(min_length=1)
    pack_version: str = "0.1.0"


@app.post("/api/packs/draft", status_code=201)
async def save_draft(body: DraftPackRequest, conn: DB, me: ME) -> dict[str, Any]:
    """Store a Pack as a draft. Drafts cannot provision.

    Not by a check - by construction. `packs.live` never returns a draft, so Gate 1
    cannot find one and nothing downstream can generate from it.

    The response carries the validator report, because a draft that has not been
    validated is the state this page exists to make impossible to mistake for a
    working one.
    """
    try:
        parsed = packs.parse_only(body.yaml_source)
    except packs.PackStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    humans.authorize(me, required_role="venture_operator", venture_id=parsed.venture_id)

    live = await packs.live(conn, parsed.venture_id)
    stored = await packs.store(
        conn, yaml_source=body.yaml_source, pack_version=body.pack_version,
        authored_by=me.human_id, publish=False,
    )
    report = await validate_pack(parsed, conn)

    await _audit_human_action(
        me, "console_pack_draft_saved",
        {"pack_version": stored.pack_version, "content_hash": stored.content_hash,
         "failing_rules": [r.rule_id for r in report.failures]},
        stored.venture_id,
    )
    return {
        "venture_id": stored.venture_id,
        "pack_version": stored.pack_version,
        "content_hash": stored.content_hash,
        "has_live_pack": live is not None,
        "validation": {
            "failures": _rule_rows(report),
            "failing": [r.rule_id for r in report.failures],
            "rules_checked": len(report.results),
        },
        "note": (
            "Saved as a draft. A draft cannot provision: `packs.live` does not return "
            "it, so Gate 1 cannot find it."
            + (
                " This venture already has a live Pack; publishing this draft will "
                "supersede it."
                if live is not None else ""
            )
        ),
    }


@app.post("/api/packs/{venture_id}/publish")
async def publish_pack_draft(
    venture_id: str, conn: DB, me: ME
) -> dict[str, Any]:
    """Promote the draft to live.

    Publishing does not start a run, and does not require a clean report - Gate 2
    refuses a failing Pack in the run, where refusing means something. What it does do
    is change what the next run provisions, and void every Gate 10 signature taken
    against the artifacts the previous version generated.
    """
    humans.authorize(me, required_role="venture_operator", venture_id=venture_id)
    try:
        stored = await packs.publish_draft(
            conn, venture_id, published_by=me.human_id
        )
    except packs.PackStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _audit_human_action(
        me, "console_pack_published",
        {"pack_version": stored.pack_version, "content_hash": stored.content_hash},
        venture_id,
    )
    return {
        "venture_id": stored.venture_id,
        "pack_version": stored.pack_version,
        "content_hash": stored.content_hash,
        "note": (
            "Live. Any Gate 10 signature taken against the previous version's artifacts "
            "is now void by comparison - nothing revoked it, it stopped matching."
        ),
    }

class RosterEntry(BaseModel):
    village_agent_ref: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    department: str = Field(min_length=1)


class RosterRequest(BaseModel):
    agents: list[RosterEntry]


@app.post("/api/agents/roster/preview")
async def preview_roster(
    body: RosterRequest, conn: DB, _me: ME
) -> dict[str, Any]:
    """What importing this roster would change. **Writes nothing.**

    Separate from applying it because an import can remove agents, and an agent that
    leaves the Village holding grants is a revocation somebody has to perform rather
    than a row that quietly disappears.
    """
    try:
        parsed = roster.parse_roster(
            [entry.model_dump() for entry in body.agents],
            known_departments=await departments.names(),
        )
        return await roster.diff(conn, parsed)
    except roster.RosterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/agents/roster")
async def import_roster(
    body: RosterRequest, conn: DB, me: ME
) -> dict[str, Any]:
    """Apply a roster the operator has already seen a diff for."""
    try:
        parsed = roster.parse_roster(
            [entry.model_dump() for entry in body.agents],
            known_departments=await departments.names(),
        )
        return await roster.apply(conn, parsed, human=me)
    except roster.RosterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class IdentityRequest(BaseModel):
    village_agent_refs: list[str] = Field(min_length=1)


@app.post("/api/agents/identities", status_code=201)
async def issue_identities(
    body: IdentityRequest, conn: DB, me: ME
) -> dict[str, Any]:
    """Make Village agents appointable.

    Not a create. The agents already exist; this records that The Office recognises
    them. Refused for an agent the roster has never reported - an identity for somebody
    the Village has not mentioned is The Office inventing a colleague.
    """
    issued: list[dict[str, str]] = []
    refused: list[dict[str, str]] = []

    for ref in body.village_agent_refs:
        try:
            office_agent_id = await roster.issue_identity(conn, ref, human=me)
            issued.append(
                {"village_agent_ref": ref, "office_agent_id": str(office_agent_id)}
            )
        except roster.RosterError as exc:
            # One refusal does not abandon the rest: a bulk issue over a department
            # where one agent already has an identity should do the other eleven.
            refused.append({"village_agent_ref": ref, "reason": str(exc)})

    return {"issued": issued, "refused": refused}


class RegisterAgentRequest(BaseModel):
    village_agent_ref: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    department: str = Field(min_length=1)


@app.post("/api/agents/village", status_code=201)
async def register_village_agent(
    body: RegisterAgentRequest, conn: DB, me: ME
) -> dict[str, str]:
    """Record a Village agent an import cannot see.

    Named for what it does. "Add agent" would imply The Office creates agents, which it
    does not, and the control would become a second source of truth for who exists.
    `village_agent_ref` is required: without it there is nothing for a later import to
    reconcile against, and the row becomes an orphan no roster can confirm or retire.
    """
    try:
        await roster.register_village_agent(
            conn,
            village_agent_ref=body.village_agent_ref,
            agent_name=body.agent_name,
            department=body.department,
            human=me,
        )
    except roster.RosterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "registered", "village_agent_ref": body.village_agent_ref}


__all__ = ["NotAuthorized", "app"]
