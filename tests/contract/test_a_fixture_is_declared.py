"""A fixture is declared at creation, and nothing infers one from a name or an address.

RULED 21 SEPTEMBER 2026 (decisions entry 151)
=============================================

    *"A fixture is declared, never guessed. `origin` is set explicitly at creation.
    Reclassify `dev-all build check` as `test_fixture`. Measured: it read
    `origin='human'`, so `assert_named_human` would not have refused it."*

WHAT THE GUESS MISSED
=====================

    `account_origin.origin_of` matched a display name shaped like `smoke-1a2b3c4d` or an
    address under a reserved `.invalid` domain. `dev-all build check` carries the address
    `dev-all@localhost`. Neither shape, so: a person.

    Nothing in this repository creates that account and `audit_log` holds no creation
    event for it, so how it was made is an open question rather than a fact this file
    can state.

    It held the `ivan` role - founder authority, the strongest in the system - from
    17 to 21 September, and `assert_named_human` would not have stopped it deciding a
    proposal, receiving an escalation or attesting a department. Measured: it did none
    of those, signed nothing and wrote no audit event. Nothing happened. The finding is
    the permission, not the damage.

WHY THE STORED COLUMN DID NOT CATCH IT
======================================

    0027 stored `origin` and backfilled it with this same function, so the two never
    disagreed - 242 accounts, zero differences, measured before 0053. A derived value
    and a stored value that always agree look like two sources confirming each other.
    They were one claim, written down twice.

THE TESTS BELOW, AND WHICH ONE IS LOAD-BEARING
==============================================

    `test_a_human_row_with_a_fixture_shaped_address_stays_a_human` is the one that would
    have failed before. Everything else here would have passed on the old code too,
    because the old code agreed with the new code on every account except the one nobody
    thought to check.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import account_origin, humans
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


def _cleanup(admin: psycopg.Connection, human_id: uuid.UUID) -> None:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


# ------------------------------------------------------ declared, at the creation point

async def test_create_human_will_not_invent_an_origin():
    """No default, so a caller that has not thought about it cannot be silent.

    This is the parameter's whole purpose. `create_human` used to call the classifier on
    the caller's behalf, which meant every caller got an answer and none of them had to
    know there was a question.
    """
    with pytest.raises(TypeError, match="origin"):
        async with connection() as conn:
            await humans.create_human(  # type: ignore[call-arg]
                conn, display_name="No Origin", email="no-origin@declared.invalid"
            )


async def test_an_origin_outside_the_three_is_refused(admin):
    """A typo is a refusal rather than a row.

    The column's CHECK would catch it too, one layer down. It is caught here as well
    because the message a caller needs - *it says what this account IS* - is not
    something a constraint violation can say.
    """
    with pytest.raises(ValueError, match="origin must be one of"):
        async with connection() as conn:
            await humans.create_human(
                conn, display_name="Typo", email="typo@declared.invalid",
                origin="fixture",  # not `test_fixture`
            )


@pytest.mark.parametrize(
    "declared",
    [account_origin.HUMAN, account_origin.TEST_FIXTURE, account_origin.SERVICE],
)
async def test_what_the_caller_declares_is_what_the_row_holds(admin, declared):
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name=f"Declared {declared}",
            email=f"{uuid.uuid4().hex[:8]}@declared.invalid", origin=declared,
        )
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT origin FROM office_human WHERE human_id = %s", (human_id,)
            )
            assert cur.fetchone()[0] == declared
    finally:
        _cleanup(admin, human_id)


async def test_a_human_row_with_a_fixture_shaped_address_stays_a_human(admin):
    """**LOAD-BEARING, and the inverse of what happened.**

    An address ending `.invalid` used to mean fixture no matter what anybody intended.
    It means nothing now, and the declaration stands - which is the same rule that stops
    `dev-all@localhost` meaning person.

    If a pattern ever creeps back into `origin_of`, this fails: the name and the address
    here are both exactly the shapes the old classifier matched on.
    """
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="smoke-1a2b3c4d",
            email="smoke-1a2b3c4d@example.invalid", origin=account_origin.HUMAN,
        )
    try:
        async with connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT display_name, email, origin FROM office_human "
                " WHERE human_id = %s", (human_id,)
            )
            row = await cur.fetchone()
        assert account_origin.origin_of(
            {"display_name": row[0], "email": row[1], "origin": row[2]}
        ) == account_origin.HUMAN, (
            "the classifier read the name or the address; entry 151 says it reads "
            "neither"
        )
    finally:
        _cleanup(admin, human_id)


# ---------------------------------------------------------- no default, at the schema

async def test_an_insert_that_omits_origin_fails(admin):
    """0053 dropped `DEFAULT 'human'`, so silence is no longer an answer.

    The tests in this repository insert into `office_human` directly in several places.
    While the default stood, every one of them created a person without saying so - and
    so would any future caller that forgot.
    """
    with pytest.raises(psycopg.errors.NotNullViolation), admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method) "
            "VALUES (%s, 'No Origin Column', 'omitted@declared.invalid', 'sso_mfa')",
            (uuid.uuid4(),),
        )
    admin.rollback()


# ------------------------------------------------------------------ the account itself

async def test_no_dev_all_build_check_account_reads_as_a_person(admin):
    """The one row the ruling names - asserted so that it needs no skip.

    **Stated as "none of these is a person" rather than "this one is a fixture".** The
    account exists on the development database, where the finding was made, and on no
    other; a test written the other way round would either assert a fact about one
    developer's machine or skip. CI refuses a run with any skip at all, deliberately -
    `requires_db` turns a broken service container into a green tick otherwise - so a
    skip here would spend that control to say nothing.

    The invariant is true either way: where the row exists it must be a fixture, and
    where it does not there is nothing to be wrong.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT origin FROM office_human WHERE email = 'dev-all@localhost'"
        )
        rows = cur.fetchall()
    assert [r[0] for r in rows if r[0] != account_origin.TEST_FIXTURE] == [], (
        "`dev-all build check` reads as a person again. It holds no role today, but it "
        "held `ivan` for four days while reading as one, and `assert_named_human` "
        "would not have refused it (entry 151)."
    )


async def test_a_fixture_is_refused_the_acts_a_named_human_may_take(admin):
    """What the reclassification actually buys, stated as the refusal it restores.

    `assert_named_human` is the control from entry 148. It reads `origin` and nothing
    else, so an account the classifier called a person passed it - which is why the
    classification and this refusal are one finding rather than two.
    """
    fixture = humans.Human(
        human_id=uuid.uuid4(), display_name="dev-all build check",
        email="dev-all@localhost", status="active",
        roles=(("ivan", None),), origin=account_origin.TEST_FIXTURE,
    )
    with pytest.raises(Exception) as refused:
        humans.assert_named_human(fixture, act="decide a proposal")
    assert "test_fixture" in str(refused.value)

    # And the same account, declared a person, is not refused - so the test above is
    # about the declaration and not about the name.
    humans.assert_named_human(
        humans.Human(
            human_id=fixture.human_id, display_name=fixture.display_name,
            email=fixture.email, status="active", roles=fixture.roles,
            origin=account_origin.HUMAN,
        ),
        act="decide a proposal",
    )
