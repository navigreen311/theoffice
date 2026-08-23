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

from broker import humans, packs, provisioning
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

    This is the real Greenstone Pack, and it blocks at 4.5 on a real finding: the
    generated workflow routes 192 compliance approvals a day against one officer's four
    coverage hours. The gate stops there and says the number, rather than continuing to
    Gate 5 and issuing grants for a venture nobody can supervise.
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
        assert blocking.gate == "4.5"
        assert blocking.verdict == provisioning.BLOCKED
        assert "192 approvals" in blocking.reason
        assert "compliance_officer" in blocking.reason
        assert state is not None
        assert state.status == "blocked"
        assert state.current_gate == "4.5"

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM agent_forge_grant WHERE venture_id = %s",
                (VENTURE,),
            )
            row = await cur.fetchone()
    assert row is not None and row[0] == 0, (
        "Gate 5 must not have run. A blocked gate that lets the next one issue grants "
        "is a gate in name only."
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
    broken = pack_yaml.replace("    backup_human: Ivan\n", "")
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
    other's gate state. The database refuses rather than the code remembering to."""
    async with connection() as conn:
        await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            await provisioning.start_run(
                conn, venture_id=VENTURE, started_by=operator.human_id
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
