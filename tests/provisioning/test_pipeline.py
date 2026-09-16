"""P3-P15 - the provisioning pipeline.

These tests exist because the increment's whole point is a control that is easy to ship
inert: `activated_at` is a column, `is_assignable` is a generated boolean, and both
would look completely correct in review while doing nothing, because nothing would ever
write NULL to one or read the other. So the assertions here are deliberately about
*consequences* rather than flags - a grant Gate 5 issued is refused by `resolve_grant`,
not merely reported as inactive.

The other recurring shape: **a verdict that is not a pass is not a failure either**.
Gate 4 waits, Gate 9 blocks, and neither is allowed to quietly become the other.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
import yaml

from broker import humans, packs, provisioning, revocation
from broker.db import connection
from broker.errors import GrantNotActivated
from broker.grants import resolve_grant
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


class HeldOutPasses:
    """Stands in for the SimForge partition that Phase 2 will stand up."""

    async def verdict(self, venture_id: str) -> str | None:
        return "PASS"


class HeldOutSays:
    """Any other verdict. `NOT_RUN` is the interesting one."""

    def __init__(self, value: str) -> None:
        self.value = value

    async def verdict(self, venture_id: str) -> str | None:
        return self.value


async def _drive(conn, run_id, actor, *, held_out=None, passes=1):
    outcomes = []
    for _ in range(passes):
        outcomes.extend(
            await provisioning.advance(
                conn, run_id=run_id, actor=actor, held_out=held_out
            )
        )
    return outcomes


def _verdicts(outcomes) -> dict[str, str]:
    return {o.gate: o.verdict for o in outcomes}


async def _to_gate_10(conn, operator, signer, *, held_out=None):
    """Everything up to and including a valid Gate 10 signature. Returns the run id."""
    run_id = await provisioning.start_run(
        conn, venture_id=VENTURE, started_by=operator.human_id
    )
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    await provisioning.record_human_review(
        conn, run_id=run_id, human=operator, note="reviewed the BOM and the gap report"
    )
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=held_out or HeldOutPasses(),
    )
    gate_10 = next(o for o in outcomes if o.gate == "10")
    await humans.sign_off(
        conn, gate="gate_10", venture_id=VENTURE, human=signer,
        artifact_kind="provisioning_artifacts",
        artifact_hash_value=gate_10.evidence["artifacts_hash"],
        note="artifacts reviewed and signed",
    )
    return run_id


# ------------------------------------------------------------------ the machine

async def test_a_run_stops_at_the_first_blocking_gate_and_names_it(
    stored_pack, operator
):
    """P3 - a state machine, not a script.

    This is the real Greenstone Pack. **It used to block at 4.5 and no longer does**, so
    the first blocking gate is now 9.5, the deployment ceiling - the run gets there because
    nothing before it refuses, which is the state this venture has never been in.

    The capacity finding that used to stop it was real and is not being waved away; it was
    computed from a constant. The comment below is that number's whole history and the last
    line of it is where it went.
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
            conn, run_id=run_id, actor=operator.human_id
        )
        state = await provisioning.get_run(conn, run_id)

        blocking = outcomes[-1]
        assert blocking.gate == "9.5"
        assert blocking.verdict == provisioning.BLOCKED
        # 192, and it has been here before. It was 192 until 2026-09-02, when cutting
        # `generate_loi` removed the workflow step that operated it - one fewer step
        # is 32 fewer approvals a day, so it fell to 160. Binding `assign_contract` on
        # 2026-09-06 restored the step, and the figure with it.
        #
        # The difference is what stands behind the number. In August it counted a step
        # operated by a module that did not exist; now it counts one the Forge
        # dispatches. The gate blocks either way, which is why the fall to 160 was not
        # an improvement and this rise is not a regression: the review load was always
        # going to be real once the work was.
        #
        # 160 again from 2026-09-15, for a different reason (decisions entries 73 and
        # 83). `voiceforge/place_call` left the Pack: it is forbidden in
        # forge_module_exclusion, so no agent could ever hold it, and its 32 approvals
        # a day were review demand for work that can never happen. Unlike September 2,
        # nothing real was removed. The gate still blocks - the reviewer was Dana, who
        # does not exist (entry 59) - so this is still not an improvement. Since entry 92
        # the reviewer is Ira Green, real, at two hours and ten minutes, and the same 128
        # approvals are eighteen times what she can review rather than five.
        #
        # 128 later the same day (entry 87): the VoiceForge binding went, and with it
        # `transcribe_call`'s steps. Nothing served that module either, so again no
        # capability left - only demand for one. Still blocks.
        #
        # 64 TO THIS REVIEWER from entry 105, and the total did not move. The five CRE
        # Forge modules stopped implying `tsr_disclosure_required` - a flag the
        # development fixture wrote one-per-Forge onto modules that contact nobody - so
        # Deal Underwriter, which declares no flag of its own, stopped routing to the
        # compliance officer. Its 64 went to the venture operator. **Nothing about the
        # work changed; what changed is that the routing now follows what the modules
        # do.** Both roles were over, which is why the fixture that made the later gates
        # reachable topped up both.
        #
        # 0.2 A DAY FROM 2026-09-16, AND GATE 4.5 STOPPED BLOCKING. Three changes, and
        # none of them cut scope:
        #
        #   the volume is declared    `expected_weekly_volume` replaced the constant 8.
        #                             Greenstone closes about one deal a week, so
        #                             `assign_contract` runs once a week - 0.2 a day over
        #                             five operating days - and that is the only module
        #                             below auto_execute left.
        #   one step per module       the workflow emitted every module once per stage its
        #                             position owned. Twelve steps became six.
        #   two positions left        `buyer_match` is auto_execute (non-mutating, no human
        #                             required) and Deal Underwriter is pending activation,
        #                             so its share is founder hours rather than an approval
        #                             queue.
        #
        # **Every figure above was a multiple of 8 and none of them was measured.** The
        # sequence 192, 160, 128, 64 tracked steps being added and removed; it never
        # tracked the venture. 0.2 is the first of these numbers that came from the
        # business rather than from a count of rows times a constant.
        #
        # The run now reaches 9.5, the deployment ceiling, which is where a run stops
        # because the deployment says so rather than because the venture is unready.
        # And 9.5 blocks for its own reason, which is not a capacity one: the held-out
        # adversarial partition does not exist. SimForge owns it outright and The Office
        # has no read path to it by construction, so no run started here can pass this
        # gate today - which is the deployment ceiling the console already names.
        assert blocking.evidence["blocked_by"] == "held_out_partition_not_created"
        assert "held-out adversarial partition" in blocking.reason
        assert state is not None
        assert state.status == "blocked"
        assert state.current_gate == "9.5"

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM agent_forge_grant WHERE venture_id = %s",
                (VENTURE,),
            )
            row = await cur.fetchone()
    # GATE 5 DOES RUN NOW, AND ISSUING GRANTS HERE IS NOT A HOLE.
    #
    # This asserted zero grants while the run stopped at 4.5, and the reason given was that
    # a blocked gate must not let the next one issue grants. That is still true and it is
    # still enforced - by `test_gate_5_issues_grants_inactive` and by Gate 11, which
    # activates nothing without a valid signature. What changed is that 4.5 no longer
    # blocks, so Gate 5 is reached legitimately and the grants it writes are INACTIVE.
    #
    # Asserting they exist and are all inactive is the stronger claim: zero grants would
    # also be satisfied by a Gate 5 that silently did nothing.
    assert row is not None and row[0] > 0, "Gate 5 was reached and must have issued grants"
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM agent_forge_grant "
            "WHERE venture_id = %s AND activated_at IS NOT NULL",
            (VENTURE,),
        )
        active = await cur.fetchone()
    assert active is not None and active[0] == 0, (
        "a grant was activated before Gate 11 signed for it"
    )


async def test_gates_run_in_order_and_none_is_skipped(feasible_pack, operator, signer):
    """P4 - the recorded sequence is the declared sequence, with nothing missing.

    Gate 5 issues grants and Gate 2 is the validator. A run that could jump would issue
    grants for a Pack nobody validated, so ordering here is a safety property rather
    than a tidiness one.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id,
                                   held_out=HeldOutPasses())
        results = await provisioning.gate_results(conn, run_id)

    # Gate 3 legitimately appears more than once: every pass regenerates the artifacts
    # rather than trusting a stored copy, so what is signed is what is provisioned.
    first_seen: list[str] = []
    for r in results:
        if r["gate"] not in first_seen:
            first_seen.append(r["gate"])

    assert first_seen == list(provisioning.GATE_SEQUENCE), (
        "every gate ran, in order, exactly once as a first occurrence"
    )


async def test_a_pack_with_a_validator_failure_never_reaches_the_generators(
    world, operator, pack_yaml
):
    """P5 - Gate 2 blocks on a FAIL, and Gate 3 does not run.

    Removing the compliance officer breaks V14 (critical roles need a backup human).
    The point is not which rule fires; it is that the run stops with the rule named.
    """
    # Remove the COMPLIANCE OFFICER's backup, found by role rather than by name. This was
    # `replace("    backup_human: Ivan\n", "")`, which breaks the Pack only while that
    # entry happens to name Ivan - and the founder rename (entry 103) changes the
    # spelling. A no-op replace leaves the Pack VALID, V14 never fires, and the failure
    # lands on the assertion below saying nothing about why: the mutation would have
    # stopped working, not the rule.
    #
    # Rewritten through YAML rather than by line, because the first line-based attempt
    # removed the venture operator's backup - V14 only checks CRITICAL roles, so the Pack
    # stayed valid and Gate 2 passed. Which entry loses its backup is the whole mutation.
    doc = yaml.safe_load(pack_yaml)
    officer = next(
        h for h in doc["human_capacity"] if h["role"] == "compliance_officer"
    )
    assert officer.pop("backup_human", None), "the officer had no backup to remove"
    broken = yaml.safe_dump(doc, sort_keys=False)
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=broken, pack_version="0.9.0",
            authored_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id
        )

    verdicts = _verdicts(outcomes)
    assert verdicts["2"] == provisioning.BLOCKED
    assert "3" not in verdicts, "the generators must not run against an invalid Pack"
    blocking = outcomes[-1]
    assert "V14" in blocking.reason
    assert blocking.evidence["failures"], "the gate must name which rules failed"


# ------------------------------------------------------------- the human gates

async def test_gate_4_waits_it_does_not_pass(feasible_pack, operator):
    """P6 - the core rule.

    A pipeline that auto-advances through a human review gate is a pipeline without
    human review, and the tell is that it still *reports* having one. `awaiting_human`
    is a third verdict for the same reason `NOT_RUN` is a third verdict everywhere else.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id
        )
        state = await provisioning.get_run(conn, run_id)

    gate_4 = outcomes[-1]
    assert gate_4.gate == "4"
    assert gate_4.verdict == provisioning.AWAITING_HUMAN
    assert gate_4.verdict != provisioning.PASSED
    assert gate_4.verdict != provisioning.BLOCKED
    assert not gate_4.advances, "waiting is not advancing"
    assert state is not None and state.status == "awaiting_human", (
        "the run status must distinguish waiting from blocked; an operator who is told "
        "'blocked' goes looking for a defect instead of reading the artifacts"
    )
    assert gate_4.evidence["artifacts_hash"], "review is of specific artifacts"
    assert "capacity" in gate_4.evidence


async def test_recording_a_review_advances_past_gate_4(feasible_pack, operator):
    """P7 - and the review is by a named human with a note."""
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="checked the appointment gaps"
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        results = await provisioning.gate_results(conn, run_id)

    assert _verdicts(outcomes)["4"] == provisioning.PASSED
    review = next(
        r for r in results if r["gate"] == "4" and "checked the appointment gaps"
        in r["reason"]
    )
    assert review["evidence"]["human_id"] == str(operator.human_id)
    assert operator.display_name in review["reason"]


async def test_a_review_with_no_note_is_not_a_review(feasible_pack, operator):
    """"Reviewed" with nothing attached is a checkbox.

    Gate 4 exists so that somebody looked at the bill of materials and the appointment
    gap report. A note is the cheapest evidence that they did.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        with pytest.raises(provisioning.ProvisioningError) as exc:
            await provisioning.record_human_review(
                conn, run_id=run_id, human=operator, note="   "
            )
    assert "requires a note" in str(exc.value)


async def test_a_human_from_another_venture_cannot_record_the_review(
    feasible_pack, operator
):
    """Role scoping, not role rank. Part 14."""
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Wrong Venture", email="wrong@provisioning.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id="burkham",
            granted_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )
        outsider = await humans.authenticate(conn, token)
        assert outsider is not None

        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        with pytest.raises(Exception) as exc:
            await provisioning.record_human_review(
                conn, run_id=run_id, human=outsider, note="not my venture"
            )
    assert "venture" in str(exc.value).lower()


# ------------------------------------------------------ certification gates

async def test_gates_9_and_9_5_block_they_are_never_skipped(feasible_pack, operator):
    """P8 - in this deployment the run stops at 9.5, and says the partition is absent.

    Not skipped, and not passed. A run that skipped certification would produce a
    venture that reads as fully provisioned and has been certified for nothing, which
    is the state Gate 0 exists to prevent one link earlier in the same chain.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed"
        )
        # No `held_out` argument: the default is the truth about this deployment.
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id
        )
        state = await provisioning.get_run(conn, run_id)

    verdicts = _verdicts(outcomes)
    assert verdicts["9"] == provisioning.PASSED, (
        "Gate 9 reads the certification record, and this world is certified"
    )
    assert verdicts["9.5"] == provisioning.BLOCKED
    assert "10" not in verdicts, "a blocked gate does not let the next one run"
    assert state is not None and state.status == "blocked"
    assert state.current_gate == "9.5"


async def test_an_uncertified_roster_blocks_gate_9_by_state_not_by_guess(
    feasible_pack, operator, admin: psycopg.Connection
):
    """Gate 9 names *which* state, and never collapses the seven into two.

    An agent nobody trained and an agent whose training no longer describes the module
    need different responses, and a gate that reports both as "not certified" sends
    whoever reads it to the wrong fix.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed"
        )
        # Advance to Gate 8 so the grants exist, then stale one Unit A certification.
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE certification SET state = 'stale_instructions' "
            "WHERE unit = 'A' AND cert_id = (SELECT operation_cert_ref::uuid "
            "  FROM agent_forge_grant WHERE venture_id = %s "
            "  AND operation_cert_ref IS NOT NULL ORDER BY grant_id LIMIT 1)",
            (VENTURE,),
        )
    admin.commit()

    async with connection() as conn:
        # A second run against the same Pack re-reaches Gate 9 with the new state.
        await _set_run_gate(conn, run_id, "9")
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )

    gate_9 = next(o for o in outcomes if o.gate == "9")
    assert gate_9.verdict == provisioning.BLOCKED
    assert "stale_instructions" in gate_9.reason
    assert gate_9.evidence["states"]["stale_instructions"] == 1
    assert gate_9.evidence["not_certified"][0]["state"] == "stale_instructions"


@pytest.mark.parametrize("verdict", ["FAIL", "NOT_RUN", "TIMEOUT", "IN_PROGRESS"])
async def test_a_held_out_verdict_that_is_not_pass_blocks_and_is_named(
    feasible_pack, operator, verdict
):
    """`NOT_RUN` is not a pass and `TIMEOUT` is not a failure. Both block, both by name."""
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed"
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutSays(verdict)
        )

    gate = next(o for o in outcomes if o.gate == "9.5")
    assert gate.verdict == provisioning.BLOCKED
    assert verdict in gate.reason
    assert gate.evidence["verdict"] == verdict


# ------------------------------------------------------ grants and activation

async def test_gate_5_issues_grants_inactive(feasible_pack, operator):
    """P9 - "sandbox provisioning" that handed out live authority is production."""
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed"
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id
        )

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*), count(activated_at), count(*) FILTER (WHERE is_assignable) "
                "FROM agent_forge_grant WHERE venture_id = %s", (VENTURE,)
            )
            row = await cur.fetchone()

    gate_5 = next(o for o in outcomes if o.gate == "5")
    assert gate_5.verdict == provisioning.PASSED
    assert gate_5.evidence["grants_active"] is False
    assert row is not None
    total, activated, assignable = row
    assert total > 0
    assert activated == 0, "Gate 5 issues grants inactive"
    assert assignable == 0, "and an inactive grant is not assignable"

    gate_7 = next(o for o in outcomes if o.gate == "7")
    assert gate_7.evidence["already_active"] == 0


async def test_the_call_path_refuses_an_inactive_grant(feasible_pack, operator):
    """P10 - the control, not the flag.

    `is_assignable` being false proves nothing on its own: the previous version of this
    column was a generated boolean that no code read, so adding a term to it changed
    exactly nothing at runtime. This asserts the consequence instead - the resolver a
    real call goes through refuses, by a named refusal type.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed"
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT office_agent_id, forge_id, module_id FROM agent_forge_grant "
                "WHERE venture_id = %s ORDER BY grant_id LIMIT 1", (VENTURE,)
            )
            grant = await cur.fetchone()
        assert grant is not None

        with pytest.raises(GrantNotActivated) as exc:
            await resolve_grant(
                conn, office_agent_id=grant[0], forge_id=grant[1],
                module_id=grant[2], venture_id=VENTURE,
            )

    assert "provisioning" in str(exc.value)
    assert exc.value.context["venture_id"] == VENTURE


async def test_gate_11_refuses_without_a_signature(feasible_pack, operator):
    """P11 - and the run does not reach Gate 12."""
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
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(activated_at) FROM agent_forge_grant WHERE venture_id = %s",
                (VENTURE,),
            )
            row = await cur.fetchone()

    verdicts = _verdicts(outcomes)
    assert verdicts["10"] == provisioning.AWAITING_HUMAN
    assert "11" not in verdicts
    assert "12" not in verdicts
    assert row is not None and row[0] == 0, "nothing was activated"


async def test_gate_11_activates_grants_against_a_valid_signature(
    feasible_pack, operator, signer
):
    """P13 - and the venture goes live only then."""
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        state = await provisioning.get_run(conn, run_id)

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*), count(activated_at), count(*) FILTER (WHERE is_assignable), "
                "       count(activated_by) "
                "FROM agent_forge_grant WHERE venture_id = %s", (VENTURE,)
            )
            row = await cur.fetchone()

    verdicts = _verdicts(outcomes)
    assert verdicts["10"] == provisioning.PASSED
    assert verdicts["11"] == provisioning.PASSED
    assert verdicts["12"] == provisioning.PASSED
    assert state is not None and state.status == "complete"
    assert state.current_gate == "12"
    assert state.artifacts_hash, "a completed run must be able to say what it provisioned"

    assert row is not None
    total, activated, assignable, activated_by = row
    assert activated == total
    assert assignable == total
    assert activated_by == total, "who activated is part of the record"


@pytest.fixture(autouse=True)
def clear_revocations(world, admin: psycopg.Connection):
    """`wipe_venture` does not reach `revocation`, and its `office_agent_id` is a
    foreign key onto the identities teardown deletes - so a row left here fails the
    NEXT test, in a teardown, naming a constraint instead of a cause.
    `test_gate_7_revocation` carries the same fixture for the same reason.

    **`world` is in the signature for ordering, not for use.** Fixtures tear down in
    reverse order of setup, so depending on `world` puts this cleanup BEFORE
    `teardown_world`. Written without it, the DELETE ran after teardown had already hit
    the foreign key and aborted the connection, and the failure reported
    `InFailedSqlTransaction` - the poisoned transaction, not the constraint that
    poisoned it.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM revocation")
    admin.commit()
    yield
    admin.rollback()  # a failing test can leave this connection mid-transaction
    with admin.cursor() as cur:
        cur.execute("DELETE FROM revocation")
    admin.commit()


# ------------------------------------------------------------------------- B53
# Gate 11 activated every inactive grant on the venture, revoked ones included. The
# predicate was `WHERE venture_id = %s AND activated_at IS NULL` - two controls over one
# invariant, and the second did not know about the first.
#
# It never fired: no run had reached Gate 11 on a venture holding a revocation, so the
# UPDATE had never met one. Found by reading what the next gate does before signing the
# gate in front of it, which is the same way entry 63's Gate 7 was found.


async def test_gate_11_does_not_activate_a_revoked_grant(
    feasible_pack, operator, signer, admin: psycopg.Connection
):
    """**The defect.** A revoked grant must not come back active.

    The call path would refuse it either way - `check_revocations` runs first in
    `resolve_grant` - so this is not about authority. It is about the record: without
    the fix the row carries a documented revocation AND `activated_by = <the signer>`,
    with no ordering visible in either, and the signer is recorded as having activated
    what they revoked.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT grant_id, office_agent_id, forge_id, module_id "
                "  FROM agent_forge_grant WHERE venture_id = %s ORDER BY granted_at",
                (VENTURE,),
            )
            grants = list(await cur.fetchall())
        assert len(grants) >= 2, "this test needs a grant to revoke and one to spare"
        target, agent_id, forge_id, module_id = grants[0]

        await revocation.revoke(
            conn, scope="agent_module",
            reason="revoked before Gate 11 ran, to prove Gate 11 asks",
            revoked_by=operator.human_id, revoked_by_role="venture_operator",
            office_agent_id=agent_id, forge_id=forge_id, module_id=module_id,
        )

        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT activated_at, activated_by FROM agent_forge_grant "
                " WHERE grant_id = %s", (target,),
            )
            revoked_row = await cur.fetchone()
            await cur.execute(
                "SELECT count(*) FROM agent_forge_grant "
                " WHERE venture_id = %s AND activated_at IS NOT NULL", (VENTURE,),
            )
            activated_total = (await cur.fetchone())[0]

    gate_11 = next(o for o in outcomes if o.gate == "11")
    assert gate_11.verdict == provisioning.PASSED, (
        "a revoked grant is not a reason to block the venture - the other grants are "
        "fine and the run should complete"
    )

    assert revoked_row is not None
    assert revoked_row[0] is None, (
        "Gate 11 activated a grant covered by a live revocation. The call path still "
        "refuses it, so nothing is exercisable - but the row now says this human both "
        "revoked and activated it, and the audit trail cannot say which came first."
    )
    assert revoked_row[1] is None, "and nobody should be recorded as its activator"

    assert activated_total == len(grants) - 1
    assert gate_11.evidence["withheld_revoked"] == 1
    assert gate_11.evidence["activated"] == len(grants) - 1
    # The reason line, not only the evidence: "N activated" reads the same to somebody
    # who does not know one was withheld.
    assert "NOT activated" in gate_11.reason
    assert "agent_module" in gate_11.reason


async def test_gate_11_still_activates_everything_when_nothing_is_revoked(
    feasible_pack, operator, signer
):
    """The control, and the one that matters most in this pair.

    Every other assertion here is that something stops being activated. A Gate 11 that
    activated nothing would satisfy them all and provision no venture. This is the same
    load-bearing shape `test_gate_7_revocation` names in its own docstring.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*), count(activated_at) FROM agent_forge_grant "
                " WHERE venture_id = %s", (VENTURE,),
            )
            total, activated = await cur.fetchone()

    gate_11 = next(o for o in outcomes if o.gate == "11")
    assert activated == total and total > 0
    assert gate_11.evidence["withheld_revoked"] == 0
    assert gate_11.evidence["withheld_inactive_identity"] == 0
    assert "NOT activated" not in gate_11.reason, (
        "the withheld clause must be absent, not zero - a reason line that always "
        "mentions revocation trains a reader to skip it"
    )


async def test_gate_11_does_not_activate_a_grant_whose_agent_is_not_active(
    feasible_pack, operator, signer, admin: psycopg.Connection
):
    """B53's sibling: a gate activating on one condition when two matter.

    The foreign key on `agent_forge_grant.office_agent_id` guarantees the identity
    EXISTS. It says nothing about its status, and Gate 11 never read it. `resolve_grant`
    refuses a non-active identity on every call (`IdentityInactive`), so this is the
    record rather than the authority: without the condition, a suspended agent's grant
    carries `activated_by = <the signer>` for authority that agent could never exercise.

    **Gate 10 catches it first, until somebody re-signs.** Suspending an appointed agent
    changes the regenerated artifacts, so the existing signature goes VOID and the run
    waits at Gate 10 - found while writing this test. A signature over the NEW artifacts
    clears Gate 10, and Gate 11's UPDATE is venture-wide over `activated_at IS NULL`, so
    the suspended agent's Gate 5 grants were still in the set it activated. The test walks
    that path rather than the one Gate 10 already closes.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT office_agent_id, count(*) FROM agent_forge_grant "
                " WHERE venture_id = %s GROUP BY office_agent_id "
                " ORDER BY office_agent_id LIMIT 1",
                (VENTURE,),
            )
            agent_id, held = await cur.fetchone()
            await cur.execute("SELECT count(*) FROM agent_forge_grant WHERE venture_id = %s",
                              (VENTURE,))
            total = (await cur.fetchone())[0]
        assert total > held, "this test needs grants on another, still-active agent"

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_agent_identity SET status = 'suspended' WHERE office_agent_id = %s",
            (agent_id,),
        )
    admin.commit()
    try:
        async with connection() as conn:
            voided = await provisioning.advance(
                conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
            )
            gate_10 = next(o for o in voided if o.gate == "10")
            assert gate_10.verdict == provisioning.AWAITING_HUMAN, (
                "suspending an appointed agent should void the signature - if it no longer "
                "does, Gate 10 stopped protecting this path and Gate 11 is the only guard"
            )
            await humans.sign_off(
                conn, gate="gate_10", venture_id=VENTURE, human=signer,
                artifact_kind="provisioning_artifacts",
                artifact_hash_value=gate_10.evidence["artifacts_hash"],
                note="re-signed over the artifacts regenerated without the suspended agent",
            )
            outcomes = await provisioning.advance(
                conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
            )
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT count(activated_at), count(activated_by) FROM agent_forge_grant "
                    " WHERE venture_id = %s AND office_agent_id = %s", (VENTURE, agent_id),
                )
                suspended_activated, suspended_activator = await cur.fetchone()
                await cur.execute(
                    "SELECT count(activated_at) FROM agent_forge_grant WHERE venture_id = %s",
                    (VENTURE,),
                )
                activated_total = (await cur.fetchone())[0]
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "UPDATE office_agent_identity SET status = 'active' "
                " WHERE office_agent_id = %s", (agent_id,),
            )
        admin.commit()

    gate_11 = next(o for o in outcomes if o.gate == "11")
    assert gate_11.verdict == provisioning.PASSED, (
        "one suspended agent is not a reason to block the venture"
    )
    assert suspended_activated == 0 and suspended_activator == 0, (
        "Gate 11 activated grants for a suspended identity - the call path refuses them, "
        "and the row now records a signer activating authority nobody could use"
    )
    assert activated_total == total - held
    assert gate_11.evidence["withheld_inactive_identity"] == held
    assert gate_11.evidence["inactive_identity_statuses"] == {"suspended": held}
    assert gate_11.evidence["withheld_revoked"] == 0
    assert "agent identity not active" in gate_11.reason
    assert "suspended" in gate_11.reason


async def test_a_revocation_lifted_before_gate_11_does_not_withhold_the_grant(
    feasible_pack, operator, signer, admin: psycopg.Connection
):
    """Withholding is a live question, not a stamp.

    `covered_grants` is recomputed against the `revocation` table every time it is
    asked, so a revocation lifted before Gate 11 runs withholds nothing. If this fails,
    something is remembering coverage that the module's own docstring says must never be
    cached - *"a venture-scope revocation must cover grants issued after it was
    declared, which a column stamped at revoke time cannot do."*

    **Reinstated before the run reaches Gate 11, deliberately.** Rewinding a completed
    run to replay Gate 11 puts already-activated grants in front of Gate 7, which blocks
    on them - correctly, and that is a different rule being tested by accident.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT grant_id, office_agent_id, forge_id, module_id "
                "  FROM agent_forge_grant WHERE venture_id = %s ORDER BY granted_at",
                (VENTURE,),
            )
            _, agent_id, forge_id, module_id = (await cur.fetchall())[0]

        revocation_id = await revocation.revoke(
            conn, scope="agent_module", reason="revoked, then lifted before Gate 11",
            revoked_by=operator.human_id, revoked_by_role="venture_operator",
            office_agent_id=agent_id, forge_id=forge_id, module_id=module_id,
        )
        await revocation.reinstate(
            conn, revocation_id=revocation_id,
            reinstated_by=operator.human_id, reinstated_by_role="venture_operator",
            reason="the reason it was revoked no longer holds",
        )

        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*), count(activated_at) FROM agent_forge_grant "
                " WHERE venture_id = %s", (VENTURE,),
            )
            total, activated = await cur.fetchone()

    gate_11 = next(o for o in outcomes if o.gate == "11")
    assert gate_11.evidence["withheld_revoked"] == 0, (
        "a lifted revocation still withheld the grant, so coverage is being remembered "
        "rather than recomputed"
    )
    assert activated == total and total > 0


# ------------------------------------------------------------------ entry 91, Gate 9
# Gate 9 counted every grant on the venture, revoked ones included, so a grant revoked
# because it should never have existed still demanded two certifications. B53's shape one
# gate earlier: burkham-wickmont's four Phase 0 engineering grants held it at Gate 9 after
# both deactivation and revocation, because the query read neither.

#: A research agent from the test world, and a module no research position operates - so
#: the world never certifies this pair and the grant below can only ever read never_certified.
_STRAY_AGENT = "11111111-1111-5111-8111-111111111111"
_STRAY_MODULE = "underwrite_deal"


async def _run_to_gate_9_with_a_stray_grant(conn, operator, admin, *, revoke: bool):
    run_id = await provisioning.start_run(conn, venture_id=VENTURE, started_by=operator.human_id)
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    await provisioning.record_human_review(
        conn, run_id=run_id, human=operator, note="reviewed the BOM and the gap report"
    )
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_forge_grant (grant_id, office_agent_id, forge_id, module_id, "
            "venture_id, trust_tier, granted_by) VALUES (%s, %s, 'cre-forge', %s, %s, "
            "'propose', %s)",
            (str(uuid.uuid4()), _STRAY_AGENT, _STRAY_MODULE, VENTURE, str(operator.human_id)),
        )
    admin.commit()
    if revoke:
        await revocation.revoke(
            conn, scope="agent_module", reason="should never have been issued",
            revoked_by=operator.human_id, revoked_by_role="venture_operator",
            office_agent_id=uuid.UUID(_STRAY_AGENT), forge_id="cre-forge",
            module_id=_STRAY_MODULE,
        )
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
    )
    return next(o for o in outcomes if o.gate == "9")


async def test_gate_9_does_not_ask_a_revoked_grant_for_a_certification(
    feasible_pack, operator, admin: psycopg.Connection
):
    """The defect: a grant a live revocation covers is not one the Readiness Gate waits on."""
    async with connection() as conn:
        gate_9 = await _run_to_gate_9_with_a_stray_grant(conn, operator, admin, revoke=True)

    assert gate_9.verdict == provisioning.PASSED, (
        f"Gate 9 still counted a revoked grant: {gate_9.reason}"
    )
    assert gate_9.evidence["withheld_revoked"] == 1
    assert gate_9.evidence["revocation_scopes"] == ["agent_module"]
    assert gate_9.evidence["not_certified_total"] == 0
    # Named in the reason, as Gate 11's withheld clause is.
    assert "1 revoked grant(s) not counted" in gate_9.reason


async def test_gate_9_still_blocks_on_the_same_grant_when_it_is_not_revoked(
    feasible_pack, operator, admin: psycopg.Connection
):
    """The control. Without it, a Gate 9 that ignored every uncertified grant would pass too."""
    async with connection() as conn:
        gate_9 = await _run_to_gate_9_with_a_stray_grant(conn, operator, admin, revoke=False)

    assert gate_9.verdict == provisioning.BLOCKED
    assert gate_9.evidence["not_certified_total"] == 2, "Unit A and Unit B of the stray grant"
    assert gate_9.evidence["withheld_revoked"] == 0
    assert "revoked grant" not in gate_9.reason


async def test_the_call_path_accepts_the_grant_once_it_is_activated(
    feasible_pack, operator, signer
):
    """The other half of P10. A control that refuses everything is an outage."""
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id,
                                   held_out=HeldOutPasses())

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT office_agent_id, forge_id, module_id FROM agent_forge_grant "
                "WHERE venture_id = %s ORDER BY grant_id LIMIT 1", (VENTURE,)
            )
            grant = await cur.fetchone()
        assert grant is not None
        resolved = await resolve_grant(
            conn, office_agent_id=grant[0], forge_id=grant[1],
            module_id=grant[2], venture_id=VENTURE,
        )
    assert resolved.trust_tier in ("auto_execute", "propose", "suggest")


# ---------------------------------------------------- Part 14 doing real work

async def test_changing_the_artifacts_voids_the_signature_by_comparison(
    feasible_pack, operator, signer, admin: psycopg.Connection
):
    """P12 - void and missing are different findings, and the run says which.

    The signature is made against a specific artifact hash. Then the world changes
    underneath the run: one agent's certification goes stale, the appointment changes,
    the artifacts change, and the hash no longer describes what would be provisioned.

    Nothing revoked anything. The signature voided **by comparison**, which is the
    property Part 14's artifact-hash binding exists for and the first place it does real
    work. Reporting it as *missing* would send the operator to find a signer, when what
    they need to know is that the document changed after signing.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE certification SET state = 'stale_instructions' WHERE unit = 'A' "
            "AND office_agent_id = %s",
            ("11111111-1111-5111-8111-111111111111",),
        )
    admin.commit()

    async with connection() as conn:
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        state = await provisioning.get_run(conn, run_id)
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(activated_at) FROM agent_forge_grant WHERE venture_id = %s",
                (VENTURE,),
            )
            row = await cur.fetchone()

    gate_10 = next(o for o in outcomes if o.gate == "10")
    assert gate_10.verdict == provisioning.AWAITING_HUMAN
    assert "VOID" in gate_10.reason
    assert "must be signed again" in gate_10.reason
    assert gate_10.evidence["voided_signatures"] == 1
    assert gate_10.evidence["valid_signatures"] == 0
    assert _verdicts(outcomes).get("11") is None, "the run stopped at 10"
    assert state is not None and state.status == "awaiting_human"
    assert row is not None and row[0] == 0, "no grant was activated against a void signature"


async def test_gate_11_refuses_a_void_signature_even_when_gate_10_is_recorded_passed(
    feasible_pack, operator, signer, admin: psycopg.Connection
):
    """P12, the half the sequence hides.

    In a normal run Gate 10 catches a void signature first, so Gate 11's own check never
    fires. That is exactly why it needs its own test: a gate that trusts its
    predecessor's recorded verdict can be reached by any path that sets the
    predecessor's state, and activation is the moment agents gain production authority.

    So here the run's record says Gate 10 passed, the artifacts have since changed, and
    Gate 11 is asked to activate anyway. It refuses.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        # A clean pass: Gate 10 passes and the run reaches 11 legitimately.
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id,
                                   held_out=HeldOutPasses())
        results = await provisioning.gate_results(conn, run_id)
        assert [r for r in results if r["gate"] == "10" and r["verdict"] == "passed"]

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE certification SET state = 'stale_instructions' WHERE unit = 'A' "
            "AND office_agent_id = %s",
            ("11111111-1111-5111-8111-111111111111",),
        )
        cur.execute(
            "UPDATE agent_forge_grant SET activated_at = NULL, activated_by = NULL "
            "WHERE venture_id = %s", (VENTURE,)
        )
    admin.commit()

    async with connection() as conn:
        await _set_run_gate(conn, run_id, "11")
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(activated_at) FROM agent_forge_grant WHERE venture_id = %s",
                (VENTURE,),
            )
            row = await cur.fetchone()

    gate_11 = next(o for o in outcomes if o.gate == "11")
    assert gate_11.verdict == provisioning.BLOCKED
    assert "without a Gate 10 signature" in gate_11.reason
    assert gate_11.evidence["voided"] == 1
    assert row is not None and row[0] == 0, "nothing was activated"


async def test_a_new_run_against_an_edited_pack_starts_unsigned(
    feasible_pack, operator, signer, pack_yaml
):
    """Editing the Pack means signing again, and the new run says so plainly.

    The previous run's signature was made against the previous Pack's artifacts. It is
    not carried forward, and it is not silently reused - the amended Pack gets its own
    review and its own signature.
    """
    from tests.provisioning.conftest import amend_for_capacity

    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        await provisioning.abort_run(
            conn, run_id=run_id, human=operator,
            reason="the Pack is being amended; this run provisions the old one",
        )

        # An edit that changes the artifacts: one position loses a head.
        import yaml as _yaml

        doc = _yaml.safe_load(amend_for_capacity(pack_yaml))
        doc["positions_required"][-1]["headcount"] -= 1
        edited = _yaml.safe_dump(doc, sort_keys=False)
        assert edited != amend_for_capacity(pack_yaml), "the edit must land"
        await packs.store(
            conn, yaml_source=edited, pack_version="1.2.0",
            authored_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )
        run_2 = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_2, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_2, human=operator, note="reviewing the amended Pack"
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_2, actor=operator.human_id, held_out=HeldOutPasses()
        )

    gate_10 = next(o for o in outcomes if o.gate == "10")
    assert gate_10.verdict == provisioning.AWAITING_HUMAN
    assert gate_10.evidence["valid_signatures"] == 0
    assert gate_10.evidence["voided_signatures"] == 1, (
        "the old signature is reported as void rather than quietly ignored"
    )


async def test_an_abandoned_run_frees_the_venture_and_leaves_grants_alone(
    feasible_pack, operator
):
    """Aborting is not revoking.

    A venture may only have one active run, so a run parked at a signature that is never
    coming would block it permanently. Aborting releases the venture - and deliberately
    does not touch grants, because abandoning a run and pulling a venture's authority
    are different acts with different authority, and collapsing them would make the
    first a silent way to do the second with no revocation record.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        with pytest.raises(provisioning.ProvisioningError):
            await provisioning.abort_run(
                conn, run_id=run_id, human=operator, reason="  "
            )
        await provisioning.abort_run(
            conn, run_id=run_id, human=operator, reason="superseded by a new Pack"
        )
        state = await provisioning.get_run(conn, run_id)
        assert state is not None and state.status == "aborted"

        # The venture is free again.
        second = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        assert second != run_id

        with pytest.raises(provisioning.ProvisioningError) as exc:
            await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    assert "aborted" in str(exc.value)


async def test_the_reviewer_at_gate_4_cannot_sign_at_gate_10(feasible_pack, operator):
    """Separation of duties, checked rather than trusted to process.

    The Pack declares `distinct_humans`. One person reviewing the artifacts and then
    signing them off is one person, and a two-signature control staffed by one person
    is a one-signature control with extra paperwork.
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

        await humans.sign_off(
            conn, gate="gate_4", venture_id=VENTURE, human=operator,
            artifact_kind="provisioning_artifacts",
            artifact_hash_value=gate_10.evidence["artifacts_hash"],
        )
        with pytest.raises(Exception) as exc:
            await humans.sign_off(
                conn, gate="gate_10", venture_id=VENTURE, human=operator,
                artifact_kind="provisioning_artifacts",
                artifact_hash_value=gate_10.evidence["artifacts_hash"],
            )
    assert "separation of duties" in str(exc.value)


# --------------------------------------------------------------- the record

async def test_every_gate_result_carries_evidence(feasible_pack, operator, signer):
    """P14 - a verdict with no evidence is an opinion.

    Every gate here records what it looked at, not merely what it concluded, so an
    operator reading a blocked run can see the denominator rather than being asked to
    trust the numerator.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id,
                                   held_out=HeldOutPasses())
        results = await provisioning.gate_results(conn, run_id)

    for r in results:
        assert r["reason"].strip(), f"gate {r['gate']} recorded no reason"
        assert isinstance(r["evidence"], dict)
        assert r["evidence"], f"gate {r['gate']} recorded no evidence"
        assert r["verdict"] in (
            provisioning.PASSED, provisioning.BLOCKED, provisioning.AWAITING_HUMAN
        )


async def test_a_run_is_auditable_end_to_end(
    feasible_pack, operator, signer, clean_audit, admin: psycopg.Connection
):
    """P15 - and the audit trail is the hash-chained one, not the run's own table.

    `provisioning_gate_result` is what the console reads. `audit_log` is what survives
    somebody with write access to the console's table. Gate 11 hands agents production
    authority, so it has to be in the second one.
    """
    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id,
                                   held_out=HeldOutPasses())

    with admin.cursor() as cur:
        cur.execute(
            "SELECT event_type, subject FROM audit_log WHERE venture_id = %s "
            "ORDER BY audit_id", (VENTURE,)
        )
        events = cur.fetchall()

    types = [e[0] for e in events]
    assert "provisioning_run_started" in types
    assert "provisioning_gate_4_reviewed" in types
    gates_audited = {
        e[1]["gate"] for e in events if e[0].startswith("provisioning_gate_")
        and "gate" in e[1]
    }
    assert set(provisioning.GATE_SEQUENCE) <= gates_audited, (
        "every gate verdict must reach the append-only log"
    )
    assert any(
        e[0] == "provisioning_gate_passed" and e[1]["gate"] == "11" for e in events
    ), "the moment agents gained production authority must be in the chained log"

    from tests.conftest import verify_chain

    ok, checked, first_break, reason = verify_chain(admin)
    assert ok, f"audit chain broken at {first_break}: {reason}"
    assert checked >= len(provisioning.GATE_SEQUENCE)


async def test_a_gate_result_cannot_be_deleted_by_the_runtime_role(
    feasible_pack, operator, app: psycopg.Connection
):
    """Deleting one would make a gate that blocked indistinguishable from one that
    never ran - which is precisely the difference the whole design turns on."""
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)

    with app.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("DELETE FROM provisioning_gate_result WHERE run_id = %s", (run_id,))
    app.rollback()


async def test_two_concurrent_runs_for_one_venture_are_refused(feasible_pack, operator):
    """Two runs would each issue grants for the same engagement, each unaware of the
    other's gate state.

    Both halves matter, and they are different claims.

    `start_run` checks first and says something useful, because this surfaced in the
    console as a bare 500 - a deliberate rule reported as an internal error teaches an
    operator that the system is broken when it is working exactly as designed.

    The **database** is still what refuses. The pre-check is a courtesy and loses a race:
    two requests can both read no-active-run before either inserts. So the constraint is
    asserted separately, by inserting directly and bypassing the check entirely - which
    is the only way to prove the guarantee does not depend on the code remembering.
    """
    async with connection() as conn:
        first = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )

        with pytest.raises(provisioning.ProvisioningError) as caught:
            await provisioning.start_run(
                conn, venture_id=VENTURE, started_by=operator.human_id
            )
        assert "already has an active run" in str(caught.value)
        assert str(first)[:8] in str(caught.value), (
            "the refusal does not name the run that is in the way, so the operator "
            "cannot go and deal with it"
        )

        # Past the check, straight at the constraint. This is the control.
        run = await packs.live(conn, VENTURE)
        assert run is not None
        with pytest.raises(psycopg.errors.UniqueViolation):
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO provisioning_run
                      (run_id, venture_id, pack_version, pack_hash, status,
                       current_gate, started_by)
                    VALUES (%s, %s, %s, %s, 'running', '0', %s)
                    """,
                    (
                        uuid.uuid4(), VENTURE, run.pack_version, run.content_hash,
                        operator.human_id,
                    ),
                )
        await conn.rollback()


async def test_a_run_cannot_start_without_a_live_pack(world, operator):
    """Gate 1's precondition, refused before a run row exists at all."""
    async with connection() as conn:
        with pytest.raises(provisioning.ProvisioningError) as exc:
            await provisioning.start_run(
                conn, venture_id=VENTURE, started_by=operator.human_id
            )
    assert "no live Pack" in str(exc.value)


async def _set_run_gate(conn, run_id: uuid.UUID, gate: str) -> None:
    """Rewind a run to a gate, so a re-check can be observed.

    Test-only, and deliberately not a public operation: a production caller able to set
    the current gate could set it to 11 and skip certification entirely.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET status = 'running', current_gate = %s "
            "WHERE run_id = %s", (gate, run_id),
        )
    await conn.commit()
