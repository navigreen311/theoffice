"""Renaming an account is an act with consequences, so it is audited - entry 103.

A display name is a key in practice. Two Packs name their reviewers by display name, and
two joins read those names against `office_human.display_name`: the access overview's
missing-people list, and the approvals page attaching a reviewer's decisions. **Nothing
could change one except hand-run SQL, which writes no audit event and leaves the
hash-chained log with no record that it happened.**

These pin the four properties: only `ivan` may rename, the event carries both names, a
name another account holds is refused, and the frozen history is left alone.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import account_origin, humans
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _clean(admin: psycopg.Connection):
    def wipe() -> None:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM office_human_role")
            cur.execute("DELETE FROM office_human")
        admin.commit()

    wipe()
    yield
    wipe()


async def make(name: str, role: str, email: str) -> tuple[uuid.UUID, str]:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, origin=account_origin.HUMAN, display_name=name, email=email
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, granted_by=human_id
        )
        return human_id, token


async def test_a_rename_names_both_names_and_who_did_it(api, admin):
    """The whole point. An event saying only what a name became cannot answer
    "who was Ivan in September"."""
    actor_id, token = await make("Ivan", "ivan", "ivan@office.example.com")

    response = await api.post(
        f"/api/humans/{actor_id}/name",
        json={"display_name": "Ivan Green"},
        headers=auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["from"] == "Ivan"
    assert response.json()["to"] == "Ivan Green"

    with admin.cursor() as cur:
        cur.execute("SELECT display_name FROM office_human WHERE human_id = %s", (actor_id,))
        assert cur.fetchone()[0] == "Ivan Green"

        cur.execute(
            "SELECT actor_id, subject FROM audit_log "
            "WHERE event_type = 'console_human_renamed' ORDER BY ts DESC LIMIT 1"
        )
        row = cur.fetchone()

    assert row is not None, "a rename with no audit event is the state this replaces"
    actor, subject = row
    assert actor == actor_id, "the event names who did it"
    assert subject["from"] == "Ivan"
    assert subject["to"] == "Ivan Green"


async def test_only_ivan_may_rename_anybody_including_themselves(api):
    """Scoped tighter than token reissue, and for a reason.

    Rotating your own token affects only you. Your display name is what a Pack calls its
    reviewer, so renaming yourself moves what somebody else's Pack resolves to.
    """
    _officer_id, officer_token = await make(
        "Officer", "compliance_officer", "officer@office.example.com"
    )
    operator_id, operator_token = await make(
        "Operator", "venture_operator", "operator@office.example.com"
    )

    mine = await api.post(
        f"/api/humans/{operator_id}/name",
        json={"display_name": "Operator Renamed"},
        headers=auth(operator_token),
    )
    assert mine.status_code == 403, "not even your own, without `ivan`"

    theirs = await api.post(
        f"/api/humans/{operator_id}/name",
        json={"display_name": "Operator Renamed"},
        headers=auth(officer_token),
    )
    assert theirs.status_code == 403


async def test_a_name_another_account_holds_is_refused(api):
    """Refused by the function, with the holder named - and by the index underneath it.

    Two accounts with one name are two accounts the Packs' name matching cannot tell
    apart, which turns a cosmetic collision into a wrong answer about who signed.
    """
    actor_id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    await make("Ira Green", "venture_operator", "ira@office.example.com")

    response = await api.post(
        f"/api/humans/{actor_id}/name",
        json={"display_name": "ira green"},
        headers=auth(token),
    )
    assert response.status_code == 403, response.text
    assert "already another account's display name" in response.text, response.text
    assert "Ira Green" in response.text, "name the holder"


async def test_the_index_refuses_a_duplicate_even_if_the_function_is_bypassed(admin):
    """The constraint is the control; the function's check is the better message.

    Case-insensitive, because that is how `access_overview` compares: a plain unique
    index would admit `Ivan` and `ivan` as two accounts those joins cannot tell apart.
    """
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin) "
            "VALUES (%s, 'Ivan Green', 'a@office.example.com', 'bearer_token', 'human')",
            (uuid.uuid4(),),
        )
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO office_human (human_id, display_name, email, auth_method, "
                "                          origin) "
                "VALUES (%s, '  ivan green ', 'b@office.example.com', 'bearer_token', 'human')",
                (uuid.uuid4(),),
            )
    admin.rollback()


async def test_a_rename_does_not_rewrite_what_was_already_attested(api, admin):
    """The history keeps the old spelling, deliberately.

    `provisioning_gate_result.reason` holds "reviewed by <name>: ..." frozen at signing,
    and `audit_log` carries names inside `subject`. An attestation records what was true
    when it was made; editing it would change what somebody attested to.

    Asserted against the audit log rather than a fabricated gate result: a run needs a
    published Pack behind it, and standing one up would test the fixture. The log is the
    stronger case anyway - it is hash-chained, so a rename that rewrote it would break
    the chain rather than merely lose a fact.
    """
    from broker import audit

    actor_id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    async with connection() as conn:
        await audit.write_event(
            event_type="console_human_created",
            actor_type="human", actor_id=actor_id, venture_id=None,
            subject={"note": "created by Ivan", "display_name": "Ivan"},
            conn=conn,
        )

    await api.post(
        f"/api/humans/{actor_id}/name",
        json={"display_name": "Ivan Green"},
        headers=auth(token),
    )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT subject FROM audit_log WHERE event_type = 'console_human_created' "
            "ORDER BY ts DESC LIMIT 1"
        )
        subject = cur.fetchone()[0]
        cur.execute("SELECT * FROM audit_log_verify_chain()")
        verified, _count, _first_bad, _broken, note = cur.fetchone()

    assert subject["display_name"] == "Ivan", "the old name stands in what was recorded"
    assert verified, f"the hash chain must survive a rename: {note}"
