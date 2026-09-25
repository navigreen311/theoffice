"""A TIMEOUT replaces nothing.

RULED 23 SEPTEMBER 2026 (decisions entry 183)
=============================================

    *"A TIMEOUT replaces nothing. It is the absence of an answer, not an answer. Ingest
    records it without overwriting a certification's basis, state or references. A PASS
    or FAIL still supersedes, per entry 167. Measured: three unit-B TIMEOUTs from a
    blocked run erased two simulation certifications within three minutes of a named
    human writing them, and had been doing so every three minutes."*

WHAT HAPPENED
=============

    Run `d59650aa` blocked at Gate 9 and will not advance. Its three open department
    submissions pass The Office's own deadline, `verdict_ingest` synthesises a TIMEOUT
    for each, and `record_result`'s upsert replaced everything on the row: `basis`,
    `state`, `scenario_pack_ref`, `simulation_ref`, `certified_tier`.

    So `operations` and `research`, certified for simulation by Ivan Green at 19:32,
    read `in_training / tested / TIMEOUT` at 19:35, again at 19:38, and again at 19:41.

THE TWO THAT CARRY THE RULING
=============================

    `test_a_timeout_leaves_a_standing_certification_alone` - the case measured.
    `test_a_pass_still_supersedes` - entry 167, unchanged.
"""

from __future__ import annotations

import uuid

import pytest

from broker import certification
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

FORGE = "probe-forge"
HASH_A = "a" * 64
HASH_B = "b" * 64

#: Enough of ADR-0060's model identity for a real verdict to be recorded.
MODEL = {
    "file_digest": "sha256:" + "c" * 64,
    "settings": {"temperature": 0.0, "max_tokens": 1024},
}


@pytest.fixture(autouse=True)
async def _clean():
    yield
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM certification WHERE forge_id LIKE 'probe-forge%'")
            await cur.execute(
                "DELETE FROM office_agent_identity WHERE department LIKE 'probe-%'")
        await conn.commit()


async def _agent(conn) -> uuid.UUID:
    agent_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_agent_identity (office_agent_id, agent_name, "
            "  village_agent_ref, department, status) "
            "VALUES (%s, %s, %s, %s, 'active')",
            (agent_id, f"Probe {str(agent_id)[:8]}", f"probe_{str(agent_id)[:8]}",
             f"probe-{uuid.uuid4().hex[:8]}"))
    return agent_id


async def _row(conn, *, department=None, agent_id=None):
    async with conn.cursor() as cur:
        if department is not None:
            await cur.execute(
                "SELECT cert_id::text, state, basis, certified_tier, simforge_verdict, "
                "       scenario_pack_ref, simulation_ref, instruction_content_hash "
                "  FROM certification WHERE unit='B' AND forge_id=%s AND department=%s",
                (FORGE, department))
        else:
            await cur.execute(
                "SELECT cert_id::text, state, basis, certified_tier, simforge_verdict, "
                "       scenario_pack_ref, simulation_ref, instruction_content_hash "
                "  FROM certification WHERE unit='A' AND forge_id=%s "
                "   AND office_agent_id=%s", (FORGE, agent_id))
        return await cur.fetchone()


async def _standing_cert(conn, department: str, *, basis: str = "tested",
                         state: str = "certified") -> uuid.UUID:
    """A unit-B row the TIMEOUT below will be asked to replace.

    **NOT `basis = 'simulation'`, and the reason is a constraint rather than a
    preference.** A simulation certification needs a `venture_simulation` row, that
    table refuses DELETE by trigger (entry 166), and the row would pin its declarer's
    account forever - which is the shape `tests/conftest.py` already records for
    `compliance_library_entry`, where a held-down author broke `DELETE FROM
    office_human` in suites that touch neither table. Leaving one here would do it
    again, to every suite.

    **The guard does not read `basis`.** It reads the standing row on the upsert's own
    key and returns it untouched, so `tested`, `attested`, `bootstrap` and `simulation`
    take one path. `test_the_guard_does_not_look_at_the_basis` pins that, and the
    measured case - two simulation certifications erased every three minutes - is this
    same code path with a different value in a column nothing here branches on.
    """
    cert_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO certification (cert_id, unit, rubric_kind, forge_id, "
            "  department, state, certified_tier, instruction_content_hash, "
            "  forge_api_version, rubric_version, scenario_pack_ref, basis, "
            "  simforge_verdict, agent_model, model_digest, model_temperature, "
            "  model_max_tokens) "
            "VALUES (%s, 'B', 'domain', %s, %s, %s, 'propose', %s, '1.0.0', "
            "        '0.5.0', 'run:earlier/departments', %s, %s, %s, %s, 0.0, 1024)",
            (cert_id, FORGE, department, state, HASH_B, basis,
             "PASS" if basis == "tested" else None,
             "probe-model" if basis == "tested" else None,
             "sha256:" + "c" * 64 if basis == "tested" else None))
    return cert_id


# ======================================================== the ruling

async def test_a_timeout_leaves_a_standing_certification_alone():
    """**THE RULING**, in the shape measured on `operations` and `research`."""
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        cert_id = await _standing_cert(conn, department)
        await conn.commit()
        before = await _row(conn, department=department)

        state = await certification.record_result(
            conn, unit="B", forge_id=FORGE, department=department,
            verdict="TIMEOUT", rubric_version="none: the run did not answer",
            instruction_content_hash=HASH_A,
            scenario_pack_ref="run:d59650aa/departments")

        after = await _row(conn, department=department)
        assert after == before, "the TIMEOUT replaced something"
        assert str(state.cert_id) == str(cert_id)
        assert state.state == "certified"
        assert after[2] == "tested", "basis was overwritten"
        assert after[4] == "PASS", "simforge_verdict was overwritten"


async def test_a_pass_still_supersedes():
    """**Entry 167, unchanged.** A real answer is a new answer to the same question."""
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _standing_cert(conn, department)
        await conn.commit()

        await certification.record_result(
            conn, unit="B", forge_id=FORGE, department=department,
            verdict="PASS", rubric_version="0.5.0",
            certified_tier="propose", instruction_content_hash=HASH_A,
            forge_api_version="1.4.0", scenario_pack_ref="run:real/departments",
            agent_model="probe-model", model_identity=MODEL)

        after = await _row(conn, department=department)
        assert after[1] == "certified"
        assert after[2] == "tested"
        assert after[4] == "PASS"
        assert after[5] == "run:real/departments", "the pack ref did not move"


async def test_a_fail_still_supersedes():
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _standing_cert(conn, department)
        await conn.commit()

        await certification.record_result(
            conn, unit="B", forge_id=FORGE, department=department,
            verdict="FAIL", rubric_version="0.5.0",
            instruction_content_hash=HASH_A, scenario_pack_ref="run:real/departments",
            agent_model="probe-model", model_identity=MODEL)

        after = await _row(conn, department=department)
        assert (after[1], after[2], after[4]) == ("failed", "tested", "FAIL")


# ======================================================== recording, not replacing

async def test_a_first_certification_is_still_written_on_a_timeout():
    """**Replacement, not recording.**

    A department with no row at all, whose run timed out, IS `in_training` - there is
    nothing to preserve and the row says the honest thing.
    """
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        assert await _row(conn, department=department) is None

        await certification.record_result(
            conn, unit="B", forge_id=FORGE, department=department,
            verdict="TIMEOUT", rubric_version="none: the run did not answer",
            instruction_content_hash=HASH_A,
            scenario_pack_ref="run:probe/departments")

        after = await _row(conn, department=department)
        assert after is not None
        assert (after[1], after[2], after[4]) == ("in_training", "tested", "TIMEOUT")


async def test_repeated_timeouts_change_nothing_after_the_first():
    """The three-minute cycle that did the damage, run twice against a standing row."""
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _standing_cert(conn, department)
        await conn.commit()
        before = await _row(conn, department=department)

        for _ in range(3):
            await certification.record_result(
                conn, unit="B", forge_id=FORGE, department=department,
                verdict="TIMEOUT", rubric_version="none: the run did not answer",
                instruction_content_hash=HASH_A,
                scenario_pack_ref="run:d59650aa/departments")

        assert await _row(conn, department=department) == before


# ======================================================== both units

async def test_unit_a_is_covered_too():
    """The ruling names a certification, not a unit, and the argument is the same.

    A `certified` agent whose re-exam timed out has not been shown to have got worse.
    `recompute_staleness` is what moves a certification the instructions have outrun.
    """
    async with connection() as conn:
        agent_id = await _agent(conn)
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO forge_registry (forge_id, display_name, base_url, "
                "  api_version, auth_model, credential_mode, health_status) "
                "VALUES (%s, %s, 'http://probe.invalid', '1.0.0', 'bearer', "
                "        'brokered', 'GREEN') ON CONFLICT DO NOTHING", (FORGE, FORGE))
        await certification.record_result(
            conn, unit="A", forge_id=FORGE, office_agent_id=agent_id,
            module_id="alpha", verdict="PASS", rubric_version="0.5.0",
certified_tier="propose",
            instruction_content_hash=HASH_A, forge_api_version="1.0.0",
            scenario_pack_ref="run:probe/alpha", agent_model="probe-model", model_identity=MODEL)
        before = await _row(conn, agent_id=agent_id)
        assert before[1] == "certified"

        await certification.record_result(
            conn, unit="A", forge_id=FORGE, office_agent_id=agent_id,
            module_id="alpha", verdict="TIMEOUT",
            rubric_version="none: the run did not answer",
            instruction_content_hash=HASH_B, scenario_pack_ref="run:late/alpha")

        assert await _row(conn, agent_id=agent_id) == before


# ======================================================== the reasoning, pinned

def test_the_guard_asks_the_same_key_the_upsert_conflicts_on():
    """Otherwise it would preserve a row the INSERT was never going to replace."""
    import inspect

    source = inspect.getsource(certification.record_result)
    assert "office_agent_id = %s AND module_id = %s" in source
    assert 'target = "department = %s"' in source


def test_the_guard_is_the_rule_and_not_the_word():
    """**Entry 184 corrects entry 183, and this test is where it was wrong.**

    183 shipped `if verdict == "TIMEOUT"` and a test asserting that IN_PROGRESS and
    NOT_RUN were deliberately NOT guarded - on the reasoning that those are "states
    SimForge reports about a run it HAS", a different fact from the sweep saying
    nobody replied.

    That distinction is true about provenance and was wrong about consequence.
    Measured within the hour: three IN_PROGRESS department units from run `844a5b01`
    erased both simulation certifications, and Gate 9 went from five blockers to ten.
    """
    assert {"TIMEOUT", "IN_PROGRESS", "NOT_RUN"} == certification.NOT_AN_ANSWER


def test_an_answer_still_supersedes():
    """PROVISIONAL and REVOKED are answers and are not guarded.

    A PROVISIONAL is a battery that ran and WITHHELD; a REVOKED is a withdrawal. Both
    reduce standing, and a guard against erasure must not become a guard against
    demotion - `buyer_match`/Ronan went `certified` -> `provisional` today carrying
    `the_competence_half_did_not_run`, and blocking that would have left the row
    reading certified while SimForge had withheld it.
    """
    for answer in ("PASS", "FAIL", "PROVISIONAL", "REVOKED"):
        assert answer not in certification.NOT_AN_ANSWER
    # And every one of them still maps to a state, so none is silently unreachable.
    for answer in certification.NOT_AN_ANSWER:
        assert answer in certification.VERDICT_TO_STATE


async def test_the_guard_does_not_look_at_the_basis():
    """**Why the measured case is covered without a `venture_simulation` row.**

    `simulation`, `attested` and `bootstrap` all take the same path: the guard reads
    the standing row on the upsert's own key and returns it. Nothing branches on
    `basis`, so a simulation certification is preserved by the identical code these
    assertions exercise.
    """
    import inspect

    source = inspect.getsource(certification.record_result)
    guard = source[source.index("if verdict in NOT_AN_ANSWER:"):]
    guard = guard[:guard.index("return CertState")]
    # Comments stripped: the rule is about what the code reads, and the comment there
    # says `basis` is deliberately not read.
    code = " ".join(
        line for line in guard.splitlines() if not line.strip().startswith("#"))
    assert "basis" not in code, (
        "the guard reads or branches on basis; it must preserve every row alike")

    # `bootstrap` rather than `attested`: an attested row needs an `attestation_ref`
    # (`an_attested_certification_names_its_attestation`), and building one would test
    # that constraint rather than this guard.
    for basis, state in (("bootstrap", "certified"),):
        department = f"probe-{uuid.uuid4().hex[:8]}"
        async with connection() as conn:
            await _standing_cert(conn, department, basis=basis, state=state)
            await conn.commit()
            before = await _row(conn, department=department)

            await certification.record_result(
                conn, unit="B", forge_id=FORGE, department=department,
                verdict="TIMEOUT", rubric_version="none: the run did not answer",
                instruction_content_hash=HASH_A,
                scenario_pack_ref="run:d59650aa/departments")

            assert await _row(conn, department=department) == before, basis


@pytest.mark.parametrize("verdict", sorted(certification.NOT_AN_ANSWER))
async def test_no_non_answer_replaces_a_standing_certification(verdict):
    """**THE RULING.** All three, against the same standing row.

    IN_PROGRESS is the one that was measured erasing two simulation certifications
    while the guard for TIMEOUT was already merged.
    """
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await _standing_cert(conn, department)
        await conn.commit()
        before = await _row(conn, department=department)

        await certification.record_result(
            conn, unit="B", forge_id=FORGE, department=department,
            verdict=verdict, rubric_version="none: the run did not answer",
            instruction_content_hash=HASH_A,
            scenario_pack_ref="run:844a5b01/departments")

        assert await _row(conn, department=department) == before, verdict


@pytest.mark.parametrize("verdict", sorted(certification.NOT_AN_ANSWER))
async def test_a_first_certification_is_still_written_for_each(verdict):
    """Replacement, not recording - and that holds for all three."""
    department = f"probe-{uuid.uuid4().hex[:8]}"
    async with connection() as conn:
        await certification.record_result(
            conn, unit="B", forge_id=FORGE, department=department,
            verdict=verdict, rubric_version="none: the run did not answer",
            instruction_content_hash=HASH_A,
            scenario_pack_ref="run:probe/departments")

        row = await _row(conn, department=department)
        assert row is not None, verdict
        assert row[4] == verdict
