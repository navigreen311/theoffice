"""A certification records which instruction sections its exam showed.

SimForge ADR-0112 publishes `instruction_sections` on each battery-result
certification: `{shown, required_by_keys, missing}`, section names only.
Until this, `verdict_evidence.instruction_sections` was absent on every
certification here - all six Greenstone exams - while SimForge had recorded
`missing: []` on all six.

`missing` is what says whether a 0.0 on a `failure_signatures` key is the
agent's fault or the submitter's omission.

ASSERT THE ROW, NOT THE RESPONSE
================================

    The ingest tests drive the real sweep, then read `verdict_evidence` back
    from the database on the admin connection - not from what the sweep or the
    parser returned. A gap, no gap and nothing-recorded must each land as
    themselves. An adapter that stored nothing, or a constant, fails at least
    two of the three.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from broker import simforge
from broker.simforge import SimForgeError
from tests.conftest import requires_db
from tests.contract.test_verdict_ingest import (  # noqa: F401 - fixtures
    FakeSimForge,
    _clean_sweep_runs,
    _gate_result,
    forge,
    run_sweep,
    world,
)

REQUIRED = ["correct_sequence", "failure_signatures", "inputs", "retry_vs_escalate"]
GAP = {
    "shown": ["correct_sequence", "inputs", "retry_vs_escalate"],
    "required_by_keys": REQUIRED,
    "missing": ["failure_signatures"],
}
WHOLE = {"shown": REQUIRED, "required_by_keys": REQUIRED, "missing": []}


def _battery(run_ref: str, sections: Any, *, include: bool = True) -> dict[str, Any]:
    """A battery-result body in SimForge's shape as of ADR-0112."""
    cert: dict[str, Any] = {
        "state": "failed",
        "operation_rubric_version": "0.5.0",
        "instruction_content_hash": "d" * 64,
        "agent_model": "ollama/llama3.1:8b",
        "exam_attempts": [{"seed": 0, "score": 0.0, "passed": False, "failure_modes": []}],
        "operation_rubric_results": [
            {"channel": "restraint", "dimension": "failure_recognition",
             "score": 0.0, "verdict": "FAIL"},
        ],
        "per_scenario_class": {"failure_signature": "FAIL"},
        "withheld_because": [],
        "failure_modes_observed": [],
        "created_at": "2026-09-23T00:24:00",
    }
    if include:
        cert["instruction_sections"] = sections
    return {
        "run_ref": run_ref, "unit": "A", "forge_id": "cre-forge",
        "module_id": "parse_document", "agent_id": str(uuid.uuid4()),
        "observed": True, "certifications": [cert],
        "join": "natural_key(forge_id, module_id, agent_id) bounded by run.startedAt",
    }


# ================================================== the parse

@pytest.mark.parametrize("sections", [GAP, WHOLE])
def test_the_three_lists_arrive_distinct(sections):
    evidence = simforge.parse_battery_result(_battery("r", sections))
    assert evidence is not None
    assert evidence.instruction_sections == sections
    assert evidence.as_record()["instruction_sections"] == sections


def test_a_gap_and_no_gap_are_different_facts():
    gap = simforge.parse_battery_result(_battery("r", GAP))
    whole = simforge.parse_battery_result(_battery("r", WHOLE))
    assert gap is not None and whole is not None
    assert gap.instruction_sections != whole.instruction_sections


@pytest.mark.parametrize("include", [True, False])
def test_nothing_recorded_is_none_not_an_empty_gap(include):
    """Null on the wire, or a SimForge before ADR-0112. Neither is `missing: []`."""
    evidence = simforge.parse_battery_result(_battery("r", None, include=include))
    assert evidence is not None
    assert evidence.instruction_sections is None


@pytest.mark.parametrize(
    "bad",
    [
        True,
        {"missing": ["inputs"]},
        {**GAP, "text": ["x"]},
        {**GAP, "missing": "failure_signatures"},
        {**GAP, "missing": [1]},
    ],
    ids=["boolean", "one-field", "fourth-field", "string-not-list", "non-name"],
)
def test_a_shape_nobody_agreed_is_refused_not_coerced(bad):
    """A guess about another system's response reads as that system's silence."""
    with pytest.raises(SimForgeError, match="ADR-0112"):
        simforge.parse_battery_result(_battery("r", bad))


def test_it_passes_the_content_guard_unchanged():
    """No exemption: `echoed` is None, as `parse_battery_result` calls it."""
    for sections in (GAP, WHOLE, None):
        simforge.assert_no_scenario_content(
            "get_battery_result", _battery("r", sections), echoed=None
        )


# ================================================== the row


class _WithEvidence(FakeSimForge):
    """The verdict read, plus a battery read that goes through the real parser."""

    def __init__(self, verdicts, bodies: dict[str, dict[str, Any]]) -> None:
        super().__init__(verdicts)
        self.bodies = bodies

    async def read_battery_result(self, conn, run_ref):
        return simforge.parse_battery_result(self.bodies[run_ref])


def _stored(admin: psycopg.Connection, agent_id: uuid.UUID) -> dict[str, Any]:
    """`verdict_evidence` as the database holds it. Not what anything returned."""
    admin.rollback()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT verdict_evidence FROM certification "
            "WHERE unit = 'A' AND office_agent_id = %s",
            (agent_id,),
        )
        rows = cur.fetchall()
    assert len(rows) == 1, f"expected one certification row, found {len(rows)}"
    evidence = rows[0][0]
    assert evidence is not None, "the sweep stored no evidence at all"
    return evidence


@requires_db
@pytest.mark.db
@pytest.mark.parametrize(
    ("sections", "stored_missing"),
    [(GAP, ["failure_signatures"]), (WHOLE, []), (None, None)],
    ids=["gap", "no-gap", "nothing-recorded"],
)
async def test_the_ingest_stores_what_simforge_recorded(
    admin, world, sections, stored_missing  # noqa: F811
):
    ref = world["run_ref"]
    client = _WithEvidence(
        {ref: _gate_result("FAIL", run_ref=ref)}, {ref: _battery(ref, sections)}
    )

    result = await run_sweep(client)
    assert result.findings["ingested"] == 1
    assert not result.findings.get("evidence_unreadable")

    stored = _stored(admin, world["agent_id"])
    assert "instruction_sections" in stored
    if stored_missing is None:
        assert stored["instruction_sections"] is None
    else:
        assert stored["instruction_sections"] == sections
        assert stored["instruction_sections"]["missing"] == stored_missing


@requires_db
@pytest.mark.db
async def test_a_refused_shape_costs_the_evidence_and_says_so_not_the_verdict(
    admin, world  # noqa: F811
):
    """The verdict still lands. The unreadable evidence is a named finding."""
    ref = world["run_ref"]
    client = _WithEvidence(
        {ref: _gate_result("FAIL", run_ref=ref)}, {ref: _battery(ref, True)}
    )

    result = await run_sweep(client)

    assert result.findings["ingested"] == 1
    [note] = result.findings["evidence_unreadable"]
    assert "ADR-0112" in note["reason"]
    admin.rollback()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT verdict_evidence FROM certification "
            "WHERE unit = 'A' AND office_agent_id = %s",
            (world["agent_id"],),
        )
        assert cur.fetchone()[0] is None
