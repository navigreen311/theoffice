"""Registry rows and manifest rows, both produced by generators rather than typed.

`docs/coordination-plan-gate45-packages.md`, P-13: *"registry and manifest rows via the
proper generators, NOT by hand."* Two different generators, and the tests are kept apart
because the two rows mean different things:

    forge_module_registry   what The Office believes a Forge exposes, and what
                            `broker/grants.py` reads for `is_mutating` - the copy V31
                            spends. Produced by `generators/forge_module_rows.py`, new
                            here, from the adapter's dispatch map INTERSECTED with the
                            Pack's declaration.

    venture_forge_manifest  which of those a venture is entitled to call. Produced by
                            generators 5.6 and 5.7, which already existed; this asserts
                            the FunnelForge binding reaches them and comes out the far
                            side, not that the generators work.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.funnelforge.modules import MODULES, manifest
from broker import forge_modules
from generators import forge_module_rows
from generators.forge_manifest import generate as generate_manifest
from generators.pack import load_pack
from generators.roles import generate as generate_roles
from generators.workflow import generate as generate_workflow

ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / "packs" / "burkham-wickmont.draft.yaml"
FORGE = "funnelforge"
API_VERSION = "1.0.0"


@pytest.fixture(scope="module")
def pack():
    return load_pack(PACK_PATH)


@pytest.fixture(scope="module")
def declared(pack):
    binding = next(
        b for b in pack.forge_dependencies.forge_bindings if b.forge == FORGE
    )
    return set(binding.modules_expected)


# ------------------------------------------------------------------- registry rows


def test_idempotency_values_match_the_broker():
    """The generator restates the three values rather than importing the broker.

    A generator importing `broker` inverts this package's dependency direction. The cost
    of restating is that the two can drift, so this is the thing that notices.
    """
    assert forge_module_rows.IDEMPOTENCY_SUPPORT == forge_modules.IDEMPOTENCY_SUPPORT


def test_a_row_is_produced_for_every_module_both_sides_name(declared):
    generated = forge_module_rows.generate(FORGE, API_VERSION, manifest(), declared)

    assert generated.blocked is None
    assert [r.module_id for r in generated.rows] == sorted(MODULES)
    assert generated.dispatched_not_declared == ()
    assert generated.declared_not_dispatched == ()


def test_the_shape_in_a_row_comes_from_the_adapter_not_from_anyone_typing_it(declared):
    """`property_lookup` was recorded `is_mutating: TRUE` by hand and it is a search.

    Every field below is compared against the binding site, which is where the
    declaration lives, so a row cannot disagree with the handler it describes.
    """
    generated = forge_module_rows.generate(FORGE, API_VERSION, manifest(), declared)
    by_id = {r.module_id: r for r in generated.rows}

    for module_id, binding in MODULES.items():
        assert by_id[module_id].is_mutating == binding.is_mutating
        assert by_id[module_id].idempotency_support == binding.idempotency_support
        assert by_id[module_id].verified_against == (
            f"{FORGE}@{API_VERSION} via adapter_manifest"
        )


def test_a_dispatched_module_nobody_declared_gets_no_row(declared):
    """*"A Forge does not enlarge its own agent-facing surface."*

    Deriving rows from the adapter alone would mean that adding a handler is enough to
    make it grantable, which inverts the point of the registry.
    """
    generated = forge_module_rows.generate(
        FORGE, API_VERSION, manifest(), declared - {"capture_contact"}
    )
    assert "capture_contact" not in {r.module_id for r in generated.rows}
    assert generated.dispatched_not_declared == ("capture_contact",)


def test_a_declared_module_the_adapter_does_not_dispatch_gets_no_row(declared):
    """The `lender_match` shape: a Pack, a role and a registry row all agreeing about a
    capability that does not exist, because each was made consistent with the last."""
    generated = forge_module_rows.generate(
        FORGE, API_VERSION, manifest(), declared | {"send_whatever_marketing_wants"}
    )
    assert generated.declared_not_dispatched == ("send_whatever_marketing_wants",)
    assert len(generated.rows) == len(MODULES)


def test_an_unreadable_manifest_entry_blocks_the_whole_run(declared):
    """Not the one row. A manifest this cannot read is a disagreement about the
    contract, and writing the readable subset records that disagreement nowhere."""
    broken = {
        "forge": FORGE,
        "modules": [
            {"module_id": "capture_contact", "is_mutating": True,
             "idempotency_support": "natural"},
            {"module_id": "send_brief_cover", "is_mutating": True,
             "idempotency_support": "sometimes"},
        ],
    }
    generated = forge_module_rows.generate(FORGE, API_VERSION, broken, declared)
    assert generated.blocked is not None
    assert "sometimes" in generated.blocked


def test_a_reserved_prefix_is_rejected_rather_than_registered(declared):
    broken = {
        "forge": FORGE,
        "modules": [
            {"module_id": "_modules", "is_mutating": False,
             "idempotency_support": "natural"}
        ],
    }
    generated = forge_module_rows.generate(FORGE, API_VERSION, broken, declared)
    assert generated.blocked is not None
    assert "_modules" in generated.blocked


def test_compliance_flags_default_to_empty_rather_than_guessed(declared):
    """`record_consent` was given a flag that exists, resolves, passes every check, and
    is the wrong framework. A wrong flag that resolves is worse than an absent one."""
    generated = forge_module_rows.generate(FORGE, API_VERSION, manifest(), declared)
    assert all(r.compliance_flags_implied == () for r in generated.rows)


async def test_apply_refuses_without_confirmation(declared):
    generated = forge_module_rows.generate(FORGE, API_VERSION, manifest(), declared)
    with pytest.raises(ValueError, match="confirmed=True"):
        await forge_module_rows.apply(None, generated)  # type: ignore[arg-type]


# ------------------------------------------------------------------- manifest rows


def test_the_pack_declares_funnelforge_with_nine_modules(declared):
    assert declared == set(MODULES)


async def test_the_binding_reaches_the_manifest_generator(pack):
    """Generators 5.1 -> 5.3 -> 5.6, the path `runtime_config.apply` writes its rows from.

    Not asserted by hand-listing nine ids. 5.6 marks an entry `required` only when a
    workflow step names the module, and 5.3 emits a step per (stage, position, module)
    from a position's `forge_modules_operated`. So this exercises the whole chain the
    Pack edit joined up - binding -> position -> workflow step -> manifest entry - and
    any one of those links being absent shows up here as a missing entry rather than as
    an empty manifest three gates later.

    `conn=None` is 5.1's real no-database path: it skips the registry lookup, so nothing
    is stubbed and `unresolved_modules` is empty by construction rather than by mock.
    """
    roles = await generate_roles(pack, None)
    workflow = generate_workflow(pack, roles)
    forge_manifest = generate_manifest(pack, workflow)

    entries = {e.module_id: e for e in forge_manifest.entries if e.forge_id == FORGE}
    assert set(entries) == set(MODULES), sorted(set(MODULES) - set(entries))
    assert all(e.declared for e in entries.values())
    assert all(e.required for e in entries.values()), (
        "a declared module no workflow step names is DECLARED_NOT_REQUIRED (V25) and "
        "produces no grant"
    )


async def test_the_manifest_generator_reports_no_new_reconciliation_finding(pack):
    """The FunnelForge binding must not arrive carrying a `REQUIRED_NOT_DECLARED`.

    That one FAILS the Pack rather than warning, and it is the failure a position naming
    a module its binding forgot would produce.
    """
    roles = await generate_roles(pack, None)
    workflow = generate_workflow(pack, roles)
    recon = generate_manifest(pack, workflow).reconciliation

    assert not [m for m in recon.required_not_declared if m in MODULES]
    assert not [m for m in recon.declared_not_required if m in MODULES]
