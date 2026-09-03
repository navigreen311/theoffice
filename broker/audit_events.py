"""What each audit event means, and what writes it.

Event names reached the Audit page as raw identifiers - `console_token_reissued` - with
no glossary anywhere in the console. The filter asked the reader to type one, which means
it could only be used by somebody who already knew the answer.

The list is derived from the call sites, the same way the incident taxonomy is:
`test_every_audit_event_written_in_the_source_is_published` walks `broker/` and fails on
an event this file does not describe. A glossary that drifts from the code is worse than
none, because it reads as authoritative.

Labels are plain language, and deliberately say what *happened* rather than restating the
identifier in title case. "Console token reissued" is the identifier with spaces;
"Somebody's token was replaced, invalidating the old one" is what a reader needs when the
question is whether that entry explains an outage.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Written by a person acting in the console. Every one of these carries the actor's
#: human_id, which is what makes the log non-repudiable.
CONSOLE = "console"
#: Written by the provisioning engine as a run moves.
PROVISIONING = "provisioning"
#: Written by the platform itself, with no person behind it.
SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class Event:
    event_type: str
    label: str
    meaning: str
    #: The module that writes it, so a reader can find the code that produced a row.
    written_by: str
    family: str


EVENTS: tuple[Event, ...] = (
    # ------------------------------------------------------------------ console
    Event("console_human_created", "Person added",
          "An account was created and a token issued once.",
          "broker.app", CONSOLE),
    Event("console_human_status_changed", "Person suspended or reactivated",
          "Somebody's access was taken away or given back. Takes effect on their next "
          "request, not their next session.",
          "broker.app", CONSOLE),
    Event("console_token_reissued", "Token reissued",
          "Somebody's token was replaced. The old one stopped working immediately, which "
          "is the entry to look for when a session dies for no apparent reason.",
          "broker.app", CONSOLE),
    Event("console_role_granted", "Role granted",
          "Somebody was given a role by somebody holding a stronger one.",
          "broker.app", CONSOLE),
    Event("console_role_revoked", "Role removed",
          "A role was taken away.", "broker.app", CONSOLE),
    Event("console_test_fixtures_suspended", "Test accounts suspended",
          "Every account created by this project's test paths was suspended in bulk. "
          "Reversible; nothing was deleted.",
          "broker.app", CONSOLE),
    Event("console_venture_created", "Venture created",
          "A new engagement was opened.", "broker.app", CONSOLE),
    Event("console_venture_lifecycle_changed", "Venture lifecycle changed",
          "An engagement moved between draft, active, winding down or archived.",
          "broker.app", CONSOLE),
    Event("console_pack_draft_saved", "Pack draft saved",
          "A Business Pack was edited. Drafts do not provision anything.",
          "broker.app", CONSOLE),
    Event("console_pack_published", "Pack published",
          "A Pack became the live one for its venture. This is what a provisioning run "
          "reads.", "broker.app", CONSOLE),
    Event("console_proposal_decided", "Proposal decided",
          "A human approved or rejected an agent's proposed action.",
          "broker.app", CONSOLE),
    Event("console_gate_signed", "Gate signed off",
          "A human signed a provisioning gate, binding their name to the artifacts.",
          "broker.app", CONSOLE),
    Event("console_incident_raised", "Incident filed by hand",
          "Somebody recorded a detection no control could catch - an external report or "
          "a regulator inquiry.", "broker.app", CONSOLE),
    Event("console_incident_resolved", "Incident closed",
          "An incident was closed with an account of what was done. The detection itself "
          "is untouched.", "broker.app", CONSOLE),
    Event("console_incident_account_appended", "Incident account appended",
          "One stage of an incident response was written down.",
          "broker.app", CONSOLE),
    Event("console_revocation_created", "Revocation issued",
          "The kill switch. Takes effect on the target's next call.",
          "broker.app", CONSOLE),
    Event("console_revocation_reinstated", "Revocation lifted",
          "A revocation was ended. The revocation itself stays in the record.",
          "broker.app", CONSOLE),
    Event("console_hard_cap_reversed", "Hard cap reversed",
          "A spend ceiling was overridden. Requires the strongest role.",
          "broker.app", CONSOLE),
    Event("console_controls_run", "Controls run",
          "The verification sweeps were run from the console rather than on a timer.",
          "broker.app", CONSOLE),
    Event("console_disposition_resolved", "Manifest finding dispositioned",
          "An undeclared Forge call was given a written disposition.",
          "broker.app", CONSOLE),
    Event("console_compliance_exported", "Compliance pack exported",
          "A structured record export was produced, for a regulator or an auditor.",
          "broker.app", CONSOLE),
    Event("console_compliance_entry_authored", "Compliance entry written",
          "A runtime flag was given the entry that says what an agent must do "
          "differently.", "broker.app", CONSOLE),
    Event("console_instruction_authored", "Forge instructions written",
          "Operating instructions for a Forge module were authored or revised.",
          "broker.app", CONSOLE),
    Event("console_persona_authored", "Persona written",
          "A simulation persona was written. Write-only: the body cannot be read back.",
          "broker.app", CONSOLE),
    Event("console_playbook_authored", "Playbook written",
          "An SOP for a lifecycle stage was recorded.", "broker.app", CONSOLE),
    Event("console_playbook_shared", "Playbook shared",
          "A playbook was shared across a tenancy boundary, deliberately.",
          "broker.app", CONSOLE),
    Event("console_playbook_share_revoked", "Playbook share withdrawn",
          "A cross-venture share was taken back.", "broker.app", CONSOLE),

    # ------------------------------------------------------------- provisioning
    Event("provisioning_run_started", "Provisioning run started",
          "A venture began the gate sequence that turns a Pack into a running office.",
          "broker.provisioning", PROVISIONING),
    Event("provisioning_gate_passed", "Gate passed",
          "One provisioning gate was satisfied and the run moved on.",
          "broker.provisioning", PROVISIONING),
    Event("provisioning_gate_blocked", "Gate blocked",
          "A gate refused the run. The reason is in the subject payload.",
          "broker.provisioning", PROVISIONING),
    Event("provisioning_gate_awaiting_human", "Gate waiting for a person",
          "The run reached a gate that needs a human signature and stopped there.",
          "broker.provisioning", PROVISIONING),
    Event("provisioning_run_aborted", "Run aborted",
          "A run was stopped before completion. The Pack is unchanged.",
          "broker.provisioning", PROVISIONING),
    Event("provisioning_run_rejected", "Run rejected",
          "A reviewer refused the run at a gate.",
          "broker.provisioning", PROVISIONING),

    # -------------------------------------------------------------------- system
    Event("bootstrap_human_created", "First operator created",
          "The account that removed the need for a shell to create the second one.",
          "broker.humans", SYSTEM),
    Event("grant_issued", "Grant issued",
          "An agent was given authority to call one Forge module for one venture. "
          "Normally written at the end of the provisioning ladder; a Phase 0 bootstrap "
          "grant carries bootstrap: true in its subject and is not evidence the ladder "
          "was run.", "broker.bootstrap_phase0", SYSTEM),
    Event("office_identity_issued", "Office identity issued",
          "A Village agent was given an identity in The Office. The Office appoints; it "
          "does not create agents.", "broker.roster", SYSTEM),
    Event("village_agent_registered", "Village agent registered",
          "An agent from the Village roster became known here.",
          "broker.roster", SYSTEM),
    Event("village_roster_imported", "Village roster imported",
          "The roster was synced from the Village.", "broker.roster", SYSTEM),
    Event("proposal_expired", "Proposal expired",
          "Nobody decided a proposal before its deadline. Expiry never approves.",
          "broker.proposals", SYSTEM),
    Event("shift_assigned", "Shift assigned",
          "An agent was put on shift for a venture.", "broker.shifts", SYSTEM),
    Event("shift_boundary_completed", "Shift ended",
          "A shift closed and its boundary work ran.", "broker.shifts", SYSTEM),
    Event("shift_phi_flush", "PHI flushed at shift boundary",
          "Protected health information was cleared when a shift ended. The temporal PHI "
          "wall depends on this entry existing.", "broker.shifts", SYSTEM),
)

BY_TYPE = {event.event_type: event for event in EVENTS}
EVENT_NAMES = tuple(event.event_type for event in EVENTS)


def label(event_type: str) -> str:
    """The plain-language label, falling back to the identifier itself.

    An unknown event renders as its identifier rather than as blank or as "Unknown": a
    row whose type this file has not caught up with is still a row somebody needs to
    read.
    """
    event = BY_TYPE.get(event_type)
    return event.label if event else event_type


def published() -> list[dict[str, str]]:
    """The whole glossary, for the reference table and the filter options."""
    return [
        {
            "event_type": event.event_type,
            "label": event.label,
            "meaning": event.meaning,
            "written_by": event.written_by,
            "family": event.family,
        }
        for event in EVENTS
    ]
