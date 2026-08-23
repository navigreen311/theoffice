"""Audit writes.

The pre-call entry records *intent*. It must exist before the Forge is contacted,
so that a call which then crashes the process still left a trace. The ledger row
records *outcome* and is written after. A call that appears in audit with no
ledger row is precisely the signal incident response needs - collapsing the two
into one post-call write would erase it.

Writes go through their own connection, not the caller's transaction. If the
audit shared a transaction with anything that later rolled back, the audit entry
would vanish with it, which defeats the purpose of writing it first.
"""

from __future__ import annotations

import uuid
from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from broker.db import connection

_INSERT = """
INSERT INTO audit_log (event_type, actor_type, actor_id, venture_id, subject, trace_id)
VALUES (%(event_type)s, %(actor_type)s, %(actor_id)s, %(venture_id)s,
        %(subject)s, %(trace_id)s)
RETURNING audit_id
"""


async def write_event(
    *,
    event_type: str,
    actor_type: str,
    actor_id: uuid.UUID,
    subject: dict[str, Any],
    venture_id: str | None = None,
    trace_id: uuid.UUID | None = None,
    conn: AsyncConnection | None = None,
) -> int:
    """Append one audit entry. Returns its audit_id.

    Raises on failure rather than returning a falsy value: an audit write that
    fails silently is worse than one that fails loudly, and the caller decides
    whether to fail closed based on compliance flags.
    """
    params = {
        "event_type": event_type,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "venture_id": venture_id,
        "subject": Jsonb(subject),
        "trace_id": trace_id,
    }
    if conn is not None:
        async with conn.cursor() as cur:
            await cur.execute(_INSERT, params)
            row = await cur.fetchone()
            assert row is not None
            return int(row[0])

    async with connection() as own:
        async with own.cursor() as cur:
            await cur.execute(_INSERT, params)
            row = await cur.fetchone()
            assert row is not None
        await own.commit()
        return int(row[0])
