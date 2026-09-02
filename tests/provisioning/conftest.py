"""Fixtures for the Pack store and the provisioning pipeline.

The world here is the same one the golden snapshots use - `tests/world.py` - because a
provisioning run that provisioned a *different* venture from the one the generators are
snapshot-tested against would be testing two systems that never meet.

Teardown is broad on purpose. A provisioning run writes grants, manifest rows, budgets,
curriculum submissions, sign-offs and gate results, and a run left behind by a failed
test makes the next test's `ux_run_active` insert fail with a unique-violation that
names nothing useful.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
import pytest_asyncio
import yaml

from broker import humans, packs
from broker.db import connection
from tests.conftest import wipe_venture
from tests.world import (
    PACK_PATH,
    build_world,
    certify_for_positions,
    dispatch_from_registry,
    teardown_world,
)

VENTURE = "greenstone"


def _wipe(conn: psycopg.Connection) -> None:
    """Everything belonging to this venture, via the shared ordered list.

    Hand-rolled before. Each phase adds another table that references a venture, and a
    fixture with its own list goes stale silently - the compliance suite hit exactly
    that when `provisioning_run` came to reference `business_pack`.
    """
    wipe_venture(conn, VENTURE)
    # The humans this suite creates. Dropped by accident when this function moved to
    # the shared list, which the unique index on `email` caught immediately - the
    # operator and signer fixtures collided on their second run.
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM office_human_role WHERE human_id IN "
            "(SELECT human_id FROM office_human WHERE email LIKE %s)",
            ("%@provisioning.invalid",),
        )
        cur.execute(
            "DELETE FROM office_human WHERE email LIKE %s", ("%@provisioning.invalid",)
        )
    conn.commit()


@pytest.fixture
def world(
    admin: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[psycopg.Connection]:
    """Bridged Forges dispatching their modules, instructions authored, roster certified.

    The adapters are part of this: Gate 2 runs V32, and a Pack whose modules were never
    resolved against a Forge has not been validated. Without them every run in this
    suite stops at Gate 2 with a NOT_RUN, which is the right verdict and the wrong
    subject - these tests are about Gates 3 through 11.
    """
    _wipe(admin)
    build_world(admin)
    certify_for_positions(admin)
    dispatch_from_registry(admin, monkeypatch)
    yield admin
    _wipe(admin)
    teardown_world(admin)


@pytest.fixture
def pack_yaml() -> str:
    return PACK_PATH.read_text(encoding="utf-8")


def amend_for_capacity(yaml_source: str) -> str:
    """The Greenstone Pack amended until Gate 4.5 is satisfiable.

    The real Pack **blocks at 4.5**, and correctly: the generated workflow routes 192
    compliance approvals a day at six minutes each against one officer's four coverage
    hours. That finding is real, it is asserted in its own test, and the amendment is
    the venture's to make - the validator names three ways out (raise a trust-tier
    ceiling, add reviewer coverage, cut scope) and deliberately does not offer a fourth.

    This helper takes the second one so that the gates *after* 4.5 can be exercised at
    all. It is a test fixture, not a recommendation, and the number it lands on - five
    compliance officers - is worth reading as the size of the real problem.
    """
    doc = yaml.safe_load(yaml_source)
    officers = [h for h in doc["human_capacity"] if h["role"] == "compliance_officer"]
    template = dict(officers[0])
    for i in range(4):
        extra = dict(template)
        extra["human_name"] = f"Reviewer {i + 1}"
        extra["backup_human"] = template["human_name"]
        extra["coverage_hours"] = 8
        doc["human_capacity"].append(extra)
    return yaml.safe_dump(doc, sort_keys=False)


@pytest_asyncio.fixture
async def feasible_pack(world, pack_yaml) -> packs.StoredPack:
    """A Pack that can reach Gate 12, so the gates past 4.5 can be tested."""
    async with connection() as conn:
        return await packs.store(
            conn, yaml_source=amend_for_capacity(pack_yaml), pack_version="1.1.0",
            authored_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )


@pytest_asyncio.fixture
async def stored_pack(world, pack_yaml) -> packs.StoredPack:
    """The Greenstone Pack, published as v1 - Gate 1's precondition."""
    async with connection() as conn:
        return await packs.store(
            conn, yaml_source=pack_yaml, pack_version="1.0.0",
            authored_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )


async def _make_human(name: str, role: str, venture: str | None = VENTURE) -> humans.Human:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name,
            email=f"{name.lower().replace(' ', '.')}@provisioning.invalid",
        )
        await humans.grant_role(
            conn, human_id=human_id, role=role, venture_id=venture,
            granted_by=uuid.UUID("00000000-0000-5000-8000-00000000aaaa"),
        )
        resolved = await humans.authenticate(conn, token)
    assert resolved is not None
    return resolved


@pytest_asyncio.fixture
async def operator(world) -> AsyncIterator[humans.Human]:
    """The venture operator who reviews at Gate 4."""
    yield await _make_human("Olive Operator", "venture_operator")


@pytest_asyncio.fixture
async def signer(world) -> AsyncIterator[humans.Human]:
    """A second named human for Gate 10.

    Distinct from `operator` because `gate_signoff_policy` is `distinct_humans` and
    separation of duties is checked, not assumed - the same person cannot both review
    the artifacts and sign them off.
    """
    yield await _make_human("Sam Signer", "venture_operator")
