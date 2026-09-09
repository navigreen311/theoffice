"""The adapter's surface: the manifest, the refusals over HTTP, and the four traps.

`docs/forge-adapter.md` numbers the ways an adapter fails silently. Each of the ones an
in-repo test can reach has an assertion here, named after it, because every one of them
returned a plausible success and was found by making a real call rather than by reading.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import httpx
import pytest

from adapters.funnelforge import app as adapter_app
from adapters.funnelforge import modules as modules_mod
from adapters.funnelforge.modules import MODULES, manifest
from broker import executor, forge_modules

TOKEN = "funnelforge-adapter-test-token-not-a-secret"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv(adapter_app.TENANT_CREDENTIAL_ENV, TOKEN)
    return TOKEN


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=adapter_app.build_app()),
        base_url="http://funnelforge.invalid",
    )


# ------------------------------------------------- the manifest is the naming authority


async def test_nine_modules_are_bound():
    """The count the proposal arrived at. Not 73, and not four."""
    assert len(MODULES) == 9


async def test_manifest_is_derived_from_the_dispatch_map():
    """`sorted(MODULES)`, never a literal list beside the dict.

    This is the only answer in the whole path that is not a declaration. A list
    maintained alongside drifts silently while carrying the authority of having come
    from the Forge, which makes it worse than the two declarations that already exist.
    Asserted twice: the values agree, and the source contains no second list to agree
    with.
    """
    answered = [entry["module_id"] for entry in manifest()["modules"]]
    assert answered == sorted(MODULES)

    source = inspect.getsource(modules_mod.manifest)
    for module_id in MODULES:
        assert f'"{module_id}"' not in source, (
            f"{module_id!r} is written literally inside manifest(). The manifest must "
            "be derived from the dispatch map; a literal makes it a third declaration."
        )


async def test_no_module_id_uses_the_reserved_prefix():
    """`_` belongs to the adapter's own endpoints; `_modules` would shadow the manifest."""
    assert not [m for m in MODULES if m.startswith("_")]


async def test_the_broker_can_read_this_manifest_and_gets_shapes():
    """The receiving side, not the names.

    `broker/forge_modules._parse_modules` accepts a list of names OR a list of the
    three-field objects, and a list of names leaves `shapes = None` - which makes
    `verify_forge_modules.py` print *"states no module shapes"* and leave the registry
    copy V31 spends unchecked. So the assertion is not "the manifest parses"; it is
    "the shapes came through".
    """
    names, shapes = forge_modules._parse_modules(manifest()["modules"])
    assert names is not None and sorted(names) == sorted(MODULES)
    assert shapes is not None, "the manifest stated no shapes"
    for module_id, binding in MODULES.items():
        assert shapes[module_id].is_mutating == binding.is_mutating
        assert shapes[module_id].idempotency_support == binding.idempotency_support


async def test_every_declared_idempotency_value_is_one_the_registry_accepts():
    for module_id, binding in MODULES.items():
        assert binding.idempotency_support in forge_modules.IDEMPOTENCY_SUPPORT, module_id


async def test_seven_modules_are_the_shape_v31_refuses_and_that_is_recorded():
    """A prediction written down rather than discovered by whoever runs the ladder.

    V31 refuses `auto_execute` over a module that is mutating and `at_most_once`, and
    `auto_execute` is the only tier that reaches a Forge. This test does not assert that
    V31 is wrong or that the declarations should change - it pins the count so that a
    later change to a declaration is a deliberate act with a failing test attached.
    """
    unsafe = sorted(
        m for m, b in MODULES.items()
        if b.is_mutating and b.idempotency_support == "at_most_once"
    )
    assert len(unsafe) == 7, unsafe
    grantable = sorted(set(MODULES) - set(unsafe))
    assert grantable == ["capture_contact", "read_funnel_analytics"]


# --------------------------------------------------------------- trap #9: unconfigured


async def test_an_unconfigured_adapter_answers_503_and_says_which_state_it_is_in(
    monkeypatch,
):
    """*"An adapter that is not configured must not answer like one whose credential was
    refused."* 401 sends whoever is debugging to rotate a credential that was never the
    problem.
    """
    monkeypatch.delenv(adapter_app.TENANT_CREDENTIAL_ENV, raising=False)
    async with _client() as client:
        answer = await client.post("/capture_contact", json={})
    assert answer.status_code == 503
    assert answer.json()["error"]["code"] == "ADAPTER_NOT_CONFIGURED"
    assert "do not rotate" in answer.json()["error"]["message"].lower()


async def test_an_unconfigured_adapter_does_not_serve_the_manifest(monkeypatch):
    """Failing closed includes the manifest. It names the whole agent-facing surface."""
    monkeypatch.delenv(adapter_app.TENANT_CREDENTIAL_ENV, raising=False)
    async with _client() as client:
        answer = await client.get("/_modules")
    assert answer.status_code == 503


async def test_a_wrong_credential_is_401_and_a_missing_one_is_not(configured):
    async with _client() as client:
        wrong = await client.get("/_modules", headers={"Authorization": "Bearer nope"})
        right = await client.get("/_modules", headers={"Authorization": f"Bearer {configured}"})
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "UNAUTHENTICATED"
    assert right.status_code == 200
    assert right.json()["forge"] == "funnelforge"


# ------------------------------------------------------- trap #3: the correlation pair


async def test_the_office_header_names_are_imported_not_retyped():
    """*"A header read under the wrong name does not fail. It reads as absent."*

    The first adapter read `X-Office-Trace-Id`, FastAPI bound it to `None` on every
    request, and the call returned 200 with the correlation id silently missing. So the
    names are imported from `broker/executor.py`; this asserts nobody has since typed a
    copy beside the import.
    """
    source = Path(adapter_app.__file__).read_text(encoding="utf-8")
    for header in (
        executor.HEADER_AGENT,
        executor.HEADER_VENTURE,
        executor.HEADER_TRACE,
        executor.HEADER_IDEMPOTENCY,
    ):
        assert f'"{header}"' not in source, (
            f"{header!r} is written literally in the adapter. Import it from "
            "broker.executor so a rename there breaks this at import."
        )
    assert executor.HEADER_TRACE == "X-Office-Trace"


async def test_every_answer_carries_the_forge_request_id(configured):
    """The Office stores it as `agent_call_ledger.forge_side_ref`.

    That pair is what makes a call traceable from either end, and both sides return 200
    without it - so it is asserted on a refusal and on a 404 too, not only on a success.
    """
    async with _client() as client:
        refused = await client.post(
            "/send_brief_cover",
            headers={"Authorization": f"Bearer {configured}"},
            json={"recipient_email": "a@example.invalid", "compliance_state": "fail"},
        )
        unbound = await client.post(
            "/send_engagement_letter_cover",
            headers={"Authorization": f"Bearer {configured}"},
            json={},
        )
    assert refused.headers.get(adapter_app.HEADER_FORGE_REQUEST)
    assert unbound.headers.get(adapter_app.HEADER_FORGE_REQUEST)


# ---------------------------------------------------- the refusals, over the real surface


async def test_a_non_pass_state_is_422_with_the_code_over_http(configured):
    """422, not 400: the request was well formed and the handler declined it.

    The code travels so the ledger row says which refusal fired.
    """
    async with _client() as client:
        answer = await client.post(
            "/send_intake_acknowledgment",
            headers={"Authorization": f"Bearer {configured}"},
            json={
                "recipient_email": "a@example.invalid",
                "compliance_state": "needs_review",
            },
        )
    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "COMPLIANCE_STATE_NOT_PASS"


async def test_the_non_autonomous_template_has_no_route_at_all(configured):
    """Module-gating's outer half, over HTTP.

    There is no module id an agent could send to reach the engagement letter cover
    email, under any spelling, because the dispatch map is the address space.
    """
    async with _client() as client:
        for spelling in (
            "send_engagement_letter_cover",
            "engagement_letter_cover",
            "send_approved_template",
        ):
            answer = await client.post(
                f"/{spelling}",
                headers={"Authorization": f"Bearer {configured}"},
                json={"template_id": "engagement_letter_cover", "compliance_state": "pass"},
            )
            assert answer.status_code == 404, spelling
            assert answer.json()["error"]["code"] == "MODULE_NOT_BOUND"
