"""A module says who reviews it, instead of inheriting an answer from its neighbours.

WHAT THIS IS FOR, IN ONE MEASUREMENT

    `cre-forge/assign_contract` routes to the compliance officer. It does that today only
    because Buyer Network Manager carries `recording_consent_required` - a flag about
    recorded calls, on a position whose modules call nobody. Item F turns that flag
    founder-held and takes it off the position, and the approval lands on the venture
    operator: Ivan, who usually wrote the MAO, approving that deal's assignment.

    Nothing fails when that happens. No rule is violated, no verdict changes, no message
    appears. The demand simply moves, because the reviewer was a side effect of a flag
    rather than a decision anybody recorded.

    `test_item_f_cannot_move_assign_contract_off_the_compliance_officer` is the whole point
    of the field, and it is written to fail if the declaration is ever dropped.

AND WHAT KEEPS THE FIELD HONEST

    A declaration ONLY NARROWS. It may send a module's approvals to the compliance officer
    where the flags would not have. It may never send a flagged module's approvals away
    from one - otherwise it is a way to move compliance work off the compliance officer
    with a sentence attached, which is the opposite of what it was built for.
    Decisions entry 108, ruling 4.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from generators.approval_projection import demand_from_the_pack
from generators.pack import load_pack
from generators.validator import v40

PACKS = Path(__file__).resolve().parents[2] / "packs"
GREENSTONE = PACKS / "greenstone.yaml"


def _with_position(pack, title, **update):
    return pack.model_copy(
        update={
            "positions_required": [
                p.model_copy(update=update) if p.position_title == title else p
                for p in pack.positions_required
            ]
        }
    )


def _reflag_buyer_network_manager(pack):
    """Put the flag back, to exercise the route it used to take.

    **Item F shipped, so the Pack no longer carries it.** This file was written while the
    flag was still on the position and the collision was ahead of us; it is behind us now.
    Rather than delete the tests that read the pre-F state, they construct it - the flag is
    what makes step 2 and ruling 4 reachable at all, and a fixture that supplies it says so
    in one place.
    """
    return _with_position(
        pack,
        "Buyer Network Manager",
        compliance_flags_in_scope=["recording_consent_required"],
    )


# ------------------------------------------------------- the declaration does something

def test_the_declared_reviewer_is_what_gate_2_routes_by():
    pack = load_pack(GREENSTONE)
    bnm = next(
        p for p in pack.positions_required if p.position_title == "Buyer Network Manager"
    )
    declared = bnm.module_reviewer_roles["cre-forge/assign_contract"]

    assert declared.role == "compliance_officer"
    assert "author of an MAO may not approve" in declared.why
    assert demand_from_the_pack(pack) == {"compliance_officer": pytest.approx(0.2)}


def test_item_f_cannot_move_assign_contract_off_the_compliance_officer():
    """**The test this field exists for, and item F has now happened.**

    Buyer Network Manager carries no compliance flag any more - item F moved
    `recording_consent_required` to `market.compliance_surface` as human-held. So the
    routing rests on the declaration alone, which is the state this field was added for:

        Pack as it stands            {compliance_officer: 0.2}
        with the declaration removed {venture_operator: 0.2}

    Ivan usually writes the MAO, so that second line is the author approving his own deal's
    assignment - and before the declaration existed, item F produced it silently.

    The second assertion is what stops this passing for the wrong reason. Without it, a
    change that made `assign_contract` route to the compliance officer by some other route
    would read as this field working.
    """
    pack = load_pack(GREENSTONE)
    bnm = next(
        p for p in pack.positions_required if p.position_title == "Buyer Network Manager"
    )
    assert bnm.compliance_flags_in_scope == [], "item F has not landed; this test is stale"

    assert demand_from_the_pack(pack) == {"compliance_officer": pytest.approx(0.2)}

    undeclared = _with_position(pack, "Buyer Network Manager", module_reviewer_roles={})
    assert demand_from_the_pack(undeclared) == {"venture_operator": pytest.approx(0.2)}


def test_a_module_with_no_declaration_routes_exactly_as_it_did():
    """Steps 2 to 4 are untouched, and most modules still take them.

    Greenstone's other four modules declare no reviewer. Two are `auto_execute` and reach
    nobody; the Deal Underwriter pair is pending. Rather than assert an empty difference,
    this drops the declaration and checks the flags still decide - which is the behaviour
    every other venture in the repository is running on.
    """
    pack = load_pack(GREENSTONE)
    undeclared = _with_position(
        pack, "Buyer Network Manager", module_reviewer_roles={}
    )
    # Step 3: no declaration and no flag, which is what the Pack is after item F.
    assert demand_from_the_pack(undeclared) == {"venture_operator": pytest.approx(0.2)}

    # Step 2: no declaration, flag restored. This is how every module in every other
    # venture still routes, and the path item F took `assign_contract` off.
    flagged = _with_position(
        _reflag_buyer_network_manager(pack),
        "Buyer Network Manager",
        module_reviewer_roles={},
    )
    assert demand_from_the_pack(flagged) == {"compliance_officer": pytest.approx(0.2)}


# ------------------------------------------------------------------------- the refusals

def test_ruling_4_refuses_routing_a_flagged_module_away_from_the_compliance_officer():
    """Naming the module and the flag, because both are needed to fix it."""
    pack = _reflag_buyer_network_manager(load_pack(GREENSTONE))
    bnm = next(
        p for p in pack.positions_required if p.position_title == "Buyer Network Manager"
    )
    declared = dict(bnm.module_reviewer_roles)
    payload = bnm.model_dump()
    payload["module_reviewer_roles"] = {
        "cre-forge/assign_contract": {
            "role": "venture_operator",
            "why": declared["cre-forge/assign_contract"].why,
        }
    }

    with pytest.raises(ValidationError) as raised:
        type(bnm).model_validate(payload)

    message = str(raised.value)
    assert "only narrows" in message
    assert "cre-forge/assign_contract -> venture_operator" in message
    assert "recording_consent_required" in message


def test_routing_to_the_compliance_officer_is_always_allowed():
    """The narrowing direction, on a position carrying no flag at all.

    Acquisition Analyst is `auto_execute`, so nothing reaches a reviewer either way - the
    point is that the DECLARATION is accepted. A rule that refused this would have made the
    field useless on exactly the positions it was built for.
    """
    pack = load_pack(GREENSTONE)
    analyst = next(
        p for p in pack.positions_required if p.position_title == "Acquisition Analyst"
    )
    payload = analyst.model_dump()
    payload["compliance_flags_in_scope"] = []
    payload["module_reviewer_roles"] = {
        "cre-forge/property_lookup": {
            "role": "compliance_officer",
            "why": "Narrowing is always permitted and this is the case that proves it.",
        }
    }
    rebuilt = type(analyst).model_validate(payload)
    assert rebuilt.module_reviewer_roles["cre-forge/property_lookup"].role == (
        "compliance_officer"
    )


def test_a_reason_is_required():
    """A bare role is a routing decision with nothing recording what it was for."""
    pack = load_pack(GREENSTONE)
    bnm = next(
        p for p in pack.positions_required if p.position_title == "Buyer Network Manager"
    )
    payload = bnm.model_dump()
    payload["module_reviewer_roles"] = {
        "cre-forge/assign_contract": {"role": "compliance_officer"}
    }
    with pytest.raises(ValidationError, match="why"):
        type(bnm).model_validate(payload)

    payload["module_reviewer_roles"] = {
        "cre-forge/assign_contract": {"role": "compliance_officer", "why": "because"}
    }
    with pytest.raises(ValidationError, match="at least 20 characters"):
        type(bnm).model_validate(payload)


def test_a_declaration_must_name_a_module_this_position_operates():
    pack = load_pack(GREENSTONE)
    bnm = next(
        p for p in pack.positions_required if p.position_title == "Buyer Network Manager"
    )
    payload = bnm.model_dump()
    payload["module_reviewer_roles"] = {
        "cre-forge/underwrite_deal": {
            "role": "compliance_officer",
            "why": "A module this position does not operate, which must be refused.",
        }
    }
    with pytest.raises(ValidationError, match="does not operate"):
        type(bnm).model_validate(payload)


# ------------------------------------------------------------------------------- V40

def test_v40_refuses_a_role_the_pack_does_not_staff():
    """The failure it prevents is a PASS that reads as a catastrophe.

    Demand routed to an unstaffed role has no review minutes behind it, so V13 divides by
    zero and prints "with no reviewer review-time at all" - an overload message, on a typo.
    """
    pack = load_pack(GREENSTONE)
    typo = _with_position(
        pack,
        "Buyer Network Manager",
        module_reviewer_roles={
            "cre-forge/assign_contract": type(
                pack.positions_required[2].module_reviewer_roles[
                    "cre-forge/assign_contract"
                ]
            )(
                role="complaince_officer",
                why="A misspelling, which is the whole failure mode this rule is for.",
            )
        },
    )
    ok, message = v40(typo)
    assert not ok
    assert "complaince_officer" in message
    assert "Buyer Network Manager/cre-forge/assign_contract" in message
    assert "compliance_officer" in message, "the message must name what the Pack does staff"


def test_v40_passes_the_real_pack():
    ok, message = v40(load_pack(GREENSTONE))
    assert ok, message
