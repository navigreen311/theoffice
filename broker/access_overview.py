"""What the Access page needs to know before it lists anybody.

Three questions the roster could not answer while showing every account as a row:

  1. How concentrated is the strongest role, and how much does holding it authorise?
  2. Which people do the Packs name who have no account here?
  3. What does each role actually confer?

The first is the reason this module exists. 95 accounts hold `ivan` and one of them is a
person. `ivan` is the stated authority for Forge-scope revocation, so each of those 94
fixtures could stop every agent on every Forge in the portfolio. A page that renders that
as 95 rows has reported it and communicated nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import account_origin

#: What each role confers, in the terms somebody granting it needs. Roles appeared in
#: this console as bare strings with no definition anywhere, so a reader could not tell
#: what they were handing over.
#:
#: The revocation scopes come from `broker/revocation.SCOPE_MIN_ROLE` rather than being
#: retyped, so a scope moved between roles cannot leave this text describing the old
#: arrangement. `test_the_role_reference_matches_the_authority_matrix` holds that.
ROLE_ORDER = ("venture_operator", "compliance_officer", "ivan")

ROLE_MEANING = {
    "venture_operator": (
        "Runs one venture day to day: starts provisioning runs, decides proposals for "
        "that venture, writes knowledge and files incidents. Scoped - an operator of "
        "one engagement is nobody in another."
    ),
    "compliance_officer": (
        "Everything an operator can do, plus the reads and decisions that cross "
        "ventures: the roster, controls, dispositions, and closing an incident. "
        "Portfolio-wide by nature, which is why it is not scoped to a venture."
    ),
    "ivan": (
        "The strongest role. Everything above, plus reversing a hard cap and the "
        "widest revocation scope. Held by the person accountable for the portfolio."
    ),
}

#: How many people should hold each role for the system to be operable but not
#: over-privileged. Two administrators, because one is a single point of failure and the
#: last one cannot be suspended; more than a handful is a different problem.
EXPECTED_HOLDERS = {
    "ivan": (1, 3),
    "compliance_officer": (1, 6),
    "venture_operator": (1, 40),
}


@dataclass(frozen=True, slots=True)
class MissingPerson:
    """Somebody a Pack names who has no account."""

    human_name: str
    role: str
    venture_id: str
    reason: str


async def overview(conn: AsyncConnection) -> dict[str, Any]:
    """Everything the page states before it lists a single person."""
    from broker import revocation

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT h.human_id::text AS human_id, h.display_name, h.email, h.status,
                   h.auth_method, h.created_at, h.origin, h.last_seen_at,
                   h.mfa_enrolled_at,
                   COALESCE(
                     json_agg(
                       json_build_object('role', r.role, 'venture_id', r.venture_id)
                       ORDER BY r.role
                     ) FILTER (WHERE r.role IS NOT NULL),
                     '[]'
                   ) AS roles
            FROM office_human h
            LEFT JOIN office_human_role r ON r.human_id = h.human_id
            GROUP BY h.human_id
            ORDER BY h.created_at
            """
        )
        accounts = [dict(row) for row in await cur.fetchall()]

        await cur.execute(
            "SELECT venture_id, parsed FROM business_pack WHERE status = 'live'"
        )
        packs = [dict(row) for row in await cur.fetchall()]

    people, fixtures = account_origin.split(accounts)

    def holders(role: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            row for row in rows
            if any(grant["role"] == role for grant in row["roles"])
        ]

    strongest = ROLE_ORDER[-1]
    all_strongest = holders(strongest, accounts)
    fixture_strongest = holders(strongest, fixtures)

    # ------------------------------------------------------- the concentration finding
    _low, high = EXPECTED_HOLDERS[strongest]
    concentration = {
        "role": strongest,
        "total": len(all_strongest),
        "fixtures": len(fixture_strongest),
        "people": len(all_strongest) - len(fixture_strongest),
        "expected_max": high,
        # Either condition raises it. A test account holding the strongest role is a
        # finding at any count; so is a real over-grant with no fixtures involved.
        "raised": len(fixture_strongest) > 0 or len(all_strongest) > high,
        "authorises": [
            scope for scope, required in revocation.SCOPE_MIN_ROLE.items()
            if required == strongest
        ],
        "active_fixtures": sum(1 for row in fixture_strongest if row["status"] == "active"),
    }

    # ----------------------------------------------------- people the Packs name
    named = _people_the_packs_name(packs)
    known = {(row["display_name"] or "").strip().lower() for row in people}
    missing = [
        {
            "human_name": person.human_name,
            "role": person.role,
            "venture_id": person.venture_id,
            "reason": person.reason,
        }
        for person in named
        if person.human_name.strip().lower() not in known
    ]

    # Accounts holding a role no live Pack asks for. Not a fault on its own - somebody
    # has to administer the system before any Pack exists - but worth naming.
    pack_roles = {person.role for person in named}
    unreferenced = sorted(
        {
            grant["role"]
            for row in people
            for grant in row["roles"]
            if grant["role"] not in pack_roles
        }
    )

    # ------------------------------------------------------------ the role reference
    reference = []
    for role in ROLE_ORDER:
        role_holders = holders(role, people)
        expected_low, expected_high = EXPECTED_HOLDERS[role]
        required_by_pack = role in pack_roles
        reference.append({
            "role": role,
            "meaning": ROLE_MEANING[role],
            "revocation_scopes": [
                scope for scope, required in revocation.SCOPE_MIN_ROLE.items()
                if required == role
            ],
            "holders": len(role_holders),
            "fixture_holders": len(holders(role, fixtures)),
            "expected_min": expected_low,
            "expected_max": expected_high,
            "required_by_a_pack": required_by_pack,
            # Two different findings, kept apart: nobody holds a role a Pack needs, or
            # more people hold it than the system should have.
            "unheld_but_required": required_by_pack and not role_holders,
            "over_held": len(role_holders) > expected_high,
        })

    return {
        "accounts": accounts,
        "counts": {
            "total": len(accounts),
            "people": len(people),
            "fixtures": len(fixtures),
            "active_fixtures": sum(1 for row in fixtures if row["status"] == "active"),
            "never_seen": sum(1 for row in accounts if row["last_seen_at"] is None),
            "mfa_enrolled": sum(1 for row in people if row["mfa_enrolled_at"] is not None),
        },
        "concentration": concentration,
        "missing_people": missing,
        "unreferenced_roles": unreferenced,
        "roles": reference,
    }


def _people_the_packs_name(packs: list[dict[str, Any]]) -> list[MissingPerson]:
    """Every human a live Pack names, and why that Pack needs them.

    `human_capacity` names an operator and a compliance officer per venture, each with a
    backup. Where `separation_of_duties.gate_signoff_policy` is `distinct_humans`, Gate
    10 cannot be signed by one person twice - so a Pack naming somebody who has no
    account here is a run that cannot finish, and nothing said so.
    """
    primary: list[MissingPerson] = []
    backups: list[MissingPerson] = []
    for pack in packs:
        parsed = pack["parsed"] or {}
        venture = pack["venture_id"]
        policy = (parsed.get("separation_of_duties") or {}).get("gate_signoff_policy")
        distinct = policy == "distinct_humans"

        for entry in parsed.get("human_capacity") or []:
            name = (entry.get("human_name") or "").strip()
            if not name:
                continue
            role = entry.get("role") or "unknown"
            reason = (
                f"{venture}'s Pack names {name} as {role.replace('_', ' ')}"
                + (
                    " and requires distinct humans at Gate 10. Sign-off cannot be "
                    "completed until that person exists here."
                    if distinct
                    else ". The Pack assumes that person can act."
                )
            )
            primary.append(MissingPerson(name, role, venture, reason))

            backup = (entry.get("backup_human") or "").strip()
            if backup:
                backups.append(
                    MissingPerson(
                        backup,
                        role,
                        venture,
                        f"{venture}'s Pack names {backup} as backup {role.replace('_', ' ')}"
                        f" for {name}.",
                    )
                )

    # One entry per person, and the role they hold in their own right beats the one
    # they cover for. Dana is Greenstone's compliance officer and also Ivan's backup as
    # venture operator; deduping in encounter order described her as a venture operator,
    # which is the role she is the understudy for rather than the one Gate 10 needs her
    # to sign in.
    seen: set[str] = set()
    unique: list[MissingPerson] = []
    for person in [*primary, *backups]:
        key = person.human_name.strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(person)
    return unique
