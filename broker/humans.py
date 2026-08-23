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
            LEFT JOIN office_human_role r ON r.human_id = h.human_id
            WHERE h.token_hash = %s
            GROUP BY h.human_id, h.display_name, h.email, h.status
            """,
            (hash_token(token),),
        )
        row = await cur.fetchone()

    if row is None:
        return None

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
