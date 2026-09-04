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

from broker import audit, incidents

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
    # APPROVING DOES NOT EXECUTE, and the record says so.
    #
    # `mark_executed` exists and has no production caller: nothing reads an
    # approved proposal and makes the call it describes. Approval therefore sets a
    # status and stops, which is indistinguishable from a queue that has not got to
    # it yet - so the decision reason carries the fact.
    #
    # Recorded here rather than refused, because rejecting IS complete and an
    # approval is still a real decision worth having on the record. What is missing
    # is the execution, and the reason column is where a reader looks.
    status = "approved" if approve else "rejected"
    if approve:
        note = (
            "APPROVAL DOES NOT EXECUTE - no path exists from an approved proposal "
            "to a Forge call. The act must be carried out by a person."
        )
        reason = f"{reason} [{note}]" if reason else note
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


# --------------------------------------------------------------------- expiry

async def expire_overdue(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Expire proposals whose deadline has passed. **Never approves one.**

    A queue that drains itself looks like a queue being worked, which is exactly why
    auto-approval on timeout is the most attractive shortcut on this page and exactly why
    it does not exist. An agent below `auto_execute` asked to act, nobody answered, and
    it did not act - that is the correct outcome. A timeout that approved would make the
    trust tier a delay rather than a decision.

    The task fails and both facts are audited.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE proposal
            SET status = 'expired'
            WHERE status = 'pending' AND expires_at <= now()
            RETURNING proposal_id, office_agent_id, venture_id, forge_id, module_id,
                      task_id, created_at, expires_at
            """
        )
        expired = [dict(r) for r in await cur.fetchall()]
    await conn.commit()

    for row in expired:
        await audit.write_event(
            event_type="proposal_expired",
            # No human acted - that is the point of the entry - so the actor is the
            # agent whose proposal this was, the way `shifts` records a system act
            # against the agent it concerns.
            actor_type="system", actor_id=row["office_agent_id"],
            venture_id=row["venture_id"],
            subject={
                "proposal_id": str(row["proposal_id"]),
                "task_id": row["task_id"],
                "module": f"{row['forge_id']}/{row['module_id']}",
                # Said in the record, not only in the docs. Somebody reading this entry
                # later needs to know the task failed rather than quietly succeeded.
                "outcome": "task failed; the proposal was never approved",
            },
        )
    return expired


# ---------------------------------------------------------------------- the queue

async def queue(conn: AsyncConnection) -> dict[str, Any]:
    """Everything the approvals page needs, with the empty state's reason computed.

    The old empty state gave one explanation for an empty queue - that the agents' trust
    tiers might be set to `auto_execute` - which is a real cause and was not this cause.
    No agent held a grant to any Forge and none had ever made a call: the queue was empty
    because nothing could act, and sending a reader to inspect trust tiers wasted their
    time and implied the system was further along than it was.

    So the reason is derived from what is actually true, and there is no generic fallback
    that could be wrong.
    """
    from broker import packs

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT p.proposal_id::text AS proposal_id, p.office_agent_id::text
                     AS office_agent_id,
                   p.venture_id, p.forge_id, p.module_id, p.task_id, p.trust_tier,
                   p.payload, p.payload_hash, p.created_at, p.expires_at,
                   p.trace_id::text AS trace_id,
                   i.agent_name, i.department,
                   m.compliance_flags_implied, m.is_mutating,
                   m.module_name
            FROM proposal p
            LEFT JOIN office_agent_identity i
                   ON i.office_agent_id = p.office_agent_id
            LEFT JOIN forge_module_registry m
                   ON m.forge_id = p.forge_id AND m.module_id = p.module_id
            WHERE p.status = 'pending'
            -- Oldest first, always. Newest-first invites cherry-picking the easy ones,
            -- and the item that has waited longest is the one closest to expiring.
            ORDER BY p.created_at
            """
        )
        pending = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT p.proposal_id::text AS proposal_id, p.venture_id, p.forge_id,
                   p.module_id, p.status, p.decision_reason, p.review_seconds,
                   p.decided_at, p.payload, p.payload_hash,
                   p.office_agent_id::text AS office_agent_id,
                   i.agent_name, h.display_name AS reviewer
            FROM proposal p
            LEFT JOIN office_agent_identity i
                   ON i.office_agent_id = p.office_agent_id
            LEFT JOIN office_human h ON h.human_id = p.decided_by
            WHERE p.status <> 'pending'
            ORDER BY p.decided_at DESC NULLS LAST, p.created_at DESC
            LIMIT 100
            """
        )
        history = [dict(r) for r in await cur.fetchall()]

        # Today's decisions, for the metrics strip and the capacity headroom.
        await cur.execute(
            """
            SELECT h.display_name AS reviewer,
                   count(*)                                        AS decisions,
                   count(*) FILTER (WHERE p.status = 'approved')   AS approvals,
                   count(*) FILTER (
                     WHERE p.status = 'approved'
                       AND p.review_seconds < %s
                   )                                                AS fast_approvals,
                   percentile_cont(0.5) WITHIN GROUP (
                     ORDER BY p.review_seconds
                   )                                                AS median_seconds
            FROM proposal p
            LEFT JOIN office_human h ON h.human_id = p.decided_by
            WHERE p.decided_at >= date_trunc('day', now())
            GROUP BY h.display_name
            """,
            (RUBBER_STAMP_SECONDS,),
        )
        today_by_reviewer = [dict(r) for r in await cur.fetchall()]

        # Why the queue is empty, when it is. These are the facts that distinguish "no
        # reviewer is needed" from "nothing in this system can act yet".
        await cur.execute(
            """
            SELECT
              (SELECT count(*) FROM agent_forge_grant
                WHERE revoked_at IS NULL)                       AS live_grants,
              (SELECT count(*) FROM agent_forge_grant
                WHERE revoked_at IS NULL AND trust_tier <> 'auto_execute')
                                                                AS grants_below_auto,
              (SELECT count(*) FROM agent_call_ledger)          AS calls_ever,
              (SELECT count(*) FROM proposal
                WHERE created_at >= date_trunc('day', now()))   AS proposals_today
            """
        )
        state = dict(await cur.fetchone() or {})

        await cur.execute("SELECT venture_id FROM business_pack WHERE status = 'live'")
        live_ventures = [r["venture_id"] for r in await cur.fetchall()]

    # Reviewer capacity comes from each venture's live Pack, which is where
    # `human_capacity` is declared and where V13 reads it from. There is no reviewer
    # table: the Pack is the source of truth for who reviews and how much they can take.
    reviewers: list[dict[str, Any]] = []
    decisions_by_name = {
        row["reviewer"]: row for row in today_by_reviewer if row["reviewer"]
    }
    for venture_id in live_ventures:
        pack = await packs.live(conn, venture_id)
        if pack is None:
            continue
        for human in pack.pack.human_capacity:
            done = decisions_by_name.get(human.human_name, {})
            decisions = int(done.get("decisions") or 0)
            reviewers.append({
                "venture_id": venture_id,
                "name": human.human_name,
                "role": human.role,
                "coverage_hours": human.coverage_hours,
                "timezone": human.timezone,
                "backup_human": human.backup_human,
                "max_daily_approvals": human.max_daily_approvals,
                "median_review_minutes": human.median_review_minutes,
                "decisions_today": decisions,
                "remaining_today": max(0, human.max_daily_approvals - decisions),
                "median_seconds_today": (
                    float(done["median_seconds"])
                    if done.get("median_seconds") is not None else None
                ),
                # The Pack names a reviewer; `decided_by` names an office_human. The
                # only link between them is the display name, and when it does not match
                # the page says the reviewer has no decisions rather than inventing a
                # join.
                "matched_to_a_human": human.human_name in decisions_by_name,
            })

    decisions_today = sum(int(r["decisions"] or 0) for r in today_by_reviewer)
    approvals_today = sum(int(r["approvals"] or 0) for r in today_by_reviewer)
    fast_today = sum(int(r["fast_approvals"] or 0) for r in today_by_reviewer)
    medians = [
        float(r["median_seconds"]) for r in today_by_reviewer
        if r["median_seconds"] is not None
    ]

    capacity_remaining = sum(int(r["remaining_today"]) for r in reviewers)

    return {
        "pending": pending,
        "history": history,
        "reviewers": reviewers,
        "metrics": {
            "decisions_today": decisions_today,
            "approvals_today": approvals_today,
            "approval_rate": (
                approvals_today / decisions_today if decisions_today else None
            ),
            "median_seconds": (sum(medians) / len(medians)) if medians else None,
            "under_threshold": fast_today,
            "threshold_seconds": RUBBER_STAMP_SECONDS,
            "by_reviewer": today_by_reviewer,
        },
        "capacity": {
            "reviewers": len(reviewers),
            "remaining_today": capacity_remaining,
            "pending": len(pending),
            # The V13 question, asked against today rather than against the Pack's
            # estimate: more pending than anybody can still decide means the overflow
            # will not be reviewed before the window closes.
            "over_capacity": len(pending) > capacity_remaining and len(pending) > 0,
        },
        "state": {
            "live_grants": int(state.get("live_grants") or 0),
            "grants_below_auto": int(state.get("grants_below_auto") or 0),
            "calls_ever": int(state.get("calls_ever") or 0),
            "proposals_today": int(state.get("proposals_today") or 0),
        },
        "empty_reason": _empty_reason(state, decisions_today, medians),
    }


def _empty_reason(
    state: dict[str, Any], decisions_today: int, medians: list[float]
) -> str | None:
    """Why the queue is empty, in this system's actual terms. `None` when it is not.

    Never a generic sentence. The old one named a cause that was real in general and
    wrong here, which is worse than saying nothing: it sent a reader to check trust tiers
    on a system where no agent held a grant at all.
    """
    live_grants = int(state.get("live_grants") or 0)
    below_auto = int(state.get("grants_below_auto") or 0)
    calls = int(state.get("calls_ever") or 0)
    today = int(state.get("proposals_today") or 0)

    if today and decisions_today >= today:
        median = f"{(sum(medians) / len(medians)):.0f}s" if medians else "not recorded"
        return (
            f"All {today} proposals today have been decided. "
            f"Median decision time: {median}."
        )
    if live_grants == 0:
        return (
            "Nothing pending - and nothing could be. No agent holds a grant to any "
            "Forge, and no agent has ever made a call. An empty queue here reflects a "
            "system that has not started operating, not reviewers who are caught up."
        )
    if below_auto == 0:
        return (
            "Every live grant is at auto_execute, so no agent has to ask. An agent at "
            "auto_execute acts without proposing."
        )
    if calls == 0:
        return "Agents can propose but none has acted yet."
    return (
        "Nothing is pending. Agents below auto_execute have acted before, so proposals "
        "can arrive here."
    )
