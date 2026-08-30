"""`office sync-roster` — the Village's roster, diffed and applied on confirmation.

A one-time import is a mechanism that describes the roster on the day somebody ran it.
The Village hires, promotes, retires and kills agents continuously: an agent dies on a
mortality roll and the Village auto-hires into the vacated seat, and The Office finds out
when somebody notices. This is the thing that is meant to be run again.

WHAT A SYNC REPORTS

    new           in the Village, not here
    departed      here, not in the Village any more
    department    moved between departments
    role          moved on the role ladder
    reporting     manager changed

    Every one of those has a consequence and the report says which. A departure is the
    serious one: it revokes grants, which is why nothing is applied without confirmation
    and why a sync will not run at all against a Village that did not answer.

WHY IT NEVER APPLIES SILENTLY

    The diff is computed against whatever the Village says right now. If the Village were
    briefly unreachable and this fell back to a cached roster, every agent would look
    departed and every grant would be revoked. `village.roster(degrade=False)` refuses to
    serve a cached answer for exactly that reason, and this module refuses to apply a
    diff it did not just compute.

WHAT A NEW OCCUPANT INHERITS

    Nothing. Grants and certifications key on `office_agent_id`, never on a position, so
    an agent hired into a vacated seat arrives `never_certified` and holds nothing. That
    is the point: the seat is not the thing that was trusted, the agent was.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, village


class SyncError(Exception):
    """The roster could not be read, or the change could not be applied."""


@dataclass
class Change:
    """One agent's difference between the Village and The Office."""

    kind: str  # new | departed | department | role | reporting
    village_agent_ref: str
    agent_name: str
    detail: str


@dataclass
class Diff:
    """What a sync would do. Nothing here has been applied."""

    village_total: int = 0
    office_total: int = 0
    changes: list[Change] = field(default_factory=list)

    def of(self, kind: str) -> list[Change]:
        return [c for c in self.changes if c.kind == kind]

    @property
    def empty(self) -> bool:
        return not self.changes

    def summary(self) -> dict[str, Any]:
        return {
            "village_total": self.village_total,
            "office_total": self.office_total,
            "new": len(self.of("new")),
            "departed": len(self.of("departed")),
            "department_changes": len(self.of("department")),
            "role_changes": len(self.of("role")),
            "reporting_changes": len(self.of("reporting")),
            "changes": [
                {
                    "kind": c.kind,
                    "village_agent_ref": c.village_agent_ref,
                    "agent_name": c.agent_name,
                    "detail": c.detail,
                }
                for c in self.changes
            ],
        }


async def _village_roster() -> dict[str, dict[str, Any]]:
    """The Village's roster, keyed by ref. Never a cached answer."""
    try:
        answer = await village.roster(degrade=False)
    except village.VillageUnreachableError as exc:
        raise SyncError(
            f"the Village did not answer ({exc}). Nothing was compared and nothing was "
            "changed - a sync against a cached roster would report every agent as "
            "departed, and a departure revokes grants."
        ) from exc

    agents = answer.data.get("agents") or []
    if not agents:
        raise SyncError(
            "the Village returned an empty roster. Refusing to treat that as 186 "
            "departures."
        )
    return {a["agent_id"]: a for a in agents}


async def _office_roster(conn: AsyncConnection) -> dict[str, dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT village_agent_ref, agent_name, department, role_key, reports_to, "
            "       status "
            "FROM village_agent"
        )
        return {r["village_agent_ref"]: dict(r) for r in await cur.fetchall()}


async def diff(conn: AsyncConnection) -> Diff:
    """What has changed. Reads both sides and writes nothing."""
    village_rows = await _village_roster()
    office_rows = await _office_roster(conn)

    result = Diff(village_total=len(village_rows), office_total=len(office_rows))

    for ref, agent in sorted(village_rows.items()):
        here = office_rows.get(ref)
        name = agent.get("lore_name") or ref
        if here is None:
            result.changes.append(Change(
                "new", ref, name,
                f"{agent.get('department')} · {agent.get('role_key')}",
            ))
            continue

        if (here.get("department") or "") != (agent.get("department") or ""):
            result.changes.append(Change(
                "department", ref, name,
                f"{here.get('department')} -> {agent.get('department')}",
            ))
        if (here.get("role_key") or "") != (agent.get("role_key") or ""):
            result.changes.append(Change(
                "role", ref, name,
                f"{here.get('role_key')} -> {agent.get('role_key')}",
            ))
        if (here.get("reports_to") or "") != (agent.get("reports_to_id") or ""):
            result.changes.append(Change(
                "reporting", ref, name,
                f"{here.get('reports_to') or 'nobody'} -> "
                f"{agent.get('reports_to_id') or 'nobody'}",
            ))

    for ref, here in sorted(office_rows.items()):
        if ref not in village_rows:
            result.changes.append(Change(
                "departed", ref, here.get("agent_name") or ref,
                "no longer in the Village roster; any grants this agent holds are "
                "revoked when this is applied",
            ))

    return result


async def apply(
    conn: AsyncConnection, *, actor: uuid.UUID, confirmed: bool = False
) -> dict[str, Any]:
    """Apply the diff. Refuses without an explicit confirmation.

    Recomputed here rather than taking a diff the caller made earlier: between showing a
    diff and confirming it, the Village may have hired somebody, and applying a stale
    diff would write a roster that never existed on either side.
    """
    if not confirmed:
        raise SyncError(
            "sync-roster changes who may act in this system and will not run without "
            "--confirm. Run it without the flag first to see the diff."
        )

    changes = await diff(conn)
    village_rows = await _village_roster()

    async with conn.cursor() as cur:
        for ref, agent in village_rows.items():
            await cur.execute(
                """
                INSERT INTO village_agent
                  (village_agent_ref, agent_name, department, role_key, reports_to,
                   title, status, source)
                -- 'import', not 'village_api': village_agent_source_check
                -- permits only ('import','manual'), and broker/roster.py
                -- already writes 'import' into this same column. The audit
                -- event below still records source=village_api, which is
                -- where that distinction belongs.
                VALUES (%s, %s, %s, %s, %s, %s, 'active', 'import')
                ON CONFLICT (village_agent_ref) DO UPDATE SET
                  agent_name = EXCLUDED.agent_name,
                  department = EXCLUDED.department,
                  role_key = EXCLUDED.role_key,
                  reports_to = EXCLUDED.reports_to,
                  title = EXCLUDED.title,
                  status = 'active',
                  last_seen_at = now(),
                  departed_at = NULL
                """,
                (
                    ref,
                    agent.get("lore_name") or ref,
                    agent.get("department"),
                    agent.get("role_key"),
                    agent.get("reports_to_id"),
                    agent.get("title"),
                ),
            )

        departed = [c.village_agent_ref for c in changes.of("departed")]
        if departed:
            # Marked, not deleted. An agent who left is a fact about the past, and the
            # grants they held are the reason anybody would look them up later.
            await cur.execute(
                "UPDATE village_agent SET status = 'departed', departed_at = now() "
                "WHERE village_agent_ref = ANY(%s)",
                (departed,),
            )

        # An identity whose agent changed department follows it. The identity is the same
        # agent; the department is a property of where they now sit.
        await cur.execute(
            """
            UPDATE office_agent_identity i
               SET department = v.department,
                   role_key = v.role_key,
                   reports_to = v.reports_to,
                   agent_name = v.agent_name
              FROM village_agent v
             WHERE v.village_agent_ref = i.village_agent_ref
            """
        )

    # The audit entry is written in the same transaction as the rows it describes, and
    # one commit covers both.
    #
    # It used to commit the roster first and then write the audit entry. A failure in
    # between - and the first run of this hit one, a CHECK on `village_agent.source` -
    # left the identity table changed with nothing recording who changed it. An
    # unauditable write to the table that says who may act in this system is the one
    # outcome this command must not be able to produce, so it is now impossible rather
    # than unlikely: either both land or neither does.
    await audit.write_event(
        event_type="village_roster_imported",
        actor_type="human",
        actor_id=actor,
        subject={
            "source": "village_api",
            **changes.summary(),
        },
        conn=conn,
    )
    await conn.commit()

    return {"applied": True, **changes.summary()}
