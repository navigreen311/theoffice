"""The per-module scenario content interface — schema, loader, and the worked example.

P-06, P-07 and P-08 author against this. Every refusal below exists because the
alternative is a content file that loads with less in it than its author wrote, and
nothing says so: a misspelled key, a class declared twice, a class both authored and
declared absent, a `not_applicable` with no sentence. None of those crash, and all of
them produce a curriculum that looks finished.

No database. These are pure-parse tests and they run in the DB-less configuration too,
which matters because that configuration is the one that skips everything else here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from generators import scenario_content as sc

WORKED_EXAMPLE = Path(__file__).resolve().parents[2] / "scenarios" / "record_consent.yaml"


def write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL = """
module_id: {module}
forge_id: capitalforge
scenarios:
  - scenario_class: happy_path
    situation: A human forwards a note and asks for it to be filed.
    expected_behavior: File it, and report only that a row exists.
    expected_escalation: None expected; remove the evidence and the agent stops here.
"""


# ------------------------------------------------------------------ the class vocabulary


def test_the_office_ceiling_is_seven_of_nine_and_it_is_structural():
    """§1.1 — the two held-out classes are not a gap in the authoring."""
    assert len(sc.ALL_SCENARIO_CLASSES) == 9
    assert set(sc.HELD_OUT_CLASSES) == {"never_do_violation", "silent_failure"}
    assert len(sc.SUBMITTABLE_CLASSES) == 7
    assert not set(sc.SUBMITTABLE_CLASSES) & sc.HELD_OUT_CLASSES


def test_every_submittable_class_has_an_instruction_section():
    """`instruction_section` is required and non-empty on submission, so a class with
    no section would author a scenario that cannot be submitted."""
    for scenario_class in sc.SUBMITTABLE_CLASSES:
        section = sc.MECHANICAL_SECTIONS.get(
            scenario_class, sc.DEFAULT_SECTIONS.get(scenario_class, "")
        )
        assert section, scenario_class


def test_the_three_mechanical_sources_are_all_required_instruction_sections():
    """What makes the map mechanical rather than a guess: every live instruction has
    all three sections, non-empty, enforced by validate_sections and a CHECK."""
    from broker.instructions import REQUIRED_SECTIONS

    assert set(sc.MECHANICAL_SECTIONS) == {
        "happy_path", "permission_denied", "escalation_required"
    }
    for section in sc.MECHANICAL_SECTIONS.values():
        assert section in REQUIRED_SECTIONS, section


# ------------------------------------------------------------------ the worked example


def test_the_worked_example_loads():
    content = sc.load_module(WORKED_EXAMPLE)
    assert content.module_id == "record_consent"
    assert content.forge_id == "capitalforge"


def test_the_worked_example_accounts_for_every_submittable_class():
    """Supplied or declared. A class that is neither is refused by SimForge rather
    than silently capping the module at `demonstrated` - which is the whole of
    ADR-0049 and the reason this file exists."""
    content = sc.load_module(WORKED_EXAMPLE)
    accounted = set(content.scenarios) | set(content.not_applicable)
    assert accounted == set(sc.SUBMITTABLE_CLASSES)


def test_the_worked_example_declares_no_held_out_class():
    content = sc.load_module(WORKED_EXAMPLE)
    assert not (set(content.scenarios) | set(content.not_applicable)) & sc.HELD_OUT_CLASSES


def test_the_worked_example_carries_an_occasion_and_not_a_restated_rule():
    """§7 — the manual gives rules, a scenario needs an occasion. A situation that is
    a restated `never` teaches nothing the instruction did not already say."""
    content = sc.load_module(WORKED_EXAMPLE)
    for authored in content.scenarios.values():
        assert not authored.situation.lower().startswith("never"), authored.scenario_class
        assert len(authored.situation.split()) >= 20, authored.scenario_class


def test_the_worked_example_escalation_prose_names_a_juncture():
    """§3.2 — a value that restates 'escalation is expected' has not satisfied it."""
    content = sc.load_module(WORKED_EXAMPLE)
    for authored in content.scenarios.values():
        prose = authored.expected_escalation.strip().lower()
        assert prose != "escalation is expected"
        assert "the office's generator does not say which" not in prose
        assert len(authored.expected_escalation.split()) >= 20, authored.scenario_class


def test_the_wire_behavior_carries_both_halves_labelled():
    """The contract has no `situation` field on the wire, so it travels inside
    `expected_behavior` - separated and labelled, so a later revision can split them
    back out mechanically rather than by reading prose."""
    content = sc.load_module(WORKED_EXAMPLE)
    happy = content.scenarios["happy_path"]
    wire = happy.wire_behavior()
    assert wire.startswith("SITUATION: ")
    assert "\n\nEXPECTED: " in wire
    assert happy.situation in wire
    assert happy.expected_behavior in wire


# ------------------------------------------------------------------ refusals


def test_an_unknown_class_is_refused(tmp_path):
    write(tmp_path, "m.yaml", MINIMAL.format(module="m").replace(
        "happy_path", "happy_pathway"))
    with pytest.raises(sc.ScenarioContentError, match="not one of SimForge's nine"):
        sc.load_module(tmp_path / "m.yaml")


@pytest.mark.parametrize("held_out", sorted(sc.HELD_OUT_CLASSES))
def test_a_held_out_class_is_refused(tmp_path, held_out):
    write(tmp_path, "m.yaml", MINIMAL.format(module="m").replace("happy_path", held_out))
    with pytest.raises(sc.ScenarioContentError, match="held out"):
        sc.load_module(tmp_path / "m.yaml")


def test_a_held_out_class_is_refused_in_not_applicable_too(tmp_path):
    """Declaring a held-out class not-applicable is still The Office having an opinion
    about a class that is not its to hold one about."""
    write(tmp_path, "m.yaml", MINIMAL.format(module="m") + """
not_applicable:
  silent_failure: This module cannot over-report a success.
""")
    with pytest.raises(sc.ScenarioContentError, match="held out"):
        sc.load_module(tmp_path / "m.yaml")


def test_an_unknown_top_level_key_is_refused(tmp_path):
    write(tmp_path, "m.yaml", MINIMAL.format(module="m") + "\nscenarois: []\n")
    with pytest.raises(sc.ScenarioContentError, match="unknown key"):
        sc.load_module(tmp_path / "m.yaml")


def test_an_unknown_scenario_key_is_refused(tmp_path):
    """The one that would hurt most: `expected_escalaton` loads as an author having
    written no escalation prose while believing they wrote some."""
    write(tmp_path, "m.yaml", MINIMAL.format(module="m") + "    notes: something\n")
    with pytest.raises(sc.ScenarioContentError, match="unknown key"):
        sc.load_module(tmp_path / "m.yaml")


@pytest.mark.parametrize("field", ["situation", "expected_behavior", "expected_escalation"])
def test_a_missing_or_empty_required_field_is_refused(tmp_path, field):
    body = MINIMAL.format(module="m").replace(f"    {field}: ", f"    {field}: ''\n#  ")
    write(tmp_path, "m.yaml", body)
    with pytest.raises(sc.ScenarioContentError, match="violation, not a pass"):
        sc.load_module(tmp_path / "m.yaml")


def test_a_class_declared_twice_is_refused(tmp_path):
    body = MINIMAL.format(module="m")
    write(tmp_path, "m.yaml", body + body.split("scenarios:")[1])
    with pytest.raises(sc.ScenarioContentError, match="twice"):
        sc.load_module(tmp_path / "m.yaml")


def test_a_class_both_authored_and_declared_absent_is_refused(tmp_path):
    write(tmp_path, "m.yaml", MINIMAL.format(module="m") + """
not_applicable:
  happy_path: There is no successful path through this module.
""")
    with pytest.raises(sc.ScenarioContentError, match="opposite claims"):
        sc.load_module(tmp_path / "m.yaml")


def test_a_not_applicable_without_a_reason_is_refused(tmp_path):
    """ADR-0049 property two. Four of nine compliance_couplings rows were accidental
    empties, which is why the sentence is mandatory rather than encouraged."""
    write(tmp_path, "m.yaml", MINIMAL.format(module="m") + """
not_applicable:
  rate_limited: ''
""")
    with pytest.raises(sc.ScenarioContentError, match="no reason"):
        sc.load_module(tmp_path / "m.yaml")


def test_a_filename_that_disagrees_with_the_module_id_is_refused(tmp_path):
    write(tmp_path, "other.yaml", MINIMAL.format(module="m"))
    with pytest.raises(sc.ScenarioContentError, match="filename is the index"):
        sc.load_module(tmp_path / "other.yaml")


def test_one_module_one_file_is_enforced_by_the_filename_check(tmp_path):
    """Two files cannot describe one module, because the filename must BE the module
    id - so there is never a second copy of a module's content to reconcile."""
    write(tmp_path, "m.yaml", MINIMAL.format(module="m"))
    (tmp_path / "m2.yaml").write_text(
        MINIMAL.format(module="m").replace("module_id: m", "module_id: m2"),
        encoding="utf-8",
    )
    assert set(sc.load_all(tmp_path).modules) == {"m", "m2"}


def test_not_valid_yaml_is_refused(tmp_path):
    write(tmp_path, "m.yaml", "module_id: [unclosed\n")
    with pytest.raises(sc.ScenarioContentError, match="not valid YAML"):
        sc.load_module(tmp_path / "m.yaml")


# ------------------------------------------------------------------ the content set


def test_a_missing_root_is_reported_rather_than_silently_empty(tmp_path):
    """'Nothing has been authored' and 'the directory is not in this image' produce
    the same empty mapping and need different actions."""
    absent = sc.load_all(tmp_path / "nope")
    assert absent.modules == {}
    assert absent.root_exists is False

    present = sc.load_all(tmp_path)
    assert present.modules == {}
    assert present.root_exists is True


def test_the_default_root_finds_the_worked_example():
    """Resolved from the checkout rather than the working directory, so a test, a
    script and the golden all agree about what is authored."""
    content = sc.load_all()
    assert content.root_exists
    assert "record_consent" in content.modules


def test_section_for_prefers_an_explicit_override(tmp_path):
    write(tmp_path, "m.yaml", MINIMAL.format(module="m").replace(
        "    expected_escalation:",
        "    instruction_section: what_it_does_not_do\n    expected_escalation:",
    ))
    content = sc.load_module(tmp_path / "m.yaml")
    assert content.section_for("happy_path") == "what_it_does_not_do"
    assert content.section_for("permission_denied") == "failure_signatures"
