"""A Unit B certification on the strength of a declaration, and void when it ends.

RULED 22 SEPTEMBER 2026 (decisions entry 167)
=============================================

    *"A department may be certified for simulation. A distinct Unit B basis, never
    'verified', recorded with the declaration that permitted it. Gate 9 accepts it while
    the venture is in simulation and refuses it the moment the venture leaves, and every
    simulation certification is void at that point. Any surface showing a grant, a gate
    or a sign-off says which of its certifications are simulation-only. Measured: under
    entry 166 coupling can never be TRUE, so Unit B has no route and Gate 9 cannot
    clear."*

THE THREE THAT CARRY THE RULING
===============================

    `test_leaving_simulation_voids_the_certification` - *"void at that point."* Gate 9
    refuses it and the call path refuses every grant behind it, without anything
    editing the row.

    `test_it_is_never_recorded_as_verified` - a distinct basis, no verdict, no model, no
    score, no attestation. It cannot be read as an exam anybody sat.

    `test_republishing_an_instruction_decertifies_it` - the property that makes a
    certification worth having, kept for this basis too.
"""

from __future__ import annotations

import uuid
from typing import Any

import psycopg
import pytest

from broker import certification, humans, instructions, simulation
from broker.db import connection
from broker.errors import NotAuthorized, SimulationCertificationVoid
from broker.grants import resolve_grant
from tests.conftest import declare_author, requires_db, undeclare_author
from tests.world import CRE_MODULES, FORGE_ID, ROSTER

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
DEPARTMENT = "operations"

FOUNDER = uuid.UUID("d0d0d0d0-0000-4000-8000-000000000167")
FIXTURE = uuid.UUID("d0d0d0d0-0000-4000-8000-000000000168")

REASON = "mock runs before real clients; no counsel until then"


@pytest.fixture
def simulated(world, admin: psycopg.Connection):
    """The suite's shared world, plus the two accounts and the grants this needs.

    Built on `tests/provisioning/conftest.py::world` rather than beside it, so the Gate 9
    test below can take `feasible_pack` and `operator` from the same fixtures every other
    provisioning suite uses. A second world would be a second set of assumptions about
    what "prepared" means.
    """
    declare_author(admin, FOUNDER, "Simulation Founder")
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'smoke-founder-0167', 'smoke-0167@sim.invalid', "
            "        'bearer_token', 'test_fixture', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (FIXTURE, f"fixture-{FIXTURE.hex}"),
        )
    admin.commit()
    _issue_grants(admin)
    yield admin
    _clear_simulation(admin)
    undeclare_author(admin, FOUNDER, FIXTURE)


def _clear_simulation(admin: psycopg.Connection) -> None:
    """The declarations this suite made, and the certifications they permitted.

    In this order and not the other: the certification names the declaration, and the
    declaration names the person whose account `undeclare_author` removes next. The
    shared `world` fixture wipes the venture at SETUP, so without this a declaration
    from one test holds its declarer's account down for the whole session.
    """
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM certification WHERE simulation_ref IN "
            "(SELECT simulation_id FROM venture_simulation WHERE venture_id = %s)",
            (VENTURE,),
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
    admin.commit()


#: The department's modules, and the two agents who hold them.
#:
#: `build_world` certifies positions but issues no grants - those come from a
#: provisioning run at Gate 5, and running one here would test the ladder rather than
#: this ruling. So the fixture writes them, pointing at the certifications the world
#: already made, which is the state Gate 5 leaves behind.
OPERATIONS_MODULES = ("buyer_match", "assign_contract")


def _issue_grants(admin: psycopg.Connection) -> None:
    operations = [agent for agent, _name, dept in ROSTER if dept == DEPARTMENT]
    with admin.cursor() as cur:
        for agent in operations:
            for module_id in OPERATIONS_MODULES:
                cur.execute(
                    "SELECT cert_id FROM certification "
                    " WHERE unit = 'A' AND office_agent_id = %s AND forge_id = %s "
                    "   AND module_id = %s",
                    (agent, FORGE_ID, module_id),
                )
                unit_a = cur.fetchone()
                cur.execute(
                    "SELECT cert_id FROM certification "
                    " WHERE unit = 'B' AND forge_id = %s AND department = %s",
                    (FORGE_ID, DEPARTMENT),
                )
                unit_b = cur.fetchone()
                cur.execute(
                    "INSERT INTO agent_forge_grant "
                    "  (grant_id, office_agent_id, forge_id, module_id, venture_id, "
                    "   trust_tier, operation_cert_ref, dept_context_cert_ref, "
                    "   granted_by, origin, activated_at, activated_by) "
                    "VALUES (%s, %s, %s, %s, %s, 'suggest', %s, %s, %s, 'ladder', "
                    "        now(), %s)",
                    (uuid.uuid4(), agent, FORGE_ID, module_id, VENTURE,
                     str(unit_a[0]) if unit_a else None,
                     str(unit_b[0]) if unit_b else None,
                     FOUNDER, FOUNDER),
                )
    admin.commit()


def _live(admin: psycopg.Connection, module_id: str) -> tuple[str, str]:
    """A real (content_hash, forge_api_version) for a module.

    The by-hand inserts below need them: `bootstrap_hash_is_live` (migration 0038) is a
    row trigger that refuses a certification naming text that is not the live
    instruction, and it fires BEFORE the CHECK each of those tests is about. A
    placeholder hash would make them pass on the wrong refusal.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT content_hash, forge_api_version FROM forge_operating_instruction "
            " WHERE forge_id = %s AND module_id = %s AND superseded_at IS NULL",
            (FORGE_ID, module_id),
        )
        row = cur.fetchone()
    assert row is not None, f"no live instruction for {module_id}"
    return str(row[0]), str(row[1])


def _person(human_id: uuid.UUID, name: str, origin: str = "human") -> humans.Human:
    return humans.Human(
        human_id=human_id, display_name=name, email=f"{name}@sim.invalid",
        status="active", roles=(("ivan", None),), origin=origin,
        auth_method="bearer_token",
    )


FOUNDER_HUMAN = _person(FOUNDER, "Simulation Founder")
FIXTURE_HUMAN = _person(FIXTURE, "smoke-founder-0167", origin="test_fixture")


async def _declare() -> simulation.Simulation:
    async with connection() as conn:
        return await simulation.declare(
            conn, venture_id=VENTURE, declared_by=FOUNDER, reason=REASON
        )


async def _leave() -> simulation.Simulation:
    async with connection() as conn:
        return await simulation.leave(
            conn, venture_id=VENTURE, left_by=FOUNDER, reason="a real client signed"
        )


async def _certify(department: str = DEPARTMENT, reason: str = REASON):
    async with connection() as conn:
        return await certification.certify_for_simulation(
            conn, venture_id=VENTURE, department=department, forge_id=FORGE_ID,
            human=FOUNDER_HUMAN, reason=reason,
        )


def _row(admin: psycopg.Connection, department: str = DEPARTMENT) -> dict[str, Any]:
    with admin.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT * FROM certification "
            " WHERE unit = 'B' AND forge_id = %s AND department = %s",
            (FORGE_ID, department),
        )
        row = cur.fetchone()
    assert row is not None, f"no unit B certification for {department}"
    return dict(row)


# ================================================== the dead end, and the way out

async def test_it_is_refused_when_the_venture_is_not_in_simulation(simulated):
    """Nothing permits it. The basis is recorded WITH the declaration, and there is
    none to record."""
    with pytest.raises(certification.CertificationError) as raised:
        await _certify()
    assert "not in simulation" in str(raised.value)


async def test_a_declaration_permits_it(simulated):
    declared = await _declare()
    certified = await _certify()

    assert certified.unit == "B"
    assert certified.state == "certified"
    assert certified.certified_tier == certification.SIMULATION_TIER

    row = _row(simulated)
    assert row["basis"] == certification.SIMULATION_BASIS
    assert row["simulation_ref"] == declared.simulation_id


async def test_it_is_never_recorded_as_verified(simulated):
    """**THE RULING.** *"A distinct Unit B basis, never 'verified'."*

    No verdict, no model, no score, no attestation. Two Phase 0.8 grants once carried
    `simforge_verdict = 'PASS'` against no scenario run at all - a false statement in
    the one column that exists to say whether SimForge ran - and migration 0059 makes
    that unrepresentable for this basis rather than merely unwritten.
    """
    await _declare()
    await _certify()

    row = _row(simulated)
    assert row["basis"] not in ("tested", "attested", "bootstrap")
    assert row["simforge_verdict"] is None
    assert row["agent_model"] is None
    assert row["model_digest"] is None
    assert row["score"] is None
    assert row["attestation_ref"] is None
    # The reason is where a bootstrap's goes, so a reader finds it in one place.
    assert "NO EXAM" in row["scenario_pack_ref"]
    assert REASON in row["scenario_pack_ref"]


async def test_a_reason_is_required(simulated):
    await _declare()
    with pytest.raises(certification.CertificationError) as raised:
        await _certify(reason="   ")
    assert "gives a reason" in str(raised.value)


async def test_a_fixture_may_not_certify_for_simulation(simulated):
    await _declare()
    async with connection() as conn:
        with pytest.raises(NotAuthorized) as raised:
            await certification.certify_for_simulation(
                conn, venture_id=VENTURE, department=DEPARTMENT, forge_id=FORGE_ID,
                human=FIXTURE_HUMAN, reason=REASON,
            )
    assert "test_fixture" in str(raised.value)


def test_the_database_refuses_a_simulation_certification_with_a_verdict(simulated):
    """**The control.** Migration 0059's CHECK, reached by hand SQL."""
    with simulated.cursor() as cur:
        cur.execute(
            "INSERT INTO venture_simulation "
            "  (simulation_id, venture_id, declared_by, reason) "
            "VALUES (%s, %s, %s, 'by hand') RETURNING simulation_id",
            (uuid.uuid4(), VENTURE, FOUNDER),
        )
        simulation_id = cur.fetchone()[0]
    simulated.commit()

    content_hash, api_version = _live(simulated, CRE_MODULES[0])
    with pytest.raises(psycopg.errors.CheckViolation), simulated.cursor() as cur:
        cur.execute(
            "INSERT INTO certification "
            "  (cert_id, unit, rubric_kind, forge_id, department, state, "
            "   certified_tier, instruction_content_hash, forge_api_version, "
            "   rubric_version, basis, simulation_ref, simforge_verdict) "
            "VALUES (%s, 'B', 'domain', %s, 'by-hand-dept', 'certified', 'suggest', "
            "        %s, %s, 'r1', 'simulation', %s, 'PASS')",
            (uuid.uuid4(), FORGE_ID, content_hash, api_version, simulation_id),
        )
    simulated.rollback()


def test_the_database_refuses_a_simulation_certification_with_no_declaration(simulated):
    content_hash, api_version = _live(simulated, CRE_MODULES[0])
    with pytest.raises(psycopg.errors.CheckViolation), simulated.cursor() as cur:
        cur.execute(
            "INSERT INTO certification "
            "  (cert_id, unit, rubric_kind, forge_id, department, state, "
            "   certified_tier, instruction_content_hash, forge_api_version, "
            "   rubric_version, basis) "
            "VALUES (%s, 'B', 'domain', %s, 'by-hand-dept', 'certified', 'suggest', "
            "        %s, %s, 'r1', 'simulation')",
            (uuid.uuid4(), FORGE_ID, content_hash, api_version),
        )
    simulated.rollback()


def test_the_database_refuses_a_simulation_unit_a(simulated):
    """Mirrors `only_unit_b_is_attested`. Unit A is a per-agent, per-module exam and
    there is no version of that a declaration can stand in for."""
    with simulated.cursor() as cur:
        cur.execute(
            "INSERT INTO venture_simulation "
            "  (simulation_id, venture_id, declared_by, reason) "
            "VALUES (%s, %s, %s, 'by hand') RETURNING simulation_id",
            (uuid.uuid4(), VENTURE, FOUNDER),
        )
        simulation_id = cur.fetchone()[0]
    simulated.commit()

    content_hash, api_version = _live(simulated, CRE_MODULES[0])
    with pytest.raises(psycopg.errors.CheckViolation), simulated.cursor() as cur:
        cur.execute(
            "INSERT INTO certification "
            "  (cert_id, unit, rubric_kind, office_agent_id, forge_id, module_id, "
            "   state, certified_tier, instruction_content_hash, forge_api_version, "
            "   rubric_version, basis, simulation_ref) "
            "VALUES (%s, 'A', 'operation', %s, %s, %s, 'certified', 'suggest', "
            "        %s, %s, 'r1', 'simulation', %s)",
            (uuid.uuid4(), ROSTER[0][0], FORGE_ID, CRE_MODULES[0],
             content_hash, api_version, simulation_id),
        )
    simulated.rollback()


# ========================================= bound to the instructions, like any other

async def test_republishing_an_instruction_decertifies_it(simulated):
    """**Load-bearing.** The property that makes a certification worth anything.

    `instruction_content_hash` is the composite over the department's live instruction
    hashes - the same one Gate 8 submits. Without it this would be a certification of
    nothing in particular, valid across any rewrite of the instructions the department
    operates under.
    """
    await _declare()
    await _certify()
    before = _row(simulated)["instruction_content_hash"]

    async with connection() as conn:
        module = _some_module(simulated)
        live = await instructions.live(conn, forge_id=FORGE_ID, module_id=module)
        assert live is not None
        await instructions.author(
            conn, forge_id=FORGE_ID, module_id=module,
            instruction_version="9.9.9",
            forge_api_version=live.forge_api_version,
            version_sensitivity=live.version_sensitivity,
            content={**live.content, "what_it_does": "Changed, on purpose."},
            authored_by=FOUNDER,
        )

    await _certify()
    assert _row(simulated)["instruction_content_hash"] != before, (
        "the basis did not move when an instruction did; this certification would "
        "outlive the text it was issued against"
    )


def _some_module(admin: psycopg.Connection) -> str:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT g.module_id FROM agent_forge_grant g "
            "  JOIN office_agent_identity i USING (office_agent_id) "
            " WHERE g.venture_id = %s AND g.forge_id = %s AND i.department = %s "
            " ORDER BY 1 LIMIT 1",
            (VENTURE, FORGE_ID, DEPARTMENT),
        )
        row = cur.fetchone()
    assert row is not None, "the world granted this department nothing"
    return str(row[0])


# ============================================= void the moment the venture leaves

async def test_leaving_simulation_voids_the_certification(simulated):
    """**THE RULING.** *"...and every simulation certification is void at that point."*

    Nothing edits the row. `state` still reads `certified`, because this system does not
    rewrite a certification - void is derived from the declaration, on every read.
    """
    await _declare()
    await _certify()
    assert _row(simulated)["state"] == "certified"

    await _leave()

    still = _row(simulated)
    assert still["state"] == "certified", "the row was edited; void is derived"
    assert still["basis"] == certification.SIMULATION_BASIS

    async with connection() as conn:
        listed = await certification.simulation_certifications(conn, VENTURE)
    assert listed, "the certification vanished from the report"
    assert all(row["void"] for row in listed)


async def test_a_void_certification_refuses_the_call_path(simulated):
    """Void means void here too. This is the check that runs on every single call.

    A certification Gate 9 would now refuse cannot be one the call path still accepts,
    or the venture leaves simulation and its agents carry on regardless.
    """
    await _declare()
    await _certify()
    grant = _a_grant(simulated)

    await _leave()

    async with connection() as conn:
        with pytest.raises(SimulationCertificationVoid) as raised:
            await resolve_grant(
                conn, office_agent_id=grant["office_agent_id"], forge_id=FORGE_ID,
                module_id=grant["module_id"], venture_id=VENTURE,
            )
    assert "void" in str(raised.value)
    assert "167" in str(raised.value)


def _a_grant(admin: psycopg.Connection) -> dict[str, Any]:
    with admin.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT g.office_agent_id, g.module_id FROM agent_forge_grant g "
            "  JOIN office_agent_identity i USING (office_agent_id) "
            " WHERE g.venture_id = %s AND g.forge_id = %s AND i.department = %s "
            "   AND g.superseded_at IS NULL LIMIT 1",
            (VENTURE, FORGE_ID, DEPARTMENT),
        )
        row = cur.fetchone()
    assert row is not None
    return dict(row)


async def test_declaring_again_does_not_revive_the_old_certification(simulated):
    """A certification is bound to ONE declaration.

    Entry 166 makes re-entering a NEW row with its own name, reason and date. If the
    old certifications revived, leaving would mean nothing - which is the only reading
    under which *"void at that point"* is a rule rather than a pause.
    """
    first = await _declare()
    await _certify()
    await _leave()

    second = await _declare()
    assert second.simulation_id != first.simulation_id

    async with connection() as conn:
        listed = await certification.simulation_certifications(conn, VENTURE)
    assert all(row["void"] for row in listed), (
        "a new declaration revived a certification the old one permitted"
    )


# ================================== every surface says which are simulation-only

async def test_the_report_names_them_and_whether_they_still_stand(simulated):
    """*"Any surface showing a grant, a gate or a sign-off says which of its
    certifications are simulation-only."* This is what those surfaces read."""
    declared = await _declare()
    await _certify()

    async with connection() as conn:
        listed = await certification.simulation_certifications(conn, VENTURE)

    assert [row["department"] for row in listed] == [DEPARTMENT]
    row = listed[0]
    assert row["void"] is False
    assert row["declared_by"] == "Simulation Founder"
    assert row["declared_reason"] == REASON
    assert str(declared.simulation_id)  # the declaration is reachable from the report


async def test_a_grant_says_its_department_is_simulation_only(simulated):
    """The grant surface. `ResolvedGrant` carries it, so it reaches the audit subject
    of every call the grant authorises."""
    await _declare()
    await _certify()
    grant = _a_grant(simulated)

    async with connection() as conn:
        resolved = await resolve_grant(
            conn, office_agent_id=grant["office_agent_id"], forge_id=FORGE_ID,
            module_id=grant["module_id"], venture_id=VENTURE,
        )
    assert resolved.unit_b_simulation_only is True


async def test_a_grant_on_a_real_certification_is_not_marked(simulated):
    """**Load-bearing.** The flag is about this certification, not about the venture.

    The world certifies its positions the ordinary way, so before any simulation
    certification is issued the same grant must read false - otherwise the mark means
    "the venture is in simulation", which is a different and much weaker claim.
    """
    await _declare()
    grant = _a_grant(simulated)

    async with connection() as conn:
        resolved = await resolve_grant(
            conn, office_agent_id=grant["office_agent_id"], forge_id=FORGE_ID,
            module_id=grant["module_id"], venture_id=VENTURE,
        )
    assert resolved.unit_b_simulation_only is False


# ================================================ Gate 9 accepts it, then refuses it

async def _gate_9_outcome(operator: humans.Human, run_id: uuid.UUID):
    """Rewind to Gate 9 and run it through the pipeline.

    Rewinding is test-only, for the reason `test_pipeline._set_run_gate` gives: a
    production caller able to set the current gate could set it to 11 and skip
    certification entirely.
    """
    from broker import provisioning

    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE provisioning_run SET status = 'running', current_gate = '9' "
                " WHERE run_id = %s", (run_id,)
            )
        await conn.commit()
        outcomes = await provisioning.advance(
            conn, run_id=run_id, actor=operator.human_id
        )
    return next(o for o in outcomes if o.gate == "9")


async def test_gate_9_accepts_it_in_simulation_and_refuses_it_after(
    simulated, feasible_pack, operator
):
    """**THE RULING.** *"Gate 9 accepts it while the venture is in simulation and
    refuses it the moment the venture leaves."*

    One run, read twice, with nothing between the two reads except the venture leaving.
    The certification is untouched - Gate 9's answer changes because the permission
    behind it ended, which is the whole of *"void at that point."*
    """
    from broker import provisioning

    await _declare()
    await _certify()

    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )

    accepted = await _gate_9_outcome(operator, run_id)
    assert "SIMULATION-ONLY" in accepted.reason, accepted.reason
    assert accepted.evidence["simulation_only_units"] >= 1
    assert accepted.evidence["simulation_units"], "the units are named, not just counted"
    assert not accepted.evidence["voided_simulation_units"]

    await _leave()

    refused = await _gate_9_outcome(operator, run_id)
    assert refused.verdict == provisioning.BLOCKED, refused.reason
    assert "simulation_certification_void" in str(refused.evidence["states"])
    assert refused.evidence["voided_simulation_units"], (
        "the voided units are named; a reader cannot act on a count"
    )
    assert "VOID" in refused.reason
