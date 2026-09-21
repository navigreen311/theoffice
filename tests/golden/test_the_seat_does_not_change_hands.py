"""Incumbency decides a seat; roster order is a reported last resort; an unearned plan
claims nothing.

RULED 21 SEPTEMBER 2026, amending entry 145 before it merged
============================================================

    *"Eligibility prefers an existing live grant holder for the seat. Roster order is a
    tie-break only when no candidate holds a grant, and the tie-break is reported, never
    silent. A seat does not change hands because of list order."*

    *"An uncertified module's planned tier reads as none, not the declared tier. A plan
    that claims authority nothing earned reads as authority."*

WHAT MADE THEM RULINGS
======================

    The first build of entry 145 measured this against the dev database: `buyer_match`'s
    two seats passed from Ronan and Seraphine Valek - both holding live grants, both with
    an exam IN_PROGRESS, one carrying a recorded FAIL - to two candidates who came
    earlier in the roster and had never been examined. Nothing about either pair had
    changed except that certification stopped narrowing the field, and the alphabet
    decided who operates a venture.

    The second: with nobody certified, `certified_tiers` fell back to the tier the Pack
    DECLARES. Greenstone's `buyer_match` declares `auto_execute`, so six grants nothing
    had earned would have been written carrying it, in the column `resolve_grant` caps a
    live call against.

THE LOAD-BEARING TESTS IN THIS FILE
===================================

    `test_issuing_grants_does_not_move_the_artifacts_hash`. Appointment now reads
    `agent_forge_grant` and Gate 5 writes it. Every other test here would pass with that
    loop wide open, and a venture would find its Gate 10 signature void every time Gate 5
    ran.

    `test_roster_order_still_decides_when_nobody_holds_a_grant` is the second: a ranking
    that only ever preferred incumbents would satisfy the first three assertions and seat
    nobody on a venture's first run.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import provisioning
from broker.db import connection
from generators import pipeline
from generators.pack import load_pack
from tests.conftest import requires_db
from tests.world import (
    PACK_PATH,
    ROSTER,
    build_world,
    certify,
    certify_for_positions,
    seed_nv_discharge,
    teardown_world,
)

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
FORGE = "cre-forge"

#: **Acquisition Analyst is the position with a surplus**, and a surplus is the only
#: shape in which a preference can be observed. It draws from `research`, which holds
#: three candidates, and its headcount is 1 - so two of the three are passed over, and
#: which one is seated is decided by the ranking rather than by arithmetic.
#:
#: Buyer Network Manager is deliberately NOT used: operations holds exactly two
#: candidates for two seats, so every ordering seats the same pair and a test there would
#: assert nothing.
SEAT = "Acquisition Analyst"
RESEARCH = [(a, n) for a, n, d in ROSTER if d == "research"]

#: The position spans two Forges and only the CRE Forge half can be granted at all:
#: `forge_module_exclusion_guard` refuses a grant for `place_call`, because a founder
#: decision forbids an agent initiating an outbound call. So incumbency here is two of
#: the position's three modules - which is the partial case, and enough: the ranking
#: counts grants held, and two outranks one outranks none.
RESEARCH_MODULES = {
    "property_lookup": "cre-forge",
    "comp_analysis": "cre-forge",
}


@pytest.fixture
def world(admin: psycopg.Connection):
    build_world(admin)
    seed_nv_discharge(admin)
    yield admin
    teardown_world(admin)


def grant(
    conn: psycopg.Connection, agent_id: str, module_id: str, forge_id: str = FORGE
) -> uuid.UUID:
    """One live, inactive grant - the shape Gate 5 issues and `_exam_takers` reads."""
    grant_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_forge_grant "
            "  (grant_id, office_agent_id, forge_id, module_id, venture_id, "
            "   trust_tier, granted_by, origin) "
            "VALUES (%s, %s, %s, %s, %s, 'propose', %s, 'ladder')",
            (grant_id, agent_id, forge_id, module_id, VENTURE, uuid.uuid4()),
        )
    conn.commit()
    return grant_id


async def appoint():
    pack = load_pack(PACK_PATH)
    async with connection() as conn:
        return await pipeline.run_all(pack, conn)


def seat(artifacts, title: str):
    return next(
        a for a in artifacts.appointment.appointments if a.position_title == title
    )


# --------------------------------------------------- the seat does not change hands

async def test_a_grant_holder_keeps_the_seat_over_a_roster_earlier_candidate(
    world, admin
):
    """The measurement that produced the ruling, as an assertion.

    Nobody is certified, so certification cannot decide. The last research agent by name
    holds grants for both grantable modules; the two ahead of it hold none. It must be
    seated.
    """
    last_id, last_name = RESEARCH[-1]
    for module_id, forge_id in RESEARCH_MODULES.items():
        grant(admin, last_id, module_id, forge_id)

    position = seat(await appoint(), SEAT)
    assert position.headcount_required == 1, "this test needs one seat and a surplus"
    assert [a.agent_name for a in position.appointed] == [last_name], (
        f"{last_name} holds a live grant for every grantable module and came LAST in "
        "the roster; "
        f"the seat went to {[a.agent_name for a in position.appointed]} instead, which "
        "is a seat changing hands because of list order"
    )
    assert position.tie_break is None, (
        "incumbency decided this, which is a reason - a tie-break must not be reported "
        "where one was not taken"
    )


async def test_more_of_the_seat_held_outranks_less(world, admin):
    """Counted, not flagged. A candidate holding two of a position's modules is more the
    incumbent than one holding a single module, and no threshold had to be picked."""
    partial_id, _partial_name = RESEARCH[0]
    full_id, full_name = RESEARCH[-1]
    grant(admin, partial_id, "property_lookup", "cre-forge")
    for module_id, forge_id in RESEARCH_MODULES.items():
        grant(admin, full_id, module_id, forge_id)

    position = seat(await appoint(), SEAT)
    assert [a.agent_name for a in position.appointed] == [full_name], (
        "one grant outranked two"
    )


async def test_roster_order_still_decides_when_nobody_holds_a_grant(world, admin):
    """**Load-bearing.** A ranking that only ever preferred incumbents would seat nobody
    on a venture's first run, and every assertion above would still pass."""
    position = seat(await appoint(), SEAT)
    assert len(position.appointed) == position.headcount_required
    assert [a.agent_name for a in position.appointed] == [
        n for _a, n in RESEARCH[:position.headcount_required]
    ]


async def test_the_tie_break_is_reported_when_the_alphabet_decides(world, admin):
    """*"the tie-break is reported, never silent."*

    Three eligible candidates, one seat, nobody holding a grant and nobody certified.
    The seat was decided by where two names fall in an alphabet, and that is a decision
    about who operates a venture.
    """
    position = seat(await appoint(), SEAT)
    assert position.tie_break is not None, (
        "roster order decided the second seat and the artifact says nothing about it"
    )
    assert "roster order decided" in position.tie_break
    seated_last = position.appointed[-1].agent_name
    assert seated_last in position.tie_break
    assert "neither holds a grant" in position.tie_break


async def test_the_tie_break_reaches_the_gate_sentence(world, admin):
    """Reported where an operator reads, not only where a hash is taken.

    `tie_break` is kept out of the serialised artifact - see
    `PositionAppointment.omit_from_serialisation` - so V24's sentence is the whole of
    "never silent", and this is the test that makes that true.
    """
    from generators.validator import validate_gate_4_5

    pack = load_pack(PACK_PATH)
    artifacts = await appoint()
    report = await validate_gate_4_5(
        pack, artifacts.approval_projection, artifacts.appointment
    )
    v24 = next(r for r in report.results if r.rule_id == "V24")
    assert "TIE-BREAK" in v24.message
    assert "roster order decided" in v24.message


# ------------------------------------------------- the loop this must not open

async def test_issuing_grants_does_not_move_the_artifacts_hash(world, admin):
    """**The load-bearing test of this amendment.**

    Appointment reads `agent_forge_grant`; Gate 5 writes it. If anything grant-derived
    reached the serialised artifact, issuing grants would move `artifacts_hash` and void
    every Gate 10 signature bound to it - measured the first time this was built, as
    twelve suites going red with `Gate 10 awaiting_human` on a run where the appointment
    had not changed.

    What makes the ordering safe to use at all is that Gate 5 grants to exactly the
    agents already seated, so preferring holders re-seats the same people. The counts
    move; the seating does not; and the hash must not.
    """
    certify_for_positions(admin)
    before = await appoint()
    hash_before = provisioning.artifacts_hash(before)

    for position in before.appointment.appointments:
        for agent in position.appointed:
            for module_id in agent.modules:
                with admin.cursor() as cur:
                    cur.execute(
                        "SELECT forge_id FROM forge_module_registry WHERE module_id = %s",
                        (module_id,),
                    )
                    row = cur.fetchone()
                if row and row[0] == FORGE:
                    grant(admin, agent.office_agent_id, module_id)

    after = await appoint()
    assert provisioning.artifacts_hash(after) == hash_before, (
        "issuing grants moved the artifacts hash. Every Gate 10 signature bound to the "
        "old one is now void, and nothing about the appointment changed"
    )
    assert [a.agent_name for p in after.appointment.appointments for a in p.appointed] \
        == [a.agent_name for p in before.appointment.appointments for a in p.appointed]


# ------------------------------------------- a plan that earned nothing claims nothing

async def test_an_uncertified_module_has_no_planned_tier(world, admin):
    """*"An uncertified module's planned tier reads as none, not the declared tier."*

    Absent from the map, never blanked and never floored to `suggest` - which is still
    an authority level.
    """
    artifacts = await appoint()
    for position in artifacts.appointment.appointments:
        for agent in position.appointed:
            assert not agent.certified, "this world certifies nobody"
            assert agent.certified_tiers == {}, (
                f"{agent.agent_name} has a planned tier for a module it is not "
                f"certified on: {agent.certified_tiers}"
            )


async def test_the_planned_grant_carries_no_tier(world, admin):
    """The column `resolve_grant` caps a live call against. NULL, not the ceiling."""
    artifacts = await appoint()
    planned = artifacts.runtime_config.grants
    assert planned, "no grant was planned, so this test asserted nothing"
    assert all(g.trust_tier is None for g in planned), (
        "a grant nothing earned plans an authority level: "
        f"{sorted({g.trust_tier for g in planned})}"
    )


async def test_a_certified_module_still_plans_its_capped_tier(world, admin):
    """**The test that keeps this a refusal rather than an off switch.** A version that
    planned no tier for anybody would satisfy both assertions above and end provisioning.
    """
    certify(admin, [ROSTER[0][0]], ["property_lookup", "comp_analysis"],
            unit_b_departments=["research"])
    certify(admin, [ROSTER[0][0]], ["place_call"], forge="voiceforge",
            unit_b_departments=["research"])

    artifacts = await appoint()
    tiers = {
        g.trust_tier for g in artifacts.runtime_config.grants
        if g.office_agent_id == ROSTER[0][0]
    }
    assert tiers, "the certified agent planned no grant at all"
    assert None not in tiers, "a certified module must still carry its capped tier"
