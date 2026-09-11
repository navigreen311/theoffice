"""Two SQL shapes that produce plausible wrong numbers, caught at review.

Both of these shipped. Neither raised anything, neither logged anything, and neither
would have been caught by a type checker or by any test that did not happen to assert
the specific number involved:

  * a venture with **no grants at all** reported one live grant, because
    `count(*) FILTER (WHERE g.revoked_at IS NULL)` counts the single all-NULL row a
    LEFT JOIN produces when it matches nothing - and `NULL IS NULL` is true;

  * the three capacity numbers **did not sum to the roster**, because `bool_or` over
    zero rows is NULL, `NOT NULL` is NULL rather than TRUE, and an agent with no
    certification row therefore matched none of the three filters.

The second one is the worse of the two: the docstring directly above that query says
"all three, always - one hides the state", and the three numbers were quietly omitting
somebody. Nothing surfaced it because the totals simply did not add up and nobody was
adding them.

That is the argument for a structural check rather than a fix. A defect class that
produces a believable number, in a system whose entire value is believable numbers, is
worth failing the build over.

Scoped to SQL containing `LEFT JOIN`, because that is the only place either shape is
wrong: with an inner join every group has at least one row and both idioms are fine.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

from broker.db import connection
from tests.conftest import requires_db

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGES = ("broker", "client", "generators")

# `count(*) FILTER (WHERE <anything> IS NULL)`. After a LEFT JOIN the unmatched row has
# every right-hand column NULL, so the filter is TRUE for a row that represents nothing.
COUNT_STAR_IS_NULL = re.compile(
    r"count\s*\(\s*\*\s*\)\s*filter\s*\(\s*where[^)]*\bis\s+null\b", re.IGNORECASE
)

# `bool_or(...)` / `bool_and(...)` not wrapped in COALESCE. Over an empty group the
# result is NULL, and `NOT NULL` is NULL - so a negated filter silently excludes the
# group instead of including it.
BOOL_AGG = re.compile(r"\bbool_(?:or|and)\s*\(", re.IGNORECASE)
COALESCED_BOOL_AGG = re.compile(
    r"coalesce\s*\(\s*bool_(?:or|and)\s*\(", re.IGNORECASE
)


def joined_source(node: ast.JoinedStr) -> str:
    """An f-string put back together as one string, each `{...}` written as `{}`.

    Without this an f-string reaches the checks below as one fragment per placeholder,
    and the pairing those checks rest on is gone: a `count(*)` on one side of an
    interpolation and the `LEFT JOIN` on the other are never seen together, so the
    query is swept and nothing in it can fail. That is not hypothetical. The six
    `live_grants` queries became f-strings the moment they started asking the
    `revocation` table (B40), and all six silently left this sweep in the same commit -
    a guard narrowing itself while every test stayed green.

    The placeholder is NOT expanded. These are source-shape checks and the shape is
    what somebody wrote here; substituting a value would make the check depend on what
    a constant happens to hold today.
    """
    return "".join(
        value.value if isinstance(value, ast.Constant) and isinstance(value.value, str)
        else "{}"
        for value in node.values
    )


def sql_literals() -> list[tuple[pathlib.Path, int, str]]:
    """Every string in the source that looks like SQL with a LEFT JOIN.

    Read per string literal rather than per file: a file-wide regex would pair a
    `LEFT JOIN` in one query with a `count(*)` in an unrelated one three statements
    later, which is a check that fails for a reason it did not ask about.

    f-strings count, reassembled by `joined_source`. A query built with an interpolated
    predicate is still one query.
    """
    out: list[tuple[pathlib.Path, int, str]] = []
    for package in PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {
                id(node.body[0].value)
                for node in ast.walk(tree)
                if isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                )
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            }
            # Every node that lives INSIDE an f-string. Its pieces are read through the
            # f-string that owns them, so reading them again would report the same query
            # two or three times - once whole and once per fragment - and a fragment
            # that cannot fail would sit in the parametrised ids looking like coverage.
            owned: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    for piece in ast.walk(node):
                        if piece is not node:
                            owned.add(id(piece))

            for node in ast.walk(tree):
                if id(node) in owned:
                    continue
                if isinstance(node, ast.JoinedStr):
                    text = joined_source(node)
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if id(node) in docstrings:
                        continue
                    text = node.value
                else:
                    continue
                if "left join" in text.lower():
                    out.append((path, node.lineno, text))
    return out


def test_there_is_sql_to_check():
    """A sweep that finds nothing passes for the wrong reason."""
    assert len(sql_literals()) >= 5


@pytest.mark.parametrize(
    ("path", "line", "sql"),
    [pytest.param(p, n, s, id=f"{p.name}:{n}") for p, n, s in sql_literals()],
)
def test_no_count_star_filtered_on_a_null_check_after_a_left_join(
    path: pathlib.Path, line: int, sql: str
):
    """`count(*)` counts rows; a LEFT JOIN miss is a row.

    Count a column from the joined side instead - `count(g.grant_id)` skips the NULL
    row, which is the entire difference between "no grants" and "one grant".
    """
    match = COUNT_STAR_IS_NULL.search(sql)
    assert match is None, (
        f"{path.relative_to(ROOT)}:{line} filters `count(*)` on an IS NULL check inside "
        f"a LEFT JOIN: {match.group(0) if match else ''!r}. The unmatched row has every "
        "right-hand column NULL, so it satisfies the filter and gets counted - this is "
        "how a venture with no grants reported one. Count a column from the joined "
        "side: `count(g.grant_id) FILTER (...)`."
    )


@pytest.mark.parametrize(
    ("path", "line", "sql"),
    [pytest.param(p, n, s, id=f"{p.name}:{n}") for p, n, s in sql_literals()],
)
def test_bool_aggregates_after_a_left_join_are_coalesced(
    path: pathlib.Path, line: int, sql: str
):
    """`bool_or` over an empty group is NULL, and `NOT NULL` is not TRUE.

    Without a COALESCE the group falls out of every negated filter, which is how three
    capacity numbers stopped summing to the roster they were counting.
    """
    total = len(BOOL_AGG.findall(sql))
    coalesced = len(COALESCED_BOOL_AGG.findall(sql))
    assert total == coalesced, (
        f"{path.relative_to(ROOT)}:{line} uses bool_or/bool_and inside a LEFT JOIN "
        f"without COALESCE ({total - coalesced} of {total}). Over an empty group the "
        "result is NULL and `NOT NULL` is NULL rather than TRUE, so the group matches "
        "no negated filter and vanishes from the totals. Wrap it: "
        "`COALESCE(bool_or(...), false)`."
    )


def test_both_detectors_catch_the_shapes_that_actually_shipped():
    """The checks must be provably able to fail.

    A boundary test that has only ever seen compliant source proves the source is
    compliant. These are the two queries as they were written, verbatim in shape.
    """
    shipped_count_star = """
        SELECT v.venture_id,
               count(*) FILTER (WHERE g.revoked_at IS NULL) AS live_grants
        FROM ventures v
        LEFT JOIN agent_forge_grant g ON g.venture_id = v.venture_id
        GROUP BY v.venture_id
    """
    assert COUNT_STAR_IS_NULL.search(shipped_count_star), (
        "the count(*) detector does not catch the query that shipped"
    )

    shipped_bool_or = """
        SELECT i.office_agent_id,
               bool_or(c.state = 'certified') AS certified
        FROM office_agent_identity i
        LEFT JOIN certification c ON c.office_agent_id = i.office_agent_id
        GROUP BY i.office_agent_id
    """
    assert len(BOOL_AGG.findall(shipped_bool_or)) == 1
    assert len(COALESCED_BOOL_AGG.findall(shipped_bool_or)) == 0, (
        "the bool_or detector does not catch the query that shipped"
    )

    # And the fixed forms pass, or the check is just a ban on the function.
    fixed = shipped_bool_or.replace(
        "bool_or(c.state = 'certified')", "COALESCE(bool_or(c.state = 'certified'), false)"
    )
    assert len(BOOL_AGG.findall(fixed)) == len(COALESCED_BOOL_AGG.findall(fixed))


def test_an_f_string_query_is_swept_whole():
    """A query built with an interpolated predicate is still one query.

    The sweep reads `ast.Constant`. An f-string is not one: it is a `JoinedStr` whose
    pieces are separate constants, so `count(*) FILTER (...)` before the placeholder and
    `LEFT JOIN` after it land in different fragments and neither fragment can fail the
    check. Six `live_grants` queries became f-strings in B40 and left this sweep in the
    same commit, green the whole way.

    So: the bad shape, written as an f-string, must still be caught.
    """
    source = (
        'PRED = "g.venture_id = %(v)s"\n'
        'SQL = f"""\n'
        "    SELECT v.venture_id,\n"
        "           count(*) FILTER (WHERE g.revoked_at IS NULL) AS live_grants\n"
        "    FROM ventures v\n"
        "    LEFT JOIN agent_forge_grant g ON {PRED}\n"
        "    GROUP BY v.venture_id\n"
        '"""\n'
    )
    tree = ast.parse(source)
    joined = [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)]
    assert len(joined) == 1, "the fixture is not one f-string"

    whole = joined_source(joined[0])
    assert "left join" in whole.lower(), "the f-string did not come back whole"
    assert "{}" in whole, "the placeholder was lost, or silently expanded"
    assert COUNT_STAR_IS_NULL.search(whole), (
        "the count(*) detector does not catch the shipped shape once it is an f-string "
        "- which is the state the sweep was in for every query B40 touched"
    )


def test_the_sweep_reaches_f_string_queries():
    """The sweep must actually be reading f-strings, not merely able to.

    `test_an_f_string_query_is_swept_whole` proves `joined_source` works on a fixture.
    That is a different claim: `sql_literals` could stop calling it tomorrow and both
    that test and `test_the_sweep_reports_each_query_once` would stay green - the second
    more comfortably, because fewer queries swept means fewer chances to duplicate.
    Dropping the eight f-string queries out of this file's coverage is exactly the change
    that would pass.

    So the f-string queries are enumerated here independently and every one of them has
    to come back from the sweep. Looking for a placeholder in the collected text is not
    enough: `humans.py` has two plain literals that contain `{}` for unrelated reasons,
    and they kept this check green through a run where the sweep saw no f-string at all.
    """
    expected: set[tuple[str, int]] = set()
    for package in PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.JoinedStr)
                    and "left join" in joined_source(node).lower()
                ):
                    expected.add((path.name, node.lineno))

    assert expected, (
        "no f-string SQL with a LEFT JOIN exists at all, so this check proves nothing "
        "about the sweep. If that is genuinely true now, delete it rather than leave it."
    )
    found = {(p.name, n) for p, n, _ in sql_literals()}
    missing = sorted(expected - found)
    assert not missing, (
        "these queries are built as f-strings and the sweep does not see them, so "
        "nothing in this file can fail on them: "
        + ", ".join(f"{name}:{line}" for name, line in missing)
    )


def test_the_sweep_reports_each_query_once():
    """A fragment counted as a query is coverage that cannot fail.

    An f-string's pieces are `ast.Constant` nodes in their own right. Read both ways,
    one query arrives two or three times - once whole and once per fragment - and the
    duplicates sit in the parametrised ids looking like more checking than there is.
    """
    seen = [(p, n) for p, n, _ in sql_literals()]
    duplicates = {site for site in seen if seen.count(site) > 1}
    assert not duplicates, (
        "the same source location is swept more than once, so an f-string is being read "
        "both whole and in fragments: "
        + ", ".join(f"{p.name}:{n}" for p, n in sorted(duplicates, key=lambda s: s[1]))
    )


# =================================================================================================
# B37 / migration 0036 - `agent_forge_grant.revoked_at` is gone, and stays gone
# =================================================================================================

# A grant alias dereferenced (`g.revoked_at`), or the table and the column named in one
# line. NOT a ban on `revoked_at` itself: `office_human_role`, `playbook_share`,
# `revocation` and `office_agent_identity` each have one and all four are live. What is
# banned is reaching for it through a grant.
#: A backticked span - how this codebase names code inside prose.
BACKTICKED = re.compile(r"`[^`]*`")

GRANT_REVOKED_AT = re.compile(
    r"\bg\.revoked_at\b|agent_forge_grant[^\n]{0,80}?\brevoked_at\b", re.IGNORECASE
)



def _docstring_lines(text: str) -> set[int]:
    """Every line number occupied by a docstring. Empty set if the file will not parse."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines

def test_no_source_file_reads_agent_forge_grant_revoked_at():
    """The column was a second way to stop an agent, and it had no writer.

    `revoke()` inserts a `revocation` row. Nothing in the broker ever wrote this column;
    the only writers in the repository were two test fixtures, which is what made a dead
    column look load-bearing - the kill switch had a test, and the test was operating a
    switch the product does not have.

    **A text check on purpose.** The database no longer has the column, so any query
    naming it raises `UndefinedColumn` - but only when that line executes. Of the
    twenty-seven sites removed in 0036, several sat in console read-paths that no test
    asserts a number from, and one sat in a test helper the suite reached only through a
    fixture ordering: it went unnoticed through a full green run. A grep reads every file
    whether or not anything calls it.
    """
    offenders: list[str] = []

    for folder in ("broker", "generators", "adapters", "scripts", "client", "tests"):
        base = ROOT / folder
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in str(path) or path.name == "test_sql_shapes.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "revoked_at" not in text:
                continue
            prose = _docstring_lines(text)
            for n, line in enumerate(text.splitlines(), 1):
                # Prose about the removal is fine, and is most of what makes it
                # legible. Docstring ranges come from the AST rather than from a
                # line prefix: a continuation line inside a docstring starts with an
                # ordinary word, and the first version of this check flagged six of
                # them. SQL is never in a docstring, so excluding them is free.
                if n in prose or line.lstrip().startswith(("#", "--")):
                    continue
                # Backticked spans are this codebase's convention for naming code
                # inside prose - `audit_events.py` describes the dropped column in a
                # glossary entry, and `components/term.tsx` renders those spans as
                # identifiers for exactly this reason. Stripped before matching, so a
                # sentence ABOUT the column is not mistaken for a read OF it.
                if GRANT_REVOKED_AT.search(BACKTICKED.sub("", line)):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")

    assert not offenders, (
        "these read agent_forge_grant.revoked_at, dropped by migration 0036:\n  "
        + "\n  ".join(offenders)
        + "\nRevocation is a separate table, consulted per call - "
        "revocation.covered_grants()."
    )


@requires_db
@pytest.mark.db
async def test_the_grant_table_has_no_revoked_at_and_is_assignable_does_not_read_one():
    """The schema half, because the text check cannot see a generated column.

    `is_assignable` is `GENERATED ALWAYS AS (...)` and carried `revoked_at IS NULL` as a
    term - which is why `DROP COLUMN` refused until 0036 redefined it. That expression
    lives in the catalogue rather than in any `.py`, so the grep above is blind to it.
    """
    async with connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'agent_forge_grant' AND column_name = 'revoked_at'"
        )
        assert await cur.fetchone() is None, (
            "agent_forge_grant.revoked_at is back. It has no writer and refuses agents "
            "on read - see blocking.md B37."
        )

        await cur.execute(
            "SELECT generation_expression FROM information_schema.columns "
            "WHERE table_name = 'agent_forge_grant' AND column_name = 'is_assignable'"
        )
        row = await cur.fetchone()
        assert row is not None, "is_assignable is missing"
        assert "revoked_at" not in (row[0] or ""), (
            f"is_assignable is generated from revoked_at again: {row[0]}"
        )
