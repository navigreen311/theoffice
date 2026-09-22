"""A venture declared in simulation defers an unreviewed entry. It never verifies one.

RULED 22 SEPTEMBER 2026 (decisions entry 166)
=============================================

    *"A venture may be declared in simulation by a named human, with a reason and a
    date. In simulation, an unreviewed compliance entry is recorded as deliberately
    deferred, not as verified, and does not fail a gate. Leaving simulation is a
    separate named act; every unreviewed entry fails again the moment it does. No
    attestation may ever read TRUE on the strength of simulation. Greenstone and Burkham
    Wickmont are both in simulation as of today, declared by Ivan Green, reason: mock
    runs and simulations before real clients."*

THE THREE THAT CARRY THE RULING
===============================

    `test_no_attestation_reads_true_on_the_strength_of_simulation` - the clause that
    makes the rest of it safe. Without it, declaring simulation converts "we have not
    looked" into "somebody looked and it holds" one gate later.

    `test_a_deferred_entry_is_still_not_relied_on` - deferred is not verified. The entry
    is unchanged: still a draft, no approver, no counsel review.

    `test_leaving_makes_every_unreviewed_entry_fail_again` - *"the moment it does."*
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from broker import knowledge, simulation
from broker.db import connection
from broker.errors import NotAuthorized
from tests.conftest import declare_author, requires_db, undeclare_author

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "test-simulation"
REF = "test/sim-v1"

DECLARER = uuid.UUID("c0c0c0c0-0000-4000-8000-000000000166")
AUTHOR = uuid.UUID("c0c0c0c0-0000-4000-8000-000000000167")
FIXTURE = uuid.UUID("c0c0c0c0-0000-4000-8000-000000000168")

REASON = "mock runs and simulations before real clients"

ENTRY = {
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls to property owners.",
    "agent_behavior_implication": "State identity and purpose before anything else.",
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310",
}


@pytest.fixture(autouse=True)
def _world(admin: psycopg.Connection):
    declare_author(admin, DECLARER, "Simulation Declarer")
    declare_author(admin, AUTHOR, "Simulation Entry Author")
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'smoke-declarer-0166', 'smoke-0166@sim.invalid', "
            "        'bearer_token', 'test_fixture', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (FIXTURE, f"fixture-{FIXTURE.hex}"),
        )
    admin.commit()
    _wipe(admin)
    yield
    _wipe(admin)
    undeclare_author(admin, DECLARER, AUTHOR, FIXTURE)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM compliance_library_entry WHERE venture_id = %s", (VENTURE,)
        )
        cur.execute(
            "ALTER TABLE venture_simulation DISABLE TRIGGER "
            "venture_simulation_is_not_deleted"
        )
        cur.execute("DELETE FROM venture_simulation WHERE venture_id = %s", (VENTURE,))
        cur.execute(
            "ALTER TABLE venture_simulation ENABLE TRIGGER "
            "venture_simulation_is_not_deleted"
        )
    conn.commit()


async def _write(ref: str = REF, **overrides: Any) -> str:
    async with connection() as conn:
        return await knowledge.author_compliance_entry(
            conn, venture_id=VENTURE, entry_ref=ref, authored_by=AUTHOR,
            **{**ENTRY, **overrides},
        )


async def _declare(by: uuid.UUID = DECLARER, reason: str = REASON):
    async with connection() as conn:
        return await simulation.declare(
            conn, venture_id=VENTURE, declared_by=by, reason=reason
        )


async def _entry(ref: str = REF) -> dict[str, Any]:
    async with connection() as conn:
        entries = await knowledge.compliance_entries(conn, VENTURE)
    return next(e for e in entries if e["entry_ref"] == ref)


# ================================================== declaring, by a named human

async def test_a_declaration_names_a_person_a_reason_and_a_date():
    declared = await _declare()
    assert declared.declared_by == DECLARER
    assert declared.declared_by_name == "Simulation Declarer"
    assert declared.reason == REASON
    assert declared.declared_at is not None
    assert declared.live is True


async def test_a_declaration_without_a_reason_is_refused():
    """The field a reader finds in six months when they ask why a gate passed."""
    with pytest.raises(simulation.SimulationError) as raised:
        await _declare(reason="   ")
    assert "gives a reason" in str(raised.value)

    async with connection() as conn:
        assert await simulation.current(conn, VENTURE) is None


async def test_a_fixture_may_not_declare_a_venture_in_simulation():
    """A declaration suspends a compliance rule. A fixture cannot be asked about one."""
    with pytest.raises(NotAuthorized) as raised:
        await _declare(by=FIXTURE)
    assert "test_fixture" in str(raised.value)


async def test_declaring_twice_is_refused():
    """A second declaration would record a decision nobody took."""
    await _declare()
    with pytest.raises(simulation.SimulationError) as raised:
        await _declare(reason="a different reason")
    assert "already in simulation" in str(raised.value)


def test_the_database_holds_one_live_simulation_per_venture(admin):
    """**The control.** The partial unique index, reached by hand SQL."""
    insert = (
        "INSERT INTO venture_simulation "
        "  (simulation_id, venture_id, declared_by, reason) "
        "VALUES (%s, %s, %s, 'by hand')"
    )
    with admin.cursor() as cur:
        cur.execute(insert, (uuid.uuid4(), VENTURE, DECLARER))
    admin.commit()

    with pytest.raises(psycopg.errors.UniqueViolation), admin.cursor() as cur:
        cur.execute(insert, (uuid.uuid4(), VENTURE, DECLARER))
    admin.rollback()


def test_a_declaration_is_not_editable(admin):
    """Who declared it, when and why are the facts every deferral rests on."""
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO venture_simulation "
            "  (simulation_id, venture_id, declared_by, reason) "
            "VALUES (%s, %s, %s, 'the original reason')",
            (uuid.uuid4(), VENTURE, DECLARER),
        )
    admin.commit()
    with pytest.raises(psycopg.errors.RaiseException) as raised, admin.cursor() as cur:
        cur.execute(
            "UPDATE venture_simulation SET reason = 'a tidier reason' "
            " WHERE venture_id = %s", (VENTURE,)
        )
    admin.rollback()
    assert "not editable" in str(raised.value)


def test_a_declaration_is_not_deleted(admin):
    """A RAISE, not a rule that swallows the statement. A delete that quietly does
    nothing is a delete somebody believes happened."""
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO venture_simulation "
            "  (simulation_id, venture_id, declared_by, reason) "
            "VALUES (%s, %s, %s, 'r')",
            (uuid.uuid4(), VENTURE, DECLARER),
        )
    admin.commit()
    with pytest.raises(psycopg.errors.RaiseException), admin.cursor() as cur:
        cur.execute("DELETE FROM venture_simulation WHERE venture_id = %s",
                    (VENTURE,))
    admin.rollback()


# =========================================== deferred, and not verified

async def test_a_deferred_entry_is_still_not_relied_on():
    """**THE RULING'S CENTRE.** *"recorded as deliberately deferred, not as verified."*

    Nothing about the entry changes. It is still a draft, still has no approver and no
    counsel review, and `relied_on` is still false. What changes is what a gate does
    about that - and the two facts live in two fields so a declaration of simulation
    cannot read, three screens later, as an entry a lawyer approved.
    """
    await _write()
    await _declare()

    entry = await _entry()
    assert entry["status"] == "draft"
    assert entry["approved_by"] is None
    assert entry["counsel_reviewed_at"] is None
    assert entry["relied_on"] is False, "deferred is not relied on"
    assert knowledge.is_relied_on(entry) is False
    assert entry["deferred_under_simulation"] is True


async def test_an_entry_outside_simulation_is_not_deferred():
    """**Load-bearing.** The field is about the venture's declaration, not the entry."""
    await _write()
    assert (await _entry())["deferred_under_simulation"] is False


async def test_a_deferred_entry_explains_its_flag_at_gate_6():
    """*"...and does not fail a gate."* The query Gate 6 reads."""
    await _write(runtime_flag="tsr_disclosure_required")
    async with connection() as conn:
        assert await knowledge.flags_with_entries(conn, VENTURE) == set()

    await _declare()
    async with connection() as conn:
        # `flags_with_entries` is the RELIED-ON set and is deliberately unchanged: the
        # deferral lives in the gate's own query, beside the evidence that names it.
        assert await knowledge.flags_with_entries(conn, VENTURE) == set()

        await conn.execute("SELECT 1")
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT runtime_flag FROM compliance_library_entry "
                " WHERE runtime_flag IS NOT NULL AND venture_id = %(venture_id)s "
                f"   AND ({knowledge.RELIED_ON_SQL} "
                f"        OR {simulation.IN_SIMULATION_SQL})",
                {"venture_id": VENTURE},
            )
            assert {r[0] for r in await cur.fetchall()} == {"tsr_disclosure_required"}


# ============================ no attestation reads true on the strength of it

async def test_no_attestation_reads_true_on_the_strength_of_simulation(admin):
    """**THE CLAUSE THAT MAKES THE REST SAFE.**

    Simulation defers a check. An attestation is a person's statement that the check
    passed. Without this, declaring simulation would quietly convert "we have not
    looked" into "somebody looked and it holds" one gate later.
    """
    from broker import attestation, humans

    await _declare()
    async with connection() as conn:
        founder = humans.Human(
            human_id=DECLARER, display_name="Simulation Declarer",
            email="d@sim.invalid", status="active", roles=(("ivan", None),),
            origin="human", auth_method="bearer_token",
        )
        with pytest.raises(attestation.AttestationError) as raised:
            await attestation.attest(
                conn, venture_id=VENTURE, department="research", forge_id="cre-forge",
                human=founder,
                escalation_path_verified=False,
                escalation_path_reason="not drilled",
                compliance_coupling_verified=True,
                compliance_coupling_reason="the entries look fine to me",
            )

    message = str(raised.value)
    assert "in simulation" in message
    assert "166" in message
    assert REASON in message, "the refusal names why the venture is in simulation"


async def test_attesting_false_in_simulation_is_not_refused():
    """**Load-bearing.** A FALSE verdict is as recordable as a TRUE one (entry 147).

    Refusing both would mean a venture in simulation could not record that it had
    looked at its coupling and found nothing to couple - which is exactly what Ivan
    Green's attestations of 22 September say.
    """
    from broker import attestation, humans

    await _declare()
    async with connection() as conn:
        founder = humans.Human(
            human_id=DECLARER, display_name="Simulation Declarer",
            email="d@sim.invalid", status="active", roles=(("ivan", None),),
            origin="human", auth_method="bearer_token",
        )
        recorded = await attestation.attest(
            conn, venture_id=VENTURE, department="research", forge_id="cre-forge",
            human=founder,
            escalation_path_verified=False,
            escalation_path_reason="no drill has been run for this test venture",
            compliance_coupling_verified=False,
            compliance_coupling_reason="the library is deferred under simulation",
        )
    assert recorded.compliance_coupling_verified is False
    assert recorded.passed is False


async def test_there_is_no_way_to_attest_true_anyway():
    """**Load-bearing, and the shape of the refusal rather than its message.**

    A keyword argument that let a caller through would be the thing entry 166 forbids,
    spelled as a parameter. This reads the signature so adding one fails the build.
    """
    import inspect

    from broker import attestation

    parameters = set(inspect.signature(attestation.attest).parameters)
    for forbidden in ("force", "override", "allow_simulation", "despite_simulation",
                      "in_simulation", "skip_simulation_check"):
        assert forbidden not in parameters, (
            f"attest takes {forbidden!r}, which is entry 166's refusal as an argument"
        )


# ======================================= leaving, and what fails again

async def test_leaving_makes_every_unreviewed_entry_fail_again():
    """**THE RULING.** *"every unreviewed entry fails again the moment it does."*"""
    await _write()
    await _declare()
    assert (await _entry())["deferred_under_simulation"] is True

    async with connection() as conn:
        left = await simulation.leave(
            conn, venture_id=VENTURE, left_by=DECLARER,
            reason="a real client signed",
        )
    assert left.live is False
    assert left.left_by_name == "Simulation Declarer"
    assert left.left_reason == "a real client signed"

    entry = await _entry()
    assert entry["deferred_under_simulation"] is False
    assert entry["relied_on"] is False


async def test_leaving_is_a_named_act_with_a_reason():
    await _declare()
    with pytest.raises(simulation.SimulationError) as raised:
        async with connection() as conn:
            await simulation.leave(
                conn, venture_id=VENTURE, left_by=DECLARER, reason="  "
            )
    assert "gives a reason" in str(raised.value)

    async with connection() as conn:
        assert (await simulation.current(conn, VENTURE)) is not None


async def test_leaving_a_venture_that_is_not_in_simulation_is_refused():
    with pytest.raises(simulation.SimulationError) as raised:
        async with connection() as conn:
            await simulation.leave(
                conn, venture_id=VENTURE, left_by=DECLARER, reason="whatever"
            )
    assert "not in simulation" in str(raised.value)


async def test_leaving_does_not_un_happen(admin):
    """A venture cannot quietly re-enter the simulation it just left.

    Declaring again is allowed and is a NEW row with its own name, reason and date -
    which is the point: the history reads as two decisions, not one that wobbled.
    """
    await _declare()
    async with connection() as conn:
        left = await simulation.leave(
            conn, venture_id=VENTURE, left_by=DECLARER, reason="done simulating"
        )

    with pytest.raises(psycopg.errors.RaiseException) as raised, admin.cursor() as cur:
        cur.execute(
            "UPDATE venture_simulation "
            "   SET left_at = NULL, left_by = NULL, left_reason = NULL "
            " WHERE simulation_id = %s", (left.simulation_id,)
        )
    admin.rollback()
    assert "already left" in str(raised.value)

    again = await _declare(reason="back to simulation for a second drill")
    assert again.simulation_id != left.simulation_id

    async with connection() as conn:
        past = await simulation.history(conn, VENTURE)
    assert len(past) == 2, "the history keeps both declarations"
    assert [s.live for s in past] == [True, False]


def test_the_database_refuses_a_half_recorded_leaving(admin):
    """All three leaving columns or none: a date with no name is a venture that left
    simulation with nobody deciding to."""
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO venture_simulation "
            "  (simulation_id, venture_id, declared_by, reason) "
            "VALUES (%s, %s, %s, 'r')",
            (uuid.uuid4(), VENTURE, DECLARER),
        )
    admin.commit()
    with pytest.raises(psycopg.errors.CheckViolation), admin.cursor() as cur:
        cur.execute(
            "UPDATE venture_simulation SET left_at = now() WHERE venture_id = %s",
            (VENTURE,),
        )
    admin.rollback()


async def test_the_history_survives_leaving():
    """A venture in simulation last month explains a gate result from last month."""
    await _declare()
    async with connection() as conn:
        await simulation.leave(
            conn, venture_id=VENTURE, left_by=DECLARER, reason="finished"
        )
        assert await simulation.current(conn, VENTURE) is None
        past = await simulation.history(conn, VENTURE)

    assert len(past) == 1
    assert past[0].reason == REASON
    assert past[0].left_reason == "finished"
