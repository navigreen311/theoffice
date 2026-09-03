"""The Village roster, and the gap between it and The Office.

The Village creates agents. The Office appoints them. Those are different acts on
different systems, and the Agents page exists to show the distance between them - which
it could not, because The Office had nowhere to record who the Village has.

Two counts, and the difference is the point:

  village_agent            who exists. Imported from the Village's roster.
  office_agent_identity    who The Office can appoint, grant and certify.

An agent in the first and not the second is visible but unappointable. That is the state
179 of the Village's 186 agents are in, and a page rendering seven rows says the
opposite.

Nothing here creates an agent. `issue_identity` makes an existing Village agent
appointable; importing a roster records what the Village reports. The Office does not
have an "add agent" operation and must not grow one - it would be a second source of
truth for who exists, and the two would disagree within a week.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import audit, humans

# Roster work is authorised as `venture_operator`, unscoped. There are three roles in
# this system and a fourth is not warranted here: issuing an identity is an operator act
# with an audit entry, not a new kind of authority, and a role exists to express a
# distinction somebody enforces rather than to label a task.


class RosterError(Exception):
    """The roster could not be read, or the change could not be applied."""


# ---------------------------------------------------------------------- importing

def parse_roster(
    rows: list[dict[str, Any]],
    *,
    known_departments: Sequence[str] | None = None,
) -> list[dict[str, str]]:
    """Validate an incoming roster before anything is compared against it.

    A roster naming a department the Village does not have is not a roster this system
    can use: rule V29 validates a position's `source_department` against the same list,
    so an agent in an unknown department could never be appointed to anything. Rejecting
    the import is better than storing a row that is permanently unappointable for a
    reason the page cannot explain.

    `known_departments` is passed in rather than read here, and this function no longer
    holds a list of its own. The Office carried twelve names and nine of them stopped
    existing when the Village was rebuilt; a copy cannot know it has gone stale. When the
    caller has no list - the Village is unreachable - names are not checked and the
    import says so, because rejecting every row against a list nobody could read would
    be worse than accepting rows a later sync will correct.
    """
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    for index, row in enumerate(rows, start=1):
        ref = str(row.get("village_agent_ref") or "").strip()
        name = str(row.get("agent_name") or "").strip()
        department = str(row.get("department") or "").strip()

        if not ref:
            raise RosterError(f"row {index}: no village_agent_ref")
        if not name:
            raise RosterError(f"row {index} ({ref}): no agent_name")
        if not department:
            raise RosterError(
                f"row {index} ({ref}): no department. An agent with no department "
                f"could never be appointed to a position, because a position names the "
                f"department it draws from."
            )
        if known_departments is not None:
            from broker import departments as depts

            if depts.normalize(department) not in {
                depts.normalize(name) for name in known_departments
            }:
                raise RosterError(
                    f"row {index} ({ref}): {department!r} is not a Village department. "
                    f"A position's source_department is validated against the same list, "
                    f"so an agent in an unknown department could never be appointed. "
                    f"The Village has: {', '.join(sorted(known_departments))}."
                )
        if ref in seen:
            raise RosterError(f"row {index}: {ref} appears twice in this roster")

        seen.add(ref)
        out.append(
            {"village_agent_ref": ref, "agent_name": name, "department": department}
        )

    return out


async def diff(
    conn: AsyncConnection, incoming: list[dict[str, str]]
) -> dict[str, Any]:
    """What importing this roster would change. **Writes nothing.**

    Separate from applying it because a roster import can remove agents, and an agent
    that leaves the Village while holding grants is a revocation somebody has to perform
    rather than a row that quietly disappears. An operator confirms a diff; they do not
    confirm a promise that something reasonable will happen.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT village_agent_ref, agent_name, department, status "
            "FROM village_agent"
        )
        current = {r["village_agent_ref"]: dict(r) for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT i.village_agent_ref,
                   -- `count(g.grant_id)`, not `count(*)`: the LEFT JOIN gives an
                   -- identity with no grants one all-NULL row, and `g.revoked_at
                   -- IS NULL` is true of it - so `count(*)` reports 1 for an agent
                   -- holding none, in the diff somebody confirms a departure from.
                   count(g.grant_id) FILTER (WHERE g.revoked_at IS NULL)
                     AS live_grants
            FROM office_agent_identity i
            LEFT JOIN agent_forge_grant g ON g.office_agent_id = i.office_agent_id
            WHERE i.village_agent_ref IS NOT NULL
            GROUP BY i.village_agent_ref
            """
        )
        appointed = {r["village_agent_ref"]: int(r["live_grants"]) for r in await cur.fetchall()}

    incoming_by_ref = {row["village_agent_ref"]: row for row in incoming}

    added = [row for ref, row in incoming_by_ref.items() if ref not in current]
    departed = [
        {
            **row,
            # The consequence, named at the point of confirming. A departed agent still
            # holding grants is the case this whole confirmation step exists for.
            "live_grants": appointed.get(ref, 0),
            "has_identity": ref in appointed,
        }
        for ref, row in current.items()
        if ref not in incoming_by_ref and row["status"] == "active"
    ]
    moved = [
        {
            "village_agent_ref": ref,
            "agent_name": row["agent_name"],
            "from_department": current[ref]["department"],
            "to_department": row["department"],
        }
        for ref, row in incoming_by_ref.items()
        if ref in current and current[ref]["department"] != row["department"]
    ]
    renamed = [
        {
            "village_agent_ref": ref,
            "from_name": current[ref]["agent_name"],
            "to_name": row["agent_name"],
        }
        for ref, row in incoming_by_ref.items()
        if ref in current and current[ref]["agent_name"] != row["agent_name"]
    ]

    return {
        "added": sorted(added, key=lambda r: r["agent_name"]),
        "departed": sorted(departed, key=lambda r: r["agent_name"]),
        "moved": sorted(moved, key=lambda r: r["agent_name"]),
        "renamed": sorted(renamed, key=lambda r: r["to_name"]),
        "unchanged": len(incoming_by_ref) - len(added) - len(moved) - len(renamed),
        "incoming_total": len(incoming_by_ref),
        "current_total": len(current),
    }


async def apply(
    conn: AsyncConnection,
    incoming: list[dict[str, str]],
    *,
    human: humans.Human,
) -> dict[str, Any]:
    """Apply a roster. Never called without an operator having seen the diff.

    A departure marks the row `departed` and leaves it in place. Deleting it would take
    the evidence with it - an agent that left while holding grants is exactly the row
    somebody needs to find afterwards - and it would take the identity's join target
    with it too.
    """
    humans.authorize(human, required_role="venture_operator")

    summary = await diff(conn, incoming)

    async with conn.cursor() as cur:
        for row in incoming:
            await cur.execute(
                """
                INSERT INTO village_agent
                  (village_agent_ref, agent_name, department, status, source)
                VALUES (%s, %s, %s, 'active', 'import')
                ON CONFLICT (village_agent_ref) DO UPDATE
                SET agent_name   = EXCLUDED.agent_name,
                    department   = EXCLUDED.department,
                    status       = 'active',
                    departed_at  = NULL,
                    last_seen_at = now()
                """,
                (row["village_agent_ref"], row["agent_name"], row["department"]),
            )

        for row in summary["departed"]:
            await cur.execute(
                "UPDATE village_agent SET status = 'departed', departed_at = now() "
                "WHERE village_agent_ref = %s",
                (row["village_agent_ref"],),
            )
    await conn.commit()

    await audit.write_event(
        event_type="village_roster_imported",
        actor_type="human", actor_id=human.human_id, venture_id=None,
        subject={
            "added": len(summary["added"]),
            "departed": len(summary["departed"]),
            "moved": len(summary["moved"]),
            "total": summary["incoming_total"],
        },
    )
    return summary


# ------------------------------------------------------------------- identities

async def issue_identity(
    conn: AsyncConnection, village_agent_ref: str, *, human: humans.Human
) -> uuid.UUID:
    """Make a Village agent appointable.

    Not a create. The agent already exists; this records that The Office recognises it
    and can grant to it. Refused when there is no roster row, because an identity for an
    agent the Village has never reported is The Office inventing a colleague.
    """
    humans.authorize(human, required_role="venture_operator")

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT agent_name, department, status FROM village_agent "
            "WHERE village_agent_ref = %s",
            (village_agent_ref,),
        )
        agent = await cur.fetchone()
        if agent is None:
            raise RosterError(
                f"{village_agent_ref} is not in the Village roster. The Office does not "
                "create agents; import the roster first, or register the agent "
                "explicitly if the Village cannot report it."
            )
        if agent["status"] == "departed":
            raise RosterError(
                f"{village_agent_ref} has departed the Village. Issuing an identity "
                "would make a former colleague appointable."
            )

        await cur.execute(
            "SELECT office_agent_id FROM office_agent_identity "
            "WHERE village_agent_ref = %s",
            (village_agent_ref,),
        )
        existing = await cur.fetchone()
        if existing is not None:
            raise RosterError(f"{village_agent_ref} already holds an Office identity")

        office_agent_id = uuid.uuid4()
        await cur.execute(
            """
            INSERT INTO office_agent_identity
              (office_agent_id, village_agent_ref, agent_name, department, status)
            VALUES (%s, %s, %s, %s, 'active')
            """,
            (
                office_agent_id, village_agent_ref, agent["agent_name"],
                agent["department"],
            ),
        )
    await conn.commit()

    await audit.write_event(
        event_type="office_identity_issued",
        actor_type="human", actor_id=human.human_id, venture_id=None,
        subject={
            "office_agent_id": str(office_agent_id),
            "village_agent_ref": village_agent_ref,
            "department": agent["department"],
        },
    )
    return office_agent_id


async def register_village_agent(
    conn: AsyncConnection,
    *,
    village_agent_ref: str,
    agent_name: str,
    department: str,
    human: humans.Human,
) -> None:
    """Record a Village agent the roster import cannot see.

    Deliberately named for what it does. "Add agent" would imply The Office creates
    agents, which it does not - and a control that implied it would become a second
    source of truth for who exists.

    `village_agent_ref` is required for the same reason: without it there is nothing to
    reconcile against when a real roster does arrive, and the row becomes a permanent
    orphan that no import can ever confirm or retire.
    """
    humans.authorize(human, required_role="venture_operator")

    parsed = parse_roster([
        {
            "village_agent_ref": village_agent_ref,
            "agent_name": agent_name,
            "department": department,
        }
    ])[0]

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO village_agent
              (village_agent_ref, agent_name, department, status, source)
            VALUES (%s, %s, %s, 'active', 'manual')
            ON CONFLICT (village_agent_ref) DO NOTHING
            """,
            (parsed["village_agent_ref"], parsed["agent_name"], parsed["department"]),
        )
    await conn.commit()

    await audit.write_event(
        event_type="village_agent_registered",
        actor_type="human", actor_id=human.human_id, venture_id=None,
        subject={"village_agent_ref": village_agent_ref, "department": department},
    )


# ------------------------------------------------------------------ the directory

async def directory(
    conn: AsyncConnection,
    *,
    search: str | None = None,
    department: str | None = None,
    identity: str | None = None,
    grants: str | None = None,
    all_departments: Sequence[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """The whole roster, grouped by department, with every denominator real.

    The old page listed the seven agents holding an identity and stopped, so a reader
    concluded the Village has seven people. It has more, and the ones it has that The
    Office cannot appoint are the most consequential rows on the page: they are the work
    that has not been done.

    Every count here comes from the two tables. When no roster has been imported the
    roster total is zero and the page says the roster is unknown - which is a different
    statement from "the Village has seven agents", and is the reason this is not a
    hardcoded agent count.
    """

    # (department, label) pairs. Both, because they do different jobs: `department` is
    # normalized - `media_production` - and is what a row is grouped and filtered by,
    # and `label` is what the Village UI shows - `Media_Production` - and is the word an
    # operator reads. The page was rendering the first where the second belongs, which
    # `broker/departments` warns about in the docstring on the two accessors and which
    # nothing caught until the smoke script had a Village to ask.
    #
    # When the Village cannot be reached this is empty and the page renders no
    # departments at all. That is narrower than it sounds and the console says so
    # rather than implying the list is complete.
    if all_departments is None:
        from broker import departments as depts

        loaded = await depts.load()
        all_departments = tuple((d.department, d.label) for d in (loaded or ()))

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT v.village_agent_ref, v.agent_name, v.department, v.status,
                   v.source, v.departed_at,
                   i.office_agent_id::text AS office_agent_id,
                   i.status AS identity_status,
                   count(DISTINCT g.grant_id)
                     FILTER (WHERE g.revoked_at IS NULL)          AS live_grants,
                   count(DISTINCT g.grant_id)
                     FILTER (WHERE g.revoked_at IS NULL AND g.is_assignable)
                                                                  AS assignable_grants,
                   count(DISTINCT c.cert_id)
                     FILTER (WHERE c.state = 'certified')          AS certifications,
                   min(g.trust_tier)                              AS declared_tier,
                   min(c.certified_tier) FILTER (WHERE c.state = 'certified')
                                                                  AS certified_tier,
                   max(s.shift_start)                             AS last_shift
            FROM village_agent v
            LEFT JOIN office_agent_identity i
                   ON i.village_agent_ref = v.village_agent_ref
            LEFT JOIN agent_forge_grant g ON g.office_agent_id = i.office_agent_id
            LEFT JOIN certification c
                   ON c.unit = 'A' AND c.office_agent_id = i.office_agent_id
            LEFT JOIN shift_assignment s ON s.office_agent_id = i.office_agent_id
            GROUP BY v.village_agent_ref, v.agent_name, v.department, v.status,
                     v.source, v.departed_at, i.office_agent_id, i.status
            """
        )
        rows = [dict(r) for r in await cur.fetchall()]

        # Identities whose Village agent has never been imported. Not dropped: an agent
        # The Office has appointed and the roster cannot account for is a discrepancy,
        # and hiding it would make the two counts agree by losing a row.
        await cur.execute(
            """
            SELECT i.office_agent_id::text AS office_agent_id, i.agent_name,
                   i.department, i.village_agent_ref, i.status AS identity_status,
                   count(DISTINCT g.grant_id)
                     FILTER (WHERE g.revoked_at IS NULL)          AS live_grants,
                   count(DISTINCT g.grant_id)
                     FILTER (WHERE g.revoked_at IS NULL AND g.is_assignable)
                                                                  AS assignable_grants,
                   count(DISTINCT c.cert_id)
                     FILTER (WHERE c.state = 'certified')          AS certifications,
                   min(g.trust_tier)                              AS declared_tier,
                   min(c.certified_tier) FILTER (WHERE c.state = 'certified')
                                                                  AS certified_tier,
                   max(s.shift_start)                             AS last_shift
            FROM office_agent_identity i
            LEFT JOIN agent_forge_grant g ON g.office_agent_id = i.office_agent_id
            LEFT JOIN certification c
                   ON c.unit = 'A' AND c.office_agent_id = i.office_agent_id
            LEFT JOIN shift_assignment s ON s.office_agent_id = i.office_agent_id
            WHERE NOT EXISTS (
              SELECT 1 FROM village_agent v
              WHERE v.village_agent_ref = i.village_agent_ref
            )
            GROUP BY i.office_agent_id, i.agent_name, i.department,
                     i.village_agent_ref, i.status
            """
        )
        unmatched = [dict(r) for r in await cur.fetchall()]

    def shape(row: dict[str, Any], *, in_roster: bool) -> dict[str, Any]:
        has_identity = row.get("office_agent_id") is not None
        live = int(row.get("live_grants") or 0)
        certified = int(row.get("certifications") or 0)
        declared = row.get("declared_tier")
        certified_tier = row.get("certified_tier")

        return {
            "village_agent_ref": row.get("village_agent_ref"),
            "agent_name": row["agent_name"],
            "department": row["department"],
            "in_roster": in_roster,
            "roster_status": row.get("status", "unknown"),
            "source": row.get("source"),
            "office_agent_id": row.get("office_agent_id"),
            "has_identity": has_identity,
            "identity_status": row.get("identity_status"),
            "live_grants": live,
            "assignable_grants": int(row.get("assignable_grants") or 0),
            "certifications": certified,
            "declared_tier": declared,
            "certified_tier": certified_tier,
            # The Pack declares a ceiling; SimForge certifies what was earned; the
            # effective tier is the lower of the two. `None` for declared means no Pack
            # appoints this agent - which is not the same as a tier of zero, and the
            # console must not render the two the same way.
            "effective_tier": _effective(declared, certified_tier),
            "tier_inconsistent": _exceeds(certified_tier, declared),
            # The two facts the old page showed in unrelated columns.
            "certified_without_grants": certified > 0 and live == 0,
            "last_shift": (
                row["last_shift"].isoformat() if row.get("last_shift") else None
            ),
        }

    agents = [shape(row, in_roster=True) for row in rows]
    agents += [shape(row, in_roster=False) for row in unmatched]

    # Filters applied after shaping, so a filter sees the same derived state the reader
    # does - "certified with no grants" is not a column in either table.
    def keep(agent: dict[str, Any]) -> bool:
        if search and search.lower() not in agent["agent_name"].lower():
            return False
        if department and agent["department"] != department:
            return False
        if identity == "with" and not agent["has_identity"]:
            return False
        if identity == "without" and agent["has_identity"]:
            return False
        if grants == "with" and agent["live_grants"] == 0:
            return False
        if grants == "without" and agent["live_grants"] > 0:
            return False
        return not (
            grants == "certified_no_grants" and not agent["certified_without_grants"]
        )

    visible = sorted(
        (a for a in agents if keep(a)),
        key=lambda a: (a["department"], a["agent_name"]),
    )

    # Every department the Village reports, whether or not anybody in it has reached The
    # Office - a page rendering only the departments it found cannot say that nine of
    # them are empty. The pairs come from the Village; the label is what is rendered
    # and the name is what a row is grouped and filtered by.
    departments: list[dict[str, Any]] = []
    for name, label in all_departments:
        members = [a for a in agents if a["department"] == name]
        with_identity = [a for a in members if a["has_identity"]]
        departments.append({
            "department": name,
            "label": label,
            "in_roster": len(members),
            "with_identity": len(with_identity),
            "without_identity": len(members) - len(with_identity),
            "agents": [a for a in visible if a["department"] == name],
        })

    with_identity = [a for a in agents if a["has_identity"]]
    return {
        "agents": visible,
        "departments": departments,
        "departments_total": len(all_departments),
        "departments_represented": len(
            [d for d in departments if d["with_identity"]]
        ),
        "roster_total": len(rows),
        "roster_imported": len(rows) > 0,
        "with_identity": len(with_identity),
        "without_identity": len(
            [a for a in agents if a["in_roster"] and not a["has_identity"]]
        ),
        "unmatched_identities": len(unmatched),
        "capacity": {
            "certified_and_free": len(
                [a for a in with_identity if a["certifications"] and not a["live_grants"]]
            ),
            "holding_grants": len([a for a in with_identity if a["live_grants"]]),
            "not_yet_certified": len(
                [a for a in with_identity if not a["certifications"]]
            ),
            "no_identity": len([a for a in agents if not a["has_identity"]]),
        },
        "all_departments": [
            {"department": name, "label": label}
            for name, label in all_departments
        ],
    }


_TIER_ORDER = ("suggest", "propose", "auto_execute")


def _effective(declared: str | None, certified: str | None) -> str | None:
    """The lower of the two. `None` when nothing has been declared or certified."""
    present = [t for t in (declared, certified) if t in _TIER_ORDER]
    if not present:
        return None
    return min(present, key=_TIER_ORDER.index)


def _exceeds(certified: str | None, declared: str | None) -> bool:
    """Certified above the declared ceiling - the Pack is the ceiling, so this is wrong."""
    if certified not in _TIER_ORDER or declared not in _TIER_ORDER:
        return False
    return _TIER_ORDER.index(certified) > _TIER_ORDER.index(declared)


__all__ = [
    "RosterError",
    "apply",
    "diff",
    "directory",
    "issue_identity",
    "parse_roster",
    "register_village_agent",
]
