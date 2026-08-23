"""Cost metering and the Part 12 budget ladder.

| Rung                | Trigger                              | Effect                          |
|---------------------|--------------------------------------|---------------------------------|
| per-task ceiling    | task spend >= ceiling                | that task halts                 |
| per-agent daily cap | agent spend today >= cap             | agent paused                    |
| soft cap            | venture MTD >= soft_cap_pct of cap   | auto_execute -> propose |
| hard cap            | venture MTD >= monthly cap           | pause/throttle, Ivan-only reversal |

**Spend is measured, not predicted.** Exact pre-call cost is unknowable - the Forge
has not run yet and token counts do not exist until it has. The honest enforcement is
"you have already spent this much, so you may not start another", which means a
single call can carry a venture slightly past a cap. Accepted: the alternative is
either refusing to enforce at all, or blocking on an estimate that will sometimes be
wrong in the expensive direction.

The soft cap is expressed as a **tier downgrade** rather than a separate mechanism,
because Part 12 defines it as exactly that: "all auto_execute downgrades to propose
across the engagement". Routing it through the tier gate means one enforcement point
rather than two that can disagree.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.errors import BudgetExceeded, NotAuthorized


@dataclass(frozen=True, slots=True)
class BudgetState:
    venture_id: str
    month_to_date: Decimal
    monthly_cap: Decimal
    soft_cap_pct: int
    hard_cap_action: str
    soft_capped: bool
    hard_capped: bool

    @property
    def soft_cap_amount(self) -> Decimal:
        return self.monthly_cap * Decimal(self.soft_cap_pct) / Decimal(100)


_BUDGET_SQL = """
SELECT monthly_usd_cap, soft_cap_pct, hard_cap_action,
       per_agent_usd_daily_cap, per_task_usd_ceiling,
       hard_cap_reversed_at
FROM venture_budget WHERE venture_id = %s
"""


async def evaluate(
    conn: AsyncConnection,
    *,
    venture_id: str,
    office_agent_id: uuid.UUID,
    task_id: str,
) -> BudgetState | None:
    """Walk the ladder. Raises on a halting rung; returns state for the soft cap.

    Returns None when the venture has no budget row. That is deliberate: an
    unbudgeted venture is unmetered, and silently applying a default cap would
    halt work for a reason nobody configured. Validator rule V18 makes budget caps
    a required Pack field, so an unbudgeted venture cannot reach production.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_BUDGET_SQL, (venture_id,))
        budget = await cur.fetchone()
    if budget is None:
        return None

    async with conn.cursor(row_factory=dict_row) as cur:
        # One query for all three windows; three round trips on every call would
        # put the metering on the hot path for no benefit.
        await cur.execute(
            """
            SELECT
              COALESCE(SUM(usd_cost) FILTER (
                WHERE task_id = %(task_id)s), 0)                       AS task_spend,
              COALESCE(SUM(usd_cost) FILTER (
                WHERE office_agent_id = %(agent_id)s
                  AND ts_start >= date_trunc('day', now())), 0)        AS agent_today,
              COALESCE(SUM(usd_cost) FILTER (
                WHERE ts_start >= date_trunc('month', now())), 0)      AS venture_mtd
            FROM agent_call_ledger
            WHERE venture_id = %(venture_id)s
              AND ts_start >= date_trunc('month', now())
            """,
            {"task_id": task_id, "agent_id": office_agent_id, "venture_id": venture_id},
        )
        spend = await cur.fetchone()
    assert spend is not None

    task_spend = Decimal(spend["task_spend"])
    agent_today = Decimal(spend["agent_today"])
    venture_mtd = Decimal(spend["venture_mtd"])

    monthly_cap = Decimal(budget["monthly_usd_cap"])
    task_ceiling = Decimal(budget["per_task_usd_ceiling"])
    agent_cap = Decimal(budget["per_agent_usd_daily_cap"])

    # Rung 1 - narrowest scope first. A blown task should halt that task, not report
    # the venture cap it also happens to be under.
    if task_spend >= task_ceiling:
        raise BudgetExceeded(
            "per-task USD ceiling reached; this task halts",
            rung="per_task_ceiling",
            task_id=task_id,
            spent=str(task_spend),
            ceiling=str(task_ceiling),
        )

    # Rung 2
    if agent_today >= agent_cap:
        raise BudgetExceeded(
            "per-agent daily USD cap reached; agent paused until tomorrow",
            rung="per_agent_daily_cap",
            spent=str(agent_today),
            cap=str(agent_cap),
        )

    hard_capped = venture_mtd >= monthly_cap
    reversed_at = budget["hard_cap_reversed_at"]

    # Rung 4 - checked before rung 3 because the harder rung wins when both apply.
    if hard_capped and reversed_at is None and budget["hard_cap_action"] == "pause":
        raise BudgetExceeded(
            "venture monthly hard cap reached; engagement paused. "
            "Reversal is Ivan-only.",
            rung="hard_cap",
            spent=str(venture_mtd),
            cap=str(monthly_cap),
            action="pause",
        )
    # hard_cap_action = 'throttle' does not halt the call. The venture chose to keep
    # working slowly rather than stop, and overriding that here would ignore the Pack.

    soft_cap_amount = monthly_cap * Decimal(budget["soft_cap_pct"]) / Decimal(100)

    return BudgetState(
        venture_id=venture_id,
        month_to_date=venture_mtd,
        monthly_cap=monthly_cap,
        soft_cap_pct=budget["soft_cap_pct"],
        hard_cap_action=budget["hard_cap_action"],
        soft_capped=venture_mtd >= soft_cap_amount,
        hard_capped=hard_capped and reversed_at is None,
    )


async def reverse_hard_cap(
    conn: AsyncConnection,
    *,
    venture_id: str,
    actor_id: uuid.UUID,
    actor_role: str,
) -> None:
    """Lift a hard cap. Part 12: Ivan-only.

    The authority check lives here rather than in a constraint because the rule is
    about the actor, and a row can claim any role. It has to be verified where the
    claim is made.
    """
    if actor_role != "ivan":
        raise NotAuthorized(
            "hard-cap reversal is Ivan-only",
            actor_role=actor_role,
            venture_id=venture_id,
        )
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE venture_budget SET hard_cap_reversed_by = %s, "
            "hard_cap_reversed_at = now() WHERE venture_id = %s",
            (actor_id, venture_id),
        )
    await conn.commit()
