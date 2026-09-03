"""Q1-Q10 - the approval queue, and the control a UI can defeat without bypassing.

The page was an empty state and nothing else: no design for a pending item, no reviewer
capacity, no decision history, and an empty state that named the wrong cause. It said to
check whether the agents' trust tiers were set to `auto_execute` - a real cause, and not
this one. No agent held a grant to any Forge and none had ever made a call, so the queue
was empty because nothing could act.

Four properties carry these tests.

**The empty state is derived, never generic.** A sentence that is true in general and
wrong here is worse than no sentence: it sends a reader to inspect trust tiers on a
system where nothing can act at all.

**Expiry never approves.** A queue that drains itself looks like a queue being worked,
which is why auto-approval on timeout is the most attractive shortcut on this page and
why it does not exist. The task fails, and both facts are audited.

**There is no bulk approve.** Bulk approval is the rubber-stamp mechanism this page's own
copy warns about, industrialised. Bulk deny is fine - denying is the safe direction.

**Time to decision is measured, not asserted.** `review_seconds` is computed in the
database from `created_at`, so a client cannot report a review it did not perform.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import httpx
import psycopg
import pytest

from broker import humans, proposals
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000eeee")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM proposal")
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
    async with connection() as conn:
        from broker import packs

        human_id, token = await humans.create_human(
            conn, display_name="Ivan", email="ivan@approvals.invalid"
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


async def _submit(conn, agent, *, task_id: str, key: str, payload: dict):
    """Submit a proposal with the hash and trace the real caller supplies. Returns its id.

    `payload_hash` is the agent's own statement about what it sent; the queue shows it
    beside the payload so a reviewer can see the two agree.
    """
    return await proposals.submit(
        conn,
        office_agent_id=agent,
        venture_id=VENTURE,
        forge_id="cre-forge",
        module_id="place_call",
        task_id=task_id,
        trust_tier="propose",
        payload=payload,
        payload_hash=hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest(),
        idempotency_key=key,
        trace_id=uuid.uuid4(),
    )


async def _agent(admin: psycopg.Connection) -> uuid.UUID:
    with admin.cursor() as cur:
        cur.execute("SELECT office_agent_id FROM office_agent_identity LIMIT 1")
        row = cur.fetchone()
    assert row is not None, "the world has no agent"
    return row[0]


# =========================================== Q1-Q3 - the empty state, derived

async def test_the_empty_state_names_this_cause_not_a_plausible_one(api, world):
    """Q1 - the sentence that sent a reader to check trust tiers.

    It is a real cause of an empty queue and it was not this cause. With no grant to any
    Forge and no call ever made, the queue is empty because nothing can act - and saying
    otherwise implies the system is further along than it is.
    """
    body = (await api.get("/api/proposals/queue", headers=auth(world.token))).json()

    assert body["state"]["live_grants"] == 0
    assert body["state"]["calls_ever"] == 0
    reason = body["empty_reason"]
    assert "nothing could be" in reason
    assert "has not started operating" in reason
    assert "auto_execute" not in reason, (
        "the empty state still points at trust tiers on a system where no agent holds "
        "a grant at all"
    )


async def test_the_empty_state_changes_when_the_reason_changes(world):
    """Q2 - four states, four sentences, and none of them a fallback.

    A generic message would be wrong in three of these four cases, which is the whole
    argument for deriving it.
    """
    nothing = {"live_grants": 0, "grants_below_auto": 0, "calls_ever": 0, "proposals_today": 0}
    assert "nothing could be" in proposals._empty_reason(nothing, 0, [])

    all_auto = {"live_grants": 4, "grants_below_auto": 0, "calls_ever": 9, "proposals_today": 0}
    assert "auto_execute" in proposals._empty_reason(all_auto, 0, [])

    not_acted = {"live_grants": 4, "grants_below_auto": 2, "calls_ever": 0, "proposals_today": 0}
    assert "none has acted yet" in proposals._empty_reason(not_acted, 0, [])

    caught_up = {"live_grants": 4, "grants_below_auto": 2, "calls_ever": 9, "proposals_today": 3}
    message = proposals._empty_reason(caught_up, 3, [4.0, 6.0])
    assert "All 3 proposals today have been decided" in message
    assert "5s" in message, "the median is stated, not implied"


async def test_reviewer_capacity_comes_from_the_pack(api, world):
    """Q3 - this is the page where V13 either holds or fails in practice.

    `human_capacity` is declared in the Pack and is what V13 checks against. There is no
    separate reviewer table, and inventing one would give the two a way to disagree.
    """
    body = (await api.get("/api/proposals/queue", headers=auth(world.token))).json()

    assert body["reviewers"], "no reviewer capacity is reported"
    for reviewer in body["reviewers"]:
        assert reviewer["max_daily_approvals"] > 0
        assert reviewer["remaining_today"] <= reviewer["max_daily_approvals"]
        assert "coverage_hours" in reviewer
        assert "timezone" in reviewer


# ================================== Q4-Q6 - THE ONES THAT MATTER MOST

async def test_expiry_never_approves(world):
    """Q4 - the most attractive shortcut on this page.

    A queue that drains itself looks like a queue being worked. An agent below
    `auto_execute` asked to act, nobody answered, and it did not act: that is the correct
    outcome, and a timeout that approved would make the trust tier a delay rather than a
    decision.
    """
    agent = await _agent(world.admin)
    async with connection() as conn:
        proposal_id = await _submit(
            conn, agent, task_id="t-1", key="k-1", payload={"to": "+1555"}
        )

        # Past its deadline.
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE proposal SET expires_at = now() - interval '1 minute' "
                "WHERE proposal_id = %s",
                (proposal_id,),
            )
        await conn.commit()

        expired = await proposals.expire_overdue(conn)
        assert len(expired) == 1

        after = await proposals.get(conn, proposal_id)

    assert after is not None
    assert after["status"] == "expired", f"expired proposal became {after['status']}"
    assert after["status"] != "approved"
    assert after["decided_by"] is None, (
        "an expired proposal names a decider; nobody decided it"
    )


async def test_no_route_approves_in_bulk():
    """Q5 - bulk approval is the rubber-stamp mechanism, industrialised.

    If volume is high enough that bulk approval feels necessary, the answer is the V13
    fix - raise a trust-tier ceiling, add reviewer coverage, or cut scope. Bulk deny is
    acceptable: denying is the safe direction.
    """
    writes = {
        route.path
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in ("POST", "PUT", "PATCH", "DELETE")
    }
    proposal_writes = {p for p in writes if "proposal" in p.lower()}

    assert proposal_writes == {"/api/proposals/{proposal_id}/decide"}, (
        f"the proposal write surface is {sorted(proposal_writes)}. One route, one "
        "proposal at a time. A bulk-approve route is the control this page warns about, "
        "at scale."
    )
    for path in writes:
        for fragment in ("approve-all", "bulk", "auto-approve", "trusted"):
            assert fragment not in path.lower(), (
                f"{path!r} looks like a way to approve without reading. This page's own "
                "copy says a trust tier that is really a click-through is worse than no "
                "tier at all."
            )


async def test_a_decision_records_how_long_it_took(api, world):
    """Q6 - the threshold in the copy is unenforceable without this.

    `review_seconds` is computed in the database from `created_at`, so a client cannot
    report a review it did not perform.
    """
    agent = await _agent(world.admin)
    async with connection() as conn:
        proposal_id = await _submit(
            conn, agent, task_id="t-2", key="k-2", payload={"to": "+1555"}
        )

    response = await api.post(
        f"/api/proposals/{proposal_id}/decide",
        headers=auth(world.token),
        json={"approve": False, "reason": "not now"},
    )
    assert response.status_code == 200

    async with connection() as conn:
        decided = await proposals.get(conn, proposal_id)

    assert decided is not None
    assert decided["review_seconds"] is not None
    assert float(decided["review_seconds"]) >= 0


# ==================================== Q7-Q10 - what the queue renders

async def test_the_queue_is_oldest_first(api, world):
    """Q7 - newest-first invites cherry-picking the easy ones.

    The item that has waited longest is also the one closest to expiring.
    """
    agent = await _agent(world.admin)
    async with connection() as conn:
        for index in range(3):
            await _submit(
                conn, agent, task_id=f"t-order-{index}",
                key=f"order-{index}", payload={"n": index},
            )

    body = (await api.get("/api/proposals/queue", headers=auth(world.token))).json()
    created = [row["created_at"] for row in body["pending"]]
    assert created == sorted(created), "the queue is not oldest-first"


async def test_a_pending_item_carries_its_payload_and_flags(api, world):
    """Q8 - "read the payload" is the instruction; the payload has to be there.

    Compliance flags come from the module registry, so the reviewer sees what the call
    would touch rather than what the proposal claims about itself.
    """
    agent = await _agent(world.admin)
    async with connection() as conn:
        await _submit(
            conn, agent, task_id="t-payload", key="payload-1",
            payload={"to": "+15551234567", "script": "intro"},
        )

    body = (await api.get("/api/proposals/queue", headers=auth(world.token))).json()
    item = body["pending"][0]

    assert item["payload"]["to"] == "+15551234567"
    assert item["payload_hash"]
    assert item["agent_name"], "the queue shows an agent id with no name"
    assert item["expires_at"], "no deadline, so nothing can say what happens if nobody acts"
    assert "compliance_flags_implied" in item


async def test_history_carries_the_payload_as_it_stood(api, world):
    """Q9 - the evidence a regulator asks for: what did the reviewer see.

    The payload lives on the proposal row, which is never rewritten, so the decision and
    the document it was made against cannot drift apart.
    """
    agent = await _agent(world.admin)
    async with connection() as conn:
        proposal_id = await _submit(
            conn, agent, task_id="t-history", key="history-1",
            payload={"to": "+15559999999"},
        )
        await proposals.decide(
            conn, proposal_id=proposal_id, approve=False,
            decided_by=world.human_id, reason="wrong number",
        )

    body = (await api.get("/api/proposals/queue", headers=auth(world.token))).json()
    decided = next(
        row for row in body["history"] if row["proposal_id"] == str(proposal_id)
    )

    assert decided["status"] == "rejected"
    assert decided["decision_reason"] == "wrong number"
    assert decided["reviewer"] == "Ivan"
    assert decided["payload"]["to"] == "+15559999999"
    assert decided["review_seconds"] is not None


async def test_capacity_reports_when_pending_exceeds_what_is_left(api, world):
    """Q10 - the V13 question, asked against today rather than the Pack's estimate.

    More pending than anybody can still decide means the overflow will not be reviewed
    before the window closes, and the page has to say so rather than showing a long list.
    """
    body = (await api.get("/api/proposals/queue", headers=auth(world.token))).json()
    capacity = body["capacity"]

    assert capacity["remaining_today"] >= 0
    assert capacity["pending"] == len(body["pending"])
    assert capacity["over_capacity"] is (
        capacity["pending"] > capacity["remaining_today"] and capacity["pending"] > 0
    )
