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
    why = village._not_the_village(_response(200, {"items": [], "page": 1}))

    assert why is not None
    assert "identified itself as the Village" in why
    assert "items" in why


def test_a_200_that_is_not_json_is_refused() -> None:
    why = village._not_the_village(
        _response(200, text="<html>hello</html>", headers={"content-type": "text/html"})
    )
    assert why is not None
    assert "not JSON" in why


def test_a_real_village_answer_passes() -> None:
    body = {
        "success": True,
        "department_count": 2,
        "departments": [
            {"department": "research", "label": "Research", "seats": 4, "head": "a1"},
        ],
    }
    assert village._not_the_village(_response(200, body)) is None


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
