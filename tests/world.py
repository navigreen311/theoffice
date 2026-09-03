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

import hashlib
import json
import uuid
from pathlib import Path

import psycopg
import psycopg.types.json
import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "packs" / "greenstone.yaml"

FORGE_ID = "cre-forge"
# `generate_loi` was removed 2026-09-02 along with the Pack declaration. CRE Forge
# has no letter-of-intent service, route or contract template, so a world that
# registered it was a world describing a module that does not exist - which is the
# state V32 exists to refuse, reproduced inside the fixture that tests V32.
CRE_MODULES = ("property_lookup", "comp_analysis", "underwrite_deal", "buyer_match")
VOICE_MODULES = ("place_call", "transcribe_call")

# Fixed agent ids so snapshots are stable across runs and machines. Real agents arrive
# with the Village roster (Phase 0.2); these stand in for them and are deliberately
# named so a snapshot diff shows who moved.
ROSTER = [
    ("11111111-1111-5111-8111-111111111111", "Ada Sourcing",
     "research"),
    ("22222222-2222-5222-8222-222222222222", "Bram Records",
     "research"),
    ("33333333-3333-5333-8333-333333333333", "Cleo Comps",
     "research"),
    ("44444444-4444-5444-8444-444444444444", "Dorian Model",
     "banking"),
    ("55555555-5555-5555-8555-555555555555", "Esme Ledger",
     "banking"),
    ("66666666-6666-5666-8666-666666666666", "Faye Buyers",
     "operations"),
    ("77777777-7777-5777-8777-777777777777", "Gil Network",
     "operations"),
]

# Part 6.3's six fields. The Greenstone Pack's `library_entry_ref` values resolve to
# these, and V28 fails if they do not exist.
COMPLIANCE_ENTRIES = [
    {
        "entry_ref": "compliance/nv-two-party-consent-v1",
        "framework": "TWO_PARTY_CONSENT_RECORDING",
        "jurisdiction": ["NV"],
        "applicability_rule": "Any recorded call with an owner or broker in Nevada.",
        "agent_behavior_implication": (
            "Obtain and record affirmative consent from every party before recording "
            "starts. Do not begin recording while waiting for an answer."
        ),
        "escalation_trigger": (
            "Any party declines, hesitates, or asks what the recording is for."
        ),
        "citation": "NRS 200.620",
        "runtime_flag": "recording_consent_required",
    },
    {
        "entry_ref": "compliance/ftc-tsr-v2",
        "framework": "FTC_TSR",
        "jurisdiction": ["FEDERAL"],
        "applicability_rule": "Outbound cold calls to property owners.",
        "agent_behavior_implication": (
            "State identity, the company, and the purpose of the call before anything "
            "else. Honour a do-not-call request on the call it is made."
        ),
        "escalation_trigger": "The called party asserts a do-not-call registration.",
        "citation": "16 CFR 310",
        "runtime_flag": "tsr_disclosure_required",
    },
]

# A curriculum that teaches the module, because a world where agents are certified
# against `"what_it_does": "Documented."` is not a prepared world - it is the bug.
#
# This constant used to be exactly that: eight sections present, none empty, `inputs`
# of `{"a": "b"}` and a `correct_sequence` of `["a", "b"]`. It satisfied V11, which
# checked only that a row existed, and every gate test downstream ran against agents
# certified to operate a module nobody had described. The tests passed and described
# nothing.
#
# V11 now assesses the content, so this had to become real. Deliberately generic - it is
# seeded for every module - but it is prose, and `broker.curriculum_quality` reads it as
# complete rather than as a placeholder.
INSTRUCTION_CONTENT = {
    "what_it_does": (
        "Performs one operation against the Forge and returns its result. The result "
        "is data for the agent to act on in a later step, never an action in itself."
    ),
    "what_it_does_not_do": (
        "Does not retry on the agent's behalf, does not write to any other system, and "
        "does not decide what happens next. Nothing here is a commitment to a third "
        "party."
    ),
    "inputs": {
        "venture_id": "Which venture this call belongs to. Scopes the grant and the "
                      "ledger entry.",
        "idempotency_key": "Stable across retries of the same task. A new key is a new "
                           "call, not a retry of the old one.",
    },
    "correct_sequence": [
        "Confirm the grant is assignable for this module before calling.",
        "Call the module once with a stable idempotency key.",
        "Read the result; escalate rather than repeating on a 4xx.",
    ],
    "failure_signatures": {
        "silent_partial": "A 200 with fewer results than requested. The upstream index "
                          "is stale; the call did not fail.",
        "rate_limited": "429 with Retry-After. Wait the stated interval; do not retry "
                        "immediately.",
        "timeout": "No response inside the deadline. The call may still have landed - "
                   "re-send only with the same idempotency key.",
    },
    "retry_vs_escalate": (
        "Retry a 5xx twice with backoff. Escalate any 4xx to a human: a 4xx means the "
        "request was wrong, and repeating it will not make it right."
    ),
    "never_do": [
        "Never re-submit after a 200.",
        "Never generate a new idempotency key to force a retry.",
    ],
    "compliance_coupling": ["tsr_disclosure_required"],
}


#: The Village's twelve, as of the rebuild. Seeded rather than fetched: a suite that
#: needs a second application running to validate a Pack fails for reasons unrelated to
#: the code under test. Seats are the live figures, so the headcount rule is exercised
#: against real numbers - research really does have 14.
#: The twelve, read from the file the smoke script's stub Village also serves.
#:
#: One copy. The Office carried its own tuple of department names once and nine of the
#: twelve were wrong, with nothing failing because nothing checked - and a second copy
#: here, kept in step with a stub by hand, is the same bet with a shorter fuse.
VILLAGE_DEPARTMENTS = tuple(
    (d["department"], d["label"], d["seats"])
    for d in json.loads(
        (ROOT / "scripts" / "fixtures" / "village-departments.json").read_text(
            encoding="utf-8"
        )
    )["departments"]
)



def instruction_for(module_id: str) -> dict:
    """`INSTRUCTION_CONTENT`, saying which module it is about.

    The shared constant is deliberately generic, and for a while every module got it
    verbatim with `content_hash` left as the empty string. That is the production
    defect reproduced in a fixture: all five live `cre-forge` instructions were
    byte-identical and carried one hash between them, so
    `certification.instruction_content_hash` could not say which module an agent had
    been certified on, and V33 exists to fail exactly that.

    A fixture that writes one hash for every module cannot exercise V33 and would fail
    it, so each instruction here names its own module. Still generic prose - `assess`
    should keep reading it as complete - but no longer one document wearing five names.
    """
    content = json.loads(json.dumps(INSTRUCTION_CONTENT))
    content["what_it_does"] = f"{module_id}: " + content["what_it_does"]
    return content


def instruction_hash(content: dict) -> str:
    """The hash a certification is bound to. Over canonical JSON, so it is stable."""
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def seed_departments() -> None:
    """Install the department list the rules validate against."""
    from broker import departments as depts

    depts.seed([
        depts.Department(department=name, label=label, seats=seats)
        for name, label, seats in VILLAGE_DEPARTMENTS
    ])


def dispatch_from_registry(
    admin: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of a prepared world: the adapters are up and dispatching.

    Every other part of this world is a database state, and V32 is deliberately not.
    It resolves a Pack against what a Forge's adapter actually dispatches, because
    `forge_module_registry` rows are rows a human wrote and comparing a Pack to them
    compares two claims. A world built only in the database therefore leaves V32
    NOT_RUN, which blocks Gate 2 - correctly, and not because anything is wrong with
    the venture under test.

    So this supplies the state rather than the mechanism: adapters that answer with
    exactly what the world registered. The mechanism - the manifest read, the probe,
    and the calibration failure that makes a probe refuse to answer - is driven for
    real over a mock transport in `tests/validator/test_module_conformance.py`, and
    a Forge that does *not* dispatch a declared module has its own test there and in
    `test_world_rules.py`. Standing up three HTTP servers to restate that here would
    add machinery, not coverage.
    """
    from datetime import UTC, datetime

    from broker import forge_modules

    with admin.cursor() as cur:
        cur.execute(
            """
            SELECT lower(r.forge_id) AS forge_id, r.api_version, m.module_id
            FROM forge_registry r
            LEFT JOIN forge_module_registry m ON m.forge_id = r.forge_id
            """
        )
        rows = cur.fetchall()

    dispatched: dict[str, set[str]] = {}
    versions: dict[str, str] = {}
    for forge_id, api_version, module_id in rows:
        versions[forge_id] = api_version
        bucket = dispatched.setdefault(forge_id, set())
        if module_id is not None:
            bucket.add(module_id)

    async def _answer(_conn, forge_id: str, **_kw):
        key = forge_id.lower()
        if key not in dispatched:
            return forge_modules.Unread(forge_id, "not in forge_registry")
        return forge_modules.ForgeModules(
            forge_id=forge_id,
            modules=frozenset(dispatched[key]),
            method="adapter_manifest",
            api_version=versions[key],
            observed_at=datetime.now(UTC),
        )

    monkeypatch.setattr(forge_modules, "read", _answer)
    forge_modules.forget()


def build_world(admin: psycopg.Connection) -> None:
    """A fully prepared world: Forges bridged, instructions authored, roster present.

    This is the state Gates 0 through 8 exist to produce. Building it here means the
    golden snapshots - and the provisioning runs - describe a venture that could
    actually provision.

    The adapters are a separate call - `dispatch_from_registry` - because they are the
    one part of the world that is not a row. A suite that runs Gate 2 needs both.
    """
    seed_departments()
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
                       is_mutating, compliance_flags_implied,
                       verified_at, verified_against, verification_method)
                    VALUES (%s, %s, %s, %s, TRUE, %s,
                            now(), 'test world', 'adapter_manifest')
                    """,
                    (forge_id, module_id, module_id.replace("_", " ").title(),
                     "key", flags),
                )
                content = instruction_for(module_id)
                cur.execute(
                    """
                    INSERT INTO forge_operating_instruction
                      (forge_id, module_id, instruction_version, forge_api_version,
                       content, content_hash, authored_by)
                    VALUES (%s, %s, '1.0.0', %s, %s, %s, %s)
                    """,
                    (forge_id, module_id, api,
                     psycopg.types.json.Jsonb(content), instruction_hash(content),
                     "00000000-0000-5000-8000-00000000aaaa"),
                )

        # Part 6.3. The Greenstone Pack names these two refs; without them V28 fails
        # and Gate 2 blocks - which is V28 working, and is why a prepared world has to
        # include the library rather than only the bridge.
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
                ON CONFLICT (entry_ref) DO NOTHING
                """,
                entry,
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
        for entry in COMPLIANCE_ENTRIES:
            cur.execute(
                "DELETE FROM compliance_library_entry WHERE entry_ref = %s",
                (entry["entry_ref"],),
            )
        cur.execute("DELETE FROM forge_operating_instruction")
        # Proposals reference the agents about to be removed. `wipe_venture` learned this
        # the hard way with provisioning_run; a teardown that names some dependents and
        # not others fails on whichever one the next feature adds.
        cur.execute(
            "DELETE FROM proposal WHERE office_agent_id IN "
            "(SELECT office_agent_id FROM office_agent_identity)"
        )
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
    research = [a for a, _n, d in ROSTER if d == "research"]
    finance = [a for a, _n, d in ROSTER if d == "banking"]
    success = [a for a, _n, d in ROSTER if d == "operations"]

    certify(conn, research, ["property_lookup", "comp_analysis"],
            unit_b_departments=["research"])
    certify(conn, research, ["place_call"], forge="voiceforge",
            unit_b_departments=["research"])
    certify(conn, finance, ["comp_analysis", "underwrite_deal"], tier="propose",
            unit_b_departments=["banking"])
    certify(conn, success, ["buyer_match"], tier="propose",
            unit_b_departments=["operations"])
    certify(conn, success, ["place_call", "transcribe_call"], forge="voiceforge",
            tier="propose", unit_b_departments=["operations"])
