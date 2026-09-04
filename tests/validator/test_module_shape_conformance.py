"""The registry's shape fields, compared against the Forge's — the check that did not run.

`verify_forge_modules --check` resolved module *ids* and stopped. It did compare
`is_mutating` and `idempotency_support` — in `_corrections`, on the write path, where a
disagreement was silently repaired and printed. `--check`, the CI form, took the other
branch and never compared them.

So a wrong value survived indefinitely if nobody ran the write path, and was erased
without a finding when somebody did. Neither state produces a report.

That field is not decoration. `broker/grants.py` selects `m.is_mutating` from
`forge_module_registry`, so V31 permits or refuses unattended `auto_execute` on the
registry copy, not on the manifest the adapter derives from its dispatch map.

`property_lookup` carried `is_mutating: TRUE` for months. `simforge/gate_result` carried
`is_mutating: TRUE, idempotency_support: 'key'` against a manifest saying `false` /
`natural`, and `--check` exited 0 on it on 4 September 2026.

These are the tests that did not exist.
"""

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest

from broker import forge_modules
from broker.db import connection
from scripts.verify_forge_modules import _corrections, _shape_mismatches
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

FORGE = "shapetest-forge"


def _answer(shapes: dict[str, forge_modules.DispatchShape]) -> forge_modules.ForgeModules:
    return forge_modules.ForgeModules(
        forge_id=FORGE,
        modules=frozenset(shapes),
        method="adapter_manifest",
        api_version="1.0.0",
        observed_at=datetime.now(UTC),
        shapes=shapes,
    )


@pytest.fixture
def registered(admin: psycopg.Connection):
    """One Forge, one module, recorded as a WRITER with key idempotency."""
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO forge_registry (forge_id, display_name, base_url, api_version, "
            "auth_model, credential_mode, health_status) "
            "VALUES (%s, %s, 'https://example.invalid', '1.0.0', 'bearer', 'brokered', "
            "'GREEN') ON CONFLICT (forge_id) DO NOTHING",
            (FORGE, "Shape Test Forge"),
        )
        cur.execute(
            "INSERT INTO forge_module_registry "
            "(forge_id, module_id, module_name, is_mutating, idempotency_support) "
            "VALUES (%s, 'a_read', 'A read', TRUE, 'key') "
            "ON CONFLICT (forge_id, module_id) DO UPDATE "
            "SET is_mutating = TRUE, idempotency_support = 'key'",
            (FORGE,),
        )
    admin.commit()
    yield
    with admin.cursor() as cur:
        cur.execute("DELETE FROM forge_module_registry WHERE forge_id = %s", (FORGE,))
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (FORGE,))
    admin.commit()


async def test_a_row_that_says_writer_over_a_read_is_reported(registered) -> None:
    """The finding itself.

    The adapter derives `is_mutating` from the binding site; the registry row is
    somebody's word. When they disagree, the row is what The Office spends.
    """
    answer = _answer({
        "a_read": forge_modules.DispatchShape(
            is_mutating=False, idempotency_support="natural"
        )
    })

    async with connection() as conn:
        found = await _shape_mismatches(conn, FORGE, {"a_read"}, answer)

    assert len(found) == 1
    assert "a_read" in found[0]
    assert "is_mutating registry=True forge=False" in found[0]
    assert "idempotency_support registry='key' forge='natural'" in found[0]


async def test_reporting_a_mismatch_writes_nothing(registered, admin) -> None:
    """`--check` is the CI form and must not repair what it finds.

    A check that fixes the thing it is checking cannot fail twice, and the second run
    is the one that would have told somebody the first was not an accident.
    """
    answer = _answer({
        "a_read": forge_modules.DispatchShape(
            is_mutating=False, idempotency_support="natural"
        )
    })

    async with connection() as conn:
        await _shape_mismatches(conn, FORGE, {"a_read"}, answer)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT is_mutating, idempotency_support FROM forge_module_registry "
            "WHERE forge_id = %s AND module_id = 'a_read'",
            (FORGE,),
        )
        assert cur.fetchone() == (True, "key"), "the report path wrote to the registry"


async def test_an_agreeing_row_reports_nothing(registered) -> None:
    answer = _answer({
        "a_read": forge_modules.DispatchShape(is_mutating=True, idempotency_support="key")
    })

    async with connection() as conn:
        assert await _shape_mismatches(conn, FORGE, {"a_read"}, answer) == []


async def test_an_adapter_that_states_no_shapes_reports_nothing(registered) -> None:
    """`shapes is None` means the question was not answered — an older manifest that
    returns a list of names, or the probe. Not "no shapes", and not a mismatch: a row
    is not wrong because nobody asked."""
    silent = forge_modules.ForgeModules(
        forge_id=FORGE,
        modules=frozenset({"a_read"}),
        method="adapter_manifest",
        api_version="1.0.0",
        observed_at=datetime.now(UTC),
        shapes=None,
    )

    async with connection() as conn:
        assert await _shape_mismatches(conn, FORGE, {"a_read"}, silent) == []


async def test_a_module_the_manifest_omits_is_not_a_mismatch(registered) -> None:
    """A module in the registry and absent from the manifest is DRIFT, and drift is
    already reported. Counting it here too would report one fact twice under two
    names, and the more serious name would stop meaning what it says."""
    answer = _answer({
        "something_else": forge_modules.DispatchShape(
            is_mutating=False, idempotency_support="natural"
        )
    })

    async with connection() as conn:
        assert await _shape_mismatches(conn, FORGE, {"a_read"}, answer) == []


async def test_the_write_path_still_corrects(registered, admin) -> None:
    """The other half, unchanged and asserted so the split stays honest.

    Reporting on `--check` does not remove the repair on the write path. What changed
    is that the repair is no longer the ONLY thing that ever looks.
    """
    answer = _answer({
        "a_read": forge_modules.DispatchShape(
            is_mutating=False, idempotency_support="natural"
        )
    })

    async with connection() as conn:
        changed = await _corrections(conn, FORGE, {"a_read"}, answer)
        await conn.commit()

    assert len(changed) == 1
    with admin.cursor() as cur:
        cur.execute(
            "SELECT is_mutating, idempotency_support FROM forge_module_registry "
            "WHERE forge_id = %s AND module_id = 'a_read'",
            (FORGE,),
        )
        assert cur.fetchone() == (False, "natural")
