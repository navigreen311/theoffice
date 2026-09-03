"""P1-P12 - the Pack directory, and the three states a Pack can be in.

The old Packs page listed which ventures had a Pack and gave sixteen characters of a
hash. It could not answer the question a reader opens it with: **can this Pack
provision, and if not, why.** A Pack failing any FAIL rule cannot provision, cannot
generate and cannot appoint - so validation state is the most important thing on the
page, and it was the one thing the page did not carry.

Four properties carry these tests.

**`not validated` and `valid` are different states.** A rule that could not run has
validated nothing. Collapsing the two is the specific failure this page exists to
prevent, so the state machine is asserted directly rather than inferred from what the
page happens to render.

**A draft cannot provision, structurally.** Not by a flag somebody checks - `packs.live`
does not return a draft, so Gate 1 cannot find it and nothing downstream has an input.
The test asserts the mechanism, because a test that only asserted the flag would keep
passing after somebody removed the mechanism.

**Every number carries a real denominator.** `rules_total` and `schema_blocks` are
computed from the validator registry and the model. The brief that specified this page
said 27 rules and 17 blocks; both were already wrong when it was written.

**A template fails on purpose.** A template that passed validation would have shipped a
budget nobody chose, and V18 would report caps as present when the number in them was
invented by this repository.
"""

from __future__ import annotations

import contextlib
import uuid

import httpx
import psycopg
import pytest

from broker import humans, pack_templates, packs, ventures
from broker.app import app
from broker.db import connection
from generators.validator import all_rule_ids
from tests.conftest import requires_db, wipe_venture
from tests.world import PACK_PATH, build_world

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "greenstone"


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


SEED = uuid.UUID("00000000-0000-5000-8000-00000000bbbb")


def _wipe(conn: psycopg.Connection) -> None:
    for slug in (VENTURE, "collingswood"):
        wipe_venture(conn, slug)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
    conn.commit()


class World:
    """A bridged world with the reference Pack stored live, and an operator to read it.

    `build_world` stops short of storing a Pack - it builds the *world* a Pack is
    validated against. Every test here needs one in the store as well, so the fixture
    publishes the reference Pack rather than each test doing it slightly differently.
    """

    def __init__(self, admin: psycopg.Connection, human_id: uuid.UUID, token: str):
        self.admin = admin
        self.human_id = human_id
        self.token = token


@pytest.fixture
async def world(admin: psycopg.Connection):
    _wipe(admin)
    build_world(admin)

    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name="Pack operator", email="packs@packs.invalid"
        )
        await humans.grant_role(
            conn, human_id=human_id, role="venture_operator", venture_id=None,
            granted_by=SEED,
        )
        await packs.store(
            conn,
            yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="1.0.0",
            authored_by=human_id,
        )

    yield World(admin, human_id, token)
    _wipe(admin)


# ============================================================ P1 - route order

async def test_a_literal_path_under_api_packs_is_not_shadowed():
    """P1 - FastAPI matches in declaration order, and it does not warn.

    `/api/packs/directory` was registered after `/api/packs/{venture_id}` and returned
    the Pack detail for a venture literally named "directory" - with a 200 and a body
    that looked plausible enough to read past. Nothing failed; the wrong endpoint
    answered.

    So the ordering is pinned rather than remembered. A new literal segment added below
    the parameterised route fails here instead of silently never being reached.
    """
    # Per method, because a POST does not shadow a GET: Starlette keeps looking when
    # the path matches and the method does not.
    order: list[tuple[str, str]] = [
        (getattr(route, "path", ""), method)
        for route in app.routes
        for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"})
    ]

    for index, (path, method) in enumerate(order):
        if not path.startswith("/api/packs/") or path.startswith("/api/packs/{"):
            continue
        depth = path.count("/")
        earlier = [
            other
            for position, (other, other_method) in enumerate(order)
            if position < index
            and other_method == method
            and other.startswith("/api/packs/{")
            and other.count("/") == depth
        ]
        assert not earlier, (
            f"{method} {path} is declared after {earlier[0]!r} and is therefore "
            "unreachable - FastAPI matches the path parameter first and hands it the "
            "literal segment as a venture id, answering 200 with the wrong body. "
            "Move it above."
        )


# ==================================================== P2-P5 - validation states

async def test_directory_reports_the_failing_rules_message_not_the_rule_name(
    api, world
):
    """P2 - the sentence has to say what is wrong with *this* Pack.

    "every position's modules have instructions authored" is a specification. "no Forge
    Operating Instructions authored for: comp_analysis, place_call" is the thing
    somebody can act on. The page shows the second.
    """
    token = world.token
    admin = world.admin
    with admin.cursor() as cur:
        cur.execute(
            "DELETE FROM forge_operating_instruction WHERE module_id = 'place_call'"
        )
    admin.commit()

    body = (await api.get("/api/packs/directory", headers=auth(token))).json()
    pack = next(p for p in body["packs"] if p["venture_id"] == VENTURE)

    assert pack["validation"]["state"] == "failing"
    failure = next(f for f in pack["validation"]["failures"] if f["rule_id"] == "V11")
    assert "place_call" in failure["message"], (
        "the failure names the rule but not the module - a reader cannot act on it"
    )


async def test_not_validated_is_not_valid(api, world):
    """P3 - the distinction the whole page exists to draw.

    A rule that could not run has validated nothing. If a Pack with an unrun rule and a
    Pack with every rule passing produce the same state, the page is lying about the
    second one.
    """
    token = world.token

    body = (await api.get("/api/packs/directory", headers=auth(token))).json()
    pack = next(p for p in body["packs"] if p["venture_id"] == VENTURE)
    validation = pack["validation"]

    assert validation["state"] in ("failing", "not_validated", "warnings", "valid")
    if validation["not_run"]:
        assert validation["state"] != "valid", (
            f"{[r['rule_id'] for r in validation['not_run']]} could not run, and the "
            "Pack is reported as valid anyway"
        )
    if validation["state"] == "valid":
        assert not validation["failures"] and not validation["not_run"]


async def test_a_deferred_rule_does_not_make_a_pack_permanently_unvalidated(
    api, world
):
    """P4 - deferred is not unrun.

    V24 is evaluated at Gate 4.5 against appointment output, which does not exist at
    Gate 2. Counting it as unrun would make `not validated` permanent and `valid`
    unreachable, which turns the state this page exists to draw into noise. Gate 2
    excludes it from its own NOT_RUN check; this asserts the page agrees.
    """
    token = world.token

    body = (await api.get("/api/packs/directory", headers=auth(token))).json()
    pack = next(p for p in body["packs"] if p["venture_id"] == VENTURE)
    validation = pack["validation"]

    deferred = {rule["rule_id"] for rule in validation["deferred"]}
    unrun = {rule["rule_id"] for rule in validation["not_run"]}
    assert not (deferred & unrun), "a rule is counted as both deferred and unrun"
    assert "V24" not in unrun, (
        "V24 is deferred to Gate 4.5 by design; counting it as unrun makes every Pack "
        "permanently `not validated`"
    )


async def test_every_denominator_is_computed(api, world):
    """P5 - the brief said 27 rules and 17 blocks. Both were wrong when written."""
    token = world.token

    body = (await api.get("/api/packs/directory", headers=auth(token))).json()
    assert body["rules_total"] == len(all_rule_ids())
    assert body["schema_blocks"] == len(packs.schema_blocks()[0])


# ======================================================= P6-P8 - the three states

async def test_a_draft_cannot_be_found_by_gate_1(world):
    """P6 - the mechanism, not the flag.

    A draft cannot provision because `packs.live` does not return it. A test asserting
    only that `status == 'draft'` would keep passing after somebody made `live()` fall
    back to the newest row.
    """
    source = PACK_PATH.read_text(encoding="utf-8")

    # Stored on top of the live 1.0.0, and newer than it. `live()` has to keep returning
    # the older row - a fallback to "the most recent version" would hand Gate 1 the
    # draft and look like an improvement while doing it.
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=source, pack_version="9.9.9-draft",
            authored_by=world.human_id, publish=False,
        )

        current = await packs.live(conn, VENTURE)
        assert current is not None, "the live Pack disappeared when a draft was saved"
        assert current.pack_version == "1.0.0", (
            f"packs.live returned {current.pack_version!r} - the draft is reachable "
            "from Gate 1, and an unfinished Pack can be generated from"
        )
        pending = await packs.draft(conn, VENTURE)
        assert pending is not None
        assert pending.pack_version == "9.9.9-draft"


async def test_publishing_a_draft_supersedes_the_live_one(world):
    """P7 - one live Pack, and the draft is gone once it is published."""
    admin = world.admin
    source = PACK_PATH.read_text(encoding="utf-8")

    async with connection() as conn:
        author = world.human_id
        await packs.store(
            conn, yaml_source=source, pack_version="2.0.0-draft",
            authored_by=author, publish=False,
        )
        published = await packs.publish_draft(conn, VENTURE, published_by=author)

        assert published.pack_version == "2.0.0-draft"
        assert await packs.draft(conn, VENTURE) is None
        current = await packs.live(conn, VENTURE)
        assert current is not None and current.pack_version == "2.0.0-draft"

    with admin.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM business_pack WHERE venture_id = %s AND status = 'live'",
            (VENTURE,),
        )
        row = cur.fetchone()
    assert row is not None and row[0] == 1, "two Packs are live at once"


async def test_drift_is_reported_when_live_is_not_what_is_running(api, world):
    """P8 - live ahead of provisioned is two different systems."""
    token = world.token

    body = (await api.get("/api/packs/directory", headers=auth(token))).json()
    pack = next(p for p in body["packs"] if p["venture_id"] == VENTURE)

    live = pack["versions"]["live"]
    provisioned = pack["versions"]["provisioned"]
    expected = bool(live and provisioned and provisioned != live["version"])
    assert pack["drift"] is expected
    if provisioned is None:
        assert pack["never_provisioned"] is True


# ===================================================== P9-P11 - the templates

def test_every_portfolio_framework_can_be_written_into_a_pack():
    """P9 - the portfolio named a framework the Pack schema cannot express.

    `PORTFOLIO` carried `NRS_648` and the schema's literal is `NRS_648_NV`, so the cyber
    venture's only framework was one no Pack could ever declare - and nothing noticed,
    because nothing had tried to generate a Pack from the portfolio until templates
    existed. Two lists describing the same thing drift; this is what stops them.
    """
    from broker.ventures import PORTFOLIO
    from generators.pack import ComplianceSurface

    allowed = set(
        ComplianceSurface.model_fields["framework"].annotation.__args__  # type: ignore[union-attr]
    )
    for venture in PORTFOLIO:
        for framework in venture.get("frameworks") or []:
            assert framework in allowed, (
                f"{venture['slug']} declares {framework!r}, which is not a value the "
                f"Pack schema accepts - no Pack for it can ever be written"
            )


def test_every_template_parses():
    """P10 - a template that does not parse cannot be saved, validated or fixed."""
    for category in pack_templates.categories():
        source = pack_templates.skeleton(category["category"])
        pack = packs.parse_only(source)
        assert pack.identity.category == category["category"]


async def test_a_template_fails_validation_on_purpose(world):
    """P11 - a passing template would mean a budget nobody chose.

    Every value a template leaves blank is a decision that depends on the venture. A
    template that filled them in with plausible numbers would produce a Pack that passes
    V18 on caps this repository invented, and nothing downstream would ever ask again.
    """
    from generators.validator import validate

    async with connection() as conn:
        for category in pack_templates.categories():
            pack = packs.parse_only(pack_templates.skeleton(category["category"]))
            report = await validate(pack, conn)
            assert report.failures, (
                f"the {category['category']} template passes validation - it is "
                "shipping venture-specific values nobody chose"
            )
            assert any(rule.rule_id == "V18" for rule in report.failures), (
                "the template's budget caps are not failing V18, so a template could "
                "reach production carrying an invented budget"
            )


# ========================================================= P12 - absence

async def test_a_venture_with_no_pack_is_listed_rather_than_omitted(
    api, world
):
    """P12 - absence must not be able to look like health.

    A venture with grants and no Pack cannot provision at all, and the old page rendered
    that as an empty table under a heading - visually identical to everything being
    fine.
    """
    token = world.token
    admin = world.admin
    wipe_venture(admin, "collingswood")
    # Registered through the real path rather than an INSERT, so the row this asserts
    # about is the row the console would actually create. `wipe_venture` clears a
    # venture's dependents and leaves the registry row, which is the right shape for
    # everything else that uses it - so registration is conditional here rather than
    # unconditional.
    async with connection() as conn:
        with contextlib.suppress(ventures.VentureError):
            await ventures.create(
                conn, slug="collingswood", display_name="Collingswood",
                category="Outbound voice", environment="sandbox",
                created_by=world.human_id,
            )

    body = (await api.get("/api/packs/directory", headers=auth(token))).json()
    assert "collingswood" in body["packless"], (
        "a registered venture with no Pack is absent from the directory entirely, so "
        "the page cannot report it"
    )
    assert body["portfolio_size"] >= len(body["unregistered_portfolio"])
    wipe_venture(admin, "collingswood")


# ============================================= P13-P15 - the editor's own data

async def test_the_editor_is_given_the_draft_not_just_the_live_pack(api, world):
    """P13 - a draft the editor cannot see is work that disappears.

    The directory grew drafts and the detail route did not, so a draft saved from the
    directory was invisible on the one screen built to work on it. The editor opened the
    live Pack over the top of it, and the next save wrote over the draft with text the
    operator had never seen as a draft.
    """
    token = world.token
    source = PACK_PATH.read_text(encoding="utf-8")

    async with connection() as conn:
        await packs.store(
            conn, yaml_source=source, pack_version="7.7.7-draft",
            authored_by=world.human_id, publish=False,
        )

    body = (
        await api.get(f"/api/packs/{VENTURE}", headers=auth(token))
    ).json()

    assert body["draft"] is not None, (
        "the detail route returns no draft, so the editor cannot open one"
    )
    assert body["draft"]["pack_version"] == "7.7.7-draft"
    assert body["live"] is not None and body["live"]["pack_version"] == "1.0.0", (
        "the live Pack vanished when a draft was saved"
    )


async def test_a_draft_is_never_labelled_live_in_the_version_history(api, world):
    """P14 - `superseded_at IS NULL` is true of a draft as well as the live Pack.

    The history rendered "live" for anything with no `superseded_at`, so an unpublished
    draft appeared with a green live badge beside the version that was actually in
    force - two rows both claiming to be what a run would provision.
    """
    token = world.token
    async with connection() as conn:
        await packs.store(
            conn, yaml_source=PACK_PATH.read_text(encoding="utf-8"),
            pack_version="8.8.8-draft", authored_by=world.human_id, publish=False,
        )

    body = (await api.get(f"/api/packs/{VENTURE}", headers=auth(token))).json()
    by_version = {row["pack_version"]: row for row in body["versions"]}

    draft_row = by_version["8.8.8-draft"]
    assert draft_row["status"] == "draft"
    assert draft_row["superseded_at"] is None, (
        "this test is pointless unless a draft really does have no superseded_at - "
        "that is the whole reason the old check was wrong"
    )

    live = [row for row in body["versions"] if row["status"] == "live"]
    assert len(live) == 1, f"{len(live)} versions claim to be live"
    assert live[0]["pack_version"] == "1.0.0"


async def test_the_editor_and_the_directory_agree_on_validation_state(api, world):
    """P15 - one Pack cannot be `valid` on one screen and `not validated` on another.

    Both now call `packs.validation_state`. Two copies of a four-state machine disagree
    eventually, and the state they disagree about is whether a document can go live.
    """
    token = world.token

    detail = (await api.get(f"/api/packs/{VENTURE}", headers=auth(token))).json()
    directory = (await api.get("/api/packs/directory", headers=auth(token))).json()
    card = next(p for p in directory["packs"] if p["venture_id"] == VENTURE)

    report = detail["validation"]
    assert report["state"] == card["validation"]["state"]
    assert report["rules_total"] == directory["rules_total"]

    # Three states, and they account for every rule. A rule that could not be evaluated
    # has established nothing, so folding it into a "checked" count produces a badge
    # claiming the document was examined more thoroughly than it was.
    assert (
        report["passed"] + report["failed"] + report["not_evaluable"]
        == len(report["rules"])
        == report["rules_total"]
    )
    assert report["not_evaluable"] == len(
        [row for row in report["rules"] if not row["evaluable"]]
    )
    assert report["passed"] == len(
        [row for row in report["rules"] if row["verdict"] == "PASS"]
    ), "a rule that could not be evaluated is being counted as passing"


# ================================== P16-P19 - three states, and the claim they support

async def test_a_rule_that_could_not_be_evaluated_names_the_gate_that_will(api, world):
    """P16 - a bare NOT_RUN says something did not happen, not what would.

    V24 tests appointment output, which does not exist until the generators run. Saying
    only "NOT_RUN" leaves a reader to decide whether that is a defect, a gap in the Pack,
    or normal - and it is normal, at this gate, for a reason the page can state.
    """
    token = world.token
    body = (await api.get(f"/api/packs/{VENTURE}", headers=auth(token))).json()

    unevaluable = [
        rule for rule in body["validation"]["rules"] if not rule["evaluable"]
    ]
    assert unevaluable, "this world has nothing unevaluable; the test proves nothing"

    for rule in unevaluable:
        assert rule["settled_at_gate"], (
            f"{rule['rule_id']} could not be evaluated and the page cannot say which "
            "gate will settle it"
        )
        assert rule["why_not_here"], (
            f"{rule['rule_id']} names a gate but not why this stage cannot answer it"
        )


async def test_the_summary_never_counts_an_unevaluable_rule_as_passing(api, world):
    """P17 - the badge said `28 of 28 rules checked` with one rule unevaluated.

    Not evaluable, passed and failed are three states. Two of them summed into a
    "checked" count is a claim that the document was examined more thoroughly than it
    was, on the screen where somebody decides whether to publish it.
    """
    token = world.token
    report = (
        await api.get(f"/api/packs/{VENTURE}", headers=auth(token))
    ).json()["validation"]

    by_verdict = {
        "passed": [r for r in report["rules"] if r["verdict"] == "PASS"],
        "failed": [r for r in report["rules"] if r["verdict"] in ("FAIL", "WARN")],
        "not_evaluable": [r for r in report["rules"] if not r["evaluable"]],
    }
    assert report["passed"] == len(by_verdict["passed"])
    assert report["failed"] == len(by_verdict["failed"])
    assert report["not_evaluable"] == len(by_verdict["not_evaluable"])

    # The three partition the rule set. Nothing is double-counted and nothing is lost.
    assert sum(len(v) for v in by_verdict.values()) == report["rules_total"]
    assert not (
        set(r["rule_id"] for r in by_verdict["passed"])
        & set(r["rule_id"] for r in by_verdict["not_evaluable"])
    ), "a rule is counted as both passed and not evaluable"


async def test_a_rule_rechecked_at_a_later_gate_says_so(api, world):
    """P18 - V13 passes here and fails at Gate 4.5.

    Gate 2 estimates approvals from headcount; Gate 4.5 computes them from the real Task
    Ledger, and the two disagree by an order of magnitude with the Gate 2 estimate being
    the optimistic one. A Pack with no failures here has not been shown to be
    provisionable, and the editor must not imply that it has.
    """
    from generators.validator import GATE_45_RECHECKS

    token = world.token
    report = (
        await api.get(f"/api/packs/{VENTURE}", headers=auth(token))
    ).json()["validation"]

    rechecked = [rule for rule in report["rules"] if rule["rechecked_later"]]
    assert rechecked, (
        "nothing is marked as re-checked later, so the editor implies Gate 2 settles "
        "every rule it passes"
    )
    for rule in rechecked:
        assert rule["rule_id"] in GATE_45_RECHECKS
        assert rule["rechecked_reason"], f"{rule['rule_id']} says nothing about why"


def test_the_recheck_list_matches_what_gate_4_5_actually_evaluates():
    """P19 - a constant that drifts from the function it describes is worse than none.

    `GATE_45_RECHECKS` tells the editor which rules a later gate settles. If Gate 4.5
    grows a third rule and this list does not, the editor quietly goes back to implying
    that Gate 2 is the last word on it.
    """
    import inspect

    from generators import validator
    from generators.validator import GATE_45_RECHECKS

    source = inspect.getsource(validator.validate_gate_4_5)
    appended = {
        line.split('"')[1]
        for line in source.splitlines()
        if line.strip().startswith('"V') and '", Severity.' in line
    }
    assert appended == set(GATE_45_RECHECKS), (
        f"validate_gate_4_5 evaluates {sorted(appended)} but GATE_45_RECHECKS says "
        f"{sorted(GATE_45_RECHECKS)}"
    )


async def test_an_abandoned_draft_is_not_called_superseded(api, world):
    """P20 - a released version replaced by a later release, and a draft nobody
    published, are different events.

    One word for both is why the version history read as an unsorted list: an abandoned
    draft above the live version looks like a broken sort when the only thing wrong is
    that the label does not say what happened. And it must not be inferred from the
    version string - `1.2.0` can be a draft and `2.0.0-draft` can be a release.
    """
    token = world.token
    source = PACK_PATH.read_text(encoding="utf-8")

    async with connection() as conn:
        # A draft with no `-draft` in its name, replaced by another. The suffix
        # heuristic this replaced would have called it a superseded release.
        await packs.store(
            conn, yaml_source=source, pack_version="3.3.3",
            authored_by=world.human_id, publish=False,
        )
        await packs.store(
            conn, yaml_source=source, pack_version="3.3.4",
            authored_by=world.human_id, publish=False,
        )

    body = (await api.get(f"/api/packs/{VENTURE}", headers=auth(token))).json()
    rows = {row["pack_version"]: row for row in body["versions"]}

    assert rows["3.3.3"]["status"] == "abandoned"
    assert rows["3.3.3"]["disposition"] == "abandoned draft"
    assert rows["3.3.3"]["superseded_by"] is None, (
        "a draft nobody published cannot have been superseded by a release - saying so "
        "invents a lineage"
    )
    assert rows["1.0.0"]["status"] == "live"
    assert rows["1.0.0"]["runs"] >= 0
