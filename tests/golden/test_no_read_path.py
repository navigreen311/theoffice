"""THE NO-READ-PATH CHECK — SimForge's ship condition, verified by machine.

Master prompt Part 10.1:

    "Because Green Companies operates both sides of this boundary, self-attestation is
    the weakest possible enforcement for the one control whose entire purpose is
    preventing one side from seeing the other's content."

    "The Office's obligation is negative — there is no read path to build, only one
    never to build."

    "The test runs in the golden-test suite on every build. Adding a field without
    updating the manifest fails the build. Test failure blocks release of both
    operation certification and Gate 9.5."

This file is that test.

It needs no database and no SimForge instance, deliberately: a boundary check that can
only run when the far side is reachable is a check that stops running the moment
anything else is broken.

Three independent parts, because each alone is defeatable:

  1. MANIFEST COMPLETENESS — every response field is enumerated. Catches drift, and is
     what fails the build when someone adds a field. Defeated by an innocuous name.
  2. NO FIELD MAY CARRY SCENARIO CONTENT — names checked against forbidden fragments,
     values checked for prose shape. Catches an innocuous name. Defeated by a field
     that is genuinely new and genuinely benign-looking.
  3. NO PARAMETER COMBINATION WIDENS THE RESPONSE — a matrix sweep. Catches smuggling.
     Defeated by a default response change.

Together they are continuous machine verification of something two parties would
otherwise assert about themselves.
"""

from __future__ import annotations

import itertools
import json

import pytest

from broker.simforge import (
    FORBIDDEN_NAME_FRAGMENTS,
    MANIFEST_PATH,
    SMUGGLING_PARAMS,
    SimForgeError,
    assert_no_scenario_content,
    load_manifest,
    manifested_fields,
    parse_gate_result,
    validate_response,
)
from tests.golden.stub_simforge import (
    HONEST_GATE_RESULT,
    HONEST_SUBMIT,
    LEAKS,
    SCENARIO_PROSE,
    StubSimForge,
)

ENDPOINTS = ("submit_curriculum", "get_gate_result", "get_certification_status")


# --------------------------------------------------------- 1. manifest completeness

def test_manifest_file_exists_and_parses():
    """The manifest is the contract. A missing or malformed one is a release blocker,
    not a warning — without it there is nothing to check responses against."""
    assert MANIFEST_PATH.exists(), f"{MANIFEST_PATH} is missing"
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        json.load(fh)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_every_endpoint_is_enumerated(endpoint):
    manifest = load_manifest()
    assert endpoint in manifest, (
        f"{endpoint!r} is not in the manifest. Every endpoint must be enumerated "
        "before it may be called."
    )
    assert manifest[endpoint]["fields"], f"{endpoint} declares no fields"
    assert manifest[endpoint].get("purpose"), (
        f"{endpoint} has no declared purpose. A field list without a purpose cannot "
        "be reviewed for whether it should exist."
    )


def test_every_manifested_field_declares_a_purpose():
    """A field documented as 'string' is a field nobody reviewed."""
    manifest = load_manifest()
    for endpoint, spec in manifest.items():
        if endpoint.startswith("_"):
            continue
        for name, purpose in spec["fields"].items():
            assert isinstance(purpose, str) and len(purpose) > 10, (
                f"{endpoint}.{name} has no meaningful declared purpose"
            )


def test_honest_responses_satisfy_the_manifest():
    validate_response("get_gate_result", HONEST_GATE_RESULT)
    validate_response("submit_curriculum", HONEST_SUBMIT)


def test_an_undeclared_field_fails_the_check():
    """THE BUILD-FAILING CASE.

    Adding a field to a SimForge response without adding it to the manifest must
    fail, even when the field looks harmless. `attempt_number` is not scenario
    content — the point is that nobody reviewed whether it could be.
    """
    with pytest.raises(SimForgeError) as exc:
        validate_response("get_gate_result", LEAKS["undeclared_benign"])
    assert "manifest" in str(exc.value).lower()
    assert "attempt_number" in str(exc.value)


def test_an_unenumerated_endpoint_cannot_be_called():
    with pytest.raises(SimForgeError):
        manifested_fields("get_held_out_partition")


def test_deliberately_absent_fields_are_documented():
    """Absence should be a decision on the record, not an oversight.

    Listing what must never exist is what makes a later 'why not just add
    failed_scenario_ids' conversation have an answer.
    """
    manifest = load_manifest()
    absent = manifest["_deliberately_absent"]["fields"]
    for required in ("scenario_bodies", "failed_scenario_ids", "expected_outputs"):
        assert required in absent, f"{required} must be documented as forbidden"


# ------------------------------------------- 2. no field may carry scenario content

@pytest.mark.parametrize("leak", ["named_field", "innocuous_name", "nested"])
def test_scenario_content_is_caught_however_it_is_named(leak):
    """N5 — the check is not vacuous.

    Three real techniques: an honestly named field, an innocuous name, and burial
    inside a nested object. All three must be caught.
    """
    with pytest.raises(SimForgeError):
        assert_no_scenario_content("get_gate_result", LEAKS[leak])


@pytest.mark.parametrize("fragment", FORBIDDEN_NAME_FRAGMENTS)
def test_each_forbidden_fragment_is_actually_enforced(fragment):
    """Every fragment in the deny-list must reject something.

    A deny-list entry that matches nothing is a comment pretending to be a control.
    """
    with pytest.raises(SimForgeError):
        assert_no_scenario_content("get_gate_result", {f"x_{fragment}_y": "value"})


def test_no_manifested_field_name_matches_a_forbidden_fragment():
    """The manifest cannot legalise a leak by enumerating it."""
    manifest = load_manifest()
    for endpoint, spec in manifest.items():
        if endpoint.startswith("_"):
            continue
        for name in spec["fields"]:
            lowered = name.lower()
            for fragment in FORBIDDEN_NAME_FRAGMENTS:
                assert fragment not in lowered, (
                    f"{endpoint}.{name} matches forbidden fragment {fragment!r}. "
                    "A field cannot be made legitimate by adding it to the manifest."
                )


def test_prose_shaped_values_are_caught_behind_any_name():
    with pytest.raises(SimForgeError) as exc:
        assert_no_scenario_content("get_gate_result", {"meta": SCENARIO_PROSE})
    assert "prose" in str(exc.value)


def test_refs_and_hashes_are_not_mistaken_for_prose():
    """The tripwire must not fire on long strings that have no sentence structure.

    A check that fires on every hash gets disabled, and a disabled check protects
    nothing.
    """
    assert_no_scenario_content("get_gate_result", {
        "run_ref": "sf-" + "a1b2c3d4" * 40,
        "content_hash": "f" * 64,
        "rubric_version": "1.4.0-rc.1+build.20260822",
        "scenario_pack_ref": "s3://simforge-packs/" + "x" * 300,
    })


def test_short_human_labels_are_not_mistaken_for_prose():
    assert_no_scenario_content("get_gate_result", {
        "rejected_reason": "pack rejected: coverage denominator below threshold",
        "verdict": "FAIL",
    })


# ------------------------------------------------------- 3. parameter smuggling

@pytest.mark.parametrize("params", SMUGGLING_PARAMS)
def test_no_parameter_combination_widens_an_honest_response(params):
    """N4 — sweep the parameters a careless or determined caller would try."""
    stub = StubSimForge()
    body = stub.gate_result({k: str(v) for k, v in params.items()})
    validate_response("get_gate_result", body)


@pytest.mark.parametrize(
    "params",
    [dict(a) for a in itertools.combinations(
        [("include_scenarios", "true"), ("expand", "*"), ("fields", "*"),
         ("verbose", "true")], 2)],
)
def test_parameter_pairs_do_not_widen_the_response(params):
    """Single parameters can be individually ignored while a pair is honoured."""
    stub = StubSimForge()
    validate_response("get_gate_result", stub.gate_result(params))


def test_a_simforge_that_honours_smuggling_params_is_caught():
    """The sweep must fail against a SimForge that widens on request.

    Without this, the sweep could pass simply because the stub ignores everything —
    proving the stub compliant rather than the check effective.
    """
    stub = StubSimForge(honour_smuggling_params=True)
    caught = 0
    for params in SMUGGLING_PARAMS:
        body = stub.gate_result({k: str(v) for k, v in params.items()})
        try:
            validate_response("get_gate_result", body)
        except SimForgeError:
            caught += 1
    assert caught >= 4, (
        f"the parameter sweep caught only {caught} of the widening responses; "
        "the matrix is too narrow"
    )


# ------------------------------------------------------------------ integration

def test_parse_gate_result_validates_before_narrowing():
    """The dataclass is the only thing callers see, and validation runs first.

    Narrowing first would mean a leaky field never reached the check — the object
    would be clean while the response that produced it was not.
    """
    result = parse_gate_result(dict(HONEST_GATE_RESULT))
    assert result.verdict == "PASS"
    assert result.coverage_denominator == 24

    with pytest.raises(SimForgeError):
        parse_gate_result(LEAKS["named_field"])


def test_gate_result_reports_the_denominator():
    """'Report the denominator. No green check without a coverage count.'"""
    result = parse_gate_result(dict(HONEST_GATE_RESULT))
    assert result.coverage_denominator > 0
    assert result.scenario_count <= result.coverage_denominator
