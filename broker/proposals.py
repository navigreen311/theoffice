"""Trust tiers and the proposal queue.

Master prompt §1.2. Three tiers:

  auto_execute  the agent acts; the Forge is called
  propose       the agent asks; a human decides
  suggest       the agent recommends; a human decides

`propose` and `suggest` both create a proposal and touch no Forge. They are separate
tiers because the *content* differs - a proposal is an action awaiting approval, a
suggestion is advice - and Part 10.1 requires that certification states and tiers are
never collapsed. Storing which one it was preserves that distinction for the console
even though the runtime effect is identical today.

**Certified tier caps declared tier** (Part 10.1): the Pack declares a ceiling,
SimForge sets the actual, and the lower wins. Phase 2 made that reconciliation happen
in `resolve_grant` on every call rather than once at grant issuance, so a cert
downgraded after the grant was written takes effect on the next call - the same reason
revocation is not cached. By the time the call path reads `grant.trust_tier` it is
already capped; the tier gate must not re-derive it.

The soft budget cap lowers the tier further, engagement-wide (Part 12).

Rubber-stamp detection (Part 14): approvals faster than five seconds are recorded and
flagged. A human clicking approve in three seconds has not read a bank-statement
payload, and a trust tier that is really a click-through is worse than no tier at all
because it looks like oversight.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from broker import incidents

AUTO_EXECUTE = "auto_execute"
PROPOSE = "propose"
SUGGEST = "suggest"

RUBBER_STAMP_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class Proposal:
    proposal_id: uuid.UUID
    status: str
    trust_tier: str


def effective_tier(declared_tier: str, *, soft_capped: bool) -> str:
    """The tier that actually applies to this call.

    Part 12's soft-cap rung is "all auto_execute downgrades to propose across the
    engagement" - a tier change, not a separate gate. Expressing it here means one
    enforcement point instead of two that can drift apart.
    """
    if soft_capped and declared_tier == AUTO_EXECUTE:
        return PROPOSE
    return declared_tier


async def submit(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    venture_id: str,
    forge_id: str,
    module_id: str,
    task_id: str,
    trust_tier: str,
    payload: Any,
    payload_hash: str,
    idempotency_key: str,
    trace_id: uuid.UUID,
) -> uuid.UUID:
    """Create a proposal. The Forge is not called."""
    proposal_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO proposal
              (proposal_id, office_agent_id, venture_id, forge_id, module_id, task_id,
               trust_tier, payload, payload_hash, idempotency_key, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                proposal_id, office_agent_id, venture_id, forge_id, module_id, task_id,
                trust_tier, Jsonb(payload), payload_hash, idempotency_key, trace_id,
            ),
        )
    await conn.commit()
    return proposal_id


async def decide(
    conn: AsyncConnection,
    *,
    proposal_id: uuid.UUID,
    approve: bool,
    decided_by: uuid.UUID,
    reason: str | None = None,
) -> Proposal:
    """Approve or reject. Records how long the human took.

    `review_seconds` is computed from `created_at` in the database rather than
    passed in, so a caller cannot report a review time it did not take.
    """
    status = "approved" if approve else "rejected"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE proposal
            SET status = %s,
                decided_at = now(),
                decided_by = %s,
                decision_reason = %s,
                review_seconds = EXTRACT(EPOCH FROM (now() - created_at))
            WHERE proposal_id = %s AND status = 'pending'
            RETURNING proposal_id, status, trust_tier, review_seconds,
                      venture_id, office_agent_id
            """,
            (status, decided_by, reason, proposal_id),
        )
        row = await cur.fetchone()
    await conn.commit()

    if row is None:
        raise LookupError(f"no pending proposal {proposal_id}")

    if approve and float(row["review_seconds"]) < RUBBER_STAMP_SECONDS:
        await incidents.raise_incident(
            severity="MEDIUM",
            kind="rubber_stamp_approval",
            venture_id=row["venture_id"],
            office_agent_id=row["office_agent_id"],
            detail={
                "proposal_id": str(proposal_id),
                "decided_by": str(decided_by),
                "review_seconds": float(row["review_seconds"]),
                "threshold_seconds": RUBBER_STAMP_SECONDS,
            },
        )

    return Proposal(
        proposal_id=row["proposal_id"],
        status=row["status"],
        trust_tier=row["trust_tier"],
    )


async def mark_executed(
    conn: AsyncConnection, *, proposal_id: uuid.UUID, call_id: uuid.UUID
) -> None:
    """Link an approved proposal to the call that carried it out.

    Only an approved proposal can become executed, so a rejected one cannot be
    quietly run by a second code path.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE proposal SET status = 'executed', executed_call_id = %s "
            "WHERE proposal_id = %s AND status = 'approved'",
            (call_id, proposal_id),
        )
        if cur.rowcount == 0:
            raise LookupError(f"proposal {proposal_id} is not approved")
    await conn.commit()


async def get(conn: AsyncConnection, proposal_id: uuid.UUID) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM proposal WHERE proposal_id = %s", (proposal_id,))
        return await cur.fetchone()
