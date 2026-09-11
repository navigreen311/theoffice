"""`live_grants` means "a grant no live revocation covers", on every screen that says it.

Seven queries computed a field called `live_grants` and not one of them consulted the
`revocation` table. Each said `count(...) FILTER (WHERE g.revoked_at IS NULL)`, against a
column that had no writer - `NULL IS NULL` is true for every row ever inserted - so each
counted **every grant on record, forever**. Migration 0036 dropped the column (B37) and
removed the filter, which changed no number, because the filter had never changed one.

WHY THIS IS A BLOCKER AND NOT A ROUNDING ERROR

    `console/app/agents/roster-controls.tsx` renders, for an agent who has left:

        - holds an Office identity and 2 live grants. Revoke them.

    That is an instruction to a human, computed from a number that does not mean what it
    says. An agent whose grants were revoked an hour ago read identically to one whose
    grants are live, so the reviewer was told to revoke what is already revoked - and in
    the other direction, an agent covered only by a `venture`-scope revocation appeared
    to hold live authority on the one screen that would have shown otherwise.

    Nothing was ever unsafe. `resolve_grant` and Gate 7 both ask the `revocation` table
    and always have, so no agent could act on a revoked grant. The defect was entirely in
    what a person was told. That is why B40 is a `console` item.

WHAT THESE TESTS HOLD

    Each of the seven counters, against a live revocation, at the scope that is hardest
    for it. The one that matters most is `test_a_venture_revocation_reaches_the_cross_
    venture_counters`: four of the seven aggregate across every venture in one statement
    and name no venture anywhere, so a venture-scope revocation is the case a per-venture
    helper cannot serve and a wrong answer is most plausible. It is also the case the
    console reads as authority a departed agent still holds.

    And the forward-looking half: a venture revocation covers grants issued **after** it
    was declared. A predicate that only looked at grants existing at revoke time would
    pass every test above and fail that one.
"""

from __future__ import annotations

import ast
import pathlib
import uuid
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from broker import app as broker_app
from broker import proposals, revocation, roster, ventures
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Two ventures on purpose. Every agent-shaped counter aggregates across both in one
#: statement, so a predicate that quietly scoped itself to one would still pass a
#: single-venture fixture.
HOME = "greenstone"
AWAY = "medlink-pro"

IN_ROSTER = "b40-in-roster"
#: The orphan still HAS a `village_agent_ref` - the column is NOT NULL. What makes it an
#: orphan is that no `village_agent` row carries that ref, which is the state
#: `directory()`'s second query exists to surface: an agent The Office has appointed and
#: the roster cannot account for.
NOT_IN_ROSTER = "b40-not-in-roster"


# ============================================================================ the world


def _purge(admin: psycopg.Connection) -> None:
    """Remove everything this file creates, by the names it creates them under.

    Run BEFORE seeding as well as after. A fixture that only cleans up on the way out
    leaves the database dirty whenever setup itself raises, and the next run then fails
    on a unique constraint - which reads as a broken test rather than as residue from
    the one before it. Keyed on the two refs and the `b40-forge-` prefix rather than on
    ids held in a closure, because the run that left the rows behind is gone.
    """
    with admin.cursor() as cur:
        cur.execute(
            "SELECT office_agent_id FROM office_agent_identity "
            "WHERE village_agent_ref = ANY(%s)",
            ([IN_ROSTER, NOT_IN_ROSTER],),
        )
        agent_ids = [r[0] for r in cur.fetchall()]
        cur.execute(
            "DELETE FROM revocation WHERE forge_id LIKE 'b40-forge-%%' "
            "OR office_agent_id = ANY(%s)",
            (agent_ids,),
        )
        cur.execute(
            "DELETE FROM agent_forge_grant WHERE forge_id LIKE 'b40-forge-%%' "
            "OR office_agent_id = ANY(%s)",
            (agent_ids,),
        )
        cur.execute(
            "DELETE FROM office_agent_identity WHERE office_agent_id = ANY(%s)",
            (agent_ids,),
        )
        cur.execute(
            "DELETE FROM village_agent WHERE village_agent_ref = ANY(%s)",
            ([IN_ROSTER, NOT_IN_ROSTER],),
        )
        cur.execute("DELETE FROM forge_module_registry WHERE forge_id LIKE 'b40-forge-%%'")
        cur.execute("DELETE FROM forge_registry WHERE forge_id LIKE 'b40-forge-%%'")
    admin.commit()


@pytest.fixture
def world(admin: psycopg.Connection):
    """Two agents, four grants, two ventures, two modules.

    `rostered` has a `village_agent` row, so it reaches the roster table and the
    departure diff. `orphan` has an identity and no `village_agent` row, which is the
    only way into `directory()`'s second query - the orphan-identity list.

    Both hold one grant per venture. Two modules, because an `agent_module` revocation
    names a module and a fixture with one module cannot tell "this grant" from "every
    grant this agent holds".
    """
    forge_id = f"b40-forge-{uuid.uuid4().hex[:8]}"
    modules = ("parse_document", "draft_memo")
    ids: dict[str, uuid.UUID] = {}
    grants: dict[tuple[str, str, str], uuid.UUID] = {}

    _purge(admin)

    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO forge_registry (forge_id, display_name, base_url, api_version, "
            "auth_model, credential_mode, health_status) VALUES "
            "(%s, 'B40 Forge', 'https://example.invalid', '1.2.0', 'bearer', "
            " 'brokered', 'GREEN')",
            (forge_id,),
        )
        for module_id in modules:
            cur.execute(
                "INSERT INTO forge_module_registry (forge_id, module_id, module_name, "
                "idempotency_support, is_mutating) VALUES (%s, %s, %s, 'key', TRUE)",
                (forge_id, module_id, module_id.replace("_", " ").title()),
            )

        for key, ref, name in (
            ("rostered", IN_ROSTER, "Wren Halloway"),
            ("orphan", NOT_IN_ROSTER, "Sable Quint"),
        ):
            agent_id = uuid.uuid4()
            ids[key] = agent_id
            if ref == IN_ROSTER:
                cur.execute(
                    "INSERT INTO village_agent (village_agent_ref, agent_name, "
                    "department, role_key, title, status, source) VALUES "
                    "(%s, %s, 'engineering', 'individual_contributor', 'Engineer', "
                    " 'active', 'import')",
                    (ref, name),
                )
            cur.execute(
                "INSERT INTO office_agent_identity (office_agent_id, village_agent_ref, "
                "agent_name, department, status) VALUES (%s, %s, %s, 'engineering', "
                "'active')",
                (agent_id, ref, name),
            )
            # One grant per venture, on the FIRST module. Fully live: both certification
            # refs present and activated, which is what the generated `is_assignable`
            # column requires. A grant that was never assignable would prove nothing -
            # it is already excluded by a different column, for a different reason.
            for venture in (HOME, AWAY):
                grant_id = uuid.uuid4()
                grants[(key, venture, modules[0])] = grant_id
                cur.execute(
                    "INSERT INTO agent_forge_grant (grant_id, office_agent_id, forge_id, "
                    "module_id, venture_id, trust_tier, granted_by, operation_cert_ref, "
                    "dept_context_cert_ref, activated_at, activated_by) VALUES "
                    "(%s, %s, %s, %s, %s, 'suggest', %s, 'cert://op', 'cert://dept', "
                    "now(), %s)",
                    (grant_id, agent_id, forge_id, modules[0], venture,
                     uuid.uuid4(), uuid.uuid4()),
                )
    admin.commit()

    yield {
        "forge_id": forge_id,
        "modules": modules,
        "ids": ids,
        "grants": grants,
        "admin": admin,
    }
    _purge(admin)


def _revoke(
    admin: psycopg.Connection,
    *,
    scope: str,
    office_agent_id: uuid.UUID | None = None,
    forge_id: str | None = None,
    module_id: str | None = None,
    venture_id: str | None = None,
) -> uuid.UUID:
    """A revocation row, written directly.

    `revocation.revoke()` is the writer in production and it is tested where it lives.
    What is under test here is whether the READERS consult this table at all, so the row
    goes in by SQL: a test that could only produce one through the authority check would
    be asserting two things and reporting one.
    """
    revocation_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO revocation (revocation_id, scope, office_agent_id, forge_id, "
            "module_id, venture_id, reason, revoked_by, revoked_by_role, blast_radius) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'B40 test', %s, 'ivan', '{}'::jsonb)",
            (revocation_id, scope, office_agent_id, forge_id, module_id, venture_id,
             uuid.uuid4()),
        )
    admin.commit()
    return revocation_id


def _grant(admin: psycopg.Connection, world: dict, *, agent: str, venture: str,
           module: str) -> uuid.UUID:
    grant_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_forge_grant (grant_id, office_agent_id, forge_id, "
            "module_id, venture_id, trust_tier, granted_by, operation_cert_ref, "
            "dept_context_cert_ref, activated_at, activated_by) VALUES "
            "(%s, %s, %s, %s, %s, 'suggest', %s, 'cert://op', 'cert://dept', now(), %s)",
            (grant_id, world["ids"][agent], world["forge_id"], module, venture,
             uuid.uuid4(), uuid.uuid4()),
        )
    admin.commit()
    return grant_id


# ======================================================== the seven counters, by name


async def _roster_diff(conn, world) -> int:
    """The departure diff - the number the console turns into "Revoke them."."""
    result = await roster.diff(conn, [])
    row = next(
        r for r in result["departed"] if r["village_agent_ref"] == IN_ROSTER
    )
    assert row["has_identity"], "the fixture's rostered agent lost its identity"
    return int(row["live_grants"])


async def _roster_table(conn, world) -> int:
    """`roster.directory()`, first query: the roster table itself."""
    result = await roster.directory(conn, all_departments=())
    row = next(
        a for a in result["agents"]
        if a["office_agent_id"] == str(world["ids"]["rostered"])
    )
    assert row["in_roster"], "the rostered agent should come from the roster query"
    return int(row["live_grants"])


async def _roster_orphans(conn, world) -> int:
    """`roster.directory()`, second query: identities the roster cannot account for."""
    result = await roster.directory(conn, all_departments=())
    row = next(
        a for a in result["agents"]
        if a["office_agent_id"] == str(world["ids"]["orphan"])
    )
    assert not row["in_roster"], "the orphan should come from the unmatched query"
    return int(row["live_grants"])


async def _agent_registry(conn, world) -> int:
    """`GET /api/agents` - the agent registry."""
    rows = await broker_app.list_agents(conn, None)  # type: ignore[arg-type]
    row = next(r for r in rows if r["office_agent_id"] == world["ids"]["rostered"])
    return int(row["live_grants"])


async def _venture_list(conn, world) -> int:
    """`GET /api/ventures` - the venture list."""
    rows = await broker_app.list_ventures(conn, None)  # type: ignore[arg-type]
    row = next(r for r in rows if r["venture_id"] == HOME)
    return int(row["live_grants"])


async def _ventures_table(conn, world) -> int:
    """`ventures.directory()` - the ventures table."""
    result = await ventures.directory(conn)
    row = next(v for v in result["ventures"] if v["slug"] == HOME)
    return int(row["live_grants"])


async def _empty_queue(conn, world) -> int:
    """`proposals.queue()` - the sentence explaining why the queue is empty."""
    result = await proposals.queue(conn)
    return int(result["state"]["live_grants"])


#: Counters keyed on the ROSTERED agent: each aggregates across every venture.
AGENT_COUNTERS = {
    "roster.diff / the Revoke them. sentence": _roster_diff,
    "roster.directory / the roster table": _roster_table,
    "app.list_agents / the agent registry": _agent_registry,
}

#: Counters keyed on one venture. Both still compute every venture in one statement.
VENTURE_COUNTERS = {
    "app.list_ventures / the venture list": _venture_list,
    "ventures.directory / the ventures table": _ventures_table,
}

ALL_COUNTERS = {
    **AGENT_COUNTERS,
    "roster.directory / the orphan-identity list": _roster_orphans,
    **VENTURE_COUNTERS,
    "proposals.queue / the empty-queue explanation": _empty_queue,
}


def test_all_seven_counters_are_under_test():
    """A sweep that forgot one passes for the wrong reason.

    B40's own table said six. There are seven: `roster.py` computes this three times,
    not twice - the diff, the roster table, and the orphan list - and the middle one is
    the roster page itself. A list assembled from a truncated grep is how that happened.
    """
    assert len(ALL_COUNTERS) == 7, sorted(ALL_COUNTERS)


# ================================================================== an agent is stopped


@pytest.mark.parametrize("name", sorted(ALL_COUNTERS))
async def test_an_agent_scope_revocation_reaches_every_counter(world, name):
    """The simplest case, asked of all seven, one at a time so a failure names itself."""
    counter = ALL_COUNTERS[name]
    async with connection() as conn:
        before = await counter(conn, world)
    assert before > 0, f"{name} reported nothing to revoke before the revocation"

    for key in ("rostered", "orphan"):
        _revoke(world["admin"], scope="agent", office_agent_id=world["ids"][key])

    async with connection() as conn:
        after = await counter(conn, world)

    assert after == before - _expected_drop(name, world, scope="agent"), (
        f"{name} did not consult the revocation table: {before} -> {after}"
    )


def _expected_drop(name: str, world: dict, *, scope: str) -> int:
    """How many grants an `agent`-scope revocation over BOTH agents removes here.

    Spelled out per counter rather than asserted as "goes to zero", because three of
    these are global or venture-wide and another test file's rows can be in them. A
    delta is the only figure this fixture actually owns.
    """
    if name in AGENT_COUNTERS:
        return 2  # the rostered agent's two grants, one per venture
    if name.startswith("roster.directory / the orphan"):
        return 2  # the orphan's two grants
    if name in VENTURE_COUNTERS:
        return 2  # one grant each, both agents, in HOME
    return 4  # proposals: every grant this fixture created


# ========================================================== THE CROSS-VENTURE CASE


async def test_a_venture_revocation_reaches_the_cross_venture_counters(world):
    """The case a per-venture helper does not serve, and the one B40 names.

    `revocation.covered_grants(conn, venture_id=...)` answers per venture. Four of the
    seven counters name no venture anywhere: they aggregate an agent's grants across the
    whole portfolio in one statement. A `venture`-scope revocation on ONE venture has to
    reach them anyway, taking exactly the grants issued against that venture and leaving
    the rest - and it is the console's own example, because a departed agent covered by a
    venture revocation is precisely the reader who was told to go and revoke again.
    """
    async with connection() as conn:
        rostered_before = {n: await AGENT_COUNTERS[n](conn, world) for n in AGENT_COUNTERS}
        orphan_before = await _roster_orphans(conn, world)
        home_before = {n: await VENTURE_COUNTERS[n](conn, world) for n in VENTURE_COUNTERS}
        away_before = await _away_counts(conn)

    assert set(rostered_before.values()) == {2}, rostered_before
    assert orphan_before == 2

    _revoke(world["admin"], scope="venture", venture_id=HOME)

    async with connection() as conn:
        rostered_after = {n: await AGENT_COUNTERS[n](conn, world) for n in AGENT_COUNTERS}
        orphan_after = await _roster_orphans(conn, world)
        home_after = {n: await VENTURE_COUNTERS[n](conn, world) for n in VENTURE_COUNTERS}
        away_after = await _away_counts(conn)

    # Each cross-venture counter loses exactly the HOME grant and keeps the AWAY one.
    for name, before in rostered_before.items():
        assert rostered_after[name] == before - 1, (
            f"{name} is cross-venture and did not see a venture-scope revocation: "
            f"{before} -> {rostered_after[name]}. This is the number the console turns "
            "into 'holds an Office identity and N live grants. Revoke them.'"
        )
    assert orphan_after == orphan_before - 1, "the orphan list missed it too"

    for name, before in home_before.items():
        assert home_after[name] == before - 2, (
            f"{name} should have lost both agents' {HOME} grants: {before} -> "
            f"{home_after[name]}"
        )

    assert away_after == away_before, (
        f"a {HOME} revocation moved {AWAY}'s numbers: {away_before} -> {away_after}. "
        "The predicate is wired to the wrong column, or to no column at all."
    )


async def _away_counts(conn) -> dict[str, int]:
    """The other venture's two counters. Must not move when HOME is revoked."""
    listed = await broker_app.list_ventures(conn, None)  # type: ignore[arg-type]
    directory = await ventures.directory(conn)
    return {
        "app.list_ventures": int(
            next(r for r in listed if r["venture_id"] == AWAY)["live_grants"]
        ),
        "ventures.directory": int(
            next(v for v in directory["ventures"] if v["slug"] == AWAY)["live_grants"]
        ),
    }


async def test_a_venture_revocation_covers_a_grant_issued_after_it(world):
    """The forward-looking half, which a column stamped at revoke time cannot do.

    `revocation.py`'s header says it in as many words: a venture-wide revocation must
    apply to grants issued *after* it was declared, and storing the state on the grant
    silently misses that - "exactly how a revoked venture quietly comes back to life".
    A predicate that snapshotted the covered set would pass every other test in this file
    and fail this one, which is why it is here rather than assumed.
    """
    _revoke(world["admin"], scope="venture", venture_id=HOME)

    async with connection() as conn:
        before = await _roster_diff(conn, world)
    assert before == 1, f"only the {AWAY} grant should be left, got {before}"

    _grant(world["admin"], world, agent="rostered", venture=HOME,
           module=world["modules"][1])

    async with connection() as conn:
        after = await _roster_diff(conn, world)

    assert after == before, (
        f"a grant issued into a revoked venture came back as live authority: {before} "
        f"-> {after}. The revocation is live and covers it; this number says it does not."
    )


# ============================================================ the other three scopes


async def test_an_agent_module_revocation_takes_one_module_not_the_agent(world):
    """Scope discrimination, in the direction that over-counts when it is wrong.

    A predicate that dropped the module terms would take both modules; one that dropped
    the agent terms would take the other agent too. Both fail here.
    """
    _, second = world["modules"]
    _grant(world["admin"], world, agent="rostered", venture=HOME, module=second)

    async with connection() as conn:
        before = await _roster_diff(conn, world)
        orphan_before = await _roster_orphans(conn, world)
    assert before == 3, before

    _revoke(
        world["admin"], scope="agent_module",
        office_agent_id=world["ids"]["rostered"],
        forge_id=world["forge_id"], module_id=second,
    )

    async with connection() as conn:
        after = await _roster_diff(conn, world)
        orphan_after = await _roster_orphans(conn, world)

    assert after == 2, (
        f"an agent_module revocation took {before - after} grant(s), not 1. It names one "
        "module; the other module's grants and the other venture's are untouched."
    )
    assert orphan_after == orphan_before, "it reached an agent it does not name"


async def test_a_forge_revocation_takes_every_grant_to_that_forge(world):
    """The widest scope. Names no agent and no venture, and must still reach both."""
    async with connection() as conn:
        assert await _roster_diff(conn, world) == 2
        assert await _roster_orphans(conn, world) == 2

    _revoke(world["admin"], scope="forge", forge_id=world["forge_id"])

    async with connection() as conn:
        assert await _roster_diff(conn, world) == 0, "the forge scope missed the roster"
        assert await _roster_orphans(conn, world) == 0, "and the orphan list"
        assert await _venture_list(conn, world) == 0, "and the venture list"


async def test_a_reinstated_revocation_stops_covering(world):
    """`reinstated_at IS NULL` is part of the rule, not a term a caller remembers.

    A kill switch with no off position is the other half of getting this wrong, and it
    reads as "the revocation worked" right up until somebody needs to lift it.

    At `agent` scope because the schema requires a second named human to lift anything
    wider, and that column carries a foreign key to `office_human`. The term under test
    sits in the predicate rather than in the scope, so the narrow scope proves it.
    """
    revocation_id = _revoke(
        world["admin"], scope="agent", office_agent_id=world["ids"]["rostered"]
    )

    async with connection() as conn:
        assert await _roster_diff(conn, world) == 0

    with world["admin"].cursor() as cur:
        cur.execute(
            "UPDATE revocation SET reinstated_at = now(), reinstated_by = %s, "
            "reinstatement_reason = 'B40 test' WHERE revocation_id = %s",
            (uuid.uuid4(), revocation_id),
        )
    world["admin"].commit()

    async with connection() as conn:
        assert await _roster_diff(conn, world) == 2, (
            "a lifted revocation is still being counted as covering a grant"
        )


async def test_the_counters_agree_with_the_call_path(world):
    """The number on the screen and the answer the broker gives must be one answer.

    `check_revocations` is what actually stops a call, and it has been right all along.
    If a counter says an agent holds authority the call path refuses - or the reverse -
    the screen is describing a system that does not exist. Asserted against the enforcer
    rather than against an expected integer, because an integer can agree with a second
    wrong rule.
    """
    _revoke(world["admin"], scope="venture", venture_id=HOME)
    forge_id, (module_id, _) = world["forge_id"], world["modules"]
    agent_id = world["ids"]["rostered"]

    refused: list[str] = []
    async with connection() as conn:
        for venture in (HOME, AWAY):
            try:
                await revocation.check_revocations(
                    conn, office_agent_id=agent_id, forge_id=forge_id,
                    module_id=module_id, venture_id=venture,
                )
            except Exception:  # broker.errors.Revoked
                refused.append(venture)
        counted = await _roster_diff(conn, world)

    assert refused == [HOME], refused
    assert counted == 2 - len(refused), (
        f"the call path refuses {len(refused)} of this agent's 2 grants and the console "
        f"reports {counted} live. Those are two different answers to one question."
    )


# ================================================== the rule has one copy, and stays one


PREDICATE_MODULES = ("app", "proposals", "roster", "ventures")


def _module_constant(module: str) -> str:
    """`_NOT_REVOKED` as it is written in `broker/<module>.py`, read from source."""
    path = ROOT / "broker" / f"{module}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_NOT_REVOKED"
        ):
            return ast.unparse(node.value)
    raise AssertionError(f"broker/{module}.py has no _NOT_REVOKED")


def test_the_four_modules_ask_the_same_question():
    """One rule, four callers, and the four must be the same text.

    `revocation._covers` exists because this question is asked at two cardinalities and
    the module says so at length: "THIS IS THE RULE. THERE IS ONE COPY OF IT." Four
    console modules now ask it at a third. They call the function rather than re-spell
    it, and this holds the four call sites identical - a second spelling of "is this
    covered" is how two answers to one question ship, each passing its own tests.
    """
    written = {m: _module_constant(m) for m in PREDICATE_MODULES}
    distinct = set(written.values())
    assert len(distinct) == 1, (
        "the four modules build the predicate differently:\n"
        + "\n".join(f"  broker/{m}.py: {t}" for m, t in sorted(written.items()))
    )
    one = distinct.pop()
    assert "revocation._covers" in one, (
        "the predicate no longer comes from revocation._covers, so this is a second "
        f"spelling of the four-scope rule: {one}"
    )
    for term in ("g.office_agent_id", "g.forge_id", "g.module_id", "g.venture_id"):
        assert term in one, (
            f"the predicate does not pass {term} to _covers, so one of the four scopes "
            "cannot match and the grants it covers are counted as live"
        )


def test_the_predicate_carries_all_four_scopes():
    """Read out of what `_covers` actually produces, not out of the argument names.

    The test helper this was modelled on covers two scopes - `agent` and `agent_module` -
    because a departure can only produce those. These screens are not about departures
    alone, and B40 names the `venture` case explicitly. So: the rendered SQL, checked for
    all four.
    """
    rendered = revocation._covers(
        agent="g.office_agent_id", forge="g.forge_id",
        module="g.module_id", venture="g.venture_id",
    )
    for scope in ("forge", "venture", "agent", "agent_module"):
        assert f"scope = '{scope}'" in rendered, f"{scope} is missing from the rule"
    assert "reinstated_at IS NULL" in rendered, "a lifted revocation would still cover"


def _live_grants_sites() -> list[tuple[str, int, str]]:
    """Every SQL string in `broker/` that produces a column called `live_grants`.

    f-strings are read whole and their fragments are skipped. Read both ways, a query
    with an interpolated predicate arrives twice - once entire and once as the piece
    before the placeholder, which contains the `AS live_grants` and not the predicate.
    The check below would then fail on a fragment of a query that is correct.
    """
    out: list[tuple[str, int, str]] = []
    for path in sorted((ROOT / "broker").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        owned: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                owned.update(id(piece) for piece in ast.walk(node) if piece is not node)
        for node in ast.walk(tree):
            if id(node) in owned:
                continue
            if isinstance(node, ast.JoinedStr):
                text = "".join(
                    v.value if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    else "{}"
                    for v in node.values
                )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            else:
                continue
            if "as live_grants" in text.lower():
                out.append((path.name, node.lineno, text))
    return out


def test_no_query_produces_live_grants_without_asking_the_revocation_table():
    """The eighth site, caught at review rather than on a screen.

    This defect has no symptom. The number is plausible, nothing raises, nothing logs,
    and the call path keeps refusing the revoked grant correctly - so the only place the
    error surfaces is a sentence a human acts on. A new counter written the obvious way
    would reproduce it in full and every test in this repository would stay green.
    """
    sites = _live_grants_sites()
    assert len(sites) == 7, (
        "the number of live_grants queries changed; B40 lists them and this test "
        f"enumerates them: {[(f, n) for f, n, _ in sites]}"
    )
    offenders = [
        f"broker/{name}:{line}"
        for name, line, sql in sites
        if "{}" not in sql
    ]
    assert not offenders, (
        "these produce a column called `live_grants` without an interpolated revocation "
        f"predicate: {offenders}. `live_grants` means 'a grant no live revocation "
        "covers'; a count that does not ask the `revocation` table counts every grant "
        "ever issued, and one of these screens tells a human to go and revoke them. "
        "Use the module's `_NOT_REVOKED`. See blocking.md B40."
    )


async def test_the_rendered_sql_is_accepted_by_postgres():
    """`FILTER (WHERE NOT EXISTS (...))` with a correlated subquery, actually executed.

    A predicate that only ever ran inside an aggregate this suite happens to reach would
    be a syntax question answered by luck. This runs the exact construction against the
    live schema.
    """
    predicate = revocation._covers(
        agent="g.office_agent_id", forge="g.forge_id",
        module="g.module_id", venture="g.venture_id",
    )
    async with connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"""
            SELECT count(g.grant_id) FILTER (WHERE NOT EXISTS (
                       SELECT 1 FROM revocation r WHERE {predicate}
                   )) AS live_grants,
                   count(DISTINCT g.grant_id) FILTER (WHERE NOT EXISTS (
                       SELECT 1 FROM revocation r WHERE {predicate}
                   )) AS distinct_live_grants
            FROM office_agent_identity i
            LEFT JOIN agent_forge_grant g ON g.office_agent_id = i.office_agent_id
        """)
        row: Any = await cur.fetchone()
    assert row is not None
    assert row["live_grants"] >= 0
