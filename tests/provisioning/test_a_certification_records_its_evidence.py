"""A certification records the evidence behind its verdict, not the verdict alone.

RULED 22 SEPTEMBER 2026 (decisions entry 173)
=============================================

    *"A certification records the evidence behind its verdict, not the verdict alone.
    Enough to tell a wrong verdict from a right one without asking the examiner.
    Measured: three exams scored 1.0 on every attempt with no failure modes and were
    recorded FAILED; The Office held only the aggregate and could not have seen it."*

THE SHAPE THAT PRODUCED THE RULING
==================================

    `comp_analysis`, 22 September, as The Office recorded it:

        verdict FAIL, score 0.8, threshold 1.0

    The same run, from SimForge's battery record:

        attempts    1.0, 1.0, 1.0 - passed every sitting
        modes       none
        withheld    nothing

    Three of five failing exams had exactly that shape, and a fourth with the identical
    shape was certified.

THE TWO THAT CARRY THE RULING
=============================

    `test_the_measured_shape_reads_as_a_disagreement` - the real payload, verbatim.

    `test_a_partial_score_is_not_a_disagreement` - the other side, and the reason the
    predicate is narrow: a judgement call is not a contradiction.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from broker import certification, simforge
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


def _battery(
    *, state: str = "failed", attempts: list[dict[str, Any]] | None = None,
    withheld: list[str] | None = None, modes: list[str] | None = None,
    per_class: dict[str, str] | None = None, observed: bool = True,
) -> dict[str, Any]:
    """A `battery_result` body in SimForge's real shape."""
    return {
        "run_ref": "office:greenstone:cre-forge:comp_analysis@aaaa:bbbb:cccc:p6.0.0:r0.5.0",
        "unit": "A",
        "forge_id": "cre-forge",
        "module_id": "comp_analysis",
        "agent_id": str(uuid.uuid4()),
        "observed": observed,
        "join": "natural_key(forge_id, module_id, agent_id) bounded by run.startedAt",
        "certifications": [
            {
                "state": state,
                "operation_rubric_version": "0.5.0",
                "instruction_content_hash": "d" * 64,
                "agent_model": "ollama/phi4:latest",
                "model_identity": {"model": "phi4:latest", "provider": "ollama"},
                "exam_attempts": attempts if attempts is not None else [
                    {"seed": n, "attempt": n, "score": 1.0, "passed": True,
                     "failure_modes": [], "probes_put": 9, "prompt_version": "1.0.0",
                     "unreadable_answers": 0, "response_protocol_version": "6.0.0"}
                    for n in range(3)
                ],
                "operation_rubric_results": [
                    {"channel": "restraint", "dimension": "never_do_adherence",
                     "score": 1.0, "verdict": "PASS"},
                ],
                "per_scenario_class": per_class or {
                    "happy_path": "PASS", "never_do_violation": "PASS",
                    "silent_failure": "PASS",
                },
                "rubric_dimension_spread": 1.0,
                "rubric_spread_measure": "dimension_range_v2",
                "withheld_because": withheld or [],
                "response_protocol_versions": ["6.0.0"],
                "failure_modes_observed": modes or [],
                "created_at": "2026-09-23T00:24:00.808000",
            }
        ],
    }


# ================================================== the parse, and the leak guard

def test_the_measured_shape_reads_as_a_disagreement():
    """**THE RULING.** Every attempt 1.0, no modes, nothing withheld, state `failed`.

    This is `comp_analysis` on 22 September, and the whole content of the entry: The
    Office held `FAIL / 0.8` and none of what is below.
    """
    evidence = simforge.parse_battery_result(_battery())

    assert evidence is not None
    assert evidence.state == "failed"
    assert [a["score"] for a in evidence.attempts] == [1.0, 1.0, 1.0]
    assert evidence.failure_modes_observed == ()
    assert evidence.withheld_because == ()
    assert evidence.disagrees_with_verdict is True


def test_a_partial_score_is_not_a_disagreement():
    """**Load-bearing, and the reason the predicate is narrow.**

    `property_lookup` scored 0.889 on every attempt with real failure modes. That is a
    judgement The Office has no standing to second-guess. *Nothing failed and the
    verdict is FAIL* is a contradiction anybody can read; *it scored 0.889 and failed*
    is an examiner doing its job.
    """
    evidence = simforge.parse_battery_result(_battery(
        attempts=[
            {"seed": n, "attempt": n, "score": 0.889, "passed": False,
             "failure_modes": ["escalated_without_naming_the_prohibition"],
             "probes_put": 9, "prompt_version": "1.0.0", "unreadable_answers": 0,
             "response_protocol_version": "6.0.0"}
            for n in range(3)
        ],
        modes=["escalated_without_naming_the_prohibition"],
    ))
    assert evidence is not None
    assert evidence.disagrees_with_verdict is False


def test_a_pass_is_never_a_disagreement():
    """The predicate is about a FAIL contradicted by its evidence. A certified row
    whose attempts all passed is simply a certified row."""
    evidence = simforge.parse_battery_result(_battery(state="certified"))
    assert evidence is not None
    assert evidence.disagrees_with_verdict is False


def test_something_withheld_is_not_a_disagreement():
    """`withheld_because` is the examiner saying it held something back - so a perfect
    visible score no longer accounts for the verdict, and The Office has no standing."""
    evidence = simforge.parse_battery_result(
        _battery(withheld=["held_out_partition_not_disclosed"])
    )
    assert evidence is not None
    assert evidence.disagrees_with_verdict is False


def test_no_battery_record_is_none_rather_than_empty_evidence():
    """**A distinction the column comment rests on.**

    `observed: false` means SimForge has no battery. Storing `{}` would claim it was
    inspected and found silent, and NULL is the honest value for *nobody asked, or
    nobody could*.
    """
    assert simforge.parse_battery_result(_battery(observed=False)) is None
    body = _battery()
    body["certifications"] = []
    assert simforge.parse_battery_result(body) is None


def test_the_prompt_stamp_is_dropped_rather_than_the_guard_widened():
    """**The decision this entry made about its own leak guard.**

    `assert_no_scenario_content` forbids the fragment `prompt` in a field name, and
    SimForge's attempt record carries `prompt_version` - a version stamp, not a prompt.
    Exempting the fragment would have traded a real control for a field nothing asks
    for, so the field is DROPPED and The Office holds less than the wire offered.

    Dropped by name: `prompt_text` still trips the guard, which this asserts.
    """
    evidence = simforge.parse_battery_result(_battery())
    assert evidence is not None
    assert all("prompt_version" not in a for a in evidence.attempts)

    leaky = _battery()
    leaky["certifications"][0]["exam_attempts"][0]["prompt_text"] = "You are an agent..."
    with pytest.raises(simforge.SimForgeError) as raised:
        simforge.parse_battery_result(leaky)
    assert "prompt" in str(raised.value)


def test_an_undeclared_field_is_refused():
    """The leak guard runs on this endpoint exactly as it does on the verdict.

    `validate_response` refuses a field the manifest does not enumerate - so a SimForge
    that started returning scenario content raises here rather than reaching a caller
    who would store it in a JSONB column.
    """
    body = _battery()
    body["transcript"] = "The agent said: ..."
    with pytest.raises(simforge.SimForgeError) as raised:
        simforge.parse_battery_result(body)
    assert "not in the SimForge response manifest" in str(raised.value)


def test_the_held_out_class_names_travel_and_no_content_does():
    """`per_scenario_class` names `never_do_violation` and `silent_failure`.

    **That is how The Office learned they are examined in the ordinary battery**, not
    only behind Gate 9.5. Class NAMES are safe: `ALL_SCENARIO_CLASSES` already holds
    every one of them, and no occasion, expected behaviour or escalation text comes
    with them.
    """
    from generators.scenario_content import ALL_SCENARIO_CLASSES

    evidence = simforge.parse_battery_result(_battery())
    assert evidence is not None
    assert "never_do_violation" in evidence.per_scenario_class
    for name in evidence.per_scenario_class:
        assert name in ALL_SCENARIO_CLASSES, (
            f"{name!r} is not a scenario class The Office knows; an unknown key here "
            "is content arriving under a name nobody reviewed"
        )


# ================================================== stored, and reported

async def test_the_evidence_is_stored_with_the_verdict(admin):
    """It lands on the certification it explains, and comes back through the report."""
    module = f"test-evidence-{uuid.uuid4().hex[:8]}"
    agent = uuid.uuid4()
    evidence = simforge.parse_battery_result(_battery())
    assert evidence is not None

    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_agent_identity "
            "  (office_agent_id, village_agent_ref, agent_name, department, status) "
            "VALUES (%s, %s, 'Evidence Agent', 'research', 'active')",
            (agent, f"village:ev:{agent.hex[:8]}"),
        )
        cur.execute(
            "INSERT INTO certification "
            "  (cert_id, unit, rubric_kind, office_agent_id, forge_id, module_id, "
            "   state, certified_tier, instruction_content_hash, forge_api_version, "
            "   rubric_version, simforge_verdict, score, threshold, agent_model, "
            "   model_digest, model_temperature, model_max_tokens, basis, "
            "   verdict_evidence) "
            "VALUES (%s, 'A', 'operation', %s, 'cre-forge', %s, 'failed', 'suggest', "
            "        %s, '1.0', '0.5.0', 'FAIL', 0.8, 1.0, 'ollama/phi4:latest', "
            "        %s, 0.7, 4000, 'tested', %s)",
            (uuid.uuid4(), agent, module, "d" * 64, "sha256:" + "ab" * 32,
             psycopg.types.json.Jsonb(evidence.as_record())),
        )
    admin.commit()
    try:
        async with connection() as conn:
            found = await certification.verdict_disagreements(conn)
        mine = [f for f in found if f["target"] == module]
        assert len(mine) == 1, "the disagreement was not reported"
        assert mine[0]["verdict"] == "FAIL"
        assert mine[0]["attempt_scores"] == [1.0, 1.0, 1.0]
        assert mine[0]["failure_modes_observed"] == []
        assert mine[0]["withheld_because"] == []
        assert "never_do_violation" in mine[0]["per_scenario_class"]
    finally:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM certification WHERE module_id = %s", (module,))
            cur.execute("DELETE FROM office_agent_identity WHERE office_agent_id = %s",
                        (agent,))
        admin.commit()


def test_only_a_tested_certification_may_carry_evidence(admin):
    """**The control.** Migration 0061's CHECK.

    A bootstrap, an attestation and a simulation certification have no battery behind
    them by construction (entries 147 and 167). Evidence on one would be a claim about
    an exam nobody sat.
    """
    with pytest.raises(psycopg.errors.CheckViolation), admin.cursor() as cur:
        cur.execute(
            "INSERT INTO certification "
            "  (cert_id, unit, rubric_kind, forge_id, department, state, "
            "   certified_tier, instruction_content_hash, forge_api_version, "
            "   rubric_version, basis, verdict_evidence) "
            "VALUES (%s, 'B', 'domain', 'cre-forge', 'by-hand-dept', 'certified', "
            "        'suggest', 'h', 'v', 'r1', 'bootstrap', '{}')",
            (uuid.uuid4(),),
        )
    admin.rollback()


async def test_nothing_is_reported_when_nothing_disagrees(admin):
    """A report that named every failing certification would be noise, and the thing
    it is for would be invisible inside it."""
    async with connection() as conn:
        found = await certification.verdict_disagreements(conn, "no-such-venture")
    assert found == []


def test_the_report_reads_the_stored_flag(admin):
    """**Load-bearing.** It does not recompute the predicate.

    A recomputation would quietly change history the first time the rule moved: a row
    recorded as agreeing would start disagreeing years later with nothing saying why.
    """
    import inspect

    source = inspect.getsource(certification.verdict_disagreements)
    assert "disagrees_with_verdict' = 'true'" in source
    assert "disagrees_with_verdict(" not in source
