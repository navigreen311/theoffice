"""Registry rows and manifest rows, both produced by generators rather than typed.

`docs/coordination-plan-gate45-packages.md`, P-13: *"registry and manifest rows via the
proper generators, NOT by hand."* Two different generators, and the tests are kept apart
because the two rows mean different things:

    forge_module_registry   what The Office believes a Forge exposes, and what
                            `broker/grants.py` reads for `is_mutating` - the copy V31
                            spends. Produced by `generators/forge_module_rows.py`, from
                            the adapter's dispatch map INTERSECTED with the declaration.

    venture_forge_manifest  which of those a venture is entitled to call. Produced by
                            generators 5.1 -> 5.3 -> 5.6, which already existed; these
                            tests assert the FunnelForge binding reaches them and comes
                            out the far side.

WHERE THE DECLARATION LIVES, AND WHY THAT IS A FUNCTION RATHER THAN A PATH
=========================================================================

These tests originally read the FunnelForge binding straight out of
`packs/burkham-wickmont.draft.yaml`, and that coupled two unrelated things: *does the
generator chain work* and *does one file on disk currently happen to carry a
declaration*. When the Pack edit was held back (see
`docs/plans/funnelforge-binding-RECORD.md` - adding the position moved Burkham's Gate 2
from 0 FAIL to 3 FAIL on V6, V11 and V23, because this package's owed operating
instructions and curriculum arrive there as gate failures), the second went away and
took ten tests with it. Nine of them were not even about the Pack; they errored because
a module-scoped fixture raised `StopIteration` looking for a binding that was no longer
there.

So the declaration is now resolved by `declaration()`, which reads whichever of the two
places currently holds it:

    the Pack                        once the deferred edit is re-applied
    the deferred patch              while it is held

**It is deliberately not a constant in this file.** A literal here would make
`test_the_declaration_and_the_dispatch_map_agree` a tautology - the check that a human's
declaration names exactly what the adapter dispatches only means something if the
declaration comes from outside the test. And `declaration()` raises rather than returning
an empty set when neither source carries it, so these tests cannot go quiet the way they
just did: the failure would be one loud error naming both places, not nine errors
pointing at a fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adapters.funnelforge.modules import MODULES, manifest
from broker import forge_modules
from generators import forge_module_rows
from generators.forge_manifest import generate as generate_manifest
from generators.pack import BusinessPack, ForgeBinding, Position, load_pack
from generators.roles import generate as generate_roles
from generators.workflow import generate as generate_workflow

ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / "packs" / "burkham-wickmont.draft.yaml"
DEFERRED_PATCH = ROOT / "docs" / "plans" / "funnelforge-position-DEFERRED.patch"
FORGE = "funnelforge"
API_VERSION = "1.0.0"


def _flow_sequence_after(lines: list[str], key: str) -> list[str] | None:
    """The YAML flow sequence following `key:`, from a list of already-stripped lines.

    Both sources spell the module list the same way - a key on its own line, then a
    bracketed flow sequence over several lines - so one reader serves both, and neither
    source needs to be reformatted to keep these tests working.
    """
    for index, line in enumerate(lines):
        if line.strip() != f"{key}:":
            continue
        collected: list[str] = []
        for following in lines[index + 1 :]:
            collected.append(following.strip())
            if following.strip().endswith("]"):
                loaded = yaml.safe_load(" ".join(collected))
                return list(loaded) if isinstance(loaded, list) else None
        return None
    return None


def _declared_in_pack() -> list[str] | None:
    bindings = [
        b
        for b in load_pack(PACK_PATH).forge_dependencies.forge_bindings
        if b.forge == FORGE
    ]
    return list(bindings[0].modules_expected) if bindings else None


def _declared_in_deferred_patch() -> list[str] | None:
    """The held declaration, read out of the patch that preserves it.

    Read only - `docs/plans/funnelforge-position-DEFERRED.patch` belongs to the
    coordinator. Reading it here is what stops the held declaration drifting away from
    the adapter while it sits on the shelf: a patch nothing checks is a patch that stops
    applying, and the record's promise that it can be re-applied would then be a claim
    with nothing behind it.
    """
    if not DEFERRED_PATCH.exists():
        return None
    added = [
        line[1:]
        for line in DEFERRED_PATCH.read_text(encoding="utf-8").splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return _flow_sequence_after(added, "modules_expected")


def declaration() -> set[str]:
    """The nine modules a human declared The Office intends to make grantable.

    Raises rather than returning an empty set. An empty declared set is not a neutral
    input to these tests - it makes every intersection assertion below trivially true,
    which is exactly the shape of failure that produced this function.
    """
    for read in (_declared_in_pack, _declared_in_deferred_patch):
        found = read()
        if found:
            return set(found)
    raise AssertionError(
        f"no FunnelForge declaration found in {PACK_PATH.name} and none in "
        f"{DEFERRED_PATCH.name}. One of the two must carry it: the Pack once the "
        "deferred edit is re-applied, the patch while it is held.\n"
        "  If the edit HAS been applied and the patch deleted, that is the expected end "
        "state - delete the deferred-patch branch of declaration() rather than letting "
        "these tests pass on an empty set.\n"
        "  If the patch is still there, it was reformatted: this reads `modules_expected:` "
        "on its own line followed by a bracketed YAML flow sequence, which is how both "
        "sources spell it today. Nothing is wrong with the declaration; the reader needs "
        "updating."
    )


def deferred_position() -> Position:
    """The Marketing Operations Coordinator, as the deferred patch declares it.

    Built here rather than read from the Pack for the reason in the module docstring.
    The four fields the generator chain actually consumes - the modules, the stages, the
    title and the tier - are the ones asserted against downstream; the rest is what the
    schema requires to construct a valid position.

    `auto_execute` is carried across verbatim and not softened. It is the honest
    declaration (§4.5 calls these sends Village-autonomous) and it is the tier V31
    refuses over seven of the nine. A test that quietly used `propose` here would be
    exercising the chain with a position that is not the one being deferred.
    """
    return Position(
        position_title="Marketing Operations Coordinator",
        reports_to="venture_operator",
        duties=[
            "Send approved marketing templates in a Pass compliance state",
            "Book Blueprint calls against the published appointment types",
            "Record newsletter and gated-download contacts, and read funnel analytics",
        ],
        forge_modules_operated=sorted(declaration()),
        source_department="marketing",
        compliance_flags_in_scope=[],
        headcount=1,
        trust_tier_ceiling="auto_execute",
        lifecycle_stages_owned=["Intake", "Diagnostic", "Placement"],
    )


def deferred_binding() -> ForgeBinding:
    """The FunnelForge binding, as the deferred patch declares it."""
    return ForgeBinding(
        forge=FORGE,
        api_version=API_VERSION,
        criticality="soft",
        modules_expected=sorted(declaration()),
        compliance_flags_propagated=[],
        fallback_behavior="queue",
        credential_mode="brokered",
        cost_center="burkham-marketing",
    )


@pytest.fixture(scope="module")
def bound_pack() -> BusinessPack:
    """The real Burkham Pack with the deferred binding and position applied in memory.

    The base is the Pack on disk, not a minimal fixture, because the chain under test
    reads things the surrounding Pack owns - `engagement_model.service_lines` supplies
    the lifecycle stages 5.3 iterates, and a position that owns no stage appears in no
    workflow step at all. A hand-built two-field Pack would exercise the chain against a
    world that does not resemble the one it runs in.
    """
    pack = load_pack(PACK_PATH)
    return pack.model_copy(
        update={
            "positions_required": [*pack.positions_required, deferred_position()],
            "forge_dependencies": pack.forge_dependencies.model_copy(
                update={
                    "forge_bindings": [
                        *pack.forge_dependencies.forge_bindings,
                        deferred_binding(),
                    ]
                }
            ),
        }
    )


@pytest.fixture(scope="module")
def declared() -> set[str]:
    return declaration()


# ---------------------------------------------------------------- the declaration itself


def test_the_declaration_and_the_dispatch_map_agree(declared):
    """A human's declaration names exactly what the adapter dispatches.

    This is the V6-shaped property and the reason `declaration()` reads a file rather
    than returning a constant: comparing a literal in this file against `MODULES` would
    compare the adapter to itself. The Burkham Pack once declared twelve modules of
    which three did not exist, and V6 passed on all twelve because somebody had written
    twelve rows to match.
    """
    assert declared == set(MODULES)


def test_the_declaration_is_readable_from_wherever_it_currently_lives():
    """Whichever source holds it, and it is an error for neither to.

    Named separately from the assertion above so a reader of a failure can tell "the
    declaration disagrees with the adapter" from "there is no declaration at all".
    """
    in_pack = _declared_in_pack()
    in_patch = _declared_in_deferred_patch()
    assert in_pack or in_patch, (
        "neither the Pack nor the deferred patch declares FunnelForge"
    )
    if in_pack and in_patch:
        assert set(in_pack) == set(in_patch), (
            "the Pack and the deferred patch declare different module sets. If the "
            "edit has been applied, delete the patch; do not leave two declarations."
        )


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


async def test_the_binding_reaches_the_manifest_generator(bound_pack):
    """Generators 5.1 -> 5.3 -> 5.6, the path `runtime_config.apply` writes its rows from.

    Not asserted by hand-listing nine ids. 5.6 marks an entry `required` only when a
    workflow step names the module, and 5.3 emits a step per (stage, position, module)
    from a position's `forge_modules_operated`. So this exercises the whole chain -
    binding -> position -> workflow step -> manifest entry - and any one of those links
    being absent shows up here as a missing entry rather than as an empty manifest three
    gates later.

    `conn=None` is 5.1's real no-database path: it skips the registry lookup, so nothing
    is stubbed and `unresolved_modules` is empty by construction rather than by mock.
    """
    roles = await generate_roles(bound_pack, None)
    workflow = generate_workflow(bound_pack, roles)
    forge_manifest = generate_manifest(bound_pack, workflow)

    entries = {e.module_id: e for e in forge_manifest.entries if e.forge_id == FORGE}
    assert set(entries) == set(MODULES), sorted(set(MODULES) - set(entries))
    assert all(e.declared for e in entries.values())
    assert all(e.required for e in entries.values()), (
        "a declared module no workflow step names is DECLARED_NOT_REQUIRED (V25) and "
        "produces no grant"
    )


async def test_every_module_is_named_by_a_workflow_step(bound_pack):
    """5.3's half of the chain, asserted where it happens.

    The manifest test above would still pass if 5.6 marked entries `required` for some
    other reason, and a test that can pass for the wrong reason is worth splitting. This
    reads the steps directly: nine modules, each named by at least one step belonging to
    the deferred position.
    """
    roles = await generate_roles(bound_pack, None)
    workflow = generate_workflow(bound_pack, roles)

    named: set[str] = set()
    for step in workflow.steps:
        if step.position == "Marketing Operations Coordinator":
            named |= set(step.forge_modules)
    assert named == set(MODULES), sorted(set(MODULES) ^ named)


async def test_the_manifest_generator_reports_no_new_reconciliation_finding(bound_pack):
    """The FunnelForge binding must not arrive carrying a `REQUIRED_NOT_DECLARED`.

    That one FAILS the Pack rather than warning, and it is the failure a position naming
    a module its binding forgot would produce. Run against `bound_pack`: against the Pack
    on disk, with no FunnelForge binding at all, this passed while asserting nothing.
    """
    roles = await generate_roles(bound_pack, None)
    workflow = generate_workflow(bound_pack, roles)
    recon = generate_manifest(bound_pack, workflow).reconciliation

    assert not [m for m in recon.required_not_declared if m in MODULES]
    assert not [m for m in recon.declared_not_required if m in MODULES]
