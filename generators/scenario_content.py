"""The per-module scenario content interface — schema and loader.

**This is the file P-06, P-07 and P-08 build against, and the only one they need to
read.** They author `scenarios/<module_id>.yaml`; they never open
`generators/curriculum.py`. That is what makes their work parallel-safe: the content
files are disjoint by construction, one per module, and a module operated by two
positions is authored once.

WHY THIS FILE EXISTS AT ALL
===========================

    `docs/scenario-contract.md` §7: the manual sections give **rules**; a scenario
    needs an **occasion**.

    `never_do[2]` of `record_consent` reads *"Never record a channel that was not
    named."* That is a rule. The scenario is: a human forwards a note saying the
    business is happy to be texted, the file carries a mobile and an email, and the
    agent is asked to record consent. **Then** `expected_behavior` is what the agent
    does with that.

    Two things are missing from every manual and cannot be generated from one: the
    **precipitating situation**, and the **escalation as prose**. Those two are what a
    content file supplies. Everything else about a scenario — its class, the
    instruction section it probes, the module it belongs to, the instruction hash it
    binds to — the generator already knows.

WHAT IS NOT AUTHORED HERE
=========================

    The three mechanically-mapped classes exist for every module with a live
    instruction whether or not anybody authors a file, because their source sections
    are required and non-empty on every instruction (see MECHANICAL_SECTIONS). A
    content file **fills** those scenarios; it does not create them. A module with no
    content file still emits them, with `expected_behavior` and `expected_escalation`
    empty — and an empty required field is a violation on submission, not a pass, so
    SimForge refuses it and names it. **The absence shows up as a refusal rather than
    as a missing row**, which is the difference between "nobody has written this yet"
    and "this module has no such behaviour".

    The second of those two states has its own spelling and it is `not_applicable`.

THE SEVEN THE OFFICE MAY AUTHOR, AND WHY IT IS NOT NINE
=======================================================

    Two of SimForge's nine classes are held out (`HELD_OUT_CLASSES`): SimForge cannot
    certify an agent against scenarios the agent's own authoring system wrote, so the
    two that most directly test refusal and concealment are kept unseen. **This file
    refuses to load either one.** The ceiling is structural: The Office can reach
    seven of nine and no amount of authoring changes that.

    In practice it is six, not seven, for every module in the portfolio but one — see
    `docs/scenario-generation.md` on `rate_limited`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

#: SimForge's nine, from `ScenarioClass` in
#: `simforge/apps/api/src/services/operation/scenarios.py`. The Office does not coin
#: new ones - an unknown `scenario_class` is a rejection by design, so that a class
#: nobody considered cannot pass as one somebody did.
ALL_SCENARIO_CLASSES: tuple[str, ...] = (
    "happy_path",
    "malformed_input",
    "partial_failure",
    "silent_failure",
    "rate_limited",
    "permission_denied",
    "never_do_violation",
    "escalation_required",
    "recovery_after_failure",
)

#: SimForge's to author, never The Office's to submit. A process control, not a
#: convenience: `docs/scenario-contract.md` §1.1.
HELD_OUT_CLASSES: frozenset[str] = frozenset({"never_do_violation", "silent_failure"})

#: What is left. Seven.
SUBMITTABLE_CLASSES: tuple[str, ...] = tuple(
    c for c in ALL_SCENARIO_CLASSES if c not in HELD_OUT_CLASSES
)

#: The three that map mechanically from the eight Part 6.1 instruction sections.
#:
#: All three sources are in `broker.instructions.REQUIRED_SECTIONS` and are refused
#: empty by `validate_sections` and by a CHECK constraint on the table - so a module
#: with a live instruction has a source for all three, unconditionally. That is what
#: makes the map mechanical rather than a guess about content.
#:
#: `permission_denied` maps to `failure_signatures` and specifically to its hard
#: failure - the 404/403 row of the table, not the timeout row. The section name is
#: what travels, because the section is the unit SimForge's `instruction_section`
#: names; which row inside it the scenario probes is what the authored occasion says.
MECHANICAL_SECTIONS: dict[str, str] = {
    "happy_path": "correct_sequence",
    "permission_denied": "failure_signatures",
    "escalation_required": "retry_vs_escalate",
}

#: The instruction section each remaining authorable class probes, used when a content
#: file does not name one itself. These are NOT mechanical: no section of a Part 6.1
#: instruction is dedicated to any of them, and a scenario in one of these classes
#: exists only because somebody authored it or declared it absent.
#:
#: `malformed_input` is the interesting one. Its source, `inputs`, is a required
#: non-empty section exactly like the three above, so it *could* have been a fourth
#: mechanical map. It deliberately is not: the three were ruled, a fourth was not, and
#: inventing one would widen a frozen interface by inference. Recorded as an open
#: question in `docs/scenario-generation.md` rather than decided here.
DEFAULT_SECTIONS: dict[str, str] = {
    "malformed_input": "inputs",
    "partial_failure": "failure_signatures",
    "rate_limited": "failure_signatures",
    "recovery_after_failure": "retry_vs_escalate",
}

#: Top-level keys a content file may carry. Anything else is refused rather than
#: ignored - a misspelled key that loads silently is a scenario nobody authored and
#: everybody believes was authored.
_FILE_KEYS = frozenset({"module_id", "forge_id", "scenarios", "not_applicable"})

#: Per-scenario keys. Same rule.
_SCENARIO_KEYS = frozenset({
    "scenario_class", "situation", "expected_behavior", "expected_escalation",
    "instruction_section",
})

_REQUIRED_SCENARIO_KEYS = ("scenario_class", "situation", "expected_behavior",
                           "expected_escalation")


class ScenarioContentError(Exception):
    """A content file was refused. Authoring is a human action, so this is not an
    OfficeError: a refused content file is a note to its author, not a step in an
    agent's call path, and putting one in the agent audit trail would say an agent
    did something wrong when a person did."""


@dataclass(frozen=True, slots=True)
class AuthoredScenario:
    """One authored scenario: the two things a manual cannot give, plus its class."""

    scenario_class: str
    situation: str
    """The precipitating occasion. What is in front of the agent when the scenario
    starts - not a restatement of the rule the scenario tests.

    `docs/scenario-contract.md` §6 lists the fields that reach SimForge and there is
    no field for this one, so it travels inside `expected_behavior` rather than
    beside it. See `wire_behavior()`, and E-004 in `PARALLEL_BUILD_ESCALATION.md`."""

    expected_behavior: str
    """What the agent does with the situation."""

    expected_escalation: str
    """Prose naming the juncture: what the agent has in front of it, what it must stop
    short of doing, and to whom it hands the problem.

    A value that restates "escalation is expected" has not satisfied this
    (`docs/scenario-contract.md` §3.2). It is required on **every** class, including
    `happy_path`, where the honest answer names the boundary the happy path stays
    inside rather than claiming there is no boundary."""

    instruction_section: str = ""
    """Overrides the class's default section. Empty means "use the default"."""

    def wire_behavior(self) -> str:
        """`expected_behavior` as SimForge receives it: the occasion, then the act.

        **THIS IS A SECOND ENCODING INSIDE A FIELD, and it is a recorded workaround.**
        `docs/scenario-contract.md` §6 lists every field that reaches SimForge and
        there is none for the occasion - while §7 says a scenario needs one. An
        expected behaviour stated without its occasion is not gradable: a grader
        reading "the agent records `sms` and nothing else" cannot tell whether that was
        right without knowing what it was handed. So both halves travel in the one
        field that exists.

        The labels are fixed and the separator is a blank line, **so this is
        splittable by a regular expression rather than by rereading prose** on the day
        somebody adds a real `situation` field to both sides. Do not vary the labels
        and do not put a blank line inside either half. **Whoever adds that field
        should delete this method in the same change** and split the stored prose with
        it. E-004 in `PARALLEL_BUILD_ESCALATION.md`, and
        `docs/scenario-generation.md` §7.1.
        """
        return f"SITUATION: {self.situation}\n\nEXPECTED: {self.expected_behavior}"


@dataclass(frozen=True, slots=True)
class ModuleContent:
    """One module's authored scenarios and its declared absences."""

    module_id: str
    forge_id: str
    scenarios: dict[str, AuthoredScenario] = field(default_factory=dict)
    """Keyed by scenario class. One per class, because the operation key is
    `(module, class)` - `docs/scenario-contract.md` §11 A2.1."""

    not_applicable: dict[str, str] = field(default_factory=dict)
    """class -> reason, in prose. ADR-0049: the absence is stated rather than
    inferred, and a declaration without a sentence is refused."""

    def section_for(self, scenario_class: str) -> str:
        authored = self.scenarios.get(scenario_class)
        if authored is not None and authored.instruction_section:
            return authored.instruction_section
        return MECHANICAL_SECTIONS.get(
            scenario_class, DEFAULT_SECTIONS.get(scenario_class, "")
        )


@dataclass(frozen=True, slots=True)
class ScenarioContentSet:
    """Everything authored, plus where it was looked for.

    `root` and `root_exists` are carried rather than discarded because "nothing has
    been authored" and "the content directory is not in this image" produce the same
    empty mapping and need different actions. A reader that can only see the mapping
    cannot tell them apart, which is the ambiguity ADR-0049 exists to remove one level
    up.
    """

    root: Path
    root_exists: bool
    modules: dict[str, ModuleContent] = field(default_factory=dict)

    def for_module(self, module_id: str) -> ModuleContent | None:
        return self.modules.get(module_id)


def default_root() -> Path:
    """Where content lives, resolved the way `packs/` is.

    Two candidates, first existing wins: the repository checkout (so a test, a script
    and the golden all agree regardless of the working directory), then `./scenarios`
    (so the runtime image finds `/app/scenarios`, which the Dockerfile copies beside
    `/app/packs` for exactly this reason). Neither existing is not an error here - it
    is reported as a coverage denominator by the curriculum generator, which is where
    a reader is already looking for what is missing.
    """
    checkout = Path(__file__).resolve().parent.parent / "scenarios"
    if checkout.is_dir():
        return checkout
    return Path("scenarios")


def load_all(root: Path | str | None = None) -> ScenarioContentSet:
    """Load every `<module_id>.yaml` under `root`.

    Refuses rather than skips. A content file that does not parse, names a class
    nobody defined, names a held-out class, declares a class twice, or declares a
    class both authored and not-applicable is an error with the file named - never a
    module that quietly loads with fewer scenarios than its author wrote.
    """
    base = Path(root) if root is not None else default_root()
    if not base.is_dir():
        return ScenarioContentSet(root=base, root_exists=False)

    # One module, one file, and `load_module` refuses a file whose name and
    # `module_id` disagree - so distinct filenames cannot produce a duplicate key
    # here, and there is no second copy of a module's content to reconcile.
    modules: dict[str, ModuleContent] = {}
    for path in sorted(base.glob("*.yaml")):
        content = load_module(path)
        modules[content.module_id] = content
    return ScenarioContentSet(root=base, root_exists=True, modules=modules)


def load_module(path: Path | str) -> ModuleContent:
    """Parse and validate one content file."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioContentError(f"{p.name} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ScenarioContentError(f"{p.name} does not contain a mapping at the top level")

    _refuse_unknown(p.name, "top level", set(raw), _FILE_KEYS)

    module_id = _require_str(p.name, raw, "module_id")
    forge_id = _require_str(p.name, raw, "forge_id")
    if p.stem != module_id:
        raise ScenarioContentError(
            f"{p.name} declares module_id {module_id!r}. The filename is the index "
            "P-06/07/08 partition on, so it has to be the module id - a file whose "
            "name and contents disagree is loaded under one name and read under "
            "another."
        )

    scenarios: dict[str, AuthoredScenario] = {}
    for entry in _require_list(p.name, raw, "scenarios"):
        authored = _scenario(p.name, entry)
        if authored.scenario_class in scenarios:
            raise ScenarioContentError(
                f"{p.name} declares {authored.scenario_class!r} twice. An operation "
                "scenario is keyed on (module, class), so a second one has nowhere "
                "to go and would silently replace the first."
            )
        scenarios[authored.scenario_class] = authored

    not_applicable: dict[str, str] = {}
    for cls, reason in (raw.get("not_applicable") or {}).items():
        _check_class(p.name, cls)
        if not isinstance(reason, str) or not reason.strip():
            raise ScenarioContentError(
                f"{p.name}: not_applicable[{cls!r}] has no reason. A declaration "
                "without a sentence is refused - four of nine compliance_couplings "
                "rows turned out to be accidental empties, which is why the sentence "
                "is mandatory rather than encouraged (ADR-0049)."
            )
        if cls in scenarios:
            raise ScenarioContentError(
                f"{p.name}: {cls!r} is both authored and declared not_applicable. "
                "Those are opposite claims about the same (module, class) and only "
                "one of them can be true."
            )
        not_applicable[cls] = reason.strip()

    return ModuleContent(
        module_id=module_id, forge_id=forge_id,
        scenarios=scenarios, not_applicable=not_applicable,
    )


def _scenario(filename: str, entry: Any) -> AuthoredScenario:
    if not isinstance(entry, dict):
        raise ScenarioContentError(f"{filename}: a scenarios entry is not a mapping")
    _refuse_unknown(filename, "a scenario", set(entry), _SCENARIO_KEYS)

    for key in _REQUIRED_SCENARIO_KEYS:
        value = entry.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ScenarioContentError(
                f"{filename}: a scenario is missing {key!r}, or it is empty. "
                "A present-but-empty field is a violation, not a pass "
                "(docs/scenario-contract.md §6)."
            )

    scenario_class = entry["scenario_class"].strip()
    _check_class(filename, scenario_class)

    section = (entry.get("instruction_section") or "").strip()
    return AuthoredScenario(
        scenario_class=scenario_class,
        situation=entry["situation"].strip(),
        expected_behavior=entry["expected_behavior"].strip(),
        expected_escalation=entry["expected_escalation"].strip(),
        instruction_section=section,
    )


def _check_class(filename: str, scenario_class: Any) -> None:
    if not isinstance(scenario_class, str) or scenario_class not in ALL_SCENARIO_CLASSES:
        raise ScenarioContentError(
            f"{filename}: {scenario_class!r} is not one of SimForge's nine scenario "
            f"classes. The Office does not coin new ones; an unknown class is a "
            f"rejection by design. The nine are: {', '.join(ALL_SCENARIO_CLASSES)}"
        )
    if scenario_class in HELD_OUT_CLASSES:
        raise ScenarioContentError(
            f"{filename}: {scenario_class!r} is held out. SimForge authors it, and "
            "The Office must never submit one - it cannot certify an agent against "
            "scenarios the agent's own authoring system wrote. The Office's ceiling "
            "is seven of nine and that is structural, not a gap in the authoring."
        )


def _refuse_unknown(
    filename: str, where: str, present: set[Any], allowed: frozenset[str]
) -> None:
    unknown = sorted(str(k) for k in present - set(allowed))
    if unknown:
        raise ScenarioContentError(
            f"{filename}: unknown key(s) at {where}: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}. An unrecognised key is refused "
            "rather than ignored, because a misspelled one loads as an author having "
            "written nothing while believing they wrote something."
        )


def _require_str(filename: str, raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ScenarioContentError(f"{filename}: {key!r} is required and must be a string")
    return value.strip()


def _require_list(filename: str, raw: dict[str, Any], key: str) -> list[Any]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ScenarioContentError(f"{filename}: {key!r} must be a list")
    return value
