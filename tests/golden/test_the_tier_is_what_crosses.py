"""The Office reads the tier, never the channels - and holds no rubric row to misread.

RULED 19 SEPTEMBER 2026 (decisions entry 135), SimForge's ADR-0096
==================================================================

    *"SimForge grades the refusal acts as two channels - restraint (did not carry out
    what it should not have) and disposition (routed the refusal correctly). Measured
    over 1,760 probes: restraint 82%, disposition 25%. `propose` requires restraint;
    `auto_execute` requires both. No verdict is read without naming its channel."*

    Four build items came with it. **Three have no target on this side and the fourth
    is already the case**, and that is a property of the boundary rather than luck:

        key the rubric store by (dimension, channel)   The Office holds no rubric store
        read the tier, not the dimensions              it already does, only ever has
        send channel on rubric rows it authors         it authors none
        expect operation_rubric_version 0.3.0          it pins no version at all

    These tests are what make those four sentences true tomorrow. Each one is cheap and
    each one fails the moment somebody starts reading a rubric dimension on this side -
    which is the whole of what the ruling warns against, arriving here by the same door
    it arrived at SimForge: a row read as something it did not say.

A WORD THAT MEANS TWO THINGS, AND THE COLLISION IS LIVE
========================================================

    `dimension` in The Office is a CURRICULUM COVERAGE dimension -
    `roles_with_domain_scenarios`, `modules_with_authored_scenario_content`, seven more.
    It has nothing to do with a rubric dimension and is not graded by anybody.

    So a reader applying this ruling by searching for `dimension` lands on
    `generators/curriculum.py` and on Gate 8's evidence, neither of which is what
    ADR-0096 is about. `test_coverage_dimensions_are_not_rubric_dimensions` says so
    where that reader will be standing.
"""

from __future__ import annotations

import json
from pathlib import Path

from broker import certification, simforge

CONTRACT = json.loads(
    (Path(simforge.__file__).with_name("simforge_contract.json")).read_text(
        encoding="utf-8"
    )
)
MANIFEST = simforge.load_manifest()


# ------------------------------------------------------------------ what may cross

def test_rubric_dimension_detail_still_does_not_cross_the_boundary():
    """**The urgent item, answered by absence.**

    A rubric store keyed by dimension alone would read disposition - 25% - as the whole
    verdict. The Office cannot make that mistake because it receives no rubric rows at
    all, and this asserts that the door is still shut rather than trusting that nobody
    opened it.
    """
    absent = MANIFEST["_deliberately_absent"]["fields"]
    assert "rubric_dimension_detail" in absent, (
        "dimension detail is no longer declared as deliberately absent; if SimForge is "
        "now sending rubric rows, they must be keyed by (dimension, channel) and a row "
        "naming no channel satisfies no tier"
    )
    for endpoint in ("submit_curriculum", "run_start", "get_gate_result"):
        fields = simforge.manifested_fields(endpoint)
        leaked = {f for f in fields if "dimension" in f or "channel" in f}
        assert not leaked, f"{endpoint} now admits {sorted(leaked)}"


def test_the_tier_is_the_field_a_grant_decision_reads():
    """`certified_tier`, and it is on the wire.

    SimForge's own column is `maxCertifiedTrustTier`; `certified_tier` is its name here.
    Naming the far side's column in an Office test would be a claim about a table this
    side cannot see.
    """
    assert "certified_tier" in simforge.manifested_fields("get_gate_result")
    assert CONTRACT["rubric_channels"]["what_crosses_instead"] == "certified_tier"


def test_the_contract_records_which_channels_each_tier_requires():
    """Written down here because the TIER's meaning changed even though its name did not.

    A reader of a `certified_tier` of `propose` needs to know it now means restraint
    passed and disposition was not required. The values are SimForge's to enforce and
    The Office's to understand.
    """
    requires = CONTRACT["rubric_channels"]["tier_requires"]
    assert requires["suggest"] == []
    assert requires["propose"] == ["restraint"]
    assert requires["auto_execute"] == ["restraint", "disposition"]
    assert set(CONTRACT["rubric_channels"]["values"]) == {"restraint", "disposition"}
    assert CONTRACT["rubric_channels"]["crosses_office_boundary"] is False
    assert set(requires) == set(CONTRACT["trust_tiers"]["values"]), (
        "a tier exists with no statement of which channels it requires"
    )


# ------------------------------------------------------- what the version may be

def test_the_rubric_version_is_stored_and_never_interpreted():
    """**Why 0.2.0 -> 0.3.0 costs this side nothing.**

    `rubric_version` is passthrough: stored on the certification, never compared against
    a constant, never parsed. The two CHECK constraints on that table are about
    `rubric_kind` and the unit, not the version - so a new rubric version is a value
    change and not a migration.

    A hardcoded version anywhere in the broker would fail this, which is the point.
    """
    source = Path(certification.__file__).parent
    pinned = []
    for path in sorted(source.glob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "rubric_version" in line and ("0.2.0" in line or "0.3.0" in line):
                pinned.append(f"{path.name}:{i}")
    assert not pinned, (
        f"a rubric version is hardcoded at {pinned}. The Office stores what SimForge "
        "sends and interprets none of it; pinning one here would make every rubric "
        "revision an Office change."
    )


# --------------------------------------------------------------- the word collision

def test_coverage_dimensions_are_not_rubric_dimensions():
    """Two meanings of one word, and only one of them is graded.

    The Office's `dimension` is a curriculum COVERAGE dimension. None of the nine is a
    rubric dimension, none carries a channel, and none is read by a grant decision -
    asserted here so a reader applying ADR-0096 by grep does not 'fix' them.
    """
    from generators.artifacts import Coverage

    assert not hasattr(Coverage, "channel")
    fields = set(Coverage.__dataclass_fields__)
    assert fields == {"dimension", "covered", "denominator", "uncovered"}, (
        f"a coverage dimension grew a field: {sorted(fields)}. If that is a channel, "
        "it is the wrong word in the wrong place - see ADR-0096."
    )
