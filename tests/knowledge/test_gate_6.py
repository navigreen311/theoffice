"""K10-K13 - Gate 6 counting, and the two knowledge bases that block.

Gate 6 used to carry a hardcoded list of the four knowledge bases that did not exist.
That was accurate the day it was written and would have been a lie the day after they
were built: it would have gone on reporting them missing while a venture provisioned
against a library it was being told was absent. A hardcoded list is right exactly once.

The other half of this file is that a store nobody writes to is Phase 4.1's inert
control wearing a knowledge base's name. Historical records get their writer here, and
these tests are the proof it runs.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import knowledge, provisioning
from broker.db import connection
from tests.conftest import requires_db
from tests.provisioning.conftest import VENTURE

pytestmark = [requires_db, pytest.mark.db]

AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


class HeldOutPasses:
    async def verdict(self, venture_id: str) -> str | None:
        return "PASS"


async def _to_gate_6(conn, operator, *, held_out=None):
    """Advance a run until it is past Gate 5, so Gate 6 has grants to reason about."""
    run_id = await provisioning.start_run(
        conn, venture_id=VENTURE, started_by=operator.human_id
    )
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    await provisioning.record_human_review(
        conn, run_id=run_id, human=operator, note="reviewed"
    )
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, held_out=held_out
    )
    return run_id, outcomes


async def test_gate_6_reports_real_counts_with_denominators(feasible_pack, operator):
    """K12 - five stores, each with what it covered of how many.

    "Report the denominator. No green check without a coverage count." A gate that said
    "knowledge bases seeded" and nothing else would be a green check over five stores
    of unknown depth.
    """
    async with connection() as conn:
        _run_id, outcomes = await _to_gate_6(conn, operator, held_out=HeldOutPasses())

    gate_6 = next(o for o in outcomes if o.gate == "6")
    assert gate_6.verdict == provisioning.PASSED, gate_6.reason

    evidence = gate_6.evidence
    for store in (
        "forge_operating_instructions",
        "compliance_library",
        "business_playbooks",
        "persona_library",
    ):
        assert store in evidence, f"{store} is not reported at all"
        assert "denominator" in evidence[store], f"{store} reports no denominator"
        assert "uncovered" in evidence[store], f"{store} does not name what is missing"

    assert evidence["forge_operating_instructions"]["denominator"] > 0
    assert evidence["compliance_library"]["denominator"] > 0
    assert "historical_records" in evidence

    # Playbooks and personas are genuinely empty in this world, and the gate says so
    # rather than passing over them or blocking on them.
    assert evidence["business_playbooks"]["covered"] == 0
    assert evidence["business_playbooks"]["uncovered"], "the missing stages are named"
    assert "Advisory" in gate_6.reason


async def test_gate_6_no_longer_claims_the_built_stores_are_missing(
    feasible_pack, operator
):
    """The regression the hardcoded list would have become.

    It named business_playbooks, compliance_library, persona_library and
    historical_records as `knowledge_bases_missing`. All four exist now.
    """
    async with connection() as conn:
        _run_id, outcomes = await _to_gate_6(conn, operator, held_out=HeldOutPasses())

    gate_6 = next(o for o in outcomes if o.gate == "6")
    assert "knowledge_bases_missing" not in gate_6.evidence
    assert "1 of 5 knowledge bases" not in gate_6.reason


async def test_gate_6_blocks_a_compliance_flag_with_no_library_entry(
    feasible_pack, operator, admin: psycopg.Connection
):
    """K13 - the second blocking condition, and the reason it blocks.

    An agent carrying a flag the library cannot explain has no behavioural implication
    and no escalation trigger to act on. The flag is then a label on a task rather than
    a constraint on behaviour, which is worse than no flag: it reads like coverage.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE compliance_library_entry SET runtime_flag = NULL "
            "WHERE runtime_flag = 'tsr_disclosure_required'"
        )
    admin.commit()

    async with connection() as conn:
        _run_id, outcomes = await _to_gate_6(conn, operator, held_out=HeldOutPasses())

    gate_6 = next(o for o in outcomes if o.gate == "6")
    assert gate_6.verdict == provisioning.BLOCKED
    assert "tsr_disclosure_required" in gate_6.reason
    assert "no behavioural implication" in gate_6.reason
    assert gate_6.evidence["compliance_library"]["uncovered"] == [
        "tsr_disclosure_required"
    ]
    assert "7" not in {o.gate for o in outcomes}, "a blocked gate stops the run"


async def test_gate_6_blocking_conditions_are_named_in_its_evidence(
    feasible_pack, operator
):
    """Which stores block is a decision, so it is on the record rather than in a doc.

    A venture can operate without an SOP written down. It cannot operate under a
    compliance flag nobody has defined. Saying which is which is most of what this gate
    is for, and an operator reading a passed gate with three empty stores needs to see
    that the emptiness was considered.
    """
    async with connection() as conn:
        _run_id, outcomes = await _to_gate_6(conn, operator, held_out=HeldOutPasses())

    gate_6 = next(o for o in outcomes if o.gate == "6")
    assert gate_6.evidence["blocking"] == [
        "forge_operating_instructions", "compliance_library"
    ]


# ------------------------------------------------------- the historical writer

async def test_a_completed_run_writes_a_historical_record(
    feasible_pack, operator, signer, admin: psycopg.Connection
):
    """K10 - the store has a writer on day one.

    Phase 4.1 shipped three controls that were fully tested and completely inert because
    nothing ran them. A knowledge base nothing writes to is the same mistake with a
    better name, and it would be invisible for exactly as long.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed"
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        gate_10 = next(o for o in outcomes if o.gate == "10")
        from broker import humans

        await humans.sign_off(
            conn, gate="gate_10", venture_id=VENTURE, human=signer,
            artifact_kind="provisioning_artifacts",
            artifact_hash_value=gate_10.evidence["artifacts_hash"],
        )
        await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        records = await knowledge.history(conn, venture_id=VENTURE)

    provisioned = [r for r in records if r["record_type"] == "venture_provisioned"]
    assert len(provisioned) == 1
    assert VENTURE in provisioned[0]["summary"]
    assert provisioned[0]["detail"]["run_id"] == str(run_id)
    assert provisioned[0]["actor_type"] == "human"
    assert provisioned[0]["recorded_by"] == operator.human_id


async def test_an_abandoned_run_records_what_stopped_it_and_where(
    feasible_pack, operator
):
    """K11 - arguably the more useful record of the two.

    The next person to provision this venture wants to know what stopped the last
    attempt and at which gate. A history that only kept the successes would answer the
    question nobody has.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.abort_run(
            conn, run_id=run_id, human=operator,
            reason="the capacity amendment is still being decided",
        )
        records = await knowledge.history(conn, venture_id=VENTURE)

    abandoned = [r for r in records if r["record_type"] == "provisioning_abandoned"]
    assert len(abandoned) == 1
    assert "gate 4" in abandoned[0]["summary"]
    assert "capacity amendment" in abandoned[0]["summary"]
    assert abandoned[0]["detail"]["at_gate"] == "4"
