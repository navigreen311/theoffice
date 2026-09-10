"""What becomes of a unit-B submission, and the honest answer today: nothing yet.

P-04 opens the run and writes the correlation row. P-03's sweep reads the verdict and
writes the certification. This file is the seam between them, and it is written against
the state that actually obtains rather than the one the pipeline is aiming at.

WHAT THIS ESTABLISHES, AND WHY EACH IS A SEPARATE TEST
======================================================

    **The constraints are live in this database.** CAVEAT 16 - a stamped
    `alembic_version` is not a migrated schema. Every claim below about
    `unit_targets_match` and `rubric_matches_unit` is made by handing PostgreSQL a row
    that violates it and reading the refusal, not by trusting a revision number.

    **A department with no SimForge domain certification reports as UNCERTIFIED, not as
    an error.** This is the state that obtains: no domain certification for any Burkham
    department exists on either side, so the run opens, no verdict arrives, and
    `appointment.generate` refuses the candidates as `missing_unit_b`. A refusal is the
    correct output. A crash, or a certification issued to get past it, would not be.

    **A unit-B PASS cannot be recorded today, and the sweep says so rather than writing
    a certification with no basis.** `sweeps._ingest_one` recovers `forge_api_version`
    only when `unit == "A"` - a department has no module and therefore no
    `forge_operating_instruction` row to recover one from - so a unit-B PASS reaches
    `record_result` with `forge_api_version=None` and the `certified_records_its_basis`
    guard refuses it. That is correct behaviour for a guard and it is also a blocker:
    **no unit-B PASS can be certified until somebody decides where a department's Forge
    api_version comes from.** `forge_registry.api_version` is the obvious answer and
    `broker/sweeps.py` is P-03's, so this file locks the refusal rather than reaching
    for it. When it is fixed, this test is the one that tells you.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from broker import sweeps
from broker.db import connection
from broker.simforge import GateResult, SimForgeError, department_basis_hash
from tests.conftest import drop_forge, requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "unit-b-venture"
DEPARTMENT = "administration"
BASE_URL = "http://simforge.invalid/office"


def _domain_result(verdict: str, *, run_ref: str, tier: str | None = None) -> GateResult:
    """A unit-B verdict, in the shape `gate_result_for` actually returns one.

    `unit="B"` and `rubric_kind="domain"` together, because `rubric_matches_unit` pairs
    them in the schema: two rubrics, never merged, and a composite score cannot be
    written at all rather than being discouraged in review.
    """
    return GateResult(
        run_ref=run_ref,
        unit="B",
        verdict=verdict,
        rubric_kind="domain",
        rubric_version="3.2.0",
        score=0.91 if verdict == "PASS" else None,
        threshold=0.85,
        certified_tier=tier,
        scenario_count=0,
        coverage_denominator=2,
        # A verdict names what answered it. `record_result` refuses one that does
        # not, because `certified_records_its_basis` refuses the row - so a helper
        # omitting it would build a verdict the ingest cannot store, and every test
        # through it would fail for the wrong reason.
        agent_model="ollama/llama3.1:8b",
    )


class FakeSimForge:
    """One coroutine, because the sweep's dependency on SimForge is one coroutine."""

    def __init__(self, verdicts: dict[str, GateResult] | None = None) -> None:
        self.verdicts = verdicts or {}
        self.asked: list[str] = []

    async def office_gate_result(self, conn, *, run_ref: str) -> GateResult:
        self.asked.append(run_ref)
        result = self.verdicts.get(run_ref)
        if result is None:
            raise SimForgeError(f"SimForge has no record of run_ref {run_ref!r}")
        return result

    async def aclose(self) -> None:  # pragma: no cover - injected clients are not owned
        return None


@pytest.fixture
def forge(admin: psycopg.Connection):
    """A Forge with two modules. Rows, never hardcoded - CLAUDE.md's standing rule."""
    forge_id = f"unit-b-forge-{uuid.uuid4().hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'SimForge (unit B)', %s, '1.4.0', 'bearer', 'brokered', 'GREEN')
            """,
            (forge_id, BASE_URL),
        )
        for module_id in ("draw_request", "covenant_check"):
            cur.execute(
                """
                INSERT INTO forge_module_registry
                  (forge_id, module_id, module_name, idempotency_support, is_mutating,
                   compliance_flags_implied)
                VALUES (%s, %s, %s, 'natural', FALSE, '{}')
                """,
                (forge_id, module_id, module_id.replace("_", " ").title()),
            )
    admin.commit()
    yield forge_id
    drop_forge(admin, forge_id)


@pytest.fixture(autouse=True)
def _clean(admin: psycopg.Connection):
    def wipe() -> None:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM sweep_run WHERE sweep_kind = 'verdict_ingest'")
            cur.execute(
                "DELETE FROM curriculum_submission WHERE venture_id = %s", (VENTURE,)
            )
            cur.execute(
                "DELETE FROM certification WHERE unit = 'B' AND department = %s",
                (DEPARTMENT,),
            )
        admin.commit()

    wipe()
    yield
    wipe()


def submit_department(
    conn: psycopg.Connection, *, forge_id: str, run_ref: str | None, hours_ago: float = 1.0
) -> tuple[uuid.UUID, str]:
    """The row P-04's Gate 8 writes for a department: no module, a department, a basis.

    The basis is a `department_basis_hash` and NOT a `forge_operating_instruction`
    hash, which is the honest shape: a department has no operating instruction, so it
    is the set its accepted modules were handed over under.
    """
    submission_id = uuid.uuid4()
    basis = department_basis_hash({"draw_request": "aa" * 32, "covenant_check": "bb" * 32})
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO curriculum_submission
              (submission_id, venture_id, forge_id, module_id, department,
               scenario_pack_ref, scenario_count, coverage_denominator,
               instruction_content_hash, submitted_by, submitted_at, simforge_run_ref)
            VALUES (%s, %s, %s, NULL, %s, %s, 6, 2, %s, %s, %s, %s)
            """,
            (
                submission_id, VENTURE, forge_id, DEPARTMENT,
                f"run:test/dept:{DEPARTMENT}@{forge_id}", basis, uuid.uuid4(),
                datetime.now(UTC) - timedelta(hours=hours_ago), run_ref,
            ),
        )
    conn.commit()
    return submission_id, basis


def certifications(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT unit, department, module_id, office_agent_id, forge_id, state,
                   rubric_kind, rubric_version, simforge_verdict,
                   instruction_content_hash, forge_api_version
            FROM certification WHERE unit = 'B' AND department = %s
            """,
            (DEPARTMENT,),
        )
        cols = [c.name for c in cur.description or []]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


# ---------------------------------------------- the constraints, read off the DB


def test_the_two_unit_constraints_are_live_in_this_database(
    admin: psycopg.Connection, forge: str
):
    """CAVEAT 16: check the column, not the version.

    `theoffice_test` was found stamped four revisions past a constraint it did not
    have. Every other assertion in this file about the unit rule is worth exactly what
    this one is: PostgreSQL is handed a row that breaks each constraint and the refusal
    is read, so a database that had lost them fails here first rather than passing
    everything and proving nothing.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'certification'::regclass "
            "  AND conname IN ('unit_targets_match', 'rubric_matches_unit')"
        )
        assert {r[0] for r in cur.fetchall()} == {
            "unit_targets_match", "rubric_matches_unit",
        }

    insert = """
        INSERT INTO certification
          (cert_id, unit, department, forge_id, state, rubric_kind, rubric_version)
        VALUES (%s, 'B', %s, %s, 'failed', %s, '3.2.0')
    """
    # B with no department: `unit_targets_match` reads `B -> department NOT NULL`.
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="unit_targets_match"),
        admin.cursor() as cur,
    ):
        cur.execute(insert, (uuid.uuid4(), None, forge, "domain"))
    admin.rollback()

    # B against the operation rubric: two rubrics, never merged.
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="rubric_matches_unit"),
        admin.cursor() as cur,
    ):
        cur.execute(insert, (uuid.uuid4(), DEPARTMENT, forge, "operation"))
    admin.rollback()


# ------------------------------------------------ the row the sweep actually writes


async def test_a_unit_b_verdict_lands_as_a_department_certification(
    admin: psycopg.Connection, forge: str
):
    """The whole seam, end to end, on the only verdict that can be recorded today.

    A FAIL, deliberately, and not because a PASS is uninteresting: a PASS cannot be
    recorded at all yet - see `test_a_unit_b_pass_is_refused_...` below - and a test
    that reached for one would be testing a path that does not exist while claiming to
    test this one.

    What it establishes is that the row P-04 writes and the row P-03's sweep writes fit
    together: `department` set, `module_id` NULL, `office_agent_id` NULL,
    `rubric_kind='domain'`. PostgreSQL accepting that row IS the assertion that both
    unit constraints are satisfied - the test above proves it would have refused one
    that was not.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submit_department(admin, forge_id=forge, run_ref=run_ref)
    fake = FakeSimForge({run_ref: _domain_result("FAIL", run_ref=run_ref)})

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert fake.asked == [run_ref], "the sweep did not ask about the department run"
    assert result.status == "passed", result.findings["refused"]
    assert result.findings["rows_written"] == 1

    rows = certifications(admin)
    assert len(rows) == 1
    row = rows[0]
    assert row["unit"] == "B"
    assert row["department"] == DEPARTMENT
    assert row["module_id"] is None, "a unit-B certification naming a module"
    assert row["office_agent_id"] is None, "a unit-B certification naming an agent"
    assert row["rubric_kind"] == "domain"
    assert row["state"] == "failed"
    # `attested_by` is a parameter, not a column. The structural expression of
    # "SimForge said so" is this one, and a bootstrap writes NULL here.
    assert row["simforge_verdict"] == "FAIL"


async def test_the_unit_a_path_is_untouched_by_a_unit_b_submission(
    admin: psycopg.Connection, forge: str
):
    """A department submission must not produce an agent's certification.

    Unit A is `agent x forge x module` and its population is the agents holding a live
    grant on the module. A unit-B row names no module, so there is no such population -
    and a sweep that fell through to the unit-A branch would look for grant holders on
    a NULL module, find none, and report `no_grant_holders` about a submission that
    never had any.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submit_department(admin, forge_id=forge, run_ref=run_ref)
    fake = FakeSimForge({run_ref: _domain_result("FAIL", run_ref=run_ref)})

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert result.findings["no_grant_holders"] == []
    assert result.findings["basis_unrecoverable"] == [], (
        "the sweep tried to recover a Forge api_version for a department, which has no "
        "module to recover one from"
    )
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM certification WHERE unit = 'A' "
                    "AND forge_id = %s", (forge,))
        row = cur.fetchone()
    assert row is not None and row[0] == 0


# ------------------------------------------------- the state that obtains today


async def test_a_department_with_no_domain_certification_reports_uncertified(
    admin: psycopg.Connection, forge: str
):
    """**The test that matters, because this is the state that actually obtains.**

    No domain certification exists in SimForge for any department. So the run is open,
    SimForge has no verdict for it, and the honest outcome is: the sweep completes, no
    certification is written, and the submission stays in the queue. Not an exception,
    not a `never_certified` row invented to fill the gap, and not a sweep failure - a
    verdict that has not arrived is not a sweep that broke.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submission_id, _ = submit_department(admin, forge_id=forge, run_ref=run_ref)
    # Knows about no run at all: `office_gate_result` raises, exactly as a 404 does.
    fake = FakeSimForge({})

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert result.status == "passed", "an unanswered run was reported as a failure"
    assert result.findings["examined"] == 1
    assert result.findings["still_open"] == 1
    assert result.findings["unreadable"], "the refusal was not recorded as a finding"
    assert certifications(admin) == [], (
        "a certification was written for a department SimForge has never certified"
    )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT result_received_at FROM curriculum_submission "
            "WHERE submission_id = %s",
            (submission_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] is None, (
        "the submission was closed against a verdict that never arrived"
    )


async def test_an_unanswered_department_run_times_out_as_b_and_domain(
    admin: psycopg.Connection, forge: str
):
    """Past The Office's own deadline it resolves to TIMEOUT, and TIMEOUT is not a pass.

    `VERDICT_TO_STATE` maps TIMEOUT to `in_training`, so a department whose run hung is
    reported as still in training rather than certified - and the submission is NOT
    closed, because SimForge records a late result against an already-timed-out run and
    The Office must still be asking when it does.

    The unit travels from `submission_unit`, so a run opened as B can only time out as
    B. A TIMEOUT that resolved to unit A would write into `(office_agent_id, forge_id,
    module_id)` with all three NULL.
    """
    submission_id, _ = submit_department(admin, forge_id=forge, run_ref=None, hours_ago=48)
    fake = FakeSimForge({})

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert result.findings["timed_out"] == 1
    assert result.findings["by_verdict"] == {"TIMEOUT": 1}

    rows = certifications(admin)
    assert len(rows) == 1
    assert rows[0]["state"] == "in_training", "a hung department run certified something"
    assert rows[0]["rubric_kind"] == "domain"
    assert rows[0]["simforge_verdict"] == "TIMEOUT"

    with admin.cursor() as cur:
        cur.execute(
            "SELECT result_received_at FROM curriculum_submission "
            "WHERE submission_id = %s",
            (submission_id,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] is None, (
        "a TIMEOUT closed the submission against a verdict SimForge is still holding open"
    )


async def test_a_unit_b_pass_is_refused_rather_than_certified_without_a_basis(
    admin: psycopg.Connection, forge: str
):
    """**The successor blocker, measured rather than argued.**

    A `certified` certification must record the instruction hash, the Forge api_version
    and the certified tier, or staleness is uncomputable and the certification is
    permanent by accident. `sweeps._ingest_one` recovers the api_version only for
    unit A - a department has no module and therefore no `forge_operating_instruction`
    row - so a unit-B PASS arrives with `forge_api_version=None` and is refused.

    **The refusal is right and the gap is real.** No department can be certified until
    somebody rules where a department's Forge api_version comes from;
    `forge_registry.api_version` is already read by `SimForgeClient._registry` and is
    the obvious answer. `broker/sweeps.py` and `broker/certification.py` are P-03's, so
    this locks the current behaviour instead: **the sweep must never resolve this by
    writing a certified row with no basis.** When the gap is closed, this test is what
    tells whoever closed it that the behaviour changed on purpose.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submit_department(admin, forge_id=forge, run_ref=run_ref)
    fake = FakeSimForge(
        {run_ref: _domain_result("PASS", run_ref=run_ref, tier="propose")}
    )

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert certifications(admin) == [], (
        "a department was certified with no Forge api_version: the certification's "
        "basis is unknown and it can never be recomputed or expired"
    )
    assert result.findings["refused"], "the refusal was not reported"
    assert "api_version" in result.findings["refused"][0]["reason"]
    assert result.status == "failed", (
        "a verdict arrived and no certification could be written for it - that is this "
        "sweep failing at its one job, and it must say so"
    )
