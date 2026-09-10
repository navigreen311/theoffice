"""The unit-B half of Gate 8: a run per department x forge, and no curriculum at all.

**B30's open half.** Certification has two units and one submission is one or the other,
keyed on `module_id` - `simforge.submission_unit` is the rule. Gate 8 hands over one
curriculum per module, so every row it had ever written was a unit A: ten with a module,
none with a department. `generators/appointment.py` requires BOTH, and refuses any
candidate whose position touches a Forge its department holds no certified unit-B row
for. So a perfect unit-A pipeline appoints nobody.

WHAT THIS SUITE IS CAREFUL ABOUT
================================

    **A unit B is not a curriculum, and that was established off the receiving side.**
    SimForge's `ForgeOperationCurriculum.instruction_set_ref.module_id` is a required,
    non-optional `str`, so a department-scoped curriculum cannot be expressed in the
    payload. The field that looks like it can - a `CertificationUnitRequest` carrying
    `unit_type="department_context"` and a `department_id` - is read by nothing:
    `routers/operation.py::submit_curriculum` takes
    `{u.module_id for u in body.certification_units_requested if u.module_id}` out of
    that list and consumes no other field on it. So the assertion here is not "a
    department curriculum was submitted correctly"; it is that **no curriculum was
    submitted for a department at all**, which is what the receiving side supports.

    **The counts are not invented.** `curriculum_submission.scenario_count` is
    `CHECK (scenario_count > 0)`. A department whose modules were all refused gets NO
    run and NO row rather than a count clamped to 1 - `test_a_department_with_nothing_
    accepted_is_reported_and_not_opened` is that case, and it is the one a placeholder
    would have quietly satisfied.

    **This suite does not assert that a department gets certified**, because it cannot
    be, and the reason is not on this side. See `tests/contract/test_unit_b_certification.py`.
"""

from __future__ import annotations

import pytest

from broker import provisioning
from broker.db import connection
from broker.simforge import (
    department_basis_hash,
    mint_run_ref,
    submission_unit,
)
from tests.conftest import requires_db
from tests.provisioning.test_simforge_handover import (  # noqa: F401 - fixtures
    HeldOutPasses,
    SimForgeAccepts,
    SimForgeRefuses,
    at_gate_8,
)

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


def _gate_8(outcomes):
    for outcome in outcomes:
        if outcome.gate == "8":
            return outcome
    raise AssertionError(f"gate 8 did not run; reached {[o.gate for o in outcomes]}")


async def _rows(conn, *, department: bool):
    """Submission rows of one unit. `module_id` IS the unit - `submission_unit` says so."""
    predicate = "module_id IS NULL" if department else "module_id IS NOT NULL"
    async with conn.cursor() as cur:
        await cur.execute(
            f"""
            SELECT module_id, department, forge_id, scenario_count,
                   coverage_denominator, instruction_content_hash, simforge_run_ref
            FROM curriculum_submission
            WHERE venture_id = %s AND {predicate}
            ORDER BY department, forge_id, module_id
            """,
            (VENTURE,),
        )
        return [
            {
                "module_id": r[0], "department": r[1], "forge_id": r[2],
                "scenario_count": r[3], "coverage_denominator": r[4],
                "content_hash": r[5], "run_ref": r[6],
            }
            for r in await cur.fetchall()
        ]


def _unit_b_starts(fake) -> list[dict]:
    return [call for call in fake.run_starts if call["unit"] == "B"]


# --------------------------------------------------------- the row, and its unit


async def test_a_unit_b_submission_carries_a_department_and_no_module(
    at_gate_8, operator  # noqa: F811
):
    """The two columns that ARE the unit, on the row P-03's sweep reads.

    `unit_targets_match` reads `B -> department NOT NULL`, and a unit-B row carrying a
    module would be a unit-A assertion on it. Asserted on the stored row rather than on
    the gate's evidence, because the evidence is what a wrong implementation would get
    right while writing nothing a sweep could act on - that is exactly how B8 hid.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    rows = await _rows(conn, department=True)
    assert rows, "gate 8 still writes no unit-B submission: B30's open half is open"
    for row in rows:
        assert row["module_id"] is None, "a unit-B row naming a module"
        assert row["department"], "a unit-B row with no department"
        assert row["run_ref"], "a unit-B row a sweep cannot correlate to a run"
        # Both NOT NULL CHECK > 0 on this table. Not clamped: a department with nothing
        # submitted gets no row at all.
        assert row["scenario_count"] > 0
        assert row["coverage_denominator"] > 0
        assert row["content_hash"]


async def test_the_run_is_opened_as_b_domain_with_the_department_on_it(
    at_gate_8, operator  # noqa: F811
):
    """Declared at the START, which is why `run_start` takes the unit.

    SimForge's own reason: "The Office reads one verdict per `run_ref`, and a run whose
    unit is only known once it finishes cannot be asked about while it is hanging."
    `rubric_matches_unit` pairs B with `domain`, so a run opened as B against the
    operation rubric produces a verdict that cannot be recorded at all.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    starts = _unit_b_starts(fake)
    assert starts, "no unit-B run was opened"
    for call in starts:
        assert call["rubric_kind"] == "domain"
        assert call["department_id"], "a unit-B run with no department"
        assert call["module_id"] is None, "a module id on a unit-B run"
        # A department certification is about the department. Naming one of its agents
        # would be a claim about which agent the run is for, decided by a sort order.
        assert call["agent_id"] is None
        # SimForge's policy, not an Office default. Same as the per-module path.
        assert call["window_minutes"] is None

    rows = await _rows(conn, department=True)
    assert {r["run_ref"] for r in rows} == {c["run_ref"] for c in starts}
    assert {(r["department"], r["forge_id"]) for r in rows} == {
        (c["department_id"], c["forge_id"]) for c in starts
    }


async def test_the_unit_comes_from_submission_unit_and_is_not_restated(
    at_gate_8, operator  # noqa: F811
):
    """One question, one rule - P-15 extracted `submission_unit` so there is one.

    Asserted through what the gate put on the wire against what the function answers,
    rather than by reading the source: a grep finds mentions and not construction. If
    the gate ever spelled the A/B derivation inline this still fails the moment the two
    disagree, which is the only moment it matters.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    expected = submission_unit(None)
    assert expected == ("B", "domain")
    for call in _unit_b_starts(fake):
        assert (call["unit"], call["rubric_kind"]) == expected

    per_module = submission_unit("property_lookup")
    assert per_module == ("A", "operation")
    for call in fake.run_starts:
        if call["unit"] == "A":
            assert (call["unit"], call["rubric_kind"]) == per_module


# ------------------------------------------------- what is NOT sent, and why not


async def test_no_curriculum_is_submitted_for_a_department(
    at_gate_8, operator  # noqa: F811
):
    """**Read off the receiving side, not off the name of the table.**

    `ForgeOperationCurriculum.instruction_set_ref.module_id` is required and
    non-optional, and SimForge's `submit_curriculum` reads exactly one field out of
    `certification_units_requested` - `module_id` - then upserts a `ForgeInstructionSet`
    keyed `(forgeId, moduleId, contentHash)`. A department hand-over would therefore
    either 422 on the missing module or bind an instruction set under an invented one.

    So every curriculum this gate sends names a real module, and the number of them is
    the number of per-module rows. A unit B is `run_start` and the correlation row.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    per_module = await _rows(conn, department=False)
    assert len(fake.calls) == len(per_module), (
        "a curriculum was submitted that no per-module row accounts for"
    )
    for call in fake.calls:
        module_id = call["payload"]["instruction_set_ref"]["module_id"]
        assert module_id, "a curriculum submitted with no module"
        units = call["payload"].get("certification_units_requested", [])
        assert all(u.get("unit_type") != "department_context" for u in units), (
            "a department_context unit was declared on a curriculum. SimForge reads "
            "nothing but `module_id` off that list, so it would travel and do nothing "
            "- see routers/operation.py::submit_curriculum"
        )


async def test_the_unit_a_path_is_unaffected(at_gate_8, operator):  # noqa: F811
    """The half that already worked, asserted as untouched rather than assumed to be.

    One row per module, each naming its module and carrying the ref its own run was
    opened under, and the gate's `submissions`/`modules_submitted` evidence still counts
    modules and nothing else. A unit-B entry folded into that list would make
    `modules_submitted` count something that is not a module submission - the same
    collapse B30 says hid unit B for a fortnight.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    per_module = await _rows(conn, department=False)
    assert per_module
    assert all(r["module_id"] and r["department"] is None for r in per_module)
    assert all(r["run_ref"] for r in per_module)

    gate = _gate_8(outcomes)
    attempted = [s for s in gate.evidence["submissions"] if "skipped" not in s]
    assert gate.evidence["modules_submitted"] == len(attempted)
    assert {s["module_id"] for s in attempted} == {r["module_id"] for r in per_module}
    assert all("department" not in s for s in gate.evidence["submissions"])
    # The unit-B entries live in their own list, and the count beside them is theirs.
    assert gate.evidence["department_units"]
    assert gate.evidence["department_units_opened"] == len(
        [u for u in gate.evidence["department_units"] if u["run_ref"]]
    )


# ------------------------------------------------------------ the ref, and refuse


async def test_two_departments_on_one_forge_do_not_share_a_run(
    at_gate_8, operator  # noqa: F811
):
    """The collision the department segment exists to prevent.

    `open_run` is idempotent on `run_ref` and returns the existing row with its clock
    untouched. Two departments minting one ref would mean the second `run_start` landed
    silently on the first department's run, both rows carrying one ref - and P-03's
    sweep would write two certifications, for two different departments, out of one
    verdict.
    """
    conn, run_id = at_gate_8
    fake = SimForgeAccepts()

    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=fake,
    )

    rows = await _rows(conn, department=True)
    by_forge: dict[str, set[str]] = {}
    for row in rows:
        by_forge.setdefault(row["forge_id"], set()).add(row["department"])
    assert any(len(d) > 1 for d in by_forge.values()), (
        "no Forge in this world serves two departments, so this test proves nothing"
    )

    assert len({r["run_ref"] for r in rows}) == len(rows), "two departments, one run"
    for row in rows:
        assert row["run_ref"] == mint_run_ref(
            venture_id=VENTURE, forge_id=row["forge_id"], module_id=None,
            department=row["department"], content_hash=row["content_hash"],
        ), "the ref is not a function of the submission"


async def test_a_department_with_nothing_accepted_is_reported_and_not_opened(
    at_gate_8, operator  # noqa: F811
):
    """A refusal is a finding, never a run with an invented basis.

    Every module 422s here, so SimForge holds no instruction set for any of this
    department's modules and there is nothing its context could be cleared against.
    The `CHECK (scenario_count > 0)` on `curriculum_submission` would have been
    satisfiable by clamping a zero to 1; that would have produced a correlation row for
    a run nobody opened, sitting in the sweep's queue for a verdict that cannot arrive.

    So: no run, no row, and the (department, forge) pair named in the evidence. That
    pair is exactly what `appointment.generate` will refuse as `missing_unit_b`, said
    at the gate that could have produced it rather than four gates later as "zero
    certified candidates".
    """
    conn, run_id = at_gate_8

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=SimForgeRefuses(),
    )

    assert not await _rows(conn, department=True), (
        "a unit-B row was written for a department SimForge accepted nothing for"
    )

    gate = _gate_8(outcomes)
    units = gate.evidence["department_units"]
    assert units, "the refused departments are not reported at all"
    assert gate.evidence["department_units_opened"] == 0
    for unit in units:
        assert unit["run_ref"] is None
        assert unit["department"] and unit["forge_id"]
        assert unit["modules_accepted"] == 0
        assert "no module of this department was accepted" in unit["skipped"]


async def test_an_unreachable_simforge_does_not_block_the_ladder(
    at_gate_8, operator  # noqa: F811
):
    """Same rule as the per-module path: a Forge is allowed to be down.

    The row is written with a NULL ref - The Office's half happened and is reproducible
    - and the gate still passes. A unit-B run that could not be opened must not read as
    one that was, for the reason the per-module path gives: a stored ref names a run
    SimForge has never heard of and the sweep takes a 404 for ever.
    """
    conn, run_id = at_gate_8

    class AcceptsThenCannotOpenTheDepartmentRun(SimForgeAccepts):
        async def run_start(self, conn, **kwargs):
            if kwargs["unit"] == "B":
                from broker.simforge import SimForgeError

                raise SimForgeError("run_start for 'office:...' returned 503")
            return await super().run_start(conn, **kwargs)

    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id,
        held_out=HeldOutPasses(), simforge=AcceptsThenCannotOpenTheDepartmentRun(),
    )

    gate = _gate_8(outcomes)
    assert gate.verdict == provisioning.PASSED
    assert gate.evidence["department_units_opened"] == 0
    rows = await _rows(conn, department=True)
    assert rows, "the Office's own record of the attempt is missing"
    assert all(r["run_ref"] is None for r in rows)
    assert all("503" in u["error"] for u in gate.evidence["department_units"])


# --------------------------------------------------------------- the basis hash


def test_the_department_basis_is_a_composite_of_what_was_handed_over():
    """A department has no operating instruction, so its basis is the set it operates.

    The property that makes a single hash useful is the one this needs: it changes when
    any member changes and it does not change when they do not, so a re-run of Gate 8
    against unchanged instructions mints the same ref and lands on the run that is
    already open - exactly as the per-module path does.
    """
    a = department_basis_hash({"property_lookup": "aa" * 32, "comp_analysis": "bb" * 32})
    assert a == department_basis_hash(
        {"comp_analysis": "bb" * 32, "property_lookup": "aa" * 32}
    ), "the basis depends on dict order"
    assert a != department_basis_hash(
        {"property_lookup": "aa" * 32, "comp_analysis": "cc" * 32}
    ), "a changed instruction did not change the basis"
    assert a != department_basis_hash({"property_lookup": "aa" * 32}), (
        "dropping a module from the department did not change the basis"
    )
    # Domain-separated, so it cannot collide with a real instruction hash by accident.
    assert a != "aa" * 32


def test_a_department_with_no_instructions_has_no_basis():
    """A hash of nothing is a stable value that looks like a basis and names nothing."""
    with pytest.raises(ValueError, match="at least one module instruction"):
        department_basis_hash({})


# ------------------------------------- the refusal at the far end, and it is correct


async def test_a_department_with_no_unit_b_certification_is_refused_not_appointed(
    world, admin
):
    """**The refusal this package exists to make honest, asserted at its consumer.**

    `appointment.generate` requires Unit A for every module a position operates AND
    Unit B for every Forge it touches. Both. Department certification is necessary,
    never sufficient - and until P-04 nothing could ever produce the unit-B half, so
    every Burkham candidate was refused for a reason no code could act on.

    Nothing here is fixed by opening a run. The run opens, no domain certification
    exists in SimForge for any department, and the candidates stay refused. What
    changes is that the refusal is now about a submission that was made rather than one
    that was structurally impossible.

    The assertion is `missing_unit_b` specifically, and NOT that the artifact is empty:
    a shortfall does not auto-reject the Pack, does not auto-appoint an uncertified
    agent and does not silently reduce scope. It reports.
    """
    from generators import pipeline
    from generators.pack import load_pack
    from tests.world import PACK_PATH, certify_for_positions

    certify_for_positions(admin)
    with admin.cursor() as cur:
        # The state that obtains: agents certified on every module they operate, and
        # their DEPARTMENT certified for nothing. This is exactly Burkham today.
        cur.execute("DELETE FROM certification WHERE unit = 'B'")
    admin.commit()

    pack = load_pack(PACK_PATH)
    async with connection() as conn:
        artifacts = await pipeline.run_all(pack, conn)

    appointment = artifacts.appointment
    shortfalls = [
        s for position in appointment.appointments
        for s in position.requires_certification
    ]
    assert shortfalls, "no candidate was refused, so unit B is not being required"
    reasons = {s.reason for s in shortfalls}
    assert reasons == {"missing_unit_b"}, (
        f"the refusal names {sorted(reasons)}; a candidate certified on every module "
        "it operates and holding no department certification is refused for exactly "
        "one reason, and collapsing it into another is how this stayed hidden"
    )
    assert appointment.shortfall is True
    assert not any(p.appointed for p in appointment.appointments), (
        "an uncertified agent was appointed"
    )
