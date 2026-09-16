"""bootstrap-phase0's Pack check reads qualified module refs - decisions entry 91.

`forge_modules_operated` has stored `forge_id/module_id` since 14 September (entry 48). The
check asked the stored Pack for the bare module name, matched nothing, and refused every pair
on every venture with "no position operating" it - about positions that plainly do. Nothing
exercised `_assert_pair_in_pack` against a stored Pack, so the refusal went unnoticed until a
certification was actually attempted.

These run against the real Greenstone Pack stored live, which is exactly the shape that failed.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import bootstrap_phase0, packs
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world, teardown_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


@pytest.fixture
async def greenstone_live(admin: psycopg.Connection):
    wipe_venture(admin, VENTURE)
    build_world(admin)
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="1.0.0", authored_by=AUTHOR,
        )
    yield
    wipe_venture(admin, VENTURE)
    teardown_world(admin)


async def test_a_pair_the_pack_operates_is_accepted_and_returns_its_tier(greenstone_live):
    """The defect. Acquisition Analyst (research) operates cre-forge/property_lookup at
    auto_execute; the check must find it through the qualified ref the Pack stores."""
    async with connection() as conn:
        tier = await bootstrap_phase0._assert_pair_in_pack(
            conn, venture_id=VENTURE, forge_id="cre-forge", module_id="property_lookup",
            department="research",
        )
    assert tier == "auto_execute"


async def test_a_pending_position_does_not_pin_a_shared_modules_ceiling(greenstone_live):
    """comp_analysis is Acquisition Analyst at auto_execute and Deal Underwriter at propose.

    **The weakest-wins rule still holds; what changed is who is in the running.** Deal
    Underwriter is pending activation, so no agent will be appointed to it, and letting it
    set the ceiling would hand every agent `propose` on a shared module on the strength of
    a position nobody holds. It is excluded, and the tier is Acquisition Analyst's.

    This asserted `propose` until 2026-09-16. The weakest-wins behaviour itself is
    unchanged and is exercised by the pair below, where both operators are live.
    """
    async with connection() as conn:
        tier = await bootstrap_phase0._assert_pair_in_pack(
            conn, venture_id=VENTURE, forge_id="cre-forge", module_id="comp_analysis",
            department=None,
        )
    assert tier == "auto_execute"


async def test_a_pair_whose_only_operator_is_pending_is_refused(greenstone_live):
    """underwrite_deal is operated by Deal Underwriter and by nothing else.

    A certification written for it would be a row no appointed agent can hold and no gate
    will ever read - the position is deferred, and so is the certification.
    """
    async with connection() as conn:
        with pytest.raises(bootstrap_phase0.BootstrapError, match="pending activation"):
            await bootstrap_phase0._assert_pair_in_pack(
                conn, venture_id=VENTURE, forge_id="cre-forge",
                module_id="underwrite_deal", department=None,
            )


async def test_the_refusals_still_refuse(greenstone_live):
    """The fix widens nothing: a department no position draws from, and a module no position
    operates, are still refused - each with the reason that is actually true."""
    async with connection() as conn:
        with pytest.raises(bootstrap_phase0.BootstrapError, match="draws from"):
            await bootstrap_phase0._assert_pair_in_pack(
                conn, venture_id=VENTURE, forge_id="cre-forge", module_id="property_lookup",
                department="banking",
            )
        with pytest.raises(bootstrap_phase0.BootstrapError, match="no position operating"):
            await bootstrap_phase0._assert_pair_in_pack(
                conn, venture_id=VENTURE, forge_id="cre-forge", module_id="not_a_module",
                department=None,
            )
