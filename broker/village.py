"""The Village, over HTTP, one direction only.

The Office asks the Village for things. The Village never calls back, The Office never
imports a Village module, and the two never share a database or a filesystem path.
`tests/contract/test_village_seal.py` walks this package's AST and fails on an import of
`modules.*`, `models.*` or any other Village top-level package - the same shape the
Village's own `TestSeal` uses in the other direction.

The seal is not ceremony. Reading `config/agentsrole.yaml` off a shared filesystem would
have been three lines and would have re-established exactly the single-machine coupling
these two applications are separated to avoid: one file read establishes the pattern, and
the next one is easier to justify than the first.

WHAT THE OFFICE READS

    roster          department, role ladder key and reporting line per agent
    departments     the live list, so no copy of it exists here
    agent state     department, title, status, lifecycle, mood
    shifts          who is on shift now, per department
    deputies        deputy authoring status
    board           the objectives board, and the clock that carries the quarter

UNREACHABLE

    `village_unreachable_behavior` in the Pack's availability block. The default, and the
    recommendation, is `degrade`: agents keep operating, and any view built from Village
    data falls back to the last successful answer with a visible staleness marker. The
    alternative - refusing to render - would take The Office down whenever the Village
    restarts, which is a worse failure than a page that says how old its numbers are.

    A cached answer is never returned as if it were fresh. Every reader gets `fetched_at`
    and `stale`, and a caller that ignores them is the bug.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_TIMEOUT = 8.0


class VillageUnreachableError(Exception):
    """The Village did not answer, and no cached answer was available."""


@dataclass(frozen=True, slots=True)
class Answer:
    """A Village response, with how old it is.

    `stale` is the whole point of the type. A caller that wants to render a headcount has
    to decide what to do when the number is four hours old, and it cannot decide that if
    the freshness is not in its hands.
    """

    data: dict[str, Any]
    fetched_at: datetime
    stale: bool = False
    reason: str | None = None

    @property
    def age_seconds(self) -> float:
        return (datetime.now(UTC) - self.fetched_at).total_seconds()


@dataclass
class _Cache:
    """Last successful answer per path. Process-local and deliberately small."""

    entries: dict[str, tuple[dict[str, Any], datetime]] = field(default_factory=dict)

    def put(self, path: str, data: dict[str, Any]) -> None:
        self.entries[path] = (data, datetime.now(UTC))

    def get(self, path: str) -> tuple[dict[str, Any], datetime] | None:
        return self.entries.get(path)


_cache = _Cache()


def base_url() -> str:
    return os.environ.get("VILLAGE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


async def _get(path: str, *, degrade: bool = True) -> Answer:
    """One GET, with the last good answer as the fallback.

    `degrade=False` is for the paths where a stale answer would be worse than an error -
    a roster sync must never diff against yesterday's roster and report departures that
    did not happen.
    """
    url = f"{base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # every failure mode degrades the same way
        cached = _cache.get(path)
        if cached is None or not degrade:
            raise VillageUnreachableError(f"{url}: {exc}") from exc
        data, fetched_at = cached
        return Answer(
            data=data,
            fetched_at=fetched_at,
            stale=True,
            reason=f"the Village did not answer ({type(exc).__name__})",
        )

    if isinstance(data, dict) and data.get("success") is False:
        cached = _cache.get(path)
        message = data.get("error", "the Village reported a failure")
        if cached is None or not degrade:
            raise VillageUnreachableError(f"{url}: {message}")
        cached_data, fetched_at = cached
        return Answer(cached_data, fetched_at, stale=True, reason=message)

    _cache.put(path, data)
    return Answer(data=data, fetched_at=datetime.now(UTC))


# ------------------------------------------------------------------ the roster

async def roster(*, degrade: bool = False) -> Answer:
    """Every position, with department, role ladder key and reporting line.

    `degrade=False`: a sync that diffed against a cached roster would report agents as
    departed because the Village was briefly down, and departure revokes grants.
    """
    return await _get("/api/org/roster", degrade=degrade)


async def departments(*, degrade: bool = True) -> Answer:
    """The live department list. The Office keeps no copy."""
    return await _get("/api/org/departments", degrade=degrade)


async def department_names() -> list[str]:
    """Normalized department names, for validating a Pack against."""
    answer = await departments()
    return [d["department"] for d in answer.data.get("departments", [])]


async def department_labels() -> dict[str, str]:
    """Normalized name to the label an operator sees in the Village UI.

    Both forms exist because they are used for different jobs: the normalized name is
    what a Pack is validated against, and the label is what an error message quotes back,
    because that is the word the operator read before they typed it.
    """
    answer = await departments()
    return {
        d["department"]: d.get("label", d["department"])
        for d in answer.data.get("departments", [])
    }


# ------------------------------------------------------------- agents and shifts

async def agent_state(agent_id: str) -> Answer:
    """One agent's live state: department, title, status, lifecycle, mood.

    Surfaced by the console and acted on by nothing. Simulated grief must not block
    regulated work.
    """
    return await _get(f"/api/agents/{agent_id}/overview")


async def shifts() -> Answer:
    """Who is on shift now, by department. The Village owns the shift calendar."""
    return await _get("/api/objectives/shifts")


async def deputies() -> Answer:
    """Deputy authoring status per department."""
    return await _get("/api/objectives/deputies")


# ------------------------------------------------------------------- objectives

async def board() -> Answer:
    """The objectives board, and the clock that carries the quarter."""
    return await _get("/api/objectives/board")


async def quarter() -> str | None:
    """The current objectives quarter, e.g. `2026Q1`.

    The assignment window is aligned to this rather than to a wall-clock quarter: the
    Village runs at 5/720, so its quarter and ours share a name and nothing else.
    """
    answer = await board()
    clock = answer.data.get("clock") or {}
    value = clock.get("quarter")
    return str(value) if value else None


async def clock() -> Answer:
    """The Village clock: tick, phase, day number, quarter."""
    answer = await board()
    return Answer(
        data=answer.data.get("clock") or {},
        fetched_at=answer.fetched_at,
        stale=answer.stale,
        reason=answer.reason,
    )
