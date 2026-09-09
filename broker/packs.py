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
from pydantic import ValidationError

from broker import audit
from generators.pack import BusinessPack, PackLoadError
from generators.validator import GATE_45_RULES, all_rule_ids, validate


class PackStoreError(Exception):
    """The Pack could not be stored or retrieved as asked."""


@dataclass(frozen=True, slots=True)
class SchemaTightening:
    """One occasion on which v3 began requiring something v3 had not required before.

    `schema_version` did not move for any of these, and could not have: they are not a
    new schema, they are the same schema asking for more. That is precisely why the
    column cannot answer *is this row stale* - it carries the coarse half of the answer
    (which schema) and this ledger carries the fine half (which revision of it).

    There is no revision number here on purpose. A number would be a name asserting more
    than the code knows - the exact class of defect this change exists to remove - so a
    revision is identified by the requirement it added, the date it landed, and the
    blocking-log entry that argued for it. All three are things a reader can go and
    check.
    """

    #: Where pydantic reports the field, with list indexes elided:
    #: ``("human_capacity", "provenance")`` matches loc ``("human_capacity", 3,
    #: "provenance")``.
    field_path: tuple[str, ...]

    #: The date the tightening landed, and the blocking-log entry behind it.
    landed: str
    blocking_entry: str

    #: What this build requires now, in one sentence and in the schema's own words.
    requires: str

    @property
    def label(self) -> str:
        """How the field is written when a human talks about it."""
        head, *rest = self.field_path
        return head + "".join(f"[].{part}" for part in rest)


@dataclass(frozen=True, slots=True)
class SchemaRename:
    """One occasion on which v3 began calling an existing field something else.

    **A sibling of `SchemaTightening` rather than a flag on it, and the distinction is
    load-bearing.** A tightening is v3 asking for *more*; a rename is v3 asking for the
    *same value* under another name. B31 proposed a `renamed_from` field, and putting one
    on a class called `SchemaTightening` would make the class name false for half its
    rows - a name asserting more than the code does, which is B23's class appearing
    inside the machinery built to fix B27. That is the specific trap B31 warns about, so
    it is not repeated here in the fix for it.

    The practical difference is the error signature. A tightening leaves **one** error per
    entry; a rename leaves **two** - the new name missing and the old name refused - and
    only the pair means "this row predates the rename". Either half alone means something
    else, and both of those somethings are handled below.
    """

    #: The path under the CURRENT name. Same convention as `SchemaTightening.field_path`.
    field_path: tuple[str, ...]

    #: What the field used to be called. The last segment only; a rename moves a name,
    #: not a field to another parent.
    previous_name: str

    landed: str
    blocking_entry: str
    requires: str

    @property
    def label(self) -> str:
        head, *rest = self.field_path
        return head + "".join(f"[].{part}" for part in rest)

    @property
    def previous_path(self) -> tuple[str, ...]:
        """Where the old name is reported when a stale row still carries it."""
        return (*self.field_path[:-1], self.previous_name)


#: A change v3 made to what it accepts. Two kinds, because they fail differently.
SchemaChange = SchemaTightening | SchemaRename


#: Every v3 change, oldest first.
#:
#: **Appending here is the second half of changing what `generators/pack.py` accepts.**
#: Without the entry, a row stored before the change is reported as *not a schema-v3
#: Business Pack* - false about the data, and it sends the reader to inspect a document
#: that is fine. That is blocking-log B27; B31 is what it cost when a rename landed and
#: the ledger could only describe tightenings.
V3_SCHEMA_CHANGES: tuple[SchemaChange, ...] = (
    SchemaTightening(
        field_path=("human_capacity", "provenance"),
        landed="2026-09-08",
        blocking_entry="B21",
        requires=(
            "every `human_capacity` entry carries a `provenance` block: `basis` "
            "(declared / inherited / measured), `established_by` naming a person, a "
            "`detail` sentence, and - when the basis is not `declared` - a `source` "
            "naming what was copied or observed"
        ),
    ),
    SchemaRename(
        field_path=("human_capacity", "advisory_daily_approval_ceiling"),
        previous_name="max_daily_approvals",
        landed="2026-09-09",
        blocking_entry="B23",
        requires=(
            "every `human_capacity` entry declares its daily approval figure as "
            "`advisory_daily_approval_ceiling`. The value did not change and neither "
            "did its effect - nothing enforces it, and nothing ever did. What could not "
            "persist was a name that read as a cap"
        ),
    ),
)


#: The tightenings alone. Kept as its own name because it is still exactly true, and
#: because a caller asking "what has v3 started requiring" is asking a narrower question
#: than "what has v3 changed".
V3_TIGHTENINGS: tuple[SchemaTightening, ...] = tuple(
    change for change in V3_SCHEMA_CHANGES if isinstance(change, SchemaTightening)
)

#: The renames alone, for the same reason.
V3_RENAMES: tuple[SchemaRename, ...] = tuple(
    change for change in V3_SCHEMA_CHANGES if isinstance(change, SchemaRename)
)


class PackPredatesTighteningError(PackStoreError):
    """A valid Pack of an EARLIER revision of its own schema. Not a malformed document.

    A subclass rather than a different sentence, because the two need different actions
    and until now got the same one. A malformed document is a document to inspect; this
    is a row to migrate, and the document it points at is fine. A caller that wants to
    tell them apart should not have to read prose to do it.
    """

    def __init__(self, message: str, *, predates: tuple[SchemaChange, ...]) -> None:
        super().__init__(message)
        #: The ledger changes this document was stored before, oldest first. A
        #: `SchemaTightening` or a `SchemaRename`; the caller can tell them apart by
        #: type rather than by reading the message.
        self.predates = predates


def _elide_indexes(loc: tuple[object, ...]) -> tuple[str, ...]:
    """A pydantic error location with list positions dropped.

    The ledger names a field, not an entry. Four entries missing `provenance` are one
    tightening reported four times, not four tightenings.
    """
    return tuple(part for part in loc if isinstance(part, str))


def _predated_tightenings(
    exc: ValidationError,
) -> tuple[tuple[SchemaChange, ...], dict[tuple[str, ...], int]] | None:
    """Which ledger changes explain this failure ENTIRELY, or `None` if any error does not.

    `None` does not mean *no changes*. It means at least one error is something else -
    and a document with one unexplained error is malformed whatever else is true of it.
    Reporting that one as merely old would be the same false confidence pointing the
    other way, which is not an improvement on B27, it is B27 mirrored.

    **A tightening leaves one error; a rename leaves a pair, and only the pair counts.**
    That is B31. The guard used to reject the whole diagnosis on the first
    `extra_forbidden`, which was right for every change the ledger could describe and
    wrong for a rename - so a renamed field fell back to the generic sentence, on exactly
    the class of row this machinery exists for.

    Two rules keep the guard's teeth, and both are asserted in the tests:

      * **An `extra_forbidden` is explained only as the old half of a ledgered rename
        whose new half is missing at the SAME entry.** A refused key that is not that is
        still a document disagreeing with the schema. **This is the whole value of the
        guard and it is unchanged for every input that is not half of a pair.**
      * **A `missing` at a rename's new name is explained only when the old name is
        refused at that same entry.** A row carrying neither name never satisfied either
        revision - the old field had no default - so it is malformed, not old.

    Both halves are matched on the FULL location including the list index, not on the
    elided path. A document carrying the old name in one entry and neither name in
    another is not a row that predates the rename; it is a row somebody hand-edited, and
    index-blind pairing would call it old and send the reader to a migration that will
    not help.
    """
    tightenings = {t.field_path: t for t in V3_TIGHTENINGS}
    renames_by_new = {r.field_path: r for r in V3_RENAMES}
    renames_by_old = {r.previous_path: r for r in V3_RENAMES}

    errors = [
        (str(error.get("type")), tuple(error.get("loc", ()))) for error in exc.errors()
    ]
    missing_at = {loc for kind, loc in errors if kind == "missing"}
    refused_at = {loc for kind, loc in errors if kind == "extra_forbidden"}

    ordered: list[SchemaChange] = []
    counts: dict[tuple[str, ...], int] = {}

    def note(change: SchemaChange) -> None:
        if change not in ordered:
            ordered.append(change)
        counts[change.field_path] = counts.get(change.field_path, 0) + 1

    for kind, loc in errors:
        path = _elide_indexes(loc)
        if kind == "missing":
            tightening = tightenings.get(path)
            if tightening is not None:
                note(tightening)
                continue
            rename = renames_by_new.get(path)
            if rename is None:
                return None
            # The other half must be present at this same entry.
            if (*loc[:-1], rename.previous_name) not in refused_at:
                return None
            note(rename)
        elif kind == "extra_forbidden":
            rename = renames_by_old.get(path)
            if rename is None:
                # The guard, unchanged: a refused key that is not the old half of a
                # ledgered rename disqualifies the whole diagnosis.
                return None
            if (*loc[:-1], rename.field_path[-1]) not in missing_at:
                # The old name AND the new name both present, or the old name refused
                # somewhere the new one is not missing. Neither is an unmigrated row.
                return None
            # Counted on the `missing` half only, so a pair is one change, not two.
        else:
            # A wrong type or a failed validator is a document that disagrees with the
            # schema, not one that is older than it.
            return None

    if not ordered:
        return None
    # Ledger order, not the order pydantic happened to report the errors in.
    # `PackPredatesTighteningError.predates` says "oldest first", and a docstring that
    # says so while the code sorts by whichever error pydantic emitted first is a name
    # asserting more than the code does - the defect this whole ledger exists to remove.
    ordered.sort(key=V3_SCHEMA_CHANGES.index)
    return tuple(ordered), counts


def _predates_message(
    predates: tuple[SchemaChange, ...],
    counts: dict[tuple[str, ...], int],
    stored_as: str | None,
) -> str:
    """The honest version of what B27 found the reader being told.

    Three things it has to carry, because the old sentence carried none of them: that
    the document IS schema-v3, which revision of v3 it was stored under, and what this
    build's revision requires instead. A rename gets its own bullet wording - *this used
    to be called that* is the sentence a reader needs, and "field required" is not it.
    """
    subject = f"{stored_as} is" if stored_as else "this document is"
    newest = max(c.landed for c in V3_SCHEMA_CHANGES)
    lines = [
        f"{subject} a schema-v3 Business Pack stored under an EARLIER REVISION of v3. "
        "It is not malformed. `schema_version` says 3 and that is correct - every "
        "field v3 required when this was written is present, under the name it had "
        "then. What the column cannot say is WHICH revision of v3, and this one was "
        "stored before "
        + ("this change:" if len(predates) == 1 else f"these {len(predates)} changes:"),
    ]
    for change in predates:
        affected = counts.get(change.field_path, 0)
        where = "1 entry" if affected == 1 else f"{affected} entries"
        if isinstance(change, SchemaRename):
            lines.append(
                f"  * `{change.label}` - renamed from `{change.previous_name}` on "
                f"{change.landed} (blocking-log {change.blocking_entry}); {where} here "
                f"still carry the old name. This build requires that {change.requires}."
            )
        else:
            lines.append(
                f"  * `{change.label}` - required since {change.landed} "
                f"(blocking-log {change.blocking_entry}), absent from {where} here. "
                f"This build requires that {change.requires}."
            )
    lines.append(f"This build reads v3 as of {newest}.")
    if stored_as:
        lines.append(
            "Do not go and inspect the Pack source; there is nothing wrong with it. "
            "This is a stored row that was never migrated when the schema changed. "
            "Republish the venture's Pack at a new version - see docs/blocking.md B26, "
            "B28 and B31."
        )
    else:
        lines.append(
            "The source you supplied predates the change. Bring it up to the current "
            "revision before storing it - the stored form is re-parsed on every read, "
            "so storing it as it stands would create the row B26 describes."
        )
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class StoredPack:
    venture_id: str
    pack_version: str
    content_hash: str
    yaml_source: str
    pack: BusinessPack

    #: Lines that differ from whatever this version replaced, as (before, after).
    #: Empty when nothing was in force to compare against - a first publish changes
    #: everything and comparing it to nothing would report a number nobody can use.
    changed_lines: tuple[tuple[str, str], ...] = ()
    replaced_version: str | None = None

    @property
    def identity(self) -> str:
        return f"{self.venture_id}@{self.pack_version}"

    @property
    def change_count(self) -> int:
        return len(self.changed_lines)


def parse_only(yaml_source: str, *, stored_as: str | None = None) -> BusinessPack:
    """Shape-validate before storing, or after reading.

    Storing a Pack that does not parse would let a venture hold something that reads
    like a Pack, passes a glance, and fails the moment a run tries to generate from it -
    at Gate 3, after Gates 0 to 2 have already reported healthy.

    `stored_as` is the row's identity when this is a READ rather than a store, and it
    changes the diagnosis rather than decorating it. A source a caller just handed us
    that predates a tightening is a source to fix; a row already in `business_pack` that
    predates one is a migration nobody ran, and the document it names is fine. Those are
    different problems with different fixes, and B27 is what it costs to give them the
    same sentence.
    """
    try:
        raw = yaml.safe_load(yaml_source)
    except yaml.YAMLError as exc:
        raise PackStoreError(f"not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise PackStoreError("Pack does not contain a mapping at the top level")
    try:
        return BusinessPack.model_validate(raw)
    except ValidationError as exc:
        # B27. The old message said "not a schema-v3 Business Pack" for both of the
        # cases below, and for one of them that is FALSE ABOUT THE DATA: the row's
        # `schema_version` says 3, it was published as 3, and it was valid 3 on the day
        # it was written. Saying otherwise sends the reader to inspect a Pack that has
        # nothing wrong with it while the actual fault is a row nobody migrated.
        aged = _predated_tightenings(exc)
        if aged is not None:
            predates, counts = aged
            raise PackPredatesTighteningError(
                _predates_message(predates, counts, stored_as), predates=predates
            ) from exc
        # Nothing here is explained by a tightening, so the original sentence is the
        # true one and stays exactly as it was.
        raise PackStoreError(f"not a schema-v3 Business Pack: {exc}") from exc
    except Exception as exc:
        raise PackStoreError(f"not a schema-v3 Business Pack: {exc}") from exc


class PackDiffUnexpectedError(PackStoreError):
    """The publish changed a different number of lines than the caller declared.

    Raised **before** anything is written, so a publish that does not match its own
    description does not happen at all.
    """


def _changed_lines(before: str, after: str) -> tuple[tuple[str, str], ...]:
    """Line-for-line differences, positionally.

    Positional rather than a real diff: this exists to answer "did exactly the edits I
    intended land", and for that an insertion that shifts every following line SHOULD
    read as a large change rather than as one. A caller declaring three changed lines is
    declaring that nothing moved.
    """
    b, a = before.splitlines(), after.splitlines()
    if len(b) != len(a):
        # Different lengths cannot be compared positionally. Report every line as
        # changed rather than guessing an alignment - the caller asked whether its
        # small edit landed, and the answer here is "this was not a small edit".
        return tuple(
            (x, y) for x, y in zip(b + [""] * (len(a) - len(b)),
                                   a + [""] * (len(b) - len(a)), strict=False)
            if x != y
        )
    return tuple((x, y) for x, y in zip(b, a, strict=True) if x != y)


async def store(
    conn: AsyncConnection,
    *,
    yaml_source: str,
    pack_version: str,
    authored_by: uuid.UUID,
    publish: bool = True,
    expect_changed_lines: int | None = None,
    change_summary: list[str] | None = None,
) -> StoredPack:
    """Store a Pack version, as the live one or as a draft.

    `expect_changed_lines` is the control, and the reason it exists is worth the space.

    **A source file drifts ahead of what is in force.** On 6 September a rename of three
    department names was approved and `packs/greenstone.yaml` on disk carried a second,
    unpublished change - `generate_loi` removed, with an open `# DECISION NEEDED` in the
    comment above it. "Publish the file" would have shipped that decision as a side
    effect of the rename, and **nothing in this path would have shown that more than
    three lines changed.** There was no diff, no count, and until now no audit entry: a
    publish recorded a new `content_hash` and nothing about what it did.

    So a caller that knows what it is changing says so, and a publish that does not match
    its own description raises before writing anything. Callers that cannot know - the
    console, where a human is editing a draft freehand - pass nothing and are unaffected.

    The diff is computed and audited either way. Declaring the count is optional;
    recording what changed is not.

    `change_summary` is what the publisher *meant*, in their own words, beside the count
    of what moved. The two answer different questions and both belong in the record: a
    positional diff of 273 lines is the honest answer to "did anything shift that you did
    not expect", and it says nothing about intent - 39 inserted lines of comment shift
    every line below them. The summary says the edit was five things. Neither substitutes
    for the other, and a reader six months later needs both to reconstruct the change.

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

    # What this replaces, read before anything is written so the comparison is against
    # the version actually in force at this moment.
    #
    # Read as RAW SOURCE rather than through `live()`/`draft()`, which parse. The diff is
    # textual - `_changed_lines` compares two strings and has never needed the previous
    # Pack to satisfy the current schema. Parsing it here meant that adding a required
    # field made every already-published row unreadable and so unreplaceable: the control
    # that exists to make a change visible refused to run precisely when the change was
    # big enough to alter the shape of the file. See blocking.md B26.
    #
    # This weakens nothing about what is being WRITTEN. `parse_only` above still refuses
    # any Pack that does not satisfy the current schema, and it runs before this line.
    previous = await _previous_source(conn, venture_id, "live" if publish else "draft")
    changed = (
        _changed_lines(previous.yaml_source, yaml_source) if previous is not None else ()
    )

    if expect_changed_lines is not None and len(changed) != expect_changed_lines:
        raise PackDiffUnexpectedError(
            f"publishing {venture_id}@{pack_version} would change {len(changed)} "
            f"line(s), not the {expect_changed_lines} declared. Nothing was written. "
            "A source file can drift ahead of what is in force, so publishing it ships "
            "everything that drifted rather than what was approved. The differences:\n"
            + "\n".join(f"    - {b.strip()}\n    + {a.strip()}" for b, a in changed[:10])
        )

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
            # Abandoned, not superseded, and not deleted. A draft somebody replaced
            # is still a document somebody wrote - `office_app` has no DELETE on this
            # table by design - but it was never in force, so it did not supersede
            # anything and nothing superseded it.
            await cur.execute(
                "UPDATE business_pack SET status = 'abandoned', superseded_at = now() "
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

    # Recorded whatever the caller declared. A publish changes what the next run
    # provisions and voids every Gate 10 signature taken against the previous version's
    # artifacts; that it happened, and what it altered, is not optional to write down.
    await audit.write_event(
        event_type="pack_published" if publish else "pack_drafted",
        actor_type="human",
        actor_id=authored_by,
        venture_id=venture_id,
        subject={
            "pack_version": pack_version,
            "content_hash": row["content_hash"],
            "replaced_version": previous.pack_version if previous else None,
            "changed_line_count": len(changed),
            "declared_change_count": expect_changed_lines,
            "change_summary": change_summary,
            "changed_lines": [
                {"before": b.strip(), "after": a.strip()} for b, a in changed[:40]
            ],
        },
    )

    return StoredPack(
        venture_id=venture_id,
        pack_version=pack_version,
        content_hash=row["content_hash"],
        yaml_source=yaml_source,
        pack=pack,
        changed_lines=changed,
        replaced_version=previous.pack_version if previous else None,
    )


@dataclass(frozen=True)
class _PriorVersion:
    """The bytes of the version being replaced, and nothing parsed.

    Deliberately not a `StoredPack`: the whole point is that this row may have been
    stored under a schema this build cannot parse, and the publish diff does not care.
    """

    pack_version: str
    yaml_source: str


async def _previous_source(
    conn: AsyncConnection, venture_id: str, status: str
) -> _PriorVersion | None:
    """The row a publish or a draft-store is about to replace, unparsed."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT pack_version, yaml_source FROM business_pack "
            "WHERE venture_id = %s AND status = %s",
            (venture_id, status),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return _PriorVersion(
        pack_version=row["pack_version"], yaml_source=row["yaml_source"]
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
        pack=parse_only(
            row["yaml_source"],
            stored_as=f'{row["venture_id"]}@{row["pack_version"]}',
        ),
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
        pack=parse_only(
            row["yaml_source"],
            stored_as=f'{row["venture_id"]}@{row["pack_version"]}',
        ),
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
        pack=parse_only(
            row["yaml_source"],
            stored_as=f'{row["venture_id"]}@{row["pack_version"]}',
        ),
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
            "UPDATE business_pack SET status = 'abandoned', superseded_at = now() "
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
    """Every version, newest first, and what became of each.

    The section's own copy promises that "a run names the version it provisioned", and
    nothing delivered it: the history listed versions and the runs listed versions, and
    joining them was left to the reader. `superseded` was also doing too much work - a
    published version replaced by a later publish and a draft somebody abandoned are
    different events, and one word for both is why a superseded draft sitting above a
    live version reads as a broken sort.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT b.pack_version, b.content_hash, b.authored_by::text AS authored_by,
                   b.authored_at, b.superseded_at, b.status,
                   h.display_name AS author,
                   (SELECT count(*) FROM provisioning_run r
                     WHERE r.venture_id = b.venture_id
                       AND r.pack_version = b.pack_version)   AS runs,
                   (SELECT max(r.started_at) FROM provisioning_run r
                     WHERE r.venture_id = b.venture_id
                       AND r.pack_version = b.pack_version)   AS last_run_at
            FROM business_pack b
            LEFT JOIN office_human h ON h.human_id = b.authored_by
            WHERE b.venture_id = %s
            ORDER BY b.authored_at DESC
            """,
            (venture_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    # What replaced each superseded version: the next thing published after it. Read
    # from `status`, never guessed from the version string - `1.2.0` can be a draft and
    # `2.0.0-draft` can be a release, and a suffix is a naming convention rather than a
    # fact about what happened.
    released = sorted(
        (r for r in rows if r["status"] in ("live", "superseded")),
        key=lambda r: r["authored_at"],
    )

    for row in rows:
        row["superseded_by"] = None
        row["disposition"] = row["status"]

        if row["status"] == "abandoned":
            row["disposition"] = "abandoned draft"
            continue
        if row["status"] != "superseded":
            continue

        later = [r for r in released if r["authored_at"] > row["authored_at"]]
        if later:
            row["superseded_by"] = later[0]["pack_version"]
            row["disposition"] = f"superseded by {later[0]['pack_version']}"

    return rows


async def list_ventures(conn: AsyncConnection) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, pack_version, content_hash, authored_at "
            "FROM business_pack WHERE status = 'live' ORDER BY venture_id"
        )
        return [dict(r) for r in await cur.fetchall()]


def validation_state(report: Any) -> str:
    """`failing` / `not_validated` / `warnings` / `valid`.

    One implementation, because the directory and the editor must not be able to reach
    different conclusions about the same Pack - and `not_validated` is the whole point:
    a rule that could not run has validated nothing, and rendering that as `valid` is
    the single thing these screens exist to prevent.

    V24 is deferred rather than unrun. It is evaluated at Gate 4.5 against appointment
    output, which does not exist at Gate 2; counting it would make `not validated`
    permanent and `valid` unreachable.
    """
    if report.failures:
        return "failing"
    if [r for r in report.not_run if r.rule_id not in GATE_45_RULES]:
        return "not_validated"
    if report.warnings:
        return "warnings"
    return "valid"


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

        state = validation_state(report)

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
