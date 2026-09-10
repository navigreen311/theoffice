"""Gate 8's hand-over, and the two fields that were never right.

`handed_over_to_simforge` was hard-coded `False` with an honest comment, and
`simforge_run_ref` was never written at all. The second was the expensive one: it is
what `overdue_submissions` and `timeout_gate_result` key on, so the timeout sweep
`broker/simforge.py` argues for at length could never resolve anything. See
docs/blocking.md B8.

So the assertions here are about the row and about what a sweep can do with it, not
about the flag. A gate reporting a hand-over is easy to write and easy to believe; a
submission that can be correlated to a verdict is the thing that was missing.

**Amended by P-04, and the amendment is the finding.** Four assertions here read
"every row Gate 8 writes names a module" and "every run Gate 8 opens is unit A". Both
were true of every row that had ever been written and neither was a property of Gate 8 -
they were the shape of the half of certification that existed. P-04 opens the other
half, so each is now scoped to the unit it was actually about, and the unit-B rows are
asserted on in `tests/provisioning/test_department_unit.py` rather than folded in here.
Widening an assertion to accommodate new rows would have thrown the assertion away; the
scoped version still fails if a unit-A row loses its module.

**These fakes changed shape in P-15, and the change is the point.** They used to
implement `submit_curriculum -> str`, returning a ref, because the client did. The ref
was never SimForge's to return - it is an input to `run_start`, minted on this side -
so the fakes now return the acceptance body SimForge actually sends and implement
`run_start` alongside it. A fake that answers a question the real system is never asked
is a test that passes about nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from broker import provisioning
from broker.db import connection
from broker.simforge import (
    CurriculumRejectedError,
    SimForgeError,
    mint_run_ref,
    overdue_submissions,
)
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


class HeldOutPasses:
    async def verdict(self, venture_id: str) -> str | None:
        return "PASS"


class SimForgeAccepts:
    """Answers the way the response manifest says it may, on both calls.

    `submit_curriculum` returns the acceptance body - no `run_ref` in it, because
    SimForge does not send one - and `run_start` echoes back the ref The Office minted.
    `run_starts` records what it was opened with, so a test can assert the unit was
    declared at the start rather than inferred at the end.
    """

    def __init__(self, *, level: str = "certified", already_open: bool = False) -> None:
        self.calls: list[dict] = []
        self.run_starts: list[dict] = []
        self._level = level
        self._already_open = already_open

    async def submit_curriculum(self, conn, **kwargs) -> dict:
        self.calls.append(kwargs)
        module_id = kwargs["payload"]["instruction_set_ref"]["module_id"]
        return {
            "accepted": True,
            "module_levels": {module_id: self._level},
            "module_declared_absences": {},
            "never_do_obligations": [],
            "coverage_declaration": kwargs["payload"]["coverage_declaration"],
            "gate_9_5_flag": False,
        }

    async def run_start(self, conn, **kwargs) -> dict:
        self.run_starts.append(kwargs)
        return {
            "run_ref": kwargs["run_ref"],
            "unit": kwargs["unit"],
            "started_at": "2026-09-09T00:00:00Z",
            "window_minutes": 240,
            "already_open": self._already_open,
        }

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


class SimForgeIsDown:
    """The case the old code reported as a hand-over regardless."""

    async def submit_curriculum(self, conn, **kwargs) -> dict:
        raise SimForgeError("could not reach SimForge: ConnectError")

    async def run_start(self, conn, **kwargs) -> dict:  # pragma: no cover - unreachable
        raise SimForgeError("could not reach SimForge: ConnectError")

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


class SimForgeAcceptsThenCannotOpenTheRun:
    """The half that is worse than either failure on its own.

    The curriculum landed and the run did not open, so SimForge holds an instruction set
    and no `OperationRun`. Storing the minted ref here would name a run SimForge has
    never heard of: the sweep would poll `gate_result` and take a 404 for ever, and the
    row would read as a hand-over that worked. NULL is the honest value.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def submit_curriculum(self, conn, **kwargs) -> dict:
        self.calls.append(kwargs)
        module_id = kwargs["payload"]["instruction_set_ref"]["module_id"]
        return {
            "accepted": True,
            "module_levels": {module_id: "certified"},
            "module_declared_absences": {},
            "never_do_obligations": [],
            "coverage_declaration": kwargs["payload"]["coverage_declaration"],
            "gate_9_5_flag": False,
        }

    async def run_start(self, conn, **kwargs) -> dict:
        raise SimForgeError("run_start for 'office:...' returned 503")

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


@pytest_asyncio.fixture
async def at_gate_8(feasible_pack, operator) -> AsyncIterator[tuple]:
    """A run parked immediately before Gate 8 runs.

    The first `advance` stops at Gate 4 waiting for a person; recording the review
    releases it. The *test* makes the next call, so it chooses which SimForge Gate 8
    meets.
    """
    async with connection() as conn:
        run_id = await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=operator.human_id
        )
        await provisioning.advance(conn, run_id=run_id, actor=operator.human_id)
        await provisioning.record_human_review(
            conn, run_id=run_id, human=operator, note="reviewed for the hand-over test"
        )
        yield conn, run_id


async def _submissions(conn, venture_id: str = VENTURE) -> list[dict]:
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT scenario_pack_ref, simforge_run_ref, scenario_count, module_id,
                   department
            FROM curriculum_submission WHERE venture_id = %s
            ORDER BY submitted_at
            """,
            (venture_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "pack_ref": r[0], "run_ref": r[1], "count": r[2], "module_id": r[3],
            "department": r[4],
        }
        for r in rows
    ]


def _unit_a(rows: list[dict]) -> list[dict]:
    """The per-module rows. `module_id` IS the unit - see `simforge.submission_unit`.

    Gate 8 now writes rows for both units, and the assertions in this file are about
    the per-module hand-over. Filtering on the column the rule reads keeps them about
    that, rather than about however many rows happen to exist.
    """
    return [r for r in rows if r["module_id"] is not None]


def _attempts(gate) -> list[dict]:
    """The submissions that were actually sent.

    A module with no live operating instruction is reported under `modules_skipped` and
    appears in `submissions` carrying `skipped`. Nothing was sent for it, so an
    assertion about what SimForge said does not apply to it - and folding the two
    together is how "we tried and it failed" and "we never tried" become one number.
    """
    return [s for s in gate.evidence["submissions"] if "skipped" not in s]


def _gate_8(outcomes):
    for o in outcomes:
        if o.gate == "8":
            return o
    raise AssertionError(f"gate 8 did not run; reached {[o.gate for o in outcomes]}")


async def test_an_accepted_handover_stores_the_run_ref(at_gate_8, operator):
    """The row a sweep can act on.

    Asserted on `curriculum_submission.simforge_run_ref` and not on the gate's own
    evidence dict, because the evidence is what the old code got wrong while looking
    right: it wrote a row nothing could correlate and reported the gate as passed.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    rows = await _submissions(conn)
    assert rows, "gate 8 wrote no submission"
    # One row per module, each naming its module and carrying its ref. `module_id` has
    # existed since migration 0007 and was NULL on every row Gate 8 ever wrote.
    #
    # The ref is minted by The Office, so the assertion is that every row has one and
    # that it is the one `run_start` was opened with - not that it equals a literal a
    # fake chose. A test that names the fake's constant proves the fake.
    assert all(r["run_ref"] for r in rows), "a row with no run_ref: B8 is not retired"
    opened = {call["run_ref"] for call in fake.run_starts}
    assert {r["run_ref"] for r in rows} == opened
    per_module = _unit_a(rows)
    assert per_module, "gate 8 wrote no per-module submission"
    assert all(r["module_id"] for r in per_module), "a unit-A row with no module"
    assert len({r["module_id"] for r in per_module}) == len(per_module), (
        "two rows for one module"
    )

    gate = _gate_8(outcomes)
    assert gate.evidence["handed_over_to_simforge"] is True
    assert gate.evidence["modules_accepted"] == gate.evidence["modules_submitted"]
    assert {s["module_id"] for s in _attempts(gate)} == {
        r["module_id"] for r in per_module
    }

    # The hand-over carried the human who provisioned - never an agent - and a real
    # curriculum rather than a count of one.
    assert fake.calls[0]["actor"] == operator.human_id
    payload = fake.calls[0]["payload"]
    assert payload["instruction_set_ref"]["content_hash"]
    assert payload["operation_scenarios"]
    # The two fields with no source on this side, sent as what is true.
    assert payload["coverage_declaration"]["functions_in_module"] == 0
    assert payload["coverage_declaration"]["functions_covered"] == 0


async def test_an_unreachable_simforge_is_not_reported_as_a_handover(
    at_gate_8, operator
):
    """The gate still passes, and says plainly that nothing landed.

    Passing is correct: the Office's half - the curriculum, the counts, the row - is
    complete and reproducible. What must not happen is the run reading as handed over.
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=SimForgeIsDown(),
    )

    gate = _gate_8(outcomes)
    assert gate.verdict == provisioning.PASSED
    assert gate.evidence["handed_over_to_simforge"] is False
    assert gate.evidence["modules_accepted"] == 0
    assert gate.evidence["modules_submitted"] > 0
    assert "accepted by SimForge" in gate.reason
    attempts = _attempts(gate)
    assert attempts and all("ConnectError" in s["error"] for s in attempts)

    rows = await _submissions(conn)
    assert all(r["run_ref"] is None for r in rows)


async def test_the_timeout_sweep_can_now_resolve_a_submission(at_gate_8, operator):
    """B8, asserted as a consequence rather than as a field.

    `overdue_submissions` returns unanswered rows past a deadline, and
    `timeout_gate_result` builds a TIMEOUT verdict keyed on `simforge_run_ref`. Every
    row Gate 8 wrote carried NULL there, so the sweep could find a submission and had
    nothing to key a verdict on. This asserts the ref survives all the way to the
    verdict the sweep would produce.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()
    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses(),
        simforge=fake,
    )

    # deadline_hours=0: everything unanswered is overdue, which is what a hung run
    # looks like without waiting a day to see one.
    overdue = await overdue_submissions(conn, deadline_hours=0)
    # The per-module rows. A unit-B row is in this queue too and resolves to a TIMEOUT
    # of its own; that is asserted in `test_department_unit.py`, and asserting unit "A"
    # against whichever row sorted last would be asserting the sort order.
    mine = [
        r for r in overdue
        if r["venture_id"] == VENTURE and r["module_id"] is not None
    ]
    assert mine, "the sweep found nothing"

    from broker.simforge import timeout_gate_result

    verdict = timeout_gate_result(mine[-1], rubric_version="1.4.0")
    assert verdict.verdict == "TIMEOUT"
    # The ref, not the `unanswered:<submission_id>` placeholder the helper falls back
    # to. That fallback was the only branch this could ever take before.
    assert verdict.run_ref in {call["run_ref"] for call in fake.run_starts}
    assert not verdict.run_ref.startswith("unanswered:")
    # The sweep's unit and the run's unit come from the same rule, so a run opened as
    # A can only ever time out as A.
    assert verdict.unit == "A"
    assert verdict.rubric_kind == "operation"


class SimForgeRefuses:
    """What SimForge actually says to a curriculum from `curriculum.generate`.

    One scenario per (position, module) and no `scenario_class` on any of them, against
    a validator that counts classes per module. The violations are the real ones.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def submit_curriculum(self, conn, **kwargs) -> dict:
        self.calls.append(kwargs)
        module = kwargs["payload"]["instruction_set_ref"]["module_id"]
        raise CurriculumRejectedError(
            [
                f"scenario[0] (module {module}, None): missing instruction_section, "
                "expected_behavior",
                f"module {module}: no escalation_required scenario (mandatory)",
            ]
        )

    async def run_start(self, conn, **kwargs) -> dict:
        # A refused curriculum has nothing to open a run against. Reaching this is the
        # gate opening a run for a submission SimForge rejected.
        raise AssertionError("run_start after a refusal")

    async def aclose(self) -> None:  # pragma: no cover - nothing to close
        pass


async def test_a_refusal_is_recorded_as_an_answer_not_as_an_outage(
    at_gate_8, operator
):
    """A rejection names the work; an outage names nothing.

    The two must not collapse into one `error` string, because the response to them is
    different: a rejection is a list of scenarios somebody has to write, and an outage
    is a service to restart. The evidence carries `violations` for the first and only
    `error` for the second.
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=SimForgeRefuses(),
    )

    gate = _gate_8(outcomes)
    assert gate.verdict == provisioning.PASSED
    assert gate.evidence["handed_over_to_simforge"] is False
    assert gate.evidence["modules_accepted"] == 0

    attempts = _attempts(gate)
    assert attempts, "nothing was submitted, so nothing was refused"
    for submission in attempts:
        assert submission["violations"], "a refusal recorded without its reasons"
        assert any(
            "escalation_required" in v for v in submission["violations"]
        ), "the refusal did not name the missing class"

    # The row still exists, with no ref. A refused submission is a thing that happened.
    rows = await _submissions(conn)
    assert rows and all(r["run_ref"] is None for r in rows)


# --------------------------------------------------------- P-15: B8's retirement


async def test_gate_8_populates_simforge_run_ref_on_the_stored_row(at_gate_8, operator):
    """**B8's exact retirement condition, asserted on the row and nothing else.**

    Not on the call returning, not on `handed_over_to_simforge`, not on the evidence
    dict. `overdue_submissions` selects `simforge_run_ref` out of
    `curriculum_submission`, and `timeout_gate_result` keys a verdict on what it finds
    there; a ref that exists anywhere else in this process correlates nothing. The
    column has been NULL on every row Gate 8 has ever written.

    The second assertion is the one that makes the first mean something: the stored ref
    is the ref `run_start` was called with. A row carrying a ref SimForge never opened a
    run under reads exactly like a hand-over that worked and is worse than the NULL,
    because the sweep would poll `gate_result` and take a 404 for ever.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, simforge_run_ref FROM curriculum_submission "
            "WHERE venture_id = %s",
            (VENTURE,),
        )
        all_rows = await cur.fetchall()

    assert all_rows, "gate 8 wrote no submission row"
    nulls = [r[0] for r in all_rows if r[1] is None]
    assert not nulls, f"simforge_run_ref is still NULL for {nulls}: B8 is not retired"

    opened = {c["run_ref"]: c for c in fake.run_starts}
    assert len(opened) == len(all_rows), "a row without a run opened under its ref"
    # The per-module rows only: this test is about what a unit-A hand-over declares at
    # the start, and a unit-B run declares "B"/"domain" for the same reason.
    rows = [r for r in all_rows if r[0] is not None]
    assert rows, "gate 8 wrote no per-module row"
    for module_id, ref in rows:
        assert ref in opened, f"{module_id} stored a ref no run was opened under"
        # Declared at the START, which is why `run_start` takes it. A run whose unit is
        # only known once it finishes cannot be asked about while it is hanging.
        assert opened[ref]["unit"] == "A"
        assert opened[ref]["rubric_kind"] == "operation"
        assert opened[ref]["module_id"] == module_id


async def test_a_run_that_did_not_open_stores_no_ref(at_gate_8, operator):
    """Accepted curriculum, unopened run. The half that must not read as a hand-over.

    Storing the minted ref here would name a run SimForge has never heard of. The
    existing invariant is `run_ref is not None` means this landed, and opening the run
    is now part of landing - so the row keeps its NULL and the gate says plainly that
    nothing was handed over.
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=SimForgeAcceptsThenCannotOpenTheRun(),
    )

    gate = _gate_8(outcomes)
    assert gate.verdict == provisioning.PASSED
    assert gate.evidence["handed_over_to_simforge"] is False
    assert gate.evidence["modules_accepted"] == 0

    rows = await _submissions(conn)
    assert rows, "the submission row is still a thing that happened"
    assert all(r["run_ref"] is None for r in rows)
    # The error names the run, not the curriculum. A reader has to be able to tell
    # "SimForge refused what we sent" from "SimForge took it and would not open a run".
    assert all("run_start" in s["error"] for s in _attempts(gate))


async def test_the_ref_gate_8_mints_is_derived_from_the_submission(at_gate_8, operator):
    """The reason the ref is derived and not minted fresh per attempt.

    `open_run` is idempotent on `run_ref` and answers `already_open: true` with the
    clock UNTOUCHED, so a retried hand-over cannot extend the window of a run that is
    already hanging (SimForge's ADR-0044). That guard lives on SimForge's side and can
    only work if this side presents the same ref twice - a fresh uuid per attempt would
    open a second run with a young window while SimForge's own check read as satisfied.

    Asserted by recomputing the ref from the row Gate 8 wrote, rather than by running
    the gate twice: `ux_run_active` allows one provisioning run per venture at a time,
    and the property under test is that the ref is a function of the submission, not of
    the attempt. If it were a uuid, or seeded with the provisioning run id or a
    timestamp, this fails.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()
    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT venture_id, forge_id, module_id, department,
                   instruction_content_hash, simforge_run_ref
            FROM curriculum_submission WHERE venture_id = %s
            """,
            (VENTURE,),
        )
        rows = await cur.fetchall()

    assert rows
    # Both units, recomputed from their own row. A unit-B ref names the department in
    # the segment a unit-A ref names the module in, precisely so two departments
    # operating one module set on one Forge do not mint one ref and land on one run.
    for venture_id, forge_id, module_id, department, content_hash, stored in rows:
        assert stored == mint_run_ref(
            venture_id=venture_id, forge_id=forge_id,
            module_id=module_id, department=department, content_hash=content_hash,
        ), f"{module_id or department}: the ref is not a function of the submission"


async def test_a_run_that_was_already_open_is_reported_as_such(at_gate_8, operator):
    """"Found the run that was hanging" is not "opened a run".

    `already_open` is the only signal that a window was not restarted, and folding it
    into a plain success is how a second hand-over against a hung run would look like
    progress.
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses(),
        simforge=SimForgeAccepts(already_open=True),
    )

    gate = _gate_8(outcomes)
    assert gate.evidence["handed_over_to_simforge"] is True
    assert all(s["already_open"] is True for s in _attempts(gate))


async def test_the_module_certification_level_reaches_the_evidence(at_gate_8, operator):
    """`module_levels` is worth HAVING, not merely tolerating.

    It is the per-module certification level - `certified`,
    `certified_with_declared_absence`, `demonstrated` - which is exactly what the
    certification run needs. The old contract discarded the entire acceptance body to
    read one key that was never in it, so this arrived on every accepted submission and
    was thrown away ten times out of ten.
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, held_out=HeldOutPasses(),
        simforge=SimForgeAccepts(level="certified_with_declared_absence"),
    )

    attempts = _attempts(_gate_8(outcomes))
    assert attempts
    assert all(
        s["module_level"] == "certified_with_declared_absence" for s in attempts
    )
    assert all(s["gate_9_5_flag"] is False for s in attempts)
