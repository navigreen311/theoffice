"""`forge_module_rows.apply()` against a real table, because the row is the deliverable.

A generator that produces a correct dataclass and cannot write it is a generator whose
output nobody can spend. `broker/grants.py` reads `is_mutating` out of this table and V31
decides unattended `auto_execute` on it, so the assertions below are about the row as
Postgres holds it - the CHECK constraints, the `verification_is_dated` constraint, and
the values the two consumers read.
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from adapters.funnelforge.modules import MODULES, manifest
from generators import forge_module_rows
from tests.conftest import requires_db

pytestmark = requires_db

FORGE = "funnelforge-rowtest"
API_VERSION = "1.0.0"


@pytest.fixture
def registered(admin: psycopg.Connection):
    """`forge_module_registry.forge_id` references `forge_registry`, so the Forge first."""
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'FunnelForge row test', 'https://example.invalid', %s,
                    'bearer', 'brokered', 'GREEN')
            """,
            (FORGE, API_VERSION),
        )
    admin.commit()
    yield FORGE
    with admin.cursor() as cur:
        cur.execute("DELETE FROM forge_module_registry WHERE forge_id = %s", (FORGE,))
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (FORGE,))
    admin.commit()


async def _apply(dsn: str, declared: set[str]) -> list[str]:
    generated = forge_module_rows.generate(FORGE, API_VERSION, manifest(), declared)
    assert generated.blocked is None
    async with await psycopg.AsyncConnection.connect(dsn) as conn:
        written = await forge_module_rows.apply(conn, generated, confirmed=True)
        await conn.commit()
    return written


async def test_the_rows_land_and_carry_adapter_manifest_provenance(
    registered, admin_dsn, admin
):
    """`verification_method` is what V31 will not PASS a `hand` row on.

    A generated row is not a third grade between evidence and a claim: the shape was read
    from a dispatch map, so it is stamped exactly as `scripts/verify_forge_modules.py`
    would stamp it, and `verified_at` is set because the `verification_is_dated`
    constraint refuses an undated non-`hand` row - a verification with no date is a claim
    that ages into a lie.
    """
    written = await _apply(admin_dsn, set(MODULES))
    assert len(written) == len(MODULES)

    with admin.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT module_id, is_mutating, idempotency_support, verification_method, "
            "       verified_at, verified_against, api_version_introduced "
            "FROM forge_module_registry WHERE forge_id = %s ORDER BY module_id",
            (registered,),
        )
        rows = cur.fetchall()

    assert [r["module_id"] for r in rows] == sorted(MODULES)
    for row in rows:
        binding = MODULES[row["module_id"]]
        assert row["is_mutating"] == binding.is_mutating
        assert row["idempotency_support"] == binding.idempotency_support
        assert row["verification_method"] == "adapter_manifest"
        assert row["verified_at"] is not None
        assert row["verified_against"] == f"{FORGE}@{API_VERSION} via adapter_manifest"
        assert row["api_version_introduced"] == API_VERSION


async def test_applying_twice_leaves_the_same_state(registered, admin_dsn, admin):
    """Idempotent by construction: the primary key is `(forge_id, module_id)` and every
    value is derived from the manifest, so a second run recomputes what is already there.
    """
    await _apply(admin_dsn, set(MODULES))
    await _apply(admin_dsn, set(MODULES))

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM forge_module_registry WHERE forge_id = %s",
            (registered,),
        )
        (count,) = cur.fetchone()
    assert count == len(MODULES)


async def test_a_module_the_pack_stops_declaring_is_not_deleted(
    registered, admin_dsn, admin
):
    """`agent_forge_grant` has a foreign key into this table.

    Removing the row a live grant points at is not a thing a generator does as a side
    effect of a Pack edit. `scripts/verify_forge_modules.py` says the same about a module
    a Forge has stopped dispatching: reported, not removed - somebody revokes the grant,
    deliberately.
    """
    await _apply(admin_dsn, set(MODULES))
    await _apply(admin_dsn, set(MODULES) - {"capture_contact"})

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM forge_module_registry "
            "WHERE forge_id = %s AND module_id = 'capture_contact'",
            (registered,),
        )
        (count,) = cur.fetchone()
    assert count == 1
