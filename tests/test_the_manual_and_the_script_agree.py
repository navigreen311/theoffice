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
from tests.world import build_world, instruction_for, teardown_world

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
            "        'active', 'human', 'bearer_token')",
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
    # 1.3.0: `assign_contract`'s `correct_sequence`. Both items were preconditions on
    # CALLING, and the first exam ever to SHOW them handed the agent a call that had
    # already returned 200 - so it escalated where the key expects PROCEED. Measured on
    # run e8acac95: `happy_path` and `never_do_violation` both PASS -> FAIL, on both
    # agents, with `escalated_without_naming_the_prohibition` on every failing attempt.
    "1.3.0": "361036700ca289499000daa4ec23308eeaa714e1b2be3517bb71c48c3729e892",
    # 1.5.0 WITHDRAWS A REVISION, so its digest is 1.3.0's byte for byte. The text
    # never moved in this file: the 1.4.0 paragraph reached the live rows and was
    # never committed. Entry 180, and 1.4.0 is skipped rather than reused - a version
    # that was live and is now withdrawn must not name two different texts.
    "1.5.0": "361036700ca289499000daa4ec23308eeaa714e1b2be3517bb71c48c3729e892",
    # 1.7.0 WITHDRAWS THE SECOND REVISION, so its digest is 1.5.0's byte for byte -
    # and 1.5.0's was 1.3.0's, because that withdrew the first. The text in this file
    # has not moved since 1.3.0; both revisions reached the live rows from a worktree
    # and neither PR merged. Entry 186. 1.6.0 is skipped, not reused.
    "1.7.0": "361036700ca289499000daa4ec23308eeaa714e1b2be3517bb71c48c3729e892",
    # 1.8.0 IS THE FIRST TEXT CHANGE SINCE 1.3.0. Three versions sat on 1.3.0's digest
    # because two revisions were withdrawn; this one moves it. Entry 189, and the first
    # revision to `assign_contract` since entry 186 closed it without a measured reason.
    #
    # One sentence, in `retry_vs_escalate`, beside the one that caused it. The measured
    # reason: `partial_failure` records `sent = UNKNOWN` on all three seeds and varies
    # its act across PROCEED, REFUSE 2 and ESCALATE. The manual's only pairing of an
    # unknown with an act was the timeout sentence, which is correct and which the agent
    # generalised to a scenario that has an unknown and no failure.
    "1.8.0": "9c7fbd8681a6f6cab5cbca91c6dcd7bdbae6da174abc2bd00667621dc0500c5f",
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
    _drop_forge(admin, "newforge")
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



def _drop_forge(admin: psycopg.Connection, forge_id: str) -> None:
    """Remove a Forge and everything that points at it. Idempotent, both directions.

    Called on the way in as well as out, for the reason `_drop_author` gives: a test
    that dies between the insert and its teardown leaves the rows behind, and every
    later run then fails on a unique key - a failure about the harness, reported as a
    failure about instructions. That happened once while writing these two.
    """
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM forge_operating_instruction WHERE forge_id = %s", (forge_id,)
        )
        cur.execute(
            "DELETE FROM forge_module_registry WHERE forge_id = %s", (forge_id,)
        )
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    admin.commit()

# ------------------------------------------- every Forge, not just the one (entry 152)

async def test_capitalforge_has_a_deriver_and_it_is_the_script_s_own():
    """The registration itself, because forgetting it is the failure mode.

    `scripts/check_instructions_match.py` covered `cre-forge` alone from 21 September
    until entry 152: one import, singular constants. CapitalForge's eleven authored
    modules were compared by nothing, measured by hand once, and a manual edited without
    a re-run would have drifted under a green CI exactly as `buyer_match` did.

    Asserted as identity rather than presence: a deriver registered under the name and
    then replaced by something that returns `{}` would satisfy "capitalforge is in
    SOURCES" and check nothing.
    """
    from scripts import instruction_sources

    assert instruction_sources.capital.FORGE_ID in instruction_sources.SOURCES
    assert (
        instruction_sources.SOURCES[instruction_sources.capital.FORGE_ID]
        is instruction_sources.capitalforge
    )
    # And the deriver reaches the script's real derivation, not a copy of it.
    assert hasattr(instruction_sources.capital, "derive")


async def test_a_forge_whose_manuals_a_person_authored_must_have_a_script(world, admin):
    """**LOAD-BEARING.** The control that keeps the coverage true as Forges are added.

    A loop over `SOURCES` passes for ever on a Forge nobody registered. This asks the
    database which Forges carry human-authored instructions, and reports any that no
    deriver here can produce - so binding a Forge and forgetting to register it breaks
    the build instead of reporting a clean bridge.
    """
    from scripts.author_cre_forge_instructions import main as author

    await author()
    async with connection() as conn:
        assert await differences(conn) == []

    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, %s, 'https://example.invalid', '1.0.0', 'bearer', 'brokered',
                    'GREEN')
            """,
            ("newforge", "newforge"),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating,
               compliance_flags_implied, verified_at, verified_against,
               verification_method)
            VALUES ('newforge', 'do_a_thing', 'Do A Thing', 'key', TRUE, '{}',
                    now(), 'test', 'adapter_manifest')
            """
        )
        cur.execute(
            """
            INSERT INTO forge_operating_instruction
              (forge_id, module_id, instruction_version, forge_api_version,
               content, authored_by)
            VALUES ('newforge', 'do_a_thing', '1.0.0', '1.0.0', %s, %s)
            """,
            # A COMPLETE instruction, from the world's own helper: the schema requires
            # every section, and a half-built row would fail on the CHECK rather than
            # on the thing this test is about.
            (Json(instruction_for("do_a_thing")), AUTHOR_ID),
        )
    admin.commit()

    try:
        async with connection() as conn:
            found = await differences(conn)
        named = [d for d in found if d.forge_id == "newforge"]
        assert named, (
            "a Forge with a human-authored live instruction and no deriver was not "
            f"reported: {found}"
        )
        assert named[0].kind == "no authoring script"
    finally:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM forge_operating_instruction "
                        " WHERE forge_id = 'newforge'")
            cur.execute("DELETE FROM forge_module_registry "
                        " WHERE forge_id = 'newforge'")
            cur.execute("DELETE FROM forge_registry WHERE forge_id = 'newforge'")
        admin.commit()


async def test_a_fixture_authored_row_is_not_a_manual_anybody_must_script(world, admin):
    """The other side of the same rule, and why it is drawn at the author.

    A prepared test world inserts `forge_operating_instruction` rows for `simforge` and
    `voiceforge` so the gates have something to read. They are scaffolding. Demanding an
    authoring script for them would be demanding a script to maintain fixtures, and the
    comparator would fail on every database that had ever run the suite.

    **"A person authored it" is a declaration now, not a guess** - `office_human.origin`
    is set at creation since entry 151 - so this test and the one above rest on the same
    fact the same way.
    """
    _drop_forge(admin, "scaffoldforge")
    from scripts.author_cre_forge_instructions import main as author

    await author()

    fixture_author = uuid.UUID("9a11c0de-0000-4000-8000-00000000f1ce")
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, token_hash, "
            "                          status, origin, auth_method) "
            "VALUES (%s, 'Scaffolding', 'scaffold@world.invalid', %s, 'active', "
            "        'test_fixture', 'bearer_token')",
            (fixture_author, f"scaffold-token-{fixture_author.hex}"),
        )
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, %s, 'https://example.invalid', '1.0.0', 'bearer', 'brokered',
                    'GREEN')
            """,
            ("scaffoldforge", "scaffoldforge"),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating,
               compliance_flags_implied, verified_at, verified_against,
               verification_method)
            VALUES ('scaffoldforge', 'do_a_thing', 'Do A Thing', 'key', TRUE, '{}',
                    now(), 'test', 'adapter_manifest')
            """
        )
        cur.execute(
            """
            INSERT INTO forge_operating_instruction
              (forge_id, module_id, instruction_version, forge_api_version,
               content, authored_by)
            VALUES ('scaffoldforge', 'do_a_thing', '1.0.0', '1.0.0', %s, %s)
            """,
            (Json(instruction_for("do_a_thing")), fixture_author),
        )
    admin.commit()

    try:
        async with connection() as conn:
            found = await differences(conn)
        assert [d for d in found if d.forge_id == "scaffoldforge"] == [], (
            "a fixture-authored instruction row was treated as a manual needing a "
            f"script: {found}"
        )
    finally:
        with admin.cursor() as cur:
            cur.execute("DELETE FROM forge_operating_instruction "
                        " WHERE forge_id = 'scaffoldforge'")
            cur.execute("DELETE FROM forge_module_registry "
                        " WHERE forge_id = 'scaffoldforge'")
            cur.execute("DELETE FROM forge_registry WHERE forge_id = 'scaffoldforge'")
            cur.execute("DELETE FROM office_human WHERE human_id = %s",
                        (fixture_author,))
        admin.commit()
