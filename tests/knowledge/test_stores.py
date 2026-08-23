"""K1-K11 - the four knowledge bases Part 6 names and Phase 3 did not build.

Each store has exactly one property that makes it a knowledge base rather than a table
with a screen over it, and each of those properties is what these tests are about. A
test that only asserted rows go in and come out would pass against four filing cabinets.

The two that matter most are the ones enforced by the database rather than by code:
`office_app` cannot read a persona body, and cannot rewrite history. Both are asserted
against the runtime role, never the superuser - a superuser bypasses role grants, so
asserting against `admin` would prove nothing at all.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from broker import knowledge
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000aaaa")
MINE = "greenstone"
THEIRS = "burkham-wickmont"


@pytest.fixture(autouse=True)
def _clean(admin: psycopg.Connection):
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM playbook_share")
        cur.execute("DELETE FROM business_playbook")
        cur.execute("DELETE FROM compliance_library_entry WHERE entry_ref LIKE 'test/%'")
        cur.execute("DELETE FROM persona WHERE venture_id = ANY(%s)", ([MINE, THEIRS],))
        cur.execute("ALTER TABLE historical_record DISABLE TRIGGER historical_record_append_only")
        cur.execute("DELETE FROM historical_record WHERE venture_id = ANY(%s)", ([MINE, THEIRS],))
        cur.execute("ALTER TABLE historical_record ENABLE TRIGGER historical_record_append_only")
    conn.commit()


ENTRY = {
    "framework": "FTC_TSR",
    "jurisdiction": ["FEDERAL"],
    "applicability_rule": "Outbound cold calls.",
    "agent_behavior_implication": "State identity and purpose before anything else.",
    "escalation_trigger": "The called party asserts a do-not-call registration.",
    "citation": "16 CFR 310",
}


# ======================================================= 6.2 business playbooks

async def test_a_playbook_is_invisible_to_another_venture_until_a_share_exists(_clean):
    """K1 - Part 6.2, the whole of it.

    The read path takes a venture and resolves shares in the query. A function that
    returned everything and left scoping to the caller would work correctly at every
    call site except the one that forgot, and that call site would look exactly like
    the others.
    """
    async with connection() as conn:
        written = await knowledge.author_playbook(
            conn, venture_id=MINE, title="Cold call opener", playbook_version="1.0.0",
            content={"steps": ["identify", "state purpose"]}, authored_by=AUTHOR,
            lifecycle_stage="Source",
        )

        assert [p.title for p in await knowledge.playbooks_for(conn, MINE)] == [
            "Cold call opener"
        ]
        assert await knowledge.playbooks_for(conn, THEIRS) == [], (
            "absence of a share row is a refusal, not an oversight"
        )

        await knowledge.share_playbook(
            conn, playbook_id=written.playbook_id, to_venture_id=THEIRS,
            shared_by=AUTHOR, reason="same outbound motion, reviewed by both operators",
        )
        shared = await knowledge.playbooks_for(conn, THEIRS)

    assert [p.title for p in shared] == ["Cold call opener"]
    assert shared[0].shared_from == MINE, (
        "a borrowed playbook must be marked as borrowed; an operator reading it needs "
        "to know it describes another venture's motion"
    )


async def test_revoking_a_share_hides_the_playbook_again(_clean):
    """K2 - and the row stays, so who saw what survives the withdrawal."""
    async with connection() as conn:
        written = await knowledge.author_playbook(
            conn, venture_id=MINE, title="Underwriting checklist",
            playbook_version="1.0.0", content={"steps": ["pull comps"]},
            authored_by=AUTHOR,
        )
        await knowledge.share_playbook(
            conn, playbook_id=written.playbook_id, to_venture_id=THEIRS,
            shared_by=AUTHOR, reason="cross-venture pattern",
        )
        await knowledge.revoke_share(
            conn, playbook_id=written.playbook_id, to_venture_id=THEIRS
        )

        assert await knowledge.playbooks_for(conn, THEIRS) == []
        shares = await knowledge.list_shares(conn)

    assert len(shares) == 1
    assert shares[0]["revoked_at"] is not None
    assert shares[0]["reason"] == "cross-venture pattern", (
        "the reason survives revocation, or the record of the decision does not"
    )


async def test_sharing_requires_a_reason_and_cannot_target_the_owner(_clean):
    async with connection() as conn:
        written = await knowledge.author_playbook(
            conn, venture_id=MINE, title="X", playbook_version="1.0.0",
            content={"a": 1}, authored_by=AUTHOR,
        )
        with pytest.raises(knowledge.KnowledgeError, match="requires a reason"):
            await knowledge.share_playbook(
                conn, playbook_id=written.playbook_id, to_venture_id=THEIRS,
                shared_by=AUTHOR, reason="  ",
            )
        with pytest.raises(knowledge.KnowledgeError, match="already sees its own"):
            await knowledge.share_playbook(
                conn, playbook_id=written.playbook_id, to_venture_id=MINE,
                shared_by=AUTHOR, reason="pointless",
            )


async def test_authoring_supersedes_and_the_hash_is_computed(_clean):
    """Same rule as instructions: a supplied hash is a claim, a computed one is a fact."""
    async with connection() as conn:
        first = await knowledge.author_playbook(
            conn, venture_id=MINE, title="Opener", playbook_version="1.0.0",
            content={"steps": ["a"]}, authored_by=AUTHOR,
        )
        second = await knowledge.author_playbook(
            conn, venture_id=MINE, title="Opener", playbook_version="2.0.0",
            content={"steps": ["a", "b"]}, authored_by=AUTHOR,
        )
        live = await knowledge.playbooks_for(conn, MINE)

    assert len(first.content_hash) == 64
    assert first.content_hash != second.content_hash
    assert len(live) == 1, "one live version per title"
    assert live[0].playbook_version == "2.0.0"


# ====================================================== 6.3 compliance library

@pytest.mark.parametrize("omit", list(knowledge.REQUIRED_ENTRY_FIELDS))
async def test_an_entry_missing_any_of_the_six_fields_is_refused(_clean, omit):
    """K3 - all six, or it is a prose store with column headings.

    Parameterised over every field rather than testing one, because "we check the
    required fields" is the kind of claim that is true of five of them.
    """
    fields = dict(ENTRY)
    fields[omit] = [] if omit == "jurisdiction" else "   "

    async with connection() as conn:
        with pytest.raises(knowledge.KnowledgeError) as exc:
            await knowledge.author_compliance_entry(
                conn, entry_ref="test/incomplete", authored_by=AUTHOR, **fields
            )
    assert omit in str(exc.value)


async def test_an_entry_resolves_by_ref_and_reports_both_halves(_clean):
    """`resolve_entry_refs` returns found and missing.

    Both, because "3 of 5 resolved" and "3 resolved" are different reports and only one
    of them tells the reader to go and write something.
    """
    async with connection() as conn:
        await knowledge.author_compliance_entry(
            conn, entry_ref="test/ftc-tsr", authored_by=AUTHOR,
            runtime_flag="tsr_disclosure_required", **ENTRY,
        )
        found, missing = await knowledge.resolve_entry_refs(
            conn, ["test/ftc-tsr", "test/does-not-exist"]
        )
        flags = await knowledge.flags_with_entries(conn)

    assert found == ["test/ftc-tsr"]
    assert missing == ["test/does-not-exist"]
    assert "tsr_disclosure_required" in flags


async def test_the_database_refuses_a_blank_field_even_if_the_function_is_bypassed(
    _clean, app: psycopg.Connection
):
    """The constraint is the control; the function's check is the better message.

    Checked twice on purpose. A caller reaching the table directly - a migration, a
    script, a future route - still cannot write an entry with an empty behavioural
    implication.
    """
    with app.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            """
            INSERT INTO compliance_library_entry
              (entry_ref, framework, jurisdiction, applicability_rule,
               agent_behavior_implication, escalation_trigger, citation, authored_by)
            VALUES ('test/blank', 'X', ARRAY['FEDERAL'], 'when', '   ', 'trigger',
                    'cite', %s)
            """,
            (str(AUTHOR),),
        )
    app.rollback()


# ========================================================= 6.4 persona library

async def test_the_runtime_role_cannot_read_a_persona_body(_clean, app: psycopg.Connection):
    """K6 - the control Part 6.4 actually needs.

    "SimForge only, never production" enforced by a column privilege rather than by the
    absence of a getter. Someone adding a read path later gets a privilege error instead
    of a leak, which is the difference between a boundary and a habit.

    Asserted against `app`, the runtime role. Asserting against the superuser would
    prove nothing: a superuser bypasses column grants.
    """
    with app.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("SELECT persona_body FROM persona LIMIT 1")
    app.rollback()

    with app.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("SELECT * FROM persona LIMIT 1")
    app.rollback()


async def test_the_runtime_role_can_author_a_persona_and_read_its_index(_clean):
    """K7 - write-only on the body is the point, not an accident that broke authoring."""
    async with connection() as conn:
        persona_id = await knowledge.author_persona(
            conn, venture_id=MINE, persona_name="Stalled broker",
            target_persona="Regional broker with stale pocket listings",
            persona_version="1.0.0",
            persona_body={"disposition": "impatient", "objections": ["fees"]},
            authored_by=AUTHOR,
        )
        index = await knowledge.persona_index(conn, MINE)

    assert persona_id
    assert len(index) == 1
    assert index[0]["persona_name"] == "Stalled broker"
    assert len(index[0]["body_hash"]) == 64, "the hash identifies it without revealing it"
    assert "persona_body" not in index[0]


async def test_no_module_reads_a_persona_body(_clean):
    """K8 - the negative obligation, checked the only way it can be.

    The column privilege makes a read fail at runtime. This makes it fail at review, and
    the two catch different things: the privilege stops a body reaching a caller, and
    this stops one being *written into a query at all* - including in a code path that
    never runs, which is where a leak waits patiently for the day somebody widens a
    grant.

    Two checks, because they answer different questions. **No source file may select
    the column**, anywhere, including the module that writes it - the detector is proved
    able to fail against a deliberately leaky sample, because a check that has only ever
    seen compliant source proves the source is compliant. And the **agent-facing client
    may not name it at all**: the authoring path legitimately spans a route and a write
    function, so a blanket ban would forbid writing a persona, but `client/` is what an
    agent calls and has no reason to mention it.

    Docstrings and comments are excluded. The sentence explaining that the runtime role
    holds no read privilege here is the thing a reader most needs, and a check that
    forbids saying so teaches people to delete the explanation.

    Three other layers cover what this cannot: the column privilege refuses a read at
    runtime (`test_the_runtime_role_cannot_read_a_persona_body`), an HTTP test writes a
    marker body and asserts it comes back from no route, and the console smoke script
    greps every rendered page for it.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    sources = [
        path
        for directory in ("broker", "client", "generators")
        for path in (root / directory).rglob("*.py")
    ]

    # Per string literal, not per file. A file-wide regex matches a SELECT in one query
    # against the column name in an unrelated one three statements later, which is a
    # check that fails for the wrong reason - and this suite has been bitten by exactly
    # that shape before.
    reading = []
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))

        # Docstrings are documentation, like comments: the sentence explaining that the
        # runtime role holds no SELECT on this column is the thing a reader most needs,
        # and a check that forbids saying so teaches people to delete the explanation.
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef
                          | ast.AsyncFunctionDef)
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
            lowered = node.value.lower()
            if "select" in lowered and "persona_body" in lowered:
                reading.append(f"{path.relative_to(root)}:{node.lineno}")
    assert reading == [], (
        f"a SELECT names persona_body in {reading}. Part 6.4 is SimForge only; the "
        "column privilege would refuse this at runtime, and a query that only fails "
        "when it runs is a leak waiting for someone to widen a grant."
    )

    # The check must be provably able to fail. A boundary test that has only ever seen
    # compliant source proves the source is compliant, not that the check works - the
    # same reason `tests/golden/stub_simforge.py` ships a deliberately leaky stub.
    leaky = ast.parse(
        'async def read(conn):\n'
        '    await conn.execute("SELECT persona_body FROM persona")\n'
    )
    caught = [
        node
        for node in ast.walk(leaky)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and "select" in node.value.lower() and "persona_body" in node.value.lower()
    ]
    assert caught, "the detector does not catch a plain SELECT; the check above is vacuous"

    # The agent-facing library may not name the column under any circumstances. The
    # authoring path legitimately spans two modules - the route that accepts a body and
    # the function that writes it - so a blanket ban on the name would forbid writing
    # one at all. `client/` has no such excuse: it is what an agent calls, and Part 6.4
    # is about exactly that side of the boundary.
    in_client = [
        f"{path.relative_to(root)}:{number}"
        for path in (root / "client").rglob("*.py")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "persona_body" in line and not line.lstrip().startswith("#")
    ]
    assert in_client == [], (
        f"the agent-facing client names persona_body: {in_client}. SimForge only means "
        "the production side of the boundary never mentions it."
    )


# ====================================================== 6.5 historical records

async def test_the_runtime_role_cannot_rewrite_history(_clean, app: psycopg.Connection):
    """K9 - append-only, asserted against the role that would do it.

    Both layers are live: the grant means UPDATE and DELETE were never given, and the
    trigger catches the realistic failure where somebody grants too much later.
    """
    async with connection() as conn:
        await knowledge.record(
            conn, record_type="note", venture_id=MINE,
            summary="something worth remembering", actor_type="human",
            recorded_by=AUTHOR,
        )

    for statement in (
        "UPDATE historical_record SET summary = 'rewritten' WHERE venture_id = %s",
        "DELETE FROM historical_record WHERE venture_id = %s",
    ):
        with app.cursor() as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute(statement, (MINE,))
        app.rollback()


async def test_a_record_needs_a_summary(_clean):
    """A record nobody can read at a glance is an archive rather than a memory."""
    async with connection() as conn:
        with pytest.raises(knowledge.KnowledgeError, match="needs a summary"):
            await knowledge.record(
                conn, record_type="note", venture_id=MINE, summary="   ",
                actor_type="human", recorded_by=AUTHOR,
            )


async def test_a_human_record_names_the_human(_clean, app: psycopg.Connection):
    """Part 9: humans sign, not agents. An unattributed human act is a system act."""
    with app.cursor() as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute(
            "INSERT INTO historical_record (venture_id, record_type, summary, actor_type) "
            "VALUES (%s, 'note', 'anonymous', 'human')",
            (MINE,),
        )
    app.rollback()


async def test_history_is_newest_first_and_scopes_to_a_venture(_clean):
    async with connection() as conn:
        for i in range(3):
            await knowledge.record(
                conn, record_type="note", venture_id=MINE, summary=f"note {i}",
            )
        await knowledge.record(
            conn, record_type="note", venture_id=THEIRS, summary="theirs",
        )
        mine = await knowledge.history(conn, venture_id=MINE)
        everything = await knowledge.history(conn)

    assert [r["summary"] for r in mine] == ["note 2", "note 1", "note 0"]
    assert len(everything) >= 4
