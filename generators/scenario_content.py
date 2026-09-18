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
_FILE_KEYS = frozenset({
    "module_id", "forge_id", "scenarios", "not_applicable", "status", "approved_by",
    # Provenance the split keys carry. `drafted_by` is who wrote it - the counterpart to
    # `approved_by` and never a substitute for it. `supersedes` and `revised` say which
    # key this replaces and under which ruling, so a reader meeting the file knows it is
    # not the first answer to the same question. `withdrawn_as_untestable` records a
    # scenario measured unexaminable and removed - kept rather than deleted, because a
    # scenario that silently vanishes reads as one nobody thought of.
    "drafted_by", "supersedes", "revised", "withdrawn_as_untestable",
})

#: An answer key is drafted and then approved, and only an approved one is submitted.
#: Ruled by Ivan Green, 17 September 2026: "Answer keys are drafted by Claude and
#: approved by Ivan Green. A draft is never submitted until approved."
#:
#: `status` is REQUIRED and there is no default. A missing status would have to mean
#: one of the two, and both readings are wrong: defaulting to `approved` submits
#: unreviewed prose that SimForge then GRADES an agent against, and defaulting to
#: `draft` would silently stop a venture that is already certifying. The key is cheap
#: and the ambiguity is not.
DRAFT = "draft"
APPROVED = "approved"
_STATUSES = (DRAFT, APPROVED)

#: Per-scenario keys. Same rule.
_SCENARIO_KEYS = frozenset({
    "scenario_class", "situation", "expected_behavior", "expected_escalation",
    "instruction_section", "expected_answer", "draft_note",
})

#: What `expected_answer` may carry. SimForge's ADR-0077 through ADR-0082 designed it;
#: this is The Office's copy of that vocabulary, in the same relationship as
#: `ALL_SCENARIO_CLASSES` is to SimForge's `ScenarioClass`. The Office coins none of it.
#:
#: Measured across the 44 drafted keys: `act` 44, `record_subject` 37, `record_claim` 37,
#: `record_claim_options` 25, `record` 7, `expected_caveat` 4. The two shapes are
#: exclusive - a scenario either expects a record ABOUT something, or expects `record`
#: to say NONE.
_ANSWER_KEYS = frozenset({
    "act", "record", "record_subject", "record_claim", "record_claim_options",
    "expected_caveat",
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

    expected_answer: dict[str, Any] = field(default_factory=dict)
    """The gradeable half, as SimForge's split-key design defines it.

    `expected_behavior` is prose a judge reads. THIS is the part a machine can check
    without one: the act, the subject a record is about, the claim made, the options
    that claim was chosen from, and any caveat required alongside it.

    Empty when a key predates the split - every one of The Office's own five did, until
    SimForge's 44 drafted keys arrived. Empty is not a default that means anything; it
    means this scenario has no machine-checkable half yet, and the generator emits
    nothing rather than emitting a blank.
    """
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
    status: str = APPROVED
    """`draft` or `approved`. A draft is loaded, validated and reported, and never
    submitted - see `ScenarioContentSet.for_module`."""

    approved_by: str = ""
    """Who approved it. Required on an approved file, refused on a draft: a name
    beside `status: draft` is a signature on something nobody signed."""

    scenarios: dict[str, list[AuthoredScenario]] = field(default_factory=dict)
    """Class -> the scenarios probing it, in file order.

    **A LIST, AND THAT IS A PROPOSED AMENDMENT TO §11 A2.1.** The contract says one row
    per `(module, class)`, and this now allows several.

    The reason is A2.1's own: it was written so that *"the Office's count and SimForge's
    count [are] the same count"*. SimForge's split keys have already moved - 44 scenarios
    across 27 `(module, class)` pairs, 17 beyond one each - so holding the letter of A2.1
    is what would now BREAK the parity it exists to protect. Measured, not inferred.

    Keying stays `(module, class)` everywhere it decides anything: coverage counts
    classes, `not_applicable` declares classes, and SimForge's `classify_certification_
    level` reads a set of classes. What changes is only how many occasions may probe one
    class. **Needs Ivan's ratification before it is more than a proposal.**"""

    not_applicable: dict[str, str] = field(default_factory=dict)
    """class -> reason, in prose. ADR-0049: the absence is stated rather than
    inferred, and a declaration without a sentence is refused."""

    def section_for(self, scenario_class: str) -> str:
        found = self.scenarios.get(scenario_class) or []
        if found and found[0].instruction_section:
            return found[0].instruction_section
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
        """The APPROVED content for a module, or None.

        **A draft is not content as far as anything downstream is concerned.** The
        generator, the coverage report and Gate 8 all ask this question, and a draft
        answering it would be submitted to SimForge and graded - which is precisely
        what the 17 September ruling forbids.

        Returning None rather than raising: a module with a draft key is in the same
        position as a module with no key at all, which is a state the pipeline already
        handles and reports. `drafts()` is how the difference stays visible, because
        "nobody has written it" and "somebody wrote it and it is waiting for Ivan" are
        different pieces of work.
        """
        content = self.modules.get(module_id)
        if content is not None and content.status == DRAFT:
            return None
        return content

    def drafts(self) -> dict[str, ModuleContent]:
        """Authored, validated, and not submitted. Reported, never silently dropped."""
        return {
            m: c for m, c in sorted(self.modules.items()) if c.status == DRAFT
        }


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
    status = _require_str(p.name, raw, "status")
    if status not in _STATUSES:
        raise ScenarioContentError(
            f"{p.name} declares status {status!r}. It must be one of "
            f"{', '.join(_STATUSES)} - an answer key is drafted and then approved, and "
            "only an approved one is submitted (Ivan Green, 17 September 2026)."
        )
    approved_by = str(raw.get("approved_by") or "").strip()
    if status == APPROVED and not approved_by:
        raise ScenarioContentError(
            f"{p.name} is approved and names nobody. `approved_by` is who is answerable "
            "for the prose SimForge will grade an agent against; an approval with no "
            "name on it is the shape a rubber stamp has."
        )
    if status == DRAFT and approved_by:
        raise ScenarioContentError(
            f"{p.name} is a draft and carries approved_by {approved_by!r}. A name "
            "beside a draft is a signature on something nobody signed."
        )
    if p.stem != module_id:
        raise ScenarioContentError(
            f"{p.name} declares module_id {module_id!r}. The filename is the index "
            "P-06/07/08 partition on, so it has to be the module id - a file whose "
            "name and contents disagree is loaded under one name and read under "
            "another."
        )

    scenarios: dict[str, list[AuthoredScenario]] = {}
    for entry in _require_list(p.name, raw, "scenarios"):
        authored = _scenario(p.name, entry)
        # SEVERAL OCCASIONS MAY PROBE ONE CLASS. This used to refuse the second, on
        # A2.1's one-row-per-(module, class) rule. SimForge's split keys put four
        # `happy_path` occasions on `underwrite_deal` alone, and refusing them here
        # would have kept The Office at 27 scenarios while SimForge graded 44 - which
        # is the count divergence A2.1 was written to prevent. See `ModuleContent`.
        scenarios.setdefault(authored.scenario_class, []).append(authored)

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
        status=status, approved_by=approved_by,
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
        expected_answer=_answer(filename, scenario_class, entry.get("expected_answer")),
    )


def _answer(filename: str, scenario_class: str, raw: Any) -> dict[str, Any]:
    """`expected_answer`, refused rather than coerced.

    **Absent is allowed and empty is not.** A key written before SimForge split the
    answer out has no `expected_answer` at all, and that is a true statement about it.
    A key that carries the block and leaves it blank is claiming a machine-checkable
    half it does not have, which is the substitution `no silent defaults` refuses.

    `act` is required when the block exists, because it is the one thing every one of
    the 44 drafted keys carries and the one thing a grader cannot infer. The rest are
    optional and measured that way: 37 of 44 name a subject, 25 carry options, 4 carry
    a caveat, 7 say `record: NONE` instead.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ScenarioContentError(
            f"{filename}: expected_answer on {scenario_class!r} is not a mapping. It "
            "carries the gradeable half - act, record subject, claim, options - and a "
            "bare string is prose, which is what expected_behavior is already for."
        )
    _refuse_unknown(filename, f"expected_answer on {scenario_class!r}",
                    set(raw), _ANSWER_KEYS)
    if not str(raw.get("act") or "").strip():
        raise ScenarioContentError(
            f"{filename}: expected_answer on {scenario_class!r} names no `act`. Every "
            "one of the 44 drafted keys carries one, and it is the single thing a "
            "grader cannot recover from the prose."
        )
    if "record" in raw and "record_subject" in raw:
        raise ScenarioContentError(
            f"{filename}: expected_answer on {scenario_class!r} carries both `record` "
            "and `record_subject`. They are the two exclusive shapes - a record about "
            "something, or `record: NONE` - and a scenario expecting both expects "
            "nothing checkable."
        )
    return {k: v for k, v in raw.items()}


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
