"""B26 - the round trip nothing in the suite ever made, and B27 - what it says.

**Nothing read a published Pack back out of `business_pack` and parsed it.** All 1049
tests loaded Packs from `packs/*.yaml` on disk, so the suite asserted that the FILES
satisfy the schema and never once asked whether the ROWS do. That is why making
`provenance` required on `HumanCapacity` left twelve published rows unreadable - both
Packs on disk refused to load until every entry was filled, the forcing function was
scored CORRECT, and it was correct about git and silent about what was in force.

The property under test is not "store and live agree". A test that publishes through
today's `store()` and reads the row back in the same process proves only that, and it
would have passed on the provenance commit exactly as loudly as it passes now. **The
property is that a row written by an EARLIER BUILD still parses under this one**, and the
only way to assert it is to put such a row in the table without going through the writer
that would refuse it.

So the check lives in one helper, `read_back_and_parse`, and it is pointed at both kinds
of row:

  * at a row this build published - it must pass, and
  * at a row written before `provenance` existed - **it must fail.**

The second is not a scenario, it is the demonstration. It runs on every CI run, so the
round trip cannot quietly decay into the tautology B26 warned about: if somebody makes
`parse_only` lenient to "fix" an old row, `test_the_round_trip_fails_against_a_row_from_an
_earlier_build` goes red and says why.

The earlier-build row is CONSTRUCTED rather than hand-written - `packs/greenstone.yaml`
with the `provenance` keys removed, which is what the revision before the tightening
would have written and differs from today's file in nothing else. That is checkable, and
it is checked: the diagnosis must name `human_capacity[].provenance` and nothing else. A
hand-written old Pack could drift into a document the earlier revision would ALSO have
refused, and the test would then be demonstrating the wrong failure.
"""

from __future__ import annotations

import uuid

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
SEED = uuid.UUID("00000000-0000-5000-8000-0000000007a7")


def _wipe(conn: psycopg.Connection) -> None:
    wipe_venture(conn, VENTURE)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


@pytest.fixture
async def author(admin: psycopg.Connection):
    """A world with the venture registered, and a human allowed to publish into it."""
    _wipe(admin)
    build_world(admin)
    async with connection() as conn:
        human_id, _token = await humans.create_human(
            conn, display_name="Round-trip operator", email="roundtrip@packs.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id=None,
            granted_by=SEED,
        )
    yield human_id
    _wipe(admin)


@pytest.fixture
def pack_source() -> str:
    return PACK_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------- the check itself

async def read_back_and_parse(venture_id: str) -> packs.StoredPack:
    """The round trip, in one place so both directions exercise the same code.

    A fresh connection on purpose. The point of the check is that the bytes in the table
    are enough - not that some object this process is still holding is enough.
    """
    async with connection() as conn:
        stored = await packs.live(conn, venture_id)
    assert stored is not None, f"{venture_id} has no live Pack to read back"
    return stored


def as_written_before_provenance(yaml_source: str) -> str:
    """The same document as the revision before `provenance` existed would have written.

    Built by removing the key rather than by transcribing an old Pack, so the ONLY
    difference from `packs/greenstone.yaml` is the field the tightening added. The
    assertions below check that claim rather than trusting it.
    """
    raw = yaml.safe_load(yaml_source)
    for entry in raw["human_capacity"]:
        entry.pop("provenance", None)
    return yaml.safe_dump(raw, sort_keys=False)


def insert_as_an_earlier_build(
    conn: psycopg.Connection,
    *,
    venture_id: str,
    pack_version: str,
    yaml_source: str,
    authored_by: uuid.UUID,
) -> None:
    """Write a live row the way a build that predates the tightening wrote one.

    Deliberately NOT through `packs.store()`. `store()` is this build, and this build
    refuses the document - which is correct, and is exactly why the twelve stale rows
    could only have been created by a build that did not. A fixture that went through
    `store()` could not produce the row this test exists to meet.

    `parsed` is the raw mapping, which is what the earlier build's `model_dump` produced
    for a model that had no `provenance` field at all.
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


# ---------------------------------------------------------------- B26, the round trip

async def test_a_published_pack_reads_back_out_of_the_store_and_parses(
    author, pack_source
):
    """B26. Publish, read the stored row back through `live()`, parse it.

    This is the assertion that did not exist. Every other Pack test in the suite reads
    `packs/*.yaml`; this one reads `business_pack.yaml_source`, which is what a run
    reads and what `start_run` fails on when it is stale.
    """
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=pack_source, pack_version="7.0.0", authored_by=author
        )

    stored = await read_back_and_parse(VENTURE)

    assert stored.pack_version == "7.0.0"
    assert stored.yaml_source == pack_source, "the stored bytes are the published bytes"
    assert stored.pack.schema_version == 3
    assert stored.pack.human_capacity, "the parsed form came back, not just the text"
    # Every entry carries what this build requires. Stated positively so the test says
    # what the current revision IS, not merely that nothing raised.
    assert all(entry.provenance is not None for entry in stored.pack.human_capacity)


async def test_the_round_trip_also_holds_for_a_superseded_version(author, pack_source):
    """A run names the version it provisioned, and reads it back after it is replaced.

    The same property one step further out: a superseded row is still read and still
    parsed, so a tightening breaks the record of what was provisioned as surely as it
    breaks the current Pack. `live()` would not have found this one.
    """
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=pack_source, pack_version="7.1.0", authored_by=author
        )
        await packs.store(
            conn, yaml_source=pack_source, pack_version="7.1.1", authored_by=author
        )
        superseded = await packs.get_version(conn, VENTURE, "7.1.0")

    assert superseded is not None
    assert superseded.pack.schema_version == 3


async def test_the_round_trip_fails_against_a_row_from_an_earlier_build(
    admin, author, pack_source
):
    """**The demonstration B26 asked for, and the reason the test above means anything.**

    The row here is valid under the revision that wrote it and invalid under this one.
    `read_back_and_parse` - the very helper the passing test uses - raises against it.

    If this test ever goes green, the round trip has stopped testing anything: either
    `parse_only` was loosened, or the fixture stopped being an old row. Both are
    findings, and both should arrive here rather than at a run.
    """
    old_source = as_written_before_provenance(pack_source)
    assert "provenance" not in old_source, "the fixture must not still carry the field"
    assert "provenance" in pack_source, "and today's file must, or nothing was removed"

    insert_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="1.3.0",
        yaml_source=old_source, authored_by=author,
    )

    with pytest.raises(packs.PackStoreError) as caught:
        await read_back_and_parse(VENTURE)

    assert isinstance(caught.value, packs.PackPredatesTighteningError)


async def test_the_stale_row_is_still_status_live_and_still_says_schema_version_3(
    admin, author, pack_source
):
    """B26's sharpest half: the row is recorded as the one in force, and cannot be read.

    Asserted directly because it is what makes the honest message necessary. Nothing
    about the row looks wrong - `status` says `live`, `schema_version` says `3` - and
    both are true. The staleness is invisible in every column there is.
    """
    insert_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="1.3.0",
        yaml_source=as_written_before_provenance(pack_source), authored_by=author,
    )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT status, schema_version FROM business_pack "
            "WHERE venture_id = %s AND pack_version = '1.3.0'",
            (VENTURE,),
        )
        row = cur.fetchone()

    assert row == ("live", 3)
    with pytest.raises(packs.PackStoreError):
        await read_back_and_parse(VENTURE)


# ---------------------------------------------------------------- B27, the message

async def test_the_old_row_is_not_reported_as_not_a_schema_v3_business_pack(
    admin, author, pack_source
):
    """B27. The old sentence was false ABOUT THE DATA, and this pins that it is gone.

    The row IS schema-v3. Its `schema_version` column says 3, it was published as 3, and
    it was valid 3 on the day it was written. A reader who trusts *"not a schema-v3
    Business Pack"* goes and inspects `packs/greenstone.yaml`, which is fine, while the
    fault is a row nobody migrated.
    """
    insert_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="1.3.0",
        yaml_source=as_written_before_provenance(pack_source), authored_by=author,
    )

    with pytest.raises(packs.PackStoreError) as caught:
        await read_back_and_parse(VENTURE)
    message = str(caught.value)

    assert "not a schema-v3 Business Pack" not in message, message
    assert "schema-v3" in message, "it should still say what the document IS"


async def test_the_message_names_the_revision_stored_and_what_this_build_requires(
    admin, author, pack_source
):
    """The two halves B27 said were missing, plus where the reader should go instead.

    `schema_version` carries the coarse half - which schema. What was missing is which
    REVISION of it, and the answer is named by the tightening rather than by a version
    number nobody stamps: the field, the date it landed, and the blocking entry behind
    it are all things a reader can go and check.
    """
    insert_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="1.3.0",
        yaml_source=as_written_before_provenance(pack_source), authored_by=author,
    )

    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        await read_back_and_parse(VENTURE)
    message = str(caught.value)

    # Which row, so the reader does not have to guess which of twelve this is.
    assert "greenstone@1.3.0" in message
    # Which revision it was stored under, named by what it predates.
    assert "human_capacity[].provenance" in message
    assert "2026-09-08" in message
    assert "B21" in message
    # What the current revision requires.
    assert "basis" in message and "established_by" in message
    # And where to go, which is the migration and not the Pack.
    assert "B26" in message and "B28" in message
    assert "nothing wrong with it" in message


async def test_the_exception_type_separates_old_from_malformed(
    admin, author, pack_source
):
    """The distinction is a type, not a turn of phrase.

    A caller deciding whether to halt a run or to route somebody to a migration should
    not have to grep an error string to find out which it has. `predates` carries the
    machine-readable half of the same answer the message gives in words.
    """
    insert_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="1.3.0",
        yaml_source=as_written_before_provenance(pack_source), authored_by=author,
    )

    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        await read_back_and_parse(VENTURE)

    assert issubclass(packs.PackPredatesTighteningError, packs.PackStoreError), (
        "existing callers catch PackStoreError; narrowing the type must not narrow "
        "what they catch"
    )
    predates = caught.value.predates
    assert [t.field_path for t in predates] == [("human_capacity", "provenance")], (
        "the diagnosis must name provenance and NOTHING else - if it names more, "
        "stripping the field produced a document the earlier revision would also have "
        "refused, and this fixture is not an old row"
    )


async def test_a_genuinely_malformed_document_is_still_called_malformed(
    admin, author, pack_source
):
    """The other direction, which is the easy half to get wrong.

    Reporting a broken document as *merely old* would be B27 mirrored: the same false
    confidence, pointing the reader at a migration that will not help. A document with
    one error no tightening explains is malformed whatever else is true of it.
    """
    raw = yaml.safe_load(as_written_before_provenance(pack_source))
    # Not old. Broken: a required block that has been there since v3 was v3, removed.
    del raw["availability"]
    insert_as_an_earlier_build(
        admin, venture_id=VENTURE, pack_version="1.3.0",
        yaml_source=yaml.safe_dump(raw, sort_keys=False), authored_by=author,
    )

    with pytest.raises(packs.PackStoreError) as caught:
        await read_back_and_parse(VENTURE)

    assert not isinstance(caught.value, packs.PackPredatesTighteningError)
    assert "not a schema-v3 Business Pack" in str(caught.value)


def test_every_required_field_added_since_v3_has_a_ledger_entry():
    """The forcing function for the NEXT tightening, which is the part that generalises.

    B26's finding was that a required field forces what is in git and not what is in
    force. `V3_TIGHTENINGS` is the record that closes the gap - and a ledger somebody
    forgets to append to puts the next reader straight back into B27.

    Asserted the only way it can be from inside one build: the entries must name fields
    that actually exist on the model. A ledger entry for a field nobody requires is as
    misleading as a missing one, and this catches a rename.
    """
    from generators.pack import BusinessPack, HumanCapacity

    models = {"human_capacity": HumanCapacity}
    for tightening in packs.V3_TIGHTENINGS:
        head, *rest = tightening.field_path
        assert head in BusinessPack.model_fields, (
            f"{tightening.label} names `{head}`, which BusinessPack no longer has"
        )
        for part in rest:
            assert part in models[head].model_fields, (
                f"{tightening.label} names a field `{models[head].__name__}` no longer "
                "has - a renamed field leaves the ledger pointing at nothing, and an "
                "old row goes back to being reported as malformed"
            )
