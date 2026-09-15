"""broker/env.py - opt-in `.env` loading, where the environment always wins.

Decisions entries 38 and 88: a variable in `.env` that nobody exported was invisible to every
module reading `os.environ`, and the Village client fell back to a port a different service
holds. These tests pin the two properties the loader exists for, and the one that kept it out
of `broker/__init__.py`.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from broker import env

NAME = "OFFICE_ENV_LOADER_TEST_VALUE"


@pytest.fixture
def dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv(NAME, raising=False)
    monkeypatch.delenv(NAME + "_SECOND", raising=False)
    path = tmp_path / ".env"
    path.write_text(f"{NAME}=from-file\n{NAME}_SECOND=also-from-file\n", encoding="utf-8")
    return path


def test_a_name_only_in_the_file_reaches_the_environment(dotenv: Path, monkeypatch):
    filled = env.load_dotenv_file(dotenv)
    assert os.environ[NAME] == "from-file"
    assert filled == sorted([NAME, NAME + "_SECOND"])
    # monkeypatch owns cleanup of names it deleted; these two were set by the loader.
    monkeypatch.delenv(NAME, raising=False)
    monkeypatch.delenv(NAME + "_SECOND", raising=False)


def test_an_exported_value_wins_even_when_empty(dotenv: Path, monkeypatch):
    """A value somebody exported is a decision for this process; `.env` is only a default."""
    monkeypatch.setenv(NAME, "")
    filled = env.load_dotenv_file(dotenv)
    assert os.environ[NAME] == ""
    assert NAME not in filled
    monkeypatch.delenv(NAME + "_SECOND", raising=False)


def test_a_missing_file_is_a_no_op(tmp_path: Path):
    """CI and containers have no `.env`, and their environment is complete without one."""
    assert env.load_dotenv_file(tmp_path / "absent.env") == []


def test_the_default_path_is_the_repository_root_not_the_working_directory():
    assert Path(env.__file__).resolve().parents[1] / ".env" == env.DEFAULT_PATH


def test_importing_broker_loads_nothing():
    """The property that kept the loader out of `broker/__init__.py`.

    `tests/conftest.py` imports `broker.db` before reading the database DSNs. A loader that
    ran on import would feed `.env` into that read, and `pytest` without exported DSNs would
    stop skipping the database tests and run them - against the development database when
    `.env` has no OFFICE_TEST_*. Checked in a fresh interpreter, so this test process's own
    environment cannot answer for it.
    """
    probe = (
        "import os, sys; "
        "before = set(os.environ); "
        "import broker, broker.db, broker.config; "
        "sys.exit(0 if set(os.environ) == before else 1)"
    )
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("OFFICE_", "VILLAGE_"))}
    result = subprocess.run(
        [sys.executable, "-c", probe], env=clean,
        cwd=Path(env.__file__).resolve().parents[1], capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "importing broker changed os.environ - `.env` loading must stay opt-in, see "
        "broker/env.py and tests/conftest.py's DSN read"
    )


def test_both_command_line_entry_points_opt_in():
    """The two CLIs are the processes the loader is for. Pinned so a refactor cannot drop it."""
    root = Path(env.__file__).resolve().parents[1]
    for entry in ("broker/__main__.py", "generators/__main__.py"):
        source = (root / entry).read_text(encoding="utf-8")
        assert "load_dotenv_file()" in source, f"{entry} no longer loads .env"
    importlib.import_module("broker.env")
