"""A second factor that is a factor: TOTP, enrolled by the person, verified on use.

RULED 21 SEPTEMBER 2026 (decisions entry 155)
=============================================

    *"MFA means a TOTP second factor the person enrols themselves. `attest`, `sign_off`
    and `revoke` refuse without a verified code. Only the person writes their own
    enrolment. Measured: 242 of 242 accounts claimed `sso_mfa`, zero enrolments."*

WHAT ENTRY 154 LEFT OPEN, AND THIS ANSWERS
==========================================

    154 stopped the column lying and wrote the question rather than inventing one:
    *what would "MFA enrolled" mean for an account whose only credential is a bearer
    token The Office issued?* Ivan's answer is above, and it is the one answer that makes
    the enrolment mean something: a secret the platform cannot derive from the token,
    held by the person, proved by a code only they can produce right now.

    Without that, `mfa_enrolled_at` could only ever have been a timestamp somebody wrote.

WHY THE ALGORITHM IS HERE AND NOT A DEPENDENCY
==============================================

    TOTP is RFC 6238: HMAC-SHA1 over a counter derived from the clock, truncated to six
    digits. Every primitive it needs - `hmac`, `hashlib`, `struct`, `base64` - is in the
    standard library, and the whole of it is forty lines.

    **The reason it is safe to write here is that the RFC publishes test vectors.** The
    implementation is checked against the specification rather than against itself, which
    is the property that makes a hand-written crypto composition defensible and the
    absence of which makes one reckless. `tests/contract/test_a_second_factor.py` runs
    all six of the RFC's SHA-1 vectors.

    This is not a general-purpose TOTP library and should not become one. It does what
    this system needs: enrol, confirm, verify.

THE THREE PROPERTIES THAT MATTER, AND WHERE EACH LIVES
======================================================

    the person holds it     `begin_enrolment` returns the secret ONCE. The Office stores
                            it because verification needs it, and nothing ever returns
                            it again - the same rule the bearer token follows.

    the person proves it    `confirm_enrolment` takes a code and refuses a wrong one.
                            An enrolment that did not verify is a secret nobody has
                            demonstrated they can use, which is the state this replaces.

    only the person         Every function here takes `me` and writes `me.human_id`.
                            There is NO parameter for whose enrolment it is, so there is
                            no shape in which an administrator enrols somebody else -
                            and a test asserts the module's surface still contains none.

REPLAY, AND WHY ONE USED CODE IS REFUSED FOR ITS WHOLE STEP
===========================================================

    A code is valid for a 30-second step and TOTP has no state, so the same six digits
    authorise every act inside that window. For `attest` and `sign_off` that is exactly
    the non-repudiation problem the second factor exists to solve: two signatures with
    one code are one act, and the second one nobody typed a code for.

    So a code that has been accepted is recorded and refused afterwards. The record is
    the `(human, step)` pair, not the code - storing codes would be storing credentials.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from typing import Any

from psycopg import AsyncConnection

from broker import audit, humans
from broker.errors import NotAuthorized, OfficeError

#: RFC 6238's defaults, and the ones every authenticator app assumes. Named rather than
#: inlined so a reader can see that nothing here is a local invention.
DIGITS = 6
STEP_SECONDS = 30

#: How far either side of now a code is accepted. One step, which covers the clock skew
#: between a phone and a server and the few seconds between reading and typing.
#:
#: **Not more.** Each extra step widens the window in which a shoulder-surfed or
#: intercepted code still works, and the cost of a narrow window is a retry.
SKEW_STEPS = 1


class NotEnrolledError(OfficeError):
    """This account has no second factor, so there is nothing to verify."""

    audit_event = "mfa_not_enrolled"
    status_code = 403


class BadCode(NotAuthorized):
    """The code did not verify, or has already been used for this step."""

    audit_event = "mfa_code_refused"


def new_secret() -> str:
    """A fresh base32 secret, the format every authenticator app reads.

    160 bits, which is RFC 4226's recommendation for HMAC-SHA1. `secrets` rather than
    `random`, for the reason that module exists.
    """
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def code_at(secret: str, when: float, *, digits: int = DIGITS,
            step: int = STEP_SECONDS, digest: str = "sha1") -> str:
    """The TOTP code for `secret` at unix time `when`. RFC 6238 section 4.

    `digits` and `digest` are parameters ONLY so the RFC's test vectors can be run
    against this function - they use 8 digits and all three SHA families. Nothing in
    this system calls it with anything but the defaults.
    """
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    counter = struct.pack(">Q", int(when // step))
    mac = hmac.new(key, counter, getattr(hashlib, digest)).digest()
    # Dynamic truncation, RFC 4226 section 5.3: the low nibble of the last byte picks
    # where to read four bytes from, and the top bit is masked off so the result is
    # positive on every platform.
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFF_FFFF
    return str(value % (10 ** digits)).zfill(digits)


def verify(secret: str, code: str, *, when: float | None = None) -> int | None:
    """The step the code matched, or None. Constant-time per candidate.

    Returns the STEP rather than a boolean because the caller has to record which step
    was consumed - a boolean would leave replay unenforceable.
    """
    now = time.time() if when is None else when
    supplied = (code or "").strip().replace(" ", "")
    if not supplied.isdigit() or len(supplied) != DIGITS:
        return None
    current = int(now // STEP_SECONDS)
    for offset in range(-SKEW_STEPS, SKEW_STEPS + 1):
        step = current + offset
        expected = code_at(secret, step * STEP_SECONDS)
        # `compare_digest`, not `==`: the comparison is against a secret-derived value
        # and an early return leaks how many digits were right.
        if hmac.compare_digest(expected, supplied):
            return step
    return None


# ------------------------------------------------------------------------ enrolment

async def begin_enrolment(conn: AsyncConnection, *, me: humans.Human) -> str:
    """Generate a secret for THIS person and return it once. Not yet enrolled.

    The secret is stored and `mfa_enrolled_at` is NOT set: an enrolment that has not been
    proved is exactly the claim entry 154 removed, and writing the timestamp here would
    put it straight back.

    **Re-enrolling replaces the secret and clears the enrolment**, because a person who
    has lost their authenticator has lost the factor. The row goes back to unenrolled and
    `attest`, `sign_off` and `revoke` refuse until they prove the new one - which is the
    correct direction for a lost credential.
    """
    humans.assert_named_human(me, act="enrol a second factor")
    secret = new_secret()
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human "
            "   SET mfa_secret = %s, mfa_enrolled_at = NULL, "
            "       auth_method = 'bearer_token' "
            " WHERE human_id = %s",
            (secret, me.human_id),
        )
    await conn.commit()
    await audit.write_event(
        event_type="mfa_enrolment_started",
        actor_type="human", actor_id=me.human_id, venture_id=None,
        # THE SECRET IS NOT IN THE EVENT. The chain is append-only and readable; a
        # shared secret in it would be unremovable by construction.
        subject={"human_id": str(me.human_id), "display_name": me.display_name},
    )
    return secret


async def confirm_enrolment(
    conn: AsyncConnection, *, me: humans.Human, code: str
) -> None:
    """Prove the secret with a code, and only then is the account enrolled.

    This is the step that makes `mfa_enrolled_at` mean something. Before it, the column
    says a secret exists; after it, it says a person demonstrated they can produce codes
    from it.
    """
    humans.assert_named_human(me, act="enrol a second factor")
    secret = await _secret_for(conn, me.human_id)
    if secret is None:
        raise NotEnrolledError(
            "no enrolment is in progress for this account; start one first"
        )
    step = verify(secret, code)
    if step is None:
        raise BadCode(
            "that code did not verify. Check your authenticator's clock, and use the "
            "code showing now rather than one that has rolled over."
        )
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human "
            "   SET mfa_enrolled_at = now(), auth_method = 'mfa_only' "
            " WHERE human_id = %s",
            (me.human_id,),
        )
        await _consume(cur, me.human_id, step)
    await conn.commit()
    await audit.write_event(
        event_type="mfa_enrolled",
        actor_type="human", actor_id=me.human_id, venture_id=None,
        subject={
            "human_id": str(me.human_id),
            "display_name": me.display_name,
            # SELF, always. There is no parameter that could make this somebody else,
            # and the event says so rather than leaving a reader to check the code.
            "enrolled_by": "themselves",
        },
    )


# --------------------------------------------------------------------- the refusal

async def assert_verified(
    conn: AsyncConnection, *, me: humans.Human, code: str | None, act: str
) -> None:
    """Refuse an act whose second factor is missing, wrong, or already spent.

    Called by `attestation.attest`, `humans.sign_off` and the console's revoke route -
    the three acts entry 155 names. Each carries founder or operator authority, and each
    was reachable with a bearer token alone.

    **Not called by `sync_roster`.** A departure revocation has no person at a keyboard
    to type a code, and demanding one there would mean a departed agent keeps live
    authority until somebody notices. That path is `actor_type='system'` and stays so.
    """
    if not me.is_active:
        raise NotAuthorized(f"this account is {me.status}", act=act)
    secret = await _secret_for(conn, me.human_id)
    enrolled = await _enrolled_at(conn, me.human_id)
    if secret is None or enrolled is None:
        raise NotEnrolledError(
            f"{me.display_name} has no enrolled second factor, so {act} is refused. "
            "Enrol one at /access/mfa: this act carries authority a bearer token alone "
            "is not enough for (entry 155).",
            act=act,
        )
    if not code:
        raise BadCode(f"{act} needs a code from your authenticator", act=act)
    step = verify(secret, code)
    if step is None:
        raise BadCode(f"that code did not verify, so {act} is refused", act=act)
    async with conn.cursor() as cur:
        if not await _consume(cur, me.human_id, step):
            await conn.rollback()
            raise BadCode(
                "that code has already been used. A code is good for one act: two "
                "signatures taken with one code are one act, and the second is one "
                "nobody typed a code for.",
                act=act,
            )
    await conn.commit()


# ------------------------------------------------------------------------ internals

async def _secret_for(conn: AsyncConnection, human_id: uuid.UUID) -> str | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT mfa_secret FROM office_human WHERE human_id = %s", (human_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def _enrolled_at(conn: AsyncConnection, human_id: uuid.UUID) -> Any | None:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT mfa_enrolled_at FROM office_human WHERE human_id = %s", (human_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def _consume(cur: Any, human_id: uuid.UUID, step: int) -> bool:
    """Record that this person used this step. False if it was already recorded.

    The PRIMARY KEY does the work, so two concurrent acts cannot both win: one insert
    succeeds and the other conflicts. Checking first and inserting after would be a
    read-modify-write with exactly the race this is here to stop.
    """
    await cur.execute(
        "INSERT INTO mfa_code_used (human_id, step) VALUES (%s, %s) "
        "ON CONFLICT DO NOTHING",
        (human_id, step),
    )
    return bool(cur.rowcount == 1)
