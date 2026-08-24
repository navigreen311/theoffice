"""C1-C10 - the Pack Editor and Provisioning Console routes.

Seven new write routes, and the reason each is safe to add is the same reason the
pinned surface exists: every one delegates to a guarded function. The interesting one
is `advance`, because it is the only route in the API that can end with an agent holding
production authority - and it gets there only by running the gate machine, which refuses
without a Gate 10 signature bound to the current artifacts.

The one that is new in kind is the sign-off. `POST /api/signoffs` takes whatever hash
its caller passes, which was harmless while nothing consumed it. Gate 11 consumes it
now, so the provisioning route recomputes the artifacts and refuses a mismatch: a
signature is a confirmation of what was on screen, not an assertion about the database.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans, packs
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.provisioning.conftest import amend_for_capacity
from tests.world import PACK_PATH, build_world, certify_for_positions, teardown_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


def _wipe(conn: psycopg.Connection) -> None:
    """The shared ordered list, not a copy of it. See `tests/conftest.wipe_venture`."""
    wipe_venture(conn, VENTURE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture
def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    certify_for_positions(admin)
    yield admin
    _wipe(admin)
    teardown_world(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def make_operator(name: str, venture: str | None = VENTURE) -> str:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@api.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator",
            venture_id=venture, granted_by=AUTHOR,
        )
    return token


@pytest.fixture
def pack_yaml() -> str:
    return PACK_PATH.read_text(encoding="utf-8")


@pytest.fixture
def feasible_yaml(pack_yaml) -> str:
    return amend_for_capacity(pack_yaml)


async def _publish(api, token, source, version="1.0.0"):
    response = await api.post(
        "/api/packs",
        json={"yaml_source": source, "pack_version": version},
        headers=auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _start(api, token):
    response = await api.post(
        "/api/provisioning/runs", json={"venture_id": VENTURE}, headers=auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["run_id"]


async def _advance(api, token, run_id):
    response = await api.post(
        f"/api/provisioning/runs/{run_id}/advance", headers=auth(token)
    )
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- pack editor

async def test_validate_reports_every_verdict_and_stores_nothing(
    world, api, pack_yaml
):
    """C1 - a POST that writes nothing, and a report that does not collapse NOT_RUN.

    Collapsing NOT_RUN into "no problem" is how a Pack whose bridge check never ran gets
    read as validated, which is the exact failure Gate 0 exists one link earlier to
    prevent.
    """
    token = await make_operator("Val")
    response = await api.post(
        "/api/packs/validate", json={"yaml_source": pack_yaml}, headers=auth(token)
    )
    assert response.status_code == 200
    body = response.json()

    assert body["parsed"] is True
    assert body["venture_id"] == VENTURE
    assert body["rules_checked"] >= 27
    verdicts = {r["verdict"] for r in body["results"]}
    assert verdicts <= {"PASS", "FAIL", "WARN", "NOT_RUN"}
    assert isinstance(body["not_run"], list)
    assert isinstance(body["failures"], list)
    assert isinstance(body["warnings"], list)

    async with connection() as conn:
        assert await packs.live(conn, VENTURE) is None, (
            "validation must not store the Pack it validated"
        )


async def test_validate_refuses_something_that_is_not_a_pack(world, api):
    """A parse failure is reported, not raised as a 500."""
    token = await make_operator("Val")
    response = await api.post(
        "/api/packs/validate", json={"yaml_source": "- not: a mapping"},
        headers=auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["parsed"] is False
    assert body["passed"] is False
    assert "mapping" in body["error"]


async def test_publishing_supersedes_and_returns_the_computed_hash(
    world, api, pack_yaml
):
    """C2 - and the hash comes from the database, never from the request."""
    token = await make_operator("Pub")
    first = await _publish(api, token, pack_yaml, "1.0.0")
    second = await _publish(api, token, pack_yaml + "\n# amended\n", "1.1.0")

    assert len(first["content_hash"]) == 64
    assert first["content_hash"] != second["content_hash"]

    detail = (await api.get(f"/api/packs/{VENTURE}", headers=auth(token))).json()
    assert detail["live"]["pack_version"] == "1.1.0"
    assert {v["pack_version"] for v in detail["versions"]} == {"1.0.0", "1.1.0"}
    superseded = {v["pack_version"]: v["superseded_at"] for v in detail["versions"]}
    assert superseded["1.0.0"] is not None


async def test_publishing_does_not_start_a_run(world, api, pack_yaml):
    """C3 - two acts, two routes. A save button that provisions is a save button that
    issues grants."""
    token = await make_operator("Pub")
    await _publish(api, token, pack_yaml)

    runs = (await api.get("/api/provisioning/runs", headers=auth(token))).json()
    assert runs == []


async def test_an_operator_of_another_venture_cannot_publish(world, api, pack_yaml):
    """The venture comes from the document, so authority is checked against it.

    A caller who could name the venture could publish one venture's Pack under another
    venture's id, and every gate downstream would provision the wrong business against
    a right-looking name.
    """
    token = await make_operator("Outsider", venture="burkham-wickmont")
    response = await api.post(
        "/api/packs", json={"yaml_source": pack_yaml, "pack_version": "1.0.0"},
        headers=auth(token),
    )
    assert response.status_code == 403


# -------------------------------------------------------- provisioning console

async def test_a_run_started_through_the_api_waits_at_gate_4(world, api, pack_yaml):
    """C5 - `awaiting_human` reaches the client as itself, not as blocked.

    An operator told "blocked" goes looking for a defect instead of reading the
    artifacts they are being asked to review.
    """
    token = await make_operator("Ops")
    await _publish(api, token, pack_yaml)
    run_id = await _start(api, token)
    result = await _advance(api, token, run_id)

    assert result["status"] == "awaiting_human"
    assert result["current_gate"] == "4"
    last = result["outcomes"][-1]
    assert last["gate"] == "4"
    assert last["verdict"] == "awaiting_human"
    assert "capacity" in last["evidence"]

    detail = (
        await api.get(f"/api/provisioning/runs/{run_id}", headers=auth(token))
    ).json()
    assert len(detail["ladder"]) == 16, "all sixteen gates, including the ones ahead"
    assert [g["gate"] for g in detail["ladder"]][:3] == ["0", "1", "2"]
    unrun = [g for g in detail["ladder"] if g["verdict"] is None]
    assert unrun, "gates that have not run report null, not a pass"
    assert any(g["is_current"] and g["gate"] == "4" for g in detail["ladder"])


async def test_review_requires_a_note_and_a_venture_scoped_operator(
    world, api, pack_yaml
):
    """C6 - both halves. A role string alone answers only the first question."""
    token = await make_operator("Ops")
    outsider = await make_operator("Elsewhere", venture="burkham-wickmont")
    await _publish(api, token, pack_yaml)
    run_id = await _start(api, token)
    await _advance(api, token, run_id)

    empty = await api.post(
        f"/api/provisioning/runs/{run_id}/review", json={"note": "   "},
        headers=auth(token),
    )
    assert empty.status_code == 400

    wrong_venture = await api.post(
        f"/api/provisioning/runs/{run_id}/review", json={"note": "looks fine"},
        headers=auth(outsider),
    )
    assert wrong_venture.status_code == 403

    ok = await api.post(
        f"/api/provisioning/runs/{run_id}/review",
        json={"note": "read the BOM and the appointment gap report"},
        headers=auth(token),
    )
    assert ok.status_code == 200


async def test_the_real_pack_blocks_at_gate_4_5_through_the_api(world, api, pack_yaml):
    """The capacity finding reaches the console with its number intact."""
    token = await make_operator("Ops")
    await _publish(api, token, pack_yaml)
    run_id = await _start(api, token)
    await _advance(api, token, run_id)
    await api.post(
        f"/api/provisioning/runs/{run_id}/review", json={"note": "reviewed"},
        headers=auth(token),
    )
    result = await _advance(api, token, run_id)

    assert result["status"] == "blocked"
    assert result["current_gate"] == "4.5"
    assert "192 approvals" in result["outcomes"][-1]["reason"]


async def test_a_run_from_the_console_stops_at_gate_9_5(world, api, feasible_yaml):
    """C5, the ceiling. There is no override and the route does not offer one.

    The API always uses the default held-out source, which reports that the partition
    does not exist. A parameter that let a caller supply a verdict would be a
    certification bypass with a polite name.
    """
    token = await make_operator("Ops")
    await _publish(api, token, feasible_yaml)
    run_id = await _start(api, token)
    await _advance(api, token, run_id)
    await api.post(
        f"/api/provisioning/runs/{run_id}/review", json={"note": "reviewed"},
        headers=auth(token),
    )
    result = await _advance(api, token, run_id)

    assert result["current_gate"] == "9.5"
    assert result["status"] == "blocked"
    verdicts = {o["gate"]: o["verdict"] for o in result["outcomes"]}
    assert verdicts["9"] == "passed"
    assert verdicts["9.5"] == "blocked"
    assert "10" not in verdicts


async def test_signoff_refuses_a_hash_that_is_not_the_current_artifacts(
    world, api, feasible_yaml, admin: psycopg.Connection
):
    """C7 - the control this route exists for.

    The signer sends the hash they were shown. If the world moved between render and
    click, signing would bind their name to artifacts they never read - so it is
    refused, rather than re-pointed at whatever the server computes now.
    """
    token = await make_operator("Ops")
    signer = await make_operator("Signer")
    await _publish(api, token, feasible_yaml)
    run_id = await _start(api, token)
    await _advance(api, token, run_id)
    await api.post(
        f"/api/provisioning/runs/{run_id}/review", json={"note": "reviewed"},
        headers=auth(token),
    )
    await _advance(api, token, run_id)
    # The hash the console displays, read the same way the screen reads it.
    shown = (
        await api.get(f"/api/provisioning/runs/{run_id}", headers=auth(token))
    ).json()["artifacts_hash"]
    assert shown

    stale = await api.post(
        f"/api/provisioning/runs/{run_id}/signoff",
        json={"artifacts_hash": "f" * 64}, headers=auth(signer),
    )
    assert stale.status_code == 409
    assert "have not seen" in stale.json()["detail"]

    # The world moves: one agent's certification goes stale, so the appointment changes.
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE certification SET state = 'stale_instructions' WHERE unit = 'A' "
            "AND office_agent_id = %s", ("11111111-1111-5111-8111-111111111111",)
        )
    admin.commit()

    moved = await api.post(
        f"/api/provisioning/runs/{run_id}/signoff",
        json={"artifacts_hash": shown}, headers=auth(signer),
    )
    assert moved.status_code == 409, (
        "a hash that was correct at render time and is not correct now must be refused"
    )
    assert "Reload the run" in moved.json()["detail"]

    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM signoff_record WHERE venture_id = %s", (VENTURE,)
        )
        row = await cur.fetchone()
    assert row is not None and row[0] == 0, "nothing was signed"


async def test_signing_the_displayed_hash_lets_gate_11_activate(
    world, api, feasible_yaml, admin: psycopg.Connection
):
    """C8 - and Gate 12 is still out of reach, because 9.5 is not passable here.

    So this asserts Gate 11's behaviour by driving it directly: the run is rewound to 11
    after a legitimate signature, which is what the machine would do if the partition
    existed. The point under test is that activation follows a valid signature.
    """
    token = await make_operator("Ops")
    signer = await make_operator("Signer")
    await _publish(api, token, feasible_yaml)
    run_id = await _start(api, token)
    await _advance(api, token, run_id)
    await api.post(
        f"/api/provisioning/runs/{run_id}/review", json={"note": "reviewed"},
        headers=auth(token),
    )
    await _advance(api, token, run_id)
    shown = (
        await api.get(f"/api/provisioning/runs/{run_id}", headers=auth(token))
    ).json()["artifacts_hash"]
    assert shown

    signed = await api.post(
        f"/api/provisioning/runs/{run_id}/signoff",
        json={"artifacts_hash": shown, "note": "reviewed and signed"},
        headers=auth(signer),
    )
    assert signed.status_code == 201, signed.text
    assert signed.json()["artifacts_hash"] == shown

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE provisioning_run SET status = 'running', current_gate = '10' "
            "WHERE run_id = %s", (run_id,)
        )
    admin.commit()

    final = await _advance(api, token, run_id)
    verdicts = {o["gate"]: o["verdict"] for o in final["outcomes"]}
    assert verdicts["10"] == "passed"
    assert verdicts["11"] == "passed"
    assert final["status"] == "complete"

    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*), count(activated_at) FROM agent_forge_grant "
            "WHERE venture_id = %s", (VENTURE,)
        )
        row = await cur.fetchone()
    assert row is not None
    assert row[0] > 0 and row[1] == row[0], "every grant activated"


async def test_there_is_no_route_that_activates_a_grant(world, api):
    """C9 - activation happens inside the gate machine or not at all.

    A route that set `activated_at` would be a one-call certification bypass: the
    signature check, the artifact binding and Gate 9 all live on the other side of it.
    """
    paths = {
        route.path
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in ("POST", "PUT", "PATCH", "DELETE")
    }
    for path in paths:
        assert "activate" not in path.lower()
        assert "grant" not in path.lower()

    token = await make_operator("Ops")
    for candidate in (
        "/api/grants", "/api/grants/activate", "/api/provisioning/activate",
        "/api/provisioning/runs/activate",
    ):
        response = await api.post(candidate, json={}, headers=auth(token))
        assert response.status_code in (404, 405), candidate


async def test_abort_frees_the_venture_and_leaves_grants_alone(
    world, api, feasible_yaml
):
    """C10 - abandoning a run is not revoking authority."""
    token = await make_operator("Ops")
    await _publish(api, token, feasible_yaml)
    run_id = await _start(api, token)
    await _advance(api, token, run_id)

    # A single space satisfies `min_length=1`, so the schema lets it through and the
    # domain function refuses it. That is the right order: the rule lives in one place.
    no_reason = await api.post(
        f"/api/provisioning/runs/{run_id}/abort", json={"note": " "},
        headers=auth(token),
    )
    assert no_reason.status_code == 400
    assert "requires a reason" in no_reason.json()["detail"]

    aborted = await api.post(
        f"/api/provisioning/runs/{run_id}/abort",
        json={"note": "superseded by an amended Pack"}, headers=auth(token),
    )
    assert aborted.status_code == 200

    again = await api.post(
        "/api/provisioning/runs", json={"venture_id": VENTURE}, headers=auth(token)
    )
    assert again.status_code == 201, "the venture is free for a new run"

    dead = await api.post(
        f"/api/provisioning/runs/{run_id}/advance", headers=auth(token)
    )
    assert dead.status_code == 409


async def test_every_read_route_requires_a_session(world, api):
    """The console is a client of The Office, not an anonymous view over it."""
    for path in (
        "/api/packs",
        f"/api/packs/{VENTURE}",
        "/api/provisioning/runs",
        f"/api/provisioning/runs/{uuid.uuid4()}",
    ):
        assert (await api.get(path)).status_code == 401, path
