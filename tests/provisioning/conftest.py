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
    """The Greenstone Pack, unamended. **It no longer blocks at Gate 4.5.**

    WHAT THIS USED TO DO, AND WHY IT IS A NO-OP NOW

        It appended five compliance officers and one venture operator at eight hours each -
        six invented people - so that the gates AFTER 4.5 could be exercised at all. The
        real Pack routed 128 approvals a day at ten minutes against two coverage hours,
        1,280 minutes against 72, eighteen times over. The docstring said the number it
        landed on was "worth reading as the size of the real problem", and it was.

        **The problem was not the size of the reviewer roster.** Demand was
        `DEFAULT_DAILY_VOLUME_PER_HEADCOUNT = 8` per (step, holder, module): an
        unattributed constant multiplied by a workflow that emitted every module once per
        stage its position owned. Greenstone closes about one deal a week. The Pack now
        declares that rate, the workflow emits one step per module, and Deal Underwriter is
        pending, so the projection is 0.2 approvals a day against 36 review-minutes.

        Six invented reviewers were the cost of an unmeasured constant, carried in a test
        fixture for three weeks.

    WHY IT IS KEPT RATHER THAN DELETED

        Every call site reads `amend_for_capacity(pack_yaml)` and means "the Pack, made
        able to reach Gate 12". That is now the Pack. Deleting the function would rewrite
        five call sites to say nothing, and lose the one place this note can live.

        **If Greenstone ever blocks at 4.5 again, this is where the amendment goes back** -
        and whoever puts it there will read why it was removed first.
    """
    return yaml_source


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
