"""The roles a person can be granted are the same three everywhere they are written down.

WHY THIS EXISTS
===============

    `test_tier_vocabulary_agrees.py` compares two copies of the tier vocabulary - a Python
    constant and a CHECK constraint. **The role vocabulary is written down five times**, and
    until now nothing compared any of them:

        office_human_role_role_check            the database's copy
        revocation_revoked_by_role_check        the database's SECOND copy
        broker.revocation.ROLE_RANK             the source of the hierarchy
        console/app/access/forms.tsx  ROLES     a hardcoded array in the grant form
        console/app/access/people.tsx           a hardcoded array in the filter dropdown

    And the scope-to-authority MAPPING is written down three times:

        broker.revocation.SCOPE_MIN_ROLE        the rule that is enforced
        console/app/revocations/form.tsx        SCOPES[].authority
        console/app/revocations/page.tsx        SCOPES[].authority

WHAT DRIFT COSTS, PER COPY
==========================

    **A fourth role added to `ROLE_RANK` is ungrantable from the console and nothing says
    so.** The grant form renders `ROLES`; a role absent from that array has no option in
    the dropdown, so the only way to hold it is a direct database write - which is the
    thing every rule in `humans.assert_may_grant` exists to prevent. The API would accept
    it and the UI would never offer it.

    **A role removed from a CHECK and left in `ROLE_RANK` fails at write time**, mid-grant,
    as an IntegrityConstraintViolation from `grant_role` - the same late-reporting shape
    entry 42 and the tier test both record.

    **A drifted `authority` in the revocations console is the worst of the three**, because
    it is not a crash. The page tells an operator which role may revoke at each scope,
    beside a destructive action. If `SCOPE_MIN_ROLE` says `ivan` for Forge scope and the
    page says `compliance_officer`, a compliance officer is told they may do something the
    server will refuse - or, in the other direction, the page under-states the authority a
    scope requires and somebody plans around a restriction that is not there.

WHY THE TSX IS PARSED RATHER THAN RESTATED
==========================================

    A test that hard-coded the three names would pass while every copy drifted together,
    which is the failure it exists to prevent. So each copy is read from where it lives:
    the constraints out of `pg_constraint`, the constants by import, and the arrays out of
    the TSX source. Parsing a TypeScript literal from Python is crude, and it is the crude
    thing that actually reads the file the browser gets.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from broker.revocation import ROLE_RANK, SCOPE_MIN_ROLE
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

#: Both CHECKs that spell the role vocabulary out, and the table each guards.
CONSTRAINTS = {
    "office_human_role": "office_human_role_role_check",
    "revocation": "revocation_revoked_by_role_check",
}

CONSOLE = Path(__file__).resolve().parents[2] / "console" / "app"

#: Each console file that restates the role list, and the pattern that finds its array.
#: Anchored on something specific to that file rather than on `[...]` generally - a loose
#: pattern that matched some other array would compare the wrong thing and still pass.
ROLE_ARRAYS = {
    "access/forms.tsx": re.compile(r"const ROLES = \[([^\]]*)\]"),
    "access/people.tsx": re.compile(r"\{\[([^\]]*)\]\.map\(\(role\)"),
}

#: The console's two copies of the scope-to-authority mapping.
SCOPE_TABLES = ("revocations/form.tsx", "revocations/page.tsx")

_STRING = re.compile(r"""["']([a-z_]+)["']""")


def _allowed_roles(conn, table: str, constraint: str) -> set[str]:
    """The value set `constraint` permits, read from the catalogue rather than a copy."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND conname = %s",
            (table, constraint),
        )
        row = cur.fetchone()

    assert row is not None, (
        f"{constraint} does not exist on {table}. Either it was renamed - in which case "
        "this test needs updating and the rename needs a reason - or it was dropped, and "
        "the database no longer refuses an unknown role at all."
    )
    return set(_STRING.findall(row[0]))


def _console_roles(relative: str) -> set[str]:
    path = CONSOLE / relative
    assert path.exists(), f"{relative} is gone; this test's map of the console is stale"
    match = ROLE_ARRAYS[relative].search(path.read_text(encoding="utf-8"))
    assert match is not None, (
        f"no role array found in {relative}. The array moved or was rewritten, so this "
        "test is no longer reading the copy the browser gets - which is worse than it "
        "failing, because it would pass."
    )
    return set(_STRING.findall(match.group(1)))


def test_both_check_constraints_know_the_same_roles_as_role_rank(admin) -> None:
    """`ROLE_RANK` and each CHECK hold the same names, in both directions.

    Two constraints rather than one: `office_human_role` decides what may be granted and
    `revocation` decides what may be recorded as having acted. A role addable to one and
    not the other is a role somebody can hold and cannot revoke with.
    """
    known = set(ROLE_RANK)
    for table, constraint in CONSTRAINTS.items():
        allowed = _allowed_roles(admin, table, constraint)
        assert known - allowed == set(), (
            f"ROLE_RANK knows {sorted(known - allowed)}, which {constraint} refuses. A "
            f"grant carrying one of these is written and rejected by the database, "
            "mid-call, as a raw constraint violation."
        )
        assert allowed - known == set(), (
            f"{constraint} allows {sorted(allowed - known)}, which ROLE_RANK does not "
            "rank. `authorize` and `assert_may_grant` both index ROLE_RANK directly, so "
            "a role the database accepts and the ranking does not know raises KeyError "
            "on the authorization path."
        )


@pytest.mark.parametrize("relative", sorted(ROLE_ARRAYS))
def test_the_console_offers_exactly_the_roles_that_exist(relative: str) -> None:
    """Each console copy of the role list matches `ROLE_RANK`.

    The direction that matters most is a role in `ROLE_RANK` and absent from the console:
    it is grantable by the API, invisible in the UI, and the only way to hold it is the
    direct database write that `assert_may_grant` exists to make impossible.
    """
    known = set(ROLE_RANK)
    offered = _console_roles(relative)

    assert known - offered == set(), (
        f"{relative} does not offer {sorted(known - offered)}. The role exists and the "
        "console cannot grant it, so the only route to holding it is a direct database "
        "write - which is what every rule in assert_may_grant exists to prevent."
    )
    assert offered - known == set(), (
        f"{relative} offers {sorted(offered - known)}, which is not a role. Selecting it "
        "produces a grant the database refuses, reported to the operator as a failure of "
        "the thing they were doing rather than as a stale list."
    )


@pytest.mark.parametrize("relative", SCOPE_TABLES)
def test_the_revocations_console_states_the_authority_the_server_enforces(
    relative: str,
) -> None:
    """`SCOPE_MIN_ROLE` and the console's `SCOPES[].authority` agree, scope by scope.

    This is the copy whose drift does not crash. The page tells an operator which role may
    revoke at each scope, next to the button that does it. Drift in one direction promises
    an authority the server refuses; in the other it hides one that is required, and
    somebody plans around a restriction that does not exist.
    """
    path = CONSOLE / relative
    assert path.exists(), f"{relative} is gone; this test's map of the console is stale"
    source = path.read_text(encoding="utf-8")

    # Each entry is `scope: "x"` followed, within the same object literal, by
    # `authority: "y"`. Non-greedy across the gap so two entries cannot be spliced.
    pairs = dict(
        re.findall(
            r"""scope:\s*["']([a-z_]+)["'].*?authority:\s*["']([a-z_]+)["']""",
            source,
            re.S,
        )
    )
    assert pairs, (
        f"no scope/authority pairs found in {relative}. The table moved or was rewritten, "
        "so this test is not reading what the operator is shown."
    )

    assert set(pairs) == set(SCOPE_MIN_ROLE), (
        f"{relative} lists scopes {sorted(pairs)}; SCOPE_MIN_ROLE has "
        f"{sorted(SCOPE_MIN_ROLE)}. A scope the console omits cannot be revoked at from "
        "the UI; one it invents produces a request the server rejects."
    )
    for scope, shown in sorted(pairs.items()):
        assert shown == SCOPE_MIN_ROLE[scope], (
            f"{relative} tells the operator that {scope!r} revocation requires "
            f"{shown!r}; the server enforces {SCOPE_MIN_ROLE[scope]!r}. This one does not "
            "crash - it misinforms somebody standing in front of a destructive action."
        )


def test_the_ladder_is_ranked_without_ties() -> None:
    """Distinct ranks, because `authorize` and `assert_may_grant` both compare them.

    A tie makes two roles mutually sufficient, which would let each grant the other and
    make the pair self-propagating - the exact property `assert_may_grant`'s "strictly
    stronger, except at the top" rule exists to deny.
    """
    assert len(set(ROLE_RANK.values())) == len(ROLE_RANK), (
        f"two roles share a rank in ROLE_RANK: {ROLE_RANK}. Equal ranks are mutually "
        "sufficient, so each could grant the other."
    )
