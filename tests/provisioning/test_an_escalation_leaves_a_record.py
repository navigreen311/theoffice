"""Raised, by whom, routed to which named human, received, and answered.

RULED 21 SEPTEMBER 2026 (entry 149)
===================================

    *"An escalation leaves a record: raised, by whom, routed to which named human,
    received, and answered, with timestamps. Both escalation paths return a route and
    write nothing. An escalation path cannot be attested verified until it can be shown
    to have been travelled."*

WHAT WAS MEASURED
=================

    `governance` and `operational` resolve a recipient and return a `Route`. Neither
    writes anything, and **neither has a caller** in `broker/` or `generators/` - the
    only references outside that module are `appointment.py` declaring a path on the
    artifact and calling `assert_path`. So both paths resolve, and nothing has ever
    travelled either.

THE LOAD-BEARING TESTS IN THIS FILE
===================================

    `test_resolving_a_route_records_nothing`. The two resolvers stay resolvers: a
    function that wrote a row every time somebody asked "who would this go to" would
    fill the record with escalations nobody made, and `travelled` would then be
    satisfied by a question.

    `test_an_answer_before_a_receipt_is_refused`. Raised-and-answered in one second by
    one process proves a function returns. Receipt is the step that says somebody got
    it, and it is the whole reason this record exists.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from broker import escalation, humans
from broker.db import connection
from broker.errors import NotAuthorized, OfficeError
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
REASON = "drill: does research's governance path reach a person"


@pytest_asyncio.fixture
async def conn(operator) -> AsyncIterator:
    async with connection() as opened:
        opened.operator = operator  # type: ignore[attr-defined]
        yield opened


async def _person(name: str, email: str) -> humans.Human:
    """A real account. `account_origin` classifies every `.invalid` address as a fixture
    (entry 148), and a fixture may neither be named a recipient nor record anything, so
    the promotion is explicit."""
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=email,
        )
        await humans.grant_role(
            conn, human_id=human_id, role="ivan", venture_id=None,
            granted_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE office_human SET origin = 'human' WHERE human_id = %s",
                (human_id,),
            )
        await conn.commit()
        resolved = await humans.authenticate(conn, token)
    assert resolved is not None
    return resolved


@pytest_asyncio.fixture
async def recipient(world) -> humans.Human:
    """The human this venture and department NAMES. Entry 150: account age decides
    nothing, so somebody has to be named before anything can be routed."""
    return await _person(
        "Escalation Recipient", "escalation.recipient@provisioning.invalid"
    )


@pytest_asyncio.fixture
async def raiser(world) -> humans.Human:
    """A SECOND person, and the whole point of the split.

    The first version of this suite had one human raise, receive and answer - the shape
    `0051`'s docstring says proves nothing, demonstrated by the test meant to prove the
    opposite.
    """
    return await _person("Escalation Raiser", "escalation.raiser@provisioning.invalid")


@pytest_asyncio.fixture
async def named(conn, recipient) -> humans.Human:
    """`recipient`, named for research on greenstone."""
    await escalation.name_recipient(
        conn, venture_id=VENTURE, department="research", human=recipient,
        named_by=recipient, reason="named so this suite has somewhere to route",
    )
    return recipient


async def _raise(conn, person, **over):
    kwargs = {
        "kind": "certification", "path": escalation.Path.GOVERNANCE,
        "venture_id": VENTURE, "department": "research", "reason": REASON,
        "raised_by": person.human_id, "raised_by_kind": "human",
    }
    kwargs.update(over)
    return await escalation.raise_escalation(conn, **kwargs)


# --------------------------------------------------------------- the five facts

async def test_raising_records_who_and_where_it_went(conn, raiser, named):
    raised = await _raise(conn, raiser)
    assert raised.raised_at is not None
    assert raised.raised_by == raiser.human_id
    assert raised.raised_by_kind == "human"
    # ROUTED TO THE NAMED HUMAN, by name and by id - the name is what a reader sees and
    # the id is what the two acts are checked against.
    assert raised.route.to == named.display_name
    assert raised.route.human_id == named.human_id
    assert raised.received_at is None and raised.answered_at is None
    assert raised.travelled is False


async def test_the_three_timestamps_are_separate(conn, raiser, named):
    """One stamp cannot tell a path that works from one where somebody found the item
    three days later. The gap between raised and received is what a drill produces."""
    raised = await _raise(conn, raiser)
    received = await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    answered = await escalation.record_answer(
        conn, escalation_id=raised.escalation_id, me=named,
        answer="Use 1.0 mile and 365 days; anything wider comes back to me.",
    )
    assert raised.raised_at <= received.received_at <= answered.answered_at
    assert answered.answer.startswith("Use 1.0 mile")
    assert answered.travelled is True


async def test_resolving_a_route_records_nothing(conn, raiser, named):
    """**Load-bearing.** The resolvers stay resolvers.

    A `governance` that wrote a row every time somebody asked who a decision would go to
    would fill this record with escalations nobody raised, and `travelled` would then be
    satisfied by a question rather than by a delivery.
    """
    before = await escalation.outstanding(conn, venture_id=VENTURE)
    route = await escalation.governance(conn, reason="who would this go to")
    assert route.to
    assert await escalation.outstanding(conn, venture_id=VENTURE) == before


# ------------------------------------------ only the routed human, and never the raiser

async def test_the_raiser_may_not_receive_their_own(conn, raiser, named):
    """**The shape the first build allowed and the design forbids.**

    Even when the raiser IS the named recipient, a round trip inside one party measures
    a function call. Here they are two people and the raiser is simply not the one it
    was addressed to - both refusals apply, and the message names the recipient.
    """
    raised = await _raise(conn, raiser)
    with pytest.raises(NotAuthorized) as refused:
        await escalation.record_receipt(
            conn, escalation_id=raised.escalation_id, me=raiser
        )
    assert named.display_name in str(refused.value)


async def test_the_named_recipient_may_not_close_somebody_elses(conn, raiser, named):
    """An escalation routed to research's recipient is not operations' to close."""
    other = await _person("Other Recipient", "other.recipient@provisioning.invalid")
    raised = await _raise(conn, raiser)
    with pytest.raises(NotAuthorized):
        await escalation.record_receipt(
            conn, escalation_id=raised.escalation_id, me=other
        )


async def test_a_fixture_may_not_receive(conn, raiser, named, admin):
    """A fixture cannot answer for a decision, here as at `/proposals` (entry 148)."""
    raised = await _raise(conn, raiser)
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET origin = 'test_fixture' WHERE human_id = %s",
            (named.human_id,),
        )
    admin.commit()
    demoted = humans.Human(
        human_id=named.human_id, display_name=named.display_name,
        email=named.email, status="active", roles=named.roles, origin="test_fixture",
    )
    with pytest.raises(NotAuthorized) as refused:
        await escalation.record_receipt(
            conn, escalation_id=raised.escalation_id, me=demoted
        )
    assert "test_fixture" in str(refused.value)


async def test_the_raiser_may_not_answer(conn, raiser, named):
    raised = await _raise(conn, raiser)
    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    with pytest.raises(NotAuthorized):
        await escalation.record_answer(
            conn, escalation_id=raised.escalation_id, me=raiser, answer="mine, I think",
        )


# ------------------------------------------------------------------ the refusals

async def test_an_answer_before_a_receipt_is_refused(conn, raiser, named):
    """**Load-bearing.** Receipt is the step that says somebody got it."""
    raised = await _raise(conn, raiser)
    with pytest.raises(OfficeError) as refused:
        await escalation.record_answer(
            conn, escalation_id=raised.escalation_id, me=named,
            answer="answered without ever being picked up",
        )
    assert "not been received" in str(refused.value)


async def test_an_answer_is_a_sentence(conn, raiser, named):
    raised = await _raise(conn, raiser)
    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    with pytest.raises(OfficeError):
        await escalation.record_answer(
            conn, escalation_id=raised.escalation_id, me=named, answer="   ",
        )


async def test_a_governance_decision_may_not_be_addressed_to_an_agent(
    conn, raiser, named
):
    """`assert_path` runs before anything is written, so the refusal is not recorded as
    an escalation that happened."""
    before = await escalation.outstanding(conn, venture_id=VENTURE)
    with pytest.raises(escalation.WrongPath):
        await _raise(conn, raiser, path=escalation.Path.OPERATIONAL)
    assert await escalation.outstanding(conn, venture_id=VENTURE) == before


async def test_a_receipt_is_not_taken_twice(conn, raiser, named):
    """When it was picked up is a fact; a second caller is not a second pickup."""
    raised = await _raise(conn, raiser)
    first = await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    second = await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    assert first.received_at == second.received_at


# ---------------------------------------------------- named routing, never account age

async def test_an_unnamed_department_is_refused_rather_than_routed(conn, raiser, named):
    """**Nobody named means nowhere to go, and the venture default is not a fallback.**

    Delivering a banking decision to whoever holds the venture's default would record
    banking's path as working when nobody named for banking ever saw it.
    """
    await escalation.name_recipient(
        conn, venture_id=VENTURE, department=None, human=named, named_by=named,
        reason="the venture default, for an escalation that names no department",
    )
    with pytest.raises(OfficeError) as refused:
        await _raise(conn, raiser, department="banking")
    assert "nobody is named" in str(refused.value)
    assert "banking" in str(refused.value)


async def test_the_venture_default_serves_an_escalation_with_no_department(
    conn, raiser, named
):
    """A capacity shortfall is about the venture and carries no department."""
    await escalation.name_recipient(
        conn, venture_id=VENTURE, department=None, human=named, named_by=named,
        reason="the venture default",
    )
    raised = await _raise(
        conn, raiser, department=None, kind="capacity_shortfall"
    )
    assert raised.route.human_id == named.human_id


async def test_account_age_decides_nothing(conn, raiser, named):
    """**The measurement that produced the ruling.**

    `attributable_actor` orders by `created_at`, so routing went to the oldest account
    holding `ivan` and nothing could reach anybody else. `raiser` and `named` are both
    real accounts holding `ivan`; the one that receives is the one NAMED, whichever was
    created first.
    """
    from broker import humans as humans_module

    oldest = await humans_module.attributable_actor(conn)
    raised = await _raise(conn, raiser)
    assert raised.route.human_id == named.human_id
    assert raised.route.human_id != oldest


# ---------------------------------------------------------- what a drill produces

async def test_outstanding_is_the_queue_a_drill_leaves(conn, raiser, named):
    """Raised and not yet answered. An escalation nobody picked up is a live finding,
    and this is where a reader sees it."""
    raised = await _raise(conn, raiser)
    waiting = await escalation.outstanding(conn, venture_id=VENTURE)
    assert raised.escalation_id in {e.escalation_id for e in waiting}

    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    await escalation.record_answer(
        conn, escalation_id=raised.escalation_id, me=named, answer="answered",
    )
    after = await escalation.outstanding(conn, venture_id=VENTURE)
    assert raised.escalation_id not in {e.escalation_id for e in after}


async def test_travelled_is_per_department(conn, raiser, named):
    """One drill attests one department.

    A venture-wide escalation - a capacity shortfall - carries no department and is
    evidence about the venture's path, not about research's.
    """
    await escalation.name_recipient(
        conn, venture_id=VENTURE, department=None, human=named, named_by=named,
        reason="the venture default",
    )
    raised = await _raise(conn, raiser, department=None, kind="capacity_shortfall")
    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, me=named
    )
    await escalation.record_answer(
        conn, escalation_id=raised.escalation_id, me=named, answer="noted",
    )
    assert await escalation.travelled(
        conn, venture_id=VENTURE, department="research"
    ) is None


async def test_the_inbox_shows_only_your_own(conn, raiser, named):
    """What `/api/escalations` returns, and the reason it takes no filter.

    An escalation addressed to somebody else is not this person's to see, to receive or
    to answer - so the scope is the caller, and a page cannot widen it.
    """
    raised = await _raise(conn, raiser)
    mine = await escalation.routed_to(conn, human_id=named.human_id)
    assert [e["escalation_id"] for e in mine["waiting"]] == [str(raised.escalation_id)]
    assert mine["waiting"][0]["raised_by"] == raiser.display_name
    assert mine["waiting"][0]["reason"] == REASON

    theirs = await escalation.routed_to(conn, human_id=raiser.human_id)
    assert theirs["waiting"] == []
    assert "No escalation has ever been routed to you" in theirs["empty_reason"]
