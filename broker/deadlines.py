"""Deadlines pass on their own, and the record says when they passed.

RULED 22 SEPTEMBER 2026 (decisions entries 156 and 157)
=======================================================

    156: *"A deadline passes on its own. A scheduled job expires overdue proposals and
    escalations. Measured: e19ca4ce expired at 05:17:15 and stayed pending until
    10:07:23, when a page load triggered it."*

    157: *"An expiry records when the deadline passed, not when it was noticed.
    Measured: the entry reads 10:07:23, which is when I opened the page."*

WHAT WAS THERE BEFORE
=====================

    `proposals.expire_overdue` was correct and had exactly one caller:
    `GET /api/proposals/queue`. Expiry was therefore **read-triggered**, not
    time-triggered, and nothing scheduled anything.

    Measured on the drill proposal: the deadline passed at 05:17:15 and the row stayed
    `pending` for four hours and fifty minutes, until a page was opened at 10:07:23.
    Two separate defects fell out of that one fact.

        it did not happen        a deadline that only passes when somebody looks is not
                                 a deadline, it is a side effect of attention
        it happened at the wrong an audit entry timestamped 10:07:23 for a deadline that
        time                     passed at 05:17:15 records the observer, not the event

    And the third, which is why entry 156 says "on its own" rather than "reliably": the
    outcome depended on WHO looked first. The queue expires before it reads, so the
    reviewer the proposal was routed to would have had it expired out from under her by
    the act of opening the page she was meant to decide it on.

WHERE THE TIME COMES FROM
=========================

    `expires_at` is the deadline. It is stored per row rather than computed from a
    setting, so the deadline somebody missed is still the deadline that applied - 0021
    says so about proposals and it is the reason this can be honest.

    So the expiry writes `expires_at` into the record as the moment it happened, and
    `noticed_at` beside it as the moment this job got there. The audit entry's own `ts`
    is chain time and stays chain time: it says when the row was written, which is a
    different true thing, and backdating it would corrupt the one property the chain
    has.

    **`lag_seconds` is on the record deliberately.** It is the distance between the two,
    and it is the number that tells a reader whether the scheduler is running. Nothing
    else in the system would show a stopped job; a lag that climbs says so on every row.

ESCALATIONS HAVE NO DEADLINE YET, AND THIS DOES NOT INVENT ONE
==============================================================

    The ruling names proposals and escalations together. Proposals carry `expires_at`
    with an 8-hour default declared in 0021. **Escalations carry nothing**: there is no
    column, no default, and nothing anywhere in the Pack or the schema says how long a
    named human has to receive or answer one.

    So `escalation_record.expires_at` is added NULLABLE WITH NO DEFAULT, this job
    expires the ones that carry a deadline, and today that is none of them. The
    mechanism is real and the rule is Ivan's to set. Inventing twenty-four hours here
    would put a number nobody chose in front of a reviewer, which is the defect entry
    157 has just finished removing from a placeholder.

    The open question is in entry 156, and `overdue_without_a_deadline` in this module's
    result is what makes it visible rather than quiet: it counts the escalations that
    are old and unanswered and cannot be expired because nobody has said when they
    should be.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from broker import audit

#: How often the background runner checks. Ruled "on its own", so the interval is a
#: property of the deployment rather than of anybody's attention.
#:
#: Sixty seconds because `lag_seconds` is the thing being minimised and a minute is
#: already two orders of magnitude better than the four hours and fifty minutes that
#: produced the ruling. Shorter would buy little and poll a database for nothing.
DEFAULT_INTERVAL_SECONDS = 60

SWEEP_KIND = "deadline_expiry"


async def expire_overdue_proposals(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Expire proposals whose deadline has passed. **Never approves one.**

    Moved out of `proposals` and off the read path. The rule it enforces is unchanged
    and is worth restating because it is the most attractive shortcut on this page: an
    agent below `auto_execute` asked to act, nobody answered, and it did not act. That
    is the correct outcome. A timeout that approved would make the trust tier a delay
    rather than a decision.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE proposal
               SET status = 'expired'
             WHERE status = 'pending' AND expires_at <= now()
            RETURNING proposal_id, office_agent_id, venture_id, forge_id, module_id,
                      task_id, created_at, expires_at, now() AS noticed_at
            """
        )
        expired = [dict(r) for r in await cur.fetchall()]
    await conn.commit()

    for row in expired:
        lag = (row["noticed_at"] - row["expires_at"]).total_seconds()
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
                # ENTRY 159. The deadline is the event; this row's own `ts` is when the
                # entry was written, which is a different true thing.
                "expired_at": row["expires_at"].isoformat(),
                "noticed_at": row["noticed_at"].isoformat(),
                # The number that says whether the scheduler is running. Nothing else
                # in the system would show a stopped job.
                "lag_seconds": round(lag, 3),
                # Said in the record, not only in the docs. Somebody reading this entry
                # later needs to know the task failed rather than quietly succeeded.
                "outcome": "task failed; the proposal was never approved",
            },
        )
    return expired


async def expire_overdue_escalations(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Expire escalations whose deadline has passed, of which there are none yet.

    `escalation_record.expires_at` is nullable with no default, so this expires exactly
    the rows somebody has given a deadline to. Until entry 156's open question is
    answered that is the empty set, and the count of escalations that are old,
    unanswered and undeadlined is reported instead - see `overdue_without_a_deadline`.

    An escalation that has been RECEIVED is left alone even past its deadline. Receipt
    is somebody saying they have it; expiring it afterwards would overwrite a fact a
    person asserted with a timeout, and the thing that is late at that point is the
    answer rather than the delivery.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE escalation_record
               SET expired_at = expires_at
             WHERE expires_at IS NOT NULL
               AND expires_at <= now()
               AND received_at IS NULL
               AND answered_at IS NULL
               AND expired_at IS NULL
            RETURNING escalation_id, venture_id, department, kind, routed_to_name,
                      raised_by, raised_at, expires_at, now() AS noticed_at
            """
        )
        expired = [dict(r) for r in await cur.fetchall()]
    await conn.commit()

    for row in expired:
        lag = (row["noticed_at"] - row["expires_at"]).total_seconds()
        await audit.write_event(
            event_type="escalation_expired",
            # THE RAISER, the way a proposal expiry names the agent whose proposal it
            # was. `audit_log.actor_id` is NOT NULL and this is the party the expiry is
            # about: somebody asked, nobody came, and the entry is theirs.
            actor_type="system", actor_id=row["raised_by"],
            venture_id=row["venture_id"],
            subject={
                "escalation_id": str(row["escalation_id"]),
                "department": row["department"] or "*",
                "kind": row["kind"],
                "routed_to": row["routed_to_name"],
                "expired_at": row["expires_at"].isoformat(),
                "noticed_at": row["noticed_at"].isoformat(),
                "lag_seconds": round(lag, 3),
                "outcome": (
                    "nobody received it before the deadline; the escalation was never "
                    "answered"
                ),
            },
        )
    return expired


async def _undeadlined_overdue(conn: AsyncConnection) -> int:
    """Escalations raised, unreceived, and carrying no deadline to miss.

    The visible form of entry 156's open question. A count that climbs is the argument
    for answering it.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM escalation_record "
            " WHERE expires_at IS NULL AND received_at IS NULL AND answered_at IS NULL"
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def run_once(conn: AsyncConnection) -> dict[str, Any]:
    """One pass. Returns what it did, and records that it ran.

    **Recorded in `sweep_run` for the reason the verdict-ingest sweep was not:** a job
    nothing records is a job nobody can show ran, and "has this been running" is the
    first question anybody asks about a deadline that did not pass.
    """
    sweep_run_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO sweep_run (sweep_run_id, sweep_kind, status) "
            "VALUES (%s, %s, 'running')",
            (sweep_run_id, SWEEP_KIND),
        )
    await conn.commit()

    proposals_expired = await expire_overdue_proposals(conn)
    escalations_expired = await expire_overdue_escalations(conn)
    undeadlined = await _undeadlined_overdue(conn)

    findings = {
        "proposals_expired": len(proposals_expired),
        "escalations_expired": len(escalations_expired),
        # NAMED, not summed into the two above. An escalation nobody can expire is not
        # an escalation that was fine.
        "escalations_overdue_without_a_deadline": undeadlined,
        "worst_lag_seconds": max(
            [
                (r["noticed_at"] - r["expires_at"]).total_seconds()
                for r in proposals_expired + escalations_expired
            ],
            default=0.0,
        ),
    }
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE sweep_run SET status = 'passed', completed_at = now(), "
            "denominator = %s, findings = %s WHERE sweep_run_id = %s",
            (
                len(proposals_expired) + len(escalations_expired),
                Jsonb(findings),
                sweep_run_id,
            ),
        )
    await conn.commit()
    return findings


async def run_forever(
    *, interval_seconds: float = DEFAULT_INTERVAL_SECONDS
) -> None:
    """The background runner. Started by `broker serve`; cancelled on shutdown.

    **One failed pass does not stop the loop.** A deadline job that dies on the first
    transient database error is a deadline job that was running yesterday, which is the
    state this exists to end. The error is logged and the next tick tries again.
    """
    import logging

    from broker.db import connection

    log = logging.getLogger("broker.deadlines")
    while True:
        try:
            async with connection() as conn:
                found = await run_once(conn)
            if found["proposals_expired"] or found["escalations_expired"]:
                log.info("deadline sweep: %s", found)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("deadline sweep failed; the next tick will try again")
        await asyncio.sleep(interval_seconds)


@contextlib.asynccontextmanager
async def running(*, interval_seconds: float = DEFAULT_INTERVAL_SECONDS) -> Any:
    """Run the sweep for the lifetime of the block. Used by the API's lifespan."""
    task = asyncio.create_task(run_forever(interval_seconds=interval_seconds))
    try:
        yield task
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
