"""Golden tests for the seven generators.

Blueprint §5 test strategy: "Generator regressions — fixed Packs, snapshot-asserted
outputs. Any diff fails CI and requires explicit approval."

Snapshots live in `tests/golden/snapshots/`. Regenerating them requires
`UPDATE_GOLDEN=1`, and the failure message says so — a snapshot that silently
re-records is a snapshot that never catches anything, and "just re-run with update"
becomes the reflex the moment it is convenient.

The reason this matters here specifically: a generator regression that silently alters
an appointment roster produces a *plausible-looking wrong answer*. Nothing crashes,
nothing logs, and the artifact reads fine. That is the defect class the blueprint
catalogues portfolio-wide, and a snapshot is the only cheap way to catch it.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import psycopg
import psycopg.types.json
import pytest

from broker.db import connection
from generators import pipeline
from generators.artifacts import Artifact
from generators.pack import load_pack
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / "packs" / "greenstone.yaml"
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"

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


@pytest.fixture
def greenstone_world(admin: psycopg.Connection):
    """A fully prepared world: Forges bridged, instructions authored, roster certified.

    This is the state Gate 0 through Gate 8 exist to produce. Building it here means
    the golden snapshots describe a venture that could actually provision.
    """
    _teardown(admin)
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
    yield admin
    _teardown(admin)


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


def _teardown(conn: psycopg.Connection) -> None:
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


def assert_golden(name: str, artifact: Artifact) -> None:
    """Compare against the recorded snapshot, or record it under UPDATE_GOLDEN=1."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.json"
    actual = artifact.to_json()

    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(actual, encoding="utf-8", newline="\n")
        return

    assert path.exists(), (
        f"no snapshot for {name}. Record it with UPDATE_GOLDEN=1 and review the "
        "result before committing - a snapshot recorded without being read is a "
        "test that asserts whatever the code happened to do."
    )
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, (
        f"{name} differs from its golden snapshot.\n"
        "A generator regression that silently alters an appointment roster produces a "
        "plausible-looking wrong answer - nothing crashes and the artifact reads fine. "
        "Read the diff. If the change is intended, re-record with UPDATE_GOLDEN=1."
    )


@pytest.fixture
async def artifacts(greenstone_world, admin):
    """The fully-certified happy path: every agent certified for its position."""
    research = [a for a, _n, d in ROSTER if d == "Research & Market Intelligence"]
    finance = [a for a, _n, d in ROSTER if d == "Finance & Administration"]
    success = [a for a, _n, d in ROSTER if d == "Client Success & Operations"]

    # Positions span Forges, so certification must too. The Acquisition Analyst needs
    # Unit A on CRE Forge AND VoiceForge, plus Unit B on both.
    certify(admin, research, ["property_lookup", "comp_analysis"],
            unit_b_departments=["Research & Market Intelligence"])
    certify(admin, research, ["place_call"], forge="voiceforge",
            unit_b_departments=["Research & Market Intelligence"])
    certify(admin, finance, ["comp_analysis", "underwrite_deal"], tier="propose",
            unit_b_departments=["Finance & Administration"])
    certify(admin, success, ["buyer_match", "generate_loi"], tier="propose",
            unit_b_departments=["Client Success & Operations"])
    certify(admin, success, ["place_call", "transcribe_call"], forge="voiceforge",
            tier="propose", unit_b_departments=["Client Success & Operations"])

    pack = load_pack(PACK_PATH)
    async with connection() as conn:
        return await pipeline.run_all(pack, conn)


# ------------------------------------------------------------------- determinism

async def test_every_generator_is_byte_identical_across_runs(greenstone_world, admin):
    """G1 — 'same Pack in, same artifacts out'.

    Without this the snapshots are theatre: a diff that only sometimes appears is a
    diff nobody investigates.
    """
    certify(admin, [a for a, _n, _d in ROSTER], list(CRE_MODULES),
            unit_b_departments=[d for _a, _n, d in ROSTER])
    certify(admin, [a for a, _n, _d in ROSTER], list(VOICE_MODULES), forge="voiceforge",
            unit_b_departments=[d for _a, _n, d in ROSTER])
    pack = load_pack(PACK_PATH)

    async with connection() as conn:
        first = await pipeline.run_all(pack, conn)
        second = await pipeline.run_all(pack, conn)

    assert first.to_json() == second.to_json()


async def test_no_uuid4_leaks_into_an_artifact(artifacts):
    """Ids must be derived, not random. A uuid4 anywhere makes every run differ."""
    text = artifacts.to_json()
    for grant in artifacts.runtime_config.grants:
        assert grant.grant_id in text
    # UUIDv4 sets the version nibble to 4; every derived id here is v5.
    import re

    v4 = re.findall(r'"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-', text)
    assert not v4, f"random uuid4 found in artifact: {v4[:3]}"


# --------------------------------------------------------------------- snapshots

@pytest.mark.parametrize(
    "name",
    ["roles", "appointment", "workflow", "task_ledger", "curriculum",
     "forge_manifest", "runtime_config"],
)
async def test_golden_snapshot(artifacts, name):
    """G2 — any diff fails CI and requires explicit approval."""
    assert_golden(f"greenstone_{name}", getattr(artifacts, name))


# --------------------------------------------------------------- generator rules

async def test_role_definition_derives_implied_compliance_flags(artifacts):
    """G3 — 5.1 does real work.

    The Pack author gave the Acquisition Analyst `tsr_disclosure_required`. It also
    operates `place_call`, whose module registration implies
    `recording_consent_required`. An author who omits a flag has not escaped it.
    """
    analyst = next(
        p for p in artifacts.roles.positions if p.position_title == "Acquisition Analyst"
    )
    assert "tsr_disclosure_required" in analyst.declared_compliance_flags
    assert "recording_consent_required" in analyst.implied_compliance_flags
    assert "recording_consent_required" not in analyst.declared_compliance_flags
    assert set(analyst.effective_compliance_flags) == {
        "tsr_disclosure_required", "recording_consent_required"
    }


async def test_appointment_never_fills_a_position_with_an_uncertified_agent(
    greenstone_world, admin
):
    """G4 — 5.2, absolute. Uncertified candidates appear as requires_certification,
    never as filled."""
    # Unit B only: department certification is necessary, never sufficient.
    certify(admin, [], [], unit_b_departments=[d for _a, _n, d in ROSTER])
    pack = load_pack(PACK_PATH)

    async with connection() as conn:
        result = await pipeline.run_all(pack, conn)

    for position in result.appointment.appointments:
        assert position.appointed == [], f"{position.position_title} was filled uncertified"
        assert position.unfilled == position.headcount_required
        assert position.requires_certification, "candidates must be reported, not hidden"
        assert all(
            c.reason in ("never_certified", "in_training", "missing_unit_b")
            for c in position.requires_certification
        )


async def test_shortfall_reports_all_three_capacity_numbers(greenstone_world, admin):
    """G5 + G6 — §7.2 and §7.3.

    One number hides the state. And the response to a shortfall is to flag it, never
    to auto-reject the Pack, auto-appoint an uncertified agent, or reduce scope.
    """
    certify(admin, [ROSTER[0][0]], ["property_lookup", "comp_analysis"],
            unit_b_departments=["Research & Market Intelligence"])
    certify(admin, [ROSTER[0][0]], ["place_call"], forge="voiceforge",
            unit_b_departments=["Research & Market Intelligence"])
    pack = load_pack(PACK_PATH)

    async with connection() as conn:
        result = await pipeline.run_all(pack, conn)

    cap = result.appointment.capacity
    assert result.appointment.shortfall is True
    assert cap.certified_and_free == 1
    assert cap.produced_not_yet_certified > 0
    assert cap.total_considered > 0

    escalation = result.appointment.escalation
    assert "flag to Ivan" in escalation
    for number in ("Certified and free", "certified but allocated", "not yet certified"):
        assert number in escalation
    assert "NOT auto-rejected" in escalation


async def test_every_workflow_step_names_a_module_a_flag_and_an_escalation(artifacts):
    """G7 — 5.3. A blank compliance flag is ambiguous between 'none applies' and
    'nobody checked', so NONE is spelled out."""
    assert artifacts.workflow.steps
    for step in artifacts.workflow.steps:
        assert step.forge_modules, f"step {step.number} names no module"
        assert step.compliance_flag.strip(), f"step {step.number} has a blank flag"
        assert step.failure_and_escalation.strip(), f"step {step.number} has no escalation"
        assert step.position and step.stage


async def test_workflow_steps_follow_the_declared_stage_order(artifacts):
    """Close must not precede Source. Stage order is the author's, not sorted."""
    stages = [s.stage for s in artifacts.workflow.steps]
    declared = ["Source", "Qualify", "Underwrite", "Contract", "Assign", "Close"]
    first_seen = {stage: stages.index(stage) for stage in set(stages)}
    ordered = [s for s in declared if s in first_seen]
    assert ordered == sorted(ordered, key=lambda s: first_seen[s])


async def test_task_ledger_projects_daily_approvals_per_human_role(artifacts):
    """G8 — 5.4 names this a required output; it is V13's input."""
    approvals = artifacts.task_ledger.projected_daily_approvals
    assert approvals, "no approval projection - V13 has nothing to check"
    assert all(isinstance(v, int) and v > 0 for v in approvals.values())
    # Only sub-auto_execute tasks generate approvals.
    assert any(t.trust_tier != "auto_execute" for t in artifacts.task_ledger.tasks)


async def test_at_most_once_module_carries_its_idempotency_class(artifacts):
    """generate_loi is registered at_most_once. The ledger must say so, because the
    call path refuses to auto-retry it."""
    loi = [t for t in artifacts.task_ledger.tasks if t.module_id == "generate_loi"]
    assert loi
    assert all(t.idempotency_class == "at_most_once" for t in loi)


async def test_curriculum_states_a_denominator_for_every_dimension(artifacts):
    """G9 — 'report the denominator; no green check without a coverage count'."""
    assert artifacts.curriculum.coverage
    for coverage in artifacts.curriculum.coverage:
        assert coverage.denominator > 0, f"{coverage.dimension} has no denominator"
        assert coverage.covered <= coverage.denominator
        if not coverage.complete:
            assert coverage.uncovered, "an incomplete dimension must name what it missed"


async def test_operation_scenarios_bind_to_the_instruction_hash(artifacts):
    """This is what makes certification staleness computable."""
    ops = artifacts.curriculum.operation_scenarios
    assert ops
    for scenario in ops:
        if scenario.module_id in CRE_MODULES:
            assert scenario.instruction_content_hash, scenario.scenario_id
            assert len(scenario.instruction_content_hash) == 64


async def test_domain_and_operation_scenarios_are_never_merged(artifacts):
    """Part 10.1: two rubrics, never merged - so two scenario sets, never merged."""
    assert all(s.kind == "domain" for s in artifacts.curriculum.domain_scenarios)
    assert all(s.kind == "operation" for s in artifacts.curriculum.operation_scenarios)
    domain_ids = {s.scenario_id for s in artifacts.curriculum.domain_scenarios}
    op_ids = {s.scenario_id for s in artifacts.curriculum.operation_scenarios}
    assert not (domain_ids & op_ids)


# ------------------------------------------------------------------ Gate 4.5

async def test_gate_4_5_catches_what_gate_2_could_not(artifacts, greenstone_world):
    """The Gate 2 estimate is the optimistic one, and Gate 4.5 is where that shows.

    V13 at Gate 2 estimates approvals from Pack headcount. The Task Ledger computes
    them from the real workflow, and for Greenstone as authored the two disagree by
    an order of magnitude. Neither is buggy: Gate 2 cannot see a workflow that does
    not exist yet, which is exactly why the blueprint puts a second capacity check
    after the generators run.
    """
    from generators.validator import validate, validate_gate_4_5

    pack = load_pack(PACK_PATH)
    gate_2 = await validate(pack)
    assert gate_2.get("V13").verdict.value == "PASS", "Gate 2 estimate is optimistic"

    gate_45 = await validate_gate_4_5(pack, artifacts.task_ledger, artifacts.appointment)
    v13 = gate_45.get("V13")
    assert v13.verdict.value == "FAIL", (
        "Greenstone as authored routes more approvals to its compliance officer than "
        "the coverage hours can absorb; Gate 4.5 must catch it"
    )
    assert "compliance_officer" in v13.message
    assert "decorative" in v13.message


async def test_gate_4_5_resolves_v24(artifacts, greenstone_world):
    """V24 is appointment output, so Gate 2 reported it NOT_RUN. Here it resolves."""
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    gate_45 = await validate_gate_4_5(pack, artifacts.task_ledger, artifacts.appointment)
    assert gate_45.get("V24").verdict.value == "PASS", "all positions were filled"


async def test_gate_4_5_failure_surfaces_in_the_pipeline_warnings(artifacts):
    """Gate 4 is a human reading artifacts. A finding that only exists in a log line
    is a finding that review will miss."""
    assert any("GATE 4.5" in w and "V13" in w for w in artifacts.warnings), (
        f"capacity failure not surfaced for human review: {artifacts.warnings}"
    )


# ---------------------------------------------------------- 5.7 idempotency

async def _state_snapshot(conn) -> dict:
    """Everything 5.7 writes, in a comparable shape."""
    out: dict = {}
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT grant_id, office_agent_id, forge_id, module_id, trust_tier, "
            "       operation_cert_ref IS NOT NULL, dept_context_cert_ref IS NOT NULL "
            "FROM agent_forge_grant WHERE venture_id = 'greenstone' ORDER BY grant_id"
        )
        out["grants"] = [tuple(str(v) for v in r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT forge_id, module_id, is_required, criticality FROM "
            "venture_forge_manifest WHERE venture_id = 'greenstone' "
            "ORDER BY forge_id, module_id"
        )
        out["manifest"] = [tuple(str(v) for v in r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT monthly_usd_cap, per_task_usd_ceiling FROM venture_budget "
            "WHERE venture_id = 'greenstone'"
        )
        out["budget"] = [tuple(str(v) for v in r) for r in await cur.fetchall()]
        await cur.execute(
            "SELECT bucket_key, max_tokens, refill_per_second FROM rate_limit_bucket "
            "WHERE bucket_key LIKE 'forge:%' ORDER BY bucket_key"
        )
        out["buckets"] = [tuple(str(v) for v in r) for r in await cur.fetchall()]
    return out


async def test_runtime_config_apply_is_idempotent(artifacts):
    """G12 — 5.7: "Re-running produces identical state with zero duplicate side-effects."

    Idempotency here is structural, not defensive: `grant_id` is UUIDv5 over
    (venture, agent, forge, module), so the second run computes the same primary keys
    and collides with its own prior rows.
    """
    from generators import runtime_config as runtime_gen

    async with connection() as conn:
        first = await runtime_gen.apply(
            artifacts.runtime_config, conn,
            granted_by="00000000-0000-5000-8000-00000000bbbb",
        )
        after_first = await _state_snapshot(conn)

        second = await runtime_gen.apply(
            artifacts.runtime_config, conn,
            granted_by="00000000-0000-5000-8000-00000000bbbb",
        )
        after_second = await _state_snapshot(conn)

    assert first == second, "the same config must plan the same writes both times"
    assert after_first == after_second, "re-applying changed state"
    assert len(after_first["grants"]) == len(artifacts.runtime_config.grants)
    assert len(after_first["budget"]) == 1, "budget must not duplicate"


async def test_apply_wires_both_certification_refs_onto_each_grant(artifacts):
    """A grant with a NULL cert ref is not assignable, so 5.7 must resolve both."""
    from generators import runtime_config as runtime_gen

    async with connection() as conn:
        await runtime_gen.apply(
            artifacts.runtime_config, conn,
            granted_by="00000000-0000-5000-8000-00000000bbbb",
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM agent_forge_grant "
                "WHERE venture_id = 'greenstone' AND is_assignable"
            )
            row = await cur.fetchone()
    assert row is not None
    assert row[0] == len(artifacts.runtime_config.grants), (
        "every provisioned grant must be assignable; a NULL cert ref means it is not"
    )


async def test_apply_refuses_a_blocked_config(artifacts):
    """5.7 consumes the Manifest, not the Pack — so a blocked reconciliation stops
    provisioning here rather than being caught by a later gate."""
    import dataclasses

    from generators import runtime_config as runtime_gen

    blocked = dataclasses.replace(
        artifacts.runtime_config, blocked_reason="REQUIRED_NOT_DECLARED: made_up_module"
    )
    async with connection() as conn:
        with pytest.raises(ValueError, match="blocked runtime config"):
            await runtime_gen.apply(blocked, conn, granted_by="x")


async def test_required_not_declared_blocks_provisioning(artifacts):
    """G10 — a workflow step requiring an undeclared module blocks, and the config
    carries zero grants rather than grants plus a warning."""
    import dataclasses

    from generators import forge_manifest as manifest_gen
    from generators import runtime_config as runtime_gen

    pack = load_pack(PACK_PATH)
    # Strip a module from every binding while the workflow still requires it.
    stripped = dataclasses.replace(artifacts.forge_manifest)
    recon = dataclasses.replace(
        stripped.reconciliation, required_not_declared=["underwrite_deal"]
    )
    stripped = dataclasses.replace(stripped, reconciliation=recon)

    config = runtime_gen.generate(
        pack, artifacts.roles, artifacts.appointment, stripped,
        module_forge={"underwrite_deal": "cre-forge"},
    )
    assert config.blocked_reason is not None
    assert "REQUIRED_NOT_DECLARED" in config.blocked_reason
    assert config.grants == [], "a blocked config must carry no grants at all"
    assert manifest_gen is not None


async def test_hard_dependency_on_a_module_gap_cannot_provision(artifacts):
    """G11 — 5.6 / V8."""
    import dataclasses

    from generators import runtime_config as runtime_gen

    pack = load_pack(PACK_PATH)
    recon = dataclasses.replace(
        artifacts.forge_manifest.reconciliation, hard_dependency_on_gap=["comp_analysis"]
    )
    manifest = dataclasses.replace(artifacts.forge_manifest, reconciliation=recon)

    config = runtime_gen.generate(
        pack, artifacts.roles, artifacts.appointment, manifest,
        module_forge={"comp_analysis": "cre-forge"},
    )
    assert config.blocked_reason is not None
    assert "MODULE GAP" in config.blocked_reason
    assert config.grants == []
