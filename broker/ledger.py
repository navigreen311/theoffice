"""Ledger writes.

Every call gets a row, successful or not. A ledger that only records successes
cannot answer "what did this agent try to do", which is the question asked after
an incident.

`payload_hash` is stored instead of the payload. The ledger is append-only and
long-lived; putting request bodies in it would make every retention and PHI
obligation in the platform apply to the audit store itself.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from broker.db import connection

_INSERT = """
INSERT INTO agent_call_ledger (
    call_id, trace_id, office_agent_id, venture_id, shift_id,
    forge_id, module_id, api_version,
    ts_start, ts_end, latency_ms, status_code,
    tokens_in, tokens_out, usd_cost,
    trust_tier_at_call, compliance_flags_active, data_types_touched,
    idempotency_key, manifest_match, forge_side_ref, payload_hash
) VALUES (
    %(call_id)s, %(trace_id)s, %(office_agent_id)s, %(venture_id)s, %(shift_id)s,
    %(forge_id)s, %(module_id)s, %(api_version)s,
    %(ts_start)s, %(ts_end)s, %(latency_ms)s, %(status_code)s,
    %(tokens_in)s, %(tokens_out)s, %(usd_cost)s,
    %(trust_tier_at_call)s, %(compliance_flags_active)s, %(data_types_touched)s,
    %(idempotency_key)s, %(manifest_match)s, %(forge_side_ref)s, %(payload_hash)s
)
"""


def payload_hash(payload: Any) -> str:
    """Stable hash of a request payload.

    sort_keys because two logically identical payloads must hash the same;
    otherwise reconciliation against Forge-side records produces false mismatches.
    """
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def idempotency_key(task_id: str, module_id: str, payload: Any) -> str:
    """Deterministic key for (task, module, payload).

    Master prompt Part 16: idempotency keys on all mutating calls. Deriving it
    rather than generating a random one is what makes a retry recognisable as a
    retry - a fresh uuid per attempt would defeat the at_most_once guard.
    """
    material = f"{task_id}|{module_id}|{payload_hash(payload)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


async def write_call(**fields: Any) -> None:
    """Append one ledger row. Missing optional fields default to NULL."""
    params: dict[str, Any] = {
        "shift_id": None,
        "ts_end": None,
        "latency_ms": None,
        "status_code": None,
        "tokens_in": None,
        "tokens_out": None,
        "usd_cost": None,
        "compliance_flags_active": [],
        "data_types_touched": [],
        "idempotency_key": None,
        "forge_side_ref": None,
        # Phase 1 computes this properly from the venture Forge Manifest. Until a
        # Pack exists there is nothing to reconcile against, so calls are recorded
        # as declared_only rather than claiming a reconciliation that never ran.
        "manifest_match": "declared_only",
    }
    params.update(fields)

    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(_INSERT, params)
        await conn.commit()


async def has_prior_call(idem_key: str, office_agent_id: uuid.UUID) -> bool:
    """Whether this agent already issued a call with this idempotency key."""
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM agent_call_ledger "
            "WHERE idempotency_key = %s AND office_agent_id = %s LIMIT 1",
            (idem_key, office_agent_id),
        )
        return await cur.fetchone() is not None
