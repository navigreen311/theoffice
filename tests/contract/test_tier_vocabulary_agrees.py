"""The tier names a generator can emit are exactly the ones the database accepts.

WHY THIS EXISTS, AND WHAT IT IS NOT ABOUT
=========================================

    `_TIER_RANK` in `generators/runtime_config.py` is the ladder the grant generator ranks
    tiers with, and `agent_forge_grant_trust_tier_check` is the CHECK constraint that decides
    what may be stored. **Two vocabularies for one concept, in two layers, with nothing
    comparing them.**

    Nothing is wrong with them today - both hold exactly `suggest`, `propose`, `auto_execute`.
    This is written for the day somebody adds a fourth.

WHY THE EXISTING SCHEMA TEST DOES NOT COVER IT
==============================================

    `tests/deployment/test_probes.py::test_the_expected_revision_matches_the_latest_migration`
    catches an app that expects an older schema than the migrations provide. It compares a
    revision NUMBER against a directory listing, and it caught exactly that on 13 September
    when 0038 shipped with `EXPECTED_SCHEMA_REVISION` still at `0037`.

    **It has no view into whether a Python constant and a CHECK constraint agree on a VALUE
    SET.** A fourth tier added to `_TIER_RANK` and not to the constraint leaves every revision
    number correct and every migration applied.

WHAT WOULD HAVE CAUGHT IT OTHERWISE: NOTHING
============================================

    A CHECK refusing a value is the last line, and it fires at WRITE time - at Gate 5, mid-run,
    on a venture being provisioned, after Gates 0 to 4.5 have reported healthy and a human has
    signed at Gate 4. The failure arrives as an `IntegrityConstraintViolation` from
    `runtime_config.apply`, which `_gate_5` catches only as `ValueError` - so it would surface
    as a raw database error inside a gate that had no other way to know.

    Entry 42 records the same shape from the other direction: 0038's trigger made a documented
    branch unreachable, and the only signal was CI going red. A control that can only report at
    write time is a control that reports late.

    So this compares them at test time, reading the constraint out of `pg_constraint` rather
    than restating it - a test that hard-coded the three names would pass while both sides
    drifted together, which is the failure it is meant to prevent.
"""

from __future__ import annotations

import re

import pytest

from generators.runtime_config import _TIER_RANK
from tests.conftest import requires_db

#: `db` is the registered marker; `requires_db` skips when no database is configured. Both,
#: matching every other contract test - the marker selects, the skip protects.
pytestmark = [requires_db, pytest.mark.db]

#: The constraint whose allowed array is the database's half of the vocabulary.
CONSTRAINT = "agent_forge_grant_trust_tier_check"


def _allowed_tiers(conn) -> set[str]:
    """The value set `CONSTRAINT` permits, read from the catalogue.

    Parsed from `pg_get_constraintdef` rather than a stored copy: the point is to read what
    the database will actually enforce, and a copy is the thing that drifts.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = 'agent_forge_grant'::regclass AND conname = %s",
            (CONSTRAINT,),
        )
        row = cur.fetchone()

    assert row is not None, (
        f"{CONSTRAINT} does not exist on agent_forge_grant. Either it was renamed - in which "
        "case this test's CONSTRAINT needs updating and the rename needs a reason - or the "
        "constraint was dropped, and the database no longer refuses an unknown tier at all."
    )
    return set(re.findall(r"'([a-z_]+)'::text", row[0]))


def test_the_generator_and_the_constraint_know_the_same_tiers(admin) -> None:
    """`_TIER_RANK` and the CHECK hold the same names, in both directions.

    Both directions matter and they fail differently:

      a tier the generator can emit and the database refuses -> a run dies at Gate 5, after a
      human has signed at Gate 4, with a raw constraint violation.

      a tier the database accepts and the generator never emits -> dead vocabulary. Harmless
      today and a trap later, because somebody will read the constraint as the list of tiers
      that exist and declare one in a Pack.
    """
    allowed = _allowed_tiers(admin)
    known = set(_TIER_RANK)

    assert known - allowed == set(), (
        f"generators can emit {sorted(known - allowed)}, which "
        f"{CONSTRAINT} refuses. A grant carrying one of these is written at Gate 5 and rejected "
        "by the database - mid-run, after the Gate 4 signature. Add the value to the constraint "
        "in a migration, or stop the generator producing it."
    )
    assert allowed - known == set(), (
        f"{CONSTRAINT} allows {sorted(allowed - known)}, which no generator can emit. Dead "
        "vocabulary: the constraint reads as the list of tiers that exist, so the next person "
        "to declare one in a Pack will find it accepted by the database and unknown to every "
        "generator."
    )


def test_the_ladder_is_ranked_without_ties() -> None:
    """Distinct ranks, because `_lower` picks by comparing them.

    A tie makes `_lower` return whichever argument came first, so a grant's tier would depend
    on argument order rather than on the ladder - the same class of defect as B24's
    first-in-the-list review time, which changed a gate outcome on YAML ordering.
    """
    assert len(set(_TIER_RANK.values())) == len(_TIER_RANK), (
        f"two tiers share a rank in _TIER_RANK: {_TIER_RANK}. `_lower` compares ranks, so a "
        "tie makes the result depend on which argument was passed first."
    )
