"""V31 and V32 without a database — the decisions, separated from the I/O.

Both rules query something, and both have a decision underneath that does not. Those
decisions are where the mistakes would be, so they are testable on their own:

  `unattended_writes`      which auto_execute grants are refused, and which modules
                           could not be judged at all
  `_via_manifest`          what an adapter's answer is taken to mean
  `_via_probe`             when a probe is allowed to answer, and when it must not

The probe calibration test is the one to keep. A probe that cannot tell a bound module
from an unbound one, and reports found anyway, is worse than no check: it produces a
PASS on a Pack nobody verified.
"""

from __future__ import annotations

import copy
from pathlib import Path

import httpx
import pytest

from broker import forge_modules
from generators.pack import BusinessPack, load_pack
from generators.validator import ModuleShape, unattended_writes

PACK_PATH = Path(__file__).resolve().parents[2] / "packs" / "greenstone.yaml"


@pytest.fixture(scope="module")
def greenstone() -> BusinessPack:
    return load_pack(PACK_PATH)


@pytest.fixture
def one_module(greenstone: BusinessPack) -> tuple[BusinessPack, str, str]:
    """A Pack where exactly one position operates exactly one module, unattended."""
    pack = copy.deepcopy(greenstone)
    binding = pack.forge_dependencies.forge_bindings[0]
    forge, module = binding.forge.lower(), binding.modules_expected[0]

    for position in pack.positions_required:
        position.forge_modules_operated = []
        position.trust_tier_ceiling = "propose"
    pack.positions_required[0].forge_modules_operated = [module]
    pack.positions_required[0].trust_tier_ceiling = "auto_execute"
    return pack, forge, module


# ------------------------------------------------------------------ V31 decisions

def test_a_mutating_at_most_once_module_is_refused_unattended(one_module):
    pack, forge, module = one_module

    refusals, unresolved = unattended_writes(
        pack, {(forge, module): ModuleShape(True, "at_most_once", "adapter_manifest")}
    )

    assert not unresolved
    assert len(refusals) == 1
    assert module in refusals[0]


def test_the_same_module_is_allowed_below_auto_execute(one_module):
    """The tier is the finding, not the module. `propose` puts a human in the path."""
    pack, forge, module = one_module
    pack.positions_required[0].trust_tier_ceiling = "propose"

    refusals, unresolved = unattended_writes(
        pack, {(forge, module): ModuleShape(True, "at_most_once", "adapter_manifest")}
    )

    assert not refusals and not unresolved


def test_a_mutating_module_with_an_idempotency_key_is_allowed(one_module):
    """A retry that the Forge de-duplicates is a retry the audit trail survives."""
    pack, forge, module = one_module

    refusals, _ = unattended_writes(
        pack, {(forge, module): ModuleShape(True, "key", "adapter_manifest")}
    )

    assert not refusals


def test_a_read_only_at_most_once_module_is_allowed(one_module):
    """`at_most_once` on a read writes nothing, so calling it twice records nothing."""
    pack, forge, module = one_module

    refusals, _ = unattended_writes(
        pack, {(forge, module): ModuleShape(False, "at_most_once", "adapter_manifest")}
    )

    assert not refusals


def test_a_module_with_no_registry_row_is_unresolved_not_passed(one_module):
    """The shape is unknown, so the tier has not been checked. Not a pass."""
    pack, _forge, module = one_module

    refusals, unresolved = unattended_writes(pack, {})

    assert not refusals
    assert len(unresolved) == 1
    assert module in unresolved[0]


def test_a_refusal_outranks_an_unresolved_module(greenstone):
    """A defect that has been found does not stop being found.

    One module is refused and another cannot be judged. Reporting NOT_RUN here would
    bury a real finding behind an unrelated gap.
    """
    pack = copy.deepcopy(greenstone)
    binding = pack.forge_dependencies.forge_bindings[0]
    forge = binding.forge.lower()
    known, unknown = binding.modules_expected[0], binding.modules_expected[1]

    for position in pack.positions_required:
        position.forge_modules_operated = []
        position.trust_tier_ceiling = "propose"
    pack.positions_required[0].forge_modules_operated = [known, unknown]
    pack.positions_required[0].trust_tier_ceiling = "auto_execute"

    refusals, unresolved = unattended_writes(
        pack, {(forge, known): ModuleShape(True, "at_most_once", "adapter_manifest")}
    )

    assert refusals and unresolved  # the rule reports the refusal; both are visible


# ------------------------------------------------------- V32: reading a Forge's answer

ROW = {
    "forge_id": "cre-forge",
    "base_url": "https://cre.example/forge",
    "api_version": "1.4.0",
    "auth_model": "bearer",
    "credential_ref": "env://CRE_TOKEN",
}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_manifest_is_read_as_what_the_forge_dispatches():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/_modules")
        return httpx.Response(200, json={"modules": ["property_lookup", "comp_analysis"]})

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(
            http, ROW["base_url"], {}, 5.0, ROW
        )

    assert isinstance(answer, forge_modules.ForgeModules)
    assert answer.method == "adapter_manifest"
    assert answer.missing({"property_lookup", "buyer_match"}) == ["buyer_match"]
    assert answer.provenance == "cre-forge@1.4.0 via adapter_manifest"


async def test_no_manifest_endpoint_is_unread_not_an_empty_forge():
    """404 on the manifest must not read as a Forge that dispatches nothing.

    An empty answer is a claim about the Forge. Not being able to ask is a fact about
    the adapter, and only one of the two is true here.
    """
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(http, ROW["base_url"], {}, 5.0, ROW)

    assert isinstance(answer, forge_modules.Unread)
    assert "no /_modules manifest" in answer.reason


async def test_a_manifest_that_is_not_a_module_list_is_unread():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"modules": "property_lookup"})

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(http, ROW["base_url"], {}, 5.0, ROW)

    assert isinstance(answer, forge_modules.Unread)


async def test_an_unreachable_forge_is_unread():
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(http, ROW["base_url"], {}, 5.0, ROW)

    assert isinstance(answer, forge_modules.Unread)
    assert "unreachable" in answer.reason


# ----------------------------------------------------------------- the probe fallback

async def test_a_calibrated_probe_separates_bound_from_unbound():
    """A route table with one path per module. OPTIONS runs no handler."""
    bound = {"property_lookup", "comp_analysis"}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "OPTIONS"
        module_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(405 if module_id in bound else 404)

    async with _client(handler) as http:
        answer = await forge_modules._via_probe(
            http, ROW["base_url"], {}, 5.0, ROW,
            {"property_lookup", "comp_analysis", "lender_match"},
        )

    assert isinstance(answer, forge_modules.ForgeModules)
    assert answer.method == "probe"
    assert answer.missing({"property_lookup", "lender_match"}) == ["lender_match"]


async def test_an_uncalibrated_probe_refuses_to_answer():
    """The CRE adapter's shape: `POST /{module_id}` matches every id.

    Nothing 404s, so every module looks bound — including the three that do not exist.
    A probe that reported PASS here would produce exactly the green light this whole
    check was built to stop.
    """
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(405)  # the path template matches anything

    async with _client(handler) as http:
        answer = await forge_modules._via_probe(
            http, ROW["base_url"], {}, 5.0, ROW, {"lender_match"}
        )

    assert isinstance(answer, forge_modules.Unread)
    assert "not calibrated" in answer.reason
    assert "Serve /_modules" in answer.reason


def test_every_report_carries_its_own_scope():
    """A conformance verdict without its limits is the overclaim it exists to catch."""
    assert "not that it works" in forge_modules.SCOPE


# ------------------------------------------- a hand-written row is not evidence

def test_a_refusal_stands_on_a_hand_written_row(one_module):
    """Blocking on a claim that may be wrong is safe. Passing on one is not.

    A hand-written row saying a module is an at-most-once writer might be wrong,
    and refusing on it blocks a Pack that was probably fine. That is the safe
    direction, so the refusal stands.
    """
    pack, forge, module = one_module

    refusals, _ = unattended_writes(
        pack, {(forge, module): ModuleShape(True, "at_most_once", "hand")}
    )

    assert len(refusals) == 1


def test_a_pass_on_a_hand_written_row_is_not_a_pass(one_module):
    """The other direction, and the one that matters.

    `property_lookup` was recorded `is_mutating: TRUE` by hand and it is a
    search — the only module anybody had ever called had the checkable half
    wrong. A row like that saying "harmless read" is what hands an unattended
    agent a writer, so a clean answer resting on one is NOT_RUN, not PASS.
    """
    pack, forge, module = one_module

    refusals, unresolved = unattended_writes(
        pack, {(forge, module): ModuleShape(False, "natural", "hand")}
    )

    assert not refusals
    assert len(unresolved) == 1
    assert "never verified" in unresolved[0]


def test_a_probe_verified_row_is_evidence_enough_to_pass(one_module):
    pack, forge, module = one_module

    _refusals, unresolved = unattended_writes(
        pack, {(forge, module): ModuleShape(False, "natural", "probe")}
    )

    assert not unresolved


# --------------------------------------------- shapes as the manifest states them

async def test_a_manifest_that_states_shapes_is_read_as_stating_them():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"modules": [
            {"module_id": "property_lookup", "is_mutating": False,
             "idempotency_support": "natural"},
            {"module_id": "underwrite_deal", "is_mutating": True,
             "idempotency_support": "natural"},
        ]})

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(http, ROW["base_url"], {}, 5.0, ROW)

    assert isinstance(answer, forge_modules.ForgeModules)
    assert answer.modules == {"property_lookup", "underwrite_deal"}
    assert answer.shapes is not None
    assert answer.shapes["property_lookup"].is_mutating is False
    assert answer.shapes["underwrite_deal"].is_mutating is True


async def test_a_manifest_of_bare_names_still_answers_the_existence_question():
    """An older adapter. The derived half is the module list, and it is still there.

    `shapes` is None rather than empty: the question was not answered, and the
    verifier leaves those columns alone rather than overwriting them with a guess.
    """
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"modules": ["property_lookup"]})

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(http, ROW["base_url"], {}, 5.0, ROW)

    assert isinstance(answer, forge_modules.ForgeModules)
    assert answer.modules == {"property_lookup"}
    assert answer.shapes is None


async def test_an_idempotency_value_the_registry_cannot_store_is_unread():
    """A fourth value is a manifest this cannot read, not a new kind of module."""
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"modules": [
            {"module_id": "x", "is_mutating": False,
             "idempotency_support": "probably_fine"},
        ]})

    async with _client(handler) as http:
        answer = await forge_modules._via_manifest(http, ROW["base_url"], {}, 5.0, ROW)

    assert isinstance(answer, forge_modules.Unread)


async def test_a_probe_never_states_a_shape():
    """It establishes that a path exists. It cannot say what happens behind it."""
    async def handler(request: httpx.Request) -> httpx.Response:
        module_id = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(405 if module_id == "property_lookup" else 404)

    async with _client(handler) as http:
        answer = await forge_modules._via_probe(
            http, ROW["base_url"], {}, 5.0, ROW, {"property_lookup"}
        )

    assert isinstance(answer, forge_modules.ForgeModules)
    assert answer.shapes is None
