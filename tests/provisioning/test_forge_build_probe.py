"""`SimForgeClient.build` - the probe itself, and the URL it has to get right.

Separate from the gate tests because these need no database: they are about one HTTP
call, the address it goes to, and the fact that nothing it can hit ever raises.

THE URL IS THE SUBTLE PART
==========================

    `forge_registry.base_url` is `http://127.0.0.1:8110/office` - the Office ADAPTER's
    mount. `/api/version` is SimForge's own route at the host root. Appending to the
    base would produce `/office/api/version`, which 404s and would be recorded as "this
    Forge has no version route" - a false finding about the Forge, caused by an address
    this side built wrong.
"""

from __future__ import annotations

import httpx
import pytest

from broker.simforge import SimForgeClient

BASE = "http://127.0.0.1:8110/office"

ANSWER = {
    "started_commit": "a" * 40,
    "checkout_commit": "b" * 40,
    "differs": True,
    "app_version": "1.0.0",
    # Reported by SimForge and deliberately NOT carried into the gate result.
    "launch_environment": {"modes": {}, "configured": {"office_tenant_token": True}},
}


class FakeCursor:
    def __init__(self, row): self._row = row
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def execute(self, *a, **k): return None
    async def fetchone(self): return self._row


class FakeConn:
    """Answers the one query `_registry` makes and nothing else."""

    def cursor(self, **kwargs): return FakeCursor((BASE, "v1"))


def _client(handler) -> SimForgeClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SimForgeClient(office=None, http=http)  # type: ignore[arg-type]


async def test_the_probe_asks_the_host_root_not_the_adapter_mount():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=ANSWER)

    client = _client(handler)
    await client.build(FakeConn())
    await client.aclose()

    assert seen == ["http://127.0.0.1:8110/api/version"], (
        f"the probe went to {seen}; appending to base_url would 404 and be recorded "
        "as a Forge with no version route"
    )


async def test_the_answer_is_transcribed_and_the_environment_is_dropped():
    """An unrecognised key is dropped rather than stored.

    `launch_environment` carries which credentials are configured, and a gate result is
    read by more people than a Forge's own health page. Four fields answer the
    question; the rest is somebody else's record.
    """
    client = _client(lambda r: httpx.Response(200, json=ANSWER))
    found = await client.build(FakeConn())
    await client.aclose()

    assert found == {
        "reachable": True,
        "started_commit": "a" * 40,
        "checkout_commit": "b" * 40,
        "differs": True,
        "app_version": "1.0.0",
    }
    assert "launch_environment" not in found


@pytest.mark.parametrize(
    ("handler", "expected"),
    [
        (lambda r: httpx.Response(404), "404"),
        (lambda r: httpx.Response(500), "500"),
        (lambda r: httpx.Response(200, content=b"not json"), "did not return JSON"),
        (lambda r: httpx.Response(200, json=["a", "list"]), "did not return an object"),
    ],
)
async def test_every_bad_answer_is_a_recorded_answer(handler, expected):
    """**Never raises.** A probe that threw would turn "the Forge did not say" into
    "Gate 8 fell over", and the gate would stop for a question it asked out of caution.
    """
    client = _client(handler)
    found = await client.build(FakeConn())
    await client.aclose()

    assert found["reachable"] is False
    assert expected in found["reason"]


async def test_a_connection_failure_names_the_exception_and_is_bounded():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nothing is listening " + "x" * 500)

    client = _client(handler)
    found = await client.build(FakeConn())
    await client.aclose()

    assert found["reachable"] is False
    assert found["reason"].startswith("ConnectError: ")
    assert len(found["reason"]) <= 200, "an unbounded error text goes into a gate result"


async def test_differs_absent_is_none_and_never_false():
    """SimForge sends `differs: null` when it could not read one side, on the ground
    that a process which cannot say what it is running must not report itself up to
    date. An older Forge that omits the key entirely must land in the same state."""
    client = _client(lambda r: httpx.Response(200, json={"app_version": "1.0.0"}))
    found = await client.build(FakeConn())
    await client.aclose()

    assert found["reachable"] is True
    assert found["differs"] is None
    assert found["started_commit"] is None
