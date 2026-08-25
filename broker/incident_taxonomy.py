"""What an incident can be: the severities, the kinds, and who can raise each.

Severity and kind were column headers with no published values. `severity` at least had
a CHECK constraint; `kind` had nothing at all, so any string was a kind and the column
was a free-text field with a schema-shaped name.

**The list is derived from what raises incidents, not from a wish.** Every kind here is
either raised by a named call site in this package or is one a human can file. The brief
that asked for this page listed `phi_flush_failure`, `rate_limit_breach`,
`spend_cap_breach` and `audit_write_failure`; nothing in the broker raises any of them,
and two of them name concepts the system does not have. Publishing a kind nothing can
produce is the same defect as a denominator nothing supports: it reads as coverage.
`test_every_incident_kind_is_published` walks the source and fails if a call site uses a
kind that is not here, so the two cannot drift apart.

Where the brief's name and the real one differ, the real one wins and the brief's is
recorded as an alias so a reader searching for it finds the answer rather than nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

# Stored uppercase, because that is what `incident_severity_check` has always enforced.
# Displayed lowercase, because that is how every other enumerated value in this console
# reads. One mapping, in one place, rather than a `.toUpperCase()` at each call site.
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

# How long an incident of each severity may sit before the page says it is overdue.
#
# These are the console's own markers, not a contractual SLA: nothing in the blueprint
# fixes them, and inventing a number and then presenting it as an external obligation
# would be worse than showing no marker at all. The page says whose they are.
SLA = {
    "CRITICAL": timedelta(hours=1),
    "HIGH": timedelta(hours=4),
    "MEDIUM": timedelta(days=1),
    "LOW": timedelta(days=7),
}

# The colour each severity carries. `low` is deliberately neutral: an incident log where
# everything is coloured is one where nothing stands out.
SEVERITY_TONE = {
    "LOW": "neutral",
    "MEDIUM": "warn",
    "HIGH": "bad",
    "CRITICAL": "bad",
}


@dataclass(frozen=True, slots=True)
class Kind:
    """One kind of incident, and what produces it."""

    kind: str
    label: str
    #: `automatic` if code raises it, `human` if a person files it.
    source: str
    #: What it means, in the terms of the thing that went wrong.
    meaning: str
    #: The module that raises it, for an automatic kind. Empty for a human one.
    raised_by: str = ""
    #: Names the brief or an operator might search for instead.
    aliases: tuple[str, ...] = field(default=())


AUTOMATIC: tuple[Kind, ...] = (
    Kind(
        kind="undeclared_forge_call",
        label="Undeclared Forge call",
        source="automatic",
        meaning=(
            "An agent called a Forge module that its Pack manifest does not declare. "
            "The call is refused and the gap between declared and used is the finding."
        ),
        raised_by="broker.manifest",
    ),
    Kind(
        kind="manifest_sweep_undeclared_in_use",
        label="Undeclared module in use",
        source="automatic",
        meaning=(
            "The manifest reconciliation sweep found a module being used that no live "
            "Pack declares. The same gap as above, found by the sweep rather than at "
            "the moment of the call."
        ),
        raised_by="broker.sweeps",
    ),
    Kind(
        kind="in_use_not_required",
        label="Declared but not required",
        source="automatic",
        meaning=(
            "A module is in use that the Pack no longer requires. Not a refusal - a "
            "drift between what the engagement asked for and what it is doing."
        ),
        raised_by="broker.sweeps",
    ),
    Kind(
        kind="certification_went_stale",
        label="Certification went stale",
        source="automatic",
        meaning=(
            "An agent's certification passed its maximum age and the agent left the "
            "certified state. Its grants stop being usable at the next call."
        ),
        raised_by="broker.sweeps",
        aliases=("certification_stale",),
    ),
    Kind(
        kind="audit_chain_broken",
        label="Audit chain broken",
        source="automatic",
        meaning=(
            "The hash chain over the audit log does not verify. Either a row was "
            "altered or one is missing, and both mean the log can no longer be relied "
            "on as evidence."
        ),
        raised_by="broker.sweeps",
        aliases=("audit_write_failure",),
    ),
    Kind(
        kind="audit_chain_tail_gap",
        label="Audit chain tail gap",
        source="automatic",
        meaning=(
            "The audit chain verifies but stops short of the present. Writes are not "
            "reaching the log, which looks like quiet rather than like failure."
        ),
        raised_by="broker.sweeps",
    ),
    Kind(
        kind="restore_drill_failed",
        label="Restore drill failed",
        source="automatic",
        meaning=(
            "A backup did not restore into a scratch database. The backup exists and "
            "cannot be used, which is the state that looks safest and is not."
        ),
        raised_by="broker.sweeps",
    ),
    Kind(
        kind="rubber_stamp_approval",
        label="Rubber-stamp approval",
        source="automatic",
        meaning=(
            "A proposal was approved faster than its payload could be read. The "
            "approval stands; the pattern is the finding."
        ),
        raised_by="broker.proposals",
    ),
)

# Filed by a person. These are the reason this taxonomy needed a `source` at all: the
# blueprint names agent flag, external report and regulator inquiry as detection
# sources, and only the first can arrive on its own.
HUMAN: tuple[Kind, ...] = (
    Kind(
        kind="regulator_inquiry",
        label="Regulator inquiry",
        source="human",
        meaning=(
            "A regulator has asked a question. Recorded as an incident because the "
            "response has the same stages and the same disclosure obligations."
        ),
    ),
    Kind(
        kind="external_report",
        label="External report",
        source="human",
        meaning=(
            "Someone outside the system reported a problem - a client, a Forge "
            "operator, a member of the public."
        ),
    ),
    Kind(
        kind="manual",
        label="Raised by hand",
        source="human",
        meaning=(
            "An operator saw something worth recording that no check would have "
            "caught."
        ),
    ),
)

KINDS: tuple[Kind, ...] = AUTOMATIC + HUMAN
BY_KIND = {k.kind: k for k in KINDS}
KIND_NAMES = tuple(k.kind for k in KINDS)
HUMAN_KIND_NAMES = tuple(k.kind for k in HUMAN)

# Where a detection came from. Stored on the incident so a human-filed one is never
# mistaken for something a control caught.
DETECTION_SOURCES = ("agent_flag", "control_sweep", "external_report", "regulator_inquiry")

# The five stages of Part 9's response. An incident is a detection; these are what
# happens afterwards, and each is either accounted for or outstanding.
STAGES = (
    ("detection", "Detection", "What was seen, and by what."),
    ("triage", "Triage", "How bad it is, what it touches, and who is handling it."),
    ("containment", "Containment", "What was done to stop it continuing."),
    ("disclosure", "Disclosure", "Who was told, when, and what they were told."),
    ("post_mortem", "Post-mortem", "Why it happened and what changes as a result."),
)
STAGE_NAMES = tuple(name for name, _label, _hint in STAGES)


def display_severity(severity: str) -> str:
    """The lowercase form the console shows for a stored severity."""
    return severity.lower()


def tone(severity: str) -> str:
    """The colour role for a severity, defaulting to neutral for an unknown one."""
    return SEVERITY_TONE.get(severity.upper(), "neutral")


def published() -> dict[str, object]:
    """The whole taxonomy, for the API and the console to render from one source."""
    return {
        "severities": [
            {
                "value": severity,
                "display": display_severity(severity),
                "tone": tone(severity),
                "sla_hours": int(SLA[severity].total_seconds() // 3600),
            }
            for severity in SEVERITIES
        ],
        "kinds": [
            {
                "kind": k.kind,
                "label": k.label,
                "source": k.source,
                "meaning": k.meaning,
                "raised_by": k.raised_by,
                "aliases": list(k.aliases),
            }
            for k in KINDS
        ],
        "detection_sources": list(DETECTION_SOURCES),
        "stages": [
            {"stage": name, "label": label, "hint": hint} for name, label, hint in STAGES
        ],
    }
