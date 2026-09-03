"""The divergence detector.

Three contract mismatches between The Office and SimForge were found by reading:

  1. SimForge emits `provisional`; the CHECK constraint knew seven states.
  2. The Office maps TIMEOUT to `in_training`; SimForge emits no TIMEOUT, so a hung
     run resolved to nothing at all.
  3. `not_applicable` is a real SimForge value that nobody had declared anywhere.

Each looked like success while being wrong, which is why reading found them and CI did
not. This file is CI finding the fourth.

WHAT IT CHECKS AND WHAT IT CANNOT
=================================

    It compares `broker/simforge_contract.json` against The Office's own constants,
    its migration, and its response manifest. Four representations of one vocabulary,
    all in this repository, all asserted equal.

    It cannot reach into SimForge — the two are separate applications and the seal in
    `tests/contract/test_village_seal.py` exists because cross-imports are how that
    separation dies. SimForge holds a copy of the same contract file and asserts its own
    enums against it, so a change on either side fails on that side.

    The `contract_version` is what ties the copies together. Bumping it here without
    bumping it there means the two copies disagree, and the SimForge-side test says so.

    Deliberately no database, and deliberately NOT in `tests/contract/`: that package's
    conftest opens a session-scoped admin connection for every test in it, so a
    vocabulary check placed there would be skipped in exactly the environment where
    nobody set OFFICE_ADMIN_DSN. A drift detector that only runs where Postgres is up
    is a drift detector that does not run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from broker import certification, simforge

CONTRACT_PATH = Path(simforge.__file__).with_name("simforge_contract.json")
MIGRATION_PATH = (
    Path(simforge.__file__).parent.parent
    / "db"
    / "versions"
    / "0029_provisional_is_a_certification_state.py"
)


@pytest.fixture(scope="module")
def contract() -> dict:
    with CONTRACT_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def declared_states(contract: dict) -> set[str]:
    return {k for k in contract["certification_states"] if not k.startswith("_")}


# --------------------------------------------------------------------- the states

def test_the_contract_and_the_python_constants_name_the_same_states(
    contract: dict, declared_states: set[str]
) -> None:
    assert set(certification.ALL_STATES) == declared_states, (
        "broker/certification.ALL_STATES and simforge_contract.json disagree about "
        "which certification states exist. Whichever is right, they cannot both be."
    )


def test_the_check_constraint_admits_exactly_the_declared_states(
    declared_states: set[str],
) -> None:
    """The constraint is the control. This asserts the control matches the contract.

    Parsed out of the migration source rather than read from a live database, so it
    runs everywhere. A migration that has not been applied is a separate problem with
    a separate signal.
    """
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    upgrade = source.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]

    block = re.search(
        r"ADD CONSTRAINT certification_state_check\s*\n?\s*CHECK \(state IN \((.*?)\)\)",
        upgrade,
        re.S,
    )
    assert block, "could not find the state CHECK constraint in migration 0029"

    in_constraint = set(re.findall(r"'([a-z_]+)'", block.group(1)))
    assert in_constraint == declared_states, (
        "migration 0029's CHECK constraint and simforge_contract.json disagree. A state "
        "SimForge can emit that the constraint rejects is an insert that fails at "
        "runtime, in production, on a certification."
    )


def test_provisional_is_present_and_is_not_assignable(contract: dict) -> None:
    """The decision recorded in migration 0029, asserted rather than described.

    A state The Office can store but cannot reason about is worse than one it rejects,
    so `provisional` having a defined assignability is the whole point of storing it.
    """
    assert "provisional" in certification.ALL_STATES
    assert certification.PROVISIONAL == "provisional"

    assert contract["certification_states"]["provisional"]["assignable"] is False
    assert certification.PROVISIONAL not in certification.ASSIGNABLE_STATES


def test_certified_is_the_only_assignable_state(contract: dict) -> None:
    """`resolve_grant` compares against 'certified'. This is that fact, assertable.

    If a future state is ever marked assignable in the contract, this fails — and it
    should, because the query in grants.py would need to change with it and would not
    have.
    """
    assignable_in_contract = {
        name
        for name, spec in contract["certification_states"].items()
        if not name.startswith("_") and spec["assignable"]
    }
    assert assignable_in_contract == {"certified"}
    assert frozenset({"certified"}) == certification.ASSIGNABLE_STATES


# ------------------------------------------------------------------- the verdicts

def test_every_declared_verdict_maps_to_a_declared_state(
    contract: dict, declared_states: set[str]
) -> None:
    for verdict, state in contract["gate_verdicts"].items():
        if verdict.startswith("_"):
            continue
        assert state in declared_states, (
            f"verdict {verdict!r} resolves to state {state!r}, which is not a "
            "declared certification state"
        )


def test_the_verdict_table_matches_the_contract(contract: dict) -> None:
    declared = {k: v for k, v in contract["gate_verdicts"].items() if not k.startswith("_")}
    assert declared == certification.VERDICT_TO_STATE, (
        "broker/certification.VERDICT_TO_STATE and simforge_contract.json disagree "
        "about verdict handling. This is mismatch #2 recurring."
    )


def test_the_response_manifest_declares_the_same_verdicts(contract: dict) -> None:
    """The manifest documents the verdict vocabulary in prose. It must agree.

    The manifest is the thing `test_no_read_path.py` fails the build on, so a verdict
    that is handled but undocumented there is a verdict nobody reviewed.
    """
    manifest = simforge.load_manifest()
    described = manifest["get_gate_result"]["fields"]["verdict"]

    for verdict in contract["gate_verdicts"]:
        if verdict.startswith("_"):
            continue
        assert verdict in described, (
            f"verdict {verdict!r} is in the contract and in VERDICT_TO_STATE but is "
            f"not named in the response manifest's description: {described!r}"
        )


def test_state_for_verdict_refuses_an_unknown_verdict() -> None:
    """The behaviour that made mismatch #3 survivable, kept.

    An unrecognised verdict raises rather than defaulting. `not_applicable` is a
    SimForge-internal dimension value that does not cross this boundary; if it ever
    arrives here, this is what must happen to it.
    """
    with pytest.raises(certification.CertificationError) as exc:
        certification.state_for_verdict("not_applicable")
    assert "refusing to guess" in str(exc.value)

    for verdict, expected in certification.VERDICT_TO_STATE.items():
        assert certification.state_for_verdict(verdict) == expected


# -------------------------------------------------------------------- the timeout

def test_timeout_never_resolves_to_certified(contract: dict) -> None:
    """Part 10.1's rule, as an assertion rather than a comment."""
    assert certification.VERDICT_TO_STATE["TIMEOUT"] != certification.CERTIFIED
    assert contract["timeout"]["never_resolves_to"] == "certified"
    assert contract["timeout"]["resolves_to"] == certification.VERDICT_TO_STATE["TIMEOUT"]


def test_an_unanswered_run_resolves_to_timeout_and_measures_nothing() -> None:
    """The gap that made the TIMEOUT mapping unreachable, closed.

    A hung run produces no callback. `timeout_gate_result` is what The Office resolves
    that silence to, and it must not invent a measurement: a score of 0.0 would be a
    claim about the agent rather than about the run.
    """
    submission = {
        "submission_id": "11111111-1111-1111-1111-111111111111",
        "simforge_run_ref": None,
        "module_id": "parse_bank_statement",
    }
    result = simforge.timeout_gate_result(submission, rubric_version="1.0.0")

    assert result.verdict == "TIMEOUT"
    assert certification.state_for_verdict(result.verdict) == certification.IN_TRAINING
    assert result.score is None, "a run that did not finish measured nothing"
    assert result.threshold is None
    assert result.certified_tier is None
    assert result.unit == "A"
    assert "unanswered" in result.run_ref


def test_a_department_submission_times_out_as_unit_b() -> None:
    submission = {
        "submission_id": "22222222-2222-2222-2222-222222222222",
        "simforge_run_ref": "run-77",
        "module_id": None,
        "department": "Finance",
    }
    result = simforge.timeout_gate_result(submission, rubric_version="1.0.0")

    assert result.unit == "B"
    assert result.rubric_kind == "domain"
    assert result.run_ref == "run-77"


def test_the_office_holds_the_deadline_itself(contract: dict) -> None:
    """The mechanism, asserted: waiting is the Office's job, not SimForge's.

    A process that has died cannot report that it has died, so a deadline held only by
    SimForge would be absent in exactly the case it exists for.
    """
    assert contract["timeout"]["office_default_deadline_hours"] == (
        simforge.DEFAULT_RUN_DEADLINE_HOURS
    )
    assert "cannot report that it died" in contract["timeout"]["detected_by_office_when"]


# ------------------------------------------------------------ the dimension values

def test_rubric_result_verdicts_are_declared_as_not_crossing_the_boundary(
    contract: dict,
) -> None:
    """`not_applicable` is real, and it is SimForge's, and it stops there.

    The manifest carries no rubric results at all — deliberately, because a rich enough
    explanation of a failure reconstructs the scenario that produced it. Declaring that
    here makes the absence intentional and reviewable rather than an oversight somebody
    later "fixes" by adding the field.
    """
    rubric = contract["rubric_result_verdicts"]
    assert rubric["crosses_office_boundary"] is False
    assert "not_applicable" in rubric["values"]

    manifest = simforge.load_manifest()
    for endpoint, spec in manifest.items():
        if endpoint.startswith("_"):
            continue
        for field in spec["fields"]:
            assert "rubric_result" not in field, (
                f"{endpoint}.{field} would carry per-dimension rubric results across "
                "the boundary. The contract declares they do not cross it."
            )


def test_trust_tiers_agree_with_the_capping_order(contract: dict) -> None:
    assert contract["trust_tiers"]["values"] == sorted(
        certification.TIER_RANK, key=lambda t: certification.TIER_RANK[t]
    )
