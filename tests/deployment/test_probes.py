"""D1-D3 - the only two routes on this API that do not require a token.

Adding an unauthenticated route to an API whose entire design is "every write goes
through a guarded function and every read requires a named human" is a reviewable act.
So the set is enumerated here the same way the write surface is, and the reason each one
exists is that the alternative is no health checking at all: Docker's healthcheck and
Caddy's upstream check cannot hold a bearer token, and a container that has lost its
database would otherwise keep receiving traffic.
"""

from __future__ import annotations

import httpx
import psycopg
import pytest

from broker.app import EXPECTED_SCHEMA_REVISION, app
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


async def test_live_answers_without_a_token_and_says_nothing_else(api):
    """D1 - no version, no counts, no schema revision, no error text.

    A liveness endpoint is reachable by anyone who can reach the port. Everything it
    returns is public, so it returns one word.
    """
    response = await api.get("/api/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}

    body = response.text
    assert EXPECTED_SCHEMA_REVISION not in body
    assert "0.1.0" not in body


async def test_live_does_not_touch_the_database(api, monkeypatch):
    """A liveness probe that fails on a database outage turns it into an app outage.

    The orchestrator restarts a perfectly healthy process in a loop, the restarts do
    nothing because the database is still down, and the logs fill with a symptom that
    points at the wrong system. Readiness is where the database belongs.
    """
    from broker import db

    def refuse(*args, **kwargs):
        raise AssertionError("liveness must not open a database connection")

    monkeypatch.setattr(db, "connection", refuse)
    response = await api.get("/api/live")
    assert response.status_code == 200


async def test_ready_is_ready_against_a_migrated_database(api):
    response = await api.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_ready_refuses_when_the_schema_is_not_the_one_this_build_expects(
    api, admin: psycopg.Connection
):
    """D2 - the check that keeps a deploy from switching traffic too early.

    A container serving traffic against a half-migrated database is worse than one that
    is down: it answers, and it answers wrong. Simulated by moving the recorded revision
    rather than by running a real migration, because the question is what the endpoint
    does when the two disagree.
    """
    with admin.cursor() as cur:
        cur.execute("UPDATE alembic_version SET version_num = 'not-this-one'")
    admin.commit()
    try:
        response = await api.get("/api/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready"}
        # The reason belongs in the container log, not in an unauthenticated response.
        assert "not-this-one" not in response.text
        assert EXPECTED_SCHEMA_REVISION not in response.text
    finally:
        with admin.cursor() as cur:
            cur.execute(
                "UPDATE alembic_version SET version_num = %s",
                (EXPECTED_SCHEMA_REVISION,),
            )
        admin.commit()


async def test_the_expected_revision_matches_the_latest_migration():
    """The two disagreeing is the condition `/api/ready` exists to detect, so they must
    be kept in step - and a test is the only thing that will remember."""
    from pathlib import Path

    versions = Path(__file__).resolve().parents[2] / "db" / "versions"
    revisions = sorted(
        p.name.split("_")[0] for p in versions.glob("[0-9]*.py")
    )
    assert revisions[-1] == EXPECTED_SCHEMA_REVISION, (
        f"broker.app.EXPECTED_SCHEMA_REVISION is {EXPECTED_SCHEMA_REVISION} and the "
        f"latest migration is {revisions[-1]}. Bump it in the same commit as the "
        "migration; a build that expects an older schema will never become ready."
    )


async def test_the_unauthenticated_surface_is_exactly_these_two(api):
    """D3 - enumerated, not reviewed by eye.

    Only GET-able paths are probed. The first version of this GET everything and read
    "not 401" as "unauthenticated", which caught five POST-only routes answering 405 -
    a check failing for a reason that had nothing to do with what it was asking. If the
    set had happened to match, it would have passed for the same wrong reason.

    If a new route trips this, the question is not how to make it pass. It is whether
    that route should be reachable without a named human behind it.
    """
    gettable = {
        route.path
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/")
        and "GET" in getattr(route, "methods", set())
        and "{" not in route.path
    }
    assert len(gettable) > 5, "the probe found almost no routes; it is asking nothing"

    unauthenticated = {
        path for path in sorted(gettable) if (await api.get(path)).status_code != 401
    }

    assert unauthenticated == {"/api/live", "/api/ready"}, (
        f"the unauthenticated surface changed: {sorted(unauthenticated)}"
    )


async def test_every_write_route_refuses_an_anonymous_request(api):
    """The other half. A write reachable without a token is worse than a readable one.

    401 or 422 - FastAPI may reject the body before it ever resolves the dependency
    that would have rejected the caller. What matters is that nothing anonymous gets a
    2xx or a redirect.
    """
    writes = {
        route.path
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in ("POST", "PUT", "PATCH", "DELETE")
        and "{" not in getattr(route, "path", "")
    }
    assert writes, "no write routes found; this test is asking nothing"

    for path in sorted(writes):
        response = await api.post(path, json={})
        assert response.status_code in (401, 422), f"{path} answered {response.status_code}"


async def test_a_bad_token_is_still_refused_by_everything_else(api):
    """The probes are an exception to authentication, not a hole in it."""
    headers = {"Authorization": "Bearer not-a-real-token"}
    assert (await api.get("/api/health", headers=headers)).status_code == 401
    assert (await api.get("/api/agents", headers=headers)).status_code == 401
    # And the probes do not start accepting one either way.
    assert (await api.get("/api/live", headers=headers)).status_code == 200
