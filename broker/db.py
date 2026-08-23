"""Async connection pool.

The broker connects as office_app, which holds INSERT and SELECT on the ledger
tables and nothing else. It must never be given an owner DSN: append-only is
enforced by the role, so an over-privileged connection silently removes the
control.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from broker.config import get_settings

_pool: AsyncConnectionPool | None = None


def _dsn() -> str:
    return get_settings().office_app_dsn


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        s = get_settings()
        _pool = AsyncConnectionPool(
            _dsn(), min_size=s.pool_min_size, max_size=s.pool_max_size, open=False
        )
        await _pool.open(wait=True)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    """A pooled connection at READ COMMITTED.

    The audit hash-chain trigger reads the current chain tip after taking an
    advisory lock. Under REPEATABLE READ that read uses a snapshot taken before
    the lock, so it would chain onto a stale tip - rejected by UNIQUE(prev_hash),
    but rejected is still a failed audit write. READ COMMITTED is a correctness
    requirement here, not a performance preference. See docs/ledger.md.
    """
    pool = await open_pool()
    async with pool.connection() as conn:
        await conn.set_isolation_level(None)  # server default: read committed
        yield conn
