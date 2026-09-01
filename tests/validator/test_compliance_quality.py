"""A Compliance Library entry that constrains nothing must be refused.

The instruction-set version of this defect is already on the record: a live curriculum
passed every check with `"what_it_does": "Documented."`, and 234 certifications were
bound to a hash of that word. `author_compliance_entry` has the same shape of check —
present and non-blank — so the same defect is available one layer over.

These tests are the shapes that would get past a non-blank check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from broker.compliance_quality import (
    REQUIRED_BY_TAG,
    assess,
    assess_citation_form,
    assess_claim,
    assess_field,
    assess_provenance,
)

LIBRARY_DIR = Path(__file__).resolve().parents[2] / "packs" / "compliance-library"


def entry(**overrides) -> dict:
    base = {
        "entry_ref": "compliance/test-v1",
        "framework": "GLBA",
        "jurisdiction": ["FEDERAL"],
        "applicability_rule": (
            "When the client connects a financial account through Plaid, and on every "
            "subsequent call that reads from that connection."
        ),
        "agent_behavior_implication": (
            "The agent must obtain a written authorization naming the institution and "
            "must record it before calling statement_pull for that connection."
        ),
        "escalation_trigger": (
            "When the client declines authorization, or when a stored authorization is "
            "revoked mid-engagement."
        ),
        "citation": "15 U.S.C. §§ 6801-6809; 16 C.F.R. Part 313",
    }
    base.update(overrides)
    return base


def test_a_real_entry_is_complete() -> None:
    result = assess(entry())
    assert result["state"] == "complete"
    assert result["teaches_nothing"] is False
    assert result["problems"] == []


# ---------------------------------------------------------------- the stub shapes

@pytest.mark.parametrize(
    "value",
    ["Documented.", "TODO", "N/A", "Applies.", "Comply.", "Escalate.", "-", "as required"],
)
def test_a_placeholder_implication_is_a_stub(value: str) -> None:
    """Every one of these passes a present-and-non-blank check."""
    result = assess(entry(agent_behavior_implication=value))
    assert result["state"] == "stub"
    assert result["teaches_nothing"] is True


def test_the_whole_documented_entry_is_caught() -> None:
    """The exact shape the instruction-set defect took, transposed."""
    result = assess(
        entry(
            applicability_rule="Documented.",
            agent_behavior_implication="Documented.",
            escalation_trigger="Documented.",
            citation="Documented.",
        )
    )
    assert result["teaches_nothing"] is True
    assert len(result["problems"]) == 4


# ----------------------------------------------- the three fields are not the same

def test_an_implication_that_restates_the_law_is_thin() -> None:
    """The most common way this field goes wrong, and the hardest to see.

    It is real prose, it is long enough, it is about the right framework — and an
    agent reading it does nothing differently.
    """
    result = assess(
        entry(
            agent_behavior_implication=(
                "Gramm-Leach-Bliley Act obligations apply to the handling of client "
                "financial account data obtained through this connection."
            )
        )
    )
    assert result["state"] == "thin"
    field = next(f for f in result["fields"] if f["field"] == "agent_behavior_implication")
    assert "WHAT THE AGENT DOES DIFFERENTLY" in field["reason"]


def test_an_applicability_rule_naming_no_condition_is_thin() -> None:
    result = assess(
        entry(applicability_rule="This framework governs the handling of consumer financial data.")
    )
    assert result["state"] == "thin"
    field = next(f for f in result["fields"] if f["field"] == "applicability_rule")
    assert "Names no condition" in field["reason"]


def test_an_escalation_trigger_naming_no_condition_is_thin() -> None:
    result = assess(
        entry(escalation_trigger="The agent should escalate to a human where appropriate.")
    )
    assert result["state"] == "thin"


def test_a_citation_naming_a_topic_rather_than_a_source_is_thin() -> None:
    """An agent asked 'on what authority' cannot answer from a framework name."""
    result = assess(entry(citation="Gramm-Leach-Bliley Act"))
    assert result["state"] == "thin"
    field = next(f for f in result["fields"] if f["field"] == "citation")
    assert "names a topic" in field["reason"]


@pytest.mark.parametrize(
    "citation",
    [
        "15 U.S.C. §§ 6801-6809",
        "16 C.F.R. Part 313",
        "TILA; Regulation Z 12 C.F.R. § 1026.16",
        "https://www.ecfr.gov/current/title-16/part-313",
    ],
)
def test_a_citation_naming_a_source_passes(citation: str) -> None:
    assert assess_field("citation", citation)["state"] == "complete"


# ------------------------------------------------------------------- jurisdiction

def test_a_missing_jurisdiction_is_missing() -> None:
    result = assess(entry(jurisdiction=[]))
    assert result["state"] == "missing"


def test_a_placeholder_jurisdiction_is_a_stub() -> None:
    result = assess(entry(jurisdiction=["TBD"]))
    assert result["state"] == "stub"


# --------------------------------------------------- the shipped template itself

def test_the_worked_example_in_the_template_is_complete() -> None:
    """The example is the shape everything else copies. If it is thin, so is the rest."""
    path = LIBRARY_DIR / "burkham-wickmont.yaml"
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    glba = next(e for e in doc["entries"] if e["entry_ref"].startswith("compliance/glba"))
    result = assess(glba)
    assert result["state"] == "complete", result["summary"]


def test_every_templated_entry_carries_the_pack_runtime_flag() -> None:
    """The flag is the join between the Pack and the entry.

    A typo means the Pack declares a framework that resolves to nothing, and neither
    side reports an error — the Pack validates, the entry loads, and the agent gets a
    flag with no entry behind it.
    """
    path = LIBRARY_DIR / "burkham-wickmont.yaml"
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    pack_path = LIBRARY_DIR.parent / "burkham-wickmont.draft.yaml"
    with pack_path.open(encoding="utf-8") as fh:
        pack = yaml.safe_load(fh)

    declared = {c["runtime_flag"] for c in pack["market"]["compliance_surface"]}

    for e in doc["entries"]:
        flag = e.get("runtime_flag")
        assert flag, f"{e['entry_ref']} has no runtime_flag"
        assert flag in declared, (
            f"{e['entry_ref']} names runtime_flag {flag!r}, which no framework in the "
            f"Pack declares. Known flags: {sorted(declared)}"
        )


# ------------------------------------------------- depends_on: what must exist first

def _dep_entry(**overrides) -> dict:
    """A complete, approved entry with one blocking dependency."""
    e = entry(
        entry_ref="compliance/dep-test-v1",
        status="approved",
        depends_on=[
            {
                "kind": "state_activation",
                "description": "Counsel certification and populated disclosures, per state.",
                "required_for": ["CA", "NY"],
                "satisfied_for": [],
                "blocking": True,
            }
        ],
    )
    e.update(overrides)
    return e


def _unmet(e: dict) -> list[str]:
    from scripts.check_compliance_library import _unmet_dependencies

    return _unmet_dependencies(e)


def test_an_unmet_blocking_dependency_is_reported() -> None:
    """The `status: draft` guard one layer out.

    A draft entry is honest about not being ready. An approved entry that defers to a
    per-state variant which does not exist reads as a live control and is one that
    cannot fire.
    """
    unmet = _unmet(_dep_entry())
    assert len(unmet) == 1
    assert "CA, NY" in unmet[0]


def test_a_satisfied_dependency_is_not_reported() -> None:
    e = _dep_entry()
    e["depends_on"][0]["satisfied_for"] = ["CA", "NY"]
    assert _unmet(e) == []


def test_a_partially_satisfied_dependency_names_only_what_is_missing() -> None:
    e = _dep_entry()
    e["depends_on"][0]["satisfied_for"] = ["CA"]
    unmet = _unmet(e)
    assert len(unmet) == 1
    assert "NY" in unmet[0] and "CA" not in unmet[0].split("unmet for")[1]


def test_a_non_blocking_dependency_does_not_block() -> None:
    """Not every dependency stops an entry. Some are worth recording and not gating."""
    e = _dep_entry()
    e["depends_on"][0]["blocking"] = False
    assert _unmet(e) == []


def test_a_dependency_naming_nothing_is_unmet_not_satisfied() -> None:
    """An empty `required_for` would otherwise read as satisfied, which is the whole
    failure mode this file exists to prevent: a check that passes on absence."""
    e = _dep_entry()
    e["depends_on"][0]["required_for"] = []
    unmet = _unmet(e)
    assert len(unmet) == 1
    assert "empty" in unmet[0]


def test_an_entry_with_no_dependencies_is_unaffected() -> None:
    assert _unmet(entry()) == []


def test_the_shipped_estimate_entry_declares_its_state_dependency() -> None:
    """The amendment, asserted rather than described.

    All seven seeded state modules are drafts and three of the states this entry binds
    have no module at all, so `satisfied_for` must be empty and both dependencies must
    block.
    """
    path = LIBRARY_DIR / "burkham-wickmont.yaml"
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)

    e = next(x for x in doc["entries"] if x["entry_ref"] == "compliance/estimate-not-offer-v1")
    kinds = {d["kind"] for d in e["depends_on"]}
    assert kinds == {"state_activation", "state_module_exists"}

    for dep in e["depends_on"]:
        assert dep["blocking"] is True
        assert dep["satisfied_for"] == []

    module_exists = next(d for d in e["depends_on"] if d["kind"] == "state_module_exists")
    assert set(module_exists["required_for"]) == {"VA", "GA", "CT"}


def test_a_bare_string_dependency_is_unmet_and_blocking() -> None:
    """The natural form for "this capability does not exist yet".

    The structured mapping suits per-jurisdiction dependencies. For a capability there
    is one thing and it either exists or it does not, and forcing `required_for` /
    `satisfied_for` on that is ceremony — which is how a field stops being written.
    """
    e = entry(status="approved", depends_on=["VoiceForge participant detection"])
    unmet = _unmet(e)
    assert unmet == ["capability: VoiceForge participant detection"]


def test_mixed_string_and_mapping_dependencies_both_report() -> None:
    e = entry(
        status="approved",
        depends_on=[
            "Marketing Claim Library scripted disclosures",
            {
                "kind": "state_activation",
                "required_for": ["CA"],
                "satisfied_for": [],
                "blocking": True,
            },
        ],
    )
    unmet = _unmet(e)
    assert len(unmet) == 2
    assert any(u.startswith("capability:") for u in unmet)
    assert any(u.startswith("state_activation:") for u in unmet)


def test_an_empty_string_dependency_is_ignored_rather_than_reported() -> None:
    """A blank list item is a YAML accident, not a declared dependency."""
    assert _unmet(entry(status="approved", depends_on=["", "   "])) == []


# ---------------------------------------------------------------------------
# Per-claim provenance
#
# The field mirrors the Recommendation Engine's `issuer_rule` versus
# `unresearched_default`, and mirrors the part that matters: there, an
# unresearched default without a `rationale` throws in `profile.ts` rather than
# rendering. A tag whose supporting field is optional is a tag that gets applied
# to everything, and a library where every claim says `sourced` tells a reader
# nothing.
# ---------------------------------------------------------------------------


def test_sourced_claim_without_a_source_is_refused():
    result = assess_claim({"claim": "FCRA permissible purpose", "tag": "sourced"})
    assert result["ok"] is False
    assert "`source`" in result["reason"]


def test_reconstructed_claim_without_a_basis_is_refused():
    result = assess_claim({"claim": "route to a human", "tag": "reconstructed"})
    assert result["ok"] is False
    assert "`basis`" in result["reason"]


def test_proposed_claim_without_a_reviewer_is_refused():
    result = assess_claim({"claim": "disclose the incentive", "tag": "proposed"})
    assert result["ok"] is False
    assert "`review_by`" in result["reason"]


def test_placeholder_support_is_the_same_as_no_support():
    """`source: TBD` is the 'Documented.' stub at claim scale."""
    result = assess_claim(
        {"claim": "FCRA permissible purpose", "tag": "sourced", "source": "TBD"}
    )
    assert result["ok"] is False


def test_an_unknown_tag_is_refused_rather_than_counted():
    result = assess_claim(
        {"claim": "x", "tag": "inferred", "source": "somewhere"}
    )
    assert result["ok"] is False
    assert "inferred" in result["reason"]


def test_a_well_formed_claim_of_each_tag_passes():
    for tag, field in REQUIRED_BY_TAG.items():
        result = assess_claim({"claim": "a claim", "tag": tag, field: "real support"})
        assert result["ok"] is True, tag
        assert result["tag"] == tag


def test_unmarked_is_distinct_from_fully_sourced():
    """Both have zero problems. Only one has been looked at."""
    unmarked = assess_provenance({"entry_ref": "x"})
    assert unmarked["unmarked"] is True
    assert unmarked["problems"] == []

    marked = assess_provenance(
        {
            "entry_ref": "x",
            "claim_provenance": [
                {"claim": "a", "tag": "sourced", "source": "15 U.S.C. 1681b"}
            ],
        }
    )
    assert marked["unmarked"] is False
    assert marked["problems"] == []
    assert marked["counts"]["sourced"] == 1


def test_counts_exclude_malformed_claims():
    """A claim that fails is not silently counted under its own tag."""
    prov = assess_provenance(
        {
            "claim_provenance": [
                {"claim": "a", "tag": "sourced", "source": "15 U.S.C. 1681b"},
                {"claim": "b", "tag": "sourced"},
                "not a mapping",
            ]
        }
    )
    assert prov["total"] == 3
    assert prov["counts"]["sourced"] == 1
    assert len(prov["problems"]) == 2


# ---------------------------------------------------------------------------
# Citation form
# ---------------------------------------------------------------------------


def test_a_bare_line_number_is_refused():
    problems = assess_citation_form('see blueprint line 386 for the rule')
    assert len(problems) == 1
    assert problems[0]["found"] == "line 386"
    assert "adds a line above it" in problems[0]["reason"]


def test_a_capitalised_line_number_is_refused_too():
    """Caught a real one on its first run.

    A manual sweep converted fifteen citations and missed a sixteenth because it was
    capitalised mid-sentence and the grep was lowercase. This assertion exists so the
    case that escaped a human does not escape again.
    """
    assert assess_citation_form("...not percentage-of-limit.\" Line 1128 gives the reason")


def test_a_repo_relative_path_is_refused():
    problems = assess_citation_form("in `docs/reference/blueprint-v2.md` the section reads")
    assert len(problems) == 1
    assert problems[0]["found"] == "docs/reference/blueprint-v2.md"
    assert "two repositories" in problems[0]["reason"]


def test_prose_about_disciplines_is_not_a_citation():
    """The word-boundary case, which the first version of this pattern got wrong.

    A `line` pattern with no word boundary matches "discipline 1" and "discipline 4". The
    same defect this module already fixed once in `_has_word`, reintroduced in a new regex
    - which is the argument for the boundary being tested rather than merely commented.
    """
    assert assess_citation_form("discipline 1 and discipline 4 hold structurally") == []


def test_the_replacement_form_passes():
    assert (
        assess_citation_form(
            'Marketing Plan Intake §4.2 Claims we make, item 8: "Flat success fees on '
            'approved and funded capital, not percentage-of-limit."'
        )
        == []
    )


def test_both_forms_are_reported_separately():
    problems = assess_citation_form("line 12 and docs/reference/specifications-v2.md")
    assert len(problems) == 2
