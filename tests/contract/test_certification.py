"""Phase 2 acceptance — instructions, certification, and staleness.

Blueprint acceptance, verbatim: "an agent is certified for one module and becomes
assignable; an uncertified agent cannot be granted; rewriting the instructions flips
affected certs to `stale_instructions` and removes assignability."

The last clause is the one worth writing carefully. "Removes assignability" is only
true if the *next call* fails — a flag that changes in a table while calls keep
succeeding is not a control, and a test that only inspects the table would not notice.
"""

from __future__ import annotations

import uuid

import pytest

from broker import certification, instructions
from broker.certification import CertificationError
from broker.db import connection
from broker.errors import NotCertified
from broker.instructions import InstructionError
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

AUTHOR = uuid.uuid4()


def make_content(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "what_it_does": "Parses a bank statement PDF into structured transactions.",
        "what_it_does_not_do": "Does not judge creditworthiness or approve anything.",
        "inputs": {"document_url": "signed URL, expires in 15 minutes"},
        "correct_sequence": ["upload", "parse", "reconcile totals", "return"],
        "failure_signatures": {
            "hard_failure": "422 with a parse_error code",
            "slow_success": "200 after >30s; the parse is complete, do not retry",
            "silent_partial": "200 with transactions[] shorter than page_count implies",
        },
        "retry_vs_escalate": "Retry 5xx twice. Escalate any 422 - never re-submit.",
        "never_do": ["Never re-submit after a 200", "Never infer a missing balance"],
        "compliance_coupling": ["TILA", "FCRA"],
    }
    content.update(overrides)
    return content


# ------------------------------------------------------- instructions authoring

async def test_instructions_missing_a_section_are_refused(registered_forge):
    """C1 — Part 6.1: curriculum, not filing cabinet."""
    forge_id, module_id = registered_forge
    content = make_content()
    del content["failure_signatures"]

    async with connection() as conn:
        with pytest.raises(InstructionError) as exc:
            await instructions.author(
                conn, forge_id=forge_id, module_id=module_id,
                instruction_version="1.0.0", forge_api_version="2.1.0",
                content=content, authored_by=AUTHOR,
            )
    assert "failure_signatures" in str(exc.value)


async def test_an_empty_section_is_refused(registered_forge):
    """Present-but-empty is the failure mode a `?` key check misses."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        with pytest.raises(InstructionError) as exc:
            await instructions.author(
                conn, forge_id=forge_id, module_id=module_id,
                instruction_version="1.0.0", forge_api_version="2.1.0",
                content=make_content(never_do=[]), authored_by=AUTHOR,
            )
    assert "never_do" in str(exc.value)


async def test_content_hash_is_computed_not_supplied(registered_forge):
    """C2 — a supplied hash is a claim; a computed one is a fact."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        one = await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="1.0.0", forge_api_version="2.1.0",
            content=make_content(), authored_by=AUTHOR,
        )
        two = await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="1.0.1", forge_api_version="2.1.0",
            content=make_content(), authored_by=AUTHOR,
        )
        three = await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="1.1.0", forge_api_version="2.1.0",
            content=make_content(never_do=["Never do anything at all"]),
            authored_by=AUTHOR,
        )

    assert len(one.content_hash) == 64
    assert one.content_hash == two.content_hash, "identical content hashes identically"
    assert one.content_hash != three.content_hash, "changed content changes the hash"


async def test_patch_sensitivity_requires_a_rationale(registered_forge):
    """C3 — decertifying everyone at every patch release is never accidental."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        with pytest.raises(InstructionError) as exc:
            await instructions.author(
                conn, forge_id=forge_id, module_id=module_id,
                instruction_version="1.0.0", forge_api_version="2.1.0",
                content=make_content(), authored_by=AUTHOR,
                version_sensitivity="major.minor.patch",
            )
    assert "rationale" in str(exc.value)


async def test_only_one_instruction_set_is_live_at_a_time(registered_forge):
    """Two live sets make 'the current content_hash' ambiguous, and staleness is
    defined by comparison against it."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="1.0.0", forge_api_version="2.1.0",
            content=make_content(), authored_by=AUTHOR,
        )
        second = await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="2.0.0", forge_api_version="2.1.0",
            content=make_content(what_it_does="Rewritten."), authored_by=AUTHOR,
        )
        current = await instructions.live(conn, forge_id=forge_id, module_id=module_id)

    assert current is not None
    assert current.instruction_version == "2.0.0"
    assert current.content_hash == second.content_hash


async def test_diff_names_the_changed_sections(registered_forge):
    """C4 — the question an author asks is 'did the never-do list change'."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="1.0.0", forge_api_version="2.1.0",
            content=make_content(), authored_by=AUTHOR,
        )
        await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="2.0.0", forge_api_version="2.1.0",
            content=make_content(never_do=["Never re-submit after a 200"]),
            authored_by=AUTHOR,
        )
        result = await instructions.diff(
            conn, forge_id=forge_id, module_id=module_id,
            from_version="1.0.0", to_version="2.0.0",
        )

    assert result["changed"] == ["never_do"]
    assert result["added"] == []
    assert result["removed"] == []


# ---------------------------------------------------------- verdict → state map

@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ("PASS", "certified"),
        ("FAIL", "failed"),
        ("TIMEOUT", "in_training"),
        ("NOT_RUN", "never_certified"),
        ("IN_PROGRESS", "in_training"),
        ("REVOKED", "revoked"),
    ],
)
def test_verdict_maps_to_its_own_state(verdict, expected):
    assert certification.state_for_verdict(verdict) == expected


def test_timeout_never_resolves_to_pass():
    """C15 — Part 10.1, stated explicitly because it is the omission that matters.

    A run that did not finish proved nothing. Treating "we ran out of time" as a
    pass is how an uncertified agent reaches a Forge.
    """
    assert certification.state_for_verdict("TIMEOUT") != "certified"


def test_not_run_is_never_reported_as_failure():
    """C16 — nothing was attempted. Calling that a failure defames an agent and
    pollutes the metric that is supposed to show real failures."""
    assert certification.state_for_verdict("NOT_RUN") != "failed"


def test_an_unknown_verdict_refuses_to_guess():
    with pytest.raises(CertificationError):
        certification.state_for_verdict("PROBABLY_FINE")


# ------------------------------------------------------------ version sensitivity

@pytest.mark.parametrize(
    ("sensitivity", "current", "stale"),
    [
        ("major", "2.1.5", False),
        ("major", "2.9.0", False),
        ("major", "3.0.0", True),
        ("major.minor", "2.1.5", False),
        ("major.minor", "2.2.0", True),
        ("major.minor", "3.0.0", True),
        ("major.minor.patch", "2.1.5", True),
        ("major.minor.patch", "2.2.0", True),
        ("major.minor.patch", "2.1.0", False),
    ],
)
def test_forge_version_staleness_matrix(sensitivity, current, stale):
    """C5-C7 — precision matters: too loose certifies against behaviour that
    changed, too strict decertifies everyone at every patch."""
    assert certification.is_forge_version_stale("2.1.0", current, sensitivity) is stale


def test_a_forge_downgrade_is_also_stale():
    """The certification was earned against behaviour that is no longer current.
    Which direction the version moved is not the point."""
    assert certification.is_forge_version_stale("2.2.0", "2.1.0", "major.minor") is True


def test_certified_tier_caps_declared_tier():
    """C17 — Part 10.1: the Pack declares a ceiling; SimForge sets the actual."""
    assert certification.cap_tier("auto_execute", "propose") == "propose"
    assert certification.cap_tier("auto_execute", "auto_execute") == "auto_execute"
    assert certification.cap_tier("suggest", "auto_execute") == "suggest"
    with pytest.raises(CertificationError):
        certification.cap_tier("auto_execute", None)


async def test_a_certified_result_must_record_its_basis(registered_forge, seed_agent):
    """Without the hash and version it was earned against, staleness is
    uncomputable and the certification is permanent by accident."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        with pytest.raises(CertificationError):
            await certification.record_result(
                conn, unit="A", forge_id=forge_id, module_id=module_id,
                office_agent_id=seed_agent, verdict="PASS", rubric_version="1.0.0",
            )




# ------------------------------------------- no instruction is stale, not fresh

async def test_a_unit_a_cert_with_no_live_instruction_goes_stale(
    registered_forge, seed_agent, admin
):
    """The worst case was being treated as the best one.

    `recompute_staleness` guarded its comparison with `live_hash is not None`, so a
    Unit A cert whose module had no operating instruction at all was skipped and
    stayed `certified` - and `resolve_grant` dispatches on `state = 'certified'`.

    A certification bound to a hash that corresponds to no text cannot be said to
    match anything. Every CapitalForge certification was in that position: nine
    manuals existed as files, none authored into forge_operating_instruction, and
    the sweep ran and reported success.
    """
    forge_id, module_id = registered_forge
    async with connection() as conn:
        await certification.record_result(
            conn, unit="A", forge_id=forge_id, module_id=module_id,
            office_agent_id=seed_agent, verdict="PASS", rubric_version="1.0.0",
            certified_tier="auto_execute",
            # The fixture's forge is at 2.1.0. Passing anything else makes
            # stale_forge fire and the test measures the wrong rule.
            instruction_content_hash="c" * 64, forge_api_version="2.1.0",
        )

        with admin.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM forge_operating_instruction "
                "WHERE forge_id = %s AND module_id = %s AND superseded_at IS NULL",
                (forge_id, module_id),
            )
            assert cur.fetchone()[0] == 0, "this test needs a module with no instruction"

        changed = await certification.recompute_staleness(conn, forge_id=forge_id)

    assert len(changed) >= 1
    with admin.cursor() as cur:
        cur.execute(
            "SELECT state FROM certification WHERE unit = 'A' AND forge_id = %s "
            "AND module_id = %s",
            (forge_id, module_id),
        )
        assert cur.fetchone()[0] == certification.STALE_INSTRUCTIONS


async def test_unit_b_is_not_swept_stale_for_having_no_module(
    registered_forge, admin
):
    """Unit B carries module_id NULL by design and cannot be compared this way.

    Applying the Unit A rule to it would mark every domain certification in the
    system stale, including current ones - a different way of being wrong.
    """
    forge_id, _ = registered_forge
    async with connection() as conn:
        await certification.record_result(
            conn, unit="B", forge_id=forge_id, department="engineering",
            verdict="PASS", rubric_version="1.0.0", certified_tier="auto_execute",
            instruction_content_hash="d" * 64, forge_api_version="2.1.0",
        )
        await certification.recompute_staleness(conn, forge_id=forge_id)

    with admin.cursor() as cur:
        cur.execute(
            "SELECT state FROM certification WHERE unit = 'B' AND forge_id = %s",
            (forge_id,),
        )
        assert cur.fetchone()[0] == certification.CERTIFIED

# ------------------------------------------------- a bootstrap says it is one

async def test_a_bootstrap_certification_does_not_claim_simforge_ran(
    registered_forge, seed_agent, admin
):
    """`simforge_verdict` means SimForge said so. Nothing else may write it.

    Until 3 September 2026 a bootstrap had no way to record itself: `verdict` went
    straight into that column, so both Phase 0.8 rows claimed `PASS` against no
    scenario run. The column a reader trusts most was the one that lied.
    """
    forge_id, module_id = registered_forge
    async with connection() as conn:
        state = await certification.record_result(
            conn, unit="A", forge_id=forge_id, module_id=module_id,
            office_agent_id=seed_agent, verdict="PASS", rubric_version="bootstrap",
            certified_tier="auto_execute",
            instruction_content_hash="a" * 64, forge_api_version="1.0.0",
            attested_by="bootstrap",
            bootstrap_reason="proving the bridge before a scenario pack existed",
        )

    # The certification is real - it grants - and it does not claim to be earned.
    assert state.state == certification.CERTIFIED

    with admin.cursor() as cur:
        cur.execute(
            "SELECT simforge_verdict, scenario_pack_ref FROM certification "
            "WHERE unit = 'A' AND forge_id = %s AND module_id = %s",
            (forge_id, module_id),
        )
        verdict, pack_ref = cur.fetchone()

    assert verdict is None, "a bootstrap must not claim SimForge returned a verdict"
    assert pack_ref.startswith("NO SCENARIO RUN - ")
    assert "proving the bridge" in pack_ref


async def test_a_bootstrap_must_say_why_it_exists(registered_forge, seed_agent):
    """The reason is the only thing a later reader has to judge it by."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        with pytest.raises(CertificationError):
            await certification.record_result(
                conn, unit="A", forge_id=forge_id, module_id=module_id,
                office_agent_id=seed_agent, verdict="PASS", rubric_version="bootstrap",
                certified_tier="auto_execute",
                instruction_content_hash="a" * 64, forge_api_version="1.0.0",
                attested_by="bootstrap",
            )


async def test_a_real_verdict_still_records_one(registered_forge, seed_agent, admin):
    """The default path is unchanged: SimForge's verdict lands in its column."""
    forge_id, module_id = registered_forge
    async with connection() as conn:
        await certification.record_result(
            conn, unit="A", forge_id=forge_id, module_id=module_id,
            office_agent_id=seed_agent, verdict="PASS", rubric_version="1.0.0",
            certified_tier="auto_execute",
            instruction_content_hash="b" * 64, forge_api_version="1.0.0",
            scenario_pack_ref="pack-7",
        )

    with admin.cursor() as cur:
        cur.execute(
            "SELECT simforge_verdict, scenario_pack_ref FROM certification "
            "WHERE unit = 'A' AND forge_id = %s AND module_id = %s",
            (forge_id, module_id),
        )
        assert cur.fetchone() == ("PASS", "pack-7")

# ------------------------------------------------- assignability, end to end

async def test_both_units_certified_makes_the_agent_assignable(
    office, stub_forge, agent_ctx, certified_agent, declare_module
):
    """C12 — blueprint acceptance criterion 1."""
    _, forge_id, module_id = certified_agent
    declare_module(required=True)

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert result.status_code == 200
    assert stub_forge.call_count == 1


@pytest.mark.parametrize("drop_unit", ["A", "B"])
async def test_missing_either_unit_refuses_the_call(
    office, stub_forge, agent_ctx, certified_agent, declare_module, admin, drop_unit
):
    """C13 — department certification is necessary, never sufficient. And the
    reverse: operation competence alone is not enough either."""
    _, forge_id, _ = certified_agent
    declare_module(required=True)
    with admin.cursor() as cur:
        cur.execute("DELETE FROM certification WHERE unit = %s", (drop_unit,))
    admin.commit()

    with pytest.raises(NotCertified):
        await office.call(forge_id, "parse_bank_statement", {"n": 1}, agent_ctx=agent_ctx)
    assert stub_forge.call_count == 0


@pytest.mark.parametrize(
    "state", ["stale_instructions", "stale_forge", "in_training", "failed", "revoked"]
)
async def test_any_non_certified_state_refuses_the_call(
    office, stub_forge, agent_ctx, certified_agent, declare_module, admin, state
):
    """C14 — states are never collapsed, and only one of them is a pass."""
    _, forge_id, module_id = certified_agent
    declare_module(required=True)
    with admin.cursor() as cur:
        cur.execute("UPDATE certification SET state = %s WHERE unit = 'A'", (state,))
    admin.commit()

    with pytest.raises(NotCertified) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)

    assert exc.value.context["unit_a_state"] == state, "the state is named, not hidden"
    assert stub_forge.call_count == 0


async def test_rewriting_instructions_flips_certs_and_stops_the_next_call(
    office, stub_forge, agent_ctx, certified_agent, declare_module, admin
):
    """C8 + C9 — blueprint acceptance criterion 3, both halves.

    The table changing is not the claim. "Removes assignability" means the NEXT
    call fails, and a test that only inspected the table would not notice if it
    did not.
    """
    _agent_id, forge_id, module_id = certified_agent
    declare_module(required=True)

    first = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert first.status_code == 200

    async with connection() as conn:
        await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="2.0.0", forge_api_version="2.1.0",
            content=make_content(never_do=["Never re-submit", "Never guess a balance"]),
            authored_by=AUTHOR,
        )
        changed = await certification.recompute_staleness(
            conn, forge_id=forge_id, module_id=module_id
        )

    assert len(changed) == 1, "the Unit A cert must have gone stale"

    with admin.cursor() as cur:
        cur.execute("SELECT state FROM certification WHERE unit = 'A'")
        row = cur.fetchone()
    assert row is not None and row[0] == "stale_instructions"

    with pytest.raises(NotCertified) as exc:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)
    assert exc.value.context["unit_a_state"] == "stale_instructions"
    assert stub_forge.call_count == 1, "the Forge must not have been reached again"


async def test_forge_bump_below_sensitivity_does_not_decertify(
    office, agent_ctx, certified_agent, declare_module, admin
):
    """C10 — false decertification is expensive and erodes trust in the signal."""
    _, forge_id, module_id = certified_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_registry SET api_version = '2.1.9' WHERE forge_id = %s",
            (forge_id,),
        )
    admin.commit()

    async with connection() as conn:
        changed = await certification.recompute_staleness(conn, forge_id=forge_id)
    assert changed == [], "a patch bump under major.minor sensitivity is not stale"

    result = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert result.status_code == 200


async def test_forge_bump_at_sensitivity_flips_to_stale_forge(
    office, stub_forge, agent_ctx, certified_agent, declare_module, admin
):
    """C11 — and it is `stale_forge`, not `stale_instructions`. Two different
    causes needing two different fixes must not report as one."""
    _, forge_id, module_id = certified_agent
    declare_module(required=True)

    with admin.cursor() as cur:
        cur.execute(
            "UPDATE forge_registry SET api_version = '2.2.0' WHERE forge_id = %s",
            (forge_id,),
        )
    admin.commit()

    async with connection() as conn:
        changed = await certification.recompute_staleness(conn, forge_id=forge_id)
    assert len(changed) >= 1

    with pytest.raises(NotCertified) as exc:
        await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert exc.value.context["unit_a_state"] == "stale_forge"


async def test_a_failed_cert_does_not_become_stale(
    certified_agent, registered_forge, admin
):
    """A cert that was never fresh cannot go out of date. Collapsing the two erases
    the difference between 'was good, text changed' and 'was never good'."""
    _, forge_id, module_id = certified_agent
    with admin.cursor() as cur:
        cur.execute("UPDATE certification SET state = 'failed' WHERE unit = 'A'")
    admin.commit()

    async with connection() as conn:
        await instructions.author(
            conn, forge_id=forge_id, module_id=module_id,
            instruction_version="9.0.0", forge_api_version="2.1.0",
            content=make_content(what_it_does="Completely rewritten."),
            authored_by=AUTHOR,
        )
        changed = await certification.recompute_staleness(conn, forge_id=forge_id)

    assert changed == []
    with admin.cursor() as cur:
        cur.execute("SELECT state FROM certification WHERE unit = 'A'")
        row = cur.fetchone()
    assert row is not None and row[0] == "failed"


async def test_certified_tier_caps_the_call_live(
    office, stub_forge, agent_ctx, certified_agent, declare_module, admin
):
    """C17 + C18 — the grant says auto_execute; SimForge said propose. The lower
    wins, and it wins on the next call rather than at grant issuance."""
    _, forge_id, module_id = certified_agent
    declare_module(required=True)

    first = await office.call(forge_id, module_id, {"n": 1}, agent_ctx=agent_ctx)
    assert first.status_code == 200

    with admin.cursor() as cur:
        cur.execute("UPDATE certification SET certified_tier = 'propose' WHERE unit = 'A'")
    admin.commit()

    from broker.errors import RequiresApproval

    with pytest.raises(RequiresApproval) as exc:
        await office.call(forge_id, module_id, {"n": 2}, agent_ctx=agent_ctx)
    assert exc.value.context["effective_tier"] == "propose"
    assert stub_forge.call_count == 1
