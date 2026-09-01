"""Whether a Compliance Library entry constrains anything, as opposed to existing.

THE DEFECT THIS PREVENTS, WHICH HAS ALREADY HAPPENED ONCE
=========================================================

    `broker/curriculum_quality.py` exists because a live instruction set passed every
    check with `"what_it_does": "Documented."` — every section present, none empty, a
    valid content_hash over it, and 234 certifications bound to that hash. A hash of
    the word "Documented." is a valid hash of nothing.

    `author_compliance_entry` currently has exactly the defect that instruction set had:
    it checks the six fields are present and non-blank, and nothing more. An entry
    reading

        applicability_rule:          "Applies."
        agent_behavior_implication:  "Comply."
        escalation_trigger:          "Escalate."
        citation:                    "N/A"

    is accepted, resolves a Pack's `library_entry_ref`, and satisfies V28 and Gate 6.
    An agent reads it and learns nothing. The Pack claims coverage it does not have,
    and the claim is machine-verified.

WHY THE THREE CONTENT FIELDS ARE NOT INTERCHANGEABLE
====================================================

    A library entry answers three different questions and it is common to answer one of
    them three times:

        applicability_rule           WHEN does this bind? A condition an agent can
                                     evaluate against the case in front of it.
        agent_behavior_implication   WHAT does the agent do DIFFERENTLY? The whole
                                     point. An entry that restates the law here has
                                     described an obligation without changing behaviour.
        escalation_trigger           WHEN does the agent STOP and hand to a human?

    So the checks below are not one length rule three times. `agent_behavior_implication`
    is required to contain an instruction, and `escalation_trigger` is required to
    describe a condition — because an entry whose implication is "this rule applies"
    has answered the first question in the second field's slot.

STATES
======

    complete   all six fields real
    thin       real content that does not go far enough
    stub       one or more fields is a way of not writing the field
    missing    a required field is absent
"""

from __future__ import annotations

import re
from typing import Any

REQUIRED_FIELDS = (
    "framework",
    "jurisdiction",
    "applicability_rule",
    "agent_behavior_implication",
    "escalation_trigger",
    "citation",
)

FIELD_TITLES = {
    "framework": "Framework",
    "jurisdiction": "Jurisdiction",
    "applicability_rule": "When it applies",
    "agent_behavior_implication": "What the agent does differently",
    "escalation_trigger": "When the agent stops and escalates",
    "citation": "Citation",
    "runtime_flag": "Runtime flag",
}

#: Shared with `curriculum_quality`, deliberately duplicated rather than imported: the
#: two lists will diverge (a compliance entry may legitimately say "not applicable" about
#: a jurisdiction where an instruction section never may), and a shared constant that
#: must not diverge is a constant somebody will edit for one caller and break the other.
PLACEHOLDER_STRINGS = frozenset({
    "", "-", "--", "?", "xxx",
    "documented", "documented.",
    "todo", "tbd", "pending", "pending authoring", "pending_authoring",
    "n/a", "na", "none", "not applicable", "placeholder",
    "applies", "applies.", "comply", "comply.", "complies",
    "escalate", "escalate.", "review", "review.",
    "as required", "as appropriate", "per policy", "see policy",
    "follow the law", "follow the rules",
})

#: Below this, a field is a label rather than an explanation. Set higher than the
#: curriculum's 20 because these three fields each carry a full condition or
#: instruction, and none of them fits in a sentence fragment.
MIN_PROSE_CHARS = 40

#: An applicability rule and an escalation trigger both describe a CONDITION. One that
#: names no circumstance is a statement that the rule exists.
#:
#: Matched on WORD BOUNDARIES, not as substrings. The first version of this file used
#: `in`, and "obligations apply to data obtained through this connection" passed the
#: instruction check because `obtain` sits inside `obtained` — which is precisely the
#: defect this repository has just spent a day documenting in AnimaForge's moderation
#: filter. A checker that makes the mistake it checks for is worth nothing.
CONDITION_MARKERS = (
    # Clause openers.
    "when", "whenever", "if", "where", "before", "after", "during", "unless",
    "any time", "prior to", "once", "upon",
    # Noun-phrase conditions. "Any client-facing output containing a number about a
    # lender product" is a condition an agent can evaluate; it simply does not open
    # with `when`. The first version of this list rejected it, which is a false
    # positive on the most natural way to write a scope rule — and a checker that
    # cries wolf on a good entry is one an author routes around by entry three.
    "any", "each", "every", "containing", "that contains", "involving",
    # Participial conditions. "A returned report CARRYING a fraud alert" is a
    # condition too, and the list above still rejected it.
    "carrying", "bearing", "showing", "returning", "returned", "flagged", "marked",
    "that carries", "which carries", "on receipt", "at the point",
)

#: HONEST NOTE ON THIS HEURISTIC, kept next to it rather than in a commit message.
#:
#: It has now produced a false positive on BOTH real entries an author has written,
#: and zero true positives on either. Its genuine catches so far have all come from
#: the placeholder list and the citation check, not from here.
#:
#: It is kept because the failure it targets is real — "escalate as needed" is a
#: shrug wearing the clothes of a rule — but the marker list is the weak half of the
#: mechanism and `VAGUE_QUALIFIERS` is the strong half. Prose has unbounded ways to
#: express a condition and a finite list will keep missing them. If it false-positives
#: a third time, invert it: report `thin` only when a vague qualifier is present and
#: nothing concrete survives stripping it, and stop requiring a marker at all.

#: Qualifiers that LOOK like conditions and name no circumstance. "Escalate where
#: appropriate" contains "where" and describes nothing an agent can evaluate.
VAGUE_QUALIFIERS = (
    "where appropriate", "where necessary", "where required", "where relevant",
    "as appropriate", "as necessary", "as required", "as needed",
    "if appropriate", "if necessary", "if needed", "if required",
    "when appropriate", "when necessary", "when needed", "when required",
    "at the agent's discretion", "if in doubt",
)

#: An implication must tell an agent to do or not do something.
INSTRUCTION_MARKERS = (
    "must", "shall", "may not", "do not", "never", "always",
    "require", "requires", "obtain", "obtains", "record", "records",
    "present", "presents", "disclose", "discloses", "capture", "captures",
    "refuse", "refuses", "stop", "stops", "collect", "collects",
    "verify", "verifies", "confirm", "confirms", "attach", "attaches",
    "include", "includes",
)

#: A citation names a source. A bare framework name is not a citation.
CITATION_MARKERS = (
    r"\d",                       # a section, part, year or CFR number
    r"§",
    r"\bU\.?S\.?C\.?\b",
    r"\bC\.?F\.?R\.?\b",
    r"https?://",
)


def _norm(value: Any) -> str:
    return str(value).strip().lower()


def _is_placeholder(value: Any) -> bool:
    return _norm(value) in PLACEHOLDER_STRINGS


#: Regex word boundary. Written as an escaped literal rather than `"\b"`, which is a
#: backspace character in a normal Python string and matches nothing.
BOUNDARY = r"\b"


def _has_word(text: str, markers: tuple[str, ...]) -> bool:
    """True if any marker appears as a WHOLE word (or whole phrase).

    Never a substring: see the note on CONDITION_MARKERS.
    """
    lowered = text.lower()
    return any(
        re.search(BOUNDARY + re.escape(marker) + BOUNDARY, lowered) for marker in markers
    )


def _names_a_condition(text: str) -> bool:
    """A condition marker that is not immediately swallowed by a vague qualifier."""
    lowered = text.lower()
    if not _has_word(lowered, CONDITION_MARKERS):
        return False
    # Strip the vague forms and re-ask. "Escalate where appropriate, and when the
    # client declines" still names a condition; "escalate where appropriate" does not.
    stripped = lowered
    for vague in VAGUE_QUALIFIERS:
        stripped = stripped.replace(vague, " ")
    return _has_word(stripped, CONDITION_MARKERS)


def _ok(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "title": FIELD_TITLES.get(field, field),
        "state": "complete",
        "reason": "",
    }


def _bad(field: str, state: str, reason: str) -> dict[str, Any]:
    return {
        "field": field,
        "title": FIELD_TITLES.get(field, field),
        "state": state,
        "reason": reason,
    }


def assess_field(name: str, value: Any) -> dict[str, Any]:
    """One field: real, thin, stub or missing, and why.

    The reason is written for whoever has to fix it, so it names the specific defect
    rather than saying "invalid".
    """
    if value is None or value == "" or value == []:
        return _bad(name, "missing", "Absent. Nothing has been written here.")

    if name == "jurisdiction":
        if not isinstance(value, list) or not value:
            return _bad(
                name, "missing",
                "Absent. A jurisdiction list is what decides whether this entry binds "
                "a given client at all.",
            )
        if all(_is_placeholder(v) for v in value):
            return _bad(
                name, "stub",
                f"Placeholder — the jurisdictions read {', '.join(str(v) for v in value)!r}.",
            )
        return _ok(name)

    text = str(value).strip()

    if _is_placeholder(text):
        return _bad(name, "stub", f"Placeholder — the field reads {text!r}.")

    if name == "framework":
        # A framework is a short name, so no length rule applies. It just has to be one.
        return _ok(name)

    if name == "citation":
        if not any(re.search(p, text) for p in CITATION_MARKERS):
            return _bad(
                name, "thin",
                "No source. A citation names a statute, section, rule or URL — "
                f"{text!r} names a topic, and an agent asked 'on what authority' "
                "cannot answer from it.",
            )
        return _ok(name)

    if len(text) < MIN_PROSE_CHARS:
        return _bad(
            name, "thin",
            f"Thin — {len(text)} characters. A label rather than an explanation.",
        )

    lowered = text.lower()

    if name == "applicability_rule" and not _names_a_condition(lowered):
        return _bad(
            name, "thin",
            "Names no condition. This field answers WHEN the rule binds, so it needs a "
            "circumstance an agent can evaluate — 'when the client is a California "
            "business', not 'this rule applies to financing'.",
        )

    if name == "agent_behavior_implication":
        if not _has_word(lowered, INSTRUCTION_MARKERS):
            return _bad(
                name, "thin",
                "Describes the obligation rather than the behaviour. This field answers "
                "WHAT THE AGENT DOES DIFFERENTLY, so it needs an instruction — 'the "
                "agent must obtain and record a written authorization naming the "
                "institution before calling the module', not 'GLBA obligations apply'.",
            )
        if lowered.startswith(("this rule", "this framework", "the framework")):
            return _bad(
                name, "thin",
                "Restates the rule instead of the behaviour. An entry that says what "
                "the law is has not said what the agent does.",
            )

    if name == "escalation_trigger" and not _names_a_condition(lowered):
        return _bad(
            name, "thin",
            "Names no condition. This field answers WHEN THE AGENT STOPS, so it needs a "
            "circumstance — 'when the client declines authorization, or the recorded "
            "authorization has expired', not 'escalate as needed'.",
        )

    return _ok(name)


def assess(entry: dict[str, Any]) -> dict[str, Any]:
    """A whole entry, with the worst field's state as the entry's state.

    `teaches_nothing` mirrors `curriculum_quality`'s field of the same name and is what
    a validator rule should refuse on: it is true when the entry exists and constrains
    nothing.
    """
    fields = [assess_field(name, entry.get(name)) for name in REQUIRED_FIELDS]

    by_state = {f["state"] for f in fields}
    if "missing" in by_state:
        state = "missing"
    elif "stub" in by_state:
        state = "stub"
    elif "thin" in by_state:
        state = "thin"
    else:
        state = "complete"

    problems = [f for f in fields if f["state"] != "complete"]

    return {
        "entry_ref": entry.get("entry_ref"),
        "framework": entry.get("framework"),
        "state": state,
        "fields": fields,
        "problems": problems,
        # An entry every one of whose content fields is a stub or missing is an entry
        # that resolves a Pack ref and constrains nothing — the "Documented." case.
        "teaches_nothing": state in {"missing", "stub"},
        "summary": (
            "Complete."
            if state == "complete"
            else "; ".join(f"{f['title']}: {f['reason']}" for f in problems)
        ),
    }


# ------------------------------------------------------------- claim provenance

"""Where each claim in an entry came from.

MIRRORS DECISION D, DELIBERATELY
================================

    specifications-v2's own glossary names the pair this copies: "`issuer_rule` vs
    `unresearched_default` — provenance tags in Lender Intelligence Database per
    Decision D". The Recommendation Engine will not present a figure without saying
    how it was derived, and `lenders/profile.ts` THROWS on an `unresearched_default`
    row with no rationale: "An assumption nobody can explain cannot be argued with or
    revisited."

    A compliance entry is a derived figure of the same kind. It states what an agent
    must do, and a reader cannot weigh that without knowing whether it traces to a
    locked decision, was shaped from surrounding context, or is somebody's proposal
    awaiting review. An entry approved without that distinction is approved on the
    reader's assumption that it was sourced.

PER CLAIM, NOT PER ENTRY
========================

    An entry-level tag would be the average of its parts and therefore true of none
    of them. Every entry written so far mixes all three: a statute citation beside a
    behavioural rule shaped from context beside a phrase awaiting Claim Library
    approval. The useful question is which sentences are which.

THE REQUIRED FIELD PER TAG IS THE WHOLE MECHANISM
=================================================

    `sourced` must name its source, or it is an assertion of sourcing rather than
    sourcing. `reconstructed` must say what it was shaped FROM, for exactly the
    reason profile.ts throws. `proposed` must name who decides, or it is a
    recommendation addressed to nobody.
"""

PROVENANCE_TAGS = ("sourced", "reconstructed", "proposed")

#: The field each tag cannot omit, and why omitting it empties the tag.
REQUIRED_BY_TAG = {
    "sourced": "source",
    "reconstructed": "basis",
    "proposed": "review_by",
}


def assess_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """One claim's provenance: usable, or a tag with nothing behind it."""
    label = str(claim.get("claim", "")).strip()
    tag = str(claim.get("tag", "")).strip().lower()

    if not label:
        return {"ok": False, "tag": tag or None, "reason": "claim has no label"}
    if tag not in PROVENANCE_TAGS:
        return {
            "ok": False,
            "tag": None,
            "claim": label,
            "reason": f"tag {tag!r} is not one of {', '.join(PROVENANCE_TAGS)}",
        }

    required = REQUIRED_BY_TAG[tag]
    value = str(claim.get(required, "")).strip()
    if not value or _is_placeholder(value):
        return {
            "ok": False,
            "tag": tag,
            "claim": label,
            "reason": (
                f"`{tag}` requires `{required}`, and this one is absent. A sourced "
                "claim that names no source asserts sourcing rather than having it; "
                "a reconstruction nobody can explain cannot be argued with."
            ),
        }

    return {"ok": True, "tag": tag, "claim": label, required: value}


def assess_provenance(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry's claims, counted by tag, with the malformed ones named.

    `unmarked` is True when an entry declares no provenance at all. That is not an
    error today — the field is new — but it is the state the sweep exists to clear,
    and reporting it as a count of zero would hide it among entries that are fully
    sourced.
    """
    claims = entry.get("claim_provenance") or []
    if not claims:
        return {
            "unmarked": True,
            "total": 0,
            "counts": {tag: 0 for tag in PROVENANCE_TAGS},
            "problems": [],
        }

    results = [assess_claim(c) if isinstance(c, dict) else
               {"ok": False, "tag": None, "reason": f"malformed claim: {c!r}"}
               for c in claims]

    counts = {tag: sum(1 for r in results if r["ok"] and r["tag"] == tag)
              for tag in PROVENANCE_TAGS}

    return {
        "unmarked": False,
        "total": len(results),
        "counts": counts,
        "problems": [r for r in results if not r["ok"]],
    }


# ---------------------------------------------------------------------------
# Citation form
#
# A citation exists so a reader can go and check. Two forms in this library could
# not do that, and each failed differently:
#
#   REPOSITORY-RELATIVE PATHS. `docs/reference/blueprint-v2.md` resolves in the
#   Operations Console and not in the repository that held the citation. It had
#   been wrong since it was written, and nothing said so, because nothing
#   resolves these paths - they are read by people.
#
#   LINE NUMBERS. Fifteen of them, all still resolving by luck: the edit made to
#   the Marketing Plan on 31 August 2026 replaced two lines in place and added
#   none. One line inserted above the first citation would have invalidated six
#   silently.
#
# The replacement is document, section, quoted phrase. A phrase survives an edit
# that does not change the sentence, and when the sentence changes that is a
# finding rather than a broken link.
# ---------------------------------------------------------------------------

#: A bare line-number citation. `\b` before `line` matters: without it this
#: matches "discipline 1" and "discipline 4", which is how the first version of
#: this pattern reported two false positives in prose it had no business
#: touching. The same word-boundary bug this module already fixed once, in
#: `_has_word`, reintroduced by a regex written in a hurry.
LINE_NUMBER_CITATION = re.compile(r"\bline \d+", re.IGNORECASE)

#: A repository-relative path into a reference document.
REPO_RELATIVE_CITATION = re.compile(r"docs/reference/[A-Za-z0-9._-]+")


def assess_citation_form(text: str) -> list[dict[str, str]]:
    """Citation forms that cannot survive an edit or a repository.

    Returns one problem per offending form, with the offending text, so an author
    is told what to replace rather than that something is wrong.
    """
    problems: list[dict[str, str]] = []

    for match in LINE_NUMBER_CITATION.findall(text or ""):
        problems.append(
            {
                "found": match,
                "reason": (
                    f"'{match}' cites a line number. A line number is invalidated by any edit "
                    "that adds a line above it, silently and with nothing to report it. Cite the "
                    "document, the section, and the phrase in quotes."
                ),
            }
        )

    for match in REPO_RELATIVE_CITATION.findall(text or ""):
        problems.append(
            {
                "found": match,
                "reason": (
                    f"'{match}' is a repository-relative path. The three documents this library "
                    "cites live in two repositories, so a path resolves only for a reader who "
                    "happens to be in the right one. Name the document instead - see the manifest "
                    "at the head of the library file."
                ),
            }
        )

    return problems


# ---------------------------------------------------------------------------
# Pack references
#
# V28 already checks that a Pack's `library_entry_ref` resolves, but it is a world
# rule: it queries `compliance_library_entry` and reports NOT_RUN without a database.
# So the check that matters most - the one an author wants BEFORE anything is loaded
# anywhere - does not run at the moment the mistake is made.
#
# It also checks existence only. An entry that exists and is a TODO stub resolves
# perfectly well and constrains nothing, which is the "Documented." defect wearing the
# Pack's coverage claim: `library_gap: false` then asserts the gap is closed by a file
# with a placeholder in it.
#
# Both halves are checked here, from the two files, with no database.
# ---------------------------------------------------------------------------


def assess_pack_references(
    pack: dict[str, Any], library: dict[str, Any]
) -> list[dict[str, str]]:
    """Pack rows whose `library_entry_ref` does not resolve to a written entry.

    Returns one problem per offending row. A row declaring `library_gap` is not checked:
    it has said the entry does not exist, which is honest and is the state this rule
    exists to distinguish a false claim from.
    """
    entries = {e.get("entry_ref"): e for e in (library.get("entries") or []) if isinstance(e, dict)}

    templates = {
        ref
        for ref, entry in entries.items()
        if any(
            isinstance(value, str) and value.strip().lower() in PLACEHOLDER_STRINGS
            for value in entry.values()
        )
    }

    problems: list[dict[str, str]] = []
    surface = ((pack.get("market") or {}).get("compliance_surface")) or []

    for row in surface:
        if not isinstance(row, dict):
            continue
        ref = row.get("library_entry_ref")
        if not ref or row.get("library_gap"):
            continue

        flag = row.get("runtime_flag", "<no runtime_flag>")

        if ref not in entries:
            problems.append(
                {
                    "runtime_flag": str(flag),
                    "entry_ref": str(ref),
                    "reason": (
                        f"{flag} claims library entry {ref}, which does not exist. The Pack is "
                        "asserting coverage it does not have. Write the entry, or set "
                        "`library_gap: true` so the claim matches the world."
                    ),
                }
            )
            continue

        if ref in templates:
            problems.append(
                {
                    "runtime_flag": str(flag),
                    "entry_ref": str(ref),
                    "reason": (
                        f"{flag} claims library entry {ref}, which exists and is still a "
                        "TEMPLATE. It constrains nothing, so the flag reaches an agent as a bare "
                        "label with the Pack asserting otherwise - which is worse than declaring "
                        "the gap, because it is now machine-verified and false. Keep "
                        "`library_gap: true` until the entry is written."
                    ),
                }
            )

    return problems
