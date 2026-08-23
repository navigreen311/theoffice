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
) -> uuid.UUID:
    """Record a revocation. Takes effect on the target's very next call."""
    assert_authority(scope, revoked_by_role)

    revocation_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO revocation
              (revocation_id, scope, office_agent_id, forge_id, module_id, venture_id,
               reason, revoked_by, revoked_by_role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                revocation_id, scope, office_agent_id, forge_id, module_id,
                venture_id, reason, revoked_by, revoked_by_role,
            ),
        )
    await conn.commit()
    return revocation_id


async def reinstate(
    conn: AsyncConnection,
    *,
    revocation_id: uuid.UUID,
    reinstated_by: uuid.UUID,
    reinstated_by_role: str,
    reason: str,
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

        await cur.execute(
            "UPDATE revocation SET reinstated_at = now(), reinstated_by = %s, "
            "reinstatement_reason = %s WHERE revocation_id = %s",
            (reinstated_by, reason, revocation_id),
        )
    await conn.commit()
