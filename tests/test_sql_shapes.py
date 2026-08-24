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


def sql_literals() -> list[tuple[pathlib.Path, int, str]]:
    """Every string constant in the source that looks like SQL with a LEFT JOIN.

    Read per string literal rather than per file: a file-wide regex would pair a
    `LEFT JOIN` in one query with a `count(*)` in an unrelated one three statements
    later, which is a check that fails for a reason it did not ask about.
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
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if id(node) in docstrings:
                    continue
                if "left join" in node.value.lower():
                    out.append((path, node.lineno, node.value))
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
