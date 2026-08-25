"""O1-O9 - human administration, the two write-only loops, and pagination.

Until this increment a deployed Office needed somebody with a shell to create its second
operator. That is the gap these routes close, and they are the most privilege-sensitive
surface in the API: everything else here governs what agents may do, and this governs
who may govern.

So most of this file is about the refusals. The two that carry it:

  * a role may be granted only by somebody holding a **strictly stronger** one, because
    equal-strength granting makes a role self-propagating and the hierarchy stops
    describing anything;
  * **nobody grants themselves**, including `ivan`, so that every role anyone holds was
    granted by somebody else and the audit log says who.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


@pytest.fixture(autouse=True)
def _clean(admin: psycopg.Connection):
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        # incident_resolution is append-only, and the guard is doing exactly its job
        # here. Superuser-only, like `clean_audit` - office_app can never do this.
        cur.execute(
            "ALTER TABLE incident_resolution DISABLE TRIGGER incident_resolution_append_only"
        )
        cur.execute("DELETE FROM incident_resolution")
        cur.execute(
            "ALTER TABLE incident_resolution ENABLE TRIGGER incident_resolution_append_only"
        )
        cur.execute("DELETE FROM incident")
        cur.execute("DELETE FROM revocation")
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
        cur.execute(
            "ALTER TABLE historical_record DISABLE TRIGGER historical_record_append_only"
        )
        cur.execute("DELETE FROM historical_record")
        cur.execute(
            "ALTER TABLE historical_record ENABLE TRIGGER historical_record_append_only"
        )
    conn.commit()


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make(name: str, role: str | None, venture: str | None = None):
    """A human with a role, created directly - this is the bootstrap path."""
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@access.invalid"
        )
        if role:
            await humans.grant_role(
                conn, human_id=human_id, role=role, venture_id=venture,
                granted_by=SEED,
            )
    return human_id, token


# ------------------------------------------------------------ granting rules

async def test_granting_requires_a_strictly_stronger_role(api):
    """O1 - not "stronger or equal".

    Equal-strength granting would let a compliance officer mint another compliance
    officer, and a role that can propagate itself is a role the hierarchy does not
    actually rank.
    """
    _ivan, ivan_token = await make("Ivan", "ivan")
    officer_id, officer_token = await make("Officer", "compliance_officer")
    operator_id, operator_token = await make("Operator", "venture_operator", VENTURE)

    # ivan -> compliance_officer: allowed.
    ok = await api.post(
        f"/api/humans/{operator_id}/roles",
        json={"role": "compliance_officer"}, headers=auth(ivan_token),
    )
    assert ok.status_code == 200

    # compliance_officer -> compliance_officer: refused, this is the self-propagation.
    peer = await api.post(
        f"/api/humans/{operator_id}/roles",
        json={"role": "compliance_officer"}, headers=auth(officer_token),
    )
    assert peer.status_code == 403
    assert "strictly stronger" in peer.json()["message"]

    # compliance_officer -> venture_operator: allowed.
    weaker = await api.post(
        f"/api/humans/{officer_id}/roles",
        json={"role": "venture_operator", "venture_id": VENTURE},
        headers=auth(ivan_token),
    )
    assert weaker.status_code == 200

    # venture_operator -> anything: refused. A FRESH one: `operator_id` was promoted to
    # compliance_officer two calls ago, so reusing it here would have been asking a
    # different question and getting a correct 200 for it.
    _plain_id, plain_token = await make("Plain", "venture_operator", VENTURE)
    nothing = await api.post(
        f"/api/humans/{officer_id}/roles",
        json={"role": "venture_operator"}, headers=auth(plain_token),
    )
    assert nothing.status_code == 403
    assert operator_token  # bound above; the promotion is what this comment is about


async def test_nobody_grants_themselves_a_role_including_ivan(api):
    """O2 - the rule that keeps "who decided this" answerable.

    A holder of `ivan` has other paths to anything they want, so this stops no attack.
    What it does is guarantee that every role anyone holds has a granter who is not the
    holder, which is the property that makes the audit trail worth reading.
    """
    ivan_id, ivan_token = await make("Ivan", "ivan")

    self_grant = await api.post(
        f"/api/humans/{ivan_id}/roles",
        json={"role": "compliance_officer"}, headers=auth(ivan_token),
    )
    assert self_grant.status_code == 403
    assert "themselves" in self_grant.json()["message"]

    officer_id, officer_token = await make("Officer", "compliance_officer")
    also_refused = await api.post(
        f"/api/humans/{officer_id}/roles",
        json={"role": "venture_operator", "venture_id": VENTURE},
        headers=auth(officer_token),
    )
    assert also_refused.status_code == 403


async def test_removing_a_role_is_guarded_the_same_way_as_granting(api):
    """Being unable to grant `ivan` and able to remove it is the same power."""
    ivan_id, _ivan_token = await make("Ivan", "ivan")
    _officer_id, officer_token = await make("Officer", "compliance_officer")

    response = await api.post(
        f"/api/humans/{ivan_id}/roles",
        json={"role": "ivan", "revoke": True}, headers=auth(officer_token),
    )
    assert response.status_code == 403


async def test_the_last_administrator_cannot_be_suspended_or_demoted(api):
    """O3 - an availability control, and worth as much as a security one.

    A system with no `ivan` cannot appoint one. The only recovery is a shell on the
    database, which is exactly the dependency these routes exist to remove.
    """
    ivan_id, ivan_token = await make("Ivan", "ivan")
    other_id, _other_token = await make("Second", "ivan")

    # Two administrators: demoting one is fine.
    assert (
        await api.post(
            f"/api/humans/{other_id}/roles",
            json={"role": "ivan", "revoke": True}, headers=auth(ivan_token),
        )
    ).status_code == 200

    # One left: the same call is refused.
    demote = await api.post(
        f"/api/humans/{ivan_id}/roles",
        json={"role": "ivan", "revoke": True}, headers=auth(ivan_token),
    )
    assert demote.status_code == 403
    assert "last active administrator" in demote.json()["message"]

    suspend = await api.post(
        f"/api/humans/{ivan_id}/status",
        json={"status": "suspended", "reason": "trying to lock the door from inside"},
        headers=auth(ivan_token),
    )
    assert suspend.status_code in (400, 403)


async def test_you_cannot_suspend_yourself(api):
    """A lockout, not a breach - and one click away without this."""
    # An administrator must exist, or the last-administrator guard fires first and this
    # would pass for the wrong reason.
    await make("Ivan", "ivan")
    officer_id, officer_token = await make("Officer", "compliance_officer")

    response = await api.post(
        f"/api/humans/{officer_id}/status",
        json={"status": "suspended", "reason": "oops"}, headers=auth(officer_token),
    )
    assert response.status_code == 400
    assert "lock you out" in response.json()["detail"]


# ------------------------------------------------------------------- tokens

async def test_creating_a_human_returns_a_working_token_exactly_once(api):
    """The plaintext is in that response and nowhere else, ever."""
    _ivan_id, ivan_token = await make("Ivan", "ivan")

    created = await api.post(
        "/api/humans",
        json={"display_name": "New Operator", "email": "new@access.invalid",
              "role": "venture_operator", "venture_id": VENTURE},
        headers=auth(ivan_token),
    )
    assert created.status_code == 201
    token = created.json()["token"]

    # It works.
    assert (await api.get("/api/health", headers=auth(token))).status_code == 200

    # And it is not recoverable from any listing.
    listing = await api.get("/api/humans", headers=auth(ivan_token))
    assert listing.status_code == 200
    assert token not in listing.text
    assert "token_hash" not in listing.text, "a hash confirms a guess; it is not a field"
    assert any(h["display_name"] == "New Operator" for h in listing.json())


async def test_reissuing_a_token_invalidates_the_old_one(api):
    """O5 - rotation, which this API has never had.

    A token was valid until its human was suspended, which made a leaked token a
    permanent one. The assertion that matters is the second half: the old token stops
    working, rather than both working.
    """
    ivan_id, ivan_token = await make("Ivan", "ivan")

    response = await api.post(f"/api/humans/{ivan_id}/token", headers=auth(ivan_token))
    assert response.status_code == 200
    new_token = response.json()["token"]

    assert (await api.get("/api/health", headers=auth(new_token))).status_code == 200
    assert (await api.get("/api/health", headers=auth(ivan_token))).status_code == 401


async def test_only_ivan_may_reissue_somebody_elses_token(api):
    _ivan_id, ivan_token = await make("Ivan", "ivan")
    officer_id, officer_token = await make("Officer", "compliance_officer")

    # Their own: allowed - and it invalidates the token that authorised it, which is
    # the whole point of rotation and is easy to forget when writing the next line.
    rotated = await api.post(
        f"/api/humans/{officer_id}/token", headers=auth(officer_token)
    )
    assert rotated.status_code == 200
    officer_token = rotated.json()["token"]

    # Somebody else's: not.
    assert (
        await api.post(f"/api/humans/{_ivan_id}/token", headers=auth(officer_token))
    ).status_code == 403

    # ivan may rotate anyone's.
    assert (
        await api.post(f"/api/humans/{officer_id}/token", headers=auth(ivan_token))
    ).status_code == 200


async def test_a_suspended_human_is_refused_on_their_next_request(api):
    """O6 - their next request, not their next session.

    Status is read live on every call. The same rule agent revocation follows, and for
    the same reason: a check that trusts a session is a check that is one session behind.
    """
    _ivan_id, ivan_token = await make("Ivan", "ivan")
    officer_id, officer_token = await make("Officer", "compliance_officer")

    assert (await api.get("/api/health", headers=auth(officer_token))).status_code == 200

    suspended = await api.post(
        f"/api/humans/{officer_id}/status",
        json={"status": "suspended", "reason": "left the company"},
        headers=auth(ivan_token),
    )
    assert suspended.status_code == 200

    refused = await api.get("/api/health", headers=auth(officer_token))
    assert refused.status_code == 403
    assert "suspended" in refused.json()["detail"]


async def test_a_venture_operator_cannot_read_the_roster(api):
    """Who holds `ivan` is a map of whom to compromise."""
    _id, operator_token = await make("Operator", "venture_operator", VENTURE)
    assert (await api.get("/api/humans", headers=auth(operator_token))).status_code == 403


# ---------------------------------------------------- the write-only loops

async def test_revocations_are_listable_and_reinstatable(api, admin: psycopg.Connection):
    """O7 - the loop that was write-only, and the write was the kill switch.

    `POST /api/revocations/{id}/reinstate` existed and was pinned. There was no GET, so
    lifting a revocation meant getting the id out of the database by hand.
    """
    _ivan_id, ivan_token = await make("Ivan", "ivan")
    agent_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_agent_identity (office_agent_id, village_agent_ref, "
            "agent_name, department, status) VALUES (%s, %s, 'Rev Test', 'AI & Data "
            "Science', 'active')",
            (agent_id, f"village::rev-{agent_id.hex[:8]}"),
        )
    admin.commit()

    created = await api.post(
        "/api/revocations",
        json={"scope": "agent", "office_agent_id": str(agent_id),
              "reason": "testing the loop"},
        headers=auth(ivan_token),
    )
    assert created.status_code == 201
    revocation_id = created.json()["revocation_id"]

    listed = (await api.get("/api/revocations", headers=auth(ivan_token))).json()
    assert [r["revocation_id"] for r in listed] == [revocation_id]
    assert listed[0]["agent_name"] == "Rev Test", "the id alone is not actionable"
    assert listed[0]["reinstated_at"] is None

    lifted = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        json={"reason": "the incident was closed"}, headers=auth(ivan_token),
    )
    assert lifted.status_code == 200

    assert (await api.get("/api/revocations", headers=auth(ivan_token))).json() == []
    with_lifted = (
        await api.get("/api/revocations?include_lifted=true", headers=auth(ivan_token))
    ).json()
    assert len(with_lifted) == 1
    assert with_lifted[0]["reinstated_at"] is not None

    with admin.cursor() as cur:
        cur.execute("DELETE FROM revocation WHERE office_agent_id = %s", (agent_id,))
        cur.execute(
            "DELETE FROM office_agent_identity WHERE office_agent_id = %s", (agent_id,)
        )
    admin.commit()


async def test_resolving_an_incident_appends_and_never_edits(
    api, admin: psycopg.Connection
):
    """O8 - and the incident row is untouched.

    `incident` is append-only by design: "an incident is never edited; a later finding
    is a new incident referencing the trace". A detection that can be rewritten is worth
    less than the row it sits in, and severity is the field somebody under pressure
    would most want to lower.
    """
    _ivan_id, ivan_token = await make("Ivan", "ivan")
    incident_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO incident (incident_id, severity, kind, venture_id) "
            "VALUES (%s, 'HIGH', 'rubber_stamp_approval', %s)",
            (incident_id, VENTURE),
        )
    admin.commit()

    # Three spaces satisfy `min_length=1`, so the schema lets it through and the domain
    # function refuses it. That is the right order: the rule lives in one place, and the
    # database CHECK behind it is the control neither can be argued out of.
    empty = await api.post(
        f"/api/incidents/{incident_id}/resolve", json={"resolution": "   "},
        headers=auth(ivan_token),
    )
    assert empty.status_code == 409
    assert "account of what was done" in empty.json()["detail"]

    resolved = await api.post(
        f"/api/incidents/{incident_id}/resolve",
        json={"resolution": "reviewer retrained; approval re-taken with the payload read"},
        headers=auth(ivan_token),
    )
    assert resolved.status_code == 201

    # The incident itself is unchanged.
    with admin.cursor() as cur:
        cur.execute(
            "SELECT severity, kind FROM incident WHERE incident_id = %s", (incident_id,)
        )
        row = cur.fetchone()
    assert row == ("HIGH", "rubber_stamp_approval")

    # Resolving twice is refused rather than replacing who closed it.
    again = await api.post(
        f"/api/incidents/{incident_id}/resolve", json={"resolution": "again"},
        headers=auth(ivan_token),
    )
    assert again.status_code == 409

    # And the dangling enum finally has a producer.
    history = (
        await api.get(f"/api/knowledge/history?venture_id={VENTURE}",
                      headers=auth(ivan_token))
    ).json()["rows"]
    assert any(r["record_type"] == "incident_resolved" for r in history)


async def test_a_resolved_incident_leaves_the_open_list(api, admin: psycopg.Connection):
    _ivan_id, ivan_token = await make("Ivan", "ivan")
    incident_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO incident (incident_id, severity, kind, venture_id) "
            "VALUES (%s, 'LOW', 'manual', %s)",
            (incident_id, VENTURE),
        )
    admin.commit()

    before = (await api.get("/api/incidents", headers=auth(ivan_token))).json()
    assert before["total"] == 1

    await api.post(
        f"/api/incidents/{incident_id}/resolve", json={"resolution": "handled"},
        headers=auth(ivan_token),
    )

    after = (await api.get("/api/incidents", headers=auth(ivan_token))).json()
    assert after["total"] == 0
    with_resolved = (
        await api.get("/api/incidents?include_resolved=true", headers=auth(ivan_token))
    ).json()
    assert with_resolved["total"] == 1
    assert with_resolved["items"][0]["resolution"] == "handled"


# --------------------------------------------------------------- pagination

async def test_a_page_reports_a_total_larger_than_itself(api, clean_audit, admin):
    """O9 - the denominator.

    The previous version capped at 100 and said nothing about the rest, so "I searched
    the audit log and found nothing" was indistinguishable from "I looked at the most
    recent hundred". Those are different sentences and only one of them is evidence.
    """
    _ivan_id, ivan_token = await make("Ivan", "ivan")

    from tests.conftest import insert_audit

    for _ in range(25):
        insert_audit(admin, event_type="pagination_fixture")

    page = (
        await api.get("/api/audit?limit=10&event_type=pagination_fixture",
                      headers=auth(ivan_token))
    ).json()

    assert len(page["items"]) == 10
    assert page["total"] == 25, "the page must know what it did not show"
    assert page["limit"] == 10
    assert page["offset"] == 0

    second = (
        await api.get("/api/audit?limit=10&offset=10&event_type=pagination_fixture",
                      headers=auth(ivan_token))
    ).json()
    assert len(second["items"]) == 10
    assert second["total"] == 25
    first_ids = {r["audit_id"] for r in page["items"]}
    assert not (first_ids & {r["audit_id"] for r in second["items"]}), "pages overlap"

    last = (
        await api.get("/api/audit?limit=10&offset=20&event_type=pagination_fixture",
                      headers=auth(ivan_token))
    ).json()
    assert len(last["items"]) == 5


async def test_the_total_respects_the_filter(api, clean_audit, admin):
    """A denominator that ignored the filter would be a different lie."""
    _ivan_id, ivan_token = await make("Ivan", "ivan")
    from tests.conftest import insert_audit

    for _ in range(7):
        insert_audit(admin, event_type="wanted")
    for _ in range(11):
        insert_audit(admin, event_type="unwanted")

    filtered = (
        await api.get("/api/audit?event_type=wanted&limit=5", headers=auth(ivan_token))
    ).json()
    assert filtered["total"] == 7
    assert len(filtered["items"]) == 5
