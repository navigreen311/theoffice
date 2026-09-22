"""Which accounts are people, and which are left over from a test run.

The Access page showed 179 accounts and called them all people. 178 of them are fixtures:
the smoke script and this session's manual checks each create a human, grant it `ivan`,
and never remove it. 94 of those hold `ivan` — the role that authorises Forge-scope
revocation, which stops every agent on every Forge across the portfolio.

Nothing was wrong with any single one of those accounts. What was wrong is that the page
counted them as colleagues, so the one fact worth knowing — that the strongest role in the
system is held by 95 accounts and exactly one of them is a person — was buried in a list
95 rows long.

DECLARED, NOT GUESSED. RULED 21 SEPTEMBER 2026 (entry 151)
==========================================================

    *"A fixture is declared, never guessed. `origin` is set explicitly at creation.
    Reclassify `dev-all build check` as `test_fixture`. Measured: it read
    `origin='human'`, so `assert_named_human` would not have refused it."*

    This module used to classify from two patterns: a display name shaped like
    `smoke-1a2b3c4d`, or an email under a reserved `.invalid` domain. Both are gone.

    **What the patterns could not see.** `dev-all build check` is created by
    `scripts/dev-all.sh` with the address `dev-all@localhost`. `@localhost` is not
    `.invalid` and `dev-all build check` is not `prefix-hexhex`, so it read as a person
    and held the `ivan` role for four days as one. The classifier was not wrong about
    its own rule; the rule was a guess about a naming convention, and a new caller did
    not follow it.

    **Why the stored column did not catch it.** 0027 stored `origin` and backfilled it
    with this same function. Measured before 0053: 242 accounts, and the column
    disagreed with the guess on **none** of them. Two spellings of one claim look like
    corroboration. They were not.

    So the column is now the whole answer, and it is written by a caller that says what
    it is creating. `create_human` requires it, `office_human.origin` has no DEFAULT,
    and a direct `INSERT` that omits it fails.

WHAT THIS MODULE IS NOW
=======================

    The vocabulary, and the two readers that need to split a list of accounts. There is
    no inference left in it, which is why there is no regex left in it either.
"""

from __future__ import annotations

from typing import Any

HUMAN = "human"
TEST_FIXTURE = "test_fixture"
SERVICE = "service"

#: Every value a caller may declare, and the same three the column's CHECK allows.
#: `create_human` validates against this so a typo is a refusal rather than a row.
DECLARABLE = frozenset({HUMAN, TEST_FIXTURE, SERVICE})


def origin_of(row: Any) -> str:
    """The declared origin of one account row.

    A read of `origin`, and nothing else. It keeps its name and its callers because what
    they ask has not changed - *is this row a person* - only the answer's source has.

    A row that carries no `origin` raises rather than defaulting. Every such row came
    from a query that did not select the column, which is a bug in the query: guessing
    `human` here is how `dev-all build check` was a person for four days, and a reader
    that silently reports a fixture as a colleague is the defect this module was written
    for in the first place.
    """
    declared = _get(row, "origin")
    if declared in DECLARABLE:
        return str(declared)
    if declared is None:
        raise ValueError(
            "this account row carries no `origin`; select the column rather than "
            "letting it be inferred (entry 151). A missing origin is a query to fix, "
            "not a value to assume."
        )
    raise ValueError(
        f"unknown account origin {declared!r}; expected one of "
        f"{', '.join(sorted(DECLARABLE))}"
    )


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def split(rows: list[Any]) -> tuple[list[Any], list[Any]]:
    """(real accounts, test fixtures). Service accounts count as real."""
    people = [row for row in rows if origin_of(row) != TEST_FIXTURE]
    fixtures = [row for row in rows if origin_of(row) == TEST_FIXTURE]
    return people, fixtures
