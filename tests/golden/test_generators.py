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
    seed_nv_discharge,
    teardown_world,
)

pytestmark = [requires_db, pytest.mark.db]

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture
def greenstone_world(admin: psycopg.Connection):
    """Bridged Forges, authored instructions, roster present, nobody certified yet."""
    build_world(admin)
    # Item F declared `recording_consent_required` human-held, so V34 asks whether a
    # named human verified it - and a run that has not cannot clear Gate 2. Seeded here
    # rather than in `build_world` because only the suites that drive a run need it, and
    # the row references an office_human that twenty-four contract suites delete.
    seed_nv_discharge(admin)
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


@pytest.fixture
async def overloaded_artifacts(greenstone_world, admin):
    """Greenstone with one volume raised until its compliance officer cannot keep up.

    **Needed because Greenstone stopped being overloaded, and that is the correct state.**
    Two tests below assert what a capacity FAILURE looks like - that it is a failure and
    not a warning, that it names where the run halts, that its message closes off lowering
    the utilisation factor. They used to get that failure for free, because the Pack asked
    for 64 approvals a day against two hours of review on the strength of an unattributed
    constant.

    Declared volume removed the overload. Keeping these tests pointed at the real Pack
    would have meant either deleting them or keeping the Pack broken so they had something
    to find - so the overload is constructed here, explicitly, where a reader can see the
    number that causes it.

    500 a week over five operating days is 100 a day; at Ira's ten minutes that is 1,000
    minutes of review against the 36 her one review-hour supplies.
    """
    certify_for_positions(admin)
    pack = load_pack(PACK_PATH)
    pack = pack.model_copy(
        update={
            "positions_required": [
                p.model_copy(
                    update={"expected_weekly_volume": {"cre-forge/assign_contract": 500.0}}
                )
                if p.position_title == "Buyer Network Manager"
                else p
                for p in pack.positions_required
            ]
        }
    )
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

async def test_role_definition_derives_implied_compliance_flags(greenstone_world, admin):
    """G3 — 5.1 does real work.

    The Pack author gave the Buyer Network Manager `recording_consent_required`. It also
    operates `buyer_match` and `assign_contract`, whose Forge registration implies
    `tsr_disclosure_required`. An author who omits a flag has not escaped it.

    RE-ANCHORED 13 September 2026, from the Acquisition Analyst. That position carried
    the same property the other way round - it declared `tsr_disclosure_required` and
    picked up `recording_consent_required` from `place_call`. `place_call` is forbidden
    in `forge_module_exclusion` and is being removed from the Pack, so the position stops
    operating a voiceforge module and there is nothing left for it to imply.

    **The property under test did not change and the anchor did.** Buyer Network Manager
    exercises it in the same shape - one declared flag, one implied by a Forge the author
    did not think about - and it does so both before and after the Pack edit, which is
    why this lands first.

    RE-ANCHORED AGAIN 15 September 2026, and this time on a flag the test writes itself.
    The implied flag it had been reading was `tsr_disclosure_required` on
    `cre-forge/buyer_match` - which the development fixture wrote onto every CRE Forge
    module in one list, and which entry 105 removed because none of those modules
    contacts a person. **So this test was anchored on the defect**: it asserted a real
    mechanism through a value that was not true, and it would have failed the correction
    rather than confirming it.

    Setting the registry row here makes the anchor independent of what any Forge happens
    to imply. The mechanism is the claim - an author who omits a flag has not escaped it
    - and a test of a mechanism should supply its own input.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_module_registry SET compliance_flags_implied = %s "
            "WHERE forge_id = 'cre-forge' AND module_id = 'buyer_match'",
            (["privacy_request_handling"],),
        )
    admin.commit()

    async with connection() as conn:
        roles = await roles_gen.generate(load_pack(PACK_PATH), conn)

    manager = next(
        p for p in roles.positions if p.position_title == "Buyer Network Manager"
    )
    # RE-ANCHORED A THIRD TIME, 16 September 2026, and the declared half moved out.
    #
    # Item F took `recording_consent_required` off this position - the duty belongs to
    # whoever is on the call, and no agent of this venture can place one. So the position
    # declares nothing, and the assertion that it declares something had to go rather than
    # be propped up by putting the flag back.
    #
    # **The mechanism under test is untouched and is the whole of the claim:** a flag the
    # author never wrote reaches the position from the module it operates. That is what the
    # next three lines say, and it is why this test survives an edit that removed the thing
    # it used to read alongside.
    assert manager.declared_compliance_flags == [], (
        "item F moved this position's only declared flag to market.compliance_surface"
    )
    assert "privacy_request_handling" in manager.implied_compliance_flags, (
        "a flag on a module the position operates reaches the position"
    )
    assert "privacy_request_handling" not in manager.declared_compliance_flags
    assert set(manager.effective_compliance_flags) == {"privacy_request_handling"}

    underwriter = next(
        p for p in roles.positions if p.position_title == "Deal Underwriter"
    )
    assert underwriter.effective_compliance_flags == [], (
        "a position whose modules imply nothing and which declares nothing carries "
        "nothing - the state entry 105 restored"
    )


async def test_appointment_never_fills_a_position_with_an_uncertified_agent(
    greenstone_world, admin
):
    """G4 — 5.2 as entry 145 applies it: a seat may be filled by somebody eligible to
    sit the exam, and certification is what Gate 11 requires before authority.

    **This test asserted the opposite until 21 September**, and the rule it asserted
    closed the ladder: 4.5 seated only certified agents, Gate 5 granted only to the
    seated, Gate 8 examined only grant holders, and the sweep certified only the
    examined. Nothing could become certified without an off-ladder bootstrap.

    So what is asserted now is the pair that makes the change a move rather than a
    loosening: the seat IS filled, and the agent in it is `certified=False`, still named
    in `requires_certification` with the specific state that explains it, and counted
    nowhere that claims it can operate.
    """
    # Unit B only: department certification is necessary, never sufficient.
    certify(admin, [], [], unit_b_departments=[d for _a, _n, d in ROSTER])
    pack = load_pack(PACK_PATH)

    async with connection() as conn:
        result = await pipeline.run_all(pack, conn)

    for position in result.appointment.appointments:
        if position.pending:
            # A PENDING POSITION IS NOT AN UNCERTIFIED ONE, AND THE DIFFERENCE IS THE TEST.
            #
            # Both appoint nobody. What separates them is whether that is a gap: an
            # uncertified position reports its whole headcount unfilled and names the
            # candidates who fell short, because somebody should go and certify them. A
            # pending position reports nothing unfilled and no candidates, because nobody
            # is meant to be appointed to it yet.
            #
            # Asserting this inside the same loop is deliberate. If `pending` ever stopped
            # being set, this branch would go unvisited and the assertions below would run
            # against Deal Underwriter and fail - so the loop cannot silently skip it.
            assert position.unfilled == 0, "a deferred position is not a shortfall"
            assert position.requires_certification == [], (
                "a pending position must not ask anybody to go and get certified"
            )
            continue
        assert position.appointed, (
            f"{position.position_title} has eligible candidates and no seat filled; "
            "entry 145 makes an exam ticket the test, not a certification"
        )
        assert position.unfilled == 0
        assert all(not a.certified for a in position.appointed), (
            "nobody here is certified, so no appointment may claim to be"
        )
        assert position.requires_certification, "candidates must be reported, not hidden"
        assert all(
            c.reason in ("never_certified", "in_training", "missing_unit_b")
            for c in position.requires_certification
        )
        seated = {a.office_agent_id for a in position.appointed}
        assert seated <= {c.office_agent_id for c in position.requires_certification}, (
            "an uncertified agent in a seat must still be named in the gap report"
        )

    assert result.appointment.capacity.certified_and_free == 0, (
        "not one of these agents is certified; the number that says who can operate "
        "today must not move because a seat was filled by somebody who cannot"
    )

    assert any(p.pending for p in result.appointment.appointments), (
        "Deal Underwriter is declared pending in the Pack; if no appointment reports it "
        "pending, the branch above never ran and this test asserted less than it reads as"
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
    # STILL A SHORTFALL, and since entry 145 that is the assertion worth keeping. Seats
    # now fill with eligible candidates, so reading `shortfall` off `unfilled` alone
    # would have switched the governance escalation off on the day positions stopped
    # emptying. A seat held by somebody who cannot operate it is still a shortfall.
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
    # FLOAT, NOT INT, SINCE THE RATE BECAME DECLARED.
    #
    # It was `isinstance(count, int)` while demand was a count of (step, holder, module)
    # units times 8. A venture closing one deal a week runs `assign_contract` 0.2 times a
    # day, and an int would have to round that to 0 or 1 - "no reviewer load at all" or
    # "five times the real load". Neither is the answer, so the type changed.
    assert all(
        isinstance(count, float) and count > 0 for count in approvals.values()
    ), approvals
    # Every role named must be one the Pack actually staffs; a projection against a role
    # with no coverage hours divides by zero in V13 and reads as infinite overload.
    assert set(approvals) <= {"venture_operator", "compliance_officer"}


async def test_gate_4_5_routes_by_the_declared_reviewer_too(artifacts):
    """The other gate, through the real pipeline rather than through the Pack alone.

    Gate 2 resolves the reviewer from `Position`; this path resolves it from the generated
    `DefinedPosition`, against declared UNION implied flags. **Two code paths, and the
    declaration has to reach both** - it is the one input to routing that is identical at
    the two gates, which is most of why it is worth declaring.
    """
    bnm = next(
        p for p in artifacts.roles.positions
        if p.position_title == "Buyer Network Manager"
    )
    assert bnm.module_reviewer_roles == {"cre-forge/assign_contract": "compliance_officer"}
    assert artifacts.approval_projection.projected_daily_approvals == {
        "compliance_officer": 0.2
    }


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
    """G9 — 'report the denominator; no green check without a coverage count'.

    **A ZERO DENOMINATOR IS AN ANSWER NOW, AND ONLY FOR ONE DIMENSION.**

    `compliance_flags_exercised` counts the flags a scenario must exercise. Item F declared
    both of Greenstone's human-held, so no agent holds either duty and there is nothing for
    a scenario to exercise - 0 of 0, which is true. The rule G9 is about is "no green check
    without a coverage count", and 0/0 reported as 0/0 is a count.

    Every OTHER dimension still has to have something to count, which is why this is a
    named exception rather than a relaxed `>= 0`. A modules dimension that fell to zero
    would mean the venture operates no modules, and that is a defect rather than a state.
    """
    assert artifacts.curriculum.coverage

    # Dimensions whose subject can legitimately be empty, and why.
    #
    # `modules_with_a_draft_answer_key_awaiting_approval` counts the modules with NO
    # approved key, and how many of those are at least drafted. Its denominator is the
    # size of the gap, so 0/0 is the healthy end state - every module has an approved
    # answer key and there is nothing outstanding. It reached 0/0 the day Ivan approved
    # Greenstone's five, which is the outcome, not a defect.
    #
    # It is named here rather than relaxing the rule, for the reason the docstring
    # gives: a MODULES dimension falling to zero means the venture operates no modules
    # and that is a defect. This one is not a count of modules; it is a count of a gap.
    may_be_empty = {
        "compliance_flags_exercised",
        "modules_with_a_draft_answer_key_awaiting_approval",
    }

    for coverage in artifacts.curriculum.coverage:
        if coverage.denominator == 0:
            assert coverage.dimension in may_be_empty, (
                f"{coverage.dimension} has no denominator. Only a dimension whose subject "
                f"can honestly be empty may report 0/0; {sorted(may_be_empty)} is that list."
            )
            assert coverage.covered == 0
            assert coverage.uncovered == []
            continue
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

    `comp_analysis` is used because it is a real Greenstone module with a live
    instruction; the content is built here rather than read from `scenarios/`, so the
    test says what it depends on instead of depending on a file it does not name.

    RE-ANCHORED twice on 15 September 2026: from `place_call` when that left the Pack
    (entry 83), then from `transcribe_call` when the whole VoiceForge binding did (entry
    87). Each time the property - authored fields arrive in the artifact - was unchanged
    and only the module moved. `comp_analysis` is on the operating Forge, which a Pack
    cannot provision without, so the next binding removal is not going to move it again.
    """
    from generators import curriculum as curriculum_gen
    from generators import scenario_content as sc

    authored = sc.ModuleContent(
        module_id="comp_analysis",
        forge_id="cre-forge",
        # A LIST per class since the split keys landed - see the A2.1 amendment on
        # `ModuleContent.scenarios`. Two occasions here rather than one, so this also
        # asserts that a second occasion reaches the artifact instead of being dropped.
        scenarios={
            "happy_path": [
                sc.AuthoredScenario(
                    scenario_class="happy_path",
                    situation=(
                        "An analyst needs comparable sales for a candidate before "
                        "valuing it."
                    ),
                    expected_behavior="Run comp_analysis for the subject and report the comps.",
                    expected_escalation="None; the boundary is a named recipient.",
                    expected_answer={"act": "PROCEED", "record_subject": "comps"},
                ),
                sc.AuthoredScenario(
                    scenario_class="happy_path",
                    situation=(
                        "The same analyst asks again a week later, after two more "
                        "sales closed within the radius."
                    ),
                    expected_behavior="Re-run and report the radius and age window with the count.",
                    expected_escalation="None; the parameters travel with the answer.",
                    expected_answer={"act": "PROCEED", "record_subject": "comps"},
                ),
            ]
        },
        not_applicable={"rate_limited": "No section of this instruction has one."},
    )
    content = sc.ScenarioContentSet(
        root=sc.default_root(), root_exists=True, modules={"comp_analysis": authored}
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

    # A class may now carry several rows, so this groups rather than overwrites. The
    # dict-comprehension it replaces silently kept whichever row came last, which would
    # have made a dropped second occasion look identical to a working one.
    rows: dict[str, list] = {}
    for s_ in curriculum.operation_scenarios:
        if s_.module_id == "comp_analysis":
            rows.setdefault(s_.scenario_class, []).append(s_)

    assert len(rows["happy_path"]) == 2, "the second occasion was dropped"
    assert [r.summary for r in rows["happy_path"]] == [
        a.situation for a in authored.scenarios["happy_path"]
    ], "the occasions arrived out of order or altered"
    # The ordinal appears only where it has to: one occasion keeps the bare id.
    assert [r.scenario_id for r in rows["happy_path"]] == [
        "op-comp_analysis-happy_path-1", "op-comp_analysis-happy_path-2"
    ]
    assert rows["rate_limited"][0].scenario_id == "op-comp_analysis-rate_limited"
    # The gradeable half arrives too.
    assert rows["happy_path"][0].expected_answer == {
        "act": "PROCEED", "record_subject": "comps"
    }
    assert rows["happy_path"][0].expected_escalation
    # Two fields, not one packed field. `summary` carries the occasion and is what the
    # submission sends as `situation`; `expected_behavior` is the act alone.
    assert rows["happy_path"][0].summary
    assert not rows["happy_path"][0].expected_behavior.startswith("SITUATION: ")
    assert rows["rate_limited"][0].not_applicable_reason
    assert rows["rate_limited"][0].expected_behavior == ""

    # And the two mechanical classes nobody authored are still there, still empty.
    assert rows["permission_denied"][0].expected_behavior == ""
    assert rows["escalation_required"][0].expected_escalation == ""

    covered = {c.dimension: c for c in curriculum.coverage}
    assert covered["modules_with_authored_scenario_content"].covered == 1
    assert "comp_analysis" not in covered["modules_with_authored_scenario_content"].uncovered


async def test_domain_and_operation_scenarios_are_never_merged(artifacts):
    """Part 10.1: two rubrics, never merged - so two scenario sets, never merged."""
    assert all(s.kind == "domain" for s in artifacts.curriculum.domain_scenarios)
    assert all(s.kind == "operation" for s in artifacts.curriculum.operation_scenarios)
    domain_ids = {s.scenario_id for s in artifacts.curriculum.domain_scenarios}
    op_ids = {s.scenario_id for s in artifacts.curriculum.operation_scenarios}
    assert not (domain_ids & op_ids)


# ------------------------------------------------------------------ Gate 4.5

async def test_both_gates_now_agree_and_certification_is_the_only_thing_left(
    artifacts, greenstone_world
):
    """What replaced "Gate 2 is the optimistic one". They compute the same quantity now.

    **This test used to assert the opposite and was right to.** V13 at Gate 2 estimated
    approvals from Pack headcount times an unattributed constant; the Task Ledger computed
    them from the real workflow; for Greenstone as authored the two disagreed by an order
    of magnitude, and neither was buggy - Gate 2 could not see a workflow that did not
    exist yet. That is B25, and it is what put a second capacity check after the
    generators.

    A declared per-module volume sits on the POSITION, and the position carries the flags
    that pick the reviewer, so Gate 2 can attribute demand by role with no workflow at all.
    Both gates read the same rates through the same helpers.

    **One difference survives and it is named rather than removed:** Gate 4.5 caps each
    module's tier by what its appointed agents are certified to, and no appointment exists
    at Gate 2. `GATE_45_RECHECKS` still carries V13 for exactly that, which is why this
    asserts the recheck list rather than only the two verdicts.
    """
    from generators.validator import GATE_45_RECHECKS, validate, validate_gate_4_5

    pack = load_pack(PACK_PATH)
    gate_2 = await validate(pack)
    gate_45 = await validate_gate_4_5(
        pack, artifacts.approval_projection, artifacts.appointment
    )

    assert gate_2.get("V13").verdict.value == "PASS"
    assert gate_45.get("V13").verdict.value == "PASS"
    assert "V13" in GATE_45_RECHECKS, (
        "the recheck exists for the certification cap; dropping it would make Gate 2's "
        "answer final on a question it cannot see the whole of"
    )


async def test_a_capacity_failure_still_says_what_goes_wrong_above_the_line(
    overloaded_artifacts, greenstone_world
):
    """The message, pinned on a constructed overload rather than on a broken Pack."""
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    gate_45 = await validate_gate_4_5(
        pack,
        overloaded_artifacts.approval_projection,
        overloaded_artifacts.appointment,
    )
    v13 = gate_45.get("V13")

    assert v13.verdict.value == "FAIL"
    assert "compliance officer" in v13.message
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


async def test_gate_4_5_failure_surfaces_as_a_failure_not_a_warning(overloaded_artifacts):
    """Gate 4 is a human reading artifacts. A finding that only exists in a log line
    is a finding that review will miss - and a finding filed under `warnings` is one
    the reviewer discounts.

    V13 FAILs at Gate 4.5, one gate after the one the human is being asked to clear.
    Carrying that as a bare string in a list called `warnings` is how the console came
    to render "Generator warnings (2)" over one blocking failure and one advisory.
    """
    v13 = next(
        (a for a in overloaded_artifacts.advisories if a.rule_id == "V13"), None
    )
    assert v13 is not None, (
        "capacity failure not surfaced for human review: "
        f"{overloaded_artifacts.advisories}"
    )
    assert v13.severity == "fail", "a Gate 4.5 FAIL is presented as a warning"
    assert v13.blocks_at == "4.5", (
        "the advisory does not say where the run will halt, so the console has to "
        "infer it from the text of the message"
    )
    assert v13.blocking is True

    # And the genuine advisory is still an advisory. The two must not share a severity
    # any more than they share a container.
    v25 = next(
        (a for a in overloaded_artifacts.advisories if a.rule_id == "V25"), None
    )
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
    # Planned minus excluded, not planned. No Greenstone role operates an excluded
    # module since `voiceforge/place_call` left the Pack, so `grants_excluded` is empty
    # here; the exclusion path itself is covered on purpose by
    # `test_apply_skips_an_excluded_module_and_names_it`, not by this fixture.
    assert len(after_first["grants"]) == (
        len(artifacts.runtime_config.grants) - len(first["grants_excluded"])
    )
    assert len(after_first["budget"]) == 1, "budget must not duplicate"


async def test_apply_skips_an_excluded_module_and_names_it(greenstone_world, admin):
    """An excluded module is skipped and reported, and the rest of the config applies.

    SPLIT OUT 13 September 2026 from `test_apply_wires_...idempotent`, which asserted
    this by borrowing a production Pack: Greenstone declared `voiceforge/place_call`,
    which `forge_module_exclusion` forbids, so a planned-but-never-written grant fell out
    of the fixture for free. Its own comment said the quiet part - *"if this is empty the
    exclusion stopped being applied and nothing else here would notice."*

    **That made one venture's Pack the only coverage of a safety control, and the control
    was tested by accident.** Removing the forbidden module from that Pack - which is
    correct, and is happening - would have taken the only test of `apply`'s exclusion
    path with it, silently, which is the shape entry 58 rules against.

    So the grant is constructed here instead. The test now says what it depends on, holds
    whatever any Pack declares, and covers the branch on purpose.
    """
    from generators import runtime_config as runtime_gen
    from generators.artifacts import PlannedGrant, RuntimeConfig

    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT forge_id, module_id FROM forge_module_exclusion "
            " WHERE forge_id = 'voiceforge' AND module_id = 'place_call'"
        )
        row = await cur.fetchone()

    assert row is not None, (
        "voiceforge/place_call is not in forge_module_exclusion. It is forbidden by a "
        "founder decision binding every venture; if the row is gone, that is the finding "
        "and not a reason to change this test."
    )
    forge_id, module_id = row

    config = RuntimeConfig(
        venture_id="greenstone",
        environment="sandbox",
        grants=[
            PlannedGrant(
                grant_id="00000000-0000-5000-8000-0000000e0001",
                office_agent_id="11111111-1111-5111-8111-111111111111",
                forge_id=forge_id,
                module_id=module_id,
                trust_tier="suggest",
            )
        ],
        manifest_rows=[],
        rate_limits={},
        budget={
            "monthly_usd_cap": 1000.0,
            "soft_cap_pct": 80,
            "per_agent_usd_daily_cap": 10.0,
            "per_task_usd_ceiling": 1.0,
        },
        compliance_flags=[],
        blocked_reason=None,
    )

    async with connection() as conn:
        written = await runtime_gen.apply(
            config, conn, granted_by="00000000-0000-5000-8000-00000000bbbb"
        )

    assert written["grants"] == 0, (
        "a grant over an excluded module was written. The exclusion means no agent may "
        "hold this at any tier, and apply is the layer that is supposed to know."
    )
    assert len(written["grants_excluded"]) == 1, (
        "the excluded grant was skipped without being named. Skipping silently is how a "
        "Pack keeps declaring a module nobody can ever hold: nothing in the run says so."
    )
    skipped = written["grants_excluded"][0]
    assert skipped["module_id"] == module_id
    assert skipped["reason"], "an exclusion is reported with its reason or not at all"


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
    """Replace human_capacity with compliance officers at (hours, minutes) each.

    **Every hour is a review hour here, stated rather than inherited.** These cases are
    about how V13 aggregates review time across people, so the split that arrived with
    `review_hours` has to be filled in or the rule refuses before it aggregates anything -
    and a test that stopped exercising B24's arithmetic while still being named for it is
    the failure mode entry 103 records twice.

    Putting the whole of `coverage_hours` into `review_hours` keeps every number in these
    tests meaning what it meant: the weighted average that used to be taken over coverage
    is taken over review hours, and where the two are equal the arithmetic is unchanged.
    The real Packs are where they differ, and `test_v13_declared_volume.py` is where that
    difference is asserted.
    """
    base = next(h for h in pack.human_capacity if h.role == "compliance_officer")
    return pack.model_copy(
        update={
            "human_capacity": [
                base.model_copy(
                    update={
                        "human_name": f"Officer {n}",
                        "coverage_hours": hours,
                        "review_hours": hours,
                        "countersign_hours": 0.0,
                        "other_hours": 0.0,
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
    # "coverage" became the TOTAL when the hours split, so the message names what is
    # actually zero. A role can now hold six coverage-hours and no review time at all,
    # and the old wording would have called that "no coverage".
    assert "with no reviewer review-time at all" in v13.message
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


async def test_a_second_apply_reconciles_certification_refs(greenstone_world, admin):
    """Re-applying repairs a grant's certification refs; it does not rewrite its history.

    WHY THIS TEST DID NOT EXIST
    ===========================

        `record_result` upserts on the natural key, so reissuing a certification preserves
        its `cert_id` and a grant's refs stay valid forever under every sanctioned path.
        There was no reachable way to make them stale — until `certification` was truncated
        by an unisolated test run (entry 47), and 34 Burkham grants were left pointing at
        rows that no longer existed.

        The obvious remedy was to re-run the pipeline, since `apply` resolves the refs from
        live certifications. **It could not work**: every stale grant already existed, so
        every one took the `DO UPDATE` branch, which set `trust_tier` and returned
        (entry 68). This asserts the branch now converges.

    WHAT IS DELIBERATELY NOT ASSERTED
    =================================

        That `granted_by` and `granted_at` are refreshed. They are history, not pointers,
        and a re-run that rewrote who granted something or erased when would be a worse
        defect than the one this fixes. Both are asserted UNCHANGED below, so the fix
        cannot quietly widen.
    """
    from generators import runtime_config as runtime_gen

    certify_for_positions(admin)
    pack = load_pack(PACK_PATH)
    async with connection() as conn:
        artifacts = await pipeline.run_all(pack, conn)
        await runtime_gen.apply(
            artifacts.runtime_config, conn,
            granted_by="00000000-0000-5000-8000-00000000bbbb",
        )

    # Break one grant's refs the way a truncation does: a well-formed uuid pointing at
    # nothing. Not NULL — a NULL ref is already reported by resolve_grant, and the
    # failure this covers is the one that stays silent.
    dangling = "00000000-0000-4000-8000-0000deadbeef"
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET operation_cert_ref = %s, "
            "dept_context_cert_ref = %s WHERE venture_id = %s "
            "RETURNING grant_id, granted_by, granted_at",
            (dangling, dangling, pack.venture_id),
        )
        before = cur.fetchall()
    admin.commit()
    assert before, "no grants to break; the fixture stopped producing them"

    async with connection() as conn:
        await runtime_gen.apply(
            artifacts.runtime_config, conn,
            granted_by="00000000-0000-5000-8000-00000000cccc",
        )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT grant_id, operation_cert_ref, dept_context_cert_ref, "
            "       granted_by, granted_at "
            "  FROM agent_forge_grant WHERE venture_id = %s",
            (pack.venture_id,),
        )
        after = {r[0]: r for r in cur.fetchall()}

    history = {r[0]: (r[1], r[2]) for r in before}
    repaired = 0
    for grant_id, op_ref, dept_ref, granted_by, granted_at in after.values():
        assert op_ref != dangling, (
            f"grant {str(grant_id)[:8]} still carries the dangling unit-A ref after a "
            "second apply. Re-provisioning cannot repair a stale certification ref, "
            "which is the whole of entry 68."
        )
        assert dept_ref != dangling, (
            f"grant {str(grant_id)[:8]} still carries the dangling unit-B ref."
        )
        if op_ref is not None:
            repaired += 1
        # History is untouched. A re-run that rewrote these would be a worse defect.
        assert (granted_by, granted_at) == history[grant_id], (
            f"grant {str(grant_id)[:8]} had its history rewritten by a re-apply. "
            "granted_by and granted_at record who and when; only the pointers converge."
        )

    assert repaired, (
        "no grant resolved to a live certification, so this asserted nothing. The "
        "fixture certifies before applying; if that stopped happening the test is inert."
    )
