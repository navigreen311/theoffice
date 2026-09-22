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
import time
import uuid
from pathlib import Path

import psycopg
import psycopg.types.json
import pytest

#: WHAT A FIXTURE CERTIFICATION SAYS IT WAS EARNED ON.
#:
#: Since 0044 a row carrying an answered SimForge verdict must name the model, not only
#: its label - `certification_names_its_model`. Every fixture below writes
#: `simforge_verdict = 'PASS'`, so every one of them needs these three, and a fixture
#: that omitted them would fail at the INSERT rather than in the test that reads it.
#:
#: The values are SimForge's exam constants (`EXAM_TEMPERATURE`, `EXAM_MAX_TOKENS`) and
#: a digest that is visibly fake. A plausible-looking sha256 here would be a fixture
#: pretending to be evidence.
FIXTURE_MODEL_DIGEST = "sha256:" + "f1" * 32
FIXTURE_MODEL_TEMPERATURE = 0.0
FIXTURE_MODEL_MAX_TOKENS = 2048

#: The same three in the shape SimForge sends them, for a test that goes through
#: `record_result` rather than writing the row itself. One spelling, so a change to
#: what the record must contain is made here and not in nine call sites.
FIXTURE_MODEL_IDENTITY = {
    "provider": "ollama",
    "model": "llama3.1:8b",
    "file_digest": FIXTURE_MODEL_DIGEST,
    "settings": {
        "temperature": FIXTURE_MODEL_TEMPERATURE,
        "max_tokens": FIXTURE_MODEL_MAX_TOKENS,
    },
    "fingerprint": "sha256:" + "ab" * 32,
}


ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / "packs" / "greenstone.yaml"

#: RFC 6238 Appendix B's published seed, base32. Used for every enrolled test account so
#: the expected code at any instant is something a reader can look up rather than derive.
RFC_TEST_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

#: Who the fixture NV discharge is attributed to. A real uuid rather than a generated one,
#: so the row is identifiable and `teardown_world` can be checked to have removed it.
DISCHARGE_HUMAN_ID = uuid.UUID("00000000-0000-5000-8000-00000000d15c")

FORGE_ID = "cre-forge"
# `generate_loi` was removed 2026-09-02 along with the Pack declaration. CRE Forge
# has no letter-of-intent service, route or contract template, so a world that
# registered it was a world describing a module that does not exist - which is the
# state V32 exists to refuse, reproduced inside the fixture that tests V32.
CRE_MODULES = (
    "property_lookup", "comp_analysis", "underwrite_deal", "buyer_match",
    # Bound 2026-09-06. is_mutating with at_most_once idempotency, matching what
    # the adapter declares at its binding site - the registry copy is the one
    # V31 reads, so a fixture that disagreed with the adapter would be testing a
    # world the Forge does not serve.
    "assign_contract",
)
VOICE_MODULES = ("place_call", "transcribe_call")

#: SimForge's agent-facing modules. **`run_scenario_pack` is not one, and the fixture used
#: to say it was.**
#:
#: SimForge does not dispatch it and says why in its own adapter: nothing iterates a
#: Pack's scenarios into runs, so the only handler writable today would run one scenario
#: and report having run a pack. Both live Packs dropped it on 8 September (ruling Q-1),
#: `verify_forge_modules.py` has reported it as DRIFT since, and the development row was
#: deleted on 15 September with nothing referencing it.
#:
#: A fixture is a world a test believes. Keeping a module here that no Forge serves means
#: every suite reasons about a capability that does not exist - and it was the last place
#: in the system where that module still existed.
#:
#: `run_start` and `submit_curriculum` ARE dispatched and are deliberately absent too:
#: `broker/forge_modules.NOT_AGENT_FACING` records that a registry row exists so a grant
#: can be issued, and a module no agent calls has nothing to gain from one.
SIM_MODULES = ("gate_result",)

#: `compliance_flags_implied`, PER MODULE - entry 105.
#:
#: **This was one list per FORGE, looped over every module**, and that is how five CRE
#: Forge modules came to carry `tsr_disclosure_required`: a telemarketing-disclosure flag
#: on a property search, a comps pull, an underwriting calculation, a buyer ranking and a
#: contract draft. **Nobody read five modules and got five wrong answers - nobody read a
#: module.** The same shape put Greenstone's flag on two SimForge modules, which
#: `broker/compliance_couplings.py` records as its third error class: a flag that is true
#: somewhere and asserted here.
#:
#: A flag belongs on a module when the module's own behaviour implies the framework. None
#: of CRE Forge's five contacts a person, places a call or records one - `property_lookup`
#: and `comp_analysis` read, `underwrite_deal` computes, `buyer_match` ranks without
#: saving, and `assign_contract` creates a DRAFT and returns `sent: False`. The five live
#: operating instructions say so themselves: `compliance_coupling: ["no_framework_applies"]`.
#:
#: VoiceForge keeps `recording_consent_required` on both modules, and that one is earned:
#: `place_call` dials and `transcribe_call` processes a recording.
#:
#: `test_fixture_flags_match_the_instructions` fails if this map and an instruction's
#: `compliance_coupling` disagree.
MODULE_FLAGS: dict[tuple[str, str], list[str]] = {
    **{(FORGE_ID, module): [] for module in CRE_MODULES},
    **{("simforge", module): [] for module in SIM_MODULES},
    **{("voiceforge", module): ["recording_consent_required"] for module in VOICE_MODULES},
}

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
    # The coupling follows the module's flags rather than the shared constant's, which
    # named `tsr_disclosure_required` for everything. An instruction is what an agent is
    # examined on, so a fixture teaching a telemarketing duty for a comps pull is a
    # fixture certifying against the wrong text. `no_framework_applies` is the phrase the
    # real CRE Forge manuals use for a module no framework reaches.
    flags = sorted({f for (_forge, module), fs in MODULE_FLAGS.items()
                    if module == module_id for f in fs})
    content["compliance_coupling"] = flags or ["no_framework_applies"]
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


#: The database-level setting a disposable database carries, and the only thing that
#: makes `build_world` and `teardown_world` willing to run.
DISPOSABLE_MARKER = "office.disposable_world"


class NotADisposableDatabaseError(RuntimeError):
    """The database is not marked disposable, so nothing was read or written."""


def assert_disposable(conn: psycopg.Connection) -> str:
    """Refuse any database that has not been marked disposable. Returns its name.

    **WHAT IS REFUSED, AND WHY.** `teardown_world` runs first inside `build_world`, and it
    is not scoped to a venture or to this fixture's own rows: it deletes EVERY row of
    `certification` and EVERY row of `forge_operating_instruction`, every proposal
    belonging to any agent identity, and the registry, credential and module rows of three
    Forges. Against the development database on 15 September 2026 that would have removed
    18 bootstrap-attested certifications, 16 authored instructions - including the five CRE
    Forge manuals written that morning - and both Greenstone grants, then re-registered two
    Forges at `https://example.invalid` and rewritten every module row to
    `is_mutating = TRUE`, which is the exact defect `verify_forge_modules.py` exists to
    catch (decisions entry 95). Nothing checked. The seed's only guards were its callers':
    `dev-up.sh` seeds when `forge_registry` is empty and `console-smoke.sh` when
    `/api/forges` returns `[]` - both of which say what the database contains, never which
    database it is.

    **THE MARKER IS IN THE DATABASE, NOT IN THE ENVIRONMENT.** A name rule (`*_test`) was
    the obvious check and would be wrong twice: CI runs this suite against a database
    called `theoffice`, and a rule about spelling is passed by anything spelled that way.
    An environment variable is worse - the caller sets it, and the caller is what is
    already wrong when this fires. So the database itself carries the permission:

        ALTER DATABASE theoffice_test SET office.disposable_world = 'theoffice_test';

    The value must equal the database's own name, so a marked database restored under
    another name is not marked, and a marker copied between environments names the wrong
    database and refuses. Setting it takes database-owner rights and a deliberate statement
    that names the database twice; no test run, no script and no export can produce it by
    accident.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT current_database(), current_setting(%s, true)", (DISPOSABLE_MARKER,)
        )
        database, marker = cur.fetchone()

    if marker == database:
        return str(database)

    raise NotADisposableDatabaseError(
        f"{database!r} is not marked disposable, so nothing was written. This wipes every "
        f"certification and every operating instruction in the database it runs against, "
        f"not just its own rows. If {database!r} really is a throwaway test database, mark "
        f"it once:\n\n"
        f"    ALTER DATABASE \"{database}\" SET {DISPOSABLE_MARKER} = '{database}';\n\n"
        f"then reconnect - the setting is applied at connection time. If it is the "
        f"development database, point OFFICE_TEST_ADMIN_DSN at a test database instead "
        f"(./scripts/bootstrap.sh creates and marks one)."
        + (f" It currently carries the marker {marker!r}, which is not its own name."
           if marker else "")
    )


def build_world(admin: psycopg.Connection) -> None:
    """A fully prepared world: Forges bridged, instructions authored, roster present.

    This is the state Gates 0 through 8 exist to produce. Building it here means the
    golden snapshots - and the provisioning runs - describe a venture that could
    actually provision.

    The adapters are a separate call - `dispatch_from_registry` - because they are the
    one part of the world that is not a row. A suite that runs Gate 2 needs both.

    Refuses any database not marked disposable - see `assert_disposable`.
    """
    assert_disposable(admin)
    seed_departments()
    teardown_world(admin)
    with admin.cursor() as cur:
        for forge_id, api, modules in (
            (FORGE_ID, "1.4.0", CRE_MODULES),
            ("simforge", "3.2.0", SIM_MODULES),
            ("voiceforge", "2.0.0", VOICE_MODULES),
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
                     "key", MODULE_FLAGS[(forge_id, module_id)]),
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
                  (venture_id, entry_ref, framework, jurisdiction, applicability_rule,
                   agent_behavior_implication, escalation_trigger, citation,
                   runtime_flag, authored_by)
                VALUES ('greenstone', %(entry_ref)s, %(framework)s, %(jurisdiction)s,
                        %(applicability_rule)s, %(agent_behavior_implication)s,
                        %(escalation_trigger)s, %(citation)s, %(runtime_flag)s,
                        '00000000-0000-5000-8000-00000000aaaa')
                ON CONFLICT (venture_id, entry_ref) DO NOTHING
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


def clear_nv_discharge(admin: psycopg.Connection) -> None:
    """Remove what `seed_nv_discharge` wrote, including the human it is attributed to.

    **A seeder without this leaks into the next suite and into the next RUN.** The row
    references an `office_human`, twenty-four contract suites delete every human wholesale,
    and a leftover discharge turns that into a foreign-key error in a suite that never
    touched either table. Measured at 98 errors across four files, none of them about
    compliance.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM obligation_discharge WHERE venture_id = 'greenstone'")
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (DISCHARGE_HUMAN_ID,))
    admin.commit()


def seed_nv_discharge(admin: psycopg.Connection) -> None:
    """The NV discharge a prepared world has, and the real venture does not.

    **Called explicitly, not from `build_world`, for the reason `certify_for_positions` is
    not in it either.** `build_world` builds the Forge world - registry rows, adapters,
    instructions, roster. A discharge is a Pack-compliance precondition, and only the suites
    that drive a run past Gate 2 need one.

    It also could not live there in practice: the row references an `office_human`, and
    twenty-four contract suites delete every human wholesale between tests. Seeding it for
    all of them puts a foreign key under suites that never asked for one - measured, at 414
    errors on the first full run.


    Item F declared `recording_consent_required` human-held, which is correct - no
    agent of this venture can place or record a call. V34 then asks the question the
    declaration invites: has a named human actually verified the obligation? For the
    real venture the answer is no, and **V34 is a FAIL that blocks Gate 2 until
    counsel reviews Nevada**. That is the true state and it is recorded as such.

    This row says "assume the founders have filed one" for a disposable world, so the
    twenty or so suites that drive a run past Gate 2 can keep exercising gates 3 to 12. It
    is the same class of fixture as `certify_for_positions`: a precondition supplied, not a
    rule relaxed.

    **`founder_policy`, not `counsel_reviewed`, and that is the point of the choice.** It
    is what the real venture will carry: a founder decided, no lawyer has read it. V34
    passes on it and V41 warns at Gate 2 for as long as it stands - so the seeded world
    shows the ladder a reader would actually see, warning and all, rather than a cleaner
    one this fixture invented.

    **V34 is not weakened and this fixture does not hide it.**
    `test_v34_fails_for_greenstone_without_a_discharge` deletes this row and asserts the
    FAIL, so the real-world answer is exercised by name rather than left to be inferred
    from the absence of a test.
    """
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO office_human
              (human_id, display_name, email, auth_method, status, created_at, origin)
            VALUES (%s, 'World Fixture Operator', 'world-fixture@example.invalid',
                    'bearer_token', 'active', now(), 'test_fixture')
            ON CONFLICT (human_id) DO NOTHING
            """,
            (DISCHARGE_HUMAN_ID,),
        )
        cur.execute(
            """
            INSERT INTO obligation_discharge
              (discharge_id, venture_id, runtime_flag, jurisdiction_scope,
               library_entry_ref, citation, discharged_by, role_discharged_as,
               artifact_kind, artifact_hash, basis, verified_at, expires_at, status)
            VALUES (%s, 'greenstone', 'recording_consent_required', %s,
                    'compliance/nv-two-party-consent-v1', 'NRS 200.620', %s,
                    'venture operator', 'counsel_memo', 'sha256:0000',
                    'FIXTURE. A disposable world assuming counsel has reviewed NV '
                    'two-party consent. The real venture has no such review.',
                    now() - interval '1 day', now() + interval '365 days',
                    'founder_policy')
            """,
            (uuid.uuid4(), ["NV"], DISCHARGE_HUMAN_ID),
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
                       rubric_kind, rubric_version, simforge_verdict, basis, agent_model,
                       model_digest, model_temperature, model_max_tokens)
                    VALUES (%s, 'A', %s, %s, %s, 'certified', %s, %s, %s,
                            'operation', '1.4.0', 'PASS', 'tested',
                            'ollama/llama3.1:8b',
                            %s, %s, %s)
                    ON CONFLICT (office_agent_id, forge_id, module_id)
                      WHERE unit = 'A' DO NOTHING
                    """,
                    (str(uuid.uuid4()), agent_id, forge, module_id, tier,
                     hashes[module_id], api, FIXTURE_MODEL_DIGEST,
                     FIXTURE_MODEL_TEMPERATURE, FIXTURE_MODEL_MAX_TOKENS),
                )
        for dept in unit_b_departments:
            cur.execute(
                """
                INSERT INTO certification
                  (cert_id, unit, department, forge_id, state, certified_tier,
                   instruction_content_hash, forge_api_version, rubric_kind,
                   rubric_version, simforge_verdict, basis, agent_model,
                   model_digest, model_temperature, model_max_tokens)
                VALUES (%s, 'B', %s, %s, 'certified', 'auto_execute', %s, %s,
                        'domain', '3.2.0', 'PASS', 'tested', 'ollama/llama3.1:8b',
                        %s, %s, %s)
                ON CONFLICT (department, forge_id) WHERE unit = 'B' DO NOTHING
                """,
                (str(uuid.uuid4()), dept, forge,
                 next(iter(hashes.values())), api, FIXTURE_MODEL_DIGEST,
                 FIXTURE_MODEL_TEMPERATURE, FIXTURE_MODEL_MAX_TOKENS),
            )
    conn.commit()


def teardown_world(conn: psycopg.Connection) -> None:
    """Delete the world. Refuses any database not marked disposable.

    Guarded in its own right rather than only through `build_world`: the deletes are
    here, fixtures call it directly to clean up, and a guard that only covers the
    caller that happens to be destructive today is a guard that goes stale.
    """
    assert_disposable(conn)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM obligation_discharge")
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (DISCHARGE_HUMAN_ID,))
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
    # assign_contract joins buyer_match on 2026-09-06: Buyer Network Manager operates
    # both, and an agent certified for only half its position's modules leaves the
    # position unfillable - which shows up at Gate 4.5 as a capacity shortfall rather
    # than as a missing certification.
    #
    # SPLIT 2026-09-16: the two are certified at different tiers, because the Pack now
    # declares them at different tiers. `buyer_match` is auto_execute per Ivan's ruling -
    # non-mutating, and the spec requires no human on it.
    #
    # **Certifying both at `propose` would have made that declaration inert, silently.**
    # `_effective_tier` takes the LOWER of declared and certified, so a module declared
    # auto_execute and certified propose runs at propose - entry 52's finding, and the
    # reason a per-module tier needs a per-module certification behind it. The fixture
    # would have reported buyer_match as reviewed work and V13 would have demanded a
    # volume for it, on the strength of a test fixture disagreeing with the Pack.
    certify(conn, success, ["buyer_match"], unit_b_departments=["operations"])
    certify(conn, success, ["assign_contract"], tier="propose",
            unit_b_departments=["operations"])
    certify(conn, success, ["place_call", "transcribe_call"], forge="voiceforge",
            tier="propose", unit_b_departments=["operations"])


# ---------------------------------------------------------------- the second factor

def enrol_second_factor(admin: psycopg.Connection, human_id: uuid.UUID) -> str:
    """Give this account a known TOTP secret and mark it enrolled. Returns the secret.

    RULED 21 SEPTEMBER 2026 (entry 155): `attest`, `sign_off` and `revoke` refuse
    without a verified code, so a test that performs any of those needs an account that
    can produce one.

    **Written directly rather than through `mfa.begin_enrolment` and
    `mfa.confirm_enrolment`.** Those two are the thing under test in
    `tests/contract/test_a_second_factor.py`; using them to set up every OTHER test
    would make a suite-wide red the symptom of one bug in them, and would hide a
    regression in enrolment behind the fifty tests that merely need a code.

    The secret is RFC 6238's published one, so a reader who wants to know what code is
    expected at a given second can look it up rather than run anything.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human "
            "   SET mfa_secret = %s, mfa_enrolled_at = now(), auth_method = 'mfa_only' "
            " WHERE human_id = %s",
            (RFC_TEST_SECRET, human_id),
        )
    admin.commit()
    return RFC_TEST_SECRET


def code_for(human_id: uuid.UUID, *, step_offset: int = 0) -> str:
    """A code this account can use right now, enrolling it first if it has not been.

    **Opens its own connection rather than taking one.** The call sites are inside async
    helpers that hold an `AsyncConnection` and often have no `admin` fixture in scope,
    and threading one through every signing helper would put a test-harness argument
    into the signature of everything that signs. It commits immediately and closes.

    One code authorises one act - entry 155 records the step it spent - so this is called
    per act rather than once per test. A variable holding "the code" is a test that
    passes twice and fails the third time for a reason nobody will enjoy finding.

    `step_offset` is for the handful of tests that legitimately perform TWO of these acts
    seconds apart, where a person would have taken minutes: re-signing Gate 10 over
    regenerated artifacts, for instance. It asks for the NEXT step's code, which
    `verify` accepts inside its one-step skew - a different code for a different act,
    rather than a weakened rule.
    """
    import os

    from broker import mfa

    dsn = os.environ.get("OFFICE_ADMIN_DSN")
    assert dsn, "OFFICE_ADMIN_DSN not set; code_for needs it to enrol a test account"
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE office_human "
                "   SET mfa_secret = %s, mfa_enrolled_at = coalesce(mfa_enrolled_at, now()), "
                "       auth_method = 'mfa_only' "
                " WHERE human_id = %s",
                (RFC_TEST_SECRET, human_id),
            )
        conn.commit()
    return mfa.code_at(
        RFC_TEST_SECRET, time.time() + step_offset * mfa.STEP_SECONDS
    )


def code_for_token(token: str) -> str:
    """A code for whoever holds this bearer token.

    The API-level suites authenticate with a token and mostly discard the human id, so
    keying on the token avoids threading an id through a dozen call sites to reach the
    same account. It resolves the same way `humans.authenticate` does - by hash, never
    by storing the token.
    """
    import os

    from broker import humans

    dsn = os.environ.get("OFFICE_ADMIN_DSN")
    assert dsn, "OFFICE_ADMIN_DSN not set"
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT human_id FROM office_human WHERE token_hash = %s",
            (humans.hash_token(token),),
        )
        row = cur.fetchone()
    assert row, "no account holds that token"
    return code_for(row[0])
