"""Reading the audit log as evidence rather than as a list.

Four things it could not do, all of which matter because every other page in this console
leans on this one.

**It reported a verification with no timestamp and no method.** "Chain integrity verified
over 1,157 entries" was an ad-hoc check run on page load and recorded nowhere, while the
scheduled control's last *recorded* result covered 73 entries from the previous day. Two
screens described the same property and disagreed, and the reader had no way to tell which
was evidence. `chain_state` reports the recorded verification - the same row the
Compliance page reads - so the two agree by construction, and says plainly how much of the
current log that verification actually covered.

**Every entry named `human` and no person.** That is a type, not an actor. 95 accounts
could have produced any of those rows, which defeats the only property this log exists to
provide.

**Fixtures dominated it.** 1,093 of 1,157 entries were written by accounts this project's
own test paths created. They are tagged and filtered, never deleted: the store is
append-only and filtering changes the view, not the record.

**Nothing could be expanded.** A hash chain nobody can check by eye is decoration, so
entry detail shows both hashes and confirms the link to the previous entry.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import account_origin, audit_events

PAGE_SIZE = 50

#: The sweep kind whose recorded result is the evidence this page reports.
CONTROL = "audit_chain"


async def chain_state(conn: AsyncConnection) -> dict[str, Any]:
    """What was verified, when, by what method, and how much of the log it covered.

    Deliberately reads the *recorded* control result rather than running a check. A page
    that verifies on load and reports the answer without recording it produces exactly
    the contradiction this replaced: a green badge here and `never_run` on Compliance,
    both true, describing the same property.

    The fraction is the part that was missing. A verification is evidence about the
    entries it covered, and reporting "verified" over a log that has grown by 1,084
    entries since is an unqualified claim about rows nothing has checked.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT sweep_run_id::text AS sweep_run_id, started_at, completed_at, "
            "       status, denominator, findings "
            "FROM sweep_run WHERE sweep_kind = %s AND status <> 'running' "
            "ORDER BY started_at DESC LIMIT 1",
            (CONTROL,),
        )
        recorded = await cur.fetchone()

        await cur.execute(
            "SELECT count(*) AS entries, max(audit_id) AS head_id FROM audit_log"
        )
        totals = await cur.fetchone()

        await cur.execute(
            "SELECT audit_id, entry_hash, prev_hash, ts FROM audit_log "
            "ORDER BY audit_id DESC LIMIT 1"
        )
        head = await cur.fetchone()

    entries = int((totals or {}).get("entries") or 0)
    verified = int((recorded or {}).get("denominator") or 0) if recorded else 0

    # Freshness, not zero-lag, is the signal. A live append-only log is always at least
    # one entry ahead of any verification - running one writes an audit entry of its own,
    # so `covers_whole_log` is false by one the instant it finishes. Treating that as a
    # warning would make the banner permanently amber, which is how a banner stops being
    # read. What matters is whether the recorded verification is inside the control's max
    # age, and the fraction is stated either way.
    from broker import sweeps

    max_age = sweeps.MAX_AGE.get(CONTROL)
    completed = (recorded or {}).get("completed_at")
    stale = True
    age_hours = None
    if completed is not None:
        from datetime import UTC, datetime

        age = datetime.now(UTC) - completed
        age_hours = round(age.total_seconds() / 3600, 1)
        stale = bool(max_age and age > max_age)

    return {
        "entries": entries,
        "verified_entries": verified,
        # The number the old badge never showed. Entries appended since the last
        # recorded verification have not been checked by anything that left a record.
        "unverified_entries": max(0, entries - verified),
        "covers_whole_log": bool(recorded) and verified >= entries,
        "recorded": bool(recorded),
        "ok": bool(recorded and recorded["status"] == "passed"),
        "stale": stale,
        "age_hours": age_hours,
        "max_age_days": max_age.days if max_age else None,
        # Green only when a recorded verification passed and is still inside its max
        # age. Everything else is stated rather than coloured over.
        "trustworthy": bool(recorded and recorded["status"] == "passed" and not stale),
        "status": (recorded or {}).get("status"),
        "verified_at": (recorded or {}).get("completed_at"),
        # Both this page and the scheduled control call `audit_log_verify_chain()`,
        # which re-computes every hash rather than checking the head. Said out loud
        # because "verified" means something different for each.
        "method": "full re-hash of every entry" if recorded else None,
        "reason": ((recorded or {}).get("findings") or {}).get("reason"),
        "tail_gap": ((recorded or {}).get("findings") or {}).get("tail_gap"),
        "head_hash": (head or {}).get("entry_hash"),
        "head_audit_id": (head or {}).get("audit_id"),
        "head_written_at": (head or {}).get("ts"),
        "control": CONTROL,
    }


def _fixture(row: dict[str, Any]) -> bool:
    """Whether this entry came from an account the test paths created.

    By actor rather than by guessing at the event sequence. The loop the smoke script
    runs does have a shape - persona, human, draft, proposal, incident, then a run that
    aborts at gate 4 - but a shape can be coincidental and an actor cannot: these rows
    were written by `smoke-1a2b3c4d`, and that is a fact rather than an inference.
    """
    return account_origin.origin_of(
        {"display_name": row.get("actor_name"), "email": row.get("actor_email")}
    ) == account_origin.TEST_FIXTURE


_SELECT = """
SELECT a.audit_id, a.event_type, a.actor_type, a.actor_id::text AS actor_id,
       a.venture_id, a.trace_id::text AS trace_id, a.ts,
       a.prev_hash, a.entry_hash, a.subject,
       h.display_name AS actor_name, h.email AS actor_email
FROM audit_log a
LEFT JOIN office_human h ON h.human_id = a.actor_id
"""


async def entries(
    conn: AsyncConnection,
    *,
    event_type: str | None = None,
    venture_id: str | None = None,
    trace_id: str | None = None,
    actor_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_fixtures: bool = False,
    page: int = 1,
) -> dict[str, Any]:
    """One page of the log, with the person who acted and the fixtures marked."""
    where = """
    WHERE (%(event_type)s::text IS NULL OR a.event_type = %(event_type)s)
      AND (%(venture_id)s::text IS NULL OR a.venture_id = %(venture_id)s)
      AND (%(trace_id)s::uuid IS NULL OR a.trace_id = %(trace_id)s::uuid)
      AND (%(actor_id)s::uuid IS NULL OR a.actor_id = %(actor_id)s::uuid)
      AND (%(since)s::date IS NULL OR a.ts >= %(since)s::date)
      AND (%(until)s::date IS NULL OR a.ts < (%(until)s::date + 1))
    """
    params = {
        "event_type": event_type, "venture_id": venture_id, "trace_id": trace_id,
        "actor_id": actor_id, "since": since, "until": until,
    }

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"{_SELECT} {where} ORDER BY a.audit_id DESC", params)
        matched = [dict(row) for row in await cur.fetchall()]

    for row in matched:
        row["fixture"] = _fixture(row)
        row["label"] = audit_events.label(row["event_type"])

    excluded = 0
    if not include_fixtures:
        before = len(matched)
        matched = [row for row in matched if not row["fixture"]]
        excluded = before - len(matched)

    total = len(matched)
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    start = (page - 1) * PAGE_SIZE

    return {
        "rows": matched[start:start + PAGE_SIZE],
        "total": total,
        "page": page,
        "pages": pages,
        "excluded_fixtures": excluded,
    }


async def detail(conn: AsyncConnection, audit_id: int) -> dict[str, Any] | None:
    """One entry, with its link to the previous one confirmed rather than asserted.

    The chain is only legible if a reader can check one link by eye: this entry's
    `prev_hash` against the previous entry's `entry_hash`. Showing both and saying
    whether they match is what turns a truncated hash column into evidence.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"{_SELECT} WHERE a.audit_id = %s", (audit_id,))
        row = await cur.fetchone()
        if row is None:
            return None
        entry = dict(row)

        await cur.execute(
            "SELECT audit_id, entry_hash FROM audit_log WHERE audit_id < %s "
            "ORDER BY audit_id DESC LIMIT 1",
            (audit_id,),
        )
        previous = await cur.fetchone()

        siblings: list[dict[str, Any]] = []
        if entry["trace_id"]:
            await cur.execute(
                "SELECT audit_id, event_type, ts FROM audit_log "
                "WHERE trace_id = %s::uuid ORDER BY audit_id LIMIT 50",
                (entry["trace_id"],),
            )
            siblings = [dict(r) for r in await cur.fetchall()]

    entry["fixture"] = _fixture(entry)
    entry["label"] = audit_events.label(entry["event_type"])
    entry["meaning"] = (
        audit_events.BY_TYPE[entry["event_type"]].meaning
        if entry["event_type"] in audit_events.BY_TYPE
        else "This event type is not in the published glossary."
    )
    entry["previous_audit_id"] = (previous or {}).get("audit_id")
    entry["previous_entry_hash"] = (previous or {}).get("entry_hash")
    # The link, checked here rather than described. The first entry has no predecessor,
    # which is a different thing from a broken link and says so.
    if previous is None:
        entry["links_to_previous"] = None
        entry["link_note"] = "This is the first entry; it has no predecessor to link to."
    else:
        entry["links_to_previous"] = entry["prev_hash"] == previous["entry_hash"]
        entry["link_note"] = (
            f"This entry's prev_hash matches entry {previous['audit_id']}'s hash."
            if entry["links_to_previous"]
            else f"This entry's prev_hash does NOT match entry {previous['audit_id']}."
        )
    entry["trace_siblings"] = siblings
    return entry


async def shape(
    conn: AsyncConnection, *, include_fixtures: bool = False, since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Counts before paging.

    1,157 rows with no aggregate means a spike in one event type is invisible until
    somebody pages far enough to notice, which nobody does.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""{_SELECT}
            WHERE (%(since)s::date IS NULL OR a.ts >= %(since)s::date)
              AND (%(until)s::date IS NULL OR a.ts < (%(until)s::date + 1))
            """,
            {"since": since, "until": until},
        )
        rows = [dict(row) for row in await cur.fetchall()]

    fixtures = sum(1 for row in rows if _fixture(row))
    if not include_fixtures:
        rows = [row for row in rows if not _fixture(row)]

    def tally(key: str) -> list[dict[str, Any]]:
        counts: dict[Any, int] = {}
        for row in rows:
            counts[row.get(key)] = counts.get(row.get(key), 0) + 1
        return sorted(
            (
                {
                    "value": value if value is not None else "—",
                    "label": audit_events.label(value) if key == "event_type" and value else None,
                    "count": count,
                }
                for value, count in counts.items()
            ),
            key=lambda item: -item["count"],
        )

    return {
        "counted": len(rows),
        "fixtures_excluded": 0 if include_fixtures else fixtures,
        "by_event_type": tally("event_type"),
        "by_actor": tally("actor_name"),
        "by_venture": tally("venture_id"),
    }


async def export_manifest(
    conn: AsyncConnection, *, filters: dict[str, Any], include_fixtures: bool,
) -> dict[str, Any]:
    """The header an export has to carry to be worth anything.

    Part 9 requires structured record export on demand. An export of a subset, produced
    from a log whose chain verification covers six per cent of it, is misleading unless
    it says both of those things on its face - exactly as the Compliance export already
    does.
    """
    state = await chain_state(conn)
    page = await entries(conn, include_fixtures=include_fixtures, **filters)

    caveats = []
    if not state["recorded"]:
        caveats.append(
            "The scheduled audit_chain control has never recorded a result, so nothing "
            "here has been verified by anything that left a record."
        )
    elif not state["covers_whole_log"]:
        caveats.append(
            f"The last recorded verification covered {state['verified_entries']} of "
            f"{state['entries']} entries. {state['unverified_entries']} entries have "
            "been appended since and are not covered by it."
        )
    if not state["ok"] and state["recorded"]:
        caveats.append("The last recorded verification did not pass.")
    if not include_fixtures and page["excluded_fixtures"]:
        caveats.append(
            f"{page['excluded_fixtures']} entries written by test-fixture accounts were "
            "excluded from this export. They remain in the record."
        )

    return {
        "filters": {key: value for key, value in filters.items() if value},
        "fixtures_included": include_fixtures,
        "fixtures_excluded": page["excluded_fixtures"],
        "entries_included": page["total"],
        "entries_in_log": state["entries"],
        "chain": {
            "recorded": state["recorded"],
            "status": state["status"],
            "verified_entries": state["verified_entries"],
            "unverified_entries": state["unverified_entries"],
            "verified_at": state["verified_at"],
            "method": state["method"],
            "head_hash": state["head_hash"],
        },
        "caveats": caveats,
        "rows": page["rows"],
    }
