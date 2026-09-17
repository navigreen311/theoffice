"""A Phase 0 grant is retired when the ladder issues its own - not revoked, not deleted.

WHAT STOPPED RUN cb3a47f6

    Three agents were bootstrapped for greenstone hours after its Pack went live and a run
    was under way. `bootstrap-phase0` issues an ACTIVE grant, by design: Phase 0 exists to
    prove the call path works and an inactive grant proves nothing. Gate 5 then issued the
    ladder's own - inactive - for the same three triples, and Gate 7 found three active
    grants and blocked, three gates past the human review.

WHY NOT REVOCATION, MEASURED BEFORE THIS WAS BUILT

    A revocation's narrowest scope is `agent_module`: agent, forge, module. `blast_radius`
    reported `grants=2` on each of the three - the bootstrap grant AND its replacement -
    and Gate 11 activates with `AND NOT (g.grant_id = ANY(covered))`. Revoking would have
    traded a Gate 7 block for a Gate 11 one and left three of six grants permanently
    unactivatable.

    It would also have said the wrong thing. Revocation means the authority was wrong -
    what Amelie Wystan's engineering-department grants got, with a reason naming why they
    should never have existed. A Phase 0 grant that has been replaced was not wrong.

THE LOAD-BEARING TEST IN THIS FILE

    `test_an_active_grant_with_no_replacement_still_blocks_gate_7`. Every other test here
    asserts that something stops counting, and a gate that counted nothing would pass all
    of them. Gate 7's demand has not moved.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import bootstrap_phase0, grants, provisioning
from broker.db import connection
from broker.errors import GrantSuperseded
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


# ------------------------------------------------------------------------- helpers

async def _run_to_gate_7(conn, operator) -> uuid.UUID:
    run_id = await provisioning.start_run(
        conn, venture_id=VENTURE, started_by=operator.human_id
    )
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    await provisioning.record_human_review(
        conn, run_id=run_id, human=operator, note="reviewed the BOM and the gap report"
    )
    await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    return run_id


async def _recheck_gate_7(conn, run_id: uuid.UUID, operator):
    """Rewind to Gate 7 and re-run it through the pipeline. Returns its outcome.

    The same device `test_gate_7_revocation.py` uses, for the same reason: this world's
    run blocks at Gate 9 on certification, which is a true finding about the fixture and
    not the one under test. Rewinding is test-only and deliberately not a public
    operation - a production caller able to set the current gate could set it to 11.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE provisioning_run SET status = 'running', current_gate = '7' "
            "WHERE run_id = %s", (run_id,),
        )
    await conn.commit()
    outcomes = await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
    return next(o for o in outcomes if o.gate == "7")


def _bootstrap_grant(
    admin: psycopg.Connection, actor: uuid.UUID, *, module: str, agent_name: str
) -> uuid.UUID:
    """An ACTIVE bootstrap grant, the shape `bootstrap-phase0` leaves behind."""
    grant_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "SELECT office_agent_id FROM office_agent_identity WHERE agent_name = %s",
            (agent_name,),
        )
        agent_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id, trust_tier,
               operation_cert_ref, dept_context_cert_ref, granted_by,
               activated_at, activated_by, origin)
            VALUES (%s, %s, 'cre-forge', %s, %s, 'auto_execute', %s, %s, %s,
                    now(), %s, 'bootstrap')
            """,
            (grant_id, agent_id, module, VENTURE, str(uuid.uuid4()), str(uuid.uuid4()),
             actor, actor),
        )
    admin.commit()
    return grant_id


def _state(admin: psycopg.Connection, grant_id: uuid.UUID) -> tuple:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT origin, superseded_at IS NOT NULL, activated_at IS NOT NULL "
            "FROM agent_forge_grant WHERE grant_id = %s",
            (grant_id,),
        )
        return cur.fetchone()


# --------------------------------------------------------------- supersession clears 7

async def test_gate_5_retires_the_bootstrap_grant_and_gate_7_stops_blocking(
    feasible_pack, operator, admin
):
    """The whole sequence, through `advance` rather than by calling a gate directly.

    A gate tested through its own function is a gate tested somewhere the pipeline does
    not go.
    """
    first_agent = "Ada Sourcing"
    bootstrapped = _bootstrap_grant(
        admin, operator.human_id, module="property_lookup", agent_name=first_agent
    )
    assert _state(admin, bootstrapped) == ("bootstrap", False, True)

    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    # Gate 5 retired it on the way past.
    assert _state(admin, bootstrapped) == ("bootstrap", True, True), (
        "Gate 5 issued its own grant for this triple and did not retire the bootstrap one"
    )
    assert gate_7.verdict == provisioning.PASSED, gate_7.reason

    # And the row is still there. Retired, not deleted.
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM agent_forge_grant WHERE grant_id = %s",
                    (bootstrapped,))
        assert cur.fetchone()[0] == 1, "a retired grant must remain readable"


async def test_an_active_grant_with_no_replacement_still_blocks_gate_7(
    feasible_pack, operator, admin
):
    """**The test that keeps this a gate.**

    `superseded_at IS NULL` and not `origin <> 'bootstrap'`: the question is whether a
    grant still confers authority, not who wrote it. A bootstrap grant the ladder has NOT
    replaced is live authority, and Gate 7 must still refuse the run.

    `regulator_dossier_export` belongs to no Greenstone position, so Gate 5 issues nothing
    for it and the bootstrap grant stands alone.
    """
    orphan = _bootstrap_grant(
        admin, operator.human_id, module="comp_analysis", agent_name="Faye Buyers"
    )

    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)
        gate_7 = await _recheck_gate_7(conn, run_id, operator)

    assert _state(admin, orphan) == ("bootstrap", False, True), (
        "nothing replaced this grant, so nothing should have retired it"
    )
    assert gate_7.verdict == provisioning.BLOCKED
    assert "already active" in gate_7.reason


# ------------------------------------------------------------- refused at call time

async def test_a_superseded_grant_is_refused_at_call_time(feasible_pack, operator, admin):
    """Kept as history, and history confers nothing.

    The refusal is its own type. `NotGranted` would say there is no grant, which is false
    and sends the reader looking for an appointment; `Revoked` would say somebody decided
    this authority was wrong, which is a different fact about a different act.
    """
    grant_id = _bootstrap_grant(
        admin, operator.human_id, module="property_lookup", agent_name="Ada Sourcing"
    )
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE agent_forge_grant SET superseded_at = now() WHERE grant_id = %s",
            (grant_id,),
        )
        cur.execute(
            "SELECT office_agent_id FROM office_agent_identity WHERE agent_name = %s",
            ("Ada Sourcing",),
        )
        agent_id = cur.fetchone()[0]
    admin.commit()

    async with connection() as conn:
        with pytest.raises(GrantSuperseded) as refused:
            await grants.resolve_grant(
                conn, office_agent_id=agent_id, forge_id="cre-forge",
                module_id="property_lookup", venture_id=VENTURE,
            )

    assert "superseded" in str(refused.value)
    assert refused.value.audit_event == "call_refused_grant_superseded"


async def test_a_live_grant_is_preferred_over_a_retired_one_whatever_the_dates(
    feasible_pack, operator, admin
):
    """Ordering, not luck.

    `granted_at DESC` alone is nearly always enough - the ladder issues after the
    bootstrap. Nearly is not a rule, so a retired row sorts last and the refusal above
    fires only when every grant for the triple is retired.
    """
    retired = _bootstrap_grant(
        admin, operator.human_id, module="property_lookup", agent_name="Ada Sourcing"
    )
    with admin.cursor() as cur:
        # Retired, and NEWER than whatever the ladder will write.
        cur.execute(
            "UPDATE agent_forge_grant SET superseded_at = now(), "
            "granted_at = now() + interval '1 day' WHERE grant_id = %s",
            (retired,),
        )
        cur.execute(
            "SELECT office_agent_id FROM office_agent_identity WHERE agent_name = %s",
            ("Ada Sourcing",),
        )
        agent_id = cur.fetchone()[0]
    admin.commit()

    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)

        # The ladder's grant is older and inactive; it must still be the one resolved.
        with pytest.raises(Exception) as refused:
            await grants.resolve_grant(
                conn, office_agent_id=agent_id, forge_id="cre-forge",
                module_id="property_lookup", venture_id=VENTURE,
            )

    assert not isinstance(refused.value, GrantSuperseded), (
        "the retired grant was resolved over a live one because it was newer"
    )


async def test_gate_11_activates_every_live_grant_and_leaves_the_retired_one_alone(
    feasible_pack, operator, signer, admin
):
    """The whole ladder, with a retired bootstrap grant in the venture.

    **This is the half revocation could not have delivered.** Revoking the bootstrap grant
    would have covered its replacement too - same (agent, forge, module) - and Gate 11
    activates `AND NOT (g.grant_id = ANY(covered))`, so the ladder's grant would have been
    withheld. Retiring leaves every live grant activatable, which is what this asserts.
    """
    from tests.provisioning.test_pipeline import HeldOutPasses, _to_gate_10

    bootstrapped = _bootstrap_grant(
        admin, operator.human_id, module="property_lookup", agent_name="Ada Sourcing"
    )

    async with connection() as conn:
        run_id = await _to_gate_10(conn, operator, signer)
        await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FILTER (WHERE superseded_at IS NULL), "
            "       count(*) FILTER (WHERE superseded_at IS NULL "
            "                          AND activated_at IS NOT NULL) "
            "FROM agent_forge_grant WHERE venture_id = %s",
            (VENTURE,),
        )
        live, live_active = cur.fetchone()

    assert live > 0, "the ladder issued nothing, so this asserts nothing"
    assert live_active == live, (
        f"Gate 11 activated {live_active} of {live} live grants - a retired grant must "
        "not stop its replacement being activated, which is why this is supersession "
        "and not revocation"
    )
    assert _state(admin, bootstrapped)[1] is True, "the bootstrap grant must stay retired"


# ----------------------------------------------- the gates that were not in the sizing

async def test_gate_9_does_not_demand_a_certification_for_a_retired_grant(
    feasible_pack, operator, admin
):
    """Not in the sizing. Found by building the Gate 11 test and watching it stop at 9.

    Gate 7 was the symptom. Gate 9 reads the venture's grants with the same premise, so a
    retired bootstrap grant still demanded Unit A on its module and Unit B on its
    department. It already declines to ask a REVOKED grant for one (entry 91) - the same
    argument, and this is the other half of it.

    The numbers below are the measured ones: 10 live grants and 20 units either way, with
    the retired grant contributing the 2 that blocked.
    """
    bootstrapped = _bootstrap_grant(
        admin, operator.human_id, module="property_lookup", agent_name="Ada Sourcing"
    )

    from tests.provisioning.test_pipeline import HeldOutPasses

    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed the BOM and the gap report"
        )
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses()
        )

    assert _state(admin, bootstrapped)[1] is True, "Gate 5 did not retire it"
    gate_9 = next(o for o in outcomes if o.gate == "9")
    assert gate_9.verdict == provisioning.PASSED, gate_9.reason
    assert "not certified" not in gate_9.reason


async def test_is_assignable_is_false_for_a_retired_grant(feasible_pack, operator, admin):
    """The generated column has to agree with `resolve_grant`, or it lies to four readers.

    `is_assignable` is one claim: that `resolve_grant` can return this row. Gate 12, the
    console's grant badge, `roster` and `ventures` all read it, and a retired grant
    carries both certification refs and `activated_at` - so without 0043 redefining it,
    every one of them would have shown a grant the call path refuses as assignable.
    """
    grant_id = _bootstrap_grant(
        admin, operator.human_id, module="property_lookup", agent_name="Ada Sourcing"
    )
    with admin.cursor() as cur:
        cur.execute("SELECT is_assignable FROM agent_forge_grant WHERE grant_id = %s",
                    (grant_id,))
        assert cur.fetchone()[0] is True, "a live bootstrap grant is assignable"
        cur.execute(
            "UPDATE agent_forge_grant SET superseded_at = now() WHERE grant_id = %s "
            "RETURNING is_assignable", (grant_id,),
        )
        assert cur.fetchone()[0] is False
    admin.rollback()


# ------------------------------------------------------------------------ the guard

async def test_bootstrap_refuses_a_venture_that_is_on_the_ladder(feasible_pack, operator):
    """Stopping the collision is cheaper than cleaning up after it.

    Supersession repairs a venture that already holds both. This refuses the second one
    being written at all, and says why rather than only that it will not.
    """
    async with connection() as conn:
        run_id = await _run_to_gate_7(conn, operator)
        assert run_id is not None

        with pytest.raises(bootstrap_phase0.BootstrapError) as refused:
            await bootstrap_phase0.plan(
                conn, ref="ada_sourcing", forge_id="cre-forge",
                module_id="property_lookup", department="research",
                venture_id=VENTURE,
            )

    message = str(refused.value)
    assert "is on the ladder" in message
    assert "Nothing was written" in message
    assert "Gate 7" in message, "the refusal must name what would have gone wrong"
