"""A role grant or revocation writes an audit event, in the function that does it.

RULED 21 SEPTEMBER 2026 (entry 149)
===================================

    *"A role grant or revocation writes an audit event, in `grant_role` and
    `revoke_role` themselves. Measured: both wrote none, and `revoke_role`'s docstring
    claims the audit log records it."*

WHAT WAS MEASURED
=================

    `grant_role` wrote a row into `office_human_role` with `granted_by` and
    `granted_at`. `revoke_role` stamped `revoked_at` and `revoked_by`. **Neither wrote
    an audit event**, so nothing a ledger verification covers said who changed who may
    act - and `revoke_role`'s own docstring said *"the audit log says who"*.

    Found on 21 September, granting Ira Green `compliance_officer` for Greenstone: the
    event had to be written by hand beside the call, which is the shape that tells you
    the function should have written it.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_a_grant_that_changed_nothing_writes_nothing`. An event saying a role was
    granted when the human already held it is a false entry in a chain whose entire
    value is that it contains none - and it would be the easy way to make every other
    test here pass.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
import pytest_asyncio

from broker import humans
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

GRANTOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


@pytest_asyncio.fixture
async def subject(admin: psycopg.Connection) -> AsyncIterator[uuid.UUID]:
    """One account to grant to and take from. Deleted whichever way the test ends."""
    human_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, token_hash, "
            "                          status, origin, auth_method) "
            "VALUES (%s, %s, %s, %s, 'active', 'human', 'sso_mfa')",
            (human_id, f"Role Subject {human_id.hex[:6]}",
             f"{human_id.hex}@roles.invalid", f"role-token-{human_id.hex}"),
        )
    admin.commit()
    yield human_id
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (human_id,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


def _events(admin: psycopg.Connection, human_id: uuid.UUID) -> list[tuple[str, str]]:
    with admin.cursor() as cur:
        cur.execute(
            "SELECT event_type, subject->>'role' FROM audit_log "
            " WHERE subject->>'human_id' = %s ORDER BY audit_id",
            (str(human_id),),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


async def test_a_grant_is_audited(subject, admin):
    async with connection() as conn:
        await humans.grant_role(
            conn, human_id=subject, role="venture_operator",
            venture_id="greenstone", granted_by=GRANTOR,
        )
    assert _events(admin, subject) == [("human_role_granted", "venture_operator")]


async def test_a_revocation_is_audited(subject, admin):
    async with connection() as conn:
        await humans.grant_role(
            conn, human_id=subject, role="venture_operator",
            venture_id="greenstone", granted_by=GRANTOR,
        )
        await humans.revoke_role(
            conn, human_id=subject, role="venture_operator",
            venture_id="greenstone", revoked_by=GRANTOR,
        )
    assert _events(admin, subject) == [
        ("human_role_granted", "venture_operator"),
        ("human_role_revoked", "venture_operator"),
    ]


async def test_a_grant_that_changed_nothing_writes_nothing(subject, admin):
    """**Load-bearing.** `ON CONFLICT DO NOTHING` makes a re-grant a no-op, and an event
    claiming a grant that did not happen is a false entry in a hash-chained log."""
    async with connection() as conn:
        for _ in range(3):
            await humans.grant_role(
                conn, human_id=subject, role="venture_operator",
                venture_id="greenstone", granted_by=GRANTOR,
            )
    assert _events(admin, subject) == [("human_role_granted", "venture_operator")]


async def test_a_revocation_of_a_role_nobody_held_writes_nothing(subject, admin):
    async with connection() as conn:
        removed = await humans.revoke_role(
            conn, human_id=subject, role="compliance_officer",
            venture_id="greenstone", revoked_by=GRANTOR,
        )
    assert removed is False
    assert _events(admin, subject) == []


async def test_an_unscoped_grant_says_every_venture(subject, admin):
    """`venture_id` NULL means EVERY venture, and an absent key would read as "this one,
    unspecified" - so it is spelled."""
    async with connection() as conn:
        await humans.grant_role(
            conn, human_id=subject, role="ivan", venture_id=None, granted_by=GRANTOR,
        )
    with admin.cursor() as cur:
        cur.execute(
            "SELECT subject->>'venture_id' FROM audit_log "
            " WHERE subject->>'human_id' = %s ORDER BY audit_id DESC LIMIT 1",
            (str(subject),),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == "*"


def test_the_functions_write_it_themselves():
    """Asserted on the source, because 'in `grant_role` and `revoke_role` themselves' is
    the ruling.

    An event a caller remembers to write is an event the next caller forgets - which is
    how Ira Green's grant came to need one written by hand beside it.
    """
    from pathlib import Path

    from broker import humans as humans_module

    source = Path(humans_module.__file__).read_text(encoding="utf-8")
    for name, event in (
        ("async def grant_role(", "human_role_granted"),
        ("async def revoke_role(", "human_role_revoked"),
    ):
        body = source[source.index(name):]
        body = body[: body.index("\nasync def ", 1)]
        assert f'"{event}"' in body, f"{name} does not write {event}"
