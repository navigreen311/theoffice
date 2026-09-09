"""B31 - a rename is one change that arrives as two errors, and the pair must be read together.

P-07 closed B27 with a ledger of **tightenings** and a guard whose docstring said why it
refused to look further:

    "Only an absent field can be explained by 'this predates the field'. A wrong type, a
    refused extra key or a failed validator is a document that disagrees with the schema,
    not one that is older than it."

**That is right for every change the ledger could describe, and wrong for a rename.**
P-08 renamed `max_daily_approvals` to `advisory_daily_approval_ceiling`, and a stale row
then fails twice per entry - measured on `burkham-wickmont@0.6.0`, the Pack a halted
`provisioning_run` is pinned to:

    missing          human_capacity.0.advisory_daily_approval_ceiling
    extra_forbidden  human_capacity.0.max_daily_approvals
    missing          human_capacity.1.advisory_daily_approval_ceiling
    extra_forbidden  human_capacity.1.max_daily_approvals

The `extra_forbidden` disqualified the whole diagnosis, so the row fell back to *"not a
schema-v3 Business Pack"* - **the exact sentence B27 exists to eliminate, on the exact
class of row it was built for.**

## What these tests are actually protecting

Loosening a guard is easy and it is the wrong half of the job. **The guard's value is that
an unexplained error still disqualifies**, and every widening of it is a chance to lose
that silently, because the widened path passes and nothing asks what it no longer refuses.

So the disqualifying cases outnumber the explaining ones here, deliberately, and they are
not variations on one theme - each is a different way a document can carry a refused key
without being an unmigrated row:

  * a refused key that is not in the ledger at all;
  * a refused key that IS the old half of a ledgered rename, sitting next to a document
    that is otherwise current;
  * **both** names present in the same entry;
  * **neither** name present;
  * the two halves at different list indexes.

Only the first of those is what anyone pictures when they hear "a stray key". The rest
are why the pair is matched on the full location including the index, rather than on the
field path.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

import psycopg
import psycopg.types.json
import pytest
import yaml

from broker import humans, packs
from broker.db import connection
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"
SEED = uuid.UUID("00000000-0000-5000-8000-00000000b31b")

#: The field P-08 renamed, and what it was called before. Read off the ledger rather than
#: retyped, so a test that says "the rename" cannot drift from the rename the code knows.
RENAME = packs.V3_RENAMES[0]
NEW_NAME = RENAME.field_path[-1]
OLD_NAME = RENAME.previous_name


def _wipe(conn: psycopg.Connection) -> None:
    wipe_venture(conn, VENTURE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture
async def author(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)
    async with connection() as conn:
        human_id, _token = await humans.create_human(
            conn, display_name="Rename operator", email="b31@packs.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id=None,
            granted_by=SEED,
        )
    yield human_id
    _wipe(admin)


@pytest.fixture
def current() -> dict[str, Any]:
    """Today's Pack, parsed. Every fixture below is this document, minus one migration."""
    return yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))


def dump(raw: dict[str, Any]) -> str:
    return yaml.safe_dump(raw, sort_keys=False)


def as_written_before_the_rename(raw: dict[str, Any]) -> dict[str, Any]:
    """Today's Pack as the revision before the rename would have written it.

    Constructed by moving the value back under its old key - not by transcribing an old
    Pack - so the only difference from the current file is the rename itself. The
    assertions check that claim rather than trusting it: the diagnosis must name this
    one change and nothing else.
    """
    out = copy.deepcopy(raw)
    for entry in out["human_capacity"]:
        entry[OLD_NAME] = entry.pop(NEW_NAME)
    return out


def store_as_an_earlier_build(
    conn: psycopg.Connection,
    *,
    venture_id: str,
    pack_version: str,
    yaml_source: str,
    authored_by: uuid.UUID,
) -> None:
    """A live row written the way a build predating the change wrote one.

    Not through `packs.store()`, which is this build and correctly refuses the document -
    which is exactly why such rows can only have been written by a build that did not.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE business_pack SET status = 'superseded', superseded_at = now() "
            "WHERE venture_id = %s AND status = 'live'",
            (venture_id,),
        )
        cur.execute(
            """
            INSERT INTO business_pack
              (venture_id, pack_version, schema_version, yaml_source, parsed,
               content_hash, authored_by, status)
            VALUES (%s, %s, 3, %s, %s, '', %s, 'live')
            """,
            (
                venture_id, pack_version, yaml_source,
                psycopg.types.json.Jsonb(yaml.safe_load(yaml_source)), authored_by,
            ),
        )
    conn.commit()


# ================================================== the ledger entry actually fires

def test_the_rename_is_recognised_as_one_change_not_two_errors(current):
    """B31's headline. The pair is read together, and the row is called what it is."""
    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        packs.parse_only(
            dump(as_written_before_the_rename(current)),
            stored_as="burkham-wickmont@0.6.0",
        )

    predates = caught.value.predates
    assert len(predates) == 1, (
        "one rename is ONE change. Two entries in `predates` would mean the pair was "
        "counted as a missing field plus a refused key, which is the bug."
    )
    assert isinstance(predates[0], packs.SchemaRename)
    assert predates[0].field_path == RENAME.field_path


def test_the_ledger_entry_is_not_decoration(current):
    """B31's real finding, pinned: an entry that can never fire is worse than no entry.

    The coordinator added the rename to the ledger while the guard still rejected on the
    first `extra_forbidden`, and it changed nothing - the entry was true and unreachable.
    A true statement the code can never act on is B23's class, which is what the ledger
    was built to remove.

    This asserts reachability rather than presence: the diagnosis must come back holding
    **this exact ledger object**, so an entry nothing can reach fails here.
    """
    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        packs.parse_only(dump(as_written_before_the_rename(current)))

    assert RENAME in caught.value.predates


def test_the_message_says_renamed_from_and_not_field_required(current):
    """*This used to be called that* is the sentence a reader needs to act.

    "Field required" would be true and useless: it describes the shape of the error, not
    what happened to the document, and it sends the reader looking for a value that is
    already there under another name.
    """
    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        packs.parse_only(
            dump(as_written_before_the_rename(current)),
            stored_as="burkham-wickmont@0.6.0",
        )
    message = str(caught.value)

    assert "not a schema-v3 Business Pack" not in message
    assert "renamed from" in message
    assert OLD_NAME in message and NEW_NAME in message
    assert RENAME.blocking_entry in message and RENAME.landed in message
    assert "burkham-wickmont@0.6.0" in message
    assert "nothing wrong with it" in message, "the document is fine; the row is not"
    assert "B31" in message, "the reader should reach the item, not guess"


def test_a_rename_and_a_tightening_are_reported_together_oldest_first(current):
    """Two changes, one document. Ledger order, not the order pydantic reported them in.

    `predates` says "oldest first", and a document that predates both must not be told
    about them in whatever sequence pydantic emitted its errors - that ordering is an
    implementation detail of the validator, and letting it through would make the
    attribute's own docstring assert more than the code does.
    """
    raw = as_written_before_the_rename(current)
    for entry in raw["human_capacity"]:
        entry.pop("provenance", None)

    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    predates = caught.value.predates
    assert [type(c).__name__ for c in predates] == ["SchemaTightening", "SchemaRename"]
    assert [c.landed for c in predates] == sorted(c.landed for c in predates)


# ================================================== the guard keeps its teeth

def test_a_refused_key_that_is_not_a_ledgered_rename_still_disqualifies(current):
    """**The guard's whole value, and the thing a widening is most likely to cost.**

    An unknown key is a document disagreeing with the schema. Nothing about it is old,
    and calling it old would send the reader to a migration that cannot help - B27's
    false confidence pointing the other way.
    """
    raw = copy.deepcopy(current)
    raw["human_capacity"][0]["some_unknown_key"] = 3

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)
    assert "not a schema-v3 Business Pack" in str(caught.value)


def test_an_unknown_key_alongside_a_real_rename_still_disqualifies(current):
    """The case a per-error widening would let through, and the reason to test it.

    The rename half is genuinely explainable. **That must not buy the unknown key a
    pass.** A diagnosis is all-or-nothing: one error the ledger cannot account for and
    the document is malformed, whatever else is true of it.
    """
    raw = as_written_before_the_rename(current)
    raw["human_capacity"][0]["some_unknown_key"] = 3

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw), stored_as="burkham-wickmont@0.6.0")

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)


def test_a_document_carrying_both_names_is_malformed_not_old(current):
    """Both names in one entry is not a row that predates the rename.

    It is a row somebody hand-edited, or two migrations that half-ran. The new name is
    present, so there is no `missing` half - only a refused key - and the pair rule
    refuses it. **This is the case that decides index-aware pairing:** a rule that
    matched the old name against a `missing` anywhere in the document would call this
    old and be wrong.
    """
    raw = copy.deepcopy(current)
    for entry in raw["human_capacity"]:
        entry[OLD_NAME] = entry[NEW_NAME]

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)


def test_a_document_carrying_neither_name_is_malformed_not_old(current):
    """The other half of the pair rule, and the one that is easy to leave out.

    A row with no value under either name never satisfied any revision of v3 - the field
    had no default before the rename and has none after. `missing` alone is not evidence
    of age here; it is evidence the value was never there.
    """
    raw = copy.deepcopy(current)
    for entry in raw["human_capacity"]:
        entry.pop(NEW_NAME)

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)


def test_halves_at_different_entries_do_not_pair(current):
    """Why the match is on the full location, list index included.

    Entry 0 carries the old name; entry 1 carries neither. Counted across the document
    there is one `missing` and one `extra_forbidden` and they look like a pair. They are
    not: no single entry is an unmigrated entry, and the document is malformed.
    """
    raw = copy.deepcopy(current)
    raw["human_capacity"][0][OLD_NAME] = raw["human_capacity"][0].pop(NEW_NAME)
    raw["human_capacity"][1].pop(NEW_NAME)

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)


def test_a_partially_migrated_row_is_still_old(current):
    """The mirror of the test above, so "index-aware" does not quietly become "all or none".

    One entry migrated, one not. **Every** entry that fails does so as a complete pair,
    so the document genuinely predates the rename - it was simply half-fixed by hand.
    Refusing this one would be the guard overshooting.
    """
    raw = copy.deepcopy(current)
    raw["human_capacity"][0][OLD_NAME] = raw["human_capacity"][0].pop(NEW_NAME)

    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    assert "1 entry" in str(caught.value), "one entry stale, and it should say one"


def test_a_wrong_type_still_disqualifies(current):
    """Neither a missing field nor a refused key. Unchanged, and asserted so it stays."""
    raw = copy.deepcopy(current)
    raw["human_capacity"][0][NEW_NAME] = "lots"

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw), stored_as="greenstone@1.3.0")

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)


def test_the_current_pack_still_parses(current):
    """The control. Without it every assertion above could pass on a broken parser."""
    parsed = packs.parse_only(dump(current))
    assert all(
        getattr(entry, NEW_NAME) is not None for entry in parsed.human_capacity
    )


# ================================================== through the store, as a run reads it

async def test_get_version_on_a_pinned_stale_row_names_the_rename(admin, author, current):
    """B31's measured symptom: a halted run cannot read the Pack version it is pinned to.

    `provisioning_run def65e4f` is pinned to `burkham-wickmont@0.6.0`. This reproduces
    that row's shape in the test database - **the real row is left exactly as it is, it
    is evidence** - and asserts the read now says what is true of it.
    """
    store_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="0.6.0",
        yaml_source=dump(as_written_before_the_rename(current)), authored_by=author,
    )

    async with connection() as conn:
        with pytest.raises(packs.PackPredatesTighteningError) as caught:
            await packs.get_version(conn, VENTURE, "0.6.0")

    message = str(caught.value)
    assert f"{VENTURE}@0.6.0" in message
    assert "renamed from" in message
    assert "not a schema-v3 Business Pack" not in message


async def test_live_on_a_stale_row_names_the_rename_too(admin, author, current):
    """`live()` and `get_version()` take the same path, and it is asserted rather than assumed."""
    store_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="0.6.0",
        yaml_source=dump(as_written_before_the_rename(current)), authored_by=author,
    )

    async with connection() as conn:
        with pytest.raises(packs.PackPredatesTighteningError):
            await packs.live(conn, VENTURE)


# ================================================== the ledger cannot rot silently

def test_every_rename_names_a_field_that_exists_and_an_old_name_that_does_not():
    """A rename entry has to be a rename, and the model is the only place that can say so.

    Two ways the entry goes stale, both silent:

      * the NEW name stops existing - the entry points at nothing and an old row goes
        back to being called malformed;
      * the OLD name comes BACK as a real field - then `extra_forbidden` can no longer
        be produced for it, the pair can never form, and the entry is decoration again.

    The second is the one nobody would think to check, which is why it is here.
    """
    from generators.pack import BusinessPack, HumanCapacity

    owners = {"human_capacity": HumanCapacity}
    for rename in packs.V3_RENAMES:
        head, *rest = rename.field_path
        assert head in BusinessPack.model_fields, (
            f"{rename.label} names `{head}`, which BusinessPack no longer has"
        )
        owner = owners[head]
        assert rest[-1] in owner.model_fields, (
            f"{rename.label} names a field `{owner.__name__}` no longer has - the entry "
            "points at nothing and a stale row is malformed again"
        )
        assert rename.previous_name not in owner.model_fields, (
            f"`{rename.previous_name}` is a REAL field on {owner.__name__} again, so it "
            "can never be reported as an extra key. The pair can never form and this "
            "ledger entry can never fire - B31's finding, in its other direction"
        )


def test_the_two_ledgers_partition_the_one_ledger():
    """`V3_TIGHTENINGS` still means exactly what its name says, and nothing is dropped.

    It was a public name before this change and it keeps its old meaning rather than
    quietly widening to include renames - a name that grows a new meaning under an
    unchanged spelling is how the callers of one become the callers of the other.
    """
    assert set(packs.V3_TIGHTENINGS) | set(packs.V3_RENAMES) == set(
        packs.V3_SCHEMA_CHANGES
    )
    assert not set(packs.V3_TIGHTENINGS) & set(packs.V3_RENAMES)
    assert all(isinstance(t, packs.SchemaTightening) for t in packs.V3_TIGHTENINGS)
    assert all(isinstance(r, packs.SchemaRename) for r in packs.V3_RENAMES)
