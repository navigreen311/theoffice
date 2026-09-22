"""Creating an account writes an audit event, and the account says what is enforced.

RULED 21 SEPTEMBER 2026 (decisions entries 153 and 154)
=======================================================

    153: *"Creating an account writes an audit event. Measured: `dev-all build check`
    has no creation record, only its revocation."*

    154: *"An account's `auth_method` says what is enforced. Measured: Ira reads
    `sso_mfa` with `mfa_enrolled_at` NULL, and nothing reads the column."*

WHY THE TWO ARE IN ONE FILE
===========================

    They are the same moment. `origin` says what an account IS, `auth_method` says what
    is enforced for it, and both are chosen exactly once - when it is created. The event
    entry 153 requires is the only record that ever carries either at the point somebody
    decided them.

WHAT WAS THERE BEFORE
=====================

    Two events, written by two callers, covering two of the three paths.
    `console_human_created` from the route and `bootstrap_human_created` from the CLI -
    and nothing at all from anywhere else, which is why the chain holds one row about
    `dev-all build check` and it is the revocation of a role it had held for four days.

    That is the shape entry 149 already ruled against for `grant_role`: an event a
    caller remembers to write is an event the next caller forgets.
"""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest

from broker import account_origin, humans
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


def _events(admin: psycopg.Connection, human_id: uuid.UUID) -> list[dict]:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT event_type, actor_type, actor_id, subject, prev_hash, entry_hash "
            "  FROM audit_log "
            " WHERE event_type = 'human_account_created' "
            "   AND subject->>'human_id' = %s ORDER BY audit_id",
            (str(human_id),),
        )
        return [
            {"event_type": r[0], "actor_type": r[1], "actor_id": r[2],
             "subject": r[3] if isinstance(r[3], dict) else json.loads(r[3]),
             "prev_hash": r[4], "entry_hash": r[5]}
            for r in cur.fetchall()
        ]


def _cleanup(admin: psycopg.Connection, human_id: uuid.UUID) -> None:
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


# ------------------------------------------------------ the event, from the function

async def test_creating_an_account_writes_one_event(admin):
    """**The ruling.** Written by `create_human`, so no caller can omit it."""
    creator = uuid.uuid4()
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="Recorded Account",
            email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
            origin=account_origin.TEST_FIXTURE, created_by=creator,
        )
    try:
        events = _events(admin, human_id)
        assert len(events) == 1, f"expected exactly one creation event, got {events}"
        event = events[0]
        assert event["actor_type"] == "human"
        assert event["actor_id"] == creator, "the event does not name who created it"
        assert event["subject"]["display_name"] == "Recorded Account"
        assert event["subject"]["self_created"] is False
    finally:
        _cleanup(admin, human_id)


async def test_the_event_carries_both_declarations(admin):
    """`origin` and `auth_method` - what it is, and what is enforced for it.

    Both are decided once and only here, and a reader asking "how did an account with
    founder authority and no second factor come to exist" needs both on the same row.
    """
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="Both Declarations",
            email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
            origin=account_origin.TEST_FIXTURE, created_by=uuid.uuid4(),
        )
    try:
        subject = _events(admin, human_id)[0]["subject"]
        assert subject["origin"] == account_origin.TEST_FIXTURE
        assert subject["auth_method"] == "bearer_token"
    finally:
        _cleanup(admin, human_id)


async def test_the_token_is_never_in_the_event(admin):
    """**Load-bearing.** A credential in a hash-chained record cannot be redacted.

    The chain is append-only by trigger and readable by anyone who can read the Access
    page. A token that reached it would be unremovable by construction, which is the one
    property that makes this worse than an ordinary logging mistake.
    """
    async with connection() as conn:
        human_id, plaintext = await humans.create_human(
            conn, display_name="No Token Here",
            email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
            origin=account_origin.TEST_FIXTURE, created_by=uuid.uuid4(),
        )
    try:
        body = json.dumps(_events(admin, human_id)[0]["subject"])
        assert plaintext not in body
        assert humans.hash_token(plaintext) not in body
    finally:
        _cleanup(admin, human_id)


async def test_the_bootstrap_account_records_that_it_created_itself(admin):
    """The one documented exception, visible as one rather than as a gap.

    The first human has nobody above them. `grant_role`'s self-grant is the same shape
    and is recorded the same way - `assert_may_grant` forbids granting to yourself
    everywhere else, and this row is the exception that makes the rule enforceable.
    """
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="First Operator",
            email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
            origin=account_origin.TEST_FIXTURE,  # created_by deliberately omitted
        )
    try:
        event = _events(admin, human_id)[0]
        assert event["actor_id"] == human_id, "a self-created account names itself"
        assert event["subject"]["self_created"] is True
    finally:
        _cleanup(admin, human_id)


async def test_two_creations_are_linked_to_each_other(admin):
    """Not a log line beside the chain - a link in it.

    Entry 149's finding about `grant_role` was exactly this distinction: `granted_by`
    and `granted_at` on the row are a record, and they are not the record a ledger
    verification covers.

    **Two accounts, because one proves nothing.** A single entry's `prev_hash` is the
    genesis value on a freshly torn-down database, so asserting that it names some
    existing row passes or fails on how much else the suite happened to write first.
    The second creation's `prev_hash` IS the first's `entry_hash`, and that is the
    chain property itself rather than a symptom of it.
    """
    made: list[uuid.UUID] = []
    async with connection() as conn:
        for name in ("Chained One", "Chained Two"):
            human_id, _ = await humans.create_human(
                conn, display_name=name,
                email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
                origin=account_origin.TEST_FIXTURE, created_by=uuid.uuid4(),
            )
            made.append(human_id)
    try:
        first, second = (_events(admin, h)[0] for h in made)
        assert first["entry_hash"] and second["entry_hash"]
        assert second["prev_hash"] == first["entry_hash"], (
            "the second creation does not link to the first; these entries are beside "
            "the chain rather than in it"
        )
    finally:
        for human_id in made:
            _cleanup(admin, human_id)


# --------------------------------------------------------- what is actually enforced

async def test_a_new_account_claims_only_what_it_has(admin):
    """`create_human`'s default was `sso_mfa`, inherited by 242 accounts, verified by
    nothing. It is `bearer_token` now: a token The Office issued and hashed."""
    async with connection() as conn:
        human_id, _ = await humans.create_human(
            conn, display_name="Honest Default",
            email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
            origin=account_origin.TEST_FIXTURE, created_by=uuid.uuid4(),
        )
    try:
        with admin.cursor() as cur:
            cur.execute(
                "SELECT auth_method, mfa_enrolled_at FROM office_human "
                " WHERE human_id = %s", (human_id,)
            )
            assert cur.fetchone() == ("bearer_token", None)
    finally:
        _cleanup(admin, human_id)


async def test_an_authenticated_human_carries_what_is_enforced(admin):
    """**The gap entry 148 found, closed before anything needs it.**

    `Human` did not carry `origin`, so every route taking `me` from a token was
    structurally unable to ask whether the caller was a fixture. `auth_method` had the
    same shape: a route could not have asked what a signer's credential actually is,
    even if it wanted to. It can now. Nothing refuses on it yet, and entry 154 says why.
    """
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Carries It",
            email=f"{uuid.uuid4().hex[:8]}@recorded.invalid",
            origin=account_origin.TEST_FIXTURE, created_by=uuid.uuid4(),
        )
        me = await humans.authenticate(conn, token)
        fetched = await humans.get_human(conn, human_id)
    try:
        assert me is not None and me.auth_method == "bearer_token"
        assert me.origin == account_origin.TEST_FIXTURE
        # `get_human` selected NEITHER column and let both default, so a fixture read
        # back through it arrived as a person. Fixed alongside entry 154.
        assert fetched is not None
        assert fetched.auth_method == "bearer_token"
        assert fetched.origin == account_origin.TEST_FIXTURE
    finally:
        _cleanup(admin, human_id)
