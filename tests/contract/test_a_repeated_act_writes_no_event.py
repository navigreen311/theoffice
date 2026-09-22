"""A repeated receipt or answer changes nothing and claims nothing.

RULED 22 SEPTEMBER 2026 (decisions entry 159)
=============================================

    *"A repeated receipt or answer writes no audit event. `record_receipt` and
    `record_answer` write only when the row changed, as `grant_role` does. Measured: two
    `escalation_answered` entries 8 seconds apart for one answer on d8e8f35c."*

WHAT WAS ALREADY RIGHT, AND WHAT WAS NOT
========================================

    The rows were always safe. Both UPDATEs are guarded - `received_at IS NULL`,
    `answered_at IS NULL` - so a second call has never moved a timestamp or replaced an
    answer.

    The audit entries were not. `record_answer` called `write_event` unconditionally;
    `record_receipt` guarded on `if found.received_at is not None`, which is true for a
    fresh receipt AND for a repeat. So a second call left the record alone and wrote a
    claim that it had not.

    `grant_role` has read `rowcount` for this since entry 149. These two were written
    after that entry and did not inherit it.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import account_origin, escalation, humans
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
RECIPIENT = uuid.UUID("0dd1c0de-0000-4000-8000-0000000159aa")
RAISER = uuid.UUID("0dd1c0de-0000-4000-8000-0000000159bb")


async def _person(admin: psycopg.Connection, human_id: uuid.UUID,
                  name: str) -> humans.Human:
    """A real account — `_only_the_routed_human` refuses a fixture (entry 150)."""
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, %s, %s, 'bearer_token', 'human', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            (human_id, name, f"{human_id.hex[:8]}@repeated.invalid",
             f"repeated-{human_id.hex}"),
        )
    admin.commit()
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT human_id, display_name, email, status, origin, auth_method "
            "  FROM office_human WHERE human_id = %s", (human_id,))
        row = await cur.fetchone()
    return humans.Human(
        human_id=row[0], display_name=row[1], email=row[2], status=row[3],
        roles=(), origin=row[4], auth_method=row[5],
    )


def _escalation(admin: psycopg.Connection) -> uuid.UUID:
    escalation_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO escalation_record
              (escalation_id, venture_id, department, path, kind, reason,
               raised_by, raised_by_kind, routed_to_name, routed_to_human)
            VALUES (%s, %s, 'research', 'governance', 'certification',
                    'drill: does a repeat write a second entry', %s, 'agent',
                    'Repeat Recipient', %s)
            """,
            (escalation_id, VENTURE, uuid.uuid4(), RECIPIENT),
        )
    admin.commit()
    return escalation_id


def _events(admin: psycopg.Connection, event_type: str,
            escalation_id: uuid.UUID) -> int:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM audit_log WHERE event_type = %s "
            "   AND subject->>'escalation_id' = %s",
            (event_type, str(escalation_id)),
        )
        return int(cur.fetchone()[0])


def _cleanup(admin: psycopg.Connection, escalation_id: uuid.UUID) -> None:
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM escalation_record WHERE escalation_id = %s", (escalation_id,)
        )
        cur.execute(
            "DELETE FROM office_human WHERE human_id = ANY(%s)", ([RECIPIENT, RAISER],)
        )
    admin.commit()


# ------------------------------------------------------------------------- receipt

async def test_a_second_receipt_writes_no_second_event(admin):
    """**The ruling, on the receipt side.**

    `record_receipt` guarded on `if found.received_at is not None` — true for a fresh
    receipt and for a repeat alike — so the entry was written every time somebody
    clicked.
    """
    me = await _person(admin, RECIPIENT, "Repeat Recipient")
    escalation_id = _escalation(admin)
    try:
        async with connection() as conn:
            first = await escalation.record_receipt(
                conn, escalation_id=escalation_id, me=me)
            assert _events(admin, "escalation_received", escalation_id) == 1

            second = await escalation.record_receipt(
                conn, escalation_id=escalation_id, me=me)

        assert _events(admin, "escalation_received", escalation_id) == 1, (
            "a repeated receipt wrote a second entry claiming a pickup that did not "
            "happen"
        )
        # And the row is untouched, which it always was.
        assert first.received_at == second.received_at
    finally:
        _cleanup(admin, escalation_id)


# -------------------------------------------------------------------------- answer

async def test_a_second_answer_writes_no_second_event(admin):
    """**The ruling, on the side that was measured.**

    `d8e8f35c` carries two `escalation_answered` rows eight seconds apart — 10:44:31 and
    10:44:39, one escalation, the same text. A double submit on the console form.
    """
    me = await _person(admin, RECIPIENT, "Repeat Recipient")
    escalation_id = _escalation(admin)
    try:
        async with connection() as conn:
            await escalation.record_receipt(
                conn, escalation_id=escalation_id, me=me)
            first = await escalation.record_answer(
                conn, escalation_id=escalation_id, me=me,
                answer="Received and answered; this is the answer that counts.")
            assert _events(admin, "escalation_answered", escalation_id) == 1

            second = await escalation.record_answer(
                conn, escalation_id=escalation_id, me=me,
                answer="A different sentence, submitted eight seconds later.")

        assert _events(admin, "escalation_answered", escalation_id) == 1, (
            "a repeated answer wrote a second entry; that is the defect this fixes"
        )
        # THE FIRST ANSWER STANDS. Not just the timestamp - the text too, so a second
        # submit cannot quietly replace what somebody said.
        assert first.answered_at == second.answered_at
        assert second.answer == "Received and answered; this is the answer that counts."
    finally:
        _cleanup(admin, escalation_id)


# ------------------------------------------------- the rule, stated where it is shared

async def test_the_first_act_still_writes_its_event(admin):
    """**Load-bearing.** A guard that wrote nothing at all would pass both tests above.

    The point is not silence, it is one entry per act.
    """
    me = await _person(admin, RECIPIENT, "Repeat Recipient")
    escalation_id = _escalation(admin)
    try:
        async with connection() as conn:
            await escalation.record_receipt(
                conn, escalation_id=escalation_id, me=me)
            await escalation.record_answer(
                conn, escalation_id=escalation_id, me=me, answer="Answered once.")
        assert _events(admin, "escalation_received", escalation_id) == 1
        assert _events(admin, "escalation_answered", escalation_id) == 1
    finally:
        _cleanup(admin, escalation_id)


async def test_grant_role_still_follows_the_same_rule(admin):
    """The precedent, asserted rather than cited.

    Entry 149 put this rule in `grant_role` and it has held since. It is checked here
    because entry 159 exists precisely because two functions written AFTER that entry
    did not inherit it — so the thing worth protecting is the rule, not one call site.
    """
    subject = uuid.uuid4()
    granter = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, 'Grant Subject', %s, 'bearer_token', %s, %s)",
            (subject, f"{subject.hex[:8]}@repeated.invalid",
             account_origin.TEST_FIXTURE, f"grant-{subject.hex}"),
        )
    admin.commit()

    def granted_events() -> int:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM audit_log WHERE event_type = 'human_role_granted' "
                "   AND subject->>'human_id' = %s", (str(subject),)
            )
            return int(cur.fetchone()[0])

    try:
        async with connection() as conn:
            await humans.grant_role(
                conn, human_id=subject, role="venture_operator",
                venture_id=VENTURE, granted_by=granter)
            assert granted_events() == 1
            await humans.grant_role(
                conn, human_id=subject, role="venture_operator",
                venture_id=VENTURE, granted_by=granter)
        assert granted_events() == 1
    finally:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (subject,))
            cur.execute("DELETE FROM office_human WHERE human_id = %s", (subject,))
        admin.commit()
