"""SimForgeClient - the two paths, and what each refuses.

The asymmetry is the point of these tests. `get_gate_result` must go through the
brokered path and must not let an unvalidated body reach a caller; `submit_curriculum`
and `run_start` must sign with the tenant credential and audit against a human.

**Two tests here used to assert that an acceptance without a `run_ref` is refused.**
That was the contract being wrong in test form: `OperationRunStartRequest.run_ref` is an
INPUT field, so the ref was never SimForge's to return, and P-01 measured ten of ten
modules accepted while the client raised on every one of them. They now assert the
opposite, and `run_start` - declared in `forge_modules.NOT_AGENT_FACING` and never once
called - has tests for the first time.

`tests/golden/stub_simforge.py` is deliberately not used here. Its routes were invented
before there was a client, and SimForge serves neither of them - it proves
`validate_response` works and nothing about a call path. These stubs answer on the paths
the client actually posts to.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from broker.simforge import SimForgeClient, SimForgeError
from tests.golden.stub_simforge import HONEST_GATE_RESULT, LEAKS

VENTURE = "greenstone"
ACTOR = uuid.UUID("00000000-0000-5000-8000-0000000000a1")


class FakeCallResult:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body
        self.call_id = uuid.uuid4()
        self.trace_id = uuid.uuid4()
        self.latency_ms = 1
        self.idempotency_key = "k"
        self.manifest_match = "declared"


class FakeOffice:
    """Stands in for OfficeClient. Records what the brokered path was asked for."""

    def __init__(self, status_code: int = 200, body: object | None = None) -> None:
        self._status = status_code
        self._body = HONEST_GATE_RESULT if body is None else body
        self.calls: list[tuple] = []

    async def call(self, forge_id, module_id, payload, *, agent_ctx):
        self.calls.append((forge_id, module_id, payload, agent_ctx))
        return FakeCallResult(self._status, self._body)


class Ctx:
    office_agent_id = uuid.UUID("00000000-0000-5000-8000-0000000000b1")
    venture_id = VENTURE
    task_id = "t-1"
    shift_id = None


# --------------------------------------------------------------- brokered path


async def test_a_verdict_is_read_through_the_brokered_path():
    """The grant path is unmodified; this class supplies a module name.

    Asserted on what the office client was asked for, because the value of the
    brokered path is that a verdict read is a ledgered agent act - and a client that
    quietly went direct would still return the right answer.
    """
    office = FakeOffice()
    client = SimForgeClient(office)

    result = await client.get_gate_result("sf-run-0001", agent_ctx=Ctx())

    assert office.calls == [
        ("simforge", "gate_result", {"run_ref": "sf-run-0001"}, office.calls[0][3])
    ]
    assert result.verdict == "PASS"
    assert result.scenario_count == 24


@pytest.mark.parametrize("leak", sorted(LEAKS))
async def test_a_leaky_verdict_never_reaches_the_caller(leak):
    """Every leak the stub knows how to produce raises instead of returning.

    Parametrised over all four rather than one: the value of `validate_response` is
    that no single technique gets through, and testing one technique proves one.
    """
    client = SimForgeClient(FakeOffice(body=LEAKS[leak]))

    with pytest.raises(SimForgeError):
        await client.get_gate_result("sf-run-0001", agent_ctx=Ctx())


async def test_an_unknown_run_is_a_named_refusal_not_an_empty_verdict():
    client = SimForgeClient(FakeOffice(status_code=404, body={"detail": "no such run"}))

    with pytest.raises(SimForgeError, match="no record of run_ref"):
        await client.get_gate_result("sf-run-nope", agent_ctx=Ctx())


async def test_a_forge_error_body_is_not_echoed_into_the_exception():
    """An error body has not been through `validate_response`.

    So it must not travel in a message either - an exception string is the one place
    a leak would cross the boundary without being checked.
    """
    body = {"detail": LEAKS["innocuous_name"]["notes"]}
    client = SimForgeClient(FakeOffice(status_code=500, body=body))

    with pytest.raises(SimForgeError) as exc:
        await client.get_gate_result("sf-run-0001", agent_ctx=Ctx())
    assert "borrower" not in str(exc.value)
    assert "500" in str(exc.value)


# ----------------------------------------------------------- not brokered path


class FakeCursor:
    def __init__(self, rows: dict) -> None:
        self._rows = rows
        self._row: tuple | None = None

    async def execute(self, sql: str, params: tuple) -> None:
        self._row = self._rows.get("credential" if "credential" in sql else "registry")

    async def fetchone(self):
        return self._row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConn:
    def __init__(self, rows: dict) -> None:
        self._rows = rows

    def cursor(self):
        return FakeCursor(self._rows)


ROWS = {
    "credential": ("vault://simforge/tenant",),
    "registry": ("http://simforge.invalid/office", "1.4.0"),
}


class FakeResolver:
    async def resolve(self, credential_ref: str):
        from broker.credentials import Credential

        return Credential(credential_ref, "NOT-A-REAL-TOKEN")


def _transport(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_handover_returns_the_acceptance_body_and_audits_the_human(monkeypatch):
    """The audit entry names the provisioner, and no agent appears anywhere.

    That is the whole reason this call is not brokered: there is no agent behind a
    curriculum hand-over, and naming one would put a name in the record for a call it
    never made.

    The return value is the acceptance body now, not a ref. `module_levels` is the
    field worth having - the per-module certification level - and the old contract
    discarded the entire body to read one key that was never in it.
    """
    written: list[dict] = []

    async def fake_write_event(**kwargs):
        written.append(kwargs)
        return 1

    monkeypatch.setattr("broker.simforge.write_event", fake_write_event)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/submit_curriculum")
        assert request.headers["Authorization"].startswith("Bearer ")
        # SimForge's real acceptance shape, read off
        # `apps/api/src/routers/operation.py::submit_curriculum` rather than off the
        # name of anything. No `run_ref` anywhere in it.
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "module_levels": {"parse_document": "certified"},
                "module_declared_absences": {},
                "never_do_obligations": [],
                "coverage_declaration": {
                    "modules_in_forge": 4, "modules_covered": 3,
                    "modules_uncovered": ["settle_trade"],
                    "functions_in_module": 0, "functions_covered": 0,
                },
                "gate_9_5_flag": False,
            },
        )

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    body = await client.submit_curriculum(
        FakeConn(ROWS), scenario_pack_ref="run:abc",
        payload={"scenario_count": 15, "coverage_denominator": 15},
        actor=ACTOR, venture_id=VENTURE,
    )

    assert body["accepted"] is True
    # The reason the whole body is returned rather than narrowed to a ref.
    assert body["module_levels"] == {"parse_document": "certified"}
    assert len(written) == 1
    assert written[0]["event_type"] == "curriculum_handed_over"
    assert written[0]["actor_type"] == "human"
    assert written[0]["actor_id"] == ACTOR
    # Counts, never bodies.
    assert written[0]["subject"]["scenario_count"] == 15
    assert "scenarios" not in written[0]["subject"]


async def test_the_audit_entry_is_written_before_the_call(monkeypatch):
    """A hand-over that lands and then crashes this process must still have a trace.

    Asserted by failing the HTTP call and checking the entry survived - the ordering
    is invisible on the happy path.
    """
    written: list[dict] = []

    async def fake_write_event(**kwargs):
        written.append(kwargs)
        return 1

    monkeypatch.setattr("broker.simforge.write_event", fake_write_event)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    with pytest.raises(SimForgeError, match="could not reach SimForge"):
        await client.submit_curriculum(
            FakeConn(ROWS), scenario_pack_ref="run:abc",
            payload={"scenario_count": 15}, actor=ACTOR, venture_id=VENTURE,
        )

    assert len(written) == 1, "the intent entry did not survive a failed call"


async def test_an_acceptance_without_a_run_ref_is_not_refused(monkeypatch):
    """The inversion of a test that asserted the bug.

    This file used to say "an accepted hand-over with no ref cannot be correlated to a
    verdict", and that reasoning was sound about a premise that was false. **The ref
    was never SimForge's to return.** `OperationRunStartRequest.run_ref` is an input
    field, and its own docstring gives the reason: The Office reads one verdict per
    `run_ref`, so a run whose identity is only known once it finishes cannot be asked
    about while it is hanging. The correlation the old test was protecting is real; it
    is established by `run_start`, from this side.

    So an acceptance carrying no ref - which is every acceptance SimForge has ever
    sent - returns normally, and the ten-of-ten Burkham modules P-01 measured stop
    raising.
    """
    monkeypatch.setattr(
        "broker.simforge.write_event", lambda **k: _noop()
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "module_levels": {"parse_document": "demonstrated"},
                "module_declared_absences": {},
                "never_do_obligations": [],
                "coverage_declaration": {
                    "modules_in_forge": 1, "modules_covered": 1,
                    "modules_uncovered": [],
                    "functions_in_module": 0, "functions_covered": 0,
                },
                "gate_9_5_flag": False,
            },
        )

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    body = await client.submit_curriculum(
        FakeConn(ROWS), scenario_pack_ref="run:abc",
        payload={"scenario_count": 15}, actor=ACTOR, venture_id=VENTURE,
    )
    assert "run_ref" not in body
    assert body["module_levels"]["parse_document"] == "demonstrated"


async def test_an_undeclared_field_in_an_acceptance_fails_the_call(monkeypatch):
    """The manifest guards both directions, not only the verdict read."""
    monkeypatch.setattr("broker.simforge.write_event", lambda **k: _noop())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "run_ref": "sf-run-9", "accepted": True, "scenario_count": 15,
                "coverage_denominator": 15, "rejected_reason": None,
                "queue_position": 3,
            },
        )

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    with pytest.raises(SimForgeError, match="not in the SimForge response manifest"):
        await client.submit_curriculum(
            FakeConn(ROWS), scenario_pack_ref="run:abc",
            payload={"scenario_count": 15}, actor=ACTOR, venture_id=VENTURE,
        )


async def _noop():
    return 1


class NoCredential:
    """The resolver's own failure type, which is not a SimForgeError."""

    async def resolve(self, credential_ref: str):
        from broker.errors import CredentialUnavailable

        raise CredentialUnavailable(
            "credential ref did not resolve", credential_ref=credential_ref
        )


async def test_an_unresolvable_credential_is_a_simforge_error(monkeypatch):
    """The regression CI caught and 974 local tests did not.

    `CredentialUnavailable` is an `OfficeError`, not a `SimForgeError`, so it went
    straight past Gate 8's handler and 503'd the provisioning API on any environment
    without `SIMFORGE_TOKEN`. A Forge that cannot be reached must never stop a
    provisioning run, and "cannot be reached" includes "we hold no credential for it".
    """
    monkeypatch.setattr("broker.simforge.write_event", lambda **k: _noop())

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("the call must not be attempted without a credential")

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=NoCredential()
    )
    with pytest.raises(SimForgeError, match="did not resolve"):
        await client.submit_curriculum(
            FakeConn(ROWS), scenario_pack_ref="run:abc",
            payload={"scenario_count": 15}, actor=ACTOR, venture_id=VENTURE,
        )
