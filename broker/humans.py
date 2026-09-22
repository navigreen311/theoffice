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

from broker import account_origin, audit
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

    origin: str = "human"
    """`human` or `test_fixture`. **Who this account is, not what it may do.**

    Read here because a role cannot answer it: `attributable_actor` has refused to
    resolve an action to a fixture since it was written - *"an escalation delivered to
    `smoke-1a2b3c4d` is not delivered"* - and every route that takes `me` from a token
    skipped that check entirely, because `Human` did not carry the column.

    Defaulted to `human` so a hand-built `Human` in a test is a person unless it says
    otherwise. The database is what decides for a real one.
    """

    auth_method: str = "bearer_token"
    """What is actually enforced for this account. Ruled 21 September 2026, entry 154.

    **Carried but not yet enforced anywhere, and that is deliberate.** Entry 148's
    finding was that `Human` did not carry `origin`, so every route taking `me` from a
    token was structurally unable to ask the question. This closes the same gap for
    authentication before anything needs it - a caller can now ask what a signer's
    credential actually is.

    What it cannot do yet is refuse: `mfa_enrolled_at` has no writer in this repository,
    so requiring an enrolment would refuse every account including both people. What
    enrolment would MEAN for an account whose only credential is a bearer token The
    Office issued is the open question entry 154 records rather than answers.
    """

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
    origin: str,
    created_by: uuid.UUID | None = None,
    auth_method: str = "bearer_token",
    token: str | None = None,
) -> tuple[uuid.UUID, str]:
    """Create a human and return (human_id, plaintext token).

    CREATING AN ACCOUNT WRITES AN AUDIT EVENT. Ruled 21 September 2026, entry 153:
    *"Creating an account writes an audit event. Measured: `dev-all build check` has no
    creation record, only its revocation."*

    The measurement is the argument. `dev-all build check` held `ivan` - founder
    authority - for four days, and the hash-chained log contains exactly one row about
    it: the revocation of that role on 21 September. **There is no record of the account
    being made, by whom, or why**, and nothing in this repository creates it, so the
    question of where it came from cannot be answered from the ledger that exists to
    answer exactly that.

    `console_human_created` was written by the route and `bootstrap_human_created` by
    the CLI, so two of the three paths already did this - at the caller, which is the
    shape entry 149 ruled against for `grant_role`. An event a caller remembers to write
    is an event the next caller forgets, and the next caller is how this account exists.

    `created_by` is nullable for one documented case and one only: the bootstrap human,
    who has nobody above them to be created by. It resolves to the new account's own id
    there, the way `grant_role`'s self-grant does, and it is visible as an exception
    rather than as a gap.

    `origin` IS REQUIRED AND IS NOT GUESSED. Ruled 21 September 2026, entry 151:
    *"A fixture is declared, never guessed. `origin` is set explicitly at creation."*

    It used to be `account_origin.origin_of({display_name, email})` - a display-name
    pattern and a `.invalid` domain. `dev-all build check` matched neither, because its
    address is `dev-all@localhost`, so a build-check account read as a person and
    `assert_named_human` would not have refused it. No caller in this repository creates
    that account and no audit entry records its creation, which is its own finding.

    The parameter has no default for the same reason the column no longer has one: the
    caller knows what it is creating, and a value invented on its behalf is the defect.

    The plaintext is returned exactly once and never stored. A caller that loses it
    issues a new one; a system that can recover it is a system where the hash was
    pointless.
    """
    if origin not in account_origin.DECLARABLE:
        raise ValueError(
            f"origin must be one of {', '.join(sorted(account_origin.DECLARABLE))}; "
            f"got {origin!r}. It says what this account IS, not what it may do."
        )
    human_id = uuid.uuid4()
    plaintext = token or issue_token()
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "token_hash, origin) VALUES (%s, %s, %s, %s, %s, %s)",
            (
                human_id,
                display_name,
                email,
                auth_method,
                hash_token(plaintext),
                origin,
            ),
        )
    await conn.commit()

    # AFTER THE COMMIT, so the event describes an account that exists. An entry written
    # first records an intention, which is the ordering `shifts.assign_shift` already
    # argues for at the flush boundary.
    #
    # The token is not in the subject and must never be: this log is readable by anyone
    # who can read the Access page, and a credential in a hash-chained record is a
    # credential that cannot be redacted.
    await audit.write_event(
        event_type="human_account_created",
        actor_type="human",
        # SELF, for the bootstrap human only - the documented exception above.
        actor_id=created_by or human_id,
        venture_id=None,
        subject={
            "human_id": str(human_id),
            "display_name": display_name,
            "email": email,
            # BOTH DECLARATIONS ON THE RECORD (entries 151 and 154). What this account
            # is, and what is actually enforced for it - the two facts that decide what
            # it may do, recorded at the only moment they are chosen.
            "origin": origin,
            "auth_method": auth_method,
            "self_created": created_by is None,
        },
    )
    return human_id, plaintext


async def grant_role(
    conn: AsyncConnection,
    *,
    human_id: uuid.UUID,
    role: str,
    granted_by: uuid.UUID,
    venture_id: str | None = None,
) -> None:
    """Give a human a role, and say so in the ledger.

    RULED 21 SEPTEMBER 2026 (decisions entry 149)
    =============================================

        *"A role grant or revocation writes an audit event, in `grant_role` and
        `revoke_role` themselves."*

        Neither wrote one. The row records `granted_by` and `granted_at`, which is a
        record - and it is not the hash-chained one, so nothing that verifies the ledger
        covers a change to who may act. `revoke_role`'s own docstring claimed otherwise:
        *"the audit log says who"*.

        Found on 21 September, granting Ira Green `compliance_officer` for Greenstone.
        The event had to be written by hand beside the call, which is the shape that
        tells you the function should have written it.

    **IN THIS FUNCTION, not at the caller.** That is the whole of the ruling: an event a
    caller remembers to write is an event the next caller forgets.

    NOTHING IS CLAIMED WHEN NOTHING CHANGED. `ON CONFLICT DO NOTHING` makes a re-grant a
    no-op, and an event saying a role was granted when the human already held it is a
    false entry in a chain whose value is that it contains none.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_human_role (human_id, role, venture_id, granted_by) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (human_id, role, venture_id, granted_by),
        )
        granted = cur.rowcount
    await conn.commit()

    if granted:
        await audit.write_event(
            event_type="human_role_granted",
            actor_type="human", actor_id=granted_by, venture_id=venture_id,
            subject={
                "human_id": str(human_id),
                "role": role,
                # Spelled rather than omitted, because a NULL here means EVERY venture
                # and an absent key reads as "this one, unspecified".
                "venture_id": venture_id or "*",
            },
        )


async def authenticate(conn: AsyncConnection, token: str) -> Human | None:
    """Resolve a bearer token to a human, with roles.

    Status is read live rather than baked into the token. A suspended human must be
    refused on their next request, not their next session - the same rule revocation
    follows for agents, and for the same reason.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id, h.display_name, h.email, h.status, h.origin,
                   h.auth_method,
                   COALESCE(
                     array_agg(ARRAY[r.role, COALESCE(r.venture_id, '')])
                       FILTER (WHERE r.role IS NOT NULL),
                     '{}'
                   ) AS roles
            FROM office_human h
            LEFT JOIN office_human_role r
              ON r.human_id = h.human_id AND r.revoked_at IS NULL
            WHERE h.token_hash = %s
            GROUP BY h.human_id, h.display_name, h.email, h.status, h.origin,
                     h.auth_method
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
        origin=row["origin"],
        auth_method=row["auth_method"],
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


def assert_named_human(human: Human, *, act: str) -> None:
    """Refuse an act a test fixture is attempting.

    RULED 21 SEPTEMBER 2026 (decisions entry 148)
    =============================================

        *"Only a named human may decide a proposal. Smoke fixtures decided four; nothing
        stopped them."*

        Measured: four `place_call` proposals were decided on 16 September by
        `smoke-28e7bea5`, `smoke-25e8ed8f`, `smoke-a961648a` and `smoke-3e94169f` - every
        one an `origin = 'test_fixture'` account, every one recorded in `audit_log` as a
        human decision. They are the only proposal decisions this system has ever made.

    WHY A ROLE COULD NOT CATCH IT
    =============================

        The fixtures hold real roles - 239 of the 242 accounts on the development
        database are fixtures and most hold `ivan` - so every role check they met, they
        met honestly. What they are not is a person who can be held to the decision, and
        that is a different question from what they are allowed to do.

        `attributable_actor` has asked it since it was written, for exactly this reason:
        *"an escalation delivered to `smoke-1a2b3c4d` is not delivered."* It asks it of an
        account it GOES AND FINDS. This asks it of the account that turned up with a
        token, which is the half nobody was checking.

    `act` is in the message because "not a named human" with no verb is a sentence
    somebody has to go and read the code to act on.
    """
    if human.origin != "human":
        raise NotAuthorized(
            f"{human.display_name} is a {human.origin} and may not {act}. This decision "
            "is recorded against whoever makes it, and a fixture is not somebody who "
            "can be held to it.",
            human_status=human.status,
        )


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

    **AND IT WRITES AN AUDIT EVENT NOW** - ruled 21 September 2026, entry 149. The
    paragraph above used to end *"the audit log says who"*, and the audit log said
    nothing: this function wrote a column and no event. The claim is true again.
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

    # Same rule as the grant: a revocation of a role nobody held is not a revocation.
    if removed:
        await audit.write_event(
            event_type="human_role_revoked",
            actor_type="human", actor_id=revoked_by, venture_id=venture_id,
            subject={
                "human_id": str(human_id),
                "role": role,
                "venture_id": venture_id or "*",
            },
        )
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


async def rename(
    conn: AsyncConnection, *, human_id: uuid.UUID, display_name: str
) -> tuple[str, str]:
    """Change an account's display name. Returns (old, new).

    **A display name is a key in practice, and this is the only path that may change
    one.** Two Packs name their reviewers by display name, and two joins read those names
    against this column: the access overview's missing-people list, and the approvals page
    attaching a reviewer's decisions. Renaming moves what both resolve to, so it is an act
    with consequences elsewhere rather than a cosmetic edit - which is why it returns the
    old name for the caller to audit rather than quietly succeeding.

    **It does not rewrite history, deliberately.** `provisioning_gate_result.reason` holds
    "reviewed by <name>: ..." frozen at signing, evidence blobs hold the name a Pack
    declared, `audit_log` is hash-chained, and published Pack versions are immutable. An
    attestation records what was true when it was made; a rename that edited those would
    be changing what somebody attested to. The account will disagree with its own trail,
    and that is the correct outcome rather than a defect to paper over.

    A name another account already uses is refused here with a message naming the holder,
    and refused again by `ux_human_display_name` (migration 0040) if this check is ever
    bypassed. Comparison is strip+lower, matching how the access overview compares.
    """
    new_name = display_name.strip()
    if not new_name:
        raise NotAuthorized("a display name cannot be blank", human_id=str(human_id))

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT display_name FROM office_human WHERE human_id = %s", (human_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise NotAuthorized("no such human", human_id=str(human_id))
        old_name = row["display_name"]

        await cur.execute(
            "SELECT human_id, display_name FROM office_human "
            "WHERE lower(trim(display_name)) = lower(%s) AND human_id <> %s",
            (new_name, human_id),
        )
        clash = await cur.fetchone()
        if clash is not None:
            raise NotAuthorized(
                f"{clash['display_name']!r} is already another account's display name "
                f"({str(clash['human_id'])[:8]}). Two accounts with one name are two "
                "accounts the Packs' name matching cannot tell apart.",
                human_id=str(human_id),
            )

        await cur.execute(
            "UPDATE office_human SET display_name = %s WHERE human_id = %s",
            (new_name, human_id),
        )
    await conn.commit()
    return old_name, new_name


async def set_daily_total(
    conn: AsyncConnection, *, human_id: uuid.UUID, hours: float
) -> tuple[float | None, float]:
    """Declare how many hours a day this person has, across every venture. Returns (old, new).

    **The one number a Pack cannot supply, and the reason V39 can exist.** Every hours
    figure in this system is declared inside one venture's Pack, and no Pack can see
    another - so Ivan Green was declared for six hours in Greenstone and six in Burkham
    and nothing added them up. Decisions entry 94 §5 recorded sixteen a day for one person
    and noted that no rule refuses it.

    **On the account rather than in a Pack, deliberately.** A total is a fact about a
    person. In a Pack it would be declared once per venture, and a venture could raise its
    own founder's total to make its own check pass - which is the one thing a cross-venture
    rule exists to stop.

    Returns the old value so the caller can audit the change rather than only its result,
    the same reason `rename` returns the old name: an event saying what a number became
    cannot answer what it was.
    """
    if hours <= 0 or hours > 24:
        raise NotAuthorized(
            f"{hours} is not a daily total. A day holds 24 hours, and zero is an empty "
            "field with a number in it rather than a declaration of no capacity.",
            human_id=str(human_id),
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT daily_total_hours FROM office_human WHERE human_id = %s", (human_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise NotAuthorized("no such human", human_id=str(human_id))
        old = float(row["daily_total_hours"]) if row["daily_total_hours"] is not None else None

        await cur.execute(
            "UPDATE office_human SET daily_total_hours = %s WHERE human_id = %s",
            (hours, human_id),
        )
    await conn.commit()
    return old, float(hours)


async def get_human(conn: AsyncConnection, human_id: uuid.UUID) -> Human | None:
    """One human by id, carrying every field `Human` has.

    **It selected neither `origin` nor `auth_method` and let both default**, so a fixture
    fetched through here arrived as `origin='human'` and would have passed
    `assert_named_human` - the exact gap entry 148 found in the token path, surviving in
    the by-id path because the dataclass defaults are permissive. Fixed alongside entry
    154 rather than left for the next reader to find a third time.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id, h.display_name, h.email, h.status, h.origin,
                   h.auth_method,
                   COALESCE(
                     array_agg(ARRAY[r.role, COALESCE(r.venture_id, '')])
                       FILTER (WHERE r.role IS NOT NULL),
                     '{}'
                   ) AS roles
            FROM office_human h
            LEFT JOIN office_human_role r
              ON r.human_id = h.human_id AND r.revoked_at IS NULL
            WHERE h.human_id = %s
            GROUP BY h.human_id, h.display_name, h.email, h.status, h.origin,
                     h.auth_method
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
        origin=row["origin"],
        auth_method=row["auth_method"],
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


class NoAttributableActorError(Exception):
    """Nothing could sign this. There is no real account able to act."""


async def attributable_actor(
    conn: AsyncConnection, *, required_role: str = "ivan"
) -> uuid.UUID:
    """The person an audited action is recorded against.

    `origin = 'human'` is the condition that matters, and it is why this function exists
    rather than each caller writing the query. `sync-roster` resolved its actor as "the
    oldest active account holding ivan", and 222 of the 223 accounts in the development
    database are smoke fixtures that all hold `ivan`. The real account won that query by
    being the oldest, which is luck rather than a rule: a re-seed, a restore, or one
    fixture created a second earlier would have signed a change to the identity table as
    `smoke-1a2b3c4d`.

    An audit entry signed by a fixture is worthless. Non-repudiation is the whole reason
    this log exists and it does not survive an actor nobody can call.

    Raises rather than returning None. A caller that treats "nobody could sign this" as a
    value will eventually write the row anyway with a null actor, and the point is that
    the write must not happen.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id, h.display_name
              FROM office_human h
              JOIN office_human_role r ON r.human_id = h.human_id
             WHERE r.role = %s
               -- A REVOKED ROLE GRANTS NOTHING. Ruled 21 September 2026, entry 150.
               -- This query ignored it, so a role somebody had taken away still made
               -- its holder eligible to be attributed an action. Every other read of
               -- this table filtered it; this one and two more did not.
               AND r.revoked_at IS NULL
               AND h.status = 'active'
               AND h.origin = 'human'
             ORDER BY h.created_at
             LIMIT 1
            """,
            (required_role,),
        )
        row = await cur.fetchone()

    if row is None:
        raise NoAttributableActorError(
            f"no active account with origin 'human' holds {required_role!r}. Test "
            "fixtures are excluded deliberately: an audit entry signed by a fixture "
            "names nobody who can answer for it. Create a real account first: "
            "python -m broker human create."
        )
    actor_id: uuid.UUID = row["human_id"]
    return actor_id


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
    mfa_code: str,
    required_role: str = "venture_operator",
    distinct_humans: bool = True,
    note: str | None = None,
) -> uuid.UUID:
    """Record a gate sign-off bound to an artifact hash.

    `distinct_humans` implements the Pack's `gate_signoff_policy`. When set, a human who
    has already signed another gate for this venture cannot sign this one - which is the
    entire content of separation of duties, and is checked here rather than trusted to
    process.

    A SECOND FACTOR, VERIFIED NOW. Ruled 21 September 2026, entry 155. This is the
    signature Gate 11 activates production grants against, and 0025 named the exact
    consequence of leaving it on a bearer token alone: *"a signer whose MFA is a claim
    rather than an enrolment weakens the non-repudiation the Gate 10 signature is meant
    to carry."* It was a claim for every account on the platform.

    One code signs one gate. `assert_verified` records the step it consumed, so a second
    signature taken inside the same 30 seconds is refused - two signatures with one code
    are one act, and separation of duties is about two acts.
    """
    from broker import mfa

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

    # THE SECOND FACTOR IS CHECKED LAST, after role and after separation of duties.
    #
    # It ran first to begin with, and the pipeline test found what that costs: a human
    # who had already signed another gate spent their one-use code and was told "that
    # code has already been used" - true, and about the wrong problem. A refusal that
    # does not depend on the code should not consume one, and the caller should hear the
    # reason they were actually refused.
    await mfa.assert_verified(
        conn, me=human, code=mfa_code, act=f"signing {gate} for {venture_id}",
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
