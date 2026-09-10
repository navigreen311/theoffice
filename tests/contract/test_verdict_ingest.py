"""The unit-A verdict return path: a sweep, not a route.

Until this landed there was **no code anywhere that turned a SimForge verdict into a
certification row.** `certification.record_result` had one non-test caller - the Phase
0.8 bootstrap, which issues grants nobody earned and says so in `bootstrap_reason`. So
every control downstream of certification was enforcing a table that only a bootstrap
could write to, and `attested_by="simforge"` appeared nowhere in the repository.

WHY A SWEEP AND NOT AN INBOUND ROUTE
====================================

    `overdue_submissions`' own docstring rules it: "a control that depends on the
    failing component to announce its own failure is not a control." A route would have
    SimForge announcing the value that grants an agent production authority, over a path
    that goes quiet in exactly the case the control exists for. The Office asks.

WHAT THESE TESTS ARE CAREFUL ABOUT
==================================

    **The guard is exercised, never routed around.** `record_result` refuses a
    `certified` row lacking the instruction hash, the Forge api_version or the certified
    tier, and `certified_records_its_basis` backs it in the schema. One test drives a
    PASS verdict at a submission whose basis cannot be recovered and asserts the refusal
    plus zero rows - not a row with a placeholder api_version, which is the
    permanent-by-accident certification the guard exists to prevent.

    **A timeout does not close the submission.** SimForge records a verdict arriving
    after a run has timed out and leaves `timedOutAt` in place, because "a result that
    ARRIVED is better evidence than a deadline that passed". If The Office stamped
    `result_received_at` on a TIMEOUT it would stop asking while SimForge was still
    answering. `test_a_late_verdict_beats_a_recorded_timeout` is the one to keep.

    **`attested_by` is a parameter, not a column.** There is no `certification.attested_by`.
    The structural expression of "SimForge said so" is `simforge_verdict IS NOT NULL` -
    `record_result` writes the verdict there for a SimForge attestation and NULL for a
    bootstrap, precisely so the query cannot be defeated by a naming convention. These
    tests assert on that column.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import psycopg
import pytest

from broker import sweeps
from broker.db import connection
from broker.simforge import GateResult, SimForgeClient, SimForgeError
from tests.conftest import drop_forge, requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "verdict-ingest-venture"
BASE_URL = "http://simforge.invalid/office"

#: The eight Part 6.1 sections `instruction_has_all_sections` requires. Content is
#: irrelevant to this suite; its HASH is the whole subject, and the trigger computes
#: that from the content rather than accepting it, so two rows with identical content
#: get identical hashes without anything here asserting they do.
INSTRUCTION_CONTENT = {
    "what_it_does": "parses a document",
    "what_it_does_not_do": "does not file one",
    "inputs": "a document ref",
    "correct_sequence": "fetch, parse, return",
    "failure_signatures": "422 on an unreadable file",
    "retry_vs_escalate": "retry once, then escalate",
    "never_do": "never invent a field",
    "compliance_coupling": "none",
}


def _gate_result(verdict: str, *, run_ref: str, tier: str | None = None) -> GateResult:
    return GateResult(
        run_ref=run_ref,
        unit="A",
        verdict=verdict,
        rubric_kind="operation",
        rubric_version="2.3.1",
        score=0.94 if verdict == "PASS" else None,
        threshold=0.85,
        certified_tier=tier,
        scenario_count=24,
        coverage_denominator=24,
        # A verdict names what answered it. `record_result` refuses one that does
        # not, because `certified_records_its_basis` refuses the row - so a helper
        # omitting it would build a verdict the ingest cannot store, and every test
        # through it would fail for the wrong reason.
        agent_model="ollama/llama3.1:8b",
    )


class FakeSimForge:
    """Stands in for the Office-signed verdict read, and records what was asked.

    The sweep's dependency on SimForge is exactly one coroutine, so the seam is one
    coroutine. Injecting it keeps these tests about the ingest rather than about httpx -
    `test_the_verdict_read_is_signed_as_the_office` covers the wire separately.
    """

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


# ------------------------------------------------------------------------- fixtures


@pytest.fixture
def forge(admin: psycopg.Connection):
    """A Forge and one module. Rows, never hardcoded - CLAUDE.md's standing rule."""
    forge_id = f"simforge-test-{uuid.uuid4().hex[:8]}"
    module_id = "parse_document"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'SimForge (test)', %s, '1.4.0', 'bearer', 'brokered', 'GREEN')
            """,
            (forge_id, BASE_URL),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating,
               compliance_flags_implied)
            VALUES (%s, %s, 'Parse Document', 'natural', FALSE, '{}')
            """,
            (forge_id, module_id),
        )
    admin.commit()
    yield forge_id, module_id
    drop_forge(admin, forge_id)


@pytest.fixture(autouse=True)
def _clean_sweep_runs(admin: psycopg.Connection):
    """`sweep_run` is global state and the denominator assertions read it back."""
    _wipe_sweeps(admin)
    yield
    _wipe_sweeps(admin)


def _wipe_sweeps(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM sweep_run WHERE sweep_kind = 'verdict_ingest'")
    conn.commit()


def publish_instruction(
    conn: psycopg.Connection,
    *,
    forge_id: str,
    module_id: str,
    instruction_version: str,
    forge_api_version: str,
    authored_at: datetime,
    superseded_at: datetime | None = None,
    content: dict | None = None,
) -> str:
    """Insert one instruction row and return the hash the TRIGGER computed.

    Returned rather than supplied: `set_instruction_hash` overwrites whatever a caller
    passes, "because a supplied hash is a claim; this is a fact". A test that asserted
    against a hash it invented would be asserting against its own arithmetic.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_operating_instruction
              (forge_id, module_id, instruction_version, forge_api_version,
               content, content_hash, authored_by, authored_at, superseded_at)
            VALUES (%s, %s, %s, %s, %s, '', %s, %s, %s)
            RETURNING content_hash
            """,
            (
                forge_id, module_id, instruction_version, forge_api_version,
                json.dumps(content or INSTRUCTION_CONTENT), uuid.uuid4(),
                authored_at, superseded_at,
            ),
        )
        row = cur.fetchone()
    conn.commit()
    assert row is not None
    return str(row[0])


def grant(
    conn: psycopg.Connection, *, agent_id: uuid.UUID, forge_id: str, module_id: str
) -> uuid.UUID:
    """An issued, unactivated grant - the state Gate 7 requires before Gate 8 submits.

    `operation_cert_ref` is deliberately NULL. It is written at grant issuance and this
    sweep does not touch it: the call path finds a certification by
    `(office_agent_id, forge_id, module_id)` (`broker/grants.py`), and asserting through
    a pointer this package does not write would test the wrong join.
    """
    grant_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_forge_grant
              (grant_id, office_agent_id, forge_id, module_id, venture_id,
               trust_tier, granted_by)
            VALUES (%s, %s, %s, %s, %s, 'propose', %s)
            """,
            (grant_id, agent_id, forge_id, module_id, VENTURE, uuid.uuid4()),
        )
    conn.commit()
    return grant_id


def submit(
    conn: psycopg.Connection,
    *,
    forge_id: str,
    module_id: str,
    content_hash: str,
    run_ref: str | None,
    hours_ago: float,
) -> uuid.UUID:
    submission_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO curriculum_submission
              (submission_id, venture_id, forge_id, module_id, scenario_pack_ref,
               scenario_count, coverage_denominator, instruction_content_hash,
               submitted_by, submitted_at, simforge_run_ref)
            VALUES (%s, %s, %s, %s, %s, 24, 24, %s, %s, %s, %s)
            """,
            (
                submission_id, VENTURE, forge_id, module_id,
                f"run:test/{module_id}", content_hash, uuid.uuid4(),
                datetime.now(UTC) - timedelta(hours=hours_ago), run_ref,
            ),
        )
    conn.commit()
    return submission_id


def cert_rows(conn: psycopg.Connection, agent_id: uuid.UUID) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT state, certified_tier, instruction_content_hash, forge_api_version, "
            "       simforge_verdict, rubric_version, rubric_kind, score, scenario_pack_ref "
            "FROM certification WHERE unit = 'A' AND office_agent_id = %s",
            (agent_id,),
        )
        cols = [d.name for d in cur.description or []]
        return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def received_at(conn: psycopg.Connection, submission_id: uuid.UUID):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT result_received_at FROM curriculum_submission WHERE submission_id = %s",
            (submission_id,),
        )
        row = cur.fetchone()
    assert row is not None
    return row[0]


@pytest.fixture
def world(admin: psycopg.Connection, seed_agent: uuid.UUID, forge):
    """One agent, one grant, one live instruction, one submission awaiting a verdict."""
    forge_id, module_id = forge
    content_hash = publish_instruction(
        admin,
        forge_id=forge_id,
        module_id=module_id,
        instruction_version="1.0.0",
        forge_api_version="2.1.0",
        authored_at=datetime.now(UTC) - timedelta(days=10),
    )
    grant(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)
    run_ref = f"office:{VENTURE}:{forge_id}:{module_id}:abcdef012345"
    submission_id = submit(
        admin,
        forge_id=forge_id,
        module_id=module_id,
        content_hash=content_hash,
        run_ref=run_ref,
        hours_ago=2,
    )
    return {
        "agent_id": seed_agent,
        "forge_id": forge_id,
        "module_id": module_id,
        "content_hash": content_hash,
        "run_ref": run_ref,
        "submission_id": submission_id,
    }


async def run_sweep(client) -> sweeps.SweepResult:
    async with connection() as conn:
        return await sweeps.sweep_verdict_ingest(conn, client=client)


# -------------------------------------------------------------- the verdict lands


async def test_a_pass_verdict_produces_a_simforge_attested_certification(admin, world):
    """The row this whole package exists to write.

    Asserted on `simforge_verdict` rather than on a state alone: `record_result` writes
    the verdict into that column ONLY for a SimForge attestation and leaves it NULL for
    a bootstrap, so `simforge_verdict IS NOT NULL` is the structural test for "somebody
    external attested this" - and `_gate_9` refuses a certified row without one.
    """
    client = FakeSimForge(
        {world["run_ref"]: _gate_result("PASS", run_ref=world["run_ref"], tier="propose")}
    )

    result = await run_sweep(client)

    assert client.asked == [world["run_ref"]], "the sweep polls; nothing is pushed to it"
    rows = cert_rows(admin, world["agent_id"])
    assert len(rows) == 1
    row = rows[0]
    assert row["state"] == "certified"
    assert row["simforge_verdict"] == "PASS"
    assert row["certified_tier"] == "propose"
    assert row["rubric_kind"] == "operation"
    # The basis, recovered rather than supplied. 2.1.0 is the instruction's
    # forge_api_version, not the Forge registry's 1.4.0 - the version the run was
    # judged against, not the one live today.
    assert row["forge_api_version"] == "2.1.0"
    assert row["instruction_content_hash"] == world["content_hash"]
    assert result.status == "passed"
    assert result.findings["ingested"] == 1
    assert received_at(admin, world["submission_id"]) is not None


async def test_a_withheld_verdict_is_provisional_and_never_certified(admin, world):
    """PROVISIONAL is a governance hold: passed the threshold, rubric did not discriminate.

    The failure mode this guards is a `verdict in ("PASS", "PROVISIONAL")` shortcut, or a
    truthiness check on a score. Both would grant assignability to a run SimForge
    explicitly withheld it from.
    """
    client = FakeSimForge(
        {
            world["run_ref"]: _gate_result(
                "PROVISIONAL", run_ref=world["run_ref"], tier="suggest"
            )
        }
    )

    await run_sweep(client)

    rows = cert_rows(admin, world["agent_id"])
    assert len(rows) == 1
    assert rows[0]["state"] == "provisional"
    assert rows[0]["state"] != "certified"
    assert rows[0]["simforge_verdict"] == "PROVISIONAL"
    # The basis is still required for a hold - a hold whose staleness cannot be
    # recomputed is a hold nobody can clear.
    assert rows[0]["forge_api_version"] == "2.1.0"
    # A tier SimForge sent is stored rather than dropped, and this assertion exists
    # because the prediction for this package said the opposite. `record_result` does
    # not REQUIRE a tier on a hold - "demanding one here would invite a placeholder a
    # later reader takes for a real cap" - which is not the same as refusing one that
    # was measured. It is inert either way: `cap_tier` is reached only through
    # `resolve_grant`, which refuses any state but `certified` first.
    assert rows[0]["certified_tier"] == "suggest"


# ------------------------------------------------------------------- and the guard


async def test_a_certified_verdict_without_a_recoverable_basis_is_refused(
    admin, seed_agent, forge
):
    """**The guard is exercised, not bypassed.**

    A PASS whose submission carries a hash no instruction row holds. The Forge
    api_version cannot be recovered, and the only two ways past that are a placeholder
    and a refusal. `record_result` refuses; the sweep reports the refusal and writes
    nothing.

    Asserted on the row count and not only on the exception, because the failure worth
    catching is a row that exists with an invented basis - `certified_records_its_basis`
    would accept `forge_api_version = 'unknown'` quite happily.
    """
    forge_id, module_id = forge
    grant(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)
    run_ref = f"office:{VENTURE}:{forge_id}:{module_id}:deadbeef0000"
    submission_id = submit(
        admin,
        forge_id=forge_id,
        module_id=module_id,
        content_hash="a" * 64,  # no instruction row carries this
        run_ref=run_ref,
        hours_ago=2,
    )
    client = FakeSimForge({run_ref: _gate_result("PASS", run_ref=run_ref, tier="propose")})

    result = await run_sweep(client)

    assert cert_rows(admin, seed_agent) == [], "nothing written, not written with a placeholder"
    assert result.status == "failed", "a verdict that could not be recorded is not a pass"
    assert result.findings["refused"], "the write was refused, not merely reported"
    reasons = " ".join(
        f["reason"]
        for f in result.findings["basis_unrecoverable"] + result.findings["refused"]
    )
    assert "content hash" in reasons
    assert "api_version" in reasons or "api version" in reasons
    # Still owed an answer, so it stays in the candidate set.
    assert received_at(admin, submission_id) is None


async def test_a_failing_verdict_needs_no_basis_and_is_still_recorded(
    admin, seed_agent, forge
):
    """The other half of the guard, and the reason it is per-state rather than global.

    A `failed` certification records that an agent was tested and did not pass. That
    claim does not go stale, so it does not need a basis - and refusing to write it
    would leave the agent looking `never_certified`, which is a different and better
    thing to be than `failed`.
    """
    forge_id, module_id = forge
    grant(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)
    run_ref = f"office:{VENTURE}:{forge_id}:{module_id}:0badc0de0000"
    submission_id = submit(
        admin, forge_id=forge_id, module_id=module_id,
        content_hash="b" * 64, run_ref=run_ref, hours_ago=2,
    )
    client = FakeSimForge({run_ref: _gate_result("FAIL", run_ref=run_ref)})

    result = await run_sweep(client)

    rows = cert_rows(admin, seed_agent)
    assert len(rows) == 1
    assert rows[0]["state"] == "failed"
    assert result.status == "passed", (
        "an unrecoverable basis is fatal to a PASS and irrelevant to a FAIL; reporting "
        "the sweep as failed here would make every recorded failure look like an outage"
    )
    assert result.findings["refused"] == []
    assert len(result.findings["basis_unrecoverable"]) == 1
    assert rows[0]["simforge_verdict"] == "FAIL"
    assert rows[0]["forge_api_version"] is None
    # FAIL is terminal: SimForge stored it and will not revise it.
    assert received_at(admin, submission_id) is not None


async def test_the_api_version_is_the_one_in_force_when_the_curriculum_was_sent(
    admin, seed_agent, forge
):
    """`content_hash` is NOT unique per module, and the ambiguity is not hypothetical.

    Republishing an unchanged instruction against a bumped Forge API produces two rows
    with one hash and two api_versions - exactly what `version_sensitivity` exists to
    describe. A lookup on the hash alone has two answers and would take whichever the
    planner returned first.

    The rule is not a tie-break. Gate 8 puts `instruction.forge_api_version` from the
    LIVE instruction onto the wire in the curriculum it hands over, so the row in force
    at `submitted_at` is the version SimForge was actually told about.
    """
    forge_id, module_id = forge
    now = datetime.now(UTC)
    old_hash = publish_instruction(
        admin, forge_id=forge_id, module_id=module_id,
        instruction_version="1.0.0", forge_api_version="2.1.0",
        authored_at=now - timedelta(days=10), superseded_at=now - timedelta(days=5),
    )
    new_hash = publish_instruction(
        admin, forge_id=forge_id, module_id=module_id,
        instruction_version="1.1.0", forge_api_version="3.0.0",
        authored_at=now - timedelta(days=5),
    )
    assert old_hash == new_hash, (
        "identical content must hash identically - that is the whole ambiguity"
    )

    grant(admin, agent_id=seed_agent, forge_id=forge_id, module_id=module_id)
    old_ref = f"office:{VENTURE}:{forge_id}:{module_id}:000000000001"
    submit(
        admin, forge_id=forge_id, module_id=module_id,
        content_hash=old_hash, run_ref=old_ref, hours_ago=24 * 7,
    )
    client = FakeSimForge({old_ref: _gate_result("PASS", run_ref=old_ref, tier="suggest")})
    await run_sweep(client)

    rows = cert_rows(admin, seed_agent)
    assert len(rows) == 1
    assert rows[0]["forge_api_version"] == "2.1.0", (
        "a submission made seven days ago was judged against the instruction that was "
        "live seven days ago, not against the one live now"
    )

    # And the other direction, through the same rule: a submission made an hour ago.
    new_ref = f"office:{VENTURE}:{forge_id}:{module_id}:000000000002"
    submit(
        admin, forge_id=forge_id, module_id=module_id,
        content_hash=new_hash, run_ref=new_ref, hours_ago=1,
    )
    client = FakeSimForge({new_ref: _gate_result("PASS", run_ref=new_ref, tier="suggest")})
    await run_sweep(client)

    rows = cert_rows(admin, seed_agent)
    assert len(rows) == 1, "same natural key, so this replaces rather than accumulates"
    assert rows[0]["forge_api_version"] == "3.0.0"


# ------------------------------------------------------ the timeout, and what beats it


async def test_an_unanswered_run_still_resolves_to_timeout_and_in_training(admin, world):
    """The existing path, reached by a caller for the first time.

    `overdue_submissions` and `timeout_gate_result` were referenced by nothing but their
    own tests. This is a branch added beside them, not a replacement: SimForge cannot be
    read, The Office's own deadline has passed, and a deadline held by the party that is
    WAITING is the only version of this check that survives the failure it exists to
    catch.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE curriculum_submission SET submitted_at = %s WHERE submission_id = %s",
            (datetime.now(UTC) - timedelta(hours=30), world["submission_id"]),
        )
    admin.commit()

    result = await run_sweep(FakeSimForge())  # knows about no runs at all

    rows = cert_rows(admin, world["agent_id"])
    assert len(rows) == 1
    assert rows[0]["state"] == "in_training", "TIMEOUT never resolves to PASS"
    assert rows[0]["simforge_verdict"] == "TIMEOUT"
    assert rows[0]["score"] is None, (
        "a score of 0.0 would be a claim about the agent rather than about the run"
    )
    assert result.findings["timed_out"] == 1
    assert received_at(admin, world["submission_id"]) is None, (
        "a TIMEOUT must leave the submission open, or a late verdict can never land"
    )


async def test_a_run_inside_its_deadline_is_left_alone(admin, world):
    """Two hours old and unreadable is a battery running, not a battery lost."""
    result = await run_sweep(FakeSimForge())

    assert cert_rows(admin, world["agent_id"]) == []
    assert result.findings["still_open"] == 1
    assert result.findings["timed_out"] == 0
    assert result.denominator == 1, "examined, even though nothing was written"


async def test_a_late_verdict_beats_a_recorded_timeout(admin, world):
    """**The property to keep.**

    SimForge records a result arriving for a run already stamped TIMEOUT - "a result
    that ARRIVED is better evidence than a deadline that passed" - and leaves
    `timedOutAt` in place so the late arrival stays visible. If The Office stamped
    `result_received_at` when it resolved a timeout, it would stop asking while SimForge
    was still answering, and the certification would sit at `in_training` forever
    because a battery finished five minutes late.

    Two systems, one rule: the arriving verdict wins.
    """
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE curriculum_submission SET submitted_at = %s WHERE submission_id = %s",
            (datetime.now(UTC) - timedelta(hours=30), world["submission_id"]),
        )
    admin.commit()

    await run_sweep(FakeSimForge())
    assert cert_rows(admin, world["agent_id"])[0]["state"] == "in_training"

    # The battery finishes. SimForge now answers for the same run_ref.
    late = FakeSimForge(
        {world["run_ref"]: _gate_result("PASS", run_ref=world["run_ref"], tier="propose")}
    )
    result = await run_sweep(late)

    assert late.asked == [world["run_ref"]], (
        "the timed-out submission was re-examined, which is only true if the first "
        "pass left it unstamped"
    )
    rows = cert_rows(admin, world["agent_id"])
    assert len(rows) == 1, "upserted on the natural key, not appended"
    assert rows[0]["state"] == "certified"
    assert rows[0]["simforge_verdict"] == "PASS"
    assert result.findings["ingested"] == 1
    assert received_at(admin, world["submission_id"]) is not None, (
        "and NOW it closes, because a stored verdict is what the stamp means"
    )


# ------------------------------------------------------------ idempotence and counting


async def test_running_the_sweep_twice_does_not_double_write_or_flip_a_state(admin, world):
    """Idempotence asserted through the DENOMINATOR, not only through the row count.

    A sweep that re-read and re-wrote an identical row would be idempotent in effect and
    would still be lying: it would report the same submission as examined every day
    forever, and "examined" is the number a reader uses to judge coverage.
    """
    verdict = {world["run_ref"]: _gate_result("PASS", run_ref=world["run_ref"], tier="propose")}

    first = await run_sweep(FakeSimForge(verdict))
    with admin.cursor() as cur:
        cur.execute(
            "SELECT updated_at FROM certification WHERE office_agent_id = %s",
            (world["agent_id"],),
        )
        row = cur.fetchone()
    assert row is not None
    first_updated_at = row[0]

    second_client = FakeSimForge(verdict)
    second = await run_sweep(second_client)

    assert first.denominator == 1
    assert second.denominator == 0, "the stamp removed it from the candidate set"
    assert second_client.asked == [], "and SimForge was not asked a second time"
    assert second.findings["ingested"] == 0
    rows = cert_rows(admin, world["agent_id"])
    assert len(rows) == 1
    assert rows[0]["state"] == "certified"

    with admin.cursor() as cur:
        cur.execute(
            "SELECT updated_at FROM certification WHERE office_agent_id = %s",
            (world["agent_id"],),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == first_updated_at, "not rewritten"


async def test_the_denominator_reports_submissions_examined_not_ingested(
    admin, seed_agent, forge, world
):
    """"Report the denominator." A count of what was written is not coverage.

    Three submissions in flight, one of them answerable. A sweep reporting `1` would be
    reporting its own output as its scope - the same defect Gate 8 avoids by sending
    `functions_in_module` as 0 rather than guessing it.
    """
    forge_id, module_id = forge
    for n in (1, 2):
        submit(
            admin, forge_id=forge_id, module_id=module_id,
            content_hash=world["content_hash"],
            run_ref=f"office:{VENTURE}:{forge_id}:{module_id}:aaaaaaaa000{n}",
            hours_ago=1,
        )

    client = FakeSimForge(
        {world["run_ref"]: _gate_result("PASS", run_ref=world["run_ref"], tier="propose")}
    )
    result = await run_sweep(client)

    assert result.denominator == 3
    assert result.findings["examined"] == 3
    assert result.findings["ingested"] == 1
    assert result.findings["still_open"] == 2

    # And the same numbers survive into the durable record, which is the one a reader
    # of `freshness` sees months later.
    with admin.cursor() as cur:
        cur.execute(
            "SELECT denominator, findings FROM sweep_run "
            "WHERE sweep_kind = 'verdict_ingest' AND status <> 'running'"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3
    assert rows[0][1]["examined"] == 3


async def test_a_module_nobody_holds_a_grant_on_is_a_finding_not_a_write(
    admin, forge, seed_agent
):
    """No grant means no unit-A target: the verdict is about an agent, and there is none.

    Inventing one is not available - `certification.unit_targets_match` requires an
    `office_agent_id` for unit A - and picking one would be a claim about which agent
    the run was for, which `run_start` already refuses to make when a run covers several.
    """
    forge_id, module_id = forge
    content_hash = publish_instruction(
        admin, forge_id=forge_id, module_id=module_id,
        instruction_version="1.0.0", forge_api_version="2.1.0",
        authored_at=datetime.now(UTC) - timedelta(days=3),
    )
    run_ref = f"office:{VENTURE}:{forge_id}:{module_id}:cafebabe0000"
    submission_id = submit(
        admin, forge_id=forge_id, module_id=module_id,
        content_hash=content_hash, run_ref=run_ref, hours_ago=2,
    )
    client = FakeSimForge({run_ref: _gate_result("PASS", run_ref=run_ref, tier="propose")})

    result = await run_sweep(client)

    assert result.findings["no_grant_holders"] == [str(submission_id)]
    assert result.findings["ingested"] == 0
    assert result.denominator == 1
    assert received_at(admin, submission_id) is None, "the verdict is still owed to somebody"


# ----------------------------------------------------------------------- concurrency


async def test_two_concurrent_verdict_ingests_serialise(admin, app_dsn, world):
    """W12 for this sweep, and the reason it is not optional here.

    Two concurrent reconciliation sweeps open two pending dispositions and a human
    resolves one. Two concurrent verdict ingests read the same `run_ref` and both write
    a certification for the same agent - the upsert would keep them from doubling the
    row, and they would still both stamp `result_received_at`, both count the submission
    in a denominator, and race on which verdict landed last.

    **Two dedicated connections, not two checkouts from the pool.** A PostgreSQL advisory
    lock is held by a SESSION and is re-entrant within it, so two contenders that happen
    to share a connection both acquire it and the test passes while proving nothing. That
    is not hypothetical: the pooled version of this test passed and then reported
    `[True, True]` on a later run. The backend PIDs are asserted different so the setup
    cannot quietly degrade to one session again.
    """
    verdict = {world["run_ref"]: _gate_result("PASS", run_ref=world["run_ref"], tier="propose")}
    clients = [FakeSimForge(verdict), FakeSimForge(verdict)]

    async with (
        await psycopg.AsyncConnection.connect(app_dsn) as first,
        await psycopg.AsyncConnection.connect(app_dsn) as second,
    ):
        assert first.info.backend_pid != second.info.backend_pid, (
            "one session would hold the lock re-entrantly and prove nothing"
        )
        ready = asyncio.Barrier(2)

        async def contender(conn, client) -> bool:
            await ready.wait()
            async with sweeps._sweep_lock(conn, sweeps.VERDICT_INGEST) as acquired:
                if not acquired:
                    return False
                await sweeps.sweep_verdict_ingest(conn, client=client)
                return True

        ran = await asyncio.gather(
            contender(first, clients[0]), contender(second, clients[1])
        )

    assert sorted(ran) == [False, True], "exactly one contender did the work"
    assert sorted(len(c.asked) for c in clients) == [0, 1]
    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM sweep_run WHERE sweep_kind = 'verdict_ingest'")
        row = cur.fetchone()
    assert row is not None and row[0] == 1, (
        "the loser writes nothing at all - not even a sweep_run row with no findings"
    )
    assert len(cert_rows(admin, world["agent_id"])) == 1


async def test_the_verdict_ingest_declares_a_max_age():
    """A stale pass is not a pass, and a sweep with no max_age cannot go stale.

    Daily, and the argument runs opposite to the intuitive one. A missed PASS is loud -
    the agent stays uncertified and `resolve_grant` refuses its every call. A missed
    REVOKED is silent: the call path goes on enforcing a `certified` row SimForge has
    withdrawn.
    """
    assert sweeps.VERDICT_INGEST in sweeps.MAX_AGE
    assert sweeps.MAX_AGE[sweeps.VERDICT_INGEST] == timedelta(days=1)


async def test_a_verdict_ingest_that_has_not_run_is_not_green(admin):
    """`never_run` is not healthy, for the same reason `NOT_RUN` is not a pass."""
    async with connection() as conn:
        report = await sweeps.freshness(conn)

    assert report[sweeps.VERDICT_INGEST]["state"] == "never_run"
    assert report[sweeps.VERDICT_INGEST]["healthy"] is False


# ----------------------------------------------------------------------- the wire


class RefusingOffice:
    """The brokered path must not be reached by a sweep."""

    async def call(self, forge_id, module_id, payload, *, agent_ctx):  # pragma: no cover
        raise AssertionError(
            "a sweep has no agent; reaching the brokered path would mean one was minted"
        )


class FakeCursor:
    def __init__(self, rows: dict) -> None:
        self._rows = rows
        self._row: tuple | None = None

    async def execute(self, sql: str, params: tuple) -> None:
        self._row = self._rows["credential" if "credential" in sql else "registry"]

    async def fetchone(self):
        return self._row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConn:
    def __init__(self, rows: dict) -> None:
        self._rows = rows

    def cursor(self):
        return FakeCursor(self._rows)


ROWS = {
    "credential": ("vault://simforge/tenant",),
    "registry": (BASE_URL, "1.4.0"),
}


class FakeResolver:
    async def resolve(self, credential_ref: str):
        from broker.credentials import Credential

        return Credential(credential_ref, "NOT-A-REAL-TOKEN")


HONEST_VERDICT = {
    "run_ref": "office:greenstone:cre-forge:parse_document:0123456789ab",
    "unit": "A",
    "verdict": "PASS",
    "rubric_kind": "operation",
    "rubric_version": "2.3.1",
    "score": 0.94,
    "threshold": 0.85,
    "certified_tier": "propose",
    "scenario_count": 24,
    "coverage_denominator": 24,
    "completed_at": "2026-09-09T12:00:00Z",
}


async def test_the_verdict_read_is_signed_as_the_office_not_as_an_agent():
    """The sweep's read goes to the adapter on the tenant credential, naming no agent.

    **This is not a relaxation of the brokered path.** `get_gate_result` is unchanged and
    still ledgers an agent act, because an agent reading a verdict about itself IS an
    agent act. A sweep is not: `SimForgeClient`'s own docstring refuses to mint one to
    fill the signature - "a name in a ledger row for a call it did not make" - and that
    refusal is what forces this second, honestly-attributed read.

    Asserted on the outbound request, because a client that quietly went somewhere else
    would still return the right answer against a mock.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=HONEST_VERDICT)

    client = SimForgeClient(
        RefusingOffice(),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=FakeResolver(),
    )
    result = await client.office_gate_result(
        FakeConn(ROWS), run_ref=HONEST_VERDICT["run_ref"]
    )

    assert len(seen) == 1
    assert seen[0].url.path == "/office/gate_result"
    assert seen[0].headers["Authorization"].startswith("Bearer ")
    assert "x-office-agent-id" not in seen[0].headers, (
        "no agent performed this read, and the header is where one would be claimed"
    )
    assert json.loads(seen[0].content) == {"run_ref": HONEST_VERDICT["run_ref"]}
    assert result.verdict == "PASS"
    assert result.certified_tier == "propose"


async def test_a_leaky_verdict_does_not_reach_the_sweep_either():
    """**The half that shows the control was not widened.**

    The leak protection was never the brokered path - it is `parse_gate_result`, which
    runs `validate_response` and refuses a field the manifest does not name. The Office
    signing for itself changes who is attributed, not what is accepted, and a body
    carrying an undeclared field must raise here exactly as it does on the agent's read.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={**HONEST_VERDICT, "scenario_bodies": ["..."]})

    client = SimForgeClient(
        RefusingOffice(),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=FakeResolver(),
    )
    with pytest.raises(SimForgeError):
        await client.office_gate_result(FakeConn(ROWS), run_ref=HONEST_VERDICT["run_ref"])


async def test_an_unknown_run_is_a_named_refusal_not_an_empty_verdict():
    """SimForge 404s rather than inventing a NOT_RUN body, and that must not be smoothed.

    A `NOT_RUN` here would map to `never_certified` and look like an answer. The sweep
    turns the refusal into a TIMEOUT only when its own deadline has passed, which is a
    statement about the deadline rather than about the run.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no such run"})

    client = SimForgeClient(
        RefusingOffice(),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=FakeResolver(),
    )
    with pytest.raises(SimForgeError, match="no record of run_ref"):
        await client.office_gate_result(FakeConn(ROWS), run_ref="office:x:y:z:abc")
