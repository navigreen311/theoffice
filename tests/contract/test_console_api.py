"""The Operations API — authority, scope, and the routes that must not exist.

Master prompt Part 17 and Part 14.

Most of these tests are about authorisation, but the one that matters most is
`test_the_api_exposes_no_route_that_bypasses_a_control`. Every control in this system
lives in a guarded function, and an API that reached past one to a table would undo it
while looking like a feature. "Let the operator fix the certification state" is a
reasonable-sounding request that removes the entire certification gate.

So the surface is enumerated and asserted, not reviewed by eye.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import psycopg
import pytest

from broker import humans
from broker.app import app
from broker.db import connection
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

VENTURE = "burkham-wickmont"
OTHER_VENTURE = "greenstone"


@pytest.fixture(autouse=True)
def _clean_humans(admin: psycopg.Connection):
    _wipe(admin)
    yield
    _wipe(admin)


def _wipe(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM signoff_record")
        cur.execute("DELETE FROM office_human_role")
        cur.execute("DELETE FROM office_human")
        cur.execute("DELETE FROM revocation")
        cur.execute("DELETE FROM manifest_disposition")
    conn.commit()


@pytest.fixture
async def api():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://office.invalid"
    ) as client:
        yield client


async def make_human(
    *, name: str, role: str | None = None, venture_id: str | None = None
) -> tuple[uuid.UUID, str]:
    async with connection() as conn:
        human_id, token = await humans.create_human(
            conn, display_name=name, email=f"{name.lower()}@example.invalid"
        )
        if role:
            await humans.grant_role(
                conn, human_id=human_id, role=role,
                granted_by=uuid.uuid4(), venture_id=venture_id,
            )
    return human_id, token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------ authentication

async def test_an_unauthenticated_request_is_refused(api):
    """A1."""
    response = await api.get("/api/health")
    assert response.status_code == 401


async def test_an_unknown_token_is_refused(api):
    response = await api.get("/api/health", headers=auth("not-a-real-token"))
    assert response.status_code == 401


async def test_a_suspended_human_is_refused_on_the_next_request(api, admin):
    """A2 — status is read live, never baked into the token.

    A suspended human is refused on their next request rather than their next session,
    the same rule agent revocation follows and for the same reason.
    """
    human_id, token = await make_human(name="Dana", role="compliance_officer")
    assert (await api.get("/api/health", headers=auth(token))).status_code == 200

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE office_human SET status = 'suspended', suspended_at = now(), "
            "suspended_by = %s WHERE human_id = %s",
            (str(uuid.uuid4()), str(human_id)),
        )
    admin.commit()

    response = await api.get("/api/health", headers=auth(token))
    assert response.status_code == 403
    assert "suspended" in response.json()["detail"]


async def test_a_token_is_stored_only_as_a_hash(admin):
    """Same rule as `credential_ref`: prove possession without being the thing."""
    _human_id, token = await make_human(name="Ivan", role="ivan")
    with admin.cursor() as cur:
        cur.execute("SELECT token_hash FROM office_human WHERE display_name = 'Ivan'")
        row = cur.fetchone()
    assert row is not None
    assert row[0] != token
    assert len(row[0]) == 64


# --------------------------------------------------------- authority and scope

async def test_a_venture_operator_cannot_act_in_a_venture_they_do_not_operate(api):
    """A3 — the check a role string alone cannot make.

    `revocation.assert_authority` answers "is this role strong enough for this scope".
    It cannot answer "is this person an operator of *this* venture", because it only
    ever sees a role string.
    """
    _id, token = await make_human(
        name="Operator", role="venture_operator", venture_id=OTHER_VENTURE
    )
    response = await api.post(
        "/api/revocations",
        headers=auth(token),
        json={"scope": "venture", "reason": "test", "venture_id": VENTURE},
    )
    assert response.status_code == 403
    assert response.json()["error"] == "NotAuthorized"


@pytest.mark.parametrize(
    ("role", "scope", "allowed"),
    [
        ("venture_operator", "agent", True),
        ("venture_operator", "venture", False),
        ("venture_operator", "forge", False),
        ("compliance_officer", "venture", True),
        ("compliance_officer", "forge", False),
        ("ivan", "forge", True),
        ("ivan", "agent", True),
    ],
)
async def test_the_revocation_authority_matrix_is_enforced(
    api, seed_agent, role, scope, allowed
):
    """A4 — master prompt §1.4, end to end through HTTP."""
    _id, token = await make_human(name=f"H{role}{scope}", role=role)
    payload: dict[str, Any] = {"scope": scope, "reason": "matrix test"}
    if scope in ("agent", "agent_module"):
        payload["office_agent_id"] = str(seed_agent)
    if scope in ("forge", "agent_module"):
        payload["forge_id"] = "some-forge"
    if scope == "venture":
        payload["venture_id"] = VENTURE

    response = await api.post("/api/revocations", headers=auth(token), json=payload)
    if allowed:
        assert response.status_code == 201, response.text
    else:
        assert response.status_code == 403, response.text


async def test_reinstatement_requires_the_same_authority_as_the_revocation(
    api, seed_agent
):
    """A5 — otherwise a venture operator could undo a compliance officer's stop, and
    the authority matrix would be decorative."""
    _cid, compliance_token = await make_human(name="Compliance", role="compliance_officer")
    created = await api.post(
        "/api/revocations",
        headers=auth(compliance_token),
        json={"scope": "venture", "reason": "hold", "venture_id": VENTURE},
    )
    assert created.status_code == 201
    revocation_id = created.json()["revocation_id"]

    _oid, operator_token = await make_human(name="Op", role="venture_operator")
    refused = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        headers=auth(operator_token),
        json={"reason": "seems fine to me"},
    )
    assert refused.status_code == 403

    allowed = await api.post(
        f"/api/revocations/{revocation_id}/reinstate",
        headers=auth(compliance_token),
        json={"reason": "investigated, see INC-4"},
    )
    assert allowed.status_code == 200


async def test_hard_cap_reversal_is_ivan_only(api):
    _id, compliance_token = await make_human(name="C", role="compliance_officer")
    refused = await api.post(
        f"/api/ventures/{VENTURE}/reverse-hard-cap",
        headers=auth(compliance_token), json={"reason": "we need it"},
    )
    assert refused.status_code == 403


# ------------------------------------------------- the guarded function, not a copy

async def test_a_disposition_through_the_api_still_requires_a_reason(
    api, admin, seed_forge
):
    """A6 — the API calls the same guarded function, so it inherits the same rule.

    If this passed, it would mean the API had its own UPDATE.
    """
    forge_id, module_id = seed_forge
    with admin.cursor() as cur:
        cur.execute(
            "INSERT INTO manifest_disposition (venture_id, forge_id, module_id) "
            "VALUES (%s, %s, %s)",
            (VENTURE, forge_id, module_id),
        )
    admin.commit()

    _id, token = await make_human(name="Comp", role="compliance_officer")
    response = await api.post(
        "/api/dispositions/resolve",
        headers=auth(token),
        json={"venture_id": VENTURE, "forge_id": forge_id, "module_id": module_id,
              "resolution": "accepted_risk", "reason": "   "},
    )
    # 400 rather than 422: whitespace satisfies pydantic's min_length, so the refusal
    # comes from `sweeps.disposition` itself. That is the assertion - the API did not
    # write its own UPDATE, it called the function that owns the rule.
    assert response.status_code == 400
    assert "reason" in response.json()["detail"]


async def test_authoring_instructions_reports_what_it_invalidated(api, seed_forge):
    """Superseding instructions flips certifications stale. That is the consequence,
    not a side effect to hide from the author."""
    forge_id, module_id = seed_forge
    _id, token = await make_human(name="Author", role="venture_operator")

    content = {
        "what_it_does": "x", "what_it_does_not_do": "x", "inputs": {"a": "b"},
        "correct_sequence": ["a"], "failure_signatures": {"a": "b"},
        "retry_vs_escalate": "x", "never_do": ["x"], "compliance_coupling": ["x"],
    }
    response = await api.post(
        "/api/instructions",
        headers=auth(token),
        json={"forge_id": forge_id, "module_id": module_id,
              "instruction_version": "1.0.0", "forge_api_version": "1.2.0",
              "content": content},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["content_hash"]) == 64
    assert "certifications_invalidated" in body


async def test_incomplete_instructions_are_refused_with_the_missing_section(
    api, seed_forge
):
    forge_id, module_id = seed_forge
    _id, token = await make_human(name="Author2", role="venture_operator")
    content = {"what_it_does": "x"}
    response = await api.post(
        "/api/instructions",
        headers=auth(token),
        json={"forge_id": forge_id, "module_id": module_id,
              "instruction_version": "1.0.0", "forge_api_version": "1.2.0",
              "content": content},
    )
    assert response.status_code == 400
    assert "failure_signatures" in response.json()["detail"]


# ------------------------------------------------------------------ sign-offs

async def test_a_signoff_binds_to_the_artifact_hash_and_is_voided_by_a_change(api):
    """A7 + A8 — Part 14: "artifact change voids signature."

    Void by comparison, so nothing has to remember to revoke anything when the Pack
    is edited.
    """
    _id, token = await make_human(name="Signer", role="venture_operator")
    original = humans.artifact_hash("pack v1")

    created = await api.post(
        "/api/signoffs",
        headers=auth(token),
        json={"gate": "gate_10", "venture_id": VENTURE, "artifact_kind": "pack",
              "artifact_hash": original},
    )
    assert created.status_code == 201

    still = await api.get(
        f"/api/signoffs/{VENTURE}/gate_10",
        headers=auth(token), params={"current_artifact_hash": original},
    )
    assert still.json()["is_signed"] is True
    assert still.json()["voided"] == []

    edited = await api.get(
        f"/api/signoffs/{VENTURE}/gate_10",
        headers=auth(token),
        params={"current_artifact_hash": humans.artifact_hash("pack v2")},
    )
    assert edited.json()["is_signed"] is False, "an edited artifact voids the signature"
    assert len(edited.json()["voided"]) == 1


async def test_separation_of_duties_refuses_a_second_gate_from_the_same_human(api):
    """A9 — `distinct_humans`, which is the entire content of SoD."""
    _id, token = await make_human(name="Solo", role="venture_operator")
    first = await api.post(
        "/api/signoffs",
        headers=auth(token),
        json={"gate": "gate_4", "venture_id": VENTURE, "artifact_kind": "pack",
              "artifact_hash": "a" * 64},
    )
    assert first.status_code == 201

    second = await api.post(
        "/api/signoffs",
        headers=auth(token),
        json={"gate": "gate_10", "venture_id": VENTURE, "artifact_kind": "pack",
              "artifact_hash": "a" * 64},
    )
    assert second.status_code == 403
    assert second.json()["policy"] == "distinct_humans"
    assert second.json()["already_signed"] == "gate_4"


# ------------------------------------------------------------------- auditing

async def test_every_write_is_audited_with_the_human_as_actor(api, admin, seed_agent):
    """A11 — Part 9: humans sign, not agents."""
    human_id, token = await make_human(name="Auditable", role="ivan")
    await api.post(
        "/api/revocations",
        headers=auth(token),
        json={"scope": "agent", "reason": "audit test",
              "office_agent_id": str(seed_agent)},
    )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT actor_type, subject->>'human' FROM audit_log "
            "WHERE event_type = 'console_revocation_created' AND actor_id = %s",
            (str(human_id),),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "human"
    assert row[1] == "Auditable"


# ------------------------------------------------------------ reads

async def test_capacity_reports_all_three_numbers(api):
    """A12 — one number hides the state."""
    _id, token = await make_human(name="Reader", role="venture_operator")
    response = await api.get(f"/api/ventures/{VENTURE}/capacity", headers=auth(token))
    body = response.json()
    for key in (
        "certified_and_free", "certified_but_allocated", "produced_not_yet_certified"
    ):
        assert key in body, f"{key} missing - one number hides the state"


async def test_health_reports_unhealthy_controls(api):
    _id, token = await make_human(name="Health", role="venture_operator")
    body = (await api.get("/api/health", headers=auth(token))).json()
    assert "controls" in body
    assert "unhealthy" in body
    assert isinstance(body["healthy"], bool)


async def test_agent_registry_shows_certified_beside_declared_tier(api, seed_agent):
    """Part 17 lists these side by side because the certified tier caps the declared
    one - a screen showing only one would hide every place they disagree."""
    _id, token = await make_human(name="Registry", role="venture_operator")
    rows = (await api.get("/api/agents", headers=auth(token))).json()
    assert rows
    row = rows[0]
    assert "declared_tier_floor" in row
    assert "certified_tier_floor" in row


# ================================================== THE ONE THAT MATTERS MOST

async def test_the_api_exposes_no_route_that_bypasses_a_control():
    """A10 — the surface is enumerated, not reviewed by eye.

    Every control in this system lives in a guarded function. An API that reached past
    one to a table would undo it while looking like a feature: "let the operator fix
    the certification state" is a reasonable-sounding request that removes the entire
    certification gate.

    If a new route trips this test, the question is not how to make it pass. It is
    whether that route should exist.
    """
    paths = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in ("HEAD", "OPTIONS")
    }
    writes = {p for p, m in paths if m in ("POST", "PUT", "PATCH", "DELETE")}

    forbidden_fragments = (
        "certification", "cert", "flush", "ledger", "shift", "memory",
        "grant", "audit", "chain", "manifest/declare",
    )
    for path in writes:
        for fragment in forbidden_fragments:
            assert fragment not in path.lower(), (
                f"write route {path!r} touches {fragment!r}. Certification state, PHI "
                "flushes, shift assignment, grants and the ledger are not human-editable "
                "through the console - they are outcomes of guarded functions. Confirm "
                "this route cannot bypass a control before adding it here."
            )

    assert writes == {
        # The Village roster. None of these creates an agent: they import what the
        # Village reports, record one it cannot report, and issue identities for agents
        # that already exist. An "add agent" route would contradict the page's own
        # subtitle and become a second source of truth for who exists.
        "/api/agents/roster",
        "/api/agents/roster/preview",
        "/api/agents/identities",
        "/api/agents/village",
        "/api/revocations",
        "/api/revocations/{revocation_id}/reinstate",
        "/api/proposals/{proposal_id}/decide",
        "/api/dispositions/resolve",
        "/api/instructions",
        "/api/ventures/{venture_id}/reverse-hard-cap",
        "/api/signoffs",
        # Pack Editor. `validate` is a POST because the body is a document; it writes
        # nothing, which `test_validate_stores_nothing` asserts rather than trusting.
        "/api/packs/validate",
        "/api/packs",
        # Provisioning Console. `advance` is the only route that can lead to a grant
        # becoming active, and it cannot skip a gate to get there - Gate 11 refuses
        # without a signature bound to the current artifacts and re-checks rather than
        # trusting Gate 10. There is no route that activates a grant directly.
        "/api/provisioning/runs",
        "/api/provisioning/runs/{run_id}/advance",
        "/api/provisioning/runs/{run_id}/review",
        # Stops a run; it cannot start or advance one. Added deliberately: Gate 4
        # review could previously only approve, so the only way for a human to say no
        # was to abandon the run - which means something different to the next person
        # who provisions this venture.
        "/api/provisioning/runs/{run_id}/reject",
        "/api/provisioning/runs/{run_id}/abort",
        "/api/provisioning/runs/{run_id}/signoff",
        # Knowledge Base Manager. Four stores that author content, and none of them
        # touches a control: a playbook is an SOP, a compliance entry is what explains
        # a flag rather than what applies one, a persona is SimForge input, and a
        # historical record is append-only by grant. The one to watch is the persona
        # route - it writes and there is deliberately no route that reads a body back,
        # because `office_app` holds no SELECT on the column.
        "/api/knowledge/playbooks",
        "/api/knowledge/playbooks/share",
        "/api/knowledge/compliance",
        "/api/knowledge/personas",
        "/api/knowledge/history",
        # Human and role administration — the most privilege-sensitive surface in this
        # file. The rules live in `humans.assert_may_grant`: a role may be granted only
        # by somebody holding a STRICTLY stronger one, and never to yourself.
        #
        # The path is `/roles` and not `/grants` on purpose. "Grant" means agent
        # authority over a Forge module everywhere else in this system, and the
        # forbidden-fragment list above would rightly have refused it.
        "/api/humans",
        "/api/humans/{human_id}/roles",
        "/api/humans/{human_id}/status",
        "/api/humans/{human_id}/token",
        # Resolution APPENDS to incident_resolution. `incident` stays append-only and is
        # never edited, so there is deliberately no route that changes an incident's
        # severity — the field somebody under pressure would most want to lower.
        "/api/incidents/{incident_id}/resolve",
        # Running the verification sweeps from the Compliance page. A POST because a
        # sweep is not read-only: the certification sweep recomputes staleness and can
        # move agents out of `certified`, and the manifest sweep can raise incidents.
        # It delegates to `sweeps.run_all`, which is the same function cron calls.
        "/api/controls/run",
        # Part 9's regulator export. A POST because producing a record for CFPB, FTC,
        # HHS OCR or a state DFI is an act somebody performed, and it is audited as one.
        "/api/compliance/export",
        # The venture registry. `POST /api/ventures` creates a DRAFT: it commits a slug
        # that every venture-scoped table will key on for the rest of its life, and
        # nothing else. A draft has no Pack, so there is no manifest and no runtime
        # config to grant against - the inability to receive grants is structural.
        "/api/ventures",
        # Archiving revokes nothing, deliberately. Grants and the ledger outlive the
        # decision to stop operating a venture, and collapsing the two would make
        # archiving a quiet way to pull authority with no revocation record.
        "/api/ventures/{slug}/lifecycle",
        # Pack drafting. A draft cannot provision - `packs.live` does not return one, so
        # Gate 1 cannot find it and nothing downstream can generate from it. Publishing
        # is the separate act that puts one in force.
        "/api/packs/draft",
        "/api/packs/{venture_id}/publish",
    }, f"the write surface changed: {sorted(writes)}"


def _statements_only(source) -> str:
    """The Python in a module with its comments and docstrings removed.

    Tokens are rejoined with a single space, which is enough for substring matching:
    `UPDATE agent` lexes as two tokens and rejoins as `update agent`, still containing
    the `update ` the caller looks for.
    """
    import tokenize

    standalone = {
        tokenize.ENCODING,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    code: list[str] = []
    previous = tokenize.ENCODING
    with open(source, encoding="utf-8") as handle:
        for token in tokenize.generate_tokens(handle.readline):
            if token.type == tokenize.COMMENT:
                continue
            # A string sitting where a statement would start is a docstring.
            if token.type == tokenize.STRING and previous in standalone:
                continue
            if token.type != tokenize.NL:
                previous = token.type
            code.append(token.string)
    return " ".join(code)


async def test_the_api_module_contains_no_raw_mutation():
    """The other half of the same rule: no `UPDATE`/`DELETE`/`INSERT` in the API.

    Every write must delegate to a guarded domain function. A route that issues its own
    statement is a second path to a table, and a second path is one that will not have
    the checks the first one has.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "broker" / "app.py"

    # Comments and docstrings are stripped before the scan. The first version lowercased
    # the whole file, so a docstring explaining that the historical-record store refuses
    # UPDATE and DELETE tripped the very guard that exists to stop raw statements - the
    # same trap the React 19 check fell into, where a rule that greps for a phrase flags
    # the paragraph explaining it.
    #
    # Stripping makes this stricter, not laxer: every real statement is still code, and a
    # guard that forces people to avoid a word in prose is one somebody eventually argues
    # down instead. `test_the_raw_mutation_guard_still_sees_a_real_statement` holds the
    # teeth, because a check loosened in response to a false positive is exactly the kind
    # that quietly stops checking.
    text = _statements_only(source).lower()
    for statement in ("update ", "delete from", "insert into"):
        assert statement not in text, (
            f"broker/app.py contains a raw {statement.strip()!r}. Every write must go "
            "through the guarded domain function that owns that rule."
        )


def test_the_raw_mutation_guard_still_sees_a_real_statement(tmp_path):
    """The guard above learned to skip prose. This proves it did not stop looking.

    A check that passes because it was narrowed is worse than no check, and this one was
    narrowed in response to a false positive - the circumstance under which a guard most
    often stops guarding. So: hand `_statements_only` a module whose only mutations are
    real code, and require all three to survive the strip; then hand it one where the
    same words appear only in a docstring and a comment, and require silence.
    """

    def scan(text: str, name: str) -> list[str]:
        source = tmp_path / name
        source.write_text(text, encoding="utf-8")
        body = _statements_only(source).lower()
        return sorted(s for s in ("update ", "delete from", "insert into") if s in body)

    real = (
        '"""A docstring that says nothing about statements."""\n'
        "def route(cur):\n"
        '    cur.execute("UPDATE agent SET tier = 2")\n'
        '    cur.execute("DELETE FROM grant WHERE grant_id = 1")\n'
        '    cur.execute("INSERT INTO audit_log (kind) VALUES (1)")\n'
    )
    assert scan(real, "real.py") == ["delete from", "insert into", "update "], (
        "the guard stopped catching raw statements when it learned to skip prose"
    )

    prose = (
        '"""This store refuses update and delete; rows insert into it once."""\n'
        "# A comment mentioning delete from and insert into for good measure.\n"
        "def route():\n"
        "    return knowledge.record_note()\n"
    )
    assert scan(prose, "prose.py") == [], "prose still trips the guard"


async def test_serve_does_not_let_uvicorn_replace_the_event_loop_policy():
    """A regression guard for a failure that does not look like one.

    uvicorn installs `WindowsProactorEventLoopPolicy` on Windows, and psycopg's async
    driver cannot use Proactor. The symptom is not a crash: the server starts, accepts
    connections, and every database-backed request hangs until the client times out,
    with the real cause in a startup log line nobody is reading.

    `python -m broker serve` passes `loop="none"` so uvicorn leaves the policy alone.
    Asserting the argument is present is cheap; discovering its absence in production
    is not.
    """
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "broker" / "__main__.py"
    text = source.read_text(encoding="utf-8")
    assert 'loop="none"' in text, (
        "broker serve must pass loop='none' to uvicorn, or psycopg cannot connect on "
        "Windows and every request hangs instead of failing"
    )
