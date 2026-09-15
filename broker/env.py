"""Load the repository's `.env` into the process environment - explicitly, and never by import.

Decisions entries 38 and 88. `broker/config.py`'s `Settings` reads `.env`, but only into its own
fields. Six places in shipped code read `os.environ` directly - `broker.village`'s base URL, the
`env://` credential resolver, the Vault client, the restore-drill DSN and the validator CLI's
database check - and a variable that is in `.env` but was never exported is invisible to all
of them. The Village one does not fail: `broker.village` falls back to its default address,
where a different service answers (docs/port-allocation.md).

OPT-IN, NOT AN IMPORT SIDE EFFECT
=================================

    `tests/conftest.py` imports `broker.db` before it reads the database DSNs. A loader in
    `broker/__init__.py` would feed `.env` into that read, turning `pytest` without exported
    DSNs from "skip every database test" into "run them" - against the development database,
    emptying it, whenever `.env` lacks `OFFICE_TEST_*`. So nothing here runs unless an entry
    point calls it: `python -m broker` and `python -m generators` do, and pytest does not.

THE ENVIRONMENT WINS
====================

    A variable already present in `os.environ` is never overwritten, even with an empty
    string. A value exported by a shell, a CI job or a container is a decision somebody made
    for this process; `.env` is the default for a developer who made none.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

#: The repository's `.env`, found from this file rather than from the working directory, so a
#: command run from anywhere reads the same file. `Settings` resolves `.env` against the cwd;
#: this deliberately does not.
DEFAULT_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_dotenv_file(path: Path | None = None) -> list[str]:
    """Fill `os.environ` from `.env` for names not already set. Returns the names filled.

    A missing file is not an error: CI and containers have none, and their environment is
    complete without it. Returning the names - never the values - lets an entry point say
    what came from the file, so a reader can tell a default from an export.
    """
    source = path or DEFAULT_PATH
    if not source.is_file():
        return []
    filled: list[str] = []
    for name, value in dotenv_values(source).items():
        if value is None or name in os.environ:
            continue
        os.environ[name] = value
        filled.append(name)
    return sorted(filled)
