"""Revocation: pickers over UUIDs, blast radius before the act, two humans to lift it."""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans, revocation
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000cccc")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM revocation")
    wipe_venture(conn, VENTURE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM venture WHERE slug = %s", (VENTURE,))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture(autouse=True)
def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    # `build_world` seeds forges and agents and no venture. Without one the venture
    # picker is empty, and a test that accepted an empty picker would be checking
    # nothing - an empty picker is the defect this page was rebuilt to remove.
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO venture (slug, display_name, category, environment, "
            "lifecycle_state, created_by) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (slug) DO NOTHING",
            (VENTURE, "Greenstone", "services", "production", "active", SEED),
        )
    admin.commit()
    yield
    _wipe(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def make_human(name: str, role: str) -> tuple[uuid.UUID, str]:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@revocation.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=None, granted_by=SEED
        )
    return human_id, token


# ------------------------------------------------------------------- the pickers

async def test_every_revocable_target_can_be_chosen_by_name(api):
    """The form asked for four UUIDs as free text.

    This is the emergency control. Nobody recalls a UUID under pressure, and a typo has
    two outcomes: it fails, or it stops something else. The second is worse, and it is
    silent.
    """
    _id, token = await make_human("Ivan", "ivan")
    targets = (await api.get("/api/revocations/targets", headers=auth(token))).json()

    assert targets["agents"], "no agent can be chosen; the picker would be empty"
    for agent in targets["agents"]:
        assert agent["id"] and agent["name"], (
            "a picker entry needs both: the name is what a person recognises, the id is "
            "what appears in the audit entry afterwards"
        )
    assert any(v["id"] == VENTURE for v in targets["ventures"])


# --------------------------------------------------------------- the blast radius

async def test_blast_radius_is_reported_for_every_scope(api):
    """Revoking a Forge stops every agent in the portfolio. That number was not on screen."""
    _id, token = await make_human("Ivan", "ivan")
    targets = (await api.get("/api/revocations/targets", headers=auth(token))).json()
    agent = targets["agents"][0]["id"]
    forge = targets["forges"][0]["id"] if targets["forges"] else "cre-forge"

    for scope, params in (
        ("agent", {"office_agent_id": agent}),
        ("venture", {"venture_id": VENTURE}),
        ("forge", {"forge_id": forge}),
    ):
        query = "&".join(f"{k}={v}" for k, v in {"scope": scope, **params}.items())
        radius = (
            await api.get(f"/api/revocations/blast-radius?{query}", headers=auth(token))
        ).json()

        assert radius["scope"] == scope
        assert isinstance(radius["agents"], int)
        assert isinstance(radius["grants"], int)
        assert isinstance(radius["in_flight_calls"], int)
        assert radius["required_role"] == revocation.SCOPE_MIN_ROLE[scope]

    # The forward-looking half. A venture revocation applies to grants issued *after*
    # it, which is exactly how a revoked venture quietly comes back to life if nobody
    # says so.
    venture_radius = (
        await api.get(
            f"/api/revocations/blast-radius?scope=venture&venture_id={VENTURE}",
            headers=auth(token),
        )
    ).json()
    assert "after the revocation" in (venture_radius["forward_looking"] or "")


async def test_a_forge_scope_reports_shifts_as_not_applicable_rather_than_zero(api):
    """Zero and n/a read completely differently on a screen about stopping things.

    Shifts are per agent and venture. A Forge-wide stop does not map onto one, and
    reporting `0 shifts affected` would say "this affects no shifts", which is not what
    is true - it is that the question does not apply.
    """
    _id, token = await make_human("Ivan", "ivan")
    radius = (
        await api.get(
            "/api/revocations/blast-radius?scope=forge&forge_id=cre-forge",
            headers=auth(token),
        )
    ).json()
    assert radius["shifts_today"] is None


async def test_the_blast_radius_predicate_matches_the_one_the_broker_enforces():
    """A radius computed from a different rule than the one enforced reassures wrongly.

    Both live in `broker/revocation.py`: `_CHECK_SQL` decides whether a call is blocked,
    and `blast_radius` counts what would be. If they ever describe different things the
    number on screen stops being about the act it precedes.
    """
    check = revocation._CHECK_SQL
    for scope in revocation.SCOPE_MIN_ROLE:
        assert f"scope = '{scope}'" in check, f"{scope} is not enforced by the broker"

    # The fields each scope uses, in one place, and the same list the console renders.
    assert set(revocation.SCOPE_FIELDS) == set(revocation.SCOPE_MIN_ROLE)
    assert revocation.SCOPE_FIELDS["agent_module"] == (
        "office_agent_id", "forge_id", "module_id",
    )
    assert revocation.SCOPE_FIELDS["forge"] == ("forge_id",)


async def test_the_radius_is_stored_with_the_revocation(api, admin: psycopg.Connection):
    """Asked six months later, the same query answers about today's grants.

    Which is not what the revocation did: the grants it stopped have since been
    re-issued or expired, and nothing in the number would show the difference. So it is
    counted once, at the moment of the act, and stored.
    """
    _id, token = await make_human("Ivan", "ivan")
    created = await api.post(
        "/api/revocations",
        json={"scope": "venture", "venture_id": VENTURE, "reason": "Inquiry pending."},
        headers=auth(token),
    )
    assert created.status_code == 201

    with admin.cursor() as cur:
        cur.execute(
            "SELECT blast_radius FROM revocation WHERE revocation_id = %s",
            (created.json()["revocation_id"],),
        )
        stored = cur.fetchone()[0]

    assert stored["scope"] == "venture"
    assert "agents" in stored and "grants" in stored


# ------------------------------------------------------------- the re-enable ritual

async def test_lifting_a_wide_revocation_needs_a_second_named_human(api):
    """§1.4 asks for a documented ritual. One person's judgement is not one.

    A venture or Forge stop reaches an engagement or the whole portfolio. Ending it
    should not rest on the same single judgement that started it.
    """
    ivan_id, token = await make_human("Ivan", "ivan")
    created = await api.post(
        "/api/revocations",
        json={"scope": "venture", "venture_id": VENTURE, "reason": "Inquiry pending."},
        headers=auth(token),
    )
    revocation_id = created.json()["revocation_id"]

    alone = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        json={"reason": "resolved"},
        headers=auth(token),
    )
    assert alone.status_code == 403
    assert "second named human" in alone.text

    himself = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        json={"reason": "resolved", "second_human": str(ivan_id)},
        headers=auth(token),
    )
    assert himself.status_code == 403, "naming yourself twice is still one judgement"

    other_id, _other_token = await make_human("Nadia", "compliance_officer")
    together = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        json={"reason": "Consent records produced.", "second_human": str(other_id)},
        headers=auth(token),
    )
    assert together.status_code == 200


async def test_a_narrow_revocation_lifts_without_a_second_human(api):
    """The ritual is proportionate. One grant is not a portfolio."""
    _id, token = await make_human("Ivan", "ivan")
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT office_agent_id FROM office_agent_identity LIMIT 1"
        )
        row = await cur.fetchone()
    agent_id = row[0]

    created = await api.post(
        "/api/revocations",
        json={"scope": "agent", "office_agent_id": str(agent_id), "reason": "Suspended."},
        headers=auth(token),
    )
    revocation_id = created.json()["revocation_id"]

    lifted = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        json={"reason": "Reinstated after review."},
        headers=auth(token),
    )
    assert lifted.status_code == 200


async def test_the_database_refuses_a_wide_lift_with_one_human(admin: psycopg.Connection):
    """The rule lives in the schema too.

    `revocation.reinstate` enforces it, and a route added later could forget to call it.
    The CHECK cannot be forgotten, and it is the version nobody can argue with under
    pressure.
    """
    revocation_id = uuid.uuid4()
    human = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "token_hash, status) VALUES (%s, 'Solo', 'solo@x.invalid', 'mfa_only', 'x', "
            "'active')",
            (human,),
        )
        cur.execute(
            "INSERT INTO revocation (revocation_id, scope, venture_id, reason, "
            "revoked_by, revoked_by_role) "
            "VALUES (%s, 'venture', %s, 'stop', %s, 'compliance_officer')",
            (revocation_id, VENTURE, human),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "UPDATE revocation SET reinstated_at = now(), reinstated_by = %s, "
                "reinstatement_reason = 'done' WHERE revocation_id = %s",
                (human, revocation_id),
            )
        admin.rollback()


async def test_reinstating_never_removes_the_revocation(api):
    """A history that reads cleaner than what happened is worse than no history."""
    _ivan, token = await make_human("Ivan", "ivan")
    other_id, _t = await make_human("Nadia", "compliance_officer")

    created = await api.post(
        "/api/revocations",
        json={"scope": "venture", "venture_id": VENTURE, "reason": "Inquiry pending."},
        headers=auth(token),
    )
    revocation_id = created.json()["revocation_id"]
    await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        json={"reason": "Consent records produced.", "second_human": str(other_id)},
        headers=auth(token),
    )

    history = (await api.get("/api/revocations/history", headers=auth(token))).json()
    row = next(r for r in history if r["revocation_id"] == revocation_id)

    assert row["active"] is False
    assert row["reason"] == "Inquiry pending.", "the original reason was lost"
    assert row["reinstatement_reason"] == "Consent records produced."
    assert row["second_human_name"] == "Nadia"
    assert row["duration_hours"] >= 0


async def test_no_route_deletes_a_revocation():
    """Lifting is an append. There is deliberately nothing that removes the record."""
    surface = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    for path, method in surface:
        if "revocation" in path:
            assert method not in {"DELETE", "PUT", "PATCH"}, (
                f"{method} {path} would erase a revocation from the record"
            )
