"""Access: test accounts are marked, privilege concentration is surfaced, nothing is deleted."""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import access_overview, account_origin, humans
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000bbbb")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM revocation")
    wipe_venture(conn, VENTURE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture(autouse=True)
def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    yield
    _wipe(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def make(name: str, role: str, email: str | None = None) -> tuple[uuid.UUID, str]:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=email or f"{name.lower()}@office.example.com"
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=None, granted_by=SEED
        )
    return human_id, token


# ------------------------------------------------------------------ origin

def test_a_test_fixture_is_recognised_by_name_or_domain():
    """Derived, not stored, and this is the rule.

    The smoke script creates an account on every run. A column filled by one backfill
    describes the accounts that existed the day it ran; a pattern applied at read time
    recognises the ones created tomorrow.
    """
    for name, email in (
        ("smoke-1a2b3c4d", "smoke-1a2b3c4d@example.invalid"),
        ("ui-90abcdef", "ui-90abcdef@example.invalid"),
        ("Somebody", "somebody@test.invalid"),
    ):
        assert account_origin.origin_of({"display_name": name, "email": email}) == (
            account_origin.TEST_FIXTURE
        ), f"{name} was not recognised as a fixture"

    assert account_origin.origin_of(
        {"display_name": "Ivan", "email": "ivan@example.com"}
    ) == account_origin.HUMAN

    # A service account is the one thing no pattern can tell you, so it is stored.
    assert account_origin.origin_of(
        {"display_name": "nightly-sweep", "email": "ops@example.com", "origin": "service"}
    ) == account_origin.SERVICE


# -------------------------------------------------------- privilege concentration

async def test_test_accounts_holding_the_strongest_role_raise_the_banner(api):
    """The finding this page could not communicate while it was a list.

    95 accounts held `ivan` and one was a person. That is the authority for Forge-scope
    revocation, so each of the other 94 could stop every agent on every Forge.
    """
    _real_id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    await make("smoke-deadbeef", "ivan", "smoke-deadbeef@example.invalid")

    overview = (await api.get("/api/access/overview", headers=auth(token))).json()
    concentration = overview["concentration"]

    assert concentration["role"] == "ivan"
    assert concentration["total"] == 2
    assert concentration["fixtures"] == 1
    assert concentration["people"] == 1
    assert concentration["raised"] is True, (
        "a test account holding the strongest role is a finding at any count"
    )
    # What that role actually authorises, from the authority matrix rather than prose.
    assert "forge" in concentration["authorises"]


async def test_the_banner_stays_down_when_only_people_hold_the_role(api):
    _id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    overview = (await api.get("/api/access/overview", headers=auth(token))).json()
    assert overview["concentration"]["raised"] is False


async def test_the_role_reference_matches_the_authority_matrix(api):
    """The scopes are read from the matrix the API enforces, never retyped.

    A page carrying its own copy of the authority table is a page that eventually
    describes an arrangement that has changed.
    """
    from broker import revocation

    _id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    overview = (await api.get("/api/access/overview", headers=auth(token))).json()

    for row in overview["roles"]:
        expected = [
            scope for scope, required in revocation.SCOPE_MIN_ROLE.items()
            if required == row["role"]
        ]
        assert row["revocation_scopes"] == expected, (
            f"the reference says {row['role']} authorises {row['revocation_scopes']}; "
            f"the matrix says {expected}"
        )
        assert row["meaning"].strip(), f"{row['role']} has no definition"

    assert {row["role"] for row in overview["roles"]} == set(access_overview.ROLE_ORDER)


# ------------------------------------------------------- people the Packs name

async def test_a_person_a_pack_names_with_no_account_is_named(api, admin):
    """Greenstone's Pack names Dana and Gate 10 needs distinct humans.

    Nothing said so. A run that cannot be signed looked exactly like a run nobody had got
    to yet.
    """
    _id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    async with connection() as conn:
        from broker import packs
        from tests.world import PACK_PATH

        # `publish=True` stores it live in one step; the reconciliation reads live
        # Packs only, because a draft naming somebody is a proposal rather than a
        # commitment.
        await packs.store(
            conn, yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="1.0.0", authored_by=_id, publish=True,
        )

    overview = (await api.get("/api/access/overview", headers=auth(token))).json()
    names = {person["human_name"] for person in overview["missing_people"]}
    assert "Dana" in names, "the Pack names Dana and no account exists; nothing said so"

    dana = next(p for p in overview["missing_people"] if p["human_name"] == "Dana")
    # The role she is needed in, not the one she is the understudy for.
    assert dana["role"] == "compliance_officer"
    assert "Gate 10" in dana["reason"]

    # And somebody who does have an account is not reported missing.
    assert "Ivan" not in names


# --------------------------------------------------------------- bulk suspend

async def test_bulk_suspension_suspends_fixtures_and_never_the_actor(api):
    """Reversible, audited, and it cannot lock out the person running it."""
    ivan_id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    await make("smoke-11111111", "ivan", "smoke-11111111@example.invalid")
    await make("smoke-22222222", "venture_operator", "smoke-22222222@example.invalid")

    result = (
        await api.post("/api/access/suspend-test-fixtures", json={}, headers=auth(token))
    ).json()
    assert result["suspended"] == 2

    overview = (await api.get("/api/access/overview", headers=auth(token))).json()
    by_id = {row["human_id"]: row for row in overview["accounts"]}
    assert by_id[str(ivan_id)]["status"] == "active", "the actor suspended themselves"
    assert overview["counts"]["active_fixtures"] == 0


async def test_bulk_suspension_deletes_nothing(api, admin: psycopg.Connection):
    """The rule the page's own copy exists to protect.

    Deleting an account destroys the record of who held what and who granted it. A
    roster that reads more tidily because the evidence is gone is a worse roster.
    """
    _id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    await make("smoke-33333333", "ivan", "smoke-33333333@example.invalid")

    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM office_human")
        before = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM office_human_role")
        roles_before = cur.fetchone()[0]

    await api.post("/api/access/suspend-test-fixtures", json={}, headers=auth(token))

    with admin.cursor() as cur:
        cur.execute("SELECT count(*) FROM office_human")
        assert cur.fetchone()[0] == before, "an account was removed"
        cur.execute("SELECT count(*) FROM office_human_role")
        assert cur.fetchone()[0] == roles_before, "a grant was removed"


async def test_no_route_deletes_an_account():
    """The absent capability, enumerated rather than assumed."""
    surface = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    for path, method in surface:
        if "human" in path or "access" in path:
            assert method != "DELETE", f"DELETE {path} would destroy who held what"


# --------------------------------------------------------------------- presence

async def test_authenticating_records_that_the_account_was_seen(api):
    """178 accounts had never signed in and the roster had no column for it."""
    _id, token = await make("Ivan", "ivan", "ivan@office.example.com")

    # Authenticate once through the API, which is where presence is recorded.
    await api.get("/api/access/overview", headers=auth(token))

    overview = (await api.get("/api/access/overview", headers=auth(token))).json()
    me = next(row for row in overview["accounts"] if row["display_name"] == "Ivan")
    assert me["last_seen_at"] is not None, "signing in did not record presence"


async def test_mfa_enrolment_is_separate_from_the_claimed_method(api):
    """Every account claims `sso_mfa` because that is the column default.

    A signer whose second factor is a default rather than an enrolment weakens exactly
    the non-repudiation the Gate 10 signature is meant to carry, so the claim and the
    evidence are different fields.
    """
    _id, token = await make("Ivan", "ivan", "ivan@office.example.com")
    overview = (await api.get("/api/access/overview", headers=auth(token))).json()
    me = next(row for row in overview["accounts"] if row["display_name"] == "Ivan")

    assert me["auth_method"] == "sso_mfa", "the claim"
    assert me["mfa_enrolled_at"] is None, "the evidence, which nobody has provided"
    assert overview["counts"]["mfa_enrolled"] == 0
