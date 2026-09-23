"""A read that cannot find its source says so.

RULED 23 SEPTEMBER 2026 (decisions entry 177)
=============================================

    *"A read that cannot find its source says so. `read_battery_result`'s 404 handler
    returned None as 'no record', so a wrong route would have left verdict_evidence
    NULL on every certification, silently. A missing route and an absent record are
    different answers."*

WHAT WAS MEASURED
=================

    `GET /office/_modules` on the running SimForge build lists exactly three:
    `gate_result`, `run_start`, `submit_curriculum`. `read_battery_result` POSTed a
    fourth, `battery_result`, to that same adapter. It has never existed.

    Every call 404'd. The handler read 404 as "SimForge has no battery record" and
    returned None, the sweep wrote NULL, and the column's published meaning - "nobody
    asked, or nobody could" - is exactly what a reader would have concluded.

    The evidence was at `GET /api/operation/battery-result/{run_ref}` the whole time.

THE TWO THAT CARRY THE RULING
=============================

    `test_a_404_that_does_not_name_the_ref_raises` - the defect itself. A route that
    is not there must never read as a resource that is not there.

    `test_the_sweep_says_so_rather_than_writing_a_silent_null` - the half that makes
    it visible. The verdict still lands; the failed read lands beside it.
"""

from __future__ import annotations

import json

import pytest

from broker import sweeps
from broker.simforge import (
    RouteMissingError,
    SimForgeClient,
    SimForgeError,
)

REF = "office:greenstone:cre-forge:comp_analysis@e27fc174:d57e1d204bbb:k585d456f9bd5"

#: SimForge's own 404 for a ref it has no record of. Measured 23 September 2026.
UNKNOWN_REF_BODY = {
    "detail": {
        "error": "unknown_run_ref",
        "detail": f"SimForge has no record of run_ref {REF!r}.",
    }
}

#: FastAPI's 404 for a route that is not mounted. Also measured, from the adapter
#: this call spent a day asking.
NOT_FOUND_BODY = {"detail": "Not Found"}

OBSERVED_BODY = {
    "run_ref": REF,
    "unit": "A",
    "forge_id": "cre-forge",
    "module_id": "comp_analysis",
    "agent_id": "e27fc174",
    "observed": True,
    "join": "natural_key(forge_id, module_id, agent_id) bounded by run.startedAt",
    "certifications": [
        {
            "state": "failed",
            "operation_rubric_results": [
                {"channel": "restraint", "dimension": "failure_recognition",
                 "score": 0.0, "verdict": "FAIL"},
            ],
            "per_scenario_class": {"happy_path": "FAIL"},
            "exam_attempts": [{"seed": 1, "score": 0.8, "passed": False}],
            "withheld_because": [],
            "failure_modes_observed": [],
        }
    ],
}


class _Response:
    """Enough of an httpx response for the three branches that read one."""

    def __init__(self, status_code: int, body: object = None, text: str = "") -> None:
        self.status_code = status_code
        self._body = body
        self._text = text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class _Http:
    """Records the URL it was asked for, answers what the test set."""

    def __init__(self, response: _Response) -> None:
        self.response = response
        self.url: str | None = None
        self.headers: dict | None = None

    async def get(self, url, *, headers=None, timeout=None):
        self.url = url
        self.headers = headers
        return self.response

    async def post(self, url, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError(f"battery-result is a GET, not a POST to {url}")


class _Credential:
    def reveal(self) -> str:
        return "tenant-token"


def _client(response: _Response) -> tuple[SimForgeClient, _Http]:
    http = _Http(response)
    client = SimForgeClient(object(), http=http)

    async def _cred(_conn):
        return _Credential()

    async def _reg(_conn):
        return "http://simforge.example:8110/office", "1.0.0"

    client._tenant_credential = _cred  # type: ignore[method-assign]
    client._registry = _reg  # type: ignore[method-assign]
    return client, http


# ======================================================== the route

async def test_it_asks_simforges_own_route_at_the_origin():
    """**THE FIX.** The registry's `base_url` is an adapter mount, not the service.

    `build` already strips it to the origin for `/api/version` and says why in its
    docstring. This is the same road: the evidence is a direct route at the host
    root, and the adapter never dispatched a module for it.
    """
    client, http = _client(_Response(200, OBSERVED_BODY))
    await client.read_battery_result(object(), REF)

    assert http.url is not None
    assert http.url.startswith("http://simforge.example:8110/api/operation/")
    assert "/office/" not in http.url
    assert "battery-result" in http.url


async def test_the_ref_is_percent_encoded_into_the_path():
    """A ref carrying `/` would otherwise address a different route entirely.

    Today's refs carry `:` and `@`, which travel unencoded - but the minter has added
    a segment twice this month and the next one is not this call's to predict.
    """
    client, http = _client(_Response(200, OBSERVED_BODY))
    await client.read_battery_result(object(), "a/b:c@d")

    assert http.url is not None
    assert http.url.endswith("/battery-result/a%2Fb%3Ac%40d")


async def test_it_carries_the_tenant_credential():
    client, http = _client(_Response(200, OBSERVED_BODY))
    await client.read_battery_result(object(), REF)

    assert http.headers is not None
    assert http.headers["Authorization"] == "Bearer tenant-token"


# ======================================================== the ruling

async def test_a_404_that_does_not_name_the_ref_raises():
    """**THE RULING.** A route that is not there is not a record that is not there.

    This exact body - FastAPI's `{"detail": "Not Found"}` - is what the old call got
    from the adapter, every time, for a day. It was read as "no battery record".
    """
    client, _ = _client(_Response(404, NOT_FOUND_BODY))

    with pytest.raises(RouteMissingError) as caught:
        await client.read_battery_result(object(), REF)

    # The message has to be actionable: an operator reading it must not go looking for
    # a missing battery.
    assert "route" in str(caught.value)
    assert "do not read this as an absent battery record" in str(caught.value)


async def test_a_404_that_names_the_ref_is_an_absence_and_returns_none():
    """SimForge was asked, and has no such run. An answer, not a fault."""
    client, _ = _client(_Response(404, UNKNOWN_REF_BODY))

    assert await client.read_battery_result(object(), REF) is None


@pytest.mark.parametrize("body", [
    {"detail": "Not Found"},
    {"detail": {"error": "something_else"}},
    {"detail": None},
    {},
    ["not", "an", "object"],
])
async def test_every_other_404_shape_raises_rather_than_inventing_an_absence(body):
    """**The direction that fails safe.**

    A body this cannot understand is treated as the route being absent, never as the
    record being absent. Inventing an absence is how a NULL column acquires a meaning
    nobody checked.
    """
    client, _ = _client(_Response(404, body))

    with pytest.raises(RouteMissingError):
        await client.read_battery_result(object(), REF)


async def test_a_404_with_no_json_at_all_raises():
    client, _ = _client(_Response(404))

    with pytest.raises(RouteMissingError):
        await client.read_battery_result(object(), REF)


async def test_the_missing_route_error_is_a_simforge_error():
    """So every existing `except SimForgeError` still catches it.

    A new exception that escapes the handlers written for its parent would turn a
    logged finding into an unhandled failure in the verdict sweep.
    """
    assert issubclass(RouteMissingError, SimForgeError)


# ======================================================== an answered read

async def test_observed_false_is_still_an_absence():
    """SimForge's other way of saying it has nothing, and it is still not an error."""
    body = dict(OBSERVED_BODY, observed=False, certifications=[])
    client, _ = _client(_Response(200, body))

    assert await client.read_battery_result(object(), REF) is None


async def test_a_real_record_comes_back_whole():
    client, _ = _client(_Response(200, OBSERVED_BODY))
    evidence = await client.read_battery_result(object(), REF)

    assert evidence is not None
    assert evidence.run_ref == REF
    assert evidence.state == "failed"
    assert evidence.deciding_dimensions


async def test_a_non_404_error_status_still_raises_the_plain_error():
    """A 500 is SimForge failing, not a URL this side built wrong.

    Kept apart because the response differs: one is a service to look at, the other
    is a line of code to change.
    """
    client, _ = _client(_Response(503, {"detail": "unavailable"}))

    with pytest.raises(SimForgeError) as caught:
        await client.read_battery_result(object(), REF)
    assert not isinstance(caught.value, RouteMissingError)


# ======================================================== the sweep half

class _Raises:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    async def read_battery_result(self, conn, run_ref):
        raise self.exc


class _Answers:
    def __init__(self, evidence) -> None:
        self.evidence = evidence

    async def read_battery_result(self, conn, run_ref):
        return self.evidence


async def test_the_sweep_says_so_rather_than_writing_a_silent_null():
    """**THE RULING'S OTHER HALF.** A failed read is reported, not swallowed.

    `_evidence_for` used to return a bare None for five different outcomes - no ref,
    no client, unreachable, wrong URL, and a run with genuinely no battery - and all
    five were written as `verdict_evidence IS NULL`. One of them was true for a day
    and nothing said so.
    """
    record, note = await sweeps._evidence_for(
        _Raises(RouteMissingError("the battery-result route did not answer")),
        object(), REF,
    )

    assert record is None
    assert note is not None
    assert "route" in note


async def test_an_unreachable_forge_says_something_different():
    """The two notes must not read the same. One is a service to wait for; the other
    is a URL that will never heal on its own."""
    record, route_note = await sweeps._evidence_for(
        _Raises(RouteMissingError("no route")), object(), REF
    )
    record2, down_note = await sweeps._evidence_for(
        _Raises(SimForgeError("could not reach SimForge: ConnectError")),
        object(), REF,
    )

    assert record is None and record2 is None
    assert route_note != down_note
    assert "route" in str(route_note)
    assert "could not be read" in str(down_note)


async def test_a_run_with_no_battery_produces_no_note():
    """An honest absence is not a failure to read. Only the note distinguishes them,
    so a note here would put a finding in the sweep for a normal state."""
    record, note = await sweeps._evidence_for(_Answers(None), object(), REF)

    assert record is None
    assert note is None


async def test_no_run_ref_produces_no_note_either():
    """A submission whose run never opened has no battery to read and no read failed."""
    record, note = await sweeps._evidence_for(_Answers(None), object(), None)

    assert record is None
    assert note is None


async def test_no_client_says_so():
    """Distinct from an absence, because it is a fact about this sweep, not the run."""
    record, note = await sweeps._evidence_for(None, object(), REF)

    assert record is None
    assert note is not None


async def test_an_unexpected_exception_is_still_non_fatal():
    """The verdict is the thing being ingested. Evidence that raises must not cost a
    run its certification - the same argument the hand-over makes for being
    non-fatal, at the other end of the exam."""
    record, note = await sweeps._evidence_for(
        _Raises(RuntimeError("boom")), object(), REF
    )

    assert record is None
    assert "RuntimeError" in str(note)


async def test_the_findings_dict_has_somewhere_to_put_it():
    """The key has to exist before `_ingest_one` appends to it.

    Read off the source rather than by running a sweep: this is a declaration, and a
    missing key would be a KeyError in the middle of an ingest that had already
    written rows.
    """
    import inspect

    source = inspect.getsource(sweeps.sweep_verdict_ingest)
    assert '"evidence_unreadable": []' in source


# ======================================================== the manifest was never wrong

def test_the_manifest_already_described_the_right_route():
    """The field list was measured against the real body; only the URL was wrong.

    Worth pinning because it says where the defect was and where it was not: nobody
    guessed SimForge's shape here. `get_battery_result`'s declared fields are exactly
    the keys `GET /api/operation/battery-result/{run_ref}` returns.
    """
    from broker.simforge import MANIFEST_PATH

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    declared = set(manifest["get_battery_result"]["fields"])

    assert declared == {
        "run_ref", "unit", "forge_id", "module_id", "agent_id",
        "observed", "certifications", "join",
    }
