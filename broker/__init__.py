"""The Office identity broker.

Windows event-loop policy is set here, at package import, because psycopg's async
driver cannot run on the ProactorEventLoop that asyncio has selected by default on
Windows since 3.8. Without this the pool does not fail fast - it retries until
`PoolTimeout`, so the symptom is a 30-second hang rather than an error naming the
cause.

Setting a global policy from a package import is intrusive for a library. This is
an application: uvicorn, pytest-asyncio and any script share the same defect, and
fixing it in one place beats three call sites that must each remember.

The selector loop caps out around 512 sockets and cannot spawn subprocesses.
Neither constrains the broker, and production is expected to be Linux, where this
branch does not execute at all.
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
