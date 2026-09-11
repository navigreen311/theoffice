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

    **A unit-B PASS records, as of B36 half two, and the basis is the SET.** This file
    used to lock a refusal here: `sweeps._ingest_one` recovered `forge_api_version` only
    when `unit == "A"`, so a unit-B PASS reached `record_result` with
    `forge_api_version=None` and `certified_records_its_basis` refused it. The guard was
    right and the omission was the defect.

    **The department's members are now stored** (`curriculum_submission_module`,
    migration 0037), because `department_basis_hash` is one-way and the composite cannot
    name what it was composed of. Each member resolves through the same reconstruction
    unit A uses - the instruction row in force at `submitted_at` - and
    `certification.department_api_version` requires them to AGREE.

    **`forge_registry.api_version` was NOT taken**, though it is available and was once
    called the obvious answer. It is the version live now, not the version anything was
    judged against, which is the staleness `certified_records_its_basis` exists to
    prevent. The tests below cover both halves of the rule: agreement records, and
    disagreement refuses rather than picking one.
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

#: The department's two modules. Their instruction hashes are NOT written here: a
#: `BEFORE INSERT` trigger computes `content_hash` from `content`, so a literal would be
#: a value the database immediately overrules - and the `forge` fixture below already
#: says "rows, never hardcoded". The hashes come back from `RETURNING content_hash` and
#: reach the tests through the `members` fixture.
MEMBER_MODULES = ("draw_request", "covenant_check")

#: What both members' instructions carry, and therefore what a department certified from
#: them must record. Deliberately NOT the `forge_registry.api_version` the fixture sets,
#: so a test asserting this cannot be satisfied by the weaker source.
MEMBER_API_VERSION = "2.2.0"


def _instruction_content(module_id: str) -> dict:
    """A valid operating instruction. `instruction_has_all_sections` requires all eight.

    The text differs per module so the two get DIFFERENT content hashes - which is the
    point of a set, and a shared hash would make a two-member basis indistinguishable
    from a one-member one.
    """
    return {
        "what_it_does": f"Handles {module_id.replace('_', ' ')} for the department.",
        "what_it_does_not_do": f"Does not decide anything outside {module_id}.",
        "inputs": {"reference": "an opaque id"},
        "correct_sequence": ["receive", module_id, "return"],
        "failure_signatures": {"silent_partial": "200 with an empty body"},
        "retry_vs_escalate": "Retry 5xx twice; escalate any 4xx.",
        "never_do": [f"Never {module_id} twice for one reference"],
        "compliance_coupling": [],
    }


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
        for module_id in MEMBER_MODULES:
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


@pytest.fixture
def members(admin: psycopg.Connection, forge: str) -> dict[str, str]:
    """`{module_id: content_hash}` for the department's two modules.

    The instruction each module was handed over under, authored two days ago so it is in
    force at any `submitted_at` these tests use and never superseded - the unit-A
    recovery this reuses asks for the row in force AT THE SUBMISSION, not the row live
    today. The hash is read back from the trigger rather than supplied, because
    supplying one writes a value the database overrules and the test would then be
    resolving a hash no row carries.
    """
    return author_instructions(admin, forge, MEMBER_API_VERSION)


def author_instructions(
    admin: psycopg.Connection, forge_id: str, api_version: str | dict[str, str]
) -> dict[str, str]:
    """Author one instruction per member module and return their content hashes.

    `api_version` may be one string for both, or a per-module mapping - which is what
    the disagreement test needs, and the reason this is a function rather than only a
    fixture.
    """
    versions = (
        api_version if isinstance(api_version, dict)
        else dict.fromkeys(MEMBER_MODULES, api_version)
    )
    hashes: dict[str, str] = {}
    with admin.cursor() as cur:
        for module_id in MEMBER_MODULES:
            cur.execute(
                """
                INSERT INTO forge_operating_instruction
                  (forge_id, module_id, instruction_version, forge_api_version,
                   version_sensitivity, content, content_hash, authored_by, authored_at)
                VALUES (%s, %s, '1.0.0', %s, 'major.minor', %s, '', %s, %s)
                RETURNING content_hash
                """,
                (forge_id, module_id, versions[module_id],
                 psycopg.types.json.Jsonb(_instruction_content(module_id)),
                 uuid.uuid4(), datetime.now(UTC) - timedelta(days=2)),
            )
            row = cur.fetchone()
            assert row is not None
            hashes[module_id] = row[0]
    admin.commit()
    assert len(set(hashes.values())) == len(MEMBER_MODULES), (
        "the two members got the same content hash, so a two-member basis is "
        "indistinguishable from a one-member one and the test proves less than it says"
    )
    return hashes


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
    conn: psycopg.Connection, *, forge_id: str, run_ref: str | None, hours_ago: float = 1.0,
    members: dict[str, str] | None = None,
) -> tuple[uuid.UUID, str]:
    """The row P-04's Gate 8 writes for a department: no module, a department, a basis.

    The basis is a `department_basis_hash` and NOT a `forge_operating_instruction`
    hash, which is the honest shape: a department has no operating instruction, so it
    is the set its accepted modules were handed over under.

    **And the members, in the same transaction** (migration 0037). Passing `members=None`
    writes none, which is not a convenience - it is the shape of every unit-B row
    submitted before 0037, and one test needs exactly that row to prove those still
    refuse rather than certifying against a set nobody recorded.
    """
    submission_id = uuid.uuid4()
    members = {} if members is None else members
    # A submission with no members still needs a basis - that is the pre-0037 shape, and
    # the placeholder is what such a row actually carried: a composite over hashes that
    # nothing recorded.
    basis = department_basis_hash(members or {"draw_request": "aa" * 32})
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
        for module_id, content_hash in sorted(members.items()):
            cur.execute(
                "INSERT INTO curriculum_submission_module "
                "(submission_id, module_id, instruction_content_hash) VALUES (%s,%s,%s)",
                (submission_id, module_id, content_hash),
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
    admin: psycopg.Connection, forge: str, members: dict[str, str]
):
    """A department submission must not produce an agent's certification.

    Unit A is `agent x forge x module` and its population is the agents holding a live
    grant on the module. A unit-B row names no module, so there is no such population -
    and a sweep that fell through to the unit-A branch would look for grant holders on
    a NULL module, find none, and report `no_grant_holders` about a submission that
    never had any.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submit_department(admin, forge_id=forge, run_ref=run_ref, members=members)
    fake = FakeSimForge({run_ref: _domain_result("FAIL", run_ref=run_ref)})

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert result.findings["no_grant_holders"] == []
    # The basis IS recoverable now (B36 half two): the members are stored and their
    # instructions agree. This assertion used to read "a department has no module to
    # recover one from", which was true of the old gate and is not true of this one.
    assert result.findings["basis_unrecoverable"] == [], result.findings
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


async def test_members_judged_against_different_api_versions_are_refused(
    admin: psycopg.Connection, forge: str
):
    """**The half of the rule with no natural fixture, and the reason it is a rule.**

    Every Forge in this database carries exactly one live `forge_api_version` today, so
    nothing in the real data exercises this. That is a fact about four Forges on one
    day, not a property: `forge_api_version` is NOT NULL per
    `(forge_id, module_id, instruction_version)` row and nothing constrains two modules
    of one department to agree. So the disagreement is constructed.

    **The set IS the basis.** When the members disagree there is no single version the
    department was judged against, and `max()` or a first row would make the basis an
    artefact of query order - which is the argument `forge_api_version_in_force` already
    makes one level down, about two instructions carrying one hash.

    A FAIL would still be recordable (a FAIL cannot go stale and needs no basis); this
    uses a PASS because that is the verdict the guard exists to stop.
    """
    disagreeing = author_instructions(
        admin, forge, {"draw_request": "2.2.0", "covenant_check": "3.0.0"}
    )
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submit_department(admin, forge_id=forge, run_ref=run_ref, members=disagreeing)
    fake = FakeSimForge(
        {run_ref: _domain_result("PASS", run_ref=run_ref, tier="propose")}
    )

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert certifications(admin) == [], (
        "a department was certified against one of two api_versions its modules were "
        "judged under - the basis has two answers and is therefore not a basis"
    )
    unrecoverable = result.findings["basis_unrecoverable"]
    assert len(unrecoverable) == 1, result.findings
    reason = unrecoverable[0]["reason"]
    # Names BOTH versions and which modules carried them. A refusal that said only
    # "could not recover" would send a reader to look for a missing row.
    assert "2 different Forge api_versions" in reason, reason
    assert "2.2.0: draw_request" in reason and "3.0.0: covenant_check" in reason, reason


async def test_a_submission_with_no_members_is_refused_rather_than_guessed(
    admin: psycopg.Connection, forge: str
):
    """Every unit-B row written before migration 0037 has this shape.

    The composite hash does not name what it was composed of, so there is nothing to
    resolve and nothing to fall back to - `forge_registry.api_version` would answer with
    the version live today, which is not the version anything was judged against.

    **Refused, not guessed.** A certification whose basis was supplied to satisfy the
    guard is the permanent-by-accident row the guard exists to prevent.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    submit_department(admin, forge_id=forge, run_ref=run_ref, members=None)
    fake = FakeSimForge(
        {run_ref: _domain_result("PASS", run_ref=run_ref, tier="propose")}
    )

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert certifications(admin) == []
    assert len(result.findings["basis_unrecoverable"]) == 1, result.findings
    assert "no member modules" in result.findings["basis_unrecoverable"][0]["reason"]


async def test_a_unit_b_pass_records_the_api_version_its_members_agree_on(
    admin: psycopg.Connection, forge: str, members: dict[str, str]
):
    """**B36 half two, closed.** This test used to lock the refusal it now replaces.

    A `certified` certification must record the instruction hash, the Forge api_version
    and the certified tier, or staleness is uncomputable and the certification is
    permanent by accident. The sweep recovered the api_version only for unit A, so a
    unit-B PASS arrived with `forge_api_version=None` and `certified_records_its_basis`
    refused it. **The guard was right and the omission was the defect.**

    A department has no operating instruction, so there is nothing to look up - but its
    members do, and migration 0037 stores which members composed the basis because
    `department_basis_hash` is one-way. Each resolves through the SAME reconstruction
    unit A uses, and when they agree that value is what the department was judged
    against.

    The assertion that matters is the last one: the version recorded is the members'
    (`1.4.0` from their instructions), not the Forge's live
    `forge_registry.api_version`. Those are equal here by construction of the fixture,
    so the test pins the row the value came FROM rather than the value itself - a test
    that only checked the string would pass just as well against the weaker source.
    """
    run_ref = f"office:{VENTURE}:{forge}:dept:{DEPARTMENT}:abcdef012345"
    _submission_id, basis = submit_department(
        admin, forge_id=forge, run_ref=run_ref, members=members
    )
    fake = FakeSimForge(
        {run_ref: _domain_result("PASS", run_ref=run_ref, tier="propose")}
    )

    async with connection() as conn:
        result = await sweeps.sweep_verdict_ingest(conn, client=fake)

    assert not result.findings.get("refused"), result.findings
    assert not result.findings.get("basis_unrecoverable"), result.findings

    rows = certifications(admin)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["state"] == "certified", row
    assert row["forge_api_version"] == MEMBER_API_VERSION
    assert row["instruction_content_hash"] == basis, (
        "the certification must record the COMPOSITE as its hash - the department was "
        "judged against the set, and a member's hash would name one of them"
    )

    # Where the value came from, not merely what it is. Both members' instructions are
    # read; the registry row is a different fact and is not consulted.
    with admin.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT forge_api_version FROM forge_operating_instruction "
            "WHERE forge_id = %s AND module_id = ANY(%s)",
            (forge, sorted(members)),
        )
        from_members = sorted(r[0] for r in cur.fetchall())
    assert from_members == [MEMBER_API_VERSION], from_members
