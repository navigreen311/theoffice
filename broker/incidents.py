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

from broker.db import connection


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
) -> uuid.UUID:
    from psycopg.types.json import Jsonb

    incident_id = uuid.uuid4()
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO incident
              (incident_id, severity, kind, venture_id, office_agent_id,
               forge_id, module_id, trace_id, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                incident_id, severity, kind, venture_id, office_agent_id,
                forge_id, module_id, trace_id, Jsonb(detail or {}),
            ),
        )
        await conn.commit()
    return incident_id


class IncidentError(Exception):
    """The incident could not be resolved as asked."""


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
