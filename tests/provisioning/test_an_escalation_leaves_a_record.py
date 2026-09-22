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
from broker.errors import OfficeError
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
REASON = "drill: does research's governance path reach a person"


@pytest_asyncio.fixture
async def conn(operator) -> AsyncIterator:
    async with connection() as opened:
        opened.operator = operator  # type: ignore[attr-defined]
        yield opened


@pytest_asyncio.fixture
async def person(world) -> humans.Human:
    """A real account, because `governance` resolves through `attributable_actor`.

    That function refuses a fixture - *"an escalation delivered to `smoke-1a2b3c4d` is
    not delivered"* - and `account_origin` classifies every `.invalid` address as one
    (entry 148), so the promotion is explicit.
    """
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Escalation Recipient",
            email="escalation.recipient@provisioning.invalid",
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


async def _raise(conn, person, **over):
    kwargs = {
        "kind": "certification", "path": escalation.Path.GOVERNANCE,
        "venture_id": VENTURE, "department": "research", "reason": REASON,
        "raised_by": person.human_id, "raised_by_kind": "human",
    }
    kwargs.update(over)
    return await escalation.raise_escalation(conn, **kwargs)


# --------------------------------------------------------------- the five facts

async def test_raising_records_who_and_where_it_went(conn, person):
    raised = await _raise(conn, person)
    assert raised.raised_at is not None
    assert raised.raised_by == person.human_id
    assert raised.raised_by_kind == "human"
    # ROUTED TO A NAMED HUMAN, and the name and the id both - the name is what a reader
    # sees and the id is what a later reader resolves.
    assert raised.route.to
    assert raised.route.human_id is not None
    assert raised.received_at is None and raised.answered_at is None
    assert raised.travelled is False


async def test_the_three_timestamps_are_separate(conn, person):
    """One stamp cannot tell a path that works from one where somebody found the item
    three days later. The gap between raised and received is what a drill produces."""
    raised = await _raise(conn, person)
    received = await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, received_by=person.human_id
    )
    answered = await escalation.record_answer(
        conn, escalation_id=raised.escalation_id, answered_by=person.human_id,
        answer="Use 1.0 mile and 365 days; anything wider comes back to me.",
    )
    assert raised.raised_at <= received.received_at <= answered.answered_at
    assert answered.answer.startswith("Use 1.0 mile")
    assert answered.travelled is True


async def test_resolving_a_route_records_nothing(conn, person):
    """**Load-bearing.** The resolvers stay resolvers.

    A `governance` that wrote a row every time somebody asked who a decision would go to
    would fill this record with escalations nobody raised, and `travelled` would then be
    satisfied by a question rather than by a delivery.
    """
    before = await escalation.outstanding(conn, venture_id=VENTURE)
    route = await escalation.governance(conn, reason="who would this go to")
    assert route.to
    assert await escalation.outstanding(conn, venture_id=VENTURE) == before


# ------------------------------------------------------------------ the refusals

async def test_an_answer_before_a_receipt_is_refused(conn, person):
    """**Load-bearing.** Receipt is the step that says somebody got it."""
    raised = await _raise(conn, person)
    with pytest.raises(OfficeError) as refused:
        await escalation.record_answer(
            conn, escalation_id=raised.escalation_id, answered_by=person.human_id,
            answer="answered without ever being picked up",
        )
    assert "not been received" in str(refused.value)


async def test_an_answer_is_a_sentence(conn, person):
    raised = await _raise(conn, person)
    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, received_by=person.human_id
    )
    with pytest.raises(OfficeError):
        await escalation.record_answer(
            conn, escalation_id=raised.escalation_id, answered_by=person.human_id,
            answer="   ",
        )


async def test_a_governance_decision_may_not_be_addressed_to_an_agent(conn, person):
    """`assert_path` runs before anything is written, so the refusal is not recorded as
    an escalation that happened."""
    before = await escalation.outstanding(conn, venture_id=VENTURE)
    with pytest.raises(escalation.WrongPath):
        await _raise(conn, person, path=escalation.Path.OPERATIONAL)
    assert await escalation.outstanding(conn, venture_id=VENTURE) == before


async def test_a_receipt_is_not_taken_twice(conn, person):
    """When it was picked up is a fact; a second caller is not a second pickup."""
    raised = await _raise(conn, person)
    first = await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, received_by=person.human_id
    )
    second = await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, received_by=person.human_id
    )
    assert first.received_at == second.received_at


# ---------------------------------------------------------- what a drill produces

async def test_outstanding_is_the_queue_a_drill_leaves(conn, person):
    """Raised and not yet answered. An escalation nobody picked up is a live finding,
    and this is where a reader sees it."""
    raised = await _raise(conn, person)
    waiting = await escalation.outstanding(conn, venture_id=VENTURE)
    assert raised.escalation_id in {e.escalation_id for e in waiting}

    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, received_by=person.human_id
    )
    await escalation.record_answer(
        conn, escalation_id=raised.escalation_id, answered_by=person.human_id,
        answer="answered",
    )
    after = await escalation.outstanding(conn, venture_id=VENTURE)
    assert raised.escalation_id not in {e.escalation_id for e in after}


async def test_travelled_is_per_department(conn, person):
    """One drill attests one department.

    A venture-wide escalation - a capacity shortfall - carries no department and is
    evidence about the venture's path, not about research's.
    """
    raised = await _raise(conn, person, department=None, kind="capacity_shortfall")
    await escalation.record_receipt(
        conn, escalation_id=raised.escalation_id, received_by=person.human_id
    )
    await escalation.record_answer(
        conn, escalation_id=raised.escalation_id, answered_by=person.human_id,
        answer="noted",
    )
    assert await escalation.travelled(
        conn, venture_id=VENTURE, department="research"
    ) is None
