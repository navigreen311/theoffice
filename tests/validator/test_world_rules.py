"""V2, V6, V11, V28, V31 and V32 — the rules that read the world, not the document.

A Pack that *declares* a Forge is bridged proves nothing. That is precisely the state
Gate 0 exists to catch, so these rules query the database and cannot be satisfied by
editing YAML.

V32 goes one further and does not trust the database either. `forge_module_registry` is
rows a human wrote, so resolving a Pack against it compares two claims; V32 resolves
against what the Forge's own adapter dispatches. It proves a handler is bound to the
name — not that it works, and not that it does what the name says.

`ASSUMPTION` — Greenstone's operating Forge is CRE Forge, and the bridge is going to
CapitalForge first. In production this Pack FAILS V2 until CRE Forge is registered with
a credential and non-RED health. These tests register it explicitly so the other rules
can be exercised; `test_gate_0_blocks_an_unbridged_forge` covers the real state.
"""

from __future__ import annotations

import copy
import uuid
from pathlib import Path

import psycopg
import pytest

from broker.db import connection
from generators.pack import BusinessPack, load_pack
from generators.validator import Verdict, validate
from tests.conftest import requires_db
from tests.world import COMPLIANCE_ENTRIES

pytestmark = [requires_db, pytest.mark.db]

PACK_PATH = Path(__file__).resolve().parents[2] / "packs" / "greenstone.yaml"

CRE_MODULES = (
    "property_lookup", "comp_analysis", "underwrite_deal", "buyer_match", "generate_loi",
)
SIM_MODULES = ("run_scenario_pack", "gate_result")
VOICE_MODULES = ("place_call", "transcribe_call")


@pytest.fixture
def greenstone() -> BusinessPack:
    return load_pack(PACK_PATH)


@pytest.fixture
def stocked_library(admin: psycopg.Connection):
    """The two Compliance Library entries the Greenstone Pack names.

    Separate from `bridged_world` on purpose: V28 must be exercisable with the bridge
    up and the library empty, which is the realistic order in which the two get built.
    """
    _clear_library(admin)
    with admin.cursor() as cur:
        for entry in COMPLIANCE_ENTRIES:
            cur.execute(
                """
                INSERT INTO compliance_library_entry
                  (entry_ref, framework, jurisdiction, applicability_rule,
                   agent_behavior_implication, escalation_trigger, citation,
                   runtime_flag, authored_by)
                VALUES (%(entry_ref)s, %(framework)s, %(jurisdiction)s,
                        %(applicability_rule)s, %(agent_behavior_implication)s,
                        %(escalation_trigger)s, %(citation)s, %(runtime_flag)s,
                        '00000000-0000-5000-8000-00000000aaaa')
                """,
                entry,
            )
    admin.commit()
    yield
    _clear_library(admin)


def _clear_library(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        for entry in COMPLIANCE_ENTRIES:
            cur.execute(
                "DELETE FROM compliance_library_entry WHERE entry_ref = %s",
                (entry["entry_ref"],),
            )
    conn.commit()


@pytest.fixture
def bridged_world(admin: psycopg.Connection):
    """Register the Forges the Greenstone Pack depends on, bridged and healthy.

    Returns a handle that can un-bridge one of them, so the Gate 0 test breaks the
    world rather than the Pack — a Pack edit would prove the wrong thing.
    """
    # The department list is part of a prepared world too: V29 and V30 ask the Village,
    # and a world that has not answered leaves them NOT_RUN - which is correct, and is
    # not the state this fixture exists to build.
    from tests.world import seed_departments

    seed_departments()

    forges = {
        "cre-forge": ("1.4.0", CRE_MODULES),
        "simforge": ("3.2.0", SIM_MODULES),
        "voiceforge": ("2.0.0", VOICE_MODULES),
    }
    _wipe(admin, forges)
    with admin.cursor() as cur:
        for forge_id, (api_version, modules) in forges.items():
            cur.execute(
                """
                INSERT INTO forge_registry
                  (forge_id, display_name, base_url, api_version, auth_model,
                   credential_mode, health_status)
                VALUES (%s, %s, 'https://example.invalid', %s, 'bearer', 'brokered', 'GREEN')
                """,
                (forge_id, forge_id, api_version),
            )
            cur.execute(
                """
                INSERT INTO forge_tenant_credential
                  (forge_id, credential_ref, scope, rotation_due, break_glass_holders)
                VALUES (%s, %s, 'tenant', CURRENT_DATE + 90, %s)
                """,
                (forge_id, f"env://{forge_id.upper().replace('-', '_')}_TOKEN",
                 [str(uuid.uuid4()), str(uuid.uuid4())]),
            )
            for module_id in modules:
                cur.execute(
                    """
                    INSERT INTO forge_module_registry
                      (forge_id, module_id, module_name, idempotency_support, is_mutating,
                       verified_at, verified_against, verification_method)
                    VALUES (%s, %s, %s, 'key', TRUE,
                            now(), 'test world', 'adapter_manifest')
                    """,
                    (forge_id, module_id, module_id.replace("_", " ").title()),
                )
    admin.commit()
    yield admin
    _wipe(admin, forges)


def _wipe(conn: psycopg.Connection, forges: dict[str, object]) -> None:
    with conn.cursor() as cur:
        for forge_id in forges:
            cur.execute(
                "DELETE FROM forge_operating_instruction WHERE forge_id = %s", (forge_id,)
            )
            cur.execute(
                "DELETE FROM forge_tenant_credential WHERE forge_id = %s", (forge_id,)
            )
            cur.execute("DELETE FROM forge_module_registry WHERE forge_id = %s", (forge_id,))
            cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    conn.commit()


def author_instructions(conn: psycopg.Connection, modules: tuple[str, ...]) -> None:
    # The world's own curriculum, not a second placeholder one. This helper used to
    # write `"what_it_does": "x"` and `inputs: {"a": "b"}` - which V11 accepted, because
    # V11 only checked that a row existed. Now that it reads the content, a fixture that
    # writes placeholders is a fixture that tests the defect rather than the rule.
    from tests.world import INSTRUCTION_CONTENT

    content = INSTRUCTION_CONTENT
    with conn.cursor() as cur:
        for module_id in modules:
            forge = "voiceforge" if module_id in VOICE_MODULES else "cre-forge"
            cur.execute(
                """
                INSERT INTO forge_operating_instruction
                  (forge_id, module_id, instruction_version, forge_api_version,
                   content, content_hash, authored_by)
                VALUES (%s, %s, '1.0.0', '1.4.0', %s, '', %s)
                """,
                (forge, module_id, psycopg.types.json.Jsonb(content), str(uuid.uuid4())),
            )
    conn.commit()


# --------------------------------------------------------------------------- V2

async def test_gate_0_passes_when_every_hard_forge_is_bridged(greenstone, bridged_world):
    async with connection() as conn:
        report = await validate(greenstone, conn)
    assert report.get("V2").verdict is Verdict.PASS


async def test_gate_0_blocks_an_unregistered_forge(greenstone, bridged_world, admin):
    """The real state today: CRE Forge is not bridged, CapitalForge is going first."""
    _wipe(admin, {"cre-forge": None})

    async with connection() as conn:
        report = await validate(greenstone, conn)

    v2 = report.get("V2")
    assert v2.verdict is Verdict.FAIL
    assert "not in forge_registry" in v2.message
    assert not report.passed, "Gate 0 must block the Pack"


async def test_gate_0_blocks_a_forge_with_no_tenant_credential(
    greenstone, bridged_world, admin
):
    """Healthy is not the same as reachable. A Forge with no credential is one the
    broker cannot authenticate to, however green its health looks."""
    with admin.cursor() as cur:
        cur.execute("DELETE FROM forge_tenant_credential WHERE forge_id = 'cre-forge'")
    admin.commit()

    async with connection() as conn:
        report = await validate(greenstone, conn)

    v2 = report.get("V2")
    assert v2.verdict is Verdict.FAIL
    assert "no tenant credential" in v2.message


async def test_gate_0_blocks_a_red_forge(greenstone, bridged_world, admin):
    with admin.cursor() as cur:
        cur.execute("UPDATE forge_registry SET health_status = 'RED' WHERE forge_id = 'cre-forge'")
    admin.commit()

    async with connection() as conn:
        report = await validate(greenstone, conn)
    assert report.get("V2").verdict is Verdict.FAIL
    assert "RED" in report.get("V2").message


async def test_gate_0_ignores_a_soft_forge(greenstone, bridged_world, admin):
    """VoiceForge is `soft`. Losing it degrades outreach; it does not block
    provisioning, and Gate 0 says 'hard binding' for exactly this reason."""
    with admin.cursor() as cur:
        cur.execute("DELETE FROM forge_tenant_credential WHERE forge_id = 'voiceforge'")
    admin.commit()

    async with connection() as conn:
        report = await validate(greenstone, conn)
    assert report.get("V2").verdict is Verdict.PASS


async def test_a_pack_cannot_declare_itself_bridged(greenstone, bridged_world, admin):
    """The point of V2. Editing the Pack cannot make an unbridged Forge bridged."""
    _wipe(admin, {"cre-forge": None})
    lying = copy.deepcopy(greenstone)
    for binding in lying.forge_dependencies.forge_bindings:
        binding.credential_mode = "native"  # declare anything you like

    async with connection() as conn:
        report = await validate(lying, conn)
    assert report.get("V2").verdict is Verdict.FAIL


# --------------------------------------------------------------------------- V6

async def test_v6_passes_when_every_module_resolves(greenstone, bridged_world):
    async with connection() as conn:
        report = await validate(greenstone, conn)
    assert report.get("V6").verdict is Verdict.PASS


async def test_v6_fails_on_a_module_that_does_not_exist(greenstone, bridged_world, admin):
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM forge_module_registry "
            "WHERE forge_id = 'cre-forge' AND module_id = 'underwrite_deal'"
        )
    admin.commit()

    async with connection() as conn:
        report = await validate(greenstone, conn)
    v6 = report.get("V6")
    assert v6.verdict is Verdict.FAIL
    assert "underwrite_deal" in v6.message


# -------------------------------------------------------------------------- V11

async def test_v11_fails_when_instructions_are_not_authored(greenstone, bridged_world):
    """Without instructions SimForge has nothing to test against, so the position
    can never be certified and the appointment can never be filled."""
    async with connection() as conn:
        report = await validate(greenstone, conn)
    v11 = report.get("V11")
    assert v11.verdict is Verdict.FAIL
    assert "property_lookup" in v11.message


async def test_v11_passes_once_every_operated_module_has_instructions(
    greenstone, bridged_world, admin
):
    operated = tuple({m for p in greenstone.positions_required for m in p.forge_modules_operated})
    author_instructions(admin, operated)

    async with connection() as conn:
        report = await validate(greenstone, conn)
    assert report.get("V11").verdict is Verdict.PASS, report.get("V11").message


# ------------------------------------------------------------------------- V28

async def test_v28_fails_when_a_library_ref_resolves_to_nothing(
    greenstone, bridged_world, admin
):
    """K4 — the half V4 could never check.

    The Greenstone Pack names two entries. V4 passes because they are *named*; V28 asks
    whether they exist, and with an empty library the answer is no. This is the same
    upgrade V2 represents over a Pack that declares a Forge is bridged.
    """
    _clear_library(admin)
    async with connection() as conn:
        report = await validate(greenstone, conn)

    v4 = report.get("V4")
    v28 = report.get("V28")
    assert v4.verdict is Verdict.PASS, "V4 only checks that a ref is named"
    assert v28.verdict is Verdict.FAIL
    assert "COMPLIANCE LIBRARY GAP" in v28.message
    assert "compliance/ftc-tsr-v2" in v28.message
    assert "2 of 2" in v28.message, "report the denominator, not just the misses"


async def test_v28_passes_once_the_entries_exist(
    greenstone, bridged_world, stocked_library
):
    """The rule must let a correct Pack through, or it is an outage."""
    async with connection() as conn:
        report = await validate(greenstone, conn)
    result = report.get("V28")
    assert result.verdict is Verdict.PASS, result.message
    assert "2 of 2" in result.message


async def test_v28_accepts_an_explicit_library_gap(greenstone, bridged_world, admin):
    """An honest `library_gap: true` is not a failure.

    The Pack has said the entry does not exist, which is the thing V28 would otherwise
    have to discover. Failing it here would punish the Pack that told the truth and
    leave the one that named a ref into thin air indistinguishable from a correct one.
    """
    _clear_library(admin)
    gapped = copy.deepcopy(greenstone)
    for surface in gapped.market.compliance_surface:
        object.__setattr__(surface, "library_entry_ref", None)
        object.__setattr__(surface, "library_gap", True)

    async with connection() as conn:
        report = await validate(gapped, conn)
    assert report.get("V28").verdict is Verdict.PASS
    assert report.get("V4").verdict is Verdict.PASS


async def test_v28_is_not_run_without_a_connection_never_a_pass(greenstone):
    """K5 — the rule that cannot run says so.

    Part 10.1: NOT_RUN must never be reported as a failure. The converse matters just as
    much, and a Pack whose library check could not run has not been validated.
    """
    report = await validate(greenstone)
    result = report.get("V28")
    assert result.verdict is Verdict.NOT_RUN
    assert result.verdict is not Verdict.PASS
    assert not report.passed, "NOT_RUN never counts toward a passing report"


# ---------------------------------------------------------------- whole-Pack gate

@pytest.fixture
def adapters_dispatching(greenstone, monkeypatch):
    """Every bound Forge answers `_modules` with exactly what the Pack declares.

    The bridged world registers Forges at `https://example.invalid`, which is right for
    every other rule and cannot answer this one. Standing up three HTTP servers to make
    a database fixture complete would be a lot of machinery for a question already
    answered directly: `tests/validator/test_module_conformance.py` drives the real
    manifest and probe paths over a mock transport, including the calibration failure.

    What this fixture supplies is the *state* — adapters that are up and dispatch what
    was declared — so the whole-Pack gate can assert that a fully prepared world has
    nothing left NOT_RUN.
    """
    from datetime import UTC, datetime

    from broker import forge_modules

    async def _answer(_conn, forge_id, **_kw):
        declared = {
            m
            for b in greenstone.forge_dependencies.forge_bindings
            if b.forge.lower() == forge_id.lower()
            for m in b.modules_expected
        }
        return forge_modules.ForgeModules(
            forge_id=forge_id,
            modules=frozenset(declared),
            method="adapter_manifest",
            api_version="1.4.0",
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(forge_modules, "read", _answer)
    forge_modules.forget()
    yield
    forge_modules.forget()


async def test_greenstone_passes_gate_2_in_a_fully_prepared_world(
    greenstone, bridged_world, stocked_library, adapters_dispatching, admin
):
    """The blueprint acceptance criterion for this increment: the Greenstone Pack
    passes validation.

    'Fully prepared' now means four things, and none of them is true today: the bridge
    reaches CRE Forge, instructions are authored, the Compliance Library holds the
    entries the Pack names, and each Forge's adapter dispatches the modules the Pack
    declares. All four are exactly what Gate 0, V11, V28 and V32 exist to require
    before provisioning.

    The fourth is the one that is not a database state. V6 already asked whether the
    modules resolve in `forge_module_registry` and the fixture satisfies it by writing
    the rows — which is the point of V32: rows are what somebody typed, and a prepared
    world is one where the Forge itself dispatches them.
    """
    operated = tuple({m for p in greenstone.positions_required for m in p.forge_modules_operated})
    author_instructions(admin, operated)

    async with connection() as conn:
        report = await validate(greenstone, conn)

    assert report.failures == [], report.render()
    assert report.not_run == [r for r in report.not_run if r.rule_id == "V24"], (
        "only V24 may be deferred; every other rule must have run"
    )


# ------------------------------------------------------------------------- V31

async def test_v31_passes_when_every_unattended_module_survives_a_retry(
    greenstone, bridged_world
):
    """The fixture registers every module with an idempotency key.

    A retry the Forge de-duplicates is a retry the audit trail survives, so the tier
    is not the finding here whatever it is set to.
    """
    async with connection() as conn:
        report = await validate(greenstone, conn)
    assert report.get("V31").verdict is Verdict.PASS, report.get("V31").message


async def test_v31_refuses_auto_execute_over_a_mutating_at_most_once_module(
    greenstone, bridged_world, admin
):
    """The shape `regulator_dossier_export` is written around.

    Every call mints an id, writes a row and emits an event, so a retry after a
    timeout produces a second record of the same act and the audit trail then shows
    two. An unattended agent is the caller with nobody to stop it.
    """
    module = greenstone.positions_required[0].forge_modules_operated[0]
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_module_registry SET is_mutating = TRUE, "
            "idempotency_support = 'at_most_once' WHERE module_id = %s",
            (module,),
        )
    admin.commit()
    pack = copy.deepcopy(greenstone)
    pack.positions_required[0].trust_tier_ceiling = "auto_execute"

    async with connection() as conn:
        report = await validate(pack, conn)

    v31 = report.get("V31")
    assert v31.verdict is Verdict.FAIL
    assert module in v31.message
    assert "propose" in v31.message, "the message must name the way out"


async def test_v31_is_not_run_when_the_module_has_no_registry_row(
    greenstone, bridged_world, admin
):
    """An unknown shape is not a safe shape."""
    module = greenstone.positions_required[0].forge_modules_operated[0]
    with admin.cursor() as cur:
        cur.execute("DELETE FROM forge_module_registry WHERE module_id = %s", (module,))
    admin.commit()
    pack = copy.deepcopy(greenstone)
    pack.positions_required[0].trust_tier_ceiling = "auto_execute"

    async with connection() as conn:
        report = await validate(pack, conn)

    v31 = report.get("V31")
    assert v31.verdict is Verdict.NOT_RUN
    assert v31.verdict is not Verdict.PASS
    assert not report.passed


# ------------------------------------------------------------------------- V32

async def test_v32_is_not_run_when_no_adapter_can_be_reached(greenstone, bridged_world):
    """The state every Forge is in before its adapter exists.

    Not a FAIL: nothing about the Pack is known to be wrong. Not a PASS: nothing has
    been resolved against the Forge. This is the verdict the whole rule is built to be
    able to give.
    """
    from broker import forge_modules

    forge_modules.forget()
    async with connection() as conn:
        report = await validate(greenstone, conn)

    v32 = report.get("V32")
    assert v32.verdict is Verdict.NOT_RUN
    assert not report.passed, "a Pack nobody could check has not been validated"


async def test_v32_fails_on_a_module_the_forge_does_not_dispatch(
    greenstone, bridged_world, monkeypatch
):
    """The `lender_match` shape: declared, granted, and not there.

    The Forge answers, and one declared module is not in what it dispatches. The
    registry is not consulted — that is V6's question, and a row saying the module
    exists is exactly the claim this rule exists to disbelieve.
    """
    from datetime import UTC, datetime

    from broker import forge_modules

    absent = greenstone.forge_dependencies.forge_bindings[0].modules_expected[0]

    async def _answer(_conn, forge_id, **_kw):
        declared = {
            m
            for b in greenstone.forge_dependencies.forge_bindings
            if b.forge.lower() == forge_id.lower()
            for m in b.modules_expected
        }
        return forge_modules.ForgeModules(
            forge_id=forge_id,
            modules=frozenset(declared - {absent}),
            method="adapter_manifest",
            api_version="1.4.0",
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(forge_modules, "read", _answer)
    forge_modules.forget()

    async with connection() as conn:
        report = await validate(greenstone, conn)

    v32 = report.get("V32")
    assert v32.verdict is Verdict.FAIL
    assert absent in v32.message
    assert "capability that is not there" in v32.message
    assert "not that it works" in v32.message, "a verdict must carry its own scope"


async def test_the_report_header_states_what_conformance_proved(
    greenstone, bridged_world, monkeypatch
):
    """The scope belongs where the verdict is read, not only in a docstring."""
    from datetime import UTC, datetime

    from broker import forge_modules

    async def _answer(_conn, forge_id, **_kw):
        declared = {
            m
            for b in greenstone.forge_dependencies.forge_bindings
            if b.forge.lower() == forge_id.lower()
            for m in b.modules_expected
        }
        return forge_modules.ForgeModules(
            forge_id=forge_id,
            modules=frozenset(declared),
            method="adapter_manifest",
            api_version="1.4.0",
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(forge_modules, "read", _answer)
    forge_modules.forget()

    async with connection() as conn:
        report = await validate(greenstone, conn)

    assert report.get("V32").verdict is Verdict.PASS, report.get("V32").message
    assert "proves a handler is bound to the name" in report.render()
