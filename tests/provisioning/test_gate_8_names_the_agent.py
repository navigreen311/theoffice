"""Gate 8 blocks when SimForge accepts nothing, and every submission names who sat it.

Two rulings by Ivan Green, 17 September 2026, and one measurement that connects them.

WHY THE AGENT WAS NEVER NAMED
=============================

    The gate sent `agent_id` only when a module had exactly one certification
    candidate. Measured on greenstone before any of this was built: ten candidates for
    `assign_contract` and `buyer_match`, **none** for `comp_analysis` and
    `property_lookup`. Never one. So `agent_id` was NULL on every run ever opened and
    SimForge skipped every one of them - `battery.py` requires `run.agentId`.

    The population was also the wrong one. `_certification_candidates` reads
    `requires_certification`, which deliberately EXCLUDES the appointed agent: it is the
    pool of people who could fill a seat and do not hold the certification. Not one of
    greenstone's ten holds a grant for the module. Gate 9 reads certification through
    grants, so the exam would have named agents whose results nothing could read.

WHY ZERO ACCEPTED IS A BLOCK AND SOME-REFUSED IS NOT
====================================================

    This gate passed on everything for its whole life and the reasoning was sound: a
    rejection is an answer, the evidence records it, and blocking the ladder on a
    service allowed to be down would be worse. That argument covers some modules
    refused. It does not cover all of them - run cb3a47f6 passed here on "0 of 5
    module(s) accepted by SimForge" and stopped at Gate 9 with twelve certifications
    nothing external had attested, three gates later, for a reason this gate knew.

THE TEST THAT KEEPS THIS HONEST
===============================

    `test_a_partial_refusal_still_passes`. Every other test here asserts something
    stops or starts counting, and a gate that blocked on any refusal would satisfy the
    block tests while destroying the distinction the block is drawn on.
"""

from __future__ import annotations

import uuid

import pytest

from broker import provisioning
from broker.simforge import (
    CurriculumRejectedError,
    ResponseRefusedError,
    mint_run_ref,
)
from tests.conftest import requires_db
from tests.provisioning.test_simforge_handover import (  # noqa: F401 - fixtures
    SimForgeAccepts,
    SimForgeRefuses,
    at_gate_8,
)

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


def _gate_8(outcomes):
    for outcome in outcomes:
        if outcome.gate == "8":
            return outcome
    raise AssertionError("Gate 8 did not run")


async def _live_grant_holders(conn, module_id: str) -> set[str]:
    """The population `_exam_takers` is supposed to return, asked independently."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT g.office_agent_id::text FROM agent_forge_grant g "
            " WHERE g.venture_id = %s AND g.module_id = %s "
            "   AND g.superseded_at IS NULL",
            (VENTURE, module_id),
        )
        return {r[0] for r in await cur.fetchall()}


# ------------------------------------------------------- the block on zero accepted

async def test_gate_8_blocks_when_simforge_accepts_nothing(at_gate_8, operator):  # noqa: F811
    """The state run cb3a47f6 was in, and it used to pass."""
    conn, run_id = at_gate_8
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=SimForgeRefuses()
    )

    gate_8 = _gate_8(outcomes)
    assert gate_8.verdict == provisioning.BLOCKED, gate_8.reason
    assert "accepted none" in gate_8.reason
    assert gate_8.evidence["modules_accepted"] == 0
    assert gate_8.evidence["modules_submitted"] > 0
    # The refusal names the modules, so the reader is not sent to the evidence blob to
    # find out which ones are wrong.
    assert "property_lookup" in gate_8.reason

    state = await provisioning.get_run(conn, run_id)
    assert state is not None
    assert state.current_gate == "8"
    assert state.status == "blocked"


async def test_a_partial_refusal_still_passes(at_gate_8, operator):  # noqa: F811
    """**The test that keeps the block a distinction rather than a tripwire.**

    One module accepted is a venture with somewhere to start. A gate that refused on
    any rejection would pass every other test in this file.
    """
    conn, run_id = at_gate_8

    class RefusesAllButOne:
        def __init__(self) -> None:
            self.run_starts: list[dict] = []

        async def submit_curriculum(self, conn, **kwargs) -> dict:
            module_id = kwargs["payload"]["instruction_set_ref"]["module_id"]
            if module_id != "property_lookup":
                raise CurriculumRejectedError(
                    [f"scenario[0] (module {module_id}): missing everything"]
                )
            return {
                "accepted": True,
                "module_levels": {module_id: "demonstrated"},
                "module_declared_absences": {},
                "never_do_obligations": [],
                "coverage_declaration": kwargs["payload"]["coverage_declaration"],
                "gate_9_5_flag": False,
            }

        async def run_start(self, conn, **kwargs) -> dict:
            self.run_starts.append(kwargs)
            return {
                "run_ref": kwargs["run_ref"], "unit": kwargs["unit"],
                "started_at": "2026-09-17T00:00:00Z", "window_minutes": 240,
                "already_open": False,
            }

        async def aclose(self) -> None:
            pass

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=RefusesAllButOne()
    )
    gate_8 = _gate_8(outcomes)
    assert gate_8.verdict == provisioning.PASSED, gate_8.reason
    assert gate_8.evidence["modules_accepted"] == 1


# ------------------------------------- the answer The Office refused, not an outage

async def test_a_refused_response_is_not_reported_as_an_outage(at_gate_8, operator):  # noqa: F811
    """SimForge answering and The Office refusing the answer is a third thing.

    **It cost an afternoon on 17 September 2026.** SimForge echoes
    `module_declared_absences` back on every acceptance, the declared `rate_limited`
    reasons ran to 1,470-1,800 characters, and `assert_no_scenario_content` refuses any
    echoed string that long. Four Greenstone modules were ACCEPTED and recorded as a
    Forge that could not be reached - so the evidence said restart SimForge, and
    SimForge was fine.

    Three outcomes, three different responses: restart a service, write scenarios, or
    shorten what we send. The gate has to tell them apart.
    """
    conn, run_id = at_gate_8

    class AcceptsThenEchoesProse:
        """Accepts, and replies with a field the response manifest refuses."""

        async def submit_curriculum(self, conn, **kwargs) -> dict:
            module_id = kwargs["payload"]["instruction_set_ref"]["module_id"]
            raise ResponseRefusedError(
                f"submit_curriculum: field 'module_declared_absences.{module_id}."
                "rate_limited' carries 1800 characters of prose."
            )

        async def run_start(self, conn, **kwargs) -> dict:  # pragma: no cover
            raise AssertionError("run_start must not be reached")

        async def aclose(self) -> None:
            pass

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=AcceptsThenEchoesProse()
    )
    gate_8 = _gate_8(outcomes)

    # NOT blocked: SimForge did not refuse the content, so blocking would report
    # scenarios as wrong when they were accepted.
    assert gate_8.verdict == provisioning.PASSED, gate_8.reason
    assert gate_8.evidence["modules_response_refused"], (
        "a refused response was not recorded as one"
    )
    assert gate_8.evidence["modules_unreachable"] == [], (
        "a refused response was counted as an outage; that is the misreport this "
        "test exists to prevent"
    )
    assert gate_8.evidence["modules_refused"] == [], (
        "a refused response was counted as SimForge refusing the curriculum"
    )
    # And the sentence says so, because a reader who sees only "0 accepted" will go
    # and restart a Forge that is answering.
    assert "refused by The Office reading the reply back" in gate_8.reason


# ------------------------------------------------------------- naming the agent

async def test_every_run_names_the_agent_who_holds_the_grant(at_gate_8, operator):  # noqa: F811
    """One run per grant holder, each naming its own agent.

    Asserted against the grant table read separately, not against a number this gate
    reported: a gate that opened one run and said it opened one would satisfy a
    self-referential count.
    """
    conn, run_id = at_gate_8
    forge = SimForgeAccepts()
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=forge
    )
    gate_8 = _gate_8(outcomes)
    assert gate_8.verdict == provisioning.PASSED, gate_8.reason

    unit_a = [r for r in forge.run_starts if r["unit"] == "A"]
    assert unit_a, "no unit-A run was opened at all"
    assert all(r["agent_id"] is not None for r in unit_a), (
        "a unit-A run was opened without naming the agent taking it - SimForge's "
        "battery requires run.agentId and skips the run without one"
    )

    by_module: dict[str, set[str]] = {}
    for r in unit_a:
        by_module.setdefault(r["module_id"], set()).add(str(r["agent_id"]))

    for module_id, named in by_module.items():
        assert named == await _live_grant_holders(conn, module_id), (
            f"{module_id}: the agents examined are not the agents who hold the grant, "
            "so Gate 9 would read a certification for somebody who never sat it"
        )


async def test_two_holders_of_one_module_are_two_runs_with_two_refs(
    at_gate_8, operator  # noqa: F811
):
    """The collision the ref's agent segment exists to prevent.

    `buyer_match` is held by two agents. Without the agent in the ref both runs would
    mint the same one, `open_run` is idempotent on it, and the second `run_start` would
    land silently on the first agent's run - one verdict read back as two results.
    """
    conn, run_id = at_gate_8
    forge = SimForgeAccepts()
    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=forge
    )

    holders = await _live_grant_holders(conn, "buyer_match")
    assert len(holders) > 1, (
        "this world no longer has a module two agents hold, so this test asserts "
        "nothing - pick another module or restore the fixture"
    )

    runs = [r for r in forge.run_starts if r.get("module_id") == "buyer_match"]
    assert len(runs) == len(holders)
    assert len({r["run_ref"] for r in runs}) == len(holders), (
        "two agents' runs minted the same run_ref"
    )


async def test_the_submission_row_records_the_agent(at_gate_8, operator):  # noqa: F811
    """0044's column, doing the job the sweep used to reconstruct."""
    conn, run_id = at_gate_8
    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=SimForgeAccepts()
    )

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, department, office_agent_id::text, simforge_run_ref "
            "FROM curriculum_submission WHERE venture_id = %s",
            (VENTURE,),
        )
        rows = await cur.fetchall()

    unit_a = [r for r in rows if r[0] is not None and r[3] is not None]
    assert unit_a, "no unit-A submission was written"
    assert all(r[2] is not None for r in unit_a), (
        "a unit-A submission with an open run names no agent"
    )
    unit_b = [r for r in rows if r[1] is not None]
    assert all(r[2] is None for r in unit_b), (
        "a unit-B submission named an agent; it is about a department"
    )


def test_the_ref_carries_the_agent_and_a_unit_b_ref_does_not():
    """The minter, directly. Two agents, one module, one instruction: two refs."""
    a, b = uuid.uuid4(), uuid.uuid4()
    common = {
        "venture_id": VENTURE, "forge_id": "cre-forge", "content_hash": "a" * 64,
    }
    ref_a = mint_run_ref(module_id="buyer_match", office_agent_id=a, **common)
    ref_b = mint_run_ref(module_id="buyer_match", office_agent_id=b, **common)
    assert ref_a != ref_b
    assert str(a)[:8] in ref_a

    dept = mint_run_ref(module_id=None, department="research", **common)
    assert "dept:research" in dept
    assert str(a)[:8] not in dept

    # A unit-A ref minted without an agent keeps its old shape, so a run opened before
    # this ruling still resolves.
    unnamed = mint_run_ref(module_id="buyer_match", **common)
    assert unnamed == "office:greenstone:cre-forge:buyer_match:" + "a" * 12
