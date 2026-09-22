"""A second factor that is a factor: enrolled by the person, verified on use.

RULED 21 SEPTEMBER 2026 (decisions entry 155)
=============================================

    *"MFA means a TOTP second factor the person enrols themselves. `attest`, `sign_off`
    and `revoke` refuse without a verified code. Only the person writes their own
    enrolment. Measured: 242 of 242 accounts claimed `sso_mfa`, zero enrolments."*

THE ONE THAT MAKES THE REST TRUSTWORTHY
=======================================

    `test_the_rfc_6238_vectors` runs the six SHA-1 test vectors published in RFC 6238
    Appendix B. Every other test in this file asserts that our code agrees with our code;
    that one asserts it agrees with the specification, and it is the reason a hand-written
    TOTP is defensible here rather than reckless.

    If it fails, nothing else in this file means anything.
"""

from __future__ import annotations

import base64
import time
import uuid

import pytest

from broker import account_origin, humans, mfa
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


# ------------------------------------------------------------------- the algorithm

#: RFC 6238 Appendix B. The published seed is the ASCII string below; base32 of those
#: twenty bytes is what an authenticator would be given.
#:
#: **Derived rather than pasted**, and not only for tidiness: the base32 blob is 32
#: characters of `[A-Z2-7]` assigned to a name containing SECRET, which is exactly the
#: shape the "No committed secrets" job refuses - and it was right to, because a scanner
#: cannot tell a published test vector from a live credential. Deriving it removes the
#: credential-shaped literal and shows where the value comes from, which the blob did
#: not.
RFC_SEED = b"12345678901234567890"
RFC_SECRET = base64.b32encode(RFC_SEED).decode("ascii")

#: (unix time, expected 8-digit code) for SHA-1, straight out of the table.
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize(("when", "expected"), RFC_VECTORS)
def test_the_rfc_6238_vectors(when, expected):
    """**Load-bearing for this entire file.**

    Checked against the specification rather than against ourselves. A TOTP that agrees
    with its own idea of TOTP would pass every other test here and hand out codes no
    authenticator app produces - which fails closed, but fails for everybody, silently,
    at the moment somebody needs to sign.
    """
    assert mfa.code_at(RFC_SECRET, when, digits=8) == expected


def test_a_code_is_six_digits_and_changes_with_the_step():
    """The base is STEP-ALIGNED, which is the whole content of the second assertion.

    Written first with 1_000_000_000, which sits ten seconds into its step - so "+29"
    crossed into the next one and the test failed against a correct implementation. A
    boundary test whose base is not on the boundary tests the base.
    """
    secret = mfa.new_secret()
    base = 1_000_000_020  # divisible by 30: the first second of a step
    assert base % mfa.STEP_SECONDS == 0
    first = mfa.code_at(secret, base)
    assert len(first) == mfa.DIGITS and first.isdigit()
    # The last second of the same step, then the first of the next.
    assert mfa.code_at(secret, base + mfa.STEP_SECONDS - 1) == first
    assert mfa.code_at(secret, base + mfa.STEP_SECONDS) != first


def test_verify_accepts_one_step_of_skew_and_no_more():
    """A phone's clock and a server's clock are not the same clock.

    One step either side covers that and the seconds between reading and typing. Two
    would double the window in which an intercepted code still works, and the cost of
    the narrow one is a retry.
    """
    secret = mfa.new_secret()
    now = 1_700_000_000
    assert mfa.verify(secret, mfa.code_at(secret, now), when=now) is not None
    assert mfa.verify(secret, mfa.code_at(secret, now - 30), when=now) is not None
    assert mfa.verify(secret, mfa.code_at(secret, now + 30), when=now) is not None
    assert mfa.verify(secret, mfa.code_at(secret, now - 60), when=now) is None
    assert mfa.verify(secret, mfa.code_at(secret, now + 60), when=now) is None


def test_a_malformed_code_is_refused_rather_than_parsed():
    secret = mfa.new_secret()
    for bad in ("", "   ", "abcdef", "12345", "1234567", None):
        assert mfa.verify(secret, bad) is None  # type: ignore[arg-type]


# -------------------------------------------------------------------- the enrolment

async def _person(admin, name: str) -> humans.Human:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name,
            email=f"{uuid.uuid4().hex[:8]}@second-factor.invalid",
            origin=account_origin.HUMAN, created_by=uuid.uuid4(),
        )
        await humans.grant_role(
            conn, human_id=human_id, role="ivan", venture_id=None,
            granted_by=uuid.uuid4(),
        )
        resolved = await humans.authenticate(conn, token)
    assert resolved is not None
    return resolved


def _cleanup(admin, human_id: uuid.UUID) -> None:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM mfa_code_used WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


async def test_beginning_an_enrolment_does_not_enrol(admin):
    """**The distinction entry 154 could not draw and this one rests on.**

    A secret exists. Nobody has shown they can use it. That is not an enrolment, and
    writing the timestamp here would put back exactly the claim these two entries
    removed - 242 accounts asserting a factor none of them had.
    """
    me = await _person(admin, "Begins Only")
    try:
        async with connection() as conn:
            secret = await mfa.begin_enrolment(conn, me=me)
        assert secret
        with admin.cursor() as cur:
            cur.execute(
                "SELECT mfa_secret IS NOT NULL, mfa_enrolled_at, auth_method "
                "  FROM office_human WHERE human_id = %s", (me.human_id,)
            )
            has_secret, enrolled_at, auth_method = cur.fetchone()
        assert has_secret is True
        assert enrolled_at is None, "a secret nobody proved is not an enrolment"
        assert auth_method == "bearer_token"
    finally:
        _cleanup(admin, me.human_id)


async def test_confirming_with_a_real_code_enrols(admin):
    me = await _person(admin, "Confirms")
    try:
        async with connection() as conn:
            secret = await mfa.begin_enrolment(conn, me=me)
            await mfa.confirm_enrolment(
                conn, me=me, code=mfa.code_at(secret, time.time())
            )
        with admin.cursor() as cur:
            cur.execute(
                "SELECT mfa_enrolled_at IS NOT NULL, auth_method "
                "  FROM office_human WHERE human_id = %s", (me.human_id,)
            )
            enrolled, auth_method = cur.fetchone()
        assert enrolled is True
        # `auth_method` follows the enrolment, so 0054's CHECK stays true by
        # construction rather than by somebody remembering to update it.
        assert auth_method == "mfa_only"
    finally:
        _cleanup(admin, me.human_id)


async def test_confirming_with_a_wrong_code_does_not_enrol(admin):
    me = await _person(admin, "Wrong Code")
    try:
        async with connection() as conn:
            secret = await mfa.begin_enrolment(conn, me=me)
            wrong = mfa.code_at(secret, time.time() - 600)
            with pytest.raises(mfa.BadCode):
                await mfa.confirm_enrolment(conn, me=me, code=wrong)
        with admin.cursor() as cur:
            cur.execute(
                "SELECT mfa_enrolled_at FROM office_human WHERE human_id = %s",
                (me.human_id,),
            )
            assert cur.fetchone()[0] is None
    finally:
        _cleanup(admin, me.human_id)


def test_nothing_in_this_module_can_enrol_somebody_else():
    """**"Only the person writes their own enrolment", expressed as a shape.**

    Not a permission check - a permission check can be called with the wrong argument.
    Every function that writes an enrolment takes `me` and writes `me.human_id`, and
    there is no parameter anywhere in this module for whose enrolment it is. An
    administrator cannot enrol a colleague because there is nowhere to put their name.

    This test reads the signatures, so adding such a parameter fails the build.
    """
    import inspect

    for name in ("begin_enrolment", "confirm_enrolment"):
        parameters = set(inspect.signature(getattr(mfa, name)).parameters)
        assert "me" in parameters, f"{name} does not act as the caller"
        for forbidden in ("human_id", "for_human", "target", "on_behalf_of", "human"):
            assert forbidden not in parameters, (
                f"{name} takes {forbidden!r}, which is a way to enrol somebody else"
            )


# --------------------------------------------------------------------- the refusal

async def test_an_unenrolled_account_is_refused(admin):
    me = await _person(admin, "Never Enrolled")
    try:
        async with connection() as conn:
            with pytest.raises(mfa.NotEnrolledError):
                await mfa.assert_verified(
                    conn, me=me, code="123456", act="attesting something"
                )
    finally:
        _cleanup(admin, me.human_id)


async def test_an_enrolled_account_with_no_code_is_refused(admin):
    me = await _person(admin, "No Code Given")
    try:
        async with connection() as conn:
            secret = await mfa.begin_enrolment(conn, me=me)
            await mfa.confirm_enrolment(
                conn, me=me, code=mfa.code_at(secret, time.time())
            )
            with pytest.raises(mfa.BadCode):
                await mfa.assert_verified(
                    conn, me=me, code=None, act="signing something"
                )
    finally:
        _cleanup(admin, me.human_id)


async def test_a_code_authorises_one_act_and_not_two(admin):
    """**Load-bearing.** A code is valid for its whole 30-second step.

    TOTP is stateless, so without this the same six digits authorise every act inside
    that window - and two signatures taken with one code are one act, the second of
    which nobody typed a code for. That is the non-repudiation the factor exists to
    provide, so the step is recorded and refused afterwards.
    """
    me = await _person(admin, "One Act")
    try:
        async with connection() as conn:
            secret = await mfa.begin_enrolment(conn, me=me)
            code = mfa.code_at(secret, time.time())
            await mfa.confirm_enrolment(conn, me=me, code=code)
            # The confirmation itself spent that step, so the very same code cannot then
            # authorise an act - which is the property, demonstrated at its tightest.
            with pytest.raises(mfa.BadCode, match="already been used"):
                await mfa.assert_verified(
                    conn, me=me, code=code, act="signing gate_10"
                )
    finally:
        _cleanup(admin, me.human_id)


async def test_the_code_itself_is_never_stored(admin):
    """A table of live credentials would be worse than the problem it solves.

    The step identifies the window without being usable in it, which is the whole reason
    `mfa_code_used` records a number rather than six digits.
    """
    me = await _person(admin, "Not Stored")
    try:
        async with connection() as conn:
            secret = await mfa.begin_enrolment(conn, me=me)
            code = mfa.code_at(secret, time.time())
            await mfa.confirm_enrolment(conn, me=me, code=code)
        with admin.cursor() as cur:
            cur.execute("SELECT human_id, step, used_at FROM mfa_code_used "
                        " WHERE human_id = %s", (me.human_id,))
            rows = cur.fetchall()
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                " WHERE table_name = 'mfa_code_used'"
            )
            columns = {r[0] for r in cur.fetchall()}
        assert rows, "the step was not recorded, so replay is unenforceable"
        assert columns == {"human_id", "step", "used_at"}
        assert code not in str(rows)
    finally:
        _cleanup(admin, me.human_id)


async def test_a_second_factor_cannot_be_claimed_without_a_secret(admin):
    """0055's CHECK, so an enrolment date can never stand on nothing."""
    import psycopg

    me = await _person(admin, "No Secret")
    try:
        with pytest.raises(
            psycopg.errors.CheckViolation, match="an_enrolment_has_a_secret"
        ), admin.cursor() as cur:
            cur.execute(
                "UPDATE office_human SET mfa_enrolled_at = now() WHERE human_id = %s",
                (me.human_id,),
            )
        admin.rollback()
    finally:
        _cleanup(admin, me.human_id)
