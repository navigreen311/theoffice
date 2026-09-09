"""B25 — Gate 2 pools supply, Gate 4.5 splits it, and the pooling is now a stated choice.

B24 fixed how Gate 4.5 aggregates review minutes. B25 is the divergence that fix made
visible: the two V13 implementations do not compute the same quantity, and only one of
them said anything about it. `validate_gate_4_5`'s docstring explains at length why the
two gates see different *demand* figures and is silent on *supply* — a documented
difference vouching for an undocumented one.

The fix taken was the one B25 said was probably right: **Gate 2's pooling is stated as a
deliberate simplification, and the arithmetic is untouched.** These tests are what stops
that from being a comment that rots. A shared helper would have been enforced by the
helper; a stated choice is enforced by nothing unless something reads it.

So there are two kinds of test here, and both are load-bearing:

  1. **The divergence, exhibited.** Same people, same total demand — Gate 2 passes and
     Gate 4.5 fails. Nothing else in the suite shows the two gates disagreeing on supply
     with demand held equal, which is what makes it an aggregation difference rather than
     the documented demand difference.
  2. **The choice, pinned.** Gate 2's pooled unweighted mean is asserted as the number it
     prints, and the docstring is asserted to state it. If someone later changes Gate 2's
     aggregation, these fail — which is the point. The change may well be right; it must
     not be silent, because silent is exactly how B25 happened.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from generators import approval_projection as approval_projection_gen
from generators import roles as roles_gen
from generators import workflow as workflow_gen
from generators.pack import load_pack
from generators.validator import UTILISATION_FACTOR, v13, validate, validate_gate_4_5

PACKS = Path(__file__).resolve().parents[2] / "packs"
BURKHAM = PACKS / "burkham-wickmont.draft.yaml"
GREENSTONE = PACKS / "greenstone.yaml"

_NOBODY_UNFILLED = SimpleNamespace(appointments=[])


def _capacity(pack, *entries):
    """Replace `human_capacity` with (role, coverage_hours, median_review_minutes)."""
    base = pack.human_capacity[0]
    return pack.model_copy(
        update={
            "human_capacity": [
                base.model_copy(
                    update={
                        "human_name": f"Reviewer {n}",
                        "role": role,
                        "coverage_hours": hours,
                        "median_review_minutes": minutes,
                        "backup_human": f"Reviewer {n}",
                    }
                )
                for n, (role, hours, minutes) in enumerate(entries, start=1)
            ]
        }
    )


def _pooled_gate_2_numbers(pack) -> tuple[float, float]:
    """The Gate 2 formula, written out here so the test does not read it from the code.

    A test that recomputes using the same expression it is checking asserts only that
    Python is deterministic. This is the formula as the docstring describes it — pooled,
    unweighted, every role together — so if the implementation stops matching the prose,
    this stops matching the implementation.
    """
    approvals = sum(
        p.headcount
        for p in pack.positions_required
        if p.trust_tier_ceiling != "auto_execute"
    ) * max(1.0, pack.capacity_demand.agent_days_per_week / 7.0)
    humans = pack.human_capacity
    pooled_mean = sum(h.median_review_minutes for h in humans) / len(humans)
    available = sum(h.coverage_hours * 60 * UTILISATION_FACTOR for h in humans)
    return approvals * pooled_mean, available


# ------------------------------------------------------- 1. the divergence, exhibited

async def test_gate_2_pools_a_bottleneck_that_gate_4_5_finds_at_the_same_demand():
    """The two gates disagree on the same Pack with the demand held equal.

    Two reviewers: an operator with 20 hours who takes a minute a review, and a
    compliance officer with one hour who takes thirty. Every approval goes to the
    officer.

      Gate 2   pools them: mean 15.5 minutes against 21 hours of combined coverage.
      Gate 4.5 splits them: 30 minutes against the officer's one hour, alone.

    **Total demand is 20 approvals in both, and total declared supply is identical.** The
    documented difference between the gates — Gate 2 estimating approvals from headcount
    while the Task Ledger computes them from the real workflow — is held constant here on
    purpose, so the only thing left that can explain the disagreement is how each gate
    adds its reviewers up. That is B25, in one assertion pair.

    The direction matters as much as the disagreement: **Gate 2 is the one that passes.**
    Pooling lets a slack role absorb a saturated one, so it can hide a bottleneck and can
    never invent one, which is the direction the docstring claims.
    """
    pack = _capacity(
        load_pack(GREENSTONE),
        ("venture_operator", 20.0, 1.0),
        ("compliance_officer", 1.0, 30.0),
    )

    gate_2 = await validate(pack)
    assert gate_2.get("V13").verdict.value == "PASS", (
        "pooling 21 hours of coverage against a 15.5-minute mean has to pass; if it does "
        "not, Gate 2 is no longer pooling and the docstring is now wrong"
    )

    # Same total demand Gate 2 saw — 20 approvals — all of it landing on the officer.
    projection = SimpleNamespace(
        projected_daily_approvals={"compliance_officer": 20.0, "venture_operator": 0.0}
    )
    gate_45 = await validate_gate_4_5(pack, projection, _NOBODY_UNFILLED)
    v = gate_45.get("V13")
    assert v.verdict.value == "FAIL", (
        "20 approvals at 30 minutes is 600 minutes against the officer's 36; the role "
        "split is the whole reason Gate 4.5 exists"
    )
    assert "compliance officer" in v.message
    assert "venture operator" not in v.message, (
        "the operator is not overloaded and must not appear; a per-role check that "
        "reports every role is a pooled check with extra words"
    )


# ------------------------------------------------------------ 2. the choice, pinned

async def test_gate_2_uses_the_pooled_unweighted_mean_not_gate_4_5s_weighted_one():
    """Nine hours at four minutes and three at eight: unweighted 6.0, weighted 5.0.

    Deliberately the same fixture B24's tests use for the Gate 4.5 side, so the two sit
    against each other. Same two people, same declared numbers, and the two gates take
    different review times out of them — 6.0 here, 5.0 there.

    **If this test fails because Gate 2 now prints 100, somebody has made Gate 2
    coverage-weighted.** That may be the right change. It is not a silent one: the
    docstring on `v13` states the unweighted mean as the choice, and a change that leaves
    that prose standing recreates B25 pointing the other way.
    """
    pack = _capacity(
        load_pack(GREENSTONE),
        ("compliance_officer", 9.0, 4.0),
        ("compliance_officer", 3.0, 8.0),
    )

    report = await validate(pack)
    v = report.get("V13")

    # 20 approvals x the unweighted 6.0 = 120, against 12h x 60 x 0.6 = 432.
    assert v.message == "120 of 432 review-minutes used", (
        f"expected the pooled unweighted mean of 6.0; got: {v.message}"
    )
    assert "100 of 432" not in v.message, (
        "100 would be the coverage-weighted 5.0 — that is Gate 4.5's aggregation, and "
        "the two being different is B25's stated choice, not a defect to quietly fix"
    )


async def test_gate_2_pools_across_roles_even_when_the_roles_are_different():
    """One officer, one operator, and the mean crosses the role boundary.

    Four minutes and eight, one hour each: Gate 2 charges every approval at 6.0 minutes,
    a rate that describes neither reviewer and no role. That is what pooling *is*, and it
    is asserted rather than left implicit because it is the surprising half — a reader
    who has only read `validate_gate_4_5` would expect two buckets.
    """
    pack = _capacity(
        load_pack(GREENSTONE),
        ("compliance_officer", 1.0, 4.0),
        ("venture_operator", 1.0, 8.0),
    )

    v = (await validate(pack)).get("V13")

    # 20 approvals x 6.0 = 120 against 2h x 60 x 0.6 = 72. It fails, and the failure
    # message is charged at a rate neither person declared.
    assert v.verdict.value == "FAIL"
    assert "120 review-minutes" in v.message and "72 available" in v.message, v.message


def test_the_pooling_is_stated_in_the_code_and_not_only_in_blocking_md():
    """The stated choice is the deliverable, so something has to read it.

    B25 offered two fixes: share a helper, or state the simplification. A shared helper
    would be enforced by the helper existing. **A stated choice is enforced by nothing**,
    which is how the divergence survived being written into B24's own prediction document
    and still went unfixed for a day.

    Asserted on substrings that carry meaning rather than on wording, so the prose can be
    rewritten but not deleted: what it pools, that it is deliberate, why Gate 2 cannot do
    otherwise, and the item number to read next.
    """
    # Collapsed, because the phrases below are sentences and sentences get wrapped. A
    # test that breaks when a paragraph is re-flowed teaches people to delete the test.
    doc = " ".join((v13.__doc__ or "").split())
    assert doc, "v13 has no docstring; B25's fix was the docstring"

    for phrase, why in (
        ("pool", "it must say that it pools"),
        ("Gate 4.5", "it must name the other implementation it differs from"),
        ("B25", "it must point at the item, or the next reader starts over"),
        ("optimistic", "it must say which way the simplification errs"),
        ("unweighted", "it must name the mean it takes, not only the role pooling"),
    ):
        assert phrase in doc, f"v13's docstring does not say what it pools: {why}"

    # The reason, not just the fact. "Deliberate" without a reason is an assertion of
    # authority, which is what B25 objects to in the first place.
    assert "does not exist until Gate 3" in doc, (
        "the docstring states the pooling but not why Gate 2 cannot split — the reason "
        "is that per-role demand is generator output, and without it the note is just "
        "'we meant to'"
    )


# ------------------------------------------------ 3. the real Packs, as numbers not verdicts

async def test_both_real_packs_report_their_gate_2_margin_as_the_pooled_formula():
    """A PASS looks the same at twelve minutes of margin and at twelve hours.

    Burkham: 8 headcount below auto_execute x 40/7 agent-days = 45.7 approvals, at the
    pooled 3.5 minutes = 160 against 432 available. **272 minutes of margin at Gate 2.**
    Greenstone: 20 approvals at the pooled 5.0 = 100 against 360. **260 minutes.**

    Recomputed from the Pack rather than hard-coded, so a Pack that is edited moves this
    test's expectation with it — but the *shape* of the formula is fixed here, and a Gate
    2 that stopped pooling would fail both.
    """
    for path in (BURKHAM, GREENSTONE):
        pack = load_pack(path)
        needed, available = _pooled_gate_2_numbers(pack)
        v = (await validate(pack)).get("V13")
        assert v.verdict.value == "PASS", f"{path.name}: {v.message}"
        assert v.message == f"{needed:.0f} of {available:.0f} review-minutes used", (
            f"{path.name} does not match the pooled unweighted formula: {v.message}"
        )


async def test_burkhams_gate_4_5_margin_is_still_twelve_minutes():
    """The twelve minutes, measured rather than quoted from the Pack's own comment.

    Burkham's workflow is 15 steps, none of them at `auto_execute`, so the projection is
    15 x 8 = 120 approvals a day and every one goes to `compliance_officer`. Its two
    officers declare six hours each, four minutes and three: coverage-weighted 3.5,
    so 420 review-minutes against 432 available.

    **Twelve minutes.** Pinned here because B25's fix is on the Gate 2 side and this is
    the number a Gate 2 change would have to leave alone — and because a PASS that is one
    workflow step from failing should be visible as a number to whoever reads this next,
    not recoverable only by doing the arithmetic.
    """
    pack = load_pack(BURKHAM)
    roles = await roles_gen.generate(pack)
    workflow = workflow_gen.generate(pack, roles)
    unappointed = SimpleNamespace(
        appointments=[
            SimpleNamespace(position_title=p.position_title, appointed=[])
            for p in roles.positions
        ]
    )
    projection = approval_projection_gen.generate(pack, roles, workflow, unappointed)

    assert projection.projected_daily_approvals == {"compliance_officer": 120}

    officers = [h for h in pack.human_capacity if h.role == "compliance_officer"]
    coverage = sum(h.coverage_hours for h in officers)
    weighted = sum(h.coverage_hours * h.median_review_minutes for h in officers) / coverage
    needed = 120 * weighted
    available = coverage * 60 * UTILISATION_FACTOR

    assert (needed, available) == (420.0, 432.0)
    assert available - needed == 12.0, (
        f"Burkham's Gate 4.5 margin moved to {available - needed:.0f} minutes. Whatever "
        "did that, it was not supposed to be a Gate 2 documentation change"
    )

    v = (await validate_gate_4_5(pack, projection, _NOBODY_UNFILLED)).get("V13")
    assert v.verdict.value == "PASS"
