"""Before treating a response as the Village's, confirm it is the Village.

On 4 September 2026 V29 and V30 had been NOT_RUN for a week with `401 Unauthorized` from
the Village's configured address. That reads as a credential problem, so it was left for
somebody with the credential.

**There is no credential.** The Village was not running, and a container from an unrelated
project held that port. Its 401 was a different system confidently refusing a request it had
never heard of, and The Office reported it as the Village refusing The Office.

(The address is not written here on purpose. `test_only_one_module_knows_the_village_exists`
keeps it in `broker/village.py` alone, and it scans prose as well as code — bluntly, and
correctly: a number copied into a docstring is the first place a second copy comes from.)

Not a wrong value. The wrong system, answering, for a week.

The check is derivable rather than guessed: the Village serves `/api/org/*` with no
authentication — `app/blueprints/api/org.py` carries no auth decorator and the blueprint has
no `before_request` — and this client sends no credential. So a 401 or 403 on those paths is
positive evidence that whatever answered is not the Village.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest

from broker import departments as depts
from broker import village


def _response(status: int, json_body=None, *, headers=None, text: str | None = None):
    return httpx.Response(
        status_code=status,
        json=json_body if text is None else None,
        text=text,
        headers=headers or {},
        # From `broker.village`, never spelled here: `test_only_one_module_knows_the
        # _village_exists` keeps that address in exactly one file, and a test that
        # hardcoded it would be the first crack in the seal.
        request=httpx.Request("GET", f"{village.base_url()}/api/org/departments"),
    )


# --- what is and is not the Village ---------------------------------------------------


def test_a_401_is_not_the_village_refusing() -> None:
    """The exact live case, and the sentence a reader needs.

    A server answering 401 with a Bearer challenge on a path the Village serves open is
    not being strict. It is something else.
    """
    why = village._not_the_village(
        _response(401, {"detail": "Missing authentication"},
                  headers={"server": "uvicorn", "www-authenticate": "Bearer"})
    )

    assert why is not None
    assert "nothing at this address identified itself as the Village" in why
    assert "uvicorn" in why
    assert "NOT the Village refusing a credential" in why


def test_a_403_is_treated_the_same() -> None:
    assert village._not_the_village(_response(403, {"detail": "nope"})) is not None


def test_a_200_that_is_not_village_shaped_is_refused() -> None:
    """The same problem one status code over.

    A responder that answers 200 with JSON of its own would have sailed past a check that
    only looked at the status, and its payload would have been parsed as a roster.
    """
    why = village._not_the_village(
        _response(200, {"items": [], "page": 1}), "/api/org/departments"
    )

    assert why is not None
    assert "identified itself as the Village" in why
    assert "items" in why


def test_a_200_that_is_not_json_is_refused() -> None:
    why = village._not_the_village(
        _response(200, text="<html>hello</html>", headers={"content-type": "text/html"})
    )
    assert why is not None
    assert "not JSON" in why


def test_a_real_departments_answer_passes() -> None:
    """One surface. `test_every_surface_of_a_running_village_passes` is the real one.

    This test was green for the entire period the probe was rejecting a running
    Village on two of its six surfaces, because it exercised the one surface whose
    vocabulary the markers had been written from.
    """
    body = {
        "success": True,
        "department_count": 2,
        "departments": [
            {"department": "research", "label": "Research", "seats": 4, "head": "a1"},
        ],
    }
    assert village._not_the_village(_response(200, body), "/api/org/departments") is None


def test_a_500_is_not_evidence_either_way() -> None:
    """A Village having a bad day is unreachable, not an impostor. Claiming otherwise
    would send someone hunting for a port conflict that does not exist."""
    assert village._not_the_village(_response(500, {"error": "boom"})) is None
    assert village._not_the_village(_response(404, {"detail": "not found"})) is None


# --- how it reaches a reader -----------------------------------------------------------


async def test_the_error_is_an_identity_error_not_a_bare_unreachable(monkeypatch) -> None:
    """`VillageIdentityError` subclasses `VillageUnreachableError` on purpose: every
    caller that degraded to a cached answer keeps doing so. What changes is the reason."""

    class _Client:
        def __init__(self, *a, **k) -> None: ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            return _response(401, {"detail": "Missing authentication"},
                             headers={"server": "uvicorn", "www-authenticate": "Bearer"})

    monkeypatch.setattr(village.httpx, "AsyncClient", _Client)
    village._cache.entries.clear()

    with pytest.raises(village.VillageIdentityError) as caught:
        await village.departments(degrade=False)

    assert isinstance(caught.value, village.VillageUnreachableError)
    assert "NOT the Village refusing a credential" in str(caught.value)


async def test_v29_says_which_kind_of_not_run_it_is(monkeypatch) -> None:
    """The whole point. "The Village could not be read" and "nothing at the Village's
    address is the Village" send a reader to different places."""

    class _Client:
        def __init__(self, *a, **k) -> None: ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            return _response(401, {"detail": "Missing authentication"},
                             headers={"server": "uvicorn", "www-authenticate": "Bearer"})

    monkeypatch.setattr(village.httpx, "AsyncClient", _Client)
    village._cache.entries.clear()
    depts._reset_for_tests()

    assert await depts.names() is None
    assert depts.was_misidentified() is True
    assert "identified itself as the Village" in (depts.unreachable_reason() or "")


async def test_an_ordinary_outage_is_not_reported_as_misidentification(monkeypatch) -> None:
    """The negative half. A refused connection is the Village being down, and telling
    somebody to go looking for a port squatter would waste the same week in reverse."""

    class _Client:
        def __init__(self, *a, **k) -> None: ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(village.httpx, "AsyncClient", _Client)
    village._cache.entries.clear()
    depts._reset_for_tests()

    assert await depts.names() is None
    assert depts.was_misidentified() is False


# ============================================ THE SURFACES, AS A RUNNING VILLAGE SENDS THEM

#: Top-level keys of every surface `broker.village` calls, captured from a Village
#: running on 2026-09-06. Not invented: each was read off a live 200.
#:
#: The probe held one marker tuple - the roster and department vocabulary - and applied
#: it to all six. `board` and the agent overview carry none of those words, so the probe
#: answered "nothing at this address identified itself as the Village" about a Village
#: that had just answered 200 with correct data. `village.quarter()` raised,
#: `shifts.current_quarter()` turned it into `QuarterUnknown`, and `assign_shift` refused
#: every assignment for as long as the Village was up.
REAL_SURFACES: dict[str, list[str]] = {
    "/api/org/roster": [
        "agent_count", "agents", "department_count", "departments", "success",
    ],
    "/api/org/departments": ["department_count", "departments", "success"],
    "/api/objectives/shifts": [
        "current_phase", "day_number", "departments", "shifts", "success",
    ],
    "/api/objectives/deputies": ["departments", "success"],
    "/api/objectives/board": [
        "available_targets", "clock", "objectives", "success", "summary",
    ],
    "/api/agents/amelie_wystan/overview": ["agent", "overview", "success"],
}


@pytest.mark.parametrize("path", sorted(REAL_SURFACES))
def test_every_surface_of_a_running_village_passes(path: str) -> None:
    """THE test. A real Village must not be called an impostor on any surface it serves.

    Parametrised per path rather than looped, so a failure names the surface instead of
    reporting that "the Village" failed - which is the sentence that caused this.
    """
    body = {key: None for key in REAL_SURFACES[path]}
    why = village._not_the_village(_response(200, body), path)
    assert why is None, f"the probe rejected a real Village at {path}: {why}"


def test_every_path_the_client_calls_has_a_recorded_shape() -> None:
    """A surface nobody recorded must not inherit another surface's vocabulary.

    Read from the source of `broker/village.py` rather than from a list here, because a
    list here is a second copy that goes stale the moment somebody adds an endpoint -
    and going stale is precisely what happened.
    """
    import re

    source = pathlib.Path("broker/village.py").read_text(encoding="utf-8")
    called = set(re.findall(r'_get\(\s*f?"([^"]+)"', source))
    assert called, "found no _get call sites; the regex has drifted from the source"

    unrecorded = []
    for path in sorted(called):
        # f-string paths carry a placeholder; the prefix is what the lookup matches on.
        concrete = path.split("{")[0]
        if village.markers_for(concrete) is None:
            unrecorded.append(path)

    assert not unrecorded, (
        f"these paths are called with no recorded shape: {unrecorded}. Add them to "
        "_SURFACE_MARKERS with the keys a running Village actually returns - do not "
        "reuse another surface's markers, which is the bug this guard exists for."
    )


def test_the_recorded_shapes_are_not_all_the_same_vocabulary() -> None:
    """The markers must actually differ per surface, or the split is decoration.

    If a future edit collapses them back to one shared tuple this fails, which is the
    shape of the original defect rather than one instance of it.
    """
    board = set(village.markers_for("/api/objectives/board") or ())
    roster = set(village.markers_for("/api/org/roster") or ())
    assert board and roster
    assert not (board & roster), (
        "board and roster now share marker vocabulary. They describe different "
        "surfaces; a shared tuple is how a running Village got rejected."
    )


def test_an_impostor_is_still_caught_on_the_board_surface() -> None:
    """Per-surface markers must not have weakened the check into uselessness."""
    why = village._not_the_village(
        _response(200, {"items": [], "page": 1, "total": 0}), "/api/objectives/board"
    )
    assert why is not None
    assert "not the Village" in why


def test_an_unrecorded_surface_is_not_judged_on_shape() -> None:
    """Stated, because it is a deliberate hole rather than an oversight.

    Judging a surface whose shape nobody recorded is what produced the false rejection.
    The 401/403 rule still applies to every path, and that is the half that caught the
    real incident.
    """
    assert village._not_the_village(
        _response(200, {"anything": 1}), "/api/something/never/recorded"
    ) is None
    assert village._not_the_village(
        _response(401, {"detail": "nope"}), "/api/something/never/recorded"
    ) is not None
