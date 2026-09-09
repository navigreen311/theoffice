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
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

from broker.db import connection
from generators import appointment as appointment_gen
from generators import pipeline
from generators import roles as roles_gen
from generators import workflow as workflow_gen
from generators.artifacts import Artifact
from generators.pack import load_pack
from tests.conftest import requires_db
from tests.world import (
    CRE_MODULES,
    PACK_PATH,
    ROSTER,
    VOICE_MODULES,
    build_world,
    certify,
    certify_for_positions,
    teardown_world,
)

pytestmark = [requires_db, pytest.mark.db]

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture
def greenstone_world(admin: psycopg.Connection):
    """Bridged Forges, authored instructions, roster present, nobody certified yet."""
    build_world(admin)
    yield admin
    teardown_world(admin)


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
    certify_for_positions(admin)
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
    ["roles", "appointment", "workflow", "approval_projection", "curriculum",
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
            unit_b_departments=["research"])
    certify(admin, [ROSTER[0][0]], ["place_call"], forge="voiceforge",
            unit_b_departments=["research"])
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


async def test_produced_not_yet_certified_counts_examined_candidates_only(
    greenstone_world, admin
):
    """B23 / T-010 — the name says "in the venture"; the loop says `for row in candidates`.

    `produced_not_yet_certified` increments inside the per-position candidate loop in
    `generators.appointment`, once per candidate that loop examined and refused. An
    uncertified identity in a department no Greenstone position draws on is never
    examined, so it never lands in this number — while it is unambiguously an agent that
    has been produced and is not yet certified.

    **This is the experiment that separates the two readings, and only this one does.**
    Adding an identity to `research`, `banking` or `operations` moves the counter under
    both readings, because Greenstone has a position in each — every new identity is also
    a candidate. `marketing` has no position, and the two readings disagree there.

    That is the round dismissed in advance as the weaker test in
    `docs/plans/operations-identity-issuance-PREDICTION.md`; a department with no position
    was the only thing that could discriminate. Pinned here because the rename that would
    have carried the meaning is escalated, not made — see `PARALLEL_BUILD_ESCALATION.md`
    — so the docstring and this test are what stop the next reader believing the name.
    """
    unexamined = "88888888-8888-5888-8888-888888888888"
    pack = load_pack(PACK_PATH)

    async with connection() as conn:
        before = (await pipeline.run_all(pack, conn)).appointment.capacity

    try:
        with admin.cursor() as cur:
            # `marketing`: a real seeded department, and one no Greenstone position
            # sources from. Uncertified and active — the exact thing the name describes.
            cur.execute(
                """
                INSERT INTO office_agent_identity
                  (office_agent_id, village_agent_ref, agent_name, department, status)
                VALUES (%s, 'village::Unexamined Mara', 'Unexamined Mara',
                        'marketing', 'active')
                """,
                (unexamined,),
            )
        admin.commit()

        async with connection() as conn:
            after = (await pipeline.run_all(pack, conn)).appointment.capacity

        assert after.produced_not_yet_certified == before.produced_not_yet_certified, (
            "an uncertified identity in a department with no position moved the "
            "counter — it counts candidates examined for positions being appointed, "
            "and nothing examined this one"
        )

        # The other half of the claim: it really is an uncertified active identity. The
        # venture-wide population — which is what `GET /api/ventures/{id}/capacity`
        # counts under the same key — did move. Two numbers, one name, different answers.
        with admin.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM office_agent_identity i
                WHERE i.status = 'active'
                  AND NOT EXISTS (
                    SELECT 1 FROM certification c
                    WHERE c.unit = 'A' AND c.office_agent_id = i.office_agent_id
                      AND c.state = 'certified'
                  )
                """
            )
            roster_uncertified = cur.fetchone()[0]
        assert roster_uncertified > after.produced_not_yet_certified, (
            "the venture-wide count of uncertified active identities must exceed the "
            "artifact's number; if they are equal this test is not discriminating"
        )
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "DELETE FROM office_agent_identity WHERE office_agent_id = %s",
                (unexamined,),
            )
        admin.commit()


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


async def test_the_projection_counts_approvals_per_human_role(artifacts):
    """V13's only input, and the reason the Task Ledger Generator was not deleted whole.

    The ledger produced tasks with owners, priorities and SLAs, which is the Village
    Decomposer's job. This number is not about agent work: it is how many decisions a
    human will be handed per day, and no part of the Village has an opinion about how
    many a compliance officer can absorb before they stop reading them.
    """
    approvals = artifacts.approval_projection.projected_daily_approvals

    assert approvals, "no role is projected to receive any approval"
    assert all(isinstance(count, int) and count > 0 for count in approvals.values())
    # Every role named must be one the Pack actually staffs; a projection against a role
    # with no coverage hours divides by zero in V13 and reads as infinite overload.
    assert set(approvals) <= {"venture_operator", "compliance_officer"}


async def test_the_projection_carries_no_task_shaped_fields(artifacts):
    """The half that was deleted, asserted absent.

    A field that quietly came back would put The Office back in the business of deciding
    what an agent does and when, next to a Village that is already deciding it.
    """
    projection = artifacts.approval_projection
    for gone in ("tasks", "sla_minutes", "assigned_agent", "priority", "task_id"):
        assert not hasattr(projection, gone), (
            f"{gone!r} is back on the approval projection; assignment is the Village's"
        )


# `test_at_most_once_module_carries_its_idempotency_class` was here. It asserted that the
# Task Ledger copied a module's retry class onto each task, and there are no tasks any
# more - the Village Decomposer owns work assignment.
#
# The property it existed to protect is untouched and is tested where it is enforced:
# `tests/contract/test_call_path.py::test_at_most_once_replay_escalates_instead_of_retrying`
# reads `forge_module_registry` and asserts the call path escalates to a human rather
# than retrying. That is the behaviour that matters; the ledger only ever carried a copy
# of the fact.


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


async def test_authored_content_reaches_the_artifact_end_to_end(
    greenstone_world, admin
):
    """The golden covers Greenstone, which has no authored content and never will this
    run - so on its own it proves the mechanical half and nothing about the interface
    P-06/07/08 fill. This threads a content set through `generate` and asserts the
    authored fields arrive.

    `place_call` is used because it is a real Greenstone module with a live
    instruction; the content is built here rather than read from `scenarios/`, so the
    test says what it depends on instead of depending on a file it does not name.
    """
    from generators import curriculum as curriculum_gen
    from generators import scenario_content as sc

    authored = sc.ModuleContent(
        module_id="place_call",
        forge_id="voiceforge",
        scenarios={
            "happy_path": sc.AuthoredScenario(
                scenario_class="happy_path",
                situation="An analyst asks for a seller to be called about a listing.",
                expected_behavior="Place the call and report what came back.",
                expected_escalation="None; the boundary is a named recipient.",
            )
        },
        not_applicable={"rate_limited": "No section of this instruction has one."},
    )
    content = sc.ScenarioContentSet(
        root=sc.default_root(), root_exists=True, modules={"place_call": authored}
    )

    certify_for_positions(admin)
    pack = load_pack(PACK_PATH)
    async with connection() as conn:
        module_forge = await appointment_gen.module_forge_map(conn)
        roles = await roles_gen.generate(pack, conn)
        appointment = await appointment_gen.generate(
            roles, conn, venture_id=pack.venture_id, module_forge=module_forge
        )
        workflow = workflow_gen.generate(pack, roles)
        curriculum = await curriculum_gen.generate(
            pack, roles, workflow, appointment, conn, content=content
        )

    rows = {s.scenario_class: s for s in curriculum.operation_scenarios
            if s.module_id == "place_call"}

    assert rows["happy_path"].summary == authored.scenarios["happy_path"].situation
    assert rows["happy_path"].expected_escalation
    assert "SITUATION: " in rows["happy_path"].expected_behavior
    assert rows["rate_limited"].not_applicable_reason
    assert rows["rate_limited"].expected_behavior == ""

    # And the two mechanical classes nobody authored are still there, still empty.
    assert rows["permission_denied"].expected_behavior == ""
    assert rows["escalation_required"].expected_escalation == ""

    covered = {c.dimension: c for c in curriculum.coverage}
    assert covered["modules_with_authored_scenario_content"].covered == 1
    assert "place_call" not in covered["modules_with_authored_scenario_content"].uncovered


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

    gate_45 = await validate_gate_4_5(pack, artifacts.approval_projection, artifacts.appointment)
    v13 = gate_45.get("V13")
    assert v13.verdict.value == "FAIL", (
        "Greenstone as authored routes more approvals to its compliance officer than "
        "the coverage hours can absorb; Gate 4.5 must catch it"
    )
    assert "compliance officer" in v13.message
    # The message has to say what goes wrong above the line, not just report numbers.
    assert "trust tiers stop meaning anything" in v13.message

    # Verbatim, and it earns the pin. The utilisation factor is the one number here
    # somebody can lower to make the rule pass without changing anything real, so the
    # message closes that door explicitly - and a later edit that drops the clause
    # would leave the obvious wrong fix as the easiest one.
    assert v13.message.rstrip().endswith(
        "Fix by raising a trust-tier ceiling, adding reviewer coverage, or cutting "
        "scope - not by lowering the utilisation factor."
    )


async def test_gate_4_5_resolves_v24(artifacts, greenstone_world):
    """V24 is appointment output, so Gate 2 reported it NOT_RUN. Here it resolves."""
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    gate_45 = await validate_gate_4_5(pack, artifacts.approval_projection, artifacts.appointment)
    assert gate_45.get("V24").verdict.value == "PASS", "all positions were filled"


async def test_gate_4_5_failure_surfaces_as_a_failure_not_a_warning(artifacts):
    """Gate 4 is a human reading artifacts. A finding that only exists in a log line
    is a finding that review will miss - and a finding filed under `warnings` is one
    the reviewer discounts.

    V13 FAILs at Gate 4.5, one gate after the one the human is being asked to clear.
    Carrying that as a bare string in a list called `warnings` is how the console came
    to render "Generator warnings (2)" over one blocking failure and one advisory.
    """
    v13 = next(
        (a for a in artifacts.advisories if a.rule_id == "V13"), None
    )
    assert v13 is not None, (
        f"capacity failure not surfaced for human review: {artifacts.advisories}"
    )
    assert v13.severity == "fail", "a Gate 4.5 FAIL is presented as a warning"
    assert v13.blocks_at == "4.5", (
        "the advisory does not say where the run will halt, so the console has to "
        "infer it from the text of the message"
    )
    assert v13.blocking is True

    # And the genuine advisory is still an advisory. The two must not share a severity
    # any more than they share a container.
    v25 = next((a for a in artifacts.advisories if a.rule_id == "V25"), None)
    if v25 is not None:
        assert v25.severity == "warn"
        assert v25.blocks_at is None


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
    # Planned minus excluded, not planned. Greenstone's roles operate
    # `voiceforge/place_call`, which `forge_module_exclusion` refuses - so a planned
    # grant that is never written is the correct outcome, and the count that would
    # have caught a real regression is this one rather than `len(grants)`.
    assert len(after_first["grants"]) == (
        len(artifacts.runtime_config.grants) - len(first["grants_excluded"])
    )
    assert first["grants_excluded"], (
        "greenstone plans a grant over an excluded module; if this is empty the "
        "exclusion stopped being applied and nothing else here would notice"
    )
    assert len(after_first["budget"]) == 1, "budget must not duplicate"


async def test_apply_wires_both_certification_refs_onto_each_grant(artifacts):
    """5.7 resolves both certification refs, and issues the grant INACTIVE.

    Part 11 Gate 7: "agents appointed but grants inactive". A grant written during
    sandbox provisioning that was live immediately would hand agents production
    authority six gates early, so `apply` leaves `activated_at` NULL and Gate 11
    activates against a valid sign-off.
    """
    from generators import runtime_config as runtime_gen

    async with connection() as conn:
        written = await runtime_gen.apply(
            artifacts.runtime_config, conn,
            granted_by="00000000-0000-5000-8000-00000000bbbb",
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FILTER (WHERE operation_cert_ref IS NOT NULL "
                "                          AND dept_context_cert_ref IS NOT NULL) AS certed, "
                "       count(*) FILTER (WHERE activated_at IS NOT NULL) AS active, "
                "       count(*) AS total "
                "FROM agent_forge_grant WHERE venture_id = 'greenstone'"
            )
            row = await cur.fetchone()
    assert row is not None
    certed, active, total = row
    assert total == len(artifacts.runtime_config.grants) - len(written["grants_excluded"])
    assert certed == total, "both certification refs must be resolved onto every grant"
    assert active == 0, (
        "Gate 5 issues grants inactive; activating here would skip Gate 10 sign-off"
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


# --------------------------------------------- Gate 4.5 V13: weighting by coverage share
#
# blocking.md B24. The Gate 4.5 recheck used to take whichever entry of a role came first
# in the YAML as the review time for everyone in that role. With two compliance officers
# at six hours each, four minutes and three, V13 came out FAIL or PASS depending on line
# order alone - and nothing in the Pack, the message or the code said the order was
# deciding it. These tests fix the aggregation as coverage-weighted and, more importantly,
# pin the property that makes it a fix rather than a different arbitrary choice: the same
# people in a different order give the same answer.

def _officers(pack, *entries):
    """Replace human_capacity with compliance officers at (hours, minutes) each."""
    base = next(h for h in pack.human_capacity if h.role == "compliance_officer")
    return pack.model_copy(
        update={
            "human_capacity": [
                base.model_copy(
                    update={
                        "human_name": f"Officer {n}",
                        "coverage_hours": hours,
                        "median_review_minutes": minutes,
                    }
                )
                for n, (hours, minutes) in enumerate(entries, start=1)
            ]
        }
    )


def _projection(approvals):
    return SimpleNamespace(
        projected_daily_approvals={"compliance_officer": float(approvals)}
    )


_ALL_FILLED = SimpleNamespace(appointments=[])


async def test_v13_review_minutes_do_not_depend_on_list_order():
    """The B24 case itself: two officers, six hours each, four minutes and three.

    Coverage is 12h -> 432 review-minutes at the 0.6 utilisation factor. 120 approvals
    at the weighted 3.5 minutes is 420, which fits. Under the old first-wins rule the
    same two people gave 480 (FAIL) or 360 (PASS) depending on which line was on top.

    The verdicts matching is the point; the messages matching is the stronger claim,
    because it means the number the reviewer reads did not move either.
    """
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    forward = await validate_gate_4_5(
        _officers(pack, (6.0, 4.0), (6.0, 3.0)), _projection(120), _ALL_FILLED
    )
    reverse = await validate_gate_4_5(
        _officers(pack, (6.0, 3.0), (6.0, 4.0)), _projection(120), _ALL_FILLED
    )

    assert forward.get("V13").verdict == reverse.get("V13").verdict
    assert forward.get("V13").message == reverse.get("V13").message
    assert forward.get("V13").verdict.value == "PASS", (
        "120 approvals at the coverage-weighted 3.5 minutes is 420 against 432 available"
    )


async def test_v13_weights_by_coverage_share_not_by_headcount():
    """Unequal coverage separates weighted from mean, first and last.

    Nine hours at four minutes and three hours at eight gives a weighted 5.0. The plain
    mean is 6.0, the first entry is 4.0, the last is 8.0 - so asserting the minutes the
    message prints distinguishes the weighting from every other aggregation that was on
    the table.
    """
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    report = await validate_gate_4_5(
        _officers(pack, (9.0, 4.0), (3.0, 8.0)), _projection(90), _ALL_FILLED
    )

    v13 = report.get("V13")
    assert v13.verdict.value == "FAIL", "90 x 5.0 = 450 against 432 available"
    assert "At 5 minutes each" in v13.message, (
        f"expected the coverage-weighted 5.0, got: {v13.message}"
    )


async def test_v13_is_unchanged_for_a_role_with_one_person():
    """A weighted average of one value is that value.

    Both real Packs declare one person per role, so this change must be invisible to
    them. If it is not, the arithmetic is wrong rather than the Pack.
    """
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    report = await validate_gate_4_5(
        _officers(pack, (4.0, 6.0)), _projection(192), _ALL_FILLED
    )

    v13 = report.get("V13")
    assert v13.verdict.value == "FAIL"
    assert "At 6 minutes each" in v13.message
    assert "192" in v13.message and "1,152" in v13.message


async def test_v13_states_the_answer_when_a_role_has_no_coverage_at_all():
    """Zero coverage hours leaves no share to weight by, and must not divide by zero.

    The review times are still declared - it is the coverage that is missing - so the
    fallback is their plain mean, and the rule then fails on the thing that is actually
    wrong: nobody is covering the role.
    """
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    report = await validate_gate_4_5(
        _officers(pack, (0.0, 4.0), (0.0, 3.0)), _projection(10), _ALL_FILLED
    )

    v13 = report.get("V13")
    assert v13.verdict.value == "FAIL"
    assert "with no reviewer coverage at all" in v13.message
    assert "At 3.5 minutes each" in v13.message


# ------------------------------------- B23: the ceiling nothing enforces, pinned as such
#
# `max_daily_approvals` read as a per-reviewer daily cap. No gate, rule or validator read
# it; its only consumer was a display. Burkham declared Dana at 30 while the approval
# projection sent her 120 a day and nothing anywhere noticed. It is now
# `advisory_daily_approval_ceiling`, and this test is what keeps the name true: if a rule
# ever starts reading it, this fails, and whoever wires it up has to take `advisory_` off
# the front rather than leave a name that has quietly become wrong in the other direction.

async def test_no_rule_reads_the_advisory_daily_approval_ceiling():
    """B23. Vary it across four orders of magnitude; every verdict and message holds.

    Asserting the whole report rather than V13 alone is deliberate. V13 is the rule the
    number *looks* like it belongs to, and checking only V13 would leave "some other rule
    reads it" untested — which is the claim being made.
    """
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    base = _officers(pack, (6.0, 4.0), (6.0, 3.0))

    def _ceiling(value):
        return base.model_copy(
            update={
                "human_capacity": [
                    h.model_copy(update={"advisory_daily_approval_ceiling": value})
                    for h in base.human_capacity
                ]
            }
        )

    # One approval a day each, against a projection of 120. If anything enforced this,
    # 1 could not produce the same answer as 100,000.
    tight = await validate_gate_4_5(_ceiling(1), _projection(120), _ALL_FILLED)
    loose = await validate_gate_4_5(_ceiling(100_000), _projection(120), _ALL_FILLED)

    tight_rules = {r.rule_id: (r.verdict, r.message) for r in tight.results}
    loose_rules = {r.rule_id: (r.verdict, r.message) for r in loose.results}

    assert tight_rules == loose_rules, (
        "a rule read advisory_daily_approval_ceiling. That is a good thing to have "
        "built and it makes this name wrong: the number is no longer advisory, and "
        "B23's other half - 'either a rule reads it or it comes off the schema' - has "
        "been answered. Rename it, do not delete this test."
    )
    assert tight_rules["V13"][0].value == "PASS", (
        "the ceiling of 1 must not change V13: 120 approvals at the coverage-weighted "
        "3.5 minutes is 420 against 432 available, computed from coverage_hours and "
        "median_review_minutes alone"
    )
