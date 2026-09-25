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
from tests.conftest import declare_author, requires_db, undeclare_author
from tests.provisioning.conftest import VENTURE

pytestmark = [requires_db, pytest.mark.db]

#: Entry 162: a compliance entry names a real author, so this is an account now.
#: It used to be `00000000-...-00000000aaaa`, which resolves to nobody.
AUTHOR = uuid.UUID("00000000-0000-5000-8000-000000a17406")


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


async def test_gate_6_does_not_accept_another_ventures_entry_as_an_explanation(
    feasible_pack, operator, admin: psycopg.Connection
):
    """The tightening migration 0039 brings, stated as its own case.

    The flag query had no venture term while the table had no venture column, so ANY
    venture's entry explained ANY venture's flag - Greenstone's NV consent entry answered
    for Burkham's `recording_consent_required` and this gate passed on it. That is a gate
    reading a name rather than a library.

    The flag is moved rather than deleted, which is the difference from the test above:
    an entry explaining it still exists and is still complete - for somebody else.

    **The Pack's own ref stays where it is.** Moving the cited entry to another venture
    would fail V28 and block at Gate 2, and the run would never reach this gate - which
    is correct, and would test the wrong rule. So the venture's own entry keeps the ref
    and loses the flag, and a second venture's entry carries the flag.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE compliance_library_entry SET runtime_flag = NULL "
            "WHERE runtime_flag = 'tsr_disclosure_required'"
        )
        cur.execute(
            """
            INSERT INTO compliance_library_entry
              (venture_id, entry_ref, framework, jurisdiction, applicability_rule,
               agent_behavior_implication, escalation_trigger, citation, runtime_flag,
               authored_by)
            VALUES ('some-other-venture', 'test/their-tsr', 'FTC_TSR', ARRAY['FEDERAL'],
                    'Outbound cold calls.', 'State identity and purpose first.',
                    'A do-not-call assertion.', '16 CFR 310',
                    'tsr_disclosure_required', %s)
            """,
            (declare_author(admin, AUTHOR, "Gate 6 Test Author"),),
        )
    admin.commit()

    async with connection() as conn:
        _run_id, outcomes = await _to_gate_6(conn, operator, held_out=HeldOutPasses())

    gate_6 = next((o for o in outcomes if o.gate == "6"), None)
    assert gate_6 is not None, (
        "the run stopped before Gate 6: "
        + "; ".join(f"{o.gate} {o.verdict}" for o in outcomes)
    )
    assert gate_6.verdict == provisioning.BLOCKED
    assert "tsr_disclosure_required" in gate_6.reason
    assert gate_6.evidence["compliance_library"]["uncovered"] == [
        "tsr_disclosure_required"
    ]

    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM compliance_library_entry WHERE venture_id = 'some-other-venture'"
        )
    admin.commit()
    undeclare_author(admin, AUTHOR)


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
    # `instruction_versions` joined the list on 25 September 2026, entry 193: a run
    # refuses to hand over instruction text older than this repository's. It blocks for
    # the same reason the other two do - an exam set against a stale manual is graded,
    # recorded and worthless, and nothing else in the ladder can tell.
    assert gate_6.evidence["blocking"] == [
        "forge_operating_instructions", "compliance_library", "instruction_versions"
    ]
    # Nothing is stale in the prepared world, and nothing is silently skipped either:
    # the fixtures' rows carry no human author, so they are not compared at all and the
    # gate says so rather than reporting them current.
    assert gate_6.evidence["instruction_versions"]["stale"] == []



# ------------------------------------------------- instruction text older than the repo

async def test_gate_6_blocks_when_a_live_instruction_is_older_than_the_repository(
    feasible_pack, operator, admin: psycopg.Connection
):
    """Entry 193, and the run it was written for cost a whole exam.

    Manual versions 1.8.0 and 1.9.0 were merged and never authored. Gate 6 read v1.7.0,
    passed, Gate 8 minted the refs that text produces, `open_run` returned the rows
    already graded against it, and run a543ffa1 reported six exams opened having
    re-examined nothing. Every number was true.

    The row here is authored by a PERSON, because that is the distinction the gate
    draws: a prepared world's fixtures have no authoring script and are not compared.
    """
    from scripts.author_cre_forge_instructions import VERSION

    declare_author(admin, AUTHOR, "Stale Instruction Author")
    # THE LIVE ROW IS EDITED IN PLACE, not replaced. `instruction_has_all_sections` and
    # its siblings make a synthetic row a fight with four constraints that have nothing
    # to do with what is being tested, and the two columns this gate reads are the two
    # being set: the version, and an author the rule accepts.
    with admin.cursor() as cur:
        cur.execute(
            "SELECT instruction_version, authored_by FROM forge_operating_instruction "
            " WHERE forge_id = 'cre-forge' AND module_id = 'property_lookup' "
            "   AND superseded_at IS NULL"
        )
        before = cur.fetchone()
        cur.execute(
            "UPDATE forge_operating_instruction "
            "   SET instruction_version = '0.0.1-stale', authored_by = %s "
            " WHERE forge_id = 'cre-forge' AND module_id = 'property_lookup' "
            "   AND superseded_at IS NULL",
            (AUTHOR,),
        )
    admin.commit()
    try:
        async with connection() as conn:
            _run_id, outcomes = await _to_gate_6(
                conn, operator, held_out=HeldOutPasses()
            )
        gate_6 = next(o for o in outcomes if o.gate == "6")
        assert gate_6.verdict == "blocked", gate_6.reason
        assert "older than this repository" in gate_6.reason
        assert "cre-forge/property_lookup" in gate_6.reason
        # THE VERSIONS ARE NAMED, both of them. "Stale" alone sends a reader to two
        # files to find out which way round it is and by how far.
        assert "0.0.1-stale" in gate_6.reason
        assert VERSION in gate_6.reason
        stale = gate_6.evidence["instruction_versions"]["stale"]
        assert len(stale) == 1, stale
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "UPDATE forge_operating_instruction "
                "   SET instruction_version = %s, authored_by = %s "
                " WHERE forge_id = 'cre-forge' AND module_id = 'property_lookup' "
                "   AND superseded_at IS NULL",
                (before[0], before[1]),
            )
        admin.commit()
        undeclare_author(admin, AUTHOR)


async def test_a_forge_with_no_authoring_source_is_reported_not_skipped(
    feasible_pack, operator
):
    """The gap this check could have hidden in, named instead.

    `scripts/instruction_sources.uncovered` fails CI on a human-authored Forge with no
    deriver, and that is the control. This asserts the gate does not quietly agree that
    an uncomparable row is current - whatever it could not compare is listed.
    """
    async with connection() as conn:
        _run_id, outcomes = await _to_gate_6(conn, operator, held_out=HeldOutPasses())

    gate_6 = next(o for o in outcomes if o.gate == "6")
    versions = gate_6.evidence["instruction_versions"]
    assert set(versions) == {"stale", "not_compared"}
    assert isinstance(versions["not_compared"], list)


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
