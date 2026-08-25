"""Whether a curriculum teaches anything, as opposed to merely existing.

`authored` used to mean a row exists and no section is empty. The live cre-forge
curriculum passes that test with:

    "what_it_does": "Documented."
    "what_it_does_not_do": "Documented."
    "inputs": {"a": "b"}
    "correct_sequence": ["a", "b"]

Every section present, none empty, a valid `content_hash` computed over it, and 234
certifications across the portfolio bound to those hashes. A hash of the word
"Documented." is a valid hash of nothing, and every certification bound to it inherits
that emptiness - the agents read as certified to operate a module nobody has described.

So completeness is assessed from the content rather than from the row's existence, and
in one place: the console renders this, the validator refuses a Pack on it, and the
compliance page counts it. Three readers, one answer. A component that decided for itself
what "thin" meant would eventually disagree with the rule that blocks a release.

**When a new placeholder pattern turns up in practice, it is added here.** Not patched
into whichever screen noticed it - that is how the three readers drift apart.
"""

from __future__ import annotations

from typing import Any

# The eight sections Part 6.1 requires, in the order a reader needs them: what the module
# does before what it does not, the sequence before the failures, the failures before the
# rules about them.
SECTION_ORDER = (
    "what_it_does",
    "what_it_does_not_do",
    "inputs",
    "correct_sequence",
    "failure_signatures",
    "retry_vs_escalate",
    "never_do",
    "compliance_coupling",
)

SECTION_TITLES = {
    "what_it_does": "What it does",
    "what_it_does_not_do": "What it does not do",
    "inputs": "Inputs and their meanings",
    "correct_sequence": "Correct sequence",
    "failure_signatures": "Failure signatures",
    "retry_vs_escalate": "Retry vs escalate",
    "never_do": "Never do",
    "compliance_coupling": "Compliance coupling",
}

# Strings that are a way of not writing the section. Compared case-insensitively after
# stripping, so "documented." and " TODO " are the same thing.
PLACEHOLDER_STRINGS = frozenset({
    "documented.",
    "documented",
    "todo",
    "tbd",
    "pending_authoring",
    "pending authoring",
    "n/a",
    "na",
    "none",
    "-",
    "--",
    "",
    "?",
    "xxx",
    "placeholder",
})

# Names that mean "an example of a name". A curriculum whose inputs are `a: b` documents
# the shape of a dictionary, not the meanings of any inputs.
METASYNTACTIC = frozenset({
    "a", "b", "c", "x", "y", "z",
    "foo", "bar", "baz", "qux", "quux",
    "thing", "stuff", "value", "key", "item",
})

# Below this, a prose section is a label rather than an explanation. Deliberately low:
# the aim is to catch "Documented." and "Retry.", not to impose a word count on somebody
# who has written a genuinely short and complete sentence.
MIN_PROSE_CHARS = 20

# A failure-signatures section with one entry describes one way the module fails. The
# 4xx, timeout and rate-limit cases are the ones an operator meets.
MIN_FAILURE_SIGNATURES = 2

# A sequence of one step is not a sequence.
MIN_SEQUENCE_STEPS = 2


def _is_placeholder_text(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDER_STRINGS


def _is_metasyntactic(value: str) -> bool:
    return value.strip().lower() in METASYNTACTIC


def assess_section(name: str, value: Any) -> dict[str, Any]:
    """One section: is it real, thin, or a placeholder, and why.

    The reason is written for whoever has to fix it, so it names the specific defect -
    "the entire section reads 'Documented.'" rather than "invalid".
    """
    if value is None or value == "" or value == [] or value == {}:
        return {
            "section": name,
            "title": SECTION_TITLES.get(name, name),
            "state": "missing",
            "reason": "Absent. Nothing has been written here.",
        }

    if isinstance(value, str):
        if _is_placeholder_text(value):
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "stub",
                "reason": f"Placeholder — the entire section reads {value.strip()!r}.",
            }
        if len(value.strip()) < MIN_PROSE_CHARS:
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "thin",
                "reason": (
                    f"Thin — {len(value.strip())} characters. A label rather than an "
                    "explanation."
                ),
            }
        return _ok(name)

    if isinstance(value, dict):
        keys = [str(k) for k in value]
        values = [v for v in value.values() if isinstance(v, str)]

        if all(_is_metasyntactic(k) for k in keys) and keys:
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "stub",
                "reason": (
                    f"Placeholder — the keys are {', '.join(sorted(keys))}, which name "
                    "the shape of a dictionary rather than anything real."
                ),
            }
        if values and all(
            _is_placeholder_text(v) or _is_metasyntactic(v) for v in values
        ):
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "stub",
                "reason": "Placeholder — every value is an example rather than a meaning.",
            }
        if name == "failure_signatures" and len(value) < MIN_FAILURE_SIGNATURES:
            described = ", ".join(sorted(keys))
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "thin",
                "reason": (
                    f"Thin — one signature ({described}). No 4xx, timeout, or "
                    "rate-limit case described."
                ),
            }
        return _ok(name)

    if isinstance(value, list):
        entries = [str(v) for v in value]
        if entries and all(len(entry.strip()) <= 1 for entry in entries):
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "stub",
                "reason": (
                    f"Placeholder — every entry is a single character "
                    f"({', '.join(entries)})."
                ),
            }
        if entries and all(
            _is_placeholder_text(entry) or _is_metasyntactic(entry) for entry in entries
        ):
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "stub",
                "reason": "Placeholder — every entry is an example rather than a step.",
            }
        if name == "correct_sequence" and len(entries) < MIN_SEQUENCE_STEPS:
            return {
                "section": name,
                "title": SECTION_TITLES.get(name, name),
                "state": "thin",
                "reason": "Thin — a sequence of one step is not a sequence.",
            }
        return _ok(name)

    return _ok(name)


def _ok(name: str) -> dict[str, Any]:
    return {
        "section": name,
        "title": SECTION_TITLES.get(name, name),
        "state": "complete",
        "reason": None,
    }


def assess(content: dict[str, Any] | None) -> dict[str, Any]:
    """The whole curriculum: four states, computed from what is written.

    `missing` and `stub` are both failures and are kept apart because they need different
    work: one section was never written, the other was filled in with a word that means
    "not yet". `thin` is a warning - it is real content that does not go far enough.
    """
    content = content or {}
    sections = [
        assess_section(name, content.get(name)) for name in SECTION_ORDER
    ]

    states = {section["state"] for section in sections}
    if "missing" in states:
        overall = "missing"
    elif "stub" in states:
        overall = "stub"
    elif "thin" in states:
        overall = "thin"
    else:
        overall = "complete"

    return {
        "state": overall,
        "sections": sections,
        "complete": len([s for s in sections if s["state"] == "complete"]),
        "total": len(SECTION_ORDER),
        "placeholder_sections": [
            s["section"] for s in sections if s["state"] == "stub"
        ],
        "missing_sections": [
            s["section"] for s in sections if s["state"] == "missing"
        ],
        "thin_sections": [s["section"] for s in sections if s["state"] == "thin"],
        # The one a Pack cannot be released against. `thin` is a warning; these are not.
        "teaches_nothing": overall in ("stub", "missing"),
    }


__all__ = [
    "MIN_FAILURE_SIGNATURES",
    "MIN_PROSE_CHARS",
    "SECTION_ORDER",
    "SECTION_TITLES",
    "assess",
    "assess_section",
]
