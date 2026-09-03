"""Revocation at four scopes — the kill switch under Way 1.

Master prompt §1.4. With no front desk to stop and no queue to drain, revocation
is the only way to stop an agent that is already acting. Four scopes, each with a
different authority, all checked live on every call.

| Scope          | Effect                                   | Authority          |
|----------------|------------------------------------------|--------------------|
| agent_module   | one grant revoked                        | venture_operator   |
| agent          | agent cannot reach any Forge             | venture_operator   |
| venture        | all grants for that engagement           | compliance_officer |
| forge          | broker refuses all calls to that Forge    | ivan               |

Why a table and not more columns on `agent_forge_grant`: a Forge-wide revocation is
not a property of any single grant, and a venture-wide revocation must apply to
grants issued *after* it was declared. Storing it on the grant would silently miss
both, and the second is exactly how a revoked venture quietly comes back to life.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.errors import NotAuthorized, Revoked

# Ordered weakest to strongest. A stronger role may act at a weaker scope.
ROLE_RANK = {"venture_operator": 1, "compliance_officer": 2, "ivan": 3}

SCOPE_MIN_ROLE = {
    "agent_module": "venture_operator",
    "agent": "venture_operator",
    "venture": "compliance_officer",
    "forge": "ivan",
}


@dataclass(frozen=True, slots=True)
class ActiveRevocation:
    revocation_id: uuid.UUID
    scope: str
    reason: str
    revoked_at: str


_CHECK_SQL = """
SELECT revocation_id, scope, reason, revoked_at
FROM revocation
WHERE reinstated_at IS NULL
  AND (
        (scope = 'forge'        AND forge_id = %(forge_id)s)
     OR (scope = 'venture'      AND venture_id = %(venture_id)s)
     OR (scope = 'agent'        AND office_agent_id = %(agent_id)s)
     OR (scope = 'agent_module' AND office_agent_id = %(agent_id)s
                                AND forge_id = %(forge_id)s
                                AND module_id = %(module_id)s)
      )
ORDER BY CASE scope
           WHEN 'forge' THEN 1 WHEN 'venture' THEN 2
           WHEN 'agent' THEN 3 ELSE 4
         END
LIMIT 1
"""


async def check_revocations(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    forge_id: str,
    module_id: str,
    venture_id: str,
) -> None:
    """Raise `Revoked` if any scope covers this call.

    Broadest scope wins the report. An agent blocked by a Forge-wide revocation
    should be told that, not told its own grant is gone - the two call for
    completely different responses from whoever is watching.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _CHECK_SQL,
            {
                "agent_id": office_agent_id,
                "forge_id": forge_id,
                "module_id": module_id,
                "venture_id": venture_id,
            },
        )
        row = await cur.fetchone()

    if row is None:
        return

    raise Revoked(
        f"blocked by a {row['scope']} revocation",
        scope=row["scope"],
        revocation_id=str(row["revocation_id"]),
        reason=row["reason"],
    )


def assert_authority(scope: str, actor_role: str) -> None:
    """Check the actor may revoke at this scope.

    Enforced in code rather than as a CHECK constraint because the rule is about
    the *actor*, and the actor's role is not a column on the row being written -
    a row can claim any role, so the claim has to be verified where it is made.
    """
    if scope not in SCOPE_MIN_ROLE:
        raise NotAuthorized(f"unknown revocation scope {scope!r}", scope=scope)
    required = SCOPE_MIN_ROLE[scope]
    if ROLE_RANK.get(actor_role, 0) < ROLE_RANK[required]:
        raise NotAuthorized(
            f"{scope!r} revocation requires {required!r} or higher",
            scope=scope,
            actor_role=actor_role,
            required_role=required,
        )


async def revoke(
    conn: AsyncConnection,
    *,
    scope: str,
    reason: str,
    revoked_by: uuid.UUID,
    revoked_by_role: str,
    office_agent_id: uuid.UUID | None = None,
    forge_id: str | None = None,
    module_id: str | None = None,
    venture_id: str | None = None,
    commit: bool = True,
) -> uuid.UUID:
    """Record a revocation. Takes effect on the target's very next call.

    `commit=False` leaves the transaction open for a caller that is writing something
    this revocation has to be atomic with. `sync-roster` is the case: an agent marked
    departed and their grants revoked are one fact, and a commit between the two can
    leave a departed agent holding live authority. Nobody would be looking for that
    state, because the roster would say the agent is gone.
    """
    assert_authority(scope, revoked_by_role)

    # Counted before the write, inside the same transaction, so the figure is what this
    # revocation actually stopped. Recomputed later it would answer about today's grants,
    # and nothing in the number would show the difference.
    from psycopg.types.json import Jsonb

    radius = await blast_radius(
        conn,
        scope=scope,
        office_agent_id=office_agent_id,
        forge_id=forge_id,
        module_id=module_id,
        venture_id=venture_id,
    )

    revocation_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO revocation
              (revocation_id, scope, office_agent_id, forge_id, module_id, venture_id,
               reason, revoked_by, revoked_by_role, blast_radius)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                revocation_id, scope, office_agent_id, forge_id, module_id,
                venture_id, reason, revoked_by, revoked_by_role, Jsonb(radius),
            ),
        )
    if commit:
        await conn.commit()
    return revocation_id


async def reinstate(
    conn: AsyncConnection,
    *,
    revocation_id: uuid.UUID,
    reinstated_by: uuid.UUID,
    reinstated_by_role: str,
    reason: str,
    second_human: uuid.UUID | None = None,
) -> None:
    """Lift a revocation.

    §1.4: "re-enable requires a documented ritual and a named human." Both are
    required arguments here and both are NOT NULL-checked by the schema, so a
    reinstatement cannot be an anonymous UPDATE.

    Reinstating requires the same authority as revoking at that scope. Otherwise
    a venture operator could undo a compliance officer's venture-wide stop.
    """
    if not reason.strip():
        raise NotAuthorized("reinstatement requires a documented reason")

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT scope FROM revocation WHERE revocation_id = %s",
                          (revocation_id,))
        row = await cur.fetchone()
        if row is None:
            raise NotAuthorized("no such revocation", revocation_id=str(revocation_id))

        assert_authority(row["scope"], reinstated_by_role)

        # The ritual, at the scopes wide enough to need one. A venture or Forge stop was
        # one person's judgement about a portfolio; ending it should not be.
        if row["scope"] in TWO_HUMAN_SCOPES:
            if second_human is None:
                raise NotAuthorized(
                    f"lifting a {row['scope']} revocation needs a second named human",
                    scope=row["scope"],
                )
            if second_human == reinstated_by:
                raise NotAuthorized(
                    "the second human must be somebody else; naming yourself twice is "
                    "one person's judgement written down twice",
                    scope=row["scope"],
                )

        await cur.execute(
            "UPDATE revocation SET reinstated_at = now(), reinstated_by = %s, "
            "reinstatement_reason = %s, reinstatement_second_human = %s "
            "WHERE revocation_id = %s",
            (reinstated_by, reason, second_human, revocation_id),
        )
    await conn.commit()


# Scopes wide enough that ending one should not rest on a single person's judgement.
TWO_HUMAN_SCOPES = ("venture", "forge")

# Which target fields each scope actually uses. The console rendered all four inputs at
# once with hint text naming the scopes each applied to, which is documentation for
# whoever wrote the form rather than for whoever is using it at the moment it matters.
SCOPE_FIELDS = {
    "agent_module": ("office_agent_id", "forge_id", "module_id"),
    "agent": ("office_agent_id",),
    "venture": ("venture_id",),
    "forge": ("forge_id",),
}

SCOPE_EFFECT = {
    "agent_module": "One grant revoked.",
    "agent": "This agent cannot reach any Forge.",
    "venture": "Every grant for this engagement, including ones issued later.",
    "forge": "The broker refuses all calls to this Forge, for every agent.",
}


async def blast_radius(
    conn: AsyncConnection,
    *,
    scope: str,
    office_agent_id: uuid.UUID | None = None,
    forge_id: str | None = None,
    module_id: str | None = None,
    venture_id: str | None = None,
) -> dict[str, Any]:
    """What this revocation would stop, counted before it is issued.

    Revoking at venture scope stops every grant for an engagement. At forge scope the
    broker refuses every call to that Forge for every agent in the portfolio. Neither
    number was visible before clicking a red button, and "revoke" is the same word for
    both.

    This is a query against existing state, not an authorization decision. Showing an
    operator what they are about to stop does not re-implement the rule about whether
    they may - the API still decides that, once, and reports the refusal.
    """
    if scope not in SCOPE_MIN_ROLE:
        raise NotAuthorized(f"unknown revocation scope {scope!r}", scope=scope)

    # One predicate per scope, matching `_CHECK_SQL` exactly. The two are checked against
    # each other by test: a blast radius computed from a different rule than the one the
    # broker enforces is a number that reassures without describing anything.
    where = {
        "agent_module": (
            "g.office_agent_id = %(agent_id)s AND g.forge_id = %(forge_id)s "
            "AND g.module_id = %(module_id)s"
        ),
        "agent": "g.office_agent_id = %(agent_id)s",
        "venture": "g.venture_id = %(venture_id)s",
        "forge": "g.forge_id = %(forge_id)s",
    }[scope]

    params = {
        "agent_id": office_agent_id,
        "forge_id": forge_id,
        "module_id": module_id,
        "venture_id": venture_id,
    }

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            SELECT count(*) AS grants,
                   count(DISTINCT g.office_agent_id) AS agents,
                   count(DISTINCT g.venture_id) AS ventures
            FROM agent_forge_grant g
            WHERE g.revoked_at IS NULL AND {where}
            """,
            params,
        )
        grants = dict(await cur.fetchone() or {})

        # A call with no end time is still running. It fails at its next broker check,
        # which is the difference between "stopped" and "will stop".
        call_where = where.replace("g.", "c.")
        await cur.execute(
            f"""
            SELECT count(*) AS in_flight
            FROM agent_call_ledger c
            WHERE c.ts_end IS NULL AND {call_where}
            """,
            params,
        )
        in_flight = dict(await cur.fetchone() or {})

        # Shifts are per agent and venture; a Forge-scoped revocation does not map onto
        # one, and reporting zero there would read as "no shifts affected" rather than
        # "this scope does not work that way".
        shifts: int | None = None
        if scope in ("agent_module", "agent", "venture"):
            shift_where = {
                "agent_module": "s.office_agent_id = %(agent_id)s",
                "agent": "s.office_agent_id = %(agent_id)s",
                "venture": "s.venture_id = %(venture_id)s",
            }[scope]
            await cur.execute(
                f"""
                SELECT count(*) AS shifts
                FROM shift_assignment s
                WHERE {shift_where}
                  AND s.shift_start < now() + interval '1 day'
                  AND s.shift_end > now()
                """,
                params,
            )
            row = await cur.fetchone()
            shifts = int(row["shifts"]) if row else 0

    forward: str | None = None
    if scope == "venture":
        forward = "Also blocks grants issued to this engagement after the revocation."
    elif scope == "forge":
        forward = (
            "Also blocks every future call to this Forge, from every venture, until "
            "it is re-enabled."
        )

    return {
        "scope": scope,
        "effect": SCOPE_EFFECT[scope],
        "required_role": SCOPE_MIN_ROLE[scope],
        "agents": int(grants.get("agents") or 0),
        "grants": int(grants.get("grants") or 0),
        "ventures": int(grants.get("ventures") or 0),
        "in_flight_calls": int(in_flight.get("in_flight") or 0),
        "shifts_today": shifts,
        "forward_looking": forward,
        "needs_two_humans_to_lift": scope in TWO_HUMAN_SCOPES,
    }


async def history(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Every revocation ever issued, lifted or not.

    Separate from the active list on purpose. The active list answers "what is stopped
    right now"; this answers "what has this system ever stopped, why, and for how long",
    which is the regulator-export question the reason field was always specified for.

    A lifted revocation stays here in full. Re-enabling appends an account; it does not
    remove the record, because a history that looks cleaner than the truth is worse than
    no history.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.revocation_id::text AS revocation_id, r.scope, r.reason,
                   r.office_agent_id::text AS office_agent_id, r.forge_id, r.module_id,
                   r.venture_id, r.revoked_at, r.revoked_by_role,
                   r.revoked_by::text AS revoked_by,
                   actor.display_name AS revoked_by_name,
                   r.reinstated_at, r.reinstatement_reason,
                   r.reinstated_by::text AS reinstated_by,
                   lifter.display_name AS reinstated_by_name,
                   r.reinstatement_second_human::text AS second_human,
                   second.display_name AS second_human_name,
                   r.blast_radius,
                   agent.agent_name,
                   COALESCE(r.reinstated_at, now()) - r.revoked_at AS duration
            FROM revocation r
            LEFT JOIN office_human actor ON actor.human_id = r.revoked_by
            LEFT JOIN office_human lifter ON lifter.human_id = r.reinstated_by
            LEFT JOIN office_human second
                   ON second.human_id = r.reinstatement_second_human
            LEFT JOIN office_agent_identity agent
                   ON agent.office_agent_id = r.office_agent_id
            ORDER BY r.revoked_at DESC
            """
        )
        rows = []
        for row in await cur.fetchall():
            item = dict(row)
            duration = item.pop("duration")
            item["duration_hours"] = round(duration.total_seconds() / 3600, 1)
            item["active"] = item["reinstated_at"] is None
            rows.append(item)
        return rows


async def targets(conn: AsyncConnection) -> dict[str, list[dict[str, Any]]]:
    """What can be revoked, by name.

    The form asked for four UUIDs as free text. This is the emergency control: recalling
    a UUID under pressure is not a thing anybody does, and a typo either fails or revokes
    something else, which is the worse of the two outcomes.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT i.office_agent_id::text AS id, i.agent_name AS name,
                   i.department AS detail, i.status
            FROM office_agent_identity i
            WHERE i.revoked_at IS NULL
            ORDER BY i.agent_name
            """
        )
        agents = [dict(row) for row in await cur.fetchall()]

        await cur.execute(
            """
            SELECT v.slug AS id, v.display_name AS name,
                   v.lifecycle_state AS detail
            FROM venture v
            WHERE v.archived_at IS NULL
            ORDER BY v.display_name
            """
        )
        ventures = [dict(row) for row in await cur.fetchall()]

        # Forges and modules come from what is actually granted plus what is registered,
        # so a Forge with no grants can still be stopped before it has any.
        await cur.execute(
            """
            SELECT f.forge_id AS id, f.display_name AS name, f.health_status AS detail
            FROM forge_registry f
            ORDER BY f.forge_id
            """
        )
        forges = [dict(row) for row in await cur.fetchall()]

        await cur.execute(
            """
            SELECT DISTINCT g.forge_id, g.module_id,
                   g.office_agent_id::text AS office_agent_id
            FROM agent_forge_grant g
            WHERE g.revoked_at IS NULL
            ORDER BY g.forge_id, g.module_id
            """
        )
        grants = [dict(row) for row in await cur.fetchall()]

    return {
        "agents": agents,
        "ventures": ventures,
        "forges": forges,
        "grants": grants,
    }
