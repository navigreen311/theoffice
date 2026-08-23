"""Rate limiting — per agent AND per Forge global ceiling.

Master prompt §1.7 step 9. Two buckets, both of which must admit: an agent within
its own limit still cannot push a Forge past its global ceiling, and a quiet Forge
does not entitle one agent to unlimited calls.

Token bucket rather than a fixed window, because the Pack declares `max_rps` *and*
`burst` and a fixed window cannot express the difference. In Postgres rather than
Redis: the blueprint puts the queue on Postgres at v1, and a counter store would be
the same operational dependency under another name.

Concurrency: `SELECT ... FOR UPDATE` serialises access to a bucket row. **This
requires READ COMMITTED.** Under REPEATABLE READ the re-read after the lock raises a
serialization failure - the lock serialises entry, it does not refresh the snapshot.
Same constraint as the audit hash chain; see docs/ledger.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.db import connection
from broker.errors import RateLimited

DEFAULT_AGENT_RPS = 5.0
DEFAULT_AGENT_BURST = 10.0
DEFAULT_FORGE_RPS = 50.0
DEFAULT_FORGE_BURST = 100.0


def agent_key(office_agent_id: uuid.UUID) -> str:
    return f"agent:{office_agent_id}"


def forge_key(forge_id: str) -> str:
    return f"forge:{forge_id}"


@dataclass(frozen=True, slots=True)
class BucketState:
    key: str
    tokens: float
    max_tokens: float
    effective_rate: float


_ACQUIRE_SQL = """
WITH locked AS (
    SELECT bucket_key, tokens, max_tokens, refill_per_second, last_refill,
           throttle_factor, throttled_until
    FROM rate_limit_bucket
    WHERE bucket_key = %(key)s
    FOR UPDATE
),
computed AS (
    SELECT
        bucket_key,
        max_tokens,
        -- A throttle that has expired must stop applying without anyone resetting
        -- it, otherwise a forgotten throttle is indistinguishable from a policy.
        CASE WHEN throttled_until IS NOT NULL AND throttled_until > now()
             THEN refill_per_second * throttle_factor
             ELSE refill_per_second
        END AS effective_rate,
        LEAST(
            max_tokens,
            tokens + EXTRACT(EPOCH FROM (now() - last_refill)) *
                CASE WHEN throttled_until IS NOT NULL AND throttled_until > now()
                     THEN refill_per_second * throttle_factor
                     ELSE refill_per_second
                END
        ) AS refilled
    FROM locked
)
UPDATE rate_limit_bucket b
SET tokens = CASE WHEN c.refilled >= 1 THEN c.refilled - 1 ELSE c.refilled END,
    last_refill = now()
FROM computed c
WHERE b.bucket_key = c.bucket_key
RETURNING b.bucket_key, c.refilled AS available, b.tokens AS remaining,
          b.max_tokens, c.effective_rate
"""


async def ensure_bucket(
    conn: AsyncConnection, key: str, *, rps: float, burst: float
) -> None:
    """Create a bucket if absent. Idempotent; never resets an existing one.

    ON CONFLICT DO NOTHING matters: resetting the bucket on every call would hand
    a caller unlimited tokens simply by reconnecting.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO rate_limit_bucket
              (bucket_key, tokens, max_tokens, refill_per_second)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (bucket_key) DO NOTHING
            """,
            (key, burst, burst, rps),
        )


async def _acquire_one(conn: AsyncConnection, key: str) -> BucketState:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_ACQUIRE_SQL, {"key": key})
        row = await cur.fetchone()

    if row is None:
        raise RateLimited("rate limit bucket missing", bucket_key=key)

    if float(row["available"]) < 1:
        raise RateLimited(
            "rate limit exceeded",
            bucket_key=key,
            available=float(row["available"]),
            refill_per_second=float(row["effective_rate"]),
        )

    return BucketState(
        key=key,
        tokens=float(row["remaining"]),
        max_tokens=float(row["max_tokens"]),
        effective_rate=float(row["effective_rate"]),
    )


async def acquire(
    *,
    office_agent_id: uuid.UUID,
    forge_id: str,
    agent_rps: float = DEFAULT_AGENT_RPS,
    agent_burst: float = DEFAULT_AGENT_BURST,
    forge_rps: float = DEFAULT_FORGE_RPS,
    forge_burst: float = DEFAULT_FORGE_BURST,
) -> None:
    """Take one token from the agent bucket and one from the Forge bucket.

    Agent first. If the Forge ceiling then refuses, one agent token has been spent
    on a call that did not happen - a small over-charge to the agent. The reverse
    order over-charges the shared Forge ceiling instead, which penalises every
    other agent for one agent's excess. Charging the individual is the better
    failure, and it is deliberate rather than incidental.
    """
    async with connection() as conn:
        await ensure_bucket(conn, agent_key(office_agent_id), rps=agent_rps, burst=agent_burst)
        await ensure_bucket(conn, forge_key(forge_id), rps=forge_rps, burst=forge_burst)
        await conn.commit()

        await _acquire_one(conn, agent_key(office_agent_id))
        try:
            await _acquire_one(conn, forge_key(forge_id))
        except RateLimited:
            await conn.commit()  # keep the agent debit; see docstring
            raise
        await conn.commit()


async def throttle_agent(
    office_agent_id: uuid.UUID, factor: float, seconds: int
) -> None:
    """Reduce an agent's effective refill rate for a period.

    Used by the manifest check. Throttling rather than blocking outright: the goal
    is to slow a misbehaving agent while a human looks, not to take a venture down
    over one bad module reference.

    Extends but never shortens an existing throttle - a second violation must not
    be able to reset the clock to something shorter than the first.

    Upserts rather than updates. The manifest check runs BEFORE the rate limiter, so
    an agent's first offence can arrive before it has ever taken a token and its
    bucket does not exist yet. A plain UPDATE silently throttles nothing, which is
    the worst possible outcome: the incident says throttled, the agent is not.
    """
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO rate_limit_bucket
              (bucket_key, tokens, max_tokens, refill_per_second,
               throttle_factor, throttled_until)
            VALUES (%(key)s, %(burst)s, %(burst)s, %(rps)s, %(factor)s,
                    now() + make_interval(secs => %(seconds)s))
            ON CONFLICT (bucket_key) DO UPDATE
            SET throttle_factor = LEAST(rate_limit_bucket.throttle_factor, %(factor)s),
                throttled_until = GREATEST(
                    COALESCE(rate_limit_bucket.throttled_until, now()),
                    now() + make_interval(secs => %(seconds)s))
            """,
            {
                "key": agent_key(office_agent_id),
                "burst": DEFAULT_AGENT_BURST,
                "rps": DEFAULT_AGENT_RPS,
                "factor": factor,
                "seconds": seconds,
            },
        )
        await conn.commit()


async def bucket_state(office_agent_id: uuid.UUID) -> dict[str, object] | None:
    async with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT tokens, max_tokens, refill_per_second, throttle_factor, "
            "       throttled_until "
            "FROM rate_limit_bucket WHERE bucket_key = %s",
            (agent_key(office_agent_id),),
        )
        return await cur.fetchone()
