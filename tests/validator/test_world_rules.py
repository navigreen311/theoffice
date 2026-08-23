"""V2, V6, V11 and V28 — the rules that read the world rather than the document.

A Pack that *declares* a Forge is bridged proves nothing. That is precisely the state
Gate 0 exists to catch, so these three rules query the database and cannot be satisfied
by editing YAML.

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
                      (forge_id, module_id, module_name, idempotency_support, is_mutating)
                    VALUES (%s, %s, %s, 'key', TRUE)
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
    content = {
        "what_it_does": "x", "what_it_does_not_do": "x", "inputs": {"a": "b"},
        "correct_sequence": ["a"], "failure_signatures": {"a": "b"},
        "retry_vs_escalate": "x", "never_do": ["x"], "compliance_coupling": ["x"],
    }
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

async def test_greenstone_passes_gate_2_in_a_fully_prepared_world(
    greenstone, bridged_world, stocked_library, admin
):
    """The blueprint acceptance criterion for this increment: the Greenstone Pack
    passes validation.

    'Fully prepared' now means three things, and none of them is true today: the bridge
    reaches CRE Forge, instructions are authored, and the Compliance Library holds the
    entries the Pack names. All three are exactly what Gate 0, V11 and V28 exist to
    require before provisioning.
    """
    operated = tuple({m for p in greenstone.positions_required for m in p.forge_modules_operated})
    author_instructions(admin, operated)

    async with connection() as conn:
        report = await validate(greenstone, conn)

    assert report.failures == [], report.render()
    assert report.not_run == [r for r in report.not_run if r.rule_id == "V24"], (
        "only V24 may be deferred; every other rule must have run"
    )
