"""The Pack store.

Until now a Business Pack was a YAML file on disk. That is fine for a file a human edits
in an editor, and useless for everything else: a Pack Editor cannot edit a file the
server has never seen, a provisioning run cannot record which Pack it provisioned, and a
Gate 10 signature cannot bind to something with no identity.

Two rules, both mirroring the instruction store because they exist for the same reasons:

  * **One live Pack per venture**, enforced by a partial unique index. Two would make
    "the current Pack" ambiguous, and a provisioning run has to name exactly one.
  * **`content_hash` is computed in the database**, never accepted from a caller. A
    supplied hash is a claim. This one is what a Gate 10 signature binds to, so a caller
    able to choose it could sign one Pack and provision another.

The YAML source is stored alongside the parsed form. The parsed form is what the
generators read; the source is what a human edits and what the hash is taken over -
because two YAML documents that parse identically but read differently are, to a
reviewer signing one of them, not the same document.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import yaml
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from generators.pack import BusinessPack, PackLoadError


class PackStoreError(Exception):
    """The Pack could not be stored or retrieved as asked."""


@dataclass(frozen=True, slots=True)
class StoredPack:
    venture_id: str
    pack_version: str
    content_hash: str
    yaml_source: str
    pack: BusinessPack

    @property
    def identity(self) -> str:
        return f"{self.venture_id}@{self.pack_version}"


def _parse(yaml_source: str) -> BusinessPack:
    """Shape-validate before storing.

    Storing a Pack that does not parse would let a venture hold something that reads
    like a Pack, passes a glance, and fails the moment a run tries to generate from it -
    at Gate 3, after Gates 0 to 2 have already reported healthy.
    """
    try:
        raw = yaml.safe_load(yaml_source)
    except yaml.YAMLError as exc:
        raise PackStoreError(f"not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackStoreError("Pack does not contain a mapping at the top level")
    try:
        return BusinessPack.model_validate(raw)
    except Exception as exc:
        raise PackStoreError(f"not a schema-v3 Business Pack: {exc}") from exc


async def store(
    conn: AsyncConnection,
    *,
    yaml_source: str,
    pack_version: str,
    authored_by: uuid.UUID,
) -> StoredPack:
    """Publish a Pack version, superseding the current live one for that venture.

    `venture_id` is derived from the Pack rather than passed in, so a caller cannot
    store one venture's Pack under another venture's name.
    """
    pack = _parse(yaml_source)
    venture_id = pack.venture_id

    async with conn.cursor(row_factory=dict_row) as cur:
        # Supersede and insert in one transaction. Between the two statements there is
        # no live Pack, and a concurrent run starting there would find none.
        await cur.execute(
            "UPDATE business_pack SET superseded_at = now() "
            "WHERE venture_id = %s AND superseded_at IS NULL",
            (venture_id,),
        )
        await cur.execute(
            """
            INSERT INTO business_pack
              (venture_id, pack_version, schema_version, yaml_source, parsed,
               content_hash, authored_by)
            VALUES (%s, %s, %s, %s, %s, '', %s)
            RETURNING content_hash
            """,
            (
                venture_id, pack_version, pack.schema_version, yaml_source,
                Jsonb(pack.model_dump(mode="json")), authored_by,
            ),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None

    return StoredPack(
        venture_id=venture_id,
        pack_version=pack_version,
        content_hash=row["content_hash"],
        yaml_source=yaml_source,
        pack=pack,
    )


async def live(conn: AsyncConnection, venture_id: str) -> StoredPack | None:
    """The Pack currently in force for this venture."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, yaml_source, content_hash "
            "FROM business_pack WHERE venture_id = %s AND superseded_at IS NULL",
            (venture_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return StoredPack(
        venture_id=row["venture_id"],
        pack_version=row["pack_version"],
        content_hash=row["content_hash"],
        yaml_source=row["yaml_source"],
        pack=_parse(row["yaml_source"]),
    )


async def get_version(
    conn: AsyncConnection, venture_id: str, pack_version: str
) -> StoredPack | None:
    """A specific version, live or superseded.

    A run names the version it started with, and that version has to remain readable
    after it is superseded - otherwise the record of what was provisioned disappears
    the moment somebody edits the Pack.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, yaml_source, content_hash "
            "FROM business_pack WHERE venture_id = %s AND pack_version = %s",
            (venture_id, pack_version),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return StoredPack(
        venture_id=row["venture_id"],
        pack_version=row["pack_version"],
        content_hash=row["content_hash"],
        yaml_source=row["yaml_source"],
        pack=_parse(row["yaml_source"]),
    )


async def list_versions(
    conn: AsyncConnection, venture_id: str
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT pack_version, content_hash, authored_by, authored_at, superseded_at "
            "FROM business_pack WHERE venture_id = %s ORDER BY authored_at DESC",
            (venture_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def list_ventures(conn: AsyncConnection) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, content_hash, authored_at "
            "FROM business_pack WHERE superseded_at IS NULL ORDER BY venture_id"
        )
        return [dict(r) for r in await cur.fetchall()]


__all__ = [
    "PackLoadError",
    "PackStoreError",
    "StoredPack",
    "get_version",
    "list_ventures",
    "list_versions",
    "live",
    "store",
]
