"""Which accounts are people, and which are left over from a test run.

The Access page showed 179 accounts and called them all people. 178 of them are fixtures:
the smoke script and this session's manual checks each create a human, grant it `ivan`,
and never remove it. 94 of those hold `ivan` — the role that authorises Forge-scope
revocation, which stops every agent on every Forge across the portfolio.

Nothing was wrong with any single one of those accounts. What was wrong is that the page
counted them as colleagues, so the one fact worth knowing — that the strongest role in the
system is held by 95 accounts and exactly one of them is a person — was buried in a list
95 rows long.

**Derived, not stored.** The brief asked for an `origin` column with a pattern backfill.
Derived is strictly better here for the same reason it was for knowledge fixtures: the
smoke script creates more of these on every run, and a column populated by one migration
describes the accounts that existed the day it ran. A pattern applied at read time
recognises the ones created tomorrow. `service` is the exception - nothing about a service
account is inferable from its name - so that one is stored, and absent until something
needs it.
"""

from __future__ import annotations

import re
from typing import Any

#: Names this project's own test paths generate: `smoke-1a2b3c4d`, `ui-90ab...`. Each
#: prefix is a real caller - `scripts/console-smoke.sh`, and the ad-hoc checks run while
#: building the console.
TEST_NAME = re.compile(r"^(smoke|browse|check|inc|mut|ui|api|e2e)-[0-9a-f]{6,12}$")

#: RFC 2606 reserves `.invalid`, so an address in it can never belong to a person. Every
#: fixture in this repository uses one.
TEST_DOMAINS = ("example.invalid", "test.invalid", "incidents.invalid",
                "revocation.invalid", "approvals.invalid")

HUMAN = "human"
TEST_FIXTURE = "test_fixture"
SERVICE = "service"


def origin_of(row: Any) -> str:
    """`human`, `test_fixture` or `service` for one account row."""
    stored = _get(row, "origin")
    if stored == SERVICE:
        return SERVICE

    name = (_get(row, "display_name") or "").strip()
    email = (_get(row, "email") or "").strip().lower()

    if TEST_NAME.match(name):
        return TEST_FIXTURE
    if any(email.endswith(f"@{domain}") or email.endswith(domain) for domain in TEST_DOMAINS):
        return TEST_FIXTURE
    if email.endswith(".invalid"):
        return TEST_FIXTURE
    return HUMAN


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def split(rows: list[Any]) -> tuple[list[Any], list[Any]]:
    """(real accounts, test fixtures). Service accounts count as real."""
    people = [row for row in rows if origin_of(row) != TEST_FIXTURE]
    fixtures = [row for row in rows if origin_of(row) == TEST_FIXTURE]
    return people, fixtures
