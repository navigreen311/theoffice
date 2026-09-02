"""Every validator rule, in both directions.

Blueprint §5 test strategy: "Every FAIL rule has a must-fail fixture and a must-pass
fixture."

The must-fail half is the half that matters. A rule with only a must-pass fixture is a
rule nobody has watched fire, and a rule that has never fired might not — the failure
mode is a green Pack validation that checked nothing. `test_no_rule_lacks_a_must_fail_case`
fails the build if a rule is added without one.

Mutations are applied to a copy of the real Greenstone Pack rather than to a minimal
synthetic one, so each fixture is a Pack that is realistic in every respect except the
one thing being broken.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

import pytest

from generators import validator
from generators.pack import BusinessPack, load_pack
from generators.validator import Severity, Verdict, validate

PACK_PATH = Path(__file__).resolve().parents[2] / "packs" / "greenstone.yaml"


@pytest.fixture(scope="module")
def greenstone() -> BusinessPack:
    return load_pack(PACK_PATH)


def mutate(pack: BusinessPack, fn: Callable[[BusinessPack], None]) -> BusinessPack:
    """Deep-copy then break one thing. The original stays clean for the next test."""
    clone = copy.deepcopy(pack)
    fn(clone)
    return clone


# Each entry: rule id -> a mutation that must make that rule FAIL.
MUST_FAIL: dict[str, Callable[[BusinessPack], None]] = {
    "V1": lambda p: p.engagement_model.conversion_events.clear(),
    "V3": lambda p: setattr(p.market.compliance_surface[0], "runtime_flag", "  "),
    "V4": lambda p: (
        setattr(p.market.compliance_surface[0], "library_entry_ref", None),
        setattr(p.market.compliance_surface[0], "library_gap", False),
    ),
    "V5": lambda p: setattr(p.kpi_targets["day_30"][0], "measurement_source", ""),
    "V7": lambda p: setattr(p.forge_dependencies.forge_bindings[0], "api_version", "latest"),
    "V8": lambda p: (
        setattr(p.forge_dependencies.forge_bindings[0], "criticality", "hard"),
        setattr(p.forge_dependencies.forge_bindings[0], "module_gap", True),
    ),
    "V9": lambda p: (
        p.forge_dependencies.external_software[0].data_types_transmitted.append("phi_records"),
        setattr(p.forge_dependencies.external_software[0], "dpa_or_baa_status", "pending"),
    ),
    "V10": lambda p: p.positions_required[0].forge_modules_operated.clear(),
    "V12": lambda p: setattr(p.forge_operating_instructions[0], "content_hash", None),
    # 400 agent-days of propose-tier work against 10 hours of coverage.
    "V13": lambda p: (
        setattr(p.positions_required[0], "trust_tier_ceiling", "propose"),
        setattr(p.positions_required[0], "headcount", 400),
    ),
    "V14": lambda p: setattr(p.human_capacity[1], "backup_human", None),
    "V15": lambda p: (
        setattr(p.separation_of_duties, "gate_signoff_policy", "single_human_permitted"),
        setattr(p.separation_of_duties, "single_human_justification", None),
    ),
    "V16": lambda p: setattr(
        next(t for t in p.triggers if t.type == "agent_initiated"),
        "max_invocations_per_hour", None,
    ),
    "V17": lambda p: p.data_retention.clear(),
    "V18": lambda p: setattr(p.budget, "per_task_usd_ceiling", 0),
    "V19": lambda p: setattr(p.availability, "rpo_minutes", 0),
    "V20": lambda p: setattr(p.forge_dependencies.forge_bindings[0], "rate_limit_policy", None),
    "V21": lambda p: p.forge_dependencies.forge_bindings.__setitem__(
        slice(None),
        [b for b in p.forge_dependencies.forge_bindings if b.forge.lower() != "simforge"],
    ),
    "V22": lambda p: [s.compliance_flags_exercised.clear() for s in p.scenarios],
    "V23": lambda p: p.scenarios.__setitem__(slice(None), p.scenarios[:1]),
    # WARN rules
    "V25": lambda p: p.forge_dependencies.forge_bindings[0].modules_expected.clear(),
    "V26": lambda p: setattr(
        next(b for b in p.forge_dependencies.forge_bindings if b.criticality == "soft"),
        "fallback_behavior", None,
    ),
    "V27": lambda p: setattr(
        next(b for b in p.forge_dependencies.forge_bindings if b.criticality == "soft"),
        "module_gap", True,
    ),
}

# Document rules only. V2/V6/V11 need the world; V24 is Gate 4.5.
DOCUMENT_RULES = sorted(
    set(validator.all_rule_ids()) - validator.NEEDS_WORLD - validator.GATE_45_RULES,
    key=lambda r: int(r[1:]),
)


def test_no_rule_lacks_a_must_fail_case():
    """The meta-test. Adding a rule without a must-fail fixture fails the build.

    Without this, a new rule can ship with only its happy path exercised — and a
    rule that has never been watched fire is a rule that might not.
    """
    missing = [r for r in DOCUMENT_RULES if r not in MUST_FAIL]
    assert not missing, (
        f"rule(s) with no must-fail fixture: {missing}. Every rule must be watched "
        "fire at least once."
    )


def test_every_rule_from_v1_is_implemented_with_no_gaps():
    """Numbered contiguously, so a rule cannot be quietly dropped.

    V28 was added when Part 6.3 was built: V4 checks that a Pack *names* a compliance
    library entry, which is self-attestation, and V28 checks that the name resolves.

    V31 and V32 arrived the same way, from the same defect one layer down. V6 resolves
    a Pack's modules against `forge_module_registry`, which is rows a human wrote - two
    declarations compared to each other. V32 resolves them against what the Forge
    actually dispatches, and V31 asks whether the tier granted over a module is one it
    survives.
    """
    ids = validator.all_rule_ids()
    assert ids == [f"V{i}" for i in range(1, len(ids) + 1)], f"got {ids}"
    assert len(ids) == 32


@pytest.mark.parametrize("rule_id", DOCUMENT_RULES)
async def test_must_pass(greenstone, rule_id):
    """The real Greenstone Pack satisfies every document rule."""
    report = await validate(greenstone)
    result = report.get(rule_id)
    assert result.verdict is Verdict.PASS, f"{rule_id}: {result.message}"


@pytest.mark.parametrize("rule_id", DOCUMENT_RULES)
async def test_must_fail(greenstone, rule_id):
    """Break exactly the thing the rule guards; the rule must notice."""
    broken = mutate(greenstone, MUST_FAIL[rule_id])
    report = await validate(broken)
    result = report.get(rule_id)

    expected = (
        Verdict.FAIL if validator.rule_severity(rule_id) is Severity.FAIL else Verdict.WARN
    )
    assert result.verdict is expected, (
        f"{rule_id} did not fire when its condition was violated. "
        f"Got {result.verdict.value}: {result.message}"
    )
    assert result.message.strip(), f"{rule_id} fired with no explanation"


async def test_a_failing_rule_blocks_the_pack(greenstone):
    broken = mutate(greenstone, MUST_FAIL["V7"])
    report = await validate(broken)
    assert not report.passed
    assert any(r.rule_id == "V7" for r in report.failures)


async def test_a_warning_does_not_block_the_pack(greenstone):
    """WARN is reported and surfaced at Gate 4; it does not stop provisioning."""
    broken = mutate(greenstone, MUST_FAIL["V26"])
    report = await validate(broken, conn=None)
    warn = report.get("V26")
    assert warn.verdict is Verdict.WARN
    assert not warn.blocks
    assert not any(r.rule_id == "V26" for r in report.failures)


async def test_world_rules_report_not_run_without_a_connection(greenstone):
    """NOT_RUN is not a pass.

    Part 10.1 says NOT_RUN must never be reported as a failure. The converse matters
    just as much: a Pack whose bridge check could not run has not been validated,
    and calling it passed defeats the one rule that stops provisioning against a
    Forge nobody can reach.
    """
    report = await validate(greenstone, conn=None)
    for rule_id in sorted(validator.NEEDS_WORLD):
        result = report.get(rule_id)
        assert result.verdict is Verdict.NOT_RUN
        assert result.verdict is not Verdict.PASS
    assert not report.passed, "a Pack with unrun rules has not passed validation"


async def test_report_is_deterministic(greenstone):
    """Same Pack in, same report out — including order.

    Generators are specified as deterministic; a validator whose report order
    depended on import order would make every snapshot diff noise.
    """
    a = await validate(greenstone)
    b = await validate(greenstone)
    assert [(r.rule_id, r.verdict, r.message) for r in a.results] == [
        (r.rule_id, r.verdict, r.message) for r in b.results
    ]
    assert [r.rule_id for r in a.results] == [f"V{i}" for i in range(1, 33)]


async def test_render_names_the_offending_value(greenstone):
    """A validator that answers False sends an author looking. This one tells them."""
    broken = mutate(greenstone, MUST_FAIL["V13"])
    report = await validate(broken)
    text = report.render()
    assert "V13 FAIL" in text
    assert "review-minutes" in text
    assert "V7 FAIL" not in text, "passing rules must not appear in the summary"


async def test_v24_is_deferred_to_gate_4_5(greenstone):
    """Appointment output does not exist at Gate 2, so V24 cannot be evaluated here.
    Reported as NOT_RUN rather than silently passed."""
    report = await validate(greenstone)
    v24 = report.get("V24")
    assert v24.verdict is Verdict.NOT_RUN
    assert "4.5" in v24.message


def test_needs_world_matches_the_world_rules():
    """Two lists of the same thing, kept in step by a test rather than by memory.

    `NEEDS_WORLD` tells the fixture meta-test which rules cannot be exercised against a
    document alone; `_WORLD_RULES` is what the runner dispatches. They drifted the first
    time a world rule was added - V29 and V30 were registered and not declared - and the
    symptom was this file demanding document fixtures for rules that need the Village.
    """
    assert set(validator._WORLD_RULES) == validator.NEEDS_WORLD, (
        "NEEDS_WORLD and _WORLD_RULES disagree: "
        f"{validator.NEEDS_WORLD ^ set(validator._WORLD_RULES)}"
    )
