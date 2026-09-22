"""An escalation is overdue four hours after it is raised, and overdue cancels nothing.

RULED 22 SEPTEMBER 2026 (decisions entry 158)
=============================================

    *"An escalation is overdue four hours after it is raised, for every venture and
    department. Overdue flags it and cancels nothing. Measured: d8e8f35c sat 13 hours
    with nothing marking it late."*

THE ONE THAT CARRIES THE RULING
===============================

    `test_overdue_changes_nothing_about_the_row`. Four hours is a number and could be
    any number; *"flags it and cancels nothing"* is the part that decides what this is.
    An escalation that expired at four hours would be one the platform had given up on,
    and the drill it came from is evidence that people arrive late rather than not at
    all - `d8e8f35c` was received at thirteen hours and answered four minutes later.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from broker import escalation
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
RECIPIENT = uuid.UUID("0d3adbee-0000-4000-8000-00000000600d")


def _recipient(admin: psycopg.Connection) -> uuid.UUID:
    """`governance_names_a_human` (entry 149) needs somebody on file."""
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'Overdue Recipient', 'overdue@recipient.invalid', "
            "        'bearer_token', 'test_fixture', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (RECIPIENT, f"overdue-{RECIPIENT.hex}"),
        )
    admin.commit()
    return RECIPIENT


def _raise(admin: psycopg.Connection, *, age: timedelta,
           received: bool = False, answered: bool = False) -> uuid.UUID:
    """One escalation, raised `age` ago. Written directly so the clock can be chosen."""
    escalation_id = uuid.uuid4()
    raised_at = datetime.now(UTC) - age
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO escalation_record
              (escalation_id, venture_id, department, path, kind, reason, raised_at,
               raised_by, raised_by_kind, routed_to_name, routed_to_human,
               received_at, received_by, answered_at, answered_by, answer)
            VALUES (%s, %s, 'research', 'governance', 'certification',
                    'drill: is this marked late', %s, %s, 'agent',
                    'Overdue Recipient', %s, %s, %s, %s, %s, %s)
            """,
            (escalation_id, VENTURE, raised_at, uuid.uuid4(), _recipient(admin),
             raised_at + timedelta(minutes=5) if received or answered else None,
             RECIPIENT if received or answered else None,
             raised_at + timedelta(minutes=6) if answered else None,
             RECIPIENT if answered else None,
             "answered" if answered else None),
        )
    admin.commit()
    return escalation_id


def _cleanup(admin: psycopg.Connection, *ids: uuid.UUID) -> None:
    with admin.cursor() as cur:
        for escalation_id in ids:
            cur.execute(
                "DELETE FROM escalation_record WHERE escalation_id = %s",
                (escalation_id,),
            )
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (RECIPIENT,))
    admin.commit()


# --------------------------------------------------------------------- the boundary

def test_four_hours_is_the_line():
    """The predicate, at the second either side of it.

    `is_overdue` takes the clock as an argument so this is a test about the rule rather
    than a test about how fast the suite runs.
    """
    now = datetime.now(UTC)
    for age, expected in (
        (timedelta(hours=3, minutes=59, seconds=59), False),
        (timedelta(hours=4), True),
        (timedelta(hours=4, seconds=1), True),
        (timedelta(hours=13), True),
    ):
        assert escalation.is_overdue(now - age, None, now=now) is expected, age


def test_the_rule_is_four_hours_and_says_so_once():
    """One constant, so a second spelling cannot drift from it."""
    assert timedelta(hours=4) == escalation.OVERDUE_AFTER


def test_receipt_stops_the_clock():
    """**Receipt, not the answer.**

    The ruling is about an escalation nobody has picked up. Once a named human has said
    they have it, what is outstanding is their answer - a different question, and not
    one entry 158 rules on.
    """
    now = datetime.now(UTC)
    raised = now - timedelta(hours=13)
    received = now - timedelta(hours=1)
    assert escalation.is_overdue(raised, None, now=now) is True
    assert escalation.is_overdue(raised, received, now=now) is False


# ------------------------------------------------------- it flags, and cancels nothing

async def test_overdue_changes_nothing_about_the_row(admin):
    """**THE RULING.** *"Overdue flags it and cancels nothing."*

    Asserted by reading every column before and after, because "cancels nothing" is a
    statement about what is NOT written and there is no single field to watch. The
    escalation stays receivable and answerable; `d8e8f35c` was received at thirteen
    hours and answered four minutes later, which is what a rule that cancelled would
    have made impossible.
    """
    late = _raise(admin, age=timedelta(hours=13))
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT * FROM escalation_record WHERE escalation_id = %s", (late,)
            )
            before = cur.fetchone()

        async with connection() as conn:
            found = await escalation.overdue(conn, venture_id=VENTURE)
            assert [e.escalation_id for e in found] == [late]
            # And the sweep, which is the thing that runs unattended.
            from broker import deadlines

            report = await deadlines.run_once(conn)

        with admin.cursor() as cur:
            cur.execute(
                "SELECT * FROM escalation_record WHERE escalation_id = %s", (late,)
            )
            after = cur.fetchone()

        assert after == before, "being overdue changed the row"
        assert report["escalations_overdue"] >= 1
        assert report["escalations_expired"] == 0, (
            "an overdue escalation was expired; entry 158 says overdue cancels nothing"
        )
    finally:
        _cleanup(admin, late)


async def test_an_overdue_escalation_is_still_in_the_inbox(admin):
    """It is flagged where it is worked, not moved out of the way.

    A late item that left `waiting` would be a cancellation wearing a different word.
    """
    late = _raise(admin, age=timedelta(hours=13))
    fresh = _raise(admin, age=timedelta(minutes=30))
    try:
        async with connection() as conn:
            inbox = await escalation.routed_to(conn, human_id=RECIPIENT)
        waiting = {item["escalation_id"]: item for item in inbox["waiting"]}
        assert str(late) in waiting and str(fresh) in waiting
        assert waiting[str(late)]["overdue"] is True
        assert waiting[str(fresh)]["overdue"] is False
        assert waiting[str(late)]["overdue_after_hours"] == 4
    finally:
        _cleanup(admin, late, fresh)


async def test_an_answered_escalation_is_never_overdue(admin):
    answered = _raise(admin, age=timedelta(hours=13), received=True, answered=True)
    try:
        async with connection() as conn:
            assert await escalation.overdue(conn, venture_id=VENTURE) == []
    finally:
        _cleanup(admin, answered)


# --------------------------------------------------------- every venture and department

async def test_the_rule_is_the_same_for_every_venture(admin):
    """*"For every venture and department"* - so `overdue()` asks across all of them.

    A count that had to be asked per venture would report a number that depended on who
    was asking, and the sweep needs one number.
    """
    late = _raise(admin, age=timedelta(hours=9))
    try:
        async with connection() as conn:
            everywhere = await escalation.overdue(conn)
            just_greenstone = await escalation.overdue(conn, venture_id=VENTURE)
            nowhere = await escalation.overdue(conn, venture_id="burkham-wickmont")
        assert late in [e.escalation_id for e in everywhere]
        assert late in [e.escalation_id for e in just_greenstone]
        assert late not in [e.escalation_id for e in nowhere]
    finally:
        _cleanup(admin, late)


async def test_nothing_configures_the_threshold_per_venture():
    """**Load-bearing.** One number, and no way to make it two.

    A per-venture deadline would be a second thing to configure, a second thing to get
    wrong, and a reason for every late escalation to be somebody else's rule. This reads
    the signature, so adding a way to vary it fails the build.
    """
    import inspect

    for name in ("is_overdue", "overdue"):
        parameters = set(inspect.signature(getattr(escalation, name)).parameters)
        for forbidden in ("after", "threshold", "overdue_after", "hours", "sla"):
            assert forbidden not in parameters, (
                f"{name} takes {forbidden!r}, which makes the four hours configurable"
            )
