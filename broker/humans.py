"""Human identity, role scoping, and gate sign-offs.

Master prompt Part 14. "Named-human accountability — humans sign, not agents."

Until now every governance action took a `UUID` for the actor and a role *string*, and
trusted the caller about both. This module is where that stops.

Two things worth reading before changing anything here:

**A role is scoped to a venture.** `revocation.assert_authority` answers "is this role
strong enough for this scope". It cannot answer "is this person an operator of *this*
venture", because it only ever sees a role string. `authorize()` answers both, and the
second question is the one that stops a venture operator revoking in a venture they have
nothing to do with.

**A sign-off is void by comparison.** Part 14: "artifact change voids signature." The
record stores the hash of what was signed, and `signoff_status()` compares it to the
artifact now. Nothing has to remember to revoke anything — the same property that makes
certification staleness reliable rather than aspirational.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.errors import NotAuthorized
from broker.revocation import ROLE_RANK

ALL_VENTURES = "*"


@dataclass(frozen=True, slots=True)
class Human:
    human_id: uuid.UUID
    display_name: str
    email: str
    status: str
    roles: tuple[tuple[str, str | None], ...]
    """(role, venture_id). `venture_id` None means every venture."""

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def strongest_role(self, venture_id: str | None = None) -> str | None:
        """The strongest role this human holds that applies to `venture_id`."""
        applicable = [
            role
            for role, scope in self.roles
            if scope is None or venture_id is None or scope == venture_id
        ]
        if not applicable:
            return None
        return max(applicable, key=lambda r: ROLE_RANK.get(r, 0))


def hash_token(token: str) -> str:
    """SHA-256 of the bearer token.

    Not a password KDF, deliberately: these are high-entropy machine-generated tokens,
    not human-chosen secrets, so stretching buys nothing an attacker cannot skip. If
    tokens ever become human-chosen this must become argon2 and the comment must go.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token() -> str:
    return secrets.token_urlsafe(32)


async def create_human(
    conn: AsyncConnection,
    *,
    display_name: str,
    email: str,
    auth_method: str = "sso_mfa",
    token: str | None = None,
) -> tuple[uuid.UUID, str]:
    """Create a human and return (human_id, plaintext token).

    The plaintext is returned exactly once and never stored. A caller that loses it
    issues a new one; a system that can recover it is a system where the hash was
    pointless.
    """
    human_id = uuid.uuid4()
    plaintext = token or issue_token()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "token_hash) VALUES (%s, %s, %s, %s, %s)",
            (human_id, display_name, email, auth_method, hash_token(plaintext)),
        )
    await conn.commit()
    return human_id, plaintext


async def grant_role(
    conn: AsyncConnection,
    *,
    human_id: uuid.UUID,
    role: str,
    granted_by: uuid.UUID,
    venture_id: str | None = None,
) -> None:
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_human_role (human_id, role, venture_id, granted_by) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (human_id, role, venture_id, granted_by),
        )
    await conn.commit()


async def authenticate(conn: AsyncConnection, token: str) -> Human | None:
    """Resolve a bearer token to a human, with roles.

    Status is read live rather than baked into the token. A suspended human must be
    refused on their next request, not their next session - the same rule revocation
    follows for agents, and for the same reason.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id, h.display_name, h.email, h.status,
                   COALESCE(
                     array_agg(ARRAY[r.role, COALESCE(r.venture_id, '')])
                       FILTER (WHERE r.role IS NOT NULL),
                     '{}'
                   ) AS roles
            FROM office_human h
            LEFT JOIN office_human_role r
              ON r.human_id = h.human_id AND r.revoked_at IS NULL
            WHERE h.token_hash = %s
            GROUP BY h.human_id, h.display_name, h.email, h.status
            """,
            (hash_token(token),),
        )
        row = await cur.fetchone()

    if row is None:
        return None

    # Presence, recorded where authentication happens rather than inferred from the
    # audit log. 178 of 179 accounts had never signed in and the roster had no column
    # for it, so a page full of accounts nobody has ever used looked like a team.
    #
    # Written on its own connection state and committed here: the caller's transaction
    # may go on to fail for reasons that have nothing to do with whether this person
    # turned up, and a request that is refused is still a request they made.
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human SET last_seen_at = now() WHERE human_id = %s",
            (row["human_id"],),
        )
    await conn.commit()

    roles = tuple(
        (pair[0], pair[1] or None) for pair in (row["roles"] or [])
    )
    return Human(
        human_id=row["human_id"],
        display_name=row["display_name"],
        email=row["email"],
        status=row["status"],
        roles=roles,
    )


def authorize(human: Human, *, required_role: str, venture_id: str | None = None) -> str:
    """Check role strength AND venture scope. Returns the role acted as.

    Two questions, and the second is the one a role string alone cannot answer:
    "is this role strong enough for this action" and "is this person an operator of
    *this* venture". Both, or neither means anything.
    """
    if not human.is_active:
        raise NotAuthorized(
            f"{human.display_name} is {human.status}", human_status=human.status
        )

    held = human.strongest_role(venture_id)
    if held is None:
        raise NotAuthorized(
            "no role in this venture",
            venture_id=venture_id,
            required_role=required_role,
        )
    if ROLE_RANK[held] < ROLE_RANK[required_role]:
        raise NotAuthorized(
            f"{held!r} is not sufficient; {required_role!r} or higher required",
            held_role=held,
            required_role=required_role,
            venture_id=venture_id,
        )
    return held


# ------------------------------------------------------- administering humans

def assert_may_grant(
    actor: Human,
    *,
    role: str,
    target: Human | None = None,
    revoking: bool = False,
) -> str:
    """Who may hand out which role, and to whom.

    **Strictly stronger, except at the top.** `compliance_officer` grants
    `venture_operator`; a `venture_operator` grants nothing. Not "stronger or equal",
    which would let a compliance officer mint another compliance officer and make the
    role self-propagating - at which point the hierarchy describes nothing.

    `ivan` is the exception, and it has to be. Nothing outranks it, so applying the rule
    literally would make the top role **ungrantable and unremovable by anybody** - and
    since the bootstrap CLI refuses once one human exists, there could never be a second
    administrator at all. That is not a restriction, it is a single point of failure with
    no recovery. Found by writing the test for the rule and watching a legitimate
    demotion get refused.

    Refusing it also buys nothing: a holder of `ivan` already has total authority over
    this system. What actually constrains the top role is the other two rules -
    **never to yourself**, so every role anyone holds was granted by somebody else and
    the audit log says who; and the last active administrator cannot be removed, so the
    system can never become unadministrable.
    """
    if role not in ROLE_RANK:
        raise NotAuthorized(f"unknown role {role!r}", role=role)
    if not actor.is_active:
        raise NotAuthorized(f"{actor.display_name} is {actor.status}")

    held = actor.strongest_role()
    top = max(ROLE_RANK.values())
    sufficient = held is not None and (
        ROLE_RANK[held] > ROLE_RANK[role]
        # The top role manages its own rank, because nothing outranks it and the
        # alternative is a role no one can ever grant.
        or (ROLE_RANK[held] == top and ROLE_RANK[role] == top)
    )
    if not sufficient:
        raise NotAuthorized(
            f"granting {role!r} requires a strictly stronger role; you hold "
            f"{held or 'none'}. Equal-strength granting would make the role "
            "self-propagating - except at the top, where nothing outranks it.",
            held_role=held,
            granting_role=role,
        )
    assert held is not None  # narrowed by `sufficient`; mypy cannot see it

    # Self-targeting is forbidden for a grant and allowed for a revocation. Granting
    # yourself is escalation; dropping your own role is not, and refusing it would both
    # be over-broad and produce a message about granting for somebody who was removing.
    # What stops an administrator removing their own last administrator role is
    # `assert_not_the_last_administrator`, which is the rule that actually applies.
    if not revoking and target is not None and target.human_id == actor.human_id:
        raise NotAuthorized(
            "nobody grants themselves a role, including ivan. Every role anyone holds "
            "was granted by somebody else, and that is what makes the audit trail "
            "answer 'who decided this'.",
            granting_role=role,
        )
    return held


async def count_active_administrators(
    conn: AsyncConnection, *, excluding: uuid.UUID | None = None
) -> int:
    """Active humans holding `ivan`. The number that must never reach zero."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT count(DISTINCT h.human_id)
            FROM office_human h
            JOIN office_human_role r
              ON r.human_id = h.human_id AND r.revoked_at IS NULL
            WHERE h.status = 'active' AND r.role = 'ivan'
              AND (%s::uuid IS NULL OR h.human_id <> %s)
            """,
            (excluding, excluding),
        )
        row = await cur.fetchone()
    assert row is not None
    return int(row[0])


async def assert_not_the_last_administrator(
    conn: AsyncConnection, *, human_id: uuid.UUID, action: str
) -> None:
    """Refuse anything that would leave the system with no administrator.

    An availability control rather than a security one, and worth as much: a system with
    no `ivan` cannot appoint one, and the only recovery is a shell on the database -
    which is exactly the dependency this whole module exists to remove.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM office_human_role WHERE human_id = %s AND role = 'ivan' "
            "AND revoked_at IS NULL",
            (human_id,),
        )
        is_admin = await cur.fetchone() is not None
    if not is_admin:
        return
    if await count_active_administrators(conn, excluding=human_id) == 0:
        raise NotAuthorized(
            f"refusing to {action}: this is the last active administrator, and a "
            "system with no administrator cannot appoint one.",
            human_id=str(human_id),
        )


async def revoke_role(
    conn: AsyncConnection,
    *,
    human_id: uuid.UUID,
    role: str,
    revoked_by: uuid.UUID,
    venture_id: str | None = None,
) -> bool:
    """Remove a role, keeping the record of it. Returns whether one was live.

    A soft delete, the same shape `playbook_share` uses. Deleting the row would destroy
    the answer to "who had this, who gave it to them, and who took it away" - and that
    question is the entire justification for forbidding self-grants.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human_role SET revoked_at = now(), revoked_by = %s "
            "WHERE human_id = %s AND role = %s "
            "AND COALESCE(venture_id, '*') = COALESCE(%s, '*') "
            "AND revoked_at IS NULL",
            (revoked_by, human_id, role, venture_id),
        )
        removed = cur.rowcount
    await conn.commit()
    return removed > 0


async def set_status(
    conn: AsyncConnection, *, human_id: uuid.UUID, status: str, actor: uuid.UUID
) -> None:
    """Suspend or reactivate.

    Status is read live on every request, so a suspension takes effect on the suspended
    human's next call rather than their next session - the same rule agent revocation
    follows, for the same reason.
    """
    if status not in ("active", "suspended"):
        raise NotAuthorized(f"unknown status {status!r}", status=status)

    async with conn.cursor() as cur:
        if status == "suspended":
            await cur.execute(
                "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
                "suspended_by = %s WHERE human_id = %s",
                (actor, human_id),
            )
        else:
            await cur.execute(
                "UPDATE office_human SET status = 'active', suspended_at = NULL, "
                "suspended_by = NULL WHERE human_id = %s",
                (human_id,),
            )
    await conn.commit()


async def reissue_token(conn: AsyncConnection, *, human_id: uuid.UUID) -> str:
    """Replace the token. The old one stops working the moment this returns.

    The API has never had rotation: a token was valid until its human was suspended.
    Returned in plaintext exactly once, like the original - a system that can show it
    again is a system where hashing it was pointless.
    """
    plaintext = issue_token()
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human SET token_hash = %s WHERE human_id = %s",
            (hash_token(plaintext), human_id),
        )
        if cur.rowcount == 0:
            raise NotAuthorized("no such human", human_id=str(human_id))
    await conn.commit()
    return plaintext


async def get_human(conn: AsyncConnection, human_id: uuid.UUID) -> Human | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id, h.display_name, h.email, h.status,
                   COALESCE(
                     array_agg(ARRAY[r.role, COALESCE(r.venture_id, '')])
                       FILTER (WHERE r.role IS NOT NULL),
                     '{}'
                   ) AS roles
            FROM office_human h
            LEFT JOIN office_human_role r
              ON r.human_id = h.human_id AND r.revoked_at IS NULL
            WHERE h.human_id = %s
            GROUP BY h.human_id, h.display_name, h.email, h.status
            """,
            (human_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Human(
        human_id=row["human_id"],
        display_name=row["display_name"],
        email=row["email"],
        status=row["status"],
        roles=tuple((r[0], r[1] or None) for r in row["roles"]),
    )


async def suspend_test_fixtures(
    conn: AsyncConnection, *, actor: uuid.UUID
) -> dict[str, Any]:
    """Suspend every account this project's own test paths created.

    179 accounts existed and 178 were fixtures; 94 of those held `ivan`, the authority
    for Forge-scope revocation. Suspending them one at a time through 94 inline forms is
    not a thing anybody does, so it never happened and the strongest role in the system
    stayed spread across 95 accounts.

    Suspension, never deletion. It is reversible, it is audited, and it leaves the record
    of who held what and who granted it intact - which is the property the Access page's
    own copy exists to protect. A cleaner roster bought by destroying that record is a
    worse roster.

    The actor is never suspended by this, whatever their account looks like: a bulk
    action that can lock out the person running it is a bulk action that eventually does.
    """
    from broker import account_origin

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT human_id, display_name, email, origin, status FROM office_human "
            "WHERE status = 'active'"
        )
        rows = [dict(r) for r in await cur.fetchall()]

    targets = [
        row for row in rows
        if account_origin.origin_of(row) == account_origin.TEST_FIXTURE
        and row["human_id"] != actor
    ]
    if not targets:
        return {"suspended": 0, "names": []}

    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
            "suspended_by = %s WHERE human_id = ANY(%s)",
            (actor, [row["human_id"] for row in targets]),
        )
    await conn.commit()
    return {
        "suspended": len(targets),
        "names": sorted(row["display_name"] for row in targets)[:20],
    }


async def note_seen(conn: AsyncConnection, *, human_id: uuid.UUID) -> None:
    """Record that this account authenticated.

    178 accounts had never signed in and nothing on the roster showed it, which is the
    single clearest signal that nobody is behind one. Written on every verified request,
    so "last active" means what it says.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE office_human SET last_seen_at = now() WHERE human_id = %s",
            (human_id,),
        )


async def list_humans(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Everyone, with their roles. Never a token and never a hash.

    The hash is not a secret in the way the token is, but it is a verifier: anything
    holding it can confirm a guess offline. It has no business on a screen, so this
    reports only whether one exists.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id::text AS human_id, h.display_name, h.email, h.status,
                   h.auth_method, h.created_at, h.suspended_at,
                   h.origin, h.last_seen_at, h.mfa_enrolled_at,
                   h.token_hash IS NOT NULL AS has_token,
                   COALESCE(
                     json_agg(
                       json_build_object('role', r.role, 'venture_id', r.venture_id,
                                         'granted_by', r.granted_by,
                                         'granted_at', r.granted_at)
                       ORDER BY r.role
                     ) FILTER (WHERE r.role IS NOT NULL),
                     '[]'
                   ) AS roles
            FROM office_human h
            LEFT JOIN office_human_role r
              ON r.human_id = h.human_id AND r.revoked_at IS NULL
            GROUP BY h.human_id
            ORDER BY h.display_name
            """
        )
        return [dict(r) for r in await cur.fetchall()]


# ------------------------------------------------------------------- sign-offs

@dataclass(frozen=True, slots=True)
class SignoffStatus:
    gate: str
    venture_id: str
    signatures: list[dict[str, Any]]
    valid: list[dict[str, Any]]
    voided: list[dict[str, Any]]

    @property
    def is_signed(self) -> bool:
        return bool(self.valid)


def artifact_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def sign_off(
    conn: AsyncConnection,
    *,
    gate: str,
    venture_id: str,
    human: Human,
    artifact_kind: str,
    artifact_hash_value: str,
    required_role: str = "venture_operator",
    distinct_humans: bool = True,
    note: str | None = None,
) -> uuid.UUID:
    """Record a gate sign-off bound to an artifact hash.

    `distinct_humans` implements the Pack's `gate_signoff_policy`. When set, a human who
    has already signed another gate for this venture cannot sign this one - which is the
    entire content of separation of duties, and is checked here rather than trusted to
    process.
    """
    role_signed_as = authorize(human, required_role=required_role, venture_id=venture_id)

    if distinct_humans:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT gate FROM signoff_record "
                "WHERE venture_id = %s AND human_id = %s AND gate <> %s LIMIT 1",
                (venture_id, human.human_id, gate),
            )
            other = await cur.fetchone()
        if other is not None:
            raise NotAuthorized(
                "separation of duties: this human already signed another gate for this "
                "venture",
                already_signed=other[0],
                gate=gate,
                policy="distinct_humans",
            )

    signoff_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO signoff_record
              (signoff_id, gate, venture_id, human_id, role_signed_as,
               artifact_hash, artifact_kind, note)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (venture_id, gate, human_id) DO UPDATE
            SET artifact_hash = EXCLUDED.artifact_hash,
                artifact_kind = EXCLUDED.artifact_kind,
                signed_at = now(),
                note = EXCLUDED.note
            """,
            (signoff_id, gate, venture_id, human.human_id, role_signed_as,
             artifact_hash_value, artifact_kind, note),
        )
    await conn.commit()
    return signoff_id


async def signoff_status(
    conn: AsyncConnection, *, gate: str, venture_id: str, current_artifact_hash: str
) -> SignoffStatus:
    """Which signatures still stand against the artifact as it is now.

    Part 14: "artifact change voids signature." Void by comparison - nothing has to
    remember to revoke anything when a Pack is edited.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT signoff_id, human_id, role_signed_as, artifact_hash, artifact_kind, "
            "       signed_at, note "
            "FROM signoff_record WHERE venture_id = %s AND gate = %s "
            "ORDER BY signed_at",
            (venture_id, gate),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    for r in rows:
        r["signoff_id"] = str(r["signoff_id"])
        r["human_id"] = str(r["human_id"])
        r["signed_at"] = r["signed_at"].isoformat()
        r["voided"] = r["artifact_hash"] != current_artifact_hash

    return SignoffStatus(
        gate=gate,
        venture_id=venture_id,
        signatures=rows,
        valid=[r for r in rows if not r["voided"]],
        voided=[r for r in rows if r["voided"]],
    )
