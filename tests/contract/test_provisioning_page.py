"""R1-R12 - the gate ladder, and the two walls a reader has to tell apart.

The page promised that a run "stops at the first gate that blocks and says which". It
named the gate number and stopped there: sixteen gates rendered as `5 of 16`, which is a
number with no map. It could not say what happened at the gate that stopped the run,
what cleared before it, or what is still ahead.

Four properties carry these tests.

**The ceiling is not a failure.** A run blocked at 9.5 because the partition does not
exist has done everything this deployment can do. Rendering that as broken would
misreport a successful run - and a held-out verdict of FAIL at the *same gate* is a real
failure, so the distinction is drawn on the evidence rather than the gate number.

**There is no override.** The ceiling notice states there is none deliberately. That is
enforced here rather than trusted: no route may advance a run past a gate that blocked
it, and the write surface is enumerated so a new one cannot be added quietly.

**`cancelled` and `rejected` are different outcomes.** Aborting abandons a run and says
nothing about the artifacts; rejecting is a judgement about them. Before this increment
a human could only abandon - Gate 4 review had no way to decline - so the two were the
same status and the difference was unrecoverable.

**Resume is refused when the Pack moved.** A run holds the Pack hash it began with.
Resuming against different content would provision something nobody started.
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import humans, packs, provisioning
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world, certify_for_positions

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000cccc")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    wipe_venture(conn, VENTURE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


class World:
    def __init__(self, admin: psycopg.Connection, human_id: uuid.UUID, token: str):
        self.admin = admin
        self.human_id = human_id
        self.token = token


@pytest.fixture
async def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    certify_for_positions(admin)

    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Run operator", email="runs@runs.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id=None,
            granted_by=SEED,
        )
        await packs.store(
            conn, yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="1.0.0", authored_by=human_id,
        )

    yield World(admin, human_id, token)
    _wipe(admin)


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _start(world: World) -> uuid.UUID:
    async with connection() as conn:
        return await provisioning.start_run(
            conn, venture_id=VENTURE, started_by=world.human_id
        )


# ================================================= R1 - THE ONE THAT MATTERS MOST

async def test_no_route_can_pass_a_gate_that_blocked():
    """R1 - the ceiling notice says there is no override. This is why that is true.

    Not "no button exists" - no *route* exists. A force, skip or bypass would be a
    reasonable-sounding request ("let the operator get past 9.5 in dev") that removes
    the entire certification gate, and would produce a venture reading as fully
    provisioned that has been certified for nothing.

    If a new route trips this test, the question is not how to make it pass.
    """
    writes = {
        route.path
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in ("POST", "PUT", "PATCH", "DELETE")
    }
    provisioning_writes = {p for p in writes if "provisioning" in p}

    for path in provisioning_writes:
        for fragment in ("force", "skip", "override", "bypass", "unblock", "pass"):
            assert fragment not in path.lower(), (
                f"{path!r} looks like a way past a gate. The ceiling notice states there "
                "is no override, deliberately - a route that offers one makes that copy "
                "a lie and turns certification into a formality."
            )

    assert provisioning_writes == {
        "/api/provisioning/runs",
        "/api/provisioning/runs/{run_id}/advance",
        "/api/provisioning/runs/{run_id}/review",
        "/api/provisioning/runs/{run_id}/reject",
        "/api/provisioning/runs/{run_id}/abort",
        "/api/provisioning/runs/{run_id}/signoff",
    }, (
        "the provisioning write surface changed. Every one of these either starts a run, "
        "runs gates in order, or stops a run. None of them passes a gate."
    )


async def test_a_literal_path_under_api_provisioning_is_not_shadowed():
    """R2 - the same ordering trap `/api/packs/directory` shipped with.

    FastAPI matches in declaration order and does not warn, so a literal segment
    declared after a parameterised one is handed to the path parameter and answers 200
    with the wrong body.
    """
    order: list[tuple[str, str]] = [
        (getattr(route, "path", ""), method)
        for route in app.routes
        for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"})
    ]
    for index, (path, method) in enumerate(order):
        segments = path.split("/")
        if len(segments) < 4 or not path.startswith("/api/provisioning/"):
            continue
        if segments[3].startswith("{"):
            continue
        depth = path.count("/")
        earlier = [
            other
            for position, (other, other_method) in enumerate(order)
            if position < index
            and other_method == method
            and other.startswith("/api/provisioning/{")
            and other.count("/") == depth
        ]
        assert not earlier, (
            f"{method} {path} is declared after {earlier[0]!r} and is unreachable."
        )


# ======================================================= R3-R6 - the vocabulary

async def test_the_ceiling_is_not_reported_as_a_failure(world):
    """R3 - a run at 9.5 has done everything this deployment can do."""
    blocking = {
        "gate": "9.5",
        "evidence": {"blocked_by": provisioning.CEILING_EVIDENCE},
    }
    assert provisioning.display_status("blocked", "9.5", blocking) == "at ceiling"

    # The same gate, a real adversarial failure. Not the ceiling.
    failed = {"gate": "9.5", "evidence": {"verdict": "FAIL"}}
    assert provisioning.display_status("blocked", "9.5", failed) == "stopped at gate 9.5"


async def test_an_error_is_not_the_same_as_a_policy_block(world):
    """R4 - gate 4 blocking on review is not gate 3 throwing."""
    error = {"gate": "3", "evidence": {"error": True}}
    assert provisioning.display_status("blocked", "3", error) == "failed at gate 3"

    policy = {"gate": "3", "evidence": {}}
    assert provisioning.display_status("blocked", "3", policy) == "stopped at gate 3"


async def test_cancelled_and_rejected_are_different_outcomes(world):
    """R5 - one says the run was abandoned, the other judges the artifacts.

    They were the same status until this increment, because Gate 4's human review could
    only ever approve. A review that cannot decline is not a review.
    """
    assert provisioning.display_status("aborted", "4", None) == "cancelled"
    assert provisioning.display_status("rejected", "4", None) == "rejected at gate 4"


async def test_a_human_cannot_reject_a_run_no_gate_handed_them(world):
    """R6 - rejecting is a decision at a gate, not a way to stop a run mid-flight.

    Abandoning a run is what `abort_run` is for, and it carries a different meaning.
    """
    run_id = await _start(world)
    async with connection() as conn:
        human = await humans.authenticate(conn, world.token)
        assert human is not None
        state = await provisioning.get_run(conn, run_id)
        assert state is not None
        if state.status == provisioning.AWAITING_HUMAN:
            pytest.skip("this world reaches a human gate immediately")

        with pytest.raises(provisioning.ProvisioningError) as caught:
            await provisioning.reject_run(
                conn, run_id=run_id, human=human, reason="no"
            )
        assert "not awaiting a human decision" in str(caught.value)


# ======================================================== R7-R10 - the ladder

async def test_the_ladder_renders_every_gate_whether_or_not_it_ran(api, world):
    """R7 - the point is seeing the whole path, including what is still ahead."""
    await _start(world)
    body = (
        await api.get("/api/provisioning/directory", headers=auth(world.token))
    ).json()

    assert body["gates_total"] == len(provisioning.GATE_SEQUENCE)
    venture = next(v for v in body["ventures"] if v["venture_id"] == VENTURE)
    assert [row["gate"] for row in venture["ladder"]] == list(
        provisioning.GATE_SEQUENCE
    ), "the ladder is truncated or reordered; it has to be the whole path, in order"


async def test_the_ceiling_gate_is_marked_in_every_ladder(api, world):
    """R8 - the wall ahead is visible wherever the run stopped.

    Greenstone stops at a gate long before 9.5. Those are two unrelated problems and a
    reader has to be able to see both.
    """
    await _start(world)
    body = (
        await api.get("/api/provisioning/directory", headers=auth(world.token))
    ).json()
    venture = next(v for v in body["ventures"] if v["venture_id"] == VENTURE)

    ceiling = [row for row in venture["ladder"] if row["is_ceiling"]]
    assert len(ceiling) == 1
    assert ceiling[0]["gate"] == body["ceiling_gate"] == "9.5"


async def test_a_stopped_run_says_what_happened_not_what_the_gate_checks(api, world):
    """R9 - the reason is this run's outcome, never the gate's description.

    A generic description is true of every run and about none of them.
    """
    await _start(world)
    async with connection() as conn:
        await provisioning.advance(
            conn, run_id=(await _latest(conn)), actor=world.human_id
        )

    body = (
        await api.get("/api/provisioning/directory", headers=auth(world.token))
    ).json()
    venture = next(v for v in body["ventures"] if v["venture_id"] == VENTURE)
    run = venture["run"]
    assert run is not None

    if run["stop"] is not None:
        gate = run["stop"]["gate"]
        assert run["stop"]["reason"] != provisioning.GATE_TITLES[gate], (
            "the stop renders the gate's generic description in place of an outcome"
        )
        assert run["stop"]["reason"].strip()


async def test_the_empty_ladder_is_the_pipeline_not_a_blank(api, world):
    """R10 - what a run will do is more use than an empty table."""
    body = (
        await api.get("/api/provisioning/directory", headers=auth(world.token))
    ).json()
    assert [row["gate"] for row in body["empty_ladder"]] == list(
        provisioning.GATE_SEQUENCE
    )
    assert {row["state"] for row in body["empty_ladder"]} == {"pending"}


# ==================================================== R11-R12 - resume and history

async def test_resume_is_refused_when_the_pack_changed(api, world):
    """R11 - a run holds the hash it began with.

    Resuming against different content would provision something nobody started, and the
    run's Gate 10 signature would bind to artifacts nobody reviewed.
    """
    await _start(world)
    async with connection() as conn:
        await provisioning.advance(
            conn, run_id=(await _latest(conn)), actor=world.human_id
        )

        # Same version, different content: the exact case a version string cannot catch.
        edited = PACK_PATH.read_text(encoding="utf-8").replace(
            "operating_status: launching", "operating_status: operating"
        )
        await packs.store(
            conn, yaml_source=edited, pack_version="1.0.0",
            authored_by=world.human_id,
        )

    body = (
        await api.get("/api/provisioning/directory", headers=auth(world.token))
    ).json()
    venture = next(v for v in body["ventures"] if v["venture_id"] == VENTURE)

    assert venture["pack_changed"] is True
    assert venture["resumable"] is False
    assert venture["resume_blocked_because"] == (
        "Pack has changed since this run. Start a fresh run."
    )


async def test_history_lists_every_run_not_just_the_latest(api, world):
    """R12 - the same gate failing four times is a different problem from four gates
    failing once, and only the list shows that."""
    await _start(world)
    async with connection() as conn:
        human = await humans.authenticate(conn, world.token)
        assert human is not None
        run_id = await _latest(conn)
        await provisioning.abort_run(
            conn, run_id=run_id, human=human, reason="making room for a second run"
        )
    await _start(world)

    body = (
        await api.get(
            f"/api/provisioning/history/{VENTURE}", headers=auth(world.token)
        )
    ).json()
    assert len(body["runs"]) >= 2, "history shows one run; the pattern is invisible"
    assert any(run["display_status"] == "cancelled" for run in body["runs"])
    for run in body["runs"]:
        assert run["pack_version"], "a run without its Pack version is not evidence"


async def _latest(conn) -> uuid.UUID:
    # These tests start their own runs from a fixture account, so they ask for
    # fixtures explicitly - otherwise the helper filters out the very runs the
    # test just created.
    listing = await provisioning.list_runs(
        conn, venture_id=VENTURE, include_fixtures=True
    )
    runs = listing["runs"]
    return uuid.UUID(runs[0]["run_id"])
