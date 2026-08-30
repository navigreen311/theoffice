"""The Office and the Village are separate applications, and this is what enforces it.

The Village carries the same shape in the other direction, in
`tests/test_objectives.py::TestSeal`. Two applications that agree they are separate and
have no machine-checked statement of it are two applications that will share a module the
first time it is convenient.

WHY AN AST WALK RATHER THAN A GREP

    A grep for `import modules` misses `from modules.heredity import roster`, misses
    `importlib.import_module("modules.world")`, and matches the word inside a docstring
    explaining the rule. The parse tree distinguishes an import from prose, which is the
    same reason the raw-mutation guard in this suite stopped lowercasing whole files.

WHAT A VIOLATION WOULD COST

    A Village import makes The Office unrunnable without the Village on the same
    filesystem, at the same version, with the same Python. It also silently re-couples
    the two databases: `modules.world.village_clock` carries `DB_PATH`, and importing it
    to read a tick would put The Office's process one attribute access away from
    `village.db`. `run_harness --fresh` deletes four state files and has already
    overwritten a database restore once.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Village top-level packages. Anything importable from the Village's own root that could
# be shadowed by a local module of the same name belongs here.
VILLAGE_PACKAGES = {
    "modules",
    "models",
    "app",  # the Village's Quart application package
    "village",
    "villagedata",
    "evolution_bridge",
    "run_harness",
    "trait_generator",
    "position_registry",
}

# The Office's own source. Tests are included: a test that imports a Village module makes
# the suite unrunnable without the Village, which is the same coupling one layer out.
ROOTS = ("broker", "generators", "tests", "scripts")

ROOT = Path(__file__).resolve().parents[2]


def _office_sources() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        directory = ROOT / root
        if not directory.exists():
            continue
        files.extend(
            path
            for path in directory.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return files


def _imported_roots(tree: ast.AST) -> set[str]:
    """Every top-level package name this module imports, however it is written."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` has no module; a relative import cannot reach the Village.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            # `importlib.import_module("modules.world")` is an import that no import
            # statement records, and it is exactly what somebody reaches for after being
            # told not to write the import statement.
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else ""
            )
            if name in ("import_module", "__import__"):
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        roots.add(arg.value.split(".")[0])
    return roots


def test_no_office_module_imports_a_village_package():
    """The seal.

    The Office reaches the Village over HTTP and by no other route. `broker/village.py`
    is the only module that knows the Village exists at all, and it knows it as a base
    URL.
    """
    sources = _office_sources()
    assert sources, "the seal found no Office source to check; the paths are wrong"

    violations: list[str] = []
    for path in sources:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover - a parse failure is its own bug
            pytest.fail(f"{path.relative_to(ROOT)} does not parse: {exc}")

        for root in _imported_roots(tree) & VILLAGE_PACKAGES:
            violations.append(f"{path.relative_to(ROOT)} imports {root!r}")

    assert not violations, (
        "The Office imported a Village package:\n  "
        + "\n  ".join(sorted(violations))
        + "\n\nThe Office talks to the Village over HTTP and by no other route. An import "
        "makes this application unrunnable without the Village on the same filesystem, "
        "and puts its process one attribute access away from village.db - which "
        "`run_harness --fresh` deletes."
    )


def test_the_seal_would_catch_every_way_of_writing_the_import():
    """A guard narrowed to the obvious form is a guard somebody routes around.

    Each of these is a real way to reach a Village module, and the walk has to see all of
    them. Written as a mutation test because the seal passing on a clean tree proves
    nothing about what it would catch.
    """
    cases = {
        "import modules": "import modules",
        "import modules.heredity.roster": "import modules.heredity.roster",
        "from modules import x": "from modules.heredity import roster",
        "aliased": "import modules.world.village_clock as clock",
        "importlib": 'import importlib\nimportlib.import_module("modules.world")',
        "dunder import": '__import__("models")',
        "inside a function": "def f():\n    from modules.heredity import roster\n    return roster",
    }
    for label, source in cases.items():
        roots = _imported_roots(ast.parse(source))
        assert roots & VILLAGE_PACKAGES, f"the seal would not catch: {label}"

    # And it must not fire on prose or on The Office's own modules.
    for label, source in {
        "docstring": '"""Do not import modules.heredity here."""',
        "comment": "# modules.world.village_clock is off limits\nimport httpx",
        "own package": "from broker import village",
        "stdlib": "import ast, json",
    }.items():
        roots = _imported_roots(ast.parse(source))
        assert not (roots & VILLAGE_PACKAGES), f"the seal fires on: {label}"


def test_only_one_module_knows_the_village_exists():
    """Concentration, so the seam is one file rather than a habit.

    Every other module asks `broker.village`. That is what makes the Village's base URL a
    configuration value instead of a string spread through the codebase, and what makes
    the unreachable behaviour one decision instead of a dozen.
    """
    offenders: list[str] = []
    for path in _office_sources():
        if path.name in ("village.py", "test_village_seal.py"):
            continue
        text = path.read_text(encoding="utf-8")
        if "8002" in text or "VILLAGE_BASE_URL" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "these modules name the Village's address directly instead of asking "
        f"broker.village: {offenders}"
    )
