"""The run_ref contract: who mints it, who opens the run, and what actually arrives.

Two things were wrong at once and neither half is testable alone.

**A'** - `run_start` was declared in `broker.forge_modules.NOT_AGENT_FACING` with a
written reason, bound on SimForge's Office adapter, and never called by anything. So no
`OperationRun` existed between a curriculum and a verdict: a battery that hung produced
no row, no verdict and no error, and `curriculum_submission.simforge_run_ref` was NULL
on every row ever written. That is docs/blocking.md B8's exact condition.

**B'** - `SimForgeClient.submit_curriculum` raised when the response carried no
`run_ref`, and the response manifest declared `run_ref` as a `submit_curriculum` field
while omitting the five SimForge actually sends. The ref was never SimForge's to return:
`OperationRunStartRequest.run_ref` is an INPUT field, and its own docstring says why -
"The Office reads one verdict per `run_ref`, and a run whose unit is only known once it
finishes cannot be asked about while it is hanging."

THE CONTROL THAT DID NOT MOVE
=============================

    The manifest exists so a field nobody enumerated fails `validate_response` on
    arrival. Adding five fields is *declaring them known*, which is correct only
    because P-01 measured SimForge sending them. `validate_response` itself is
    byte-for-byte what it was: no wildcard, no warning path, no relaxation.

    `test_a_sixth_undeclared_field_still_fails_the_check` is the half of this file that
    proves it. A test that only shows the five now pass shows a check that was widened;
    the pair shows a check that became accurate.
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from broker.simforge import (
    SimForgeClient,
    SimForgeError,
    manifested_fields,
    mint_run_ref,
    submission_unit,
    timeout_gate_result,
    validate_response,
)

VENTURE = "greenstone"
ACTOR = uuid.UUID("00000000-0000-5000-8000-0000000000a1")

#: Exactly what `apps/api/src/routers/operation.py::submit_curriculum` returns on a 200.
#: Read off the receiving side, not off P-01's summary of it (CAVEAT 14).
REAL_ACCEPTANCE: dict = {
    "accepted": True,
    "module_levels": {"parse_document": "certified_with_declared_absence"},
    "module_declared_absences": {
        "parse_document": {"recovery_after_failure": "this module cannot fail partway"}
    },
    "never_do_obligations": ["never quote a price without a signed mandate"],
    "coverage_declaration": {
        "modules_in_forge": 4,
        "modules_covered": 3,
        "modules_uncovered": ["settle_trade"],
        "functions_in_module": 0,
        "functions_covered": 0,
    },
    "gate_9_5_flag": False,
}

#: The five P-01 measured `validate_response` raising on. `accepted` was already named.
THE_FIVE = (
    "coverage_declaration",
    "gate_9_5_flag",
    "module_declared_absences",
    "module_levels",
    "never_do_obligations",
)

#: `OperationRunStarted`, as the Office adapter dumps it.
REAL_RUN_STARTED: dict = {
    "run_ref": "office:greenstone:cre-forge:parse_document:0123456789ab",
    "unit": "A",
    "started_at": "2026-09-09T12:00:00Z",
    "window_minutes": 240,
    "already_open": False,
}


# ----------------------------------------------------------------- the manifest


@pytest.mark.parametrize("field", THE_FIVE)
def test_the_five_fields_simforge_returns_are_declared(field):
    """Each one named individually, so a failure says which is missing.

    P-01 measured `validate_response` raising on exactly these five against a real
    SimForge, ten modules out of ten. A manifest that omits what a system sends is not
    a stricter manifest - it is a wrong one, and the strictness it buys is spent
    failing on the truth.
    """
    assert field in manifested_fields("submit_curriculum")


def test_a_real_acceptance_body_passes_validate_response():
    """The whole body at once, not field by field.

    Including the nested `coverage_declaration`, which `assert_no_scenario_content`
    recurses into, and the Office-authored prose in `module_declared_absences` and
    `never_do_obligations` - the two places a legitimate field carries a sentence.
    """
    validate_response("submit_curriculum", REAL_ACCEPTANCE)


def test_a_sixth_undeclared_field_still_fails_the_check():
    """**THE HALF THAT PROVES THE CONTROL WAS NOT WEAKENED.**

    Five fields became known because somebody measured them and wrote down what they
    are for. A sixth is exactly as unreviewed as those five were an hour ago, and it
    must still fail - even when it is obviously harmless, which `queue_position` is.
    The point has never been that a new field is dangerous; it is that nobody looked.

    If this test ever needs deleting to make a build pass, the question is not how to
    make it pass.
    """
    with pytest.raises(SimForgeError) as exc:
        validate_response(
            "submit_curriculum", {**REAL_ACCEPTANCE, "queue_position": 3}
        )
    assert "queue_position" in str(exc.value)
    assert "manifest" in str(exc.value).lower()


def test_run_start_is_enumerated_before_it_may_be_called():
    """A new endpoint is a new manifest section, not an exemption.

    `manifested_fields` refuses an endpoint the manifest does not name, so binding
    `run_start` without enumerating it would have raised at the first real call - at
    Gate 8, during provisioning, on a body that had already been accepted.
    """
    fields = manifested_fields("run_start")
    assert fields == {
        "run_ref", "unit", "started_at", "window_minutes", "already_open"
    }
    validate_response("run_start", REAL_RUN_STARTED)

    with pytest.raises(SimForgeError):
        validate_response("run_start", {**REAL_RUN_STARTED, "worker_host": "sf-3"})


def test_the_manifest_still_refuses_a_field_that_could_carry_scenario_content():
    """The name check is not softened by the endpoint being new.

    `assert_no_scenario_content` runs on every validated body, so a `run_start` that
    started echoing scenarios is caught on the same terms as a verdict that did.
    """
    with pytest.raises(SimForgeError):
        validate_response("run_start", {**REAL_RUN_STARTED, "scenarios": ["x"]})


# ----------------------------------------------------------- the client contract


class FakeCallResult:
    def __init__(self, status_code: int, body: object) -> None:
        self.status_code = status_code
        self.body = body


class FakeOffice:
    async def call(self, forge_id, module_id, payload, *, agent_ctx):  # pragma: no cover
        raise AssertionError("run_start must not travel the brokered path")


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


async def _noop():
    return 1


async def test_submit_curriculum_no_longer_raises_without_a_run_ref(monkeypatch):
    """The raise that was the bug, asserted gone against the real body.

    Not a body with an empty ref - a body with no ref key at all, which is every
    acceptance SimForge has ever sent. The old client raised
    "SimForge accepted the curriculum without returning a run_ref" on all ten of the
    Burkham modules P-01 measured as ACCEPTED.
    """
    monkeypatch.setattr("broker.simforge.write_event", lambda **k: _noop())

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/submit_curriculum")
        return httpx.Response(200, json=REAL_ACCEPTANCE)

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    body = await client.submit_curriculum(
        FakeConn(ROWS), scenario_pack_ref="run:abc",
        payload={"scenario_count": 15}, actor=ACTOR, venture_id=VENTURE,
    )

    assert "run_ref" not in body
    # The field worth having, and the reason the body is returned whole.
    assert body["module_levels"]["parse_document"] == "certified_with_declared_absence"


async def test_run_start_posts_to_the_adapter_on_the_tenant_credential(monkeypatch):
    """A' - the call that was declared and never made, and the route it takes.

    `{base_url}/run_start` is SimForge's Office adapter: the same surface
    `submit_curriculum` uses, dispatched from the same `MODULES` map, gated by the same
    tenant-credential check. **It is not `POST /api/operation/run/start`**, which is
    behind `require_role("compliance_analyst")` - a user role read from a Clerk JWT,
    which The Office has no business holding for a machine hand-over.

    Asserted on the outbound request, because a client that quietly went somewhere else
    would still return the right answer against a mock.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=REAL_RUN_STARTED)

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    body = await client.run_start(
        FakeConn(ROWS),
        run_ref=REAL_RUN_STARTED["run_ref"],
        unit="A",
        forge_id="cre-forge",
        instruction_content_hash="f" * 64,
        module_id="parse_document",
        scenario_count=3,
        coverage_denominator=4,
    )

    assert len(seen) == 1
    assert seen[0].url.path == "/office/run_start"
    assert seen[0].headers["Authorization"].startswith("Bearer ")
    # The Office mints the ref and declares the unit; both travel as inputs.
    import json as _json

    sent = _json.loads(seen[0].content)
    assert sent["run_ref"] == REAL_RUN_STARTED["run_ref"]
    assert sent["unit"] == "A"
    assert sent["rubric_kind"] == "operation"
    # Not guessed. The window is SimForge's policy.
    assert sent["window_minutes"] is None
    assert body["already_open"] is False


async def test_run_start_refuses_a_body_the_manifest_does_not_name():
    """The new endpoint is validated on the same terms as the old ones."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**REAL_RUN_STARTED, "worker_pid": 41})

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    with pytest.raises(SimForgeError, match="not in the SimForge response manifest"):
        await client.run_start(
            FakeConn(ROWS), run_ref="office:x:y:z:abc", unit="A",
            forge_id="cre-forge", instruction_content_hash="f" * 64,
        )


async def test_an_unreachable_run_start_names_the_type_not_the_url():
    """The request carried a credential, so `str(exc)` must not travel."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused to http://simforge.invalid/office/run_start")

    client = SimForgeClient(
        FakeOffice(), http=_transport(handler), resolver=FakeResolver()
    )
    with pytest.raises(SimForgeError) as exc:
        await client.run_start(
            FakeConn(ROWS), run_ref="office:x:y:z:abc", unit="A",
            forge_id="cre-forge", instruction_content_hash="f" * 64,
        )
    assert "ConnectError" in str(exc.value)
    assert "simforge.invalid" not in str(exc.value)


# ------------------------------------------------------------- the unit derivation


def test_a_module_submission_is_unit_a_and_the_operation_rubric():
    """The rule Gate 8 and `run_start` now share, stated once.

    A submission naming a module is a unit A - one agent, one Forge, one module,
    judged against the operation rubric. One naming no module is a unit B.
    """
    assert submission_unit("parse_document") == ("A", "operation")
    assert submission_unit(None) == ("B", "domain")


def test_the_timeout_sweep_reuses_that_rule_rather_than_restating_it():
    """CAVEAT: one question, one rule.

    `timeout_gate_result` answered this inline before `run_start` needed the same
    answer. Two spellings would be two things to keep in step, and they would disagree
    silently because each would look right beside its own call site.

    Asserted through `timeout_gate_result`'s output rather than by reading its source,
    because a grep finds mentions and not construction: if it ever stopped calling
    `submission_unit`, this still fails the moment the two disagree.
    """
    submission = {
        "submission_id": uuid.uuid4(),
        "module_id": "parse_document",
        "simforge_run_ref": "office:greenstone:cre-forge:parse_document:0123456789ab",
    }
    verdict = timeout_gate_result(submission, rubric_version="1.4.0")
    unit, rubric_kind = submission_unit(submission["module_id"])
    assert (verdict.unit, verdict.rubric_kind) == (unit, rubric_kind) == ("A", "operation")

    department = {"submission_id": uuid.uuid4(), "module_id": None}
    b = timeout_gate_result(department, rubric_version="1.4.0")
    assert (b.unit, b.rubric_kind) == submission_unit(None) == ("B", "domain")


# ------------------------------------------------------------------ the minted ref


def test_the_same_submission_mints_the_same_ref():
    """Why the ref is derived and not a uuid.

    `open_run` is idempotent on `run_ref` and answers `already_open: true` with the
    clock UNTOUCHED, so a retried hand-over cannot extend the window of a run that is
    already hanging (SimForge's ADR-0044). A fresh uuid per attempt defeats that from
    the caller's side - two runs, two windows, the second one young - while SimForge's
    own guard reads as satisfied.
    """
    args = dict(
        venture_id="greenstone", forge_id="cre-forge",
        module_id="parse_document", content_hash="a" * 64,
    )
    assert mint_run_ref(**args) == mint_run_ref(**args)


def test_a_changed_instruction_mints_a_different_ref():
    """A different content hash is a new submission, not a retry.

    That is SimForge's own rule for the instruction-set upsert, and the ref follows it
    rather than inventing a second answer to the same question.
    """
    base = dict(
        venture_id="greenstone", forge_id="cre-forge", module_id="parse_document"
    )
    assert mint_run_ref(**base, content_hash="a" * 64) != mint_run_ref(
        **base, content_hash="b" * 64
    )


def test_refs_for_different_modules_and_ventures_do_not_collide():
    refs = {
        mint_run_ref(
            venture_id=v, forge_id=f, module_id=m, content_hash="a" * 64
        )
        for v in ("greenstone", "burkham")
        for f in ("cre-forge", "voiceforge")
        for m in ("parse_document", "settle_trade", None)
    }
    assert len(refs) == 12


def test_a_minted_ref_carries_no_scenario_content():
    """It travels in a response body and through `assert_no_scenario_content`.

    Two ids, a module name and a hash prefix. A ref long enough to trip the prose
    tripwire would fail the boundary check on the way back in `run_start`'s echo.
    """
    ref = mint_run_ref(
        venture_id="greenstone", forge_id="cre-forge",
        module_id="parse_document", content_hash="a" * 64,
    )
    validate_response("run_start", {**REAL_RUN_STARTED, "run_ref": ref})
