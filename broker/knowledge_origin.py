"""Where a knowledge-base entry came from, and whether it is substance.

The page reported *Persona Library 60 entries*. All sixty are named `Smoke 741201` and
similar, stand in for the same broker, and were written by console smoke runs. *Historical
Records 61 entries*: every one is an abandoned provisioning run summarised "console smoke
test". A library holding sixty copies of one fixture has zero personas, and reporting it
as sixty is the same failure as a green check with no denominator.

**Origin is derived, not stored.** `historical_record` is append-only - it carries a
trigger refusing UPDATE and DELETE, and `office_app` holds only INSERT and SELECT - so a
column marking fixtures could never be backfilled or maintained there. Deriving it also
means it cannot drift from the data it describes, which is the same reason curriculum
completeness is assessed from the content rather than from a flag.

Three origins:

  authored       a human wrote it, and meant it
  system         The Office recorded it as a consequence of something happening
  test_fixture   a test wrote it. Real rows, no meaning, and they must not be counted

`test_fixture` is deliberately narrow. The patterns match what the smoke script actually
writes, and a real entry that happened to match would be a bad outcome - so they are
anchored and specific rather than a substring search for "test".
"""

from __future__ import annotations

import re
from typing import Any

# What `console-smoke.sh` writes. `Smoke 741201` - the word, a space, six digits, and
# nothing else. A persona genuinely called "Smoke Detection Buyer" does not match.
SMOKE_PERSONA = re.compile(r"^Smoke \d{4,8}$")

# The summary the smoke script gives an abandoned run, and the one an operator writing
# "this was a test" would also produce. Both are fixtures.
SMOKE_SUMMARY = re.compile(r"\bconsole smoke test\b|\bsmoke test\b", re.IGNORECASE)

SMOKE_PLAYBOOK = re.compile(r"^Smoke \d{4,8}\b|\bsmoke test\b", re.IGNORECASE)


def persona_origin(row: dict[str, Any]) -> str:
    """A persona's origin. Personas are always human-authored or fixtures."""
    name = str(row.get("persona_name") or "")
    if SMOKE_PERSONA.match(name.strip()):
        return "test_fixture"
    return "authored"


def record_origin(row: dict[str, Any]) -> str:
    """A historical record's origin.

    `actor_type` already distinguishes a human note from something The Office recorded
    on its own, so `system` needs no pattern. What it cannot distinguish is a real
    machine record from one a smoke run produced, and that is what the summary is read
    for.
    """
    summary = str(row.get("summary") or "")
    if SMOKE_SUMMARY.search(summary):
        return "test_fixture"
    if str(row.get("actor_type") or "") == "system":
        return "system"
    return "authored"


def playbook_origin(row: dict[str, Any]) -> str:
    title = str(row.get("title") or "")
    if SMOKE_PLAYBOOK.search(title.strip()):
        return "test_fixture"
    return "authored"


def substantive(entries: list[dict[str, Any]], origin_of: Any) -> list[dict[str, Any]]:
    """The entries that mean something. Fixtures are excluded, never deleted.

    Returned rather than counted, because the caller usually needs both the number and
    the rows - and computing the two separately is how a count comes to disagree with
    the list beneath it.
    """
    return [entry for entry in entries if origin_of(entry) != "test_fixture"]


__all__ = [
    "persona_origin",
    "playbook_origin",
    "record_origin",
    "substantive",
]
