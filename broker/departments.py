"""The department list, read from the Village and never copied here.

The Office carried its own tuple of twelve department names. Nine of them were wrong: the
Village was rebuilt and now has `research`, `banking`, `operations` where The Office had
`Research & Market Intelligence`, `Finance & Administration`, `Client Success &
Operations`. Nothing failed, because nothing checked - a Pack naming a department that
had not existed for two days validated cleanly.

A copy of somebody else's list is a copy that goes stale silently. This module holds no
list. It asks, caches the answer, and says how old the answer is.

WHEN THE VILLAGE IS UNREACHABLE AND NOTHING IS CACHED

    The rule reports NOT_RUN, not PASS and not FAIL.

    PASS would say a Pack's departments were checked when they were not - the exact
    failure this console's own copy warns about on every other page. FAIL would report an
    unrun check as a fault, which Part 10.1 forbids in the other direction. A Pack whose
    departments could not be checked has not been validated, and the honest word for that
    is neither of the two that sound decisive.

CASING

    Two forms, because they do different jobs. `department` is normalized -
    `media_production` - and is what a Pack is validated against, because it is what the
    Village stores. `label` is what the Village UI shows - `Media_Production` - and is
    what an error message quotes back, because that is the word the operator read before
    they typed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from broker import village

#: How long a department list is trusted before it is fetched again. Departments change
#: when the Village is rebuilt, which is rare; the cache exists so that validating fifty
#: Packs on one page load does not make fifty HTTP calls.
TTL = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class Department:
    department: str
    label: str
    seats: int


@dataclass
class _State:
    departments: tuple[Department, ...] | None = None
    fetched_at: datetime | None = None
    last_error: str | None = None


_state = _State()


def _fresh() -> bool:
    return (
        _state.departments is not None
        and _state.fetched_at is not None
        and datetime.now(UTC) - _state.fetched_at < TTL
    )


async def load(*, force: bool = False) -> tuple[Department, ...] | None:
    """The live departments, or None if the Village has never answered.

    None is a real answer and callers must handle it. Returning an empty tuple would be
    indistinguishable from a Village with no departments, and a validator cannot tell
    those apart without being told.
    """
    if _fresh() and not force:
        return _state.departments

    try:
        answer = await village.departments(degrade=True)
    except village.VillageUnreachableError as exc:
        _state.last_error = str(exc)
        return _state.departments  # last known, or None

    rows = answer.data.get("departments") or []
    _state.departments = tuple(
        Department(
            department=row["department"],
            label=row.get("label", row["department"]),
            seats=int(row.get("seats", 0)),
        )
        for row in rows
    )
    _state.fetched_at = answer.fetched_at
    _state.last_error = None if not answer.stale else answer.reason
    return _state.departments


async def names() -> tuple[str, ...] | None:
    departments = await load()
    return tuple(d.department for d in departments) if departments is not None else None


async def labels() -> tuple[str, ...] | None:
    """The forms an operator sees, for quoting back in an error."""
    departments = await load()
    return tuple(d.label for d in departments) if departments is not None else None


async def seats() -> dict[str, int] | None:
    departments = await load()
    return {d.department: d.seats for d in departments} if departments is not None else None


def normalize(value: str) -> str:
    """`Media Production` and `Media_Production` both become `media_production`.

    A Pack written by hand will not match the Village's casing, and refusing it on that
    basis would be a spelling test rather than a check that the department exists.
    """
    return value.strip().lower().replace(" & ", "_").replace(" ", "_").replace("-", "_")


def unreachable_reason() -> str | None:
    """Why the list is missing or stale, for a message that says what to do."""
    return _state.last_error


def state() -> dict[str, Any]:
    """For the console, which has to show whether these numbers are current."""
    return {
        "known": _state.departments is not None,
        "count": len(_state.departments) if _state.departments else 0,
        "fetched_at": _state.fetched_at.isoformat() if _state.fetched_at else None,
        "stale": not _fresh(),
        "error": _state.last_error,
    }


def seed(departments: tuple[Department, ...] | list[Department]) -> None:
    """Install a department list without calling the Village.

    For tests and for the seeded development world. A test suite that needs a second
    application running to validate a Pack is a suite that fails for reasons unrelated to
    the code under test, and the Village being up is not what any of these tests are
    about - the rules that ask it have their own tests, and the live path is exercised by
    the smoke script.

    Seeding is deliberately explicit. There is no fallback list anywhere in this module:
    when nothing has seeded and the Village cannot be reached, the answer is None and the
    rules report NOT_RUN, which is the honest state.
    """
    global _state
    _state = _State(
        departments=tuple(departments),
        fetched_at=datetime.now(UTC),
        last_error=None,
    )


def _reset_for_tests() -> None:
    global _state
    _state = _State()
