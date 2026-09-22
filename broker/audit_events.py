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
          "An account was created and a token issued once. HISTORICAL: no longer "
          "written. Creating an account writes `human_account_created` from "
          "`create_human` itself since 21 September 2026 (entry 153). Kept here because "
          "the rows this name wrote are in the chain for good, and an entry the "
          "glossary cannot label renders as a raw identifier.",
          "broker.app", CONSOLE),
    Event("console_human_status_changed", "Person suspended or reactivated",
          "Somebody's access was taken away or given back. Takes effect on their next "
          "request, not their next session.",
          "broker.app", CONSOLE),
    Event("console_token_reissued", "Token reissued",
          "Somebody's token was replaced. The old one stopped working immediately, which "
          "is the entry to look for when a session dies for no apparent reason.",
          "broker.app", CONSOLE),
    Event("console_human_renamed", "Person renamed",
          "An account's display name changed, from what to what. Worth an event of its "
          "own because two Packs name their reviewers by display name and two joins "
          "match on it - so a rename moves what those resolve to, and the name frozen "
          "into earlier gate reasons and evidence is deliberately left as it was.",
          "broker.app", CONSOLE),
    Event("console_human_daily_total_set", "Daily total declared",
          "How many hours a day this person has, across every venture, changed from what "
          "to what. V39 measures every live Pack's declared coverage against this number, "
          "so raising it is what makes somebody else's Pack stop warning - which is why "
          "it is a portfolio act with an event rather than a field somebody edits.",
          "broker.app", CONSOLE),
    Event("console_obligation_discharged", "Obligation discharged",
          "A named human recorded that a human-held compliance obligation was "
          "verified - for which venture, which flag, which jurisdictions, and on "
          "whose authority. `founder_policy` means a founder decided and no lawyer "
          "has read it, which V41 warns about at Gate 2 until `counsel_reviewed_at` "
          "is set. Carries the discharges this one superseded, because a discharge "
          "is replaced rather than edited.",
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
    # Kept although nothing writes it any more, and that is not an oversight. Two
    # `audit_log` rows carry this type; an event the glossary stops describing renders
    # on /audit as a raw identifier, which is the defect this file exists to fix. The
    # walker in `test_every_audit_event_written_in_the_source_is_published` checks
    # written-implies-published, so a published event with no writer is legal.
    Event("grant_tombstone_cleared", "Grant tombstone cleared",
          "A hand-set `agent_forge_grant.revoked_at` was removed. That column was "
          "enforced by `resolve_grant` on every call and was never written by "
          "`revoke()`, so a value in it was a stop with no reason, no actor and no "
          "reinstatement path. This entry is the record the original stamp did not "
          "have. **The column itself was dropped in migration 0036**, so nothing can "
          "write this event again and nothing needs to. See blocking.md B37.",
          "broker.revocation", SYSTEM),
    Event("forge_tenant_credential_removed", "Forge credential removed",
          "A Forge's tenant credential row was deleted because no live Business Pack binds "
          "that Forge any more. `forge_tenant_credential` has no reason column and one row "
          "per Forge, so this entry carries the reason and the full removed row for "
          "restoration. First written 2026-09-15 for voiceforge (decisions entry 90), by hand "
          "through `audit.write_event` - no module writes it, which the walker permits.",
          "broker.audit", SYSTEM),
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
    Event("human_role_granted", "Role granted",
          "A human was given a role, by another human. The role row records who and "
          "when; this is the hash-chained half, and until 21 September 2026 it did not "
          "exist - `revoke_role`'s docstring claimed the audit log recorded this and it "
          "recorded nothing (entry 149).",
          "broker.humans", CONSOLE),
    Event("human_role_revoked", "Role revoked",
          "A human's role was taken away. Written by `revoke_role` itself, for the "
          "reason its grant is: an event a caller remembers to write is an event the "
          "next caller forgets.",
          "broker.humans", CONSOLE),
    Event("escalation_recipient_named", "Escalation recipient named",
          "A human with founder authority named who a governance escalation reaches "
          "for one venture and department. Ruled 21 September 2026: account age never "
          "decides - routing used to pick the oldest account holding `ivan`, so nothing "
          "could reach anybody else (entry 150).",
          "broker.escalation", CONSOLE),
    Event("escalation_raised", "Escalation raised",
          "Somebody escalated a decision they may not make, and this says who raised "
          "it, by which path, and which named recipient it was routed to. Ruled 21 "
          "September 2026: both paths used to return a route and write nothing, so no "
          "escalation could be shown to have been travelled (entry 149).",
          "broker.escalation", PROVISIONING),
    Event("escalation_received", "Escalation received",
          "The recipient picked it up. THE STEP THAT MATTERS: raised-and-answered in "
          "one second by one process proves a function returns, not that anybody got "
          "anything.",
          "broker.escalation", PROVISIONING),
    Event("escalation_answered", "Escalation answered",
          "What the recipient decided, in their own words. A complete raised-received-"
          "answered record is what lets a department's escalation path be attested "
          "verified at all.",
          "broker.escalation", PROVISIONING),
    Event("department_attested", "Department attested",
          "A named human with founder authority attested, for one department and Forge, "
          "that the escalation path and the compliance coupling are verified - with a "
          "reason for each. A STOP-GAP standing in for a hand-over test that does not "
          "exist yet, and the subject carries both reasons so this event and the "
          "append-only table disagree if either is altered (entry 147).",
          "broker.attestation", PROVISIONING),
    Event("department_outcomes_posted", "Department outcomes posted to SimForge",
          "Gate 8 sent a unit-B outcome built from an attestation. It is the only call "
          "that tells SimForge a result rather than asking for one, and it exists "
          "because a department run submits no curriculum, so nothing runs and no "
          "verdict is ever earned (entry 147).",
          "broker.simforge", PROVISIONING),
    Event("provisioning_run_rejected", "Run rejected",
          "A reviewer refused the run at a gate.",
          "broker.provisioning", PROVISIONING),
    Event("curriculum_handed_over", "Curriculum handed to SimForge",
          "A venture's scenario curriculum was sent to SimForge for certification, and "
          "the run reference it returned is what every later verdict is read by. The "
          "actor is the human who provisioned, not an agent: nothing an agent did "
          "produced this call, and naming one would put a name in the record for a "
          "call it never made.",
          "broker.simforge", PROVISIONING),

    # -------------------------------------------------------------------- system
    Event("human_account_created", "Account created",
          "An account was created, with what it IS (origin) and what is actually "
          "enforced for it (`auth_method`) recorded at the one moment both are chosen. "
          "Written by `create_human`, so every path that makes an account leaves this "
          "entry - ruled 21 September 2026, entry 153, because `dev-all build check` "
          "held founder authority for four days and the chain recorded only the "
          "revocation that took it away. `self_created` marks the bootstrap account, "
          "which has nobody above it to be created by.",
          "broker.humans", SYSTEM),
    Event("bootstrap_human_created", "First operator created",
          "The account that removed the need for a shell to create the second one. "
          "HISTORICAL: no longer written, replaced by `human_account_created` "
          "(entry 153).",
          "broker.humans", SYSTEM),
    Event("pack_published", "Business Pack published",
          "A new Pack version took force. It changes what the next provisioning run "
          "builds and voids every Gate 10 signature taken against the previous "
          "version's artifacts. The entry records how many lines changed against the "
          "version it replaced, and what the publisher said it was changing.",
          "broker.packs", SYSTEM),
    Event("pack_drafted", "Business Pack drafted",
          "A Pack version was stored as a draft. It supersedes nothing and cannot "
          "provision - Gate 1 will not find it.", "broker.packs", SYSTEM),
    Event("grant_issued", "Grant issued",
          "An agent was given authority to call one Forge module for one venture. "
          "Normally written at the end of the provisioning ladder; a Phase 0 bootstrap "
          "grant carries bootstrap: true in its subject and is not evidence the ladder "
          "was run.", "broker.bootstrap_phase0", SYSTEM),
    Event("office_identity_issued", "Office identity issued",
          "A Village agent was given an identity in The Office. The Office appoints; it "
          "does not create agents.", "broker.roster", SYSTEM),
    Event("grant_deactivated", "Grant returned to awaiting activation",
          "A named human returned a venture's active grants to the state Gate 5 "
          "creates and Gate 11 clears. NOT a revocation: no authority is withdrawn, "
          "no revocation row is written, and the grant keeps its certification refs "
          "and its issuer. It is the verb for a grant activated for want of a "
          "mechanism - Phase 0 issues grants active because no ladder exists to "
          "activate them - being routed through the ladder once it arrives.",
          "broker.grants", CONSOLE),
    Event("office_identity_reinstated", "Office identity reinstated",
          "A named human returned a suspended identity to active, with a reason. It is the "
          "inverse of the suspension half of a departure cascade and NOT of the revocation "
          "half: no grant is re-issued and no revocation is lifted, so a reinstated agent "
          "holds exactly the authority it held a moment earlier. Re-granting is a "
          "provisioning run.", "broker.roster", CONSOLE),
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
