"""Forge Map: three sources, four handlers, and the whole estate rather than one venture."""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from broker import forge_map, humans, packs
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _wipe(conn: psycopg.Connection) -> None:
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


async def _operator() -> tuple[uuid.UUID, str]:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Ivan", email="ivan@forgemap.example.com"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="ivan", venture_id=None, granted_by=SEED
        )
        await packs.store(
            conn, yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="1.0.0", authored_by=human_id, publish=True,
        )
    return human_id, token


# ---------------------------------------------------------------- three sources

async def test_declared_comes_from_the_pack_not_the_manifest(api):
    """The three states came from one place, so the diff the page promised could not exist.

    A `venture_forge_manifest` row was both the declaration and the requirement. With the
    manifest empty - the generators have never run - the table rendered nothing while the
    Pack declared nine modules, and "nothing declared" was not even true.
    """
    _id, _token = await _operator()
    async with connection() as conn:
        result = await forge_map.reconcile(conn, VENTURE)

    assert result["declared_count"] > 0, (
        "the Pack declares modules and the reconciliation found none"
    )
    assert result["required_count"] == 0, "no generator has run in this fixture"
    assert all(row["declared"] for row in result["rows"]), (
        "every row here should come from the Pack"
    )
    assert {row["mismatch"] for row in result["rows"]} == {"DECLARED_NOT_REQUIRED"}


async def test_the_empty_state_names_the_cause_not_the_mechanism(api):
    """"Generator 5.6 produces these rows from a Pack" says how they would arrive.

    It does not say why none has, and the answer - every run stopped at a gate - is a
    query away.
    """
    _id, _token = await _operator()
    async with connection() as conn:
        async with conn.cursor() as cur:
            for _ in range(3):
                await cur.execute(
                    "INSERT INTO provisioning_run (run_id, venture_id, pack_version, "
                    "pack_hash, status, current_gate, started_by) "
                    "VALUES (%s, %s, '1.0.0', 'abc', 'aborted', '4', %s)",
                    (uuid.uuid4(), VENTURE, SEED),
                )
        await conn.commit()
        result = await forge_map.reconcile(conn, VENTURE)

    assert result["blocked_reason"] is not None
    assert "gate 4" in result["blocked_reason"]
    assert "3 runs" in result["blocked_reason"], result["blocked_reason"]


async def test_every_handler_the_spec_names_is_published(api):
    """A classification nobody acts on is a label."""
    _id, token = await _operator()
    response = await api.get(
        f"/api/ventures/{VENTURE}/forge-map", headers=auth(token)
    )
    handlers = {row["mismatch"] for row in response.json()["handlers"]}
    assert handlers == {
        "DECLARED_NOT_REQUIRED",
        "REQUIRED_NOT_DECLARED",
        "IN_USE_NOT_REQUIRED",
        "REQUIRED_NOT_IN_USE_30D",
    }
    for row in response.json()["handlers"]:
        assert row["meaning"].strip(), f"{row['mismatch']} says nothing about what happens"


async def test_a_call_nothing_requires_is_classified_as_the_incident_it_raises(api):
    """IN_USE_NOT_REQUIRED is the shape of an agent doing work nobody asked for."""
    _id, _token = await _operator()
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT office_agent_id FROM office_agent_identity LIMIT 1"
            )
            agent = (await cur.fetchone())[0]
            # The column list the rest of this suite uses; `agent_call_ledger` has
            # several NOT NULL columns with no default, and guessing them one failure at
            # a time is how a fixture ends up subtly different from every other.
            await cur.execute(
                """
                INSERT INTO agent_call_ledger
                  (call_id, trace_id, office_agent_id, venture_id, forge_id, module_id,
                   api_version, ts_start, status_code, trust_tier_at_call,
                   manifest_match, payload_hash)
                VALUES (%s, %s, %s, %s, 'cre-forge', 'not_in_any_pack', '1.4.0', now(),
                        200, 'auto_execute', 'UNDECLARED', 'seed')
                """,
                (uuid.uuid4(), uuid.uuid4(), agent, VENTURE),
            )
        await conn.commit()
        result = await forge_map.reconcile(conn, VENTURE)

    row = next(r for r in result["rows"] if r["module_id"] == "not_in_any_pack")
    assert row["mismatch"] == "IN_USE_NOT_REQUIRED"
    assert row["tone"] == "bad"
    assert "incident" in row["meaning"].lower()


# ------------------------------------------------------------------- the estate

async def test_the_estate_lists_forges_with_no_bridge(api):
    """The map showed only what one venture declared.

    A Forge with no bridge was indistinguishable from one that does not exist, which is
    the state four of the eight are in.
    """
    _id, token = await _operator()
    response = await api.get("/api/forge-map/estate", headers=auth(token))
    forges = response.json()["forges"]

    assert len(forges) >= 8, "the portfolio names eight Forges"
    unbridged = [f["forge_id"] for f in forges if not f["bridged"]]
    assert unbridged, "every Forge is bridged, which contradicts the portfolio"
    for forge_id in ("capitalforge", "paf", "funnelforge", "visionaudioforge"):
        assert forge_id in unbridged, f"{forge_id} has no bridge and is not reported"

    # Bridged ones carry the operational facts the Agents page already had and this one
    # did not.
    for forge in forges:
        if forge["bridged"]:
            assert forge["health"], f"{forge['forge_id']} is bridged with no health"
            assert forge["credential_mode"], f"{forge['forge_id']} has no credential mode"


async def test_the_matrix_answers_which_ventures_halt(api):
    """The blast-radius view: read a column, not a row."""
    _id, token = await _operator()
    matrix = (await api.get("/api/forge-map/matrix", headers=auth(token))).json()

    assert VENTURE in matrix["ventures"]
    assert "cre-forge" in matrix["forges"]

    declared = [
        cell for cell in matrix["cells"]
        if cell["venture_id"] == VENTURE and cell["declared"]
    ]
    assert declared, "the Pack declares Forges and the matrix shows none"
    # Criticality comes from the Pack, so `hard` means the Pack said `halt`.
    assert any(cell["criticality"] == "hard" for cell in declared)


async def test_the_estate_is_declared_but_its_status_never_is():
    """`ESTATE` names the Forges; nothing in it claims one is bridged.

    The same rule `ventures.PORTFOLIO` follows: declared knowledge is fine, a hardcoded
    *status* is a page that goes on claiming a Forge is unbridged after somebody bridges
    it.
    """
    for entry in forge_map.ESTATE:
        assert set(entry) <= {"forge_id", "display_name", "note"}, (
            f"{entry['forge_id']} hardcodes status: {sorted(set(entry))}"
        )
