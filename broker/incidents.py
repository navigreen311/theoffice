"""Incident detection, and the one thing that closes one.

An incident is a *detection*, not a workflow. Triage, containment, disclosure and
post-mortem live in the console (Part 9). An incident row is never edited: a later
finding is a new incident referencing the same trace, which is why office_app holds
INSERT and SELECT here and nothing else.

`resolve` respects that rather than working around it. Closing an incident writes a row
to `incident_resolution` and leaves the incident untouched, so "resolved" is the
presence of an account of what was done rather than a flag somebody set.
"""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import incident_taxonomy as taxonomy
from broker.db import connection


class IncidentError(Exception):
    """The incident could not be recorded as asked."""


async def raise_incident(
    *,
    severity: str,
    kind: str,
    venture_id: str | None = None,
    office_agent_id: uuid.UUID | None = None,
    forge_id: str | None = None,
    module_id: str | None = None,
    trace_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    detection_source: str = "control_sweep",
    reported_by: uuid.UUID | None = None,
) -> uuid.UUID:
    """Record a detection.

    `detection_source` defaults to `control_sweep` because every caller in this package
    is a control or the broker itself. A human filing an external report or a regulator
    inquiry passes their own source and their own id, and the schema refuses the
    combination where a human source has nobody attached to it: an incident somebody
    filed must never read as one a control caught.
    """
    from psycopg.types.json import Jsonb

    if kind not in taxonomy.BY_KIND:
        raise IncidentError(
            f"{kind!r} is not a published incident kind. The list is in "
            "broker/incident_taxonomy.py, and a kind nothing publishes is a free-text "
            "column with a schema-shaped name."
        )
    if severity not in taxonomy.SEVERITIES:
        raise IncidentError(f"{severity!r} is not one of {', '.join(taxonomy.SEVERITIES)}")

    incident_id = uuid.uuid4()
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO incident
              (incident_id, severity, kind, venture_id, office_agent_id,
               forge_id, module_id, trace_id, detail, detection_source, reported_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                incident_id, severity, kind, venture_id, office_agent_id,
                forge_id, module_id, trace_id, Jsonb(detail or {}),
                detection_source, reported_by,
            ),
        )
        await conn.commit()
    return incident_id


async def file_by_hand(
    conn: AsyncConnection,
    *,
    severity: str,
    kind: str,
    detection_source: str,
    summary: str,
    reported_by: uuid.UUID,
    venture_id: str | None = None,
) -> uuid.UUID:
    """File an incident a person noticed.

    The blueprint names three detection sources - agent flag, external report, regulator
    inquiry - and only the first can arrive on its own. There was no way to record the
    other two, so a regulator's question and a client's complaint lived in somebody's
    inbox while the page showed an empty list and called it quiet.

    Takes the caller's connection rather than opening its own, unlike `raise_incident`:
    this one runs inside a request that has already authorised somebody, and the audit
    entry for it belongs in the same transaction.
    """
    if detection_source not in ("external_report", "regulator_inquiry"):
        raise IncidentError(
            f"{detection_source!r} is not a source a person files. Automatic detections "
            "come from the controls, and relabelling one as hand-filed would hide which "
            "of the two actually found it."
        )
    if kind not in taxonomy.HUMAN_KIND_NAMES:
        raise IncidentError(
            f"{kind!r} is raised by a control, not by a person. Filing it by hand would "
            f"claim a check ran that did not: use one of "
            f"{', '.join(taxonomy.HUMAN_KIND_NAMES)}."
        )
    if not summary.strip():
        raise IncidentError(
            "an incident needs an account of what was seen; a kind and a severity with "
            "nothing attached is a label"
        )
    if severity not in taxonomy.SEVERITIES:
        raise IncidentError(f"{severity!r} is not one of {', '.join(taxonomy.SEVERITIES)}")

    from psycopg.types.json import Jsonb

    incident_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO incident
              (incident_id, severity, kind, venture_id, detail, detection_source,
               reported_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                incident_id, severity, kind, venture_id,
                Jsonb({"summary": summary.strip()}), detection_source, reported_by,
            ),
        )
        # The detection is itself the first stage of the response, and writing it here
        # means the timeline starts with what was seen rather than with the first person
        # who happened to open the page.
        await cur.execute(
            "INSERT INTO incident_account (incident_id, stage, account, written_by) "
            "VALUES (%s, 'detection', %s, %s)",
            (incident_id, summary.strip(), reported_by),
        )
    await conn.commit()
    return incident_id


async def append_account(
    conn: AsyncConnection,
    *,
    incident_id: uuid.UUID,
    stage: str,
    account: str,
    written_by: uuid.UUID,
) -> int:
    """Add one account to an incident's response timeline.

    Append, never edit - the table refuses UPDATE and DELETE by trigger. A stage that
    was accounted for wrongly is corrected by appending a later account to the same
    stage, so the timeline shows both what was believed and when that changed.
    """
    if stage not in taxonomy.STAGE_NAMES:
        raise IncidentError(
            f"{stage!r} is not one of Part 9's stages: "
            f"{', '.join(taxonomy.STAGE_NAMES)}"
        )
    if not account.strip():
        raise IncidentError(
            "an account of a stage needs content; marking a stage done with nothing "
            "attached is the status change this table exists to prevent"
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT incident_id FROM incident WHERE incident_id = %s", (incident_id,)
        )
        if await cur.fetchone() is None:
            raise IncidentError(f"no incident {incident_id}")

        await cur.execute(
            "INSERT INTO incident_account (incident_id, stage, account, written_by) "
            "VALUES (%s, %s, %s, %s) RETURNING account_id",
            (incident_id, stage, account.strip(), written_by),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None
    return int(row["account_id"])


async def resolve(
    conn: AsyncConnection,
    *,
    incident_id: uuid.UUID,
    resolution: str,
    resolved_by: uuid.UUID,
) -> dict[str, Any]:
    """Close an incident with an account of what was done, as an APPEND.

    `incident` is append-only by design and says so in its own table comment: "an
    incident is never edited; a later finding is a new incident referencing the trace."
    That decision predates this function by several phases and is right - a detection
    that can be rewritten is worth less than the row it sits in, and severity is exactly
    the field somebody under pressure would want to lower. So resolution is a separate
    row and the incident is untouched.

    Resolving twice is refused rather than overwriting who closed it and why. A double
    click and a disagreement look identical to the database, and both deserve an error.

    Returns the incident, so the caller can audit against its real severity and venture
    rather than against what a request body claimed.
    """
    if not resolution.strip():
        raise IncidentError(
            "resolving an incident requires an account of what was done; 'resolved' "
            "with nothing attached is a status change"
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT i.incident_id, i.severity, i.kind, i.venture_id, r.resolved_at
            FROM incident i
            LEFT JOIN incident_resolution r ON r.incident_id = i.incident_id
            WHERE i.incident_id = %s
            """,
            (incident_id,),
        )
        incident = await cur.fetchone()

    if incident is None:
        raise IncidentError(f"no incident {incident_id}")
    if incident["resolved_at"] is not None:
        raise IncidentError(
            "already resolved; a second resolution would replace who closed it and why"
        )

    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO incident_resolution (incident_id, resolution, resolved_by) "
            "VALUES (%s, %s, %s)",
            (incident_id, resolution, resolved_by),
        )
    await conn.commit()
    return dict(incident)


async def detail(conn: AsyncConnection, incident_id: uuid.UUID) -> dict[str, Any] | None:
    """One incident: the detection as recorded, and everything appended since.

    Two separate things, kept visibly separate. The detection is what was seen and is
    never editable. The accounts are what people did about it, each with a name and a
    time. A screen that merged them would let the response quietly rewrite the finding,
    which is the whole reason `incident` refuses UPDATE.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT i.incident_id::text AS incident_id, i.severity, i.kind,
                   i.venture_id, i.office_agent_id::text AS office_agent_id,
                   i.forge_id, i.module_id, i.trace_id::text AS trace_id,
                   i.detail, i.raised_at, i.detection_source,
                   i.reported_by::text AS reported_by,
                   reporter.display_name AS reported_by_name,
                   agent.agent_name,
                   r.resolution, r.resolved_at, r.resolved_by::text AS resolved_by,
                   closer.display_name AS resolved_by_name
            FROM incident i
            LEFT JOIN incident_resolution r ON r.incident_id = i.incident_id
            LEFT JOIN office_human reporter ON reporter.human_id = i.reported_by
            LEFT JOIN office_human closer ON closer.human_id = r.resolved_by
            LEFT JOIN office_agent_identity agent
                   ON agent.office_agent_id = i.office_agent_id
            WHERE i.incident_id = %s
            """,
            (incident_id,),
        )
        incident = await cur.fetchone()
        if incident is None:
            return None

        await cur.execute(
            """
            SELECT a.account_id, a.stage, a.account, a.written_at,
                   a.written_by::text AS written_by, h.display_name AS written_by_name
            FROM incident_account a
            JOIN office_human h ON h.human_id = a.written_by
            WHERE a.incident_id = %s
            ORDER BY a.written_at, a.account_id
            """,
            (incident_id,),
        )
        accounts = [dict(row) for row in await cur.fetchall()]

        # Calls sharing this trace. The link a responder actually follows: an incident
        # names a trace, and the question is always what else happened under it.
        linked: list[dict[str, Any]] = []
        if incident["trace_id"]:
            await cur.execute(
                """
                SELECT call_id::text AS call_id, office_agent_id::text AS office_agent_id,
                       forge_id, module_id, status_code, ts_start, venture_id
                FROM agent_call_ledger
                WHERE trace_id = %s
                ORDER BY ts_start
                LIMIT 50
                """,
                (incident["trace_id"],),
            )
            linked = [dict(row) for row in await cur.fetchall()]

    result = dict(incident)

    # Each stage is either accounted for or outstanding, said explicitly. A stage
    # rendered as an empty row reads as "nothing to say"; it means nobody has said it.
    by_stage: dict[str, list[dict[str, Any]]] = {name: [] for name in taxonomy.STAGE_NAMES}
    for account in accounts:
        by_stage[account["stage"]].append(account)

    result["stages"] = [
        {
            "stage": name,
            "label": label,
            "hint": hint,
            "accounted": bool(by_stage[name]),
            "accounts": by_stage[name],
        }
        for name, label, hint in taxonomy.STAGES
    ]
    result["accounts"] = accounts
    result["linked_calls"] = linked
    result["kind_meaning"] = (
        taxonomy.BY_KIND[result["kind"]].meaning if result["kind"] in taxonomy.BY_KIND else ""
    )
    return result


async def overview(conn: AsyncConnection) -> dict[str, Any]:
    """Freshness, aging and the cross-venture pattern.

    The page used to tell the reader to go and check control freshness somewhere else.
    The answer was already computable here, and a page that knows the answer and
    suggests looking elsewhere is deferring rather than reporting.

    Aggregation by kind is the reason the spec asks for a cross-venture view: three
    `phi_flush_failure` incidents in one venture is an outage, three across two ventures
    is a pattern, and the page that lists them one per row shows neither.
    """
    from broker import sweeps

    freshness = await sweeps.freshness(conn)
    stale = sorted(
        kind for kind, state in freshness.items() if state.get("state") != "fresh"
    )
    never_ran = sorted(
        kind for kind, state in freshness.items() if state.get("state") == "never_run"
    )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT i.kind, i.severity, i.venture_id, i.raised_at,
                   (r.incident_id IS NOT NULL) AS resolved
            FROM incident i
            LEFT JOIN incident_resolution r ON r.incident_id = i.incident_id
            """
        )
        rows = [dict(row) for row in await cur.fetchall()]

    open_rows = [row for row in rows if not row["resolved"]]

    # Grouped by kind, with the ventures each spans. The venture count is the signal.
    grouped: dict[str, dict[str, Any]] = {}
    for row in open_rows:
        bucket = grouped.setdefault(
            row["kind"],
            {"kind": row["kind"], "open": 0, "ventures": set(), "worst": "LOW"},
        )
        bucket["open"] += 1
        if row["venture_id"]:
            bucket["ventures"].add(row["venture_id"])
        if taxonomy.SEVERITIES.index(row["severity"]) > taxonomy.SEVERITIES.index(
            bucket["worst"]
        ):
            bucket["worst"] = row["severity"]

    by_kind = sorted(
        (
            {
                "kind": bucket["kind"],
                "label": taxonomy.BY_KIND[bucket["kind"]].label
                if bucket["kind"] in taxonomy.BY_KIND
                else bucket["kind"],
                "open": bucket["open"],
                "ventures": sorted(bucket["ventures"]),
                "worst": bucket["worst"],
                # The whole point of the grouping, stated rather than left to be counted.
                "crosses_ventures": len(bucket["ventures"]) > 1,
            }
            for bucket in grouped.values()
        ),
        key=lambda item: (-len(item["ventures"]), -item["open"], item["kind"]),
    )

    return {
        "controls": {
            "freshness": freshness,
            "stale": stale,
            "never_ran": never_ran,
            "all_fresh": not stale,
            "total": len(freshness),
        },
        "open_count": len(open_rows),
        "total_count": len(rows),
        "by_severity": {
            severity: sum(1 for row in open_rows if row["severity"] == severity)
            for severity in taxonomy.SEVERITIES
        },
        "by_kind": by_kind,
    }
