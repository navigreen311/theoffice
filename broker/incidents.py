"""Incident detection.

An incident is a *detection*, not a workflow. Triage, containment, disclosure and
post-mortem live in the console (Part 9). An incident row is never edited: a later
finding is a new incident referencing the same trace, which is why office_app holds
INSERT and SELECT here and nothing else.
"""

from __future__ import annotations

import uuid
from typing import Any

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
