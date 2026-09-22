"""A proposal is decided by somebody who can be held to it.

RULED 21 SEPTEMBER 2026 (entry 148)
===================================

    *"Only a named human may decide a proposal. Smoke fixtures decided four; nothing
    stopped them."*

WHAT WAS MEASURED
=================

    Four `place_call` proposals were decided on 16 September, and they are the only
    proposal decisions this system has ever made:

        smoke-28e7bea5   smoke-25e8ed8f   smoke-a961648a   smoke-3e94169f

    Every one an `origin = 'test_fixture'` account. Every one recorded in `audit_log` as
    `console_proposal_decided` with that name in the subject. The module they rejected is
    one a founder decision forbids, so the outcome was right and the record of who
    decided it is not a record of anybody.

WHY THE ROLE CHECK COULD NOT SEE IT
===================================

    **Because the fixtures hold real roles.** 239 of the 242 accounts on the development
    database are fixtures, and most of them hold `ivan`. Every role check they met, they
    met honestly - what they are not is a person, and `Human` did not carry the column
    that says so.

    `attributable_actor` has asked exactly this question since it was written, of an
    account it goes and FINDS. Nothing asked it of the account that turned up holding a
    token.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_a_named_human_still_decides`. A refusal that fired on everybody would satisfy
    every other assertion here and close the approval queue.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import humans
from broker.errors import NotAuthorized
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


def _human(origin: str, name: str = "Somebody") -> humans.Human:
    return humans.Human(
        human_id=uuid.uuid4(), display_name=name, email=f"{name}@invalid",
        status="active", roles=(("ivan", None),), origin=origin,
    )


def test_a_fixture_may_not_decide():
    with pytest.raises(NotAuthorized) as refused:
        humans.assert_named_human(
            _human("test_fixture", "smoke-28e7bea5"), act="decide a proposal"
        )
    # THE NAME AND THE ACT, both. "not a named human" with no verb sends somebody to
    # read the code to find out what was refused.
    assert "smoke-28e7bea5" in str(refused.value)
    assert "decide a proposal" in str(refused.value)
    assert "test_fixture" in str(refused.value)


def test_a_named_human_still_decides():
    """**Load-bearing.** A refusal that fired on everybody would close the queue."""
    humans.assert_named_human(_human("human", "Ivan Green"), act="decide a proposal")


def test_the_default_is_a_person():
    """A hand-built `Human` in a test is a person unless it says otherwise. The database
    is what decides for a real one, and `authenticate` reads the column."""
    bare = humans.Human(
        human_id=uuid.uuid4(), display_name="Hand Built", email="h@invalid",
        status="active", roles=(),
    )
    assert bare.origin == "human"
    humans.assert_named_human(bare, act="decide a proposal")


async def test_authenticate_reads_the_origin_off_the_row(admin: psycopg.Connection):
    """The column is the fact; `Human.origin` is only its carrier.

    Both directions asserted from one database, because a reader that returned a
    constant would pass the fixture case or the person case but never both.
    """
    from broker.db import connection

    made: list[tuple[uuid.UUID, str]] = []
    for origin, name in (("human", "Origin Person"), ("test_fixture", "origin-fixture")):
        human_id = uuid.uuid4()
        token = f"origin-token-{human_id.hex}"
        with admin.cursor() as cur:
            cur.execute(
                "INSERT INTO office_human (human_id, display_name, email, token_hash, "
                "                          status, origin, auth_method) "
                "VALUES (%s, %s, %s, %s, 'active', %s, 'sso_mfa')",
                (human_id, name, f"{human_id.hex}@origin.invalid",
                 humans.hash_token(token), origin),
            )
        admin.commit()
        made.append((human_id, token))

    try:
        async with connection() as conn:
            person = await humans.authenticate(conn, made[0][1])
            fixture = await humans.authenticate(conn, made[1][1])
        assert person is not None and person.origin == "human"
        assert fixture is not None and fixture.origin == "test_fixture"

        humans.assert_named_human(person, act="decide a proposal")
        with pytest.raises(NotAuthorized):
            humans.assert_named_human(fixture, act="decide a proposal")
    finally:
        with admin.cursor() as cur:
            for human_id, _token in made:
                cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
        admin.commit()


def test_the_route_asks_before_it_decides():
    """Asserted on the source, because the ordering is the control.

    A refusal after `proposals.decide` would leave the decision written and the audit
    entry absent - the worst of both. The check sits with the role check, before
    anything is recorded.
    """
    from pathlib import Path

    from broker import app as app_module

    source = Path(app_module.__file__).read_text(encoding="utf-8")
    route = source[source.index('@app.post("/api/proposals/{proposal_id}/decide")'):]
    route = route[: route.index("\n@app.")]

    guard = route.index("assert_named_human")
    decide = route.index("proposals.decide")
    assert guard < decide, (
        "the named-human check runs after the decision is written. A refusal there "
        "leaves the proposal decided by a fixture and no audit entry saying so."
    )
