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
from generators.validator import GATE_45_RULES, all_rule_ids, validate


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


def parse_only(yaml_source: str) -> BusinessPack:
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
    publish: bool = True,
) -> StoredPack:
    """Store a Pack version, as the live one or as a draft.

    `venture_id` is derived from the Pack rather than passed in, so a caller cannot
    store one venture's Pack under another venture's name.

    `publish=False` stores a **draft**: it supersedes nothing, and `live()` will not
    return it - so Gate 1 cannot find it and nothing downstream can generate from it.
    A draft is unable to provision by construction rather than by a flag somebody
    remembers to check. Storing a second draft replaces the first, because "the current
    draft" cannot be a question with two answers.
    """
    pack = parse_only(yaml_source)
    venture_id = pack.venture_id
    status = "live" if publish else "draft"

    async with conn.cursor(row_factory=dict_row) as cur:
        if publish:
            # Supersede and insert in one transaction. Between the two statements there
            # is no live Pack, and a concurrent run starting there would find none.
            await cur.execute(
                "UPDATE business_pack SET superseded_at = now(), status = 'superseded' "
                "WHERE venture_id = %s AND status = 'live'",
                (venture_id,),
            )
        else:
            # Superseded, not deleted. A draft somebody replaced is still a document
            # somebody wrote, and `office_app` has no DELETE on this table by design -
            # the Pack store is append-only for the same reason the audit log is.
            await cur.execute(
                "UPDATE business_pack SET status = 'superseded', superseded_at = now() "
                "WHERE venture_id = %s AND status = 'draft'",
                (venture_id,),
            )

        await cur.execute(
            """
            INSERT INTO business_pack
              (venture_id, pack_version, schema_version, yaml_source, parsed,
               content_hash, authored_by, status)
            VALUES (%s, %s, %s, %s, %s, '', %s, %s)
            ON CONFLICT (venture_id, pack_version) DO UPDATE
            SET yaml_source = EXCLUDED.yaml_source,
                parsed = EXCLUDED.parsed,
                status = EXCLUDED.status,
                authored_by = EXCLUDED.authored_by,
                authored_at = now(),
                superseded_at = NULL
            RETURNING content_hash
            """,
            (
                venture_id, pack_version, pack.schema_version, yaml_source,
                Jsonb(pack.model_dump(mode="json")), authored_by, status,
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
    """The Pack currently in force. Never a draft - that is the point of the status."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, yaml_source, content_hash "
            "FROM business_pack WHERE venture_id = %s AND status = 'live'",
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
        pack=parse_only(row["yaml_source"]),
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
        pack=parse_only(row["yaml_source"]),
    )


async def draft(conn: AsyncConnection, venture_id: str) -> StoredPack | None:
    """The unpublished draft, if there is one."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, yaml_source, content_hash "
            "FROM business_pack WHERE venture_id = %s AND status = 'draft'",
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
        pack=parse_only(row["yaml_source"]),
    )


async def publish_draft(
    conn: AsyncConnection, venture_id: str, *, published_by: uuid.UUID
) -> StoredPack:
    """Promote the draft to live, superseding whatever was in force.

    The same act as `store(publish=True)` on the draft's own source, which is how it is
    implemented - so a publish cannot take a different path from the one every other
    publish takes and diverge from it later.
    """
    pending = await draft(conn, venture_id)
    if pending is None:
        raise PackStoreError(f"{venture_id} has no draft to publish")

    # Cleared first so `store` sees no draft to supersede, then re-inserted as live by
    # the ON CONFLICT path - the same row, promoted, rather than a copy of it.
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE business_pack SET status = 'superseded', superseded_at = now() "
            "WHERE venture_id = %s AND status = 'draft'",
            (venture_id,),
        )
    await conn.commit()

    return await store(
        conn,
        yaml_source=pending.yaml_source,
        pack_version=pending.pack_version,
        authored_by=published_by,
        publish=True,
    )


async def list_versions(
    conn: AsyncConnection, venture_id: str
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT pack_version, content_hash, authored_by, authored_at, "
            "       superseded_at, status "
            "FROM business_pack WHERE venture_id = %s ORDER BY authored_at DESC",
            (venture_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def list_ventures(conn: AsyncConnection) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, content_hash, authored_at "
            "FROM business_pack WHERE status = 'live' ORDER BY venture_id"
        )
        return [dict(r) for r in await cur.fetchall()]


# --------------------------------------------------------------- the directory

# Every top-level block the schema defines. Completeness is a different question from
# validation: a Pack can be schema-complete and still fail rules, or be missing an
# optional block no rule covers yet. Derived from the model rather than listed, so a new
# block cannot be added to the schema and forgotten here.
def schema_blocks() -> tuple[list[str], list[str]]:
    """(every block, the required ones)."""
    fields = BusinessPack.model_fields
    return list(fields), [n for n, f in fields.items() if f.is_required()]


# Artifacts the generators produce, and where each one ends up. Three of the six are
# persisted; the other two are generated on demand and stored nowhere, which the page
# says rather than rendering as an absence that looks like a failure.
ARTIFACTS = [
    ("positions", "the Pack's own positions_required, before appointment"),
    ("appointments", "agent_forge_grant"),
    ("workflow", None),
    ("task ledger", None),
    ("curriculum", "curriculum_submission"),
    ("manifest", "venture_forge_manifest"),
]


async def directory(conn: AsyncConnection) -> dict[str, Any]:
    """Every Pack, and whether it can provision.

    The old page showed that a Pack existed and gave its hash. It did not show whether
    the Pack **works** - and a Pack failing any FAIL rule cannot provision, cannot
    generate and cannot appoint, which makes "does it validate" the most important thing
    on the page and the one thing it did not say.

    The failing rules are reported with the validator's own `message`, which states what
    is wrong with *this* Pack ("no operating instructions authored for 3 modules"), not
    the rule's description ("every position's modules have instructions authored"). The
    second is a specification; only the first is actionable.
    """
    from broker import ventures  # local: ventures imports packs

    every_block, required_blocks = schema_blocks()

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT venture_id, pack_version, content_hash, authored_by, authored_at,
                   status, yaml_source, parsed
            FROM business_pack
            WHERE status IN ('draft', 'live')
            ORDER BY venture_id, status
            """
        )
        rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT DISTINCT ON (venture_id) venture_id, pack_version, status, current_gate
            FROM provisioning_run
            ORDER BY venture_id, started_at DESC
            """
        )
        runs = {r["venture_id"]: dict(r) for r in await cur.fetchall()}

        await cur.execute("SELECT slug, display_name FROM venture")
        registered = {r["slug"]: r["display_name"] for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT venture_id,
                   count(*) FILTER (WHERE kind = 'grant')      AS grants,
                   count(*) FILTER (WHERE kind = 'manifest')   AS manifest,
                   count(*) FILTER (WHERE kind = 'curriculum') AS curriculum
            FROM (
              SELECT venture_id, 'grant'::text AS kind FROM agent_forge_grant
              UNION ALL SELECT venture_id, 'manifest' FROM venture_forge_manifest
              UNION ALL SELECT venture_id, 'curriculum' FROM curriculum_submission
            ) a GROUP BY venture_id
            """
        )
        produced = {r["venture_id"]: dict(r) for r in await cur.fetchall()}

        await cur.execute(
            "SELECT venture_id, count(*) AS signatures FROM signoff_record "
            "WHERE gate = 'gate_10' GROUP BY venture_id"
        )
        signatures = {r["venture_id"]: int(r["signatures"]) for r in await cur.fetchall()}

        await cur.execute(
            "SELECT human_id::text AS human_id, display_name FROM office_human"
        )
        authors = {r["human_id"]: r["display_name"] for r in await cur.fetchall()}

    by_venture: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_venture.setdefault(row["venture_id"], {})[row["status"]] = row

    out: list[dict[str, Any]] = []
    for venture_id, states in sorted(by_venture.items()):
        current = states.get("live") or states.get("draft")
        assert current is not None
        pack = parse_only(current["yaml_source"])

        report = await validate(pack, conn)
        failures = [
            {"rule_id": r.rule_id, "message": r.message} for r in report.failures
        ]
        warnings = [
            {"rule_id": r.rule_id, "message": r.message} for r in report.warnings
        ]
        # V24 is *deferred*, not unrun: it is evaluated at Gate 4.5 against appointment
        # output, which does not exist at Gate 2. Gate 2 excludes it from its own
        # NOT_RUN check for exactly this reason, and the page has to agree - counting it
        # would make `not validated` permanent and `valid` unreachable, which turns the
        # distinction this page exists to draw into noise.
        deferred = [
            {"rule_id": r.rule_id, "message": r.message}
            for r in report.not_run
            if r.rule_id in GATE_45_RULES
        ]
        not_run = [
            {"rule_id": r.rule_id, "message": r.message}
            for r in report.not_run
            if r.rule_id not in GATE_45_RULES
        ]

        if failures:
            state = "failing"
        elif not_run:
            # NOT_RUN is not a pass. A rule that could not run has validated nothing,
            # and rendering that as `valid` is the single thing this page must never do.
            state = "not_validated"
        elif warnings:
            state = "warnings"
        else:
            state = "valid"

        present = [b for b in every_block if (current["parsed"] or {}).get(b) not in (None, [], {})]

        run = runs.get(venture_id)
        provisioned_version = None
        if run and run["status"] in ("complete", "running", "blocked", "awaiting_human"):
            provisioned_version = run["pack_version"]

        live_row = states.get("live")
        draft_row = states.get("draft")

        counts = produced.get(venture_id, {})
        artifacts = []
        for name, source in ARTIFACTS:
            if name == "positions":
                count = len(pack.positions_required)
            elif name == "appointments":
                count = int(counts.get("grants", 0) or 0)
            elif name == "curriculum":
                count = int(counts.get("curriculum", 0) or 0)
            elif name == "manifest":
                count = int(counts.get("manifest", 0) or 0)
            else:
                count = None
            artifacts.append({
                "name": name,
                "count": count,
                # Workflow and the task ledger are generated on demand and stored
                # nowhere. Rendering them as "none" would read as a generator failure
                # rather than as a design decision.
                "persisted": source is not None or name == "positions",
                "note": None if source or name == "positions"
                        else "generated on demand, not stored",
            })

        out.append({
            "venture_id": venture_id,
            "display_name": registered.get(venture_id)
                            or pack.identity.venture_name or venture_id,
            "validation": {
                "state": state,
                "failures": failures,
                "warnings": warnings,
                "not_run": not_run,
                "deferred": deferred,
                "rules_checked": len(report.results),
            },
            "versions": {
                "draft": None if not draft_row else {
                    "version": draft_row["pack_version"],
                    "content_hash": draft_row["content_hash"],
                    "authored_at": draft_row["authored_at"].isoformat(),
                    "author": authors.get(str(draft_row["authored_by"])),
                },
                "live": None if not live_row else {
                    "version": live_row["pack_version"],
                    "content_hash": live_row["content_hash"],
                    "authored_at": live_row["authored_at"].isoformat(),
                    "author": authors.get(str(live_row["authored_by"])),
                },
                "provisioned": provisioned_version,
            },
            # Live ahead of provisioned is drift: the running configuration is not the
            # one that is published, and nothing on the old page could express it.
            "drift": bool(
                live_row
                and provisioned_version
                and provisioned_version != live_row["pack_version"]
            ),
            "never_provisioned": provisioned_version is None,
            "signatures": signatures.get(venture_id, 0),
            # A signature binds to the artifacts a specific Pack generates. Publishing a
            # new version changes them, so every signature taken against the old one is
            # void by comparison - nothing revokes it, it stops matching.
            "signatures_voided_by_publish": bool(
                signatures.get(venture_id)
                and live_row
                and provisioned_version
                and provisioned_version != live_row["pack_version"]
            ),
            "schema": {
                "present": len(present),
                "total": len(every_block),
                "missing": [b for b in every_block if b not in present],
                "required_missing": [
                    b for b in required_blocks if b not in present
                ],
            },
            "artifacts": artifacts,
            "nothing_generated": all(
                (a["count"] or 0) == 0 for a in artifacts if a["name"] != "positions"
            ),
        })

    # Ventures with an engagement and no Pack, and the portfolio ventures that are not
    # registered at all. Absence must not be able to look like health.
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT DISTINCT v.venture_id FROM (
              SELECT DISTINCT venture_id FROM agent_forge_grant
              UNION SELECT DISTINCT venture_id FROM venture_forge_manifest
              UNION SELECT venture_id FROM venture_budget
              UNION SELECT slug FROM venture
            ) v
            WHERE v.venture_id NOT IN (
              SELECT venture_id FROM business_pack WHERE status IN ('draft', 'live')
            )
            ORDER BY 1
            """
        )
        packless = [r["venture_id"] for r in await cur.fetchall()]

    known = set(by_venture) | set(packless)
    unregistered = [v for v in ventures.PORTFOLIO if v["slug"] not in known]

    return {
        "packs": out,
        "packless": packless,
        "registered_ventures": len(known),
        "unregistered_portfolio": unregistered,
        "portfolio_size": len(ventures.PORTFOLIO),
        "rules_total": len(all_rule_ids()),
        "schema_blocks": len(every_block),
    }


__all__ = [
    "PackLoadError",
    "PackStoreError",
    "StoredPack",
    "directory",
    "draft",
    "get_version",
    "list_ventures",
    "list_versions",
    "live",
    "parse_only",
    "publish_draft",
    "store",
]
