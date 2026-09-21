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
    # Entry 143's two, NESTED - which is the shape SimForge declared when it published
    # them, and not the flat one entry 143 guessed at while neither existed. Read live
    # from `http://127.0.0.1:8110/api/version` on 21 September 2026.
    "exam": {
        "response_protocol_version": "6.0.0",
        "operation_rubric_version": "0.4.0",
    },
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
    read by more people than a Forge's own health page. Six fields answer the
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
        "response_protocol_version": "6.0.0",
        "operation_rubric_version": "0.4.0",
    }
    assert "launch_environment" not in found


async def test_a_forge_with_no_exam_block_reports_neither_version():
    """The state SimForge was in until 21 September, and any older Forge still is.

    `None` has to be the answer - a default here would put a version in a ref that
    nobody read (entry 143) - and it is not an outage: a Forge that does not publish a
    version is still reachable, and conflating the two would report a service being
    down where there is a missing field.
    """
    body = {k: v for k, v in ANSWER.items() if k != "exam"}
    client = _client(lambda r: httpx.Response(200, json=body))
    found = await client.build(FakeConn())
    await client.aclose()

    assert found["response_protocol_version"] is None
    assert found["operation_rubric_version"] is None
    assert found["reachable"] is True


@pytest.mark.parametrize(
    "exam",
    [
        pytest.param("6.0.0", id="a string where an object was declared"),
        pytest.param(["6.0.0"], id="a list"),
        pytest.param(None, id="an explicit null"),
        pytest.param({}, id="an empty object"),
        pytest.param({"operation_rubric_version": "0.4.0"}, id="one key of two"),
    ],
)
async def test_a_block_that_is_not_the_declared_shape_reports_none(exam):
    """**Never raises, and never half-reads.**

    `build`'s whole contract is that every failure is a recorded answer. A block of the
    wrong type must produce the same `None` a missing one does rather than an
    AttributeError inside a gate that asked the question out of caution.

    The last case is the one worth keeping: one key of two is not a reason to drop the
    other, and not a reason to invent the missing one.
    """
    body = dict(ANSWER, exam=exam)
    client = _client(lambda r: httpx.Response(200, json=body))
    found = await client.build(FakeConn())
    await client.aclose()

    assert found["reachable"] is True
    assert found["response_protocol_version"] is None
    if isinstance(exam, dict) and "operation_rubric_version" in exam:
        assert found["operation_rubric_version"] == "0.4.0"
    else:
        assert found["operation_rubric_version"] is None


async def test_the_flat_shape_is_not_read():
    """**The load-bearing test of this change.** One shape, not two.

    Entry 143 guessed the versions would arrive as top-level keys, because neither was
    published when it was written. SimForge nested them. Keeping a fallback to the
    guess would leave two shapes in the code, and the first time they disagreed nothing
    would say so - which is exactly how the flat guess went unnoticed in the first
    place: the probe returned None against a Forge that was answering.
    """
    body = {k: v for k, v in ANSWER.items() if k != "exam"}
    body["response_protocol_version"] = "6.0.0"
    body["operation_rubric_version"] = "0.4.0"
    client = _client(lambda r: httpx.Response(200, json=body))
    found = await client.build(FakeConn())
    await client.aclose()

    assert found["response_protocol_version"] is None
    assert found["operation_rubric_version"] is None


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
