"""P1-P2 - the Pack store.

Two properties carry the rest of the increment. **The hash is computed here**, because
a Gate 10 signature binds to it and a caller who could choose it could sign one Pack and
provision another. And **one Pack is live per venture**, because a run has to name
exactly one and "the current Pack" cannot be a question with two answers.
"""

from __future__ import annotations

import uuid

import pytest

from broker import packs
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")


async def test_a_pack_round_trips_with_a_computed_hash(world, pack_yaml):
    """P1 - store it, read it back, and get the same document and the same hash."""
    async with connection() as conn:
        stored = await packs.store(
            conn, yaml_source=pack_yaml, pack_version="1.0.0", authored_by=AUTHOR
        )
        read_back = await packs.live(conn, "greenstone")

    assert read_back is not None
    assert read_back.yaml_source == pack_yaml
    assert read_back.content_hash == stored.content_hash
    assert len(stored.content_hash) == 64, "sha256 hex, computed by the database"
    assert read_back.pack.venture_id == "greenstone"
    assert read_back.pack.positions_required, "the parsed form must survive the trip"


async def test_the_hash_is_the_documents_and_changes_with_it(world, pack_yaml):
    """A signature binds to this hash, so it must move when the document moves.

    One space in a comment is the smallest edit that changes nothing semantically. It
    still changes what a reviewer read, and a reviewer signs a document rather than a
    parse tree - so it must change the hash.
    """
    edited = pack_yaml.replace("schema_version: 3", "schema_version: 3 ", 1)
    assert edited != pack_yaml, "the edit must actually land, or this asserts nothing"

    async with connection() as conn:
        first = await packs.store(
            conn, yaml_source=pack_yaml, pack_version="1.0.0", authored_by=AUTHOR
        )
        second = await packs.store(
            conn, yaml_source=edited, pack_version="1.0.1", authored_by=AUTHOR
        )
        third = await packs.store(
            conn, yaml_source=pack_yaml, pack_version="1.0.2", authored_by=AUTHOR
        )

    assert first.content_hash != second.content_hash
    assert first.content_hash == third.content_hash, "the same bytes hash the same"


async def test_one_pack_is_live_per_venture_and_authoring_supersedes(world, pack_yaml):
    """P2 - publishing v2 retires v1, and the retired version stays readable.

    Readable matters as much as retired. A run records the version it started from, and
    that record is worthless if the version disappears the moment somebody edits.
    """
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=pack_yaml, pack_version="1.0.0", authored_by=AUTHOR
        )
        await packs.store(
            conn, yaml_source=pack_yaml + "\n# amended\n", pack_version="2.0.0",
            authored_by=AUTHOR,
        )

        live = await packs.live(conn, "greenstone")
        versions = await packs.list_versions(conn, "greenstone")
        old = await packs.get_version(conn, "greenstone", "1.0.0")
        ventures = await packs.list_ventures(conn)

    assert live is not None and live.pack_version == "2.0.0"
    assert {v["pack_version"] for v in versions} == {"1.0.0", "2.0.0"}
    superseded = {v["pack_version"]: v["superseded_at"] for v in versions}
    assert superseded["1.0.0"] is not None
    assert superseded["2.0.0"] is None
    assert old is not None and old.pack_version == "1.0.0"
    assert [v["venture_id"] for v in ventures].count("greenstone") == 1


async def test_the_venture_is_taken_from_the_pack_not_from_the_caller(world, pack_yaml):
    """`store` has no venture parameter, and that is the control.

    A caller who could name the venture could publish one venture's Pack under another
    venture's name, and every gate downstream would provision the wrong business
    against the right-looking id.
    """
    import inspect

    assert "venture_id" not in inspect.signature(packs.store).parameters

    async with connection() as conn:
        stored = await packs.store(
            conn, yaml_source=pack_yaml, pack_version="1.0.0", authored_by=AUTHOR
        )
    assert stored.venture_id == "greenstone"


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("key: [unclosed", "not valid YAML"),
        ("- just\n- a\n- list\n", "mapping at the top level"),
        ("venture_id: nope\n", "not a schema-v3 Business Pack"),
    ],
)
async def test_something_that_is_not_a_pack_is_refused_at_the_door(
    world, source, fragment
):
    """Storing an unparseable Pack would move the failure to Gate 3.

    Gates 0 through 2 would report healthy first, so the run would look like it was
    working right up until the generators ran. Refusing here costs one error message;
    refusing there costs a debugging session.
    """
    async with connection() as conn:
        with pytest.raises(packs.PackStoreError) as exc:
            await packs.store(
                conn, yaml_source=source, pack_version="1.0.0", authored_by=AUTHOR
            )
        assert fragment in str(exc.value)
        assert await packs.live(conn, "greenstone") is None, "nothing was stored"


async def test_the_live_pack_of_a_venture_with_no_pack_is_none(world):
    """Not an exception, and not an empty Pack. Gate 1 asks this question."""
    async with connection() as conn:
        assert await packs.live(conn, "no-such-venture") is None
        assert await packs.get_version(conn, "greenstone", "9.9.9") is None
