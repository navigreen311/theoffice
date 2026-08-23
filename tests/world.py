"""The Greenstone world - one definition, two suites.

This started as a fixture inside `tests/golden/test_generators.py`, which was fine
while the golden snapshots were the only thing that needed a fully bridged venture.
The provisioning suite needs the same world, and a second copy of it would drift: the
copies would disagree about which Forges are registered or which modules have
instructions, and whichever suite was read last would look correct.

`build_world` leaves the roster *uncertified*. Certification is the variable both
suites vary deliberately - the golden happy path certifies everyone for their position,
and a provisioning test that wants Gate 6 or Gate 4.5 to block certifies less than that.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import psycopg
import psycopg.types.json

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "packs" / "greenstone.yaml"

FORGE_ID = "cre-forge"
CRE_MODULES = ("property_lookup", "comp_analysis", "underwrite_deal", "buyer_match",
               "generate_loi")
VOICE_MODULES = ("place_call", "transcribe_call")

# Fixed agent ids so snapshots are stable across runs and machines. Real agents arrive
# with the Village roster (Phase 0.2); these stand in for them and are deliberately
# named so a snapshot diff shows who moved.
ROSTER = [
    ("11111111-1111-5111-8111-111111111111", "Ada Sourcing",
     "Research & Market Intelligence"),
    ("22222222-2222-5222-8222-222222222222", "Bram Records",
     "Research & Market Intelligence"),
    ("33333333-3333-5333-8333-333333333333", "Cleo Comps",
     "Research & Market Intelligence"),
    ("44444444-4444-5444-8444-444444444444", "Dorian Model",
     "Finance & Administration"),
    ("55555555-5555-5555-8555-555555555555", "Esme Ledger",
     "Finance & Administration"),
    ("66666666-6666-5666-8666-666666666666", "Faye Buyers",
     "Client Success & Operations"),
    ("77777777-7777-5777-8777-777777777777", "Gil Network",
     "Client Success & Operations"),
]

INSTRUCTION_CONTENT = {
    "what_it_does": "Documented.", "what_it_does_not_do": "Documented.",
    "inputs": {"a": "b"}, "correct_sequence": ["a", "b"],
    "failure_signatures": {"silent_partial": "short result"},
    "retry_vs_escalate": "Retry 5xx twice; escalate 4xx.",
    "never_do": ["Never re-submit after a 200"],
    "compliance_coupling": ["tsr_disclosure_required"],
}


def build_world(admin: psycopg.Connection) -> None:
    """A fully prepared world: Forges bridged, instructions authored, roster present.

    This is the state Gates 0 through 8 exist to produce. Building it here means the
    golden snapshots - and the provisioning runs - describe a venture that could
    actually provision.
    """
    teardown_world(admin)
    with admin.cursor() as cur:
        for forge_id, api, modules, flags in (
            (FORGE_ID, "1.4.0", CRE_MODULES, ["tsr_disclosure_required"]),
            ("simforge", "3.2.0", ("run_scenario_pack", "gate_result"), []),
            ("voiceforge", "2.0.0", VOICE_MODULES, ["recording_consent_required"]),
        ):
            cur.execute(
                """
                INSERT INTO forge_registry
                  (forge_id, display_name, base_url, api_version, auth_model,
                   credential_mode, health_status)
                VALUES (%s, %s, 'https://example.invalid', %s, 'bearer', 'brokered', 'GREEN')
                """,
                (forge_id, forge_id, api),
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
                      (forge_id, module_id, module_name, idempotency_support,
                       is_mutating, compliance_flags_implied)
                    VALUES (%s, %s, %s, %s, TRUE, %s)
                    """,
                    (forge_id, module_id, module_id.replace("_", " ").title(),
                     "at_most_once" if module_id == "generate_loi" else "key", flags),
                )
                cur.execute(
                    """
                    INSERT INTO forge_operating_instruction
                      (forge_id, module_id, instruction_version, forge_api_version,
                       content, content_hash, authored_by)
                    VALUES (%s, %s, '1.0.0', %s, %s, '', %s)
                    """,
                    (forge_id, module_id, api,
                     psycopg.types.json.Jsonb(INSTRUCTION_CONTENT),
                     "00000000-0000-5000-8000-00000000aaaa"),
                )

        for agent_id, name, dept in ROSTER:
            cur.execute(
                """
                INSERT INTO office_agent_identity
                  (office_agent_id, village_agent_ref, agent_name, department, status)
                VALUES (%s, %s, %s, %s, 'active')
                """,
                (agent_id, f"village::{name}", name, dept),
            )
    admin.commit()


def certify(conn: psycopg.Connection, agent_ids, modules, *, forge=FORGE_ID,
            tier="auto_execute", unit_b_departments=()):
    """Grant Unit A on the named modules and Unit B on the named departments."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT module_id, content_hash FROM forge_operating_instruction "
            "WHERE forge_id = %s AND superseded_at IS NULL", (forge,)
        )
        hashes = dict(cur.fetchall())
        cur.execute("SELECT api_version FROM forge_registry WHERE forge_id = %s", (forge,))
        api_row = cur.fetchone()
        assert api_row is not None
        api = api_row[0]

        for agent_id in agent_ids:
            for module_id in modules:
                cur.execute(
                    """
                    INSERT INTO certification
                      (cert_id, unit, office_agent_id, forge_id, module_id, state,
                       certified_tier, instruction_content_hash, forge_api_version,
                       rubric_kind, rubric_version, simforge_verdict)
                    VALUES (%s, 'A', %s, %s, %s, 'certified', %s, %s, %s,
                            'operation', '1.4.0', 'PASS')
                    ON CONFLICT (office_agent_id, forge_id, module_id)
                      WHERE unit = 'A' DO NOTHING
                    """,
                    (str(uuid.uuid4()), agent_id, forge, module_id, tier,
                     hashes[module_id], api),
                )
        for dept in unit_b_departments:
            cur.execute(
                """
                INSERT INTO certification
                  (cert_id, unit, department, forge_id, state, certified_tier,
                   instruction_content_hash, forge_api_version, rubric_kind,
                   rubric_version, simforge_verdict)
                VALUES (%s, 'B', %s, %s, 'certified', 'auto_execute', %s, %s,
                        'domain', '3.2.0', 'PASS')
                ON CONFLICT (department, forge_id) WHERE unit = 'B' DO NOTHING
                """,
                (str(uuid.uuid4()), dept, forge,
                 next(iter(hashes.values())), api),
            )
    conn.commit()


def teardown_world(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM venture_forge_manifest WHERE venture_id = 'greenstone'")
        cur.execute("DELETE FROM venture_budget WHERE venture_id = 'greenstone'")
        cur.execute("DELETE FROM agent_forge_grant WHERE venture_id = 'greenstone'")
        cur.execute("DELETE FROM certification")
        cur.execute("DELETE FROM forge_operating_instruction")
        for agent_id, _n, _d in ROSTER:
            cur.execute("DELETE FROM office_agent_identity WHERE office_agent_id = %s",
                        (agent_id,))
        for forge_id in (FORGE_ID, "simforge", "voiceforge"):
            cur.execute("DELETE FROM forge_tenant_credential WHERE forge_id = %s", (forge_id,))
            cur.execute("DELETE FROM forge_module_registry WHERE forge_id = %s", (forge_id,))
            cur.execute("DELETE FROM rate_limit_bucket WHERE bucket_key = %s",
                        (f"forge:{forge_id}",))
            cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    conn.commit()


def certify_for_positions(conn: psycopg.Connection) -> None:
    """The happy path: every agent certified for the position it will be appointed to.

    Positions span Forges, so certification must too - the Acquisition Analyst needs
    Unit A on CRE Forge *and* VoiceForge, plus Unit B on both. Getting this wrong is
    how the cross-Forge appointment bug hid: one Forge per position was assumed, and
    `place_call` was never certifiable.
    """
    research = [a for a, _n, d in ROSTER if d == "Research & Market Intelligence"]
    finance = [a for a, _n, d in ROSTER if d == "Finance & Administration"]
    success = [a for a, _n, d in ROSTER if d == "Client Success & Operations"]

    certify(conn, research, ["property_lookup", "comp_analysis"],
            unit_b_departments=["Research & Market Intelligence"])
    certify(conn, research, ["place_call"], forge="voiceforge",
            unit_b_departments=["Research & Market Intelligence"])
    certify(conn, finance, ["comp_analysis", "underwrite_deal"], tier="propose",
            unit_b_departments=["Finance & Administration"])
    certify(conn, success, ["buyer_match", "generate_loi"], tier="propose",
            unit_b_departments=["Client Success & Operations"])
    certify(conn, success, ["place_call", "transcribe_call"], forge="voiceforge",
            tier="propose", unit_b_departments=["Client Success & Operations"])
