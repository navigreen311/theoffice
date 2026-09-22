"""A manual edited without a version bump never reaches a live instruction.

RULED 21 SEPTEMBER 2026 (entry 148)
===================================

    *"The live operating instructions must match the authoring script. CI fails when
    they differ. Measured: `buyer_match` carried a correction entry 137 proved necessary
    until 21 September, because nobody ran the script, and every exam in between was set
    against the false text."*

WHAT ACTUALLY FAILED, AND WHAT A TEST CAN HOLD
==============================================

    Two things went wrong and they need different controls.

    **The edit never landed.** `author_cre_forge_instructions.main` skips a module
    already live at `VERSION`, the correction was merged without bumping it, and the
    script became a no-op for the one module it had been changed for. That is caught
    here, in CI, by `test_the_manual_digest_matches_its_version`: the content is
    fingerprinted against the version it belongs to, so editing a manual without moving
    `VERSION` fails the build.

    **Nobody ran the script.** No test can catch that - CI's database is empty, so the
    manuals always match whatever the test itself authored. `scripts/
    check_instructions_match.py` is what answers it, against a database that has been
    run against, and what CI holds is that the comparator WORKS: it is driven both ways
    below, once on a matching database and once on a deliberately altered one.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_the_comparator_finds_a_difference_somebody_made`. A comparator that returned
    an empty list unconditionally would satisfy the matching case, pass CI for ever, and
    report a clean bridge on the day a manual went stale - which is the whole of the
    20-September failure with a green tick on it.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import psycopg
import pytest
from psycopg.types.json import Json

from broker.db import connection
from scripts.author_cre_forge_instructions import FORGE, MANUALS, VERSION
from scripts.check_instructions_match import differences
from tests.conftest import requires_db
from tests.world import build_world, teardown_world

pytestmark = [requires_db, pytest.mark.db]

#: Fixed so teardown can find it whichever way a test ended.
AUTHOR_ID = uuid.UUID("9a11c0de-0000-4000-8000-00000000a417")


@pytest.fixture
def world(admin: psycopg.Connection):
    """The bridged Forges and a real human, so `attributable_actor` can resolve one.

    The authoring script records who authored each manual and refuses to attribute that
    to a fixture, so this needs the world rather than an empty database.
    """
    build_world(admin)
    _drop_author(admin)
    # A REAL ACCOUNT, because the script refuses to attribute a manual to a fixture:
    # "an audit entry signed by a fixture names nobody who can answer for it". The test
    # needs one to exist, and `origin = 'human'` is the whole of what makes it real.
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, token_hash, "
            "                          status, origin, auth_method) "
            "VALUES (%s, 'Instruction Author', 'author@manual.invalid', %s, "
            "        'active', 'human', 'sso_mfa')",
            (AUTHOR_ID, "not-a-real-token-hash-" + AUTHOR_ID.hex),
        )
        cur.execute(
            "INSERT INTO office_human_role (human_id, role, venture_id, granted_by) "
            "VALUES (%s, 'ivan', NULL, %s)",
            (AUTHOR_ID, AUTHOR_ID),
        )
    admin.commit()
    yield admin
    _drop_author(admin)
    teardown_world(admin)


def _drop_author(admin: psycopg.Connection) -> None:
    """Idempotent, and called on the way in as well as out.

    A test that dies between the insert and the teardown would otherwise leave the row
    behind and every later test in this file would fail on the primary key - a failure
    about the harness, reported as a failure about instructions.
    """
    with admin.cursor() as cur:
        cur.execute("DELETE FROM office_human_role WHERE human_id = %s", (AUTHOR_ID,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (AUTHOR_ID,))
    admin.commit()

#: The fingerprint of `MANUALS` at `VERSION`, recorded so a change to either without the
#: other fails the build.
#:
#: **Update it in the same commit as the manual, and bump `VERSION` with it.** That is
#: the whole instruction: the pairing is the control, and a digest updated alone would
#: record an edit that the script will still skip.
MANUAL_DIGEST = {
    "1.2.0": "865032e7214b22dc60462ed12127eedd5c664918c584ddee55a369b0f044a8dd",
}


def _digest() -> str:
    """Canonical JSON over every manual. Hashed HERE and nowhere else.

    Not `instruction_hash`, which is a database function this side must not reimplement
    (see `check_instructions_match`'s docstring). This digest never leaves this file and
    is compared only with itself, so there is no second spelling of anything.
    """
    canonical = json.dumps(MANUALS, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_the_manual_digest_matches_its_version():
    """**The test that catches what happened on 20 September.**

    `buyer_match`'s `correct_sequence` was corrected in the script and merged. `VERSION`
    stayed at 1.1.0, `main` skips a module already live at `VERSION`, and the correction
    was a no-op for as long as nobody noticed. The live manual kept a claim entry 137 had
    proved false, and every exam in between was bound to it.

    So the content is pinned against the version that carries it. Edit a manual and this
    fails until `VERSION` moves and the digest is re-recorded - and a moved `VERSION` is
    a version the script cannot skip.
    """
    assert VERSION in MANUAL_DIGEST, (
        f"VERSION is {VERSION} and MANUAL_DIGEST has no entry for it. If the manuals "
        "changed, record the new digest here in the same commit; if they did not, the "
        "version should not have moved."
    )
    assert _digest() == MANUAL_DIGEST[VERSION], (
        f"the manuals have changed and VERSION is still {VERSION}. "
        "`author_cre_forge_instructions.main` SKIPS a module already live at this "
        "version, so this edit would never reach a live instruction - which is exactly "
        "what happened to buyer_match between 20 and 21 September (entry 148). Bump "
        f"VERSION and record the new digest: {_digest()}"
    )


async def test_the_comparator_says_so_when_they_match(world, admin):
    """The positive case, so nothing below is satisfied by reporting drift always."""
    from scripts.author_cre_forge_instructions import main as author

    await author()
    async with connection() as conn:
        assert await differences(conn) == []


async def test_the_comparator_finds_a_difference_somebody_made(world, admin):
    """**Load-bearing.** A comparator that always returned nothing would pass every
    other test here and report a clean bridge on the day a manual went stale.

    The live row is altered rather than the script, because that is the direction the
    failure came from: a database that stopped matching a file nobody re-ran.
    """
    from scripts.author_cre_forge_instructions import main as author

    await author()
    # The whole document is rewritten rather than one key patched: `content` is `json`
    # and not `jsonb`, so there is no `jsonb_set` to reach for.
    altered = dict(MANUALS["buyer_match"], what_it_does="something nobody authored")
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_operating_instruction SET content = %s "
            " WHERE forge_id = %s AND module_id = 'buyer_match' "
            "   AND superseded_at IS NULL",
            (Json(altered), FORGE),
        )
    admin.commit()

    async with connection() as conn:
        found = await differences(conn)

    assert found, "the live manual was altered and the comparator saw nothing"
    named = [d for d in found if d.module_id == "buyer_match"]
    assert named, f"the difference was not attributed to buyer_match: {found}"
    assert any("what_it_does" in d.kind for d in named), (
        f"the field that differs is not named: {[d.kind for d in named]}"
    )
    assert not [d for d in found if d.module_id != "buyer_match"], (
        "modules nobody touched are reported as differing"
    )


async def test_a_module_the_script_authors_and_nothing_holds_is_reported(world, admin):
    """The other direction: the script authors it and the database has no live row.

    Kept apart from a field difference because the response differs - this is a script
    that has never been run against this database, not one that has drifted from it.
    """
    from scripts.author_cre_forge_instructions import main as author

    await author()
    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_operating_instruction SET superseded_at = now() "
            " WHERE forge_id = %s AND module_id = 'comp_analysis'",
            (FORGE,),
        )
    admin.commit()

    async with connection() as conn:
        found = await differences(conn)

    assert [d.kind for d in found if d.module_id == "comp_analysis"] == ["not live"]
