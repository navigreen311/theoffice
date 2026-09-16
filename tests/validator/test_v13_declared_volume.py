"""V13, both gates, against a declared per-module volume instead of the constant 8.

WHAT THIS FILE REPLACES, AND WHY THE OLD ONE COULD NOT BE KEPT

    `test_v13_gate_2_aggregation.py` pinned B25: the two V13 implementations did not
    compute the same quantity, Gate 2 pooled supply across roles and estimated demand from
    headcount, Gate 4.5 split by role and walked the real workflow, and only one of them
    said so. Its six tests asserted that divergence - one of them by name
    (`test_gate_2_pools_a_bottleneck_that_gate_4_5_finds_at_the_same_demand`).

    **The divergence is gone, so tests that assert it would now fail for the right reason
    and be deleted for the wrong one.** Gate 2 could not split demand by role because
    nothing in the Pack attributed demand to a reviewer; a declared per-module volume sits
    on the position, and the position carries the flags that pick the reviewer. Both gates
    now read the same rates through the same three helpers.

    B25 is closed by construction rather than by comment, which is what its own note asked
    for: *"a shared helper would have been enforced by the helper; a stated choice is
    enforced by nothing unless something reads it."*

WHAT IS LEFT TO PIN, AND IT IS THE PART THAT CAN STILL ROT

    1. An undeclared volume BLOCKS and names the module. The constant it replaced is the
       reason: a number standing in for a missing fact reports a verdict about a venture
       nobody measured.
    2. A declared volume is used AS DECLARED - not scaled by headcount. The old constant
       was per holder, so demand rose when the roster grew and nothing happened in the
       world.
    3. Only `review_hours` is supply. Countersign and other hours are declared, reconcile
       against the total, and buy no review capacity.
    4. The one difference the two gates still have is certification, and it is named.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from generators import approval_projection as projection_gen
from generators.approval_projection import (
    VolumeNotDeclaredError,
    demand_from_the_pack,
    modules_needing_volume,
)
from generators.pack import load_pack
from generators.validator import (
    UTILISATION_FACTOR,
    _review_supply_by_role,
    v13,
    validate_gate_4_5,
)

PACKS = Path(__file__).resolve().parents[2] / "packs"
GREENSTONE = PACKS / "greenstone.yaml"
BURKHAM = PACKS / "burkham-wickmont.draft.yaml"

_NOBODY_UNFILLED = SimpleNamespace(appointments=[])


def _bnm(pack):
    return next(
        p for p in pack.positions_required if p.position_title == "Buyer Network Manager"
    )


def _with_position(pack, title, **update):
    """Replace one position, leaving the rest of the Pack alone."""
    return pack.model_copy(
        update={
            "positions_required": [
                p.model_copy(update=update) if p.position_title == title else p
                for p in pack.positions_required
            ]
        }
    )


def _safe_demand(pack):
    try:
        return demand_from_the_pack(pack)
    except VolumeNotDeclaredError:
        return {}


def _gate_4_5(pack):
    """Gate 4.5 with a projection the Pack itself implies and nobody unfilled."""
    projection = SimpleNamespace(projected_daily_approvals=dict(_safe_demand(pack)))
    return asyncio.run(validate_gate_4_5(pack, projection, _NOBODY_UNFILLED))


# --------------------------------------------------------------- an undeclared volume

def test_gate_2_blocks_on_an_undeclared_volume_and_names_the_module():
    """Burkham's live Pack, unedited. This is the whole of its Gate 2 verdict today."""
    pack = load_pack(BURKHAM)
    ok, message = v13(pack)

    assert not ok
    assert message.startswith("volume not declared:")
    for module in (
        "Intake Concierge/capitalforge/record_consent",
        "Placement Strategist/capitalforge/submit_application",
        "Compliance Reviewer/capitalforge/scan_communication",
        "Compliance Reviewer/capitalforge/regulator_dossier_export",
    ):
        assert module in message, f"{module} is not named in the refusal"

    # Named, and named ONLY - a module at auto_execute asks nobody, so a rate for it would
    # multiply by zero. Requiring one would be requiring a number nobody can act on.
    assert "capitalforge/client_read" not in message
    assert "capitalforge/portfolio_health" not in message


def test_gate_4_5_blocks_on_the_same_undeclared_volume():
    """Not a second implementation of the refusal - the same one, from the projection.

    Gate 4.5's demand comes from the projection artifact, so the refusal surfaces when the
    projection is built rather than when the rule is evaluated. Asserting it here is what
    stops a future caller from catching the exception and substituting a default.
    """
    pack = load_pack(BURKHAM)
    with pytest.raises(VolumeNotDeclaredError) as raised:
        demand_from_the_pack(pack)
    assert "Intake Concierge/capitalforge/record_consent" in raised.value.missing


def test_an_auto_execute_module_needs_no_volume_and_lowering_its_tier_requires_one():
    """The exemption is a consequence of the tier, and it expires with the tier.

    Greenstone declares `buyer_match` auto_execute and no volume for it. Drop it to
    `propose` and the same Pack is refused, naming that module - which is what stops the
    exemption becoming a place to park a module nobody wants to size.
    """
    pack = load_pack(GREENSTONE)
    assert modules_needing_volume(pack) == []

    lowered = _with_position(
        pack,
        "Buyer Network Manager",
        module_trust_tiers={"cre-forge/buyer_match": "propose"},
    )
    assert modules_needing_volume(lowered) == [
        "Buyer Network Manager/cre-forge/buyer_match"
    ]
    ok, message = v13(lowered)
    assert not ok
    assert "Buyer Network Manager/cre-forge/buyer_match" in message


def test_an_undeclared_divisor_blocks_rather_than_assuming_a_week():
    """Nothing in a Pack supplied one, so nothing infers one.

    `agent_days_per_week` is agent-days across the venture, `shift_pattern` is prose, and
    Gate 2 used to divide by a hardcoded 7.0. Removing the declared field must refuse, not
    fall back to any of the three.
    """
    pack = load_pack(GREENSTONE)
    no_divisor = pack.model_copy(
        update={
            "capacity_demand": pack.capacity_demand.model_copy(
                update={"operating_days_per_week": None}
            )
        }
    )
    ok, message = v13(no_divisor)
    assert not ok
    assert "operating_days_per_week" in message


# -------------------------------------------------- a declared volume, used as declared

def test_the_declared_rate_is_used_and_is_not_multiplied_by_headcount():
    """One closed assignment a week, over five operating days, is 0.2 approvals a day.

    **The headcount assertion is the load-bearing half.** The constant this replaced was
    per (step, holder, module), so demand scaled with the roster: appointing a second Buyer
    Network Manager doubled the projected reviews without the venture closing a single
    extra deal. A rate is a property of the business.
    """
    pack = load_pack(GREENSTONE)
    assert _bnm(pack).expected_weekly_volume == {"cre-forge/assign_contract": 1}
    assert pack.capacity_demand.operating_days_per_week == 5

    demand = demand_from_the_pack(pack)
    assert demand == {"compliance_officer": pytest.approx(0.2)}

    for headcount in (1, 2, 10, 50):
        grown = _with_position(pack, "Buyer Network Manager", headcount=headcount)
        assert demand_from_the_pack(grown)["compliance_officer"] == pytest.approx(0.2), (
            f"demand moved when headcount became {headcount}. The rate is the "
            "business's, not the roster's."
        )


def test_gate_2_passes_greenstone_on_the_declared_rate():
    """The verdict, with its arithmetic, so a change to either side is visible here."""
    pack = load_pack(GREENSTONE)
    ok, message = v13(pack)
    assert ok, message
    # 0.2 approvals a day; Ira reviews at 10 minutes; 2 minutes of demand.
    # Supply is review hours only: Ivan 1h + Ira 1h = 2h x 60 x 0.6 = 72.
    assert "0.20 projected approvals" in message
    assert "72 review-minutes" in message


# ------------------------------------------------------------- only review hours supply

def test_only_review_hours_are_supply():
    """Countersign and other hours are declared, reconcile, and buy no review capacity.

    Greenstone declares six founder-hours across two people and two of them are review.
    Supply is 2h x 60 x 0.6 = 72, not 6h x 60 x 0.6 = 216 - and the 144-minute difference
    is the review capacity the Pack used to assert for work that is not review.
    """
    pack = load_pack(GREENSTONE)
    total_declared = sum(h.coverage_hours for h in pack.human_capacity)
    review_declared = sum(h.review_hours or 0 for h in pack.human_capacity)
    assert (total_declared, review_declared) == (6, 2)

    supply = _review_supply_by_role(pack)
    assert sum(supply.values()) == pytest.approx(2 * 60 * UTILISATION_FACTOR)
    assert sum(supply.values()) != pytest.approx(6 * 60 * UTILISATION_FACTOR)


def test_an_unsplit_pack_blocks_at_both_gates_rather_than_reading_the_total_as_review():
    """`coverage_hours` is the total. Reading it as review is the defect entry 96 §5 names.

    Burkham's live Pack is the unsplit case and it blocks on volume first, so this uses
    Greenstone with the split removed - the state every Pack authored before this change
    is in.
    """
    pack = load_pack(GREENSTONE)
    unsplit = pack.model_copy(
        update={
            "human_capacity": [
                h.model_copy(
                    update={
                        "review_hours": None,
                        "countersign_hours": None,
                        "other_hours": None,
                    }
                )
                for h in pack.human_capacity
            ]
        }
    )
    ok, message = v13(unsplit)
    assert not ok
    assert "hours not split" in message
    assert "Ivan" in message and "Ira Green" in message

    report = _gate_4_5(unsplit)
    assert report.get("V13").message.startswith("hours not split")


def test_a_half_declared_split_is_refused_at_load():
    """An omitted kind reads as zero, which asserts more than leaving the split out does."""
    pack = load_pack(GREENSTONE)
    with pytest.raises(ValueError, match="Declare all three or none"):
        pack.human_capacity[0].model_copy(
            update={"other_hours": None}
        ).model_validate(
            pack.human_capacity[0].model_dump() | {"other_hours": None}
        )


def test_a_split_that_does_not_reconcile_is_refused():
    """The total is what the console shows; a split that disagrees describes two people."""
    pack = load_pack(GREENSTONE)
    entry = pack.human_capacity[0].model_dump()
    entry["review_hours"] = 5
    with pytest.raises(ValueError, match="must reconcile"):
        type(pack.human_capacity[0]).model_validate(entry)


# ------------------------------------------------- what still differs between the gates

def test_the_only_remaining_difference_between_the_gates_is_certification():
    """Same rates, same supply, same verdict - until an appointment caps a tier.

    Stated in `v13`'s docstring and asserted here, because a stated choice is enforced by
    nothing unless something reads it. That sentence is B25's, and it is the reason this
    file exists rather than a comment.
    """
    pack = load_pack(GREENSTONE)
    gate_2_ok, _ = v13(pack)
    report = _gate_4_5(pack)

    assert gate_2_ok
    assert report.get("V13").verdict.value == "PASS"

    source = Path(projection_gen.__file__).read_text(encoding="utf-8")
    assert "Not multiplied by headcount" in source, (
        "the reason the rate is not scaled by roster size left the code"
    )
