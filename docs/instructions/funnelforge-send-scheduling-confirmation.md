# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `send_scheduling_confirmation`
**Endpoint:** `POST /api/emails/send` (via the adapter's `POST /send_scheduling_confirmation`)
**Template:** `scheduling_confirmation` — closed over, not a parameter
**Version:** 1.0 — drafted 10 September 2026 by P-16b, against `adapters/funnelforge/` at
`ac6475c`
**Status:** draft, pending Compliance Review Board

> **AMENDED 10 SEPTEMBER 2026 — THE APPROVED COPY CHANGED UNDER `docs/blocking.md` B43.**
> The §4.5 gate ruled on B43's D-6 (the attachment promise) and D-1 (the reply instruction)
> and **removed both from the copy rather than building the transport**, because carrying
> them needs a second email transport in FunnelForge and *"that shouldn't happen as a side
> effect of an attachment promise"*. The body quoted in §1 below is the current one.
>
> **Superseded in premise: **§2 *It does not give the client a way to reply to Burkham***. D-1 removed the reply instruction. **§2 *It does not put the details in the email*** and **§2 *It does not send a calendar invitation*** are NOT superseded — B43's D-2 is still open and both sentences are still in the copy.**
>
> **What did not change: the transport.** Every statement in this manual about what the send
> path cannot do is still true, and every rule in §7 still stands — an agent must not say by
> hand what the copy no longer says. **What changed is only that the copy no longer says it.**
>
> **AND THE RULING LEFT THIS TEMPLATE WORSE ON ONE AXIS, WHICH B43 RECORDS RATHER THAN HIDES.** *"reply here and we will move it"* was the only remedy the message offered a client whose appointment time is wrong. It did not work — it reached FunnelForge, and there is no reschedule module — but it was the only thing there. **The message now offers no remedy at all**, while still saying the details are below and still promising a calendar invitation. B43 records `send_scheduling_confirmation` as a module that should not be sent until D-2 is ruled.


Read `funnelforge-approved-send-rules.md` first, and
`funnelforge-send-intake-acknowledgment.md` second — that is the canonical manual for the six
approved sends, and the request shape, the two refusals, the adapter failure table and the
retry rule are identical here and are not repeated. **This manual covers the occasion, the
recipient, the approved copy and the compliance entries that copy touches**, which is what
differs.

**Two things about this module are true of no other send, and they are the manual:**

1. **It is never the first confirmation.** FunnelForge already sent one, unconditionally, at
   the moment the appointment was created. §1.
2. **Its approved copy makes three promises the stack cannot keep**, and none of them is the
   attachment problem. §2 and `docs/blocking.md` B38.

## 1. WHAT IT DOES

Sends one fixed email to one named person: the Blueprint scheduling confirmation.

Subject: *"Your Blueprint call is confirmed"*. Body, in full:

> Your Blueprint call is confirmed. The details are below, and a calendar invitation follows
> separately.

That is the entire message. Two sentences and a closing line.

**Who receives it.** A client who has paid for the Funding Readiness Score Blueprint — $497
Standard or $997 Comprehensive — and has just taken a time
(`docs/reference/burkham-wickmont-marketing-plan-intake.md` Part 2.1 step 4, and §6.5 on
pricing: *"Prospect pays before the Blueprint call"*). **They have already paid.** This is not
a prospect being courted; it is a customer waiting for the thing they bought, and the Blueprint
call is the first human contact Burkham has with them at all (Part 5: *"first human touch is
the Blueprint call"*).

**What that recipient believes when this arrives.** That the message contains their
appointment. The subject says confirmed, the first sentence says the details are below, and a
person who has just chosen a time and paid several hundred dollars for what happens at it
opens the mail to read back the date. **There is nothing below.** They then wait for the
calendar invitation the second clause promises, which does not come, and the natural next act
is to reply — which does not reach Burkham either. §2.

### The confirmation this module sends is the second one

**`POST /api/scheduling/public/:businessId/:slug/book` calls `sendAppointmentConfirmationEmail`
on every successful booking**, guarded only by `if (clientEmail)`, which the route's own schema
requires. `funnelforge-schedule-blueprint-call.md` §2 sets this out in full and
`docs/blocking.md` B33 finding 4 records it: the copy is FunnelForge's own
`templates.appointmentConfirmation`, it is not on the approved list, it was not reviewed under
§4.5, and no refusal in `adapters/funnelforge/gate.py` can reach it.

**So an appointment cannot exist without FunnelForge having attempted a confirmation for it.**
That is true whether the agent booked it through `schedule_blueprint_call` or the client booked
it themselves from the public booking page — it is the same route, and the module reaches the
identical handler.

**Which makes this module's only possible role a second confirmation for one appointment**, and
leaves the awkward half where it belongs, in the open: **the reviewed message is the
duplicate.** FunnelForge's unreviewed one goes first because it is welded to the write. Which
of the two should exist is a §4.5 decision and it has not been made. Today the question is
hidden by the fact that neither arrives (shared rule 3), and the day somebody configures a
provider it stops being hidden and becomes two emails to a paying client for one appointment.

**One refusal pair and one required state**, exactly as the canonical manual sets out:
`TEMPLATE_NOT_AUTONOMOUS` / `TEMPLATE_NOT_APPROVED`, and `COMPLIANCE_STATE_ABSENT` /
`COMPLIANCE_STATE_NOT_PASS`. Nothing about them is different here.

## 2. WHAT IT DOES NOT DO

### It does not put the details in the email, and the copy says it does

**There are no details below.** The approved body is a fixed string in
`adapters/funnelforge/templates.py`, and **none of the six approved subjects or bodies contains
a merge field** — shared rule 7a states it and `templates.py` can be counted: zero occurrences
of any `{{...}}`. So `personalizeContent` has nothing to substitute, `context` and
`recipient_first_name` travel upstream and change nothing, and there is no date, no time, no
duration, no location and no name in the message that goes out.

**The sentence *"The details are below"* is therefore false on every send**, and it is false in
a way the recipient discovers immediately, because it is an instruction to look at something
that is not there.

**This is the same family as shared rule 7f and it is not the same defect**, which is worth
separating rather than merging. 7f is about an enclosure the transport cannot carry. This is
about a message whose body promises its own contents. `docs/blocking.md` B33's finding 3 lists
`scheduling_confirmation` among the three templates *unaffected* by the attachment problem, and
that is correct — it promises no enclosure. It promises something else instead, and nobody had
looked. Recorded in `docs/blocking.md` B38.

### It does not send a calendar invitation, and nothing on this Forge can

*"a calendar invitation follows separately."* Nothing follows.

**No module on this Forge emits one.** The nine are five sends, a distribution, a booking, a
capture and a read; none produces an `.ics`, and the booking route supplies no `calendarUrl` to
its own confirmation and leaves `Appointment.meetingUrl` null
(`funnelforge-schedule-blueprint-call.md` §2 and its PROVENANCE, read from the route and the
Prisma schema).

**And the transport could not carry one in either form.** As a file it is an attachment, and
shared rule 7f establishes there is no attachment field at any layer — not in
`sendEmailSchema`, not in `SendEmailOptions`, not in any provider call. As a link it needs a
URL, and the only URL field on the appointment is the null `meetingUrl`.

So this is not a step somebody forgot to run. **There is no path by which the promised
invitation could arrive**, and an agent must not describe it as delayed, queued or pending.

### It does not give the client a way to reply to Burkham

*"reply here and we will move it."* A reply does not reach Burkham.

**The adapter sends no `from`**, so the envelope is `FunnelForge <hello@funnelforge.ai>` —
shared rule 7b, measured. **And there is no way to set a Reply-To on this path**: the send
schema's fields are enumerated in two places in this repository — shared rule 7f (`to`,
`from`, `subject`, `html`, `text`, `preheader`, `tags`, `leadId`) and the route comment in
`adapters/funnelforge/upstream.py` — and neither enumeration contains one. With no Reply-To, a
reply goes to the From address, which is FunnelForge's.

**So the client replies to `hello@funnelforge.ai`**, and this manual cannot say what happens
after that, because that mailbox is not Burkham's and nothing in The Office watches it.

**Worse for this template than for the others, because the reply is the remedy the copy
offers.** The message tells a client with a wrong appointment time that replying is how it gets
moved. It is the only remedy stated, and it is the one thing the client will act on.

**And there is nothing to move it with.** These nine modules include no read, no list, no
cancel and no reschedule (`funnelforge-schedule-blueprint-call.md` OPEN). Even a reply that
somehow reached Burkham could not be acted on through this Forge.

Recorded together in `docs/blocking.md` B38, because three of the six approved templates say
*"reply"* and the same absence defeats all three.

### The rest

**It does not tell you whether an email was sent.** `sent: true` is a constant. Shared rule 1.
Read `upstream.status`.

**It does not book, confirm, verify, read or touch an appointment.** It sends an email that
says an appointment is confirmed. **It never checks that one exists.** There is no lookup on
this path and no read module on this Forge — so a call with a correct address and a `pass`
state sends *"Your Blueprint call is confirmed"* to somebody with no appointment, successfully,
and nothing anywhere objects.

**It does not know what was booked.** No appointment id is an input, no appointment id is read,
and the message carries none. The module and the booking are joined by nothing but the agent's
own belief that they belong together.

**It does not record anything in FunnelForge.** Shared rule 7c. No `EmailQueue` row, no
`EmailEvent` row.

**It does not know whether it has already sent.** Shared rule 8, and here that compounds with
§1: the module cannot see its own prior sends *or* the confirmation the booking route already
attempted.

## 3. WHAT EACH INPUT MEANS

Identical to `funnelforge-send-intake-acknowledgment.md` §3 — `recipient_email` and
`compliance_state` required, `recipient_first_name` and `context` accepted and inert,
`template_id` read by nothing. Three notes are specific to this module.

**`context` is more tempting here than anywhere else on this Forge**, and it is the same inert
field. The message says the details are below; an agent that puts the date and time in
`context` has done the thing the message appears to be asking for, and produced the identical
empty confirmation. **Then it reports the appointment details as communicated.** That is the
worst available outcome on this module: the recipient's confusion is now invisible, because
somebody upstream believes the time was sent.

**There is no field for the appointment.** Not the id, not the date, not the time, not the
type. The agent cannot supply them and the message cannot carry them. If a client must be told
when their call is, **this module is not how**, and no module on this Forge is.

**`compliance_state` is §3.3's categorical state for this message**, produced by a compliance
process and never composed by the agent. It says nothing about whether an appointment exists.
A `pass` is not clearance that the booking is real.

## 4. THE CORRECT SEQUENCE

1. **Establish that an appointment actually exists, outside this module.** From the
   `upstream.body.data.id` a booking returned, or from a person who can see the calendar. The
   module cannot check and will send the confirmation regardless.
2. **Establish what FunnelForge already sent.** A booking succeeded, so
   `sendAppointmentConfirmationEmail` ran (§1). Today it failed silently; if a provider is
   configured it did not. **Either way this send is the second one**, and whether it should
   happen at all is a question for whoever asked, not a step to perform.
3. **Obtain the categorical compliance state** from the process that produces it.
4. **Call once**, with `recipient_email` and `compliance_state`.
5. **Read `upstream.status`.** Not `sent`. Shared rule 1.
6. **Report what the message actually contained**, and this is the step this module adds to the
   canonical sequence. A `200` means a provider accepted a two-sentence email that says the
   details are below, contains no details, promises a calendar invitation that does not exist,
   and invites a reply that reaches FunnelForge. **Report the send and that description
   together.** Not the send alone.
7. **Tell whoever asked how the client will learn the time**, because it will not be from this.
8. **Do not call again.** Shared rules 8 and 9; the 429 exception is in §6.

**Step 6 is this module's step 4.** The canonical manual's warning is that an agent reads
`sent` instead of `upstream.status` and reports an email that does not exist. Here there is a
second, quieter version of the same error available to an agent that gets step 5 right: a
truthful *"the confirmation was sent"* that leaves a person believing their client now knows
when the call is.

## 5. WHAT FAILURE LOOKS LIKE

**Both tables in `funnelforge-send-intake-acknowledgment.md` §5 apply unchanged** — the
adapter's `503` / `401` / `404` / `422` / `200`, and FunnelForge's `200` / `400` / `401` /
`429` / `500`. There is no route difference: this is the same `POST /api/emails/send` with a
different `html` string. Two things about what they mean are different here.

**`500 SEND_FAILED` on this module leaves a client with FunnelForge's confirmation and nothing
else** — and today, with no provider configured, with neither. The client picked a time and
heard nothing at all. That is not a worse failure than any other 500 on this Forge; it is a
more urgent one, because the client is expected on a call.

**A `200` is the misleading answer here, for a different reason than on
`distribute_referrer_briefing`.** There the message refers to an absent enclosure. Here the
message refers to absent contents of itself, and unlike a missing attachment, a reader cannot
tell whether something was stripped or was never there. **They will assume the mail is broken
and reply.** The reply is the failure that has no signature at all: it produces no status, no
code and no row anywhere, and the first anyone learns of it is a missed call.

## 6. RETRY VS ESCALATE

**On a timeout: stop and escalate. Do not retry. Do not check first.** Shared rule 9, and the
canonical manual's reasoning holds unchanged — there is nothing to check, because nothing is
written.

**The duplicate this module risks is a third message, not a second.** FunnelForge's
confirmation, this one, and a retry: a client who booked one Blueprint call receives three
confirmations for it, one of which no founder has read. That is the asymmetry, and it is
sharper than the canonical case.

**A 429 is a wait, not a retry.** Refused before the route ran, nothing sent. Honour
`retryAfter` from the body; read shared rule 4c before concluding anything about pacing.

**A 500 is an escalation about FunnelForge's configuration and it carries a deadline.** The
message names the cause and it is not the agent's to fix — but unlike an acknowledgment, this
one has a date attached. **Say when the call is** when handing it over, so that whoever
receives it knows how long they have to reach the client another way. That is the only fact
about the appointment the agent has, and it did not come from this module.

**The three unkeepable promises are not an escalation an agent resolves and they are not a
reason to send.** If a person asks for the confirmation to go out and the agent knows it
carries no details, promises an invitation that cannot arrive, and offers a reply address that
is not Burkham's, **the honest act is to say so before sending.** That is a refusal addressed
to the person who asked, and the decision belongs to whoever owns the §4.5 template review.

## 7. NEVER

All of `funnelforge-send-intake-acknowledgment.md` §7 applies. Eight more are this module's.

**Never say the client has been told when their call is.** The message contains no date and no
time. This is the single most likely false report on this module, because the subject line and
the module's own name both say confirmation.

**Never say a calendar invitation is on its way, following, queued or delayed.** Nothing on
this Forge produces one and the transport could not carry one. §2.

**Never tell a client to reply to this message**, and never report that the client has a way to
reach Burkham about the time. The reply goes to `hello@funnelforge.ai`.

**Never put the appointment details in `context` and then report them as sent.** The approved
copy has no merge field. Nothing in `context` reaches the recipient. Shared rule 7a.

**Never send this without establishing that the appointment exists.** The module checks
nothing. *"Your Blueprint call is confirmed"* sent to somebody with no booking is a false
statement to a paying client, made in Burkham's name, and it is one call away at any time.

**Never send this as the confirmation.** It is the second one. FunnelForge already sent one on
the booking, unreviewed, and an agent that describes this as *the* confirmation has hidden the
existence of the first from whoever it is reporting to.

**Never state the appointment time without stating the timezone it was agreed in.**
`funnelforge-schedule-blueprint-call.md` §3: `startTime` is a bare `HH:mm` string, nothing in
the request, the response or the row carries a zone, and this module cannot see any of it
anyway. An agent that reads a time off a booking and states it to the client has stated a zone
nobody established.

**Never present a confirmed call as a commitment, a place in the process, or anything Burkham
has promised beyond the hour itself.** The client has bought a diagnostic. The confirmation
confirms a time and nothing else.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR, runtime flag
`outbound_contact_boundary_required`) — *"Any Burkham-initiated contact with an individual, any
channel."* The governing entry, as for all six sends.

**And this is the send where its three-part test is satisfied most cleanly, which is worth
saying rather than assuming.** The entry requires all three before any contact:

- **A — the relationship exists.** The client took an affirmative initiating action and paid
  for a Blueprint. Documented, with source attribution.
- **B — the channel is authorised.** They supplied the email address at booking; the entry's
  rule is that *"the channel the person gave is the channel available"*, and email is it.
- **C — the purpose matches the reason.** They booked a Blueprint call; this is about that
  Blueprint call. The entry's own example is *"A Blueprint client may be contacted about their
  Blueprint"*.

**So nothing about whether this may be sent is in doubt.** What can go wrong on this module is
entirely what the message says, which is why §2 is the long section and this one is short.
**Do not read that as headroom.** The test is satisfied for *this* message about *this* call,
and it does not extend to anything else the agent might want to tell the client while it has
their attention — the entry is explicit that a Blueprint client is not thereby cross-sellable,
and the agent could not add a sentence anyway (shared rule 7a).

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT, `own_claims_discipline_required`) — the
entry permits deliverable promises and defines the boundary precisely: *"The Blueprint may
promise its own contents: a readiness assessment with named components, in a stated format, by
a stated date. It may not promise a funding outcome."* **This copy makes three promises of that
permitted kind and the stack keeps none of them** — details in this message, an invitation
after it, a reply channel back. The entry's standard is *"whether a reasonable consumer would
be misled"*, and it records that there is **no safe harbour**: no disclosure rescues a claim
that misleads.

**That is a §4.5 matter and not an agent's**, exactly as the attachment problem is. The copy
was admitted to the approved list by a two-founder review, this manual documents the code, and
what retires the item is a decision — the copy changes and returns through that gate, the
transport grows the fields the copy assumes, or the template stops being an autonomous send.
**The agent's obligation is narrow and absolute: never repeat any of the three promises as
though it were kept.**

**`compliance/client-interest-standard-v1`** (UDAAP, `client_interest_standard_required`) —
*"Any client-facing claim about approval, cost or outcome."* The approved copy makes none, and
the agent cannot add one (shared rule 7a). Named because the recipient is at the point of the
engagement where a claim about outcome would land hardest: they have paid and not yet met
anybody.

**`compliance/estimate-not-offer-v1`** (STATE_COMMERCIAL_FINANCING_DISCLOSURE;
MCA_DISCLOSURE_CA_SB1235) — **scoped out, explicitly, for the reason
`funnelforge-schedule-blueprint-call.md` §8 scopes it out.** A confirmation of a diagnostic
conversation states no rate, no amount and no term. Named because "confirming the capital
conversation" is where somebody would reasonably look for it.

**`compliance/consumer-privacy-rights-v1`** (CCPA; STATE_PRIVACY_COMPREHENSIVE) — the
recipient's address is personal data about an identified person. The module writes nothing
(shared rule 7c), so it creates no record to answer an access or deletion request from; The
Office's ledger row is the only one it produces.

**No FCRA entry and no GLBA entry apply.** §6.3 caps FunnelForge at anonymous browsing data and
named-contact marketing PII. An address and a template id are inside that cap.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** the `send_scheduling_confirmation` binding
and its declarations, `_send_approved` and the closed-over template id, the two refusals, the
request body, the constant `sent: True`, the `scheduling_confirmation` subject and html
verbatim from `templates.py`, and the absence of any `{{...}}` in all six approved bodies —
counted in this repository, not taken on report.

**Derived in this repository, and labelled as derived rather than measured:** that no Reply-To
can be set on this path. Two independent enumerations of `sendEmailSchema` exist here — shared
rule 7f and the `EMAILS_SEND` comment in `adapters/funnelforge/upstream.py` — and neither
contains such a field. With no Reply-To, a reply addresses the From, which shared rule 7b
measured as `FunnelForge <hello@funnelforge.ai>`. **P-16b did not probe a running
FunnelForge** and this is read out of the schema, exactly as `docs/forge-adapter.md` trap #4
warns is weaker than a call.

**Inherited, measured by P-16 on 9 September 2026:** the empty `RESEND_API_KEY` and the
`EmailSender` startup log, the 429 body and headers, and the absent tenant credential.
Transcripts in the shared rules.

**Inherited from `funnelforge-schedule-blueprint-call.md`:** the unconditional
`sendAppointmentConfirmationEmail` on the booking route, the null `meetingUrl`, the absent
`calendarUrl`, and the `HH:mm` string with no timezone anywhere on the path.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** Part 2.1 step 4 and §6.5
(the client has paid before the call), Part 5 (the Blueprint call is Burkham's first human
touch), and §4.5 (the template, its scope, and the two-founder gate).

**From `packs/compliance-library/burkham-wickmont.yaml`:** the three-part test in
`outbound-contact-boundary-v1`, and the deliverable-promise rule and the no-safe-harbour
statement in `own-claims-and-pricing-v1`. **Both entries are committed and readable**, which
corrects shared rule 10's closing paragraph — see B38.

## OPEN

**Which confirmation should exist.** §1. The reviewed one is the duplicate, the unreviewed one
is welded to the write, and the §4.5 decision has not been made. Today neither arrives, which
is the only reason nobody has had to make it.

**Whether a send module should be able to assert an appointment it cannot see.** This module
will say *"Your Blueprint call is confirmed"* to any address, at any time, with no booking
behind it. Nothing in the design prevents it and nothing in the response would reveal it. That
is a property of the six-modules-one-template architecture rather than a defect in this
binding, and it is recorded here because this is the module where it is most visible.

**Where a client's reply goes.** `hello@funnelforge.ai` is not Burkham's mailbox and nothing in
The Office watches it. Whether that address is monitored at all is not knowable from this
repository. B38.
