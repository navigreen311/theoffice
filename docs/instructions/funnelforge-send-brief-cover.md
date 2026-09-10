# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `send_brief_cover`
**Endpoint:** `POST /api/emails/send` (via the adapter's `POST /send_brief_cover`)
**Template:** `brief_cover` — closed over, not a parameter
**Version:** 1.0 — drafted 10 September 2026 by P-16b, against `adapters/funnelforge/` at
`ac6475c`
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first, and
`funnelforge-send-intake-acknowledgment.md` second — the request shape, the two refusals, the
adapter failure table and the retry rule are identical here and are not repeated. **This manual
covers the occasion, the recipient, the approved copy and the compliance entries that copy
touches.**

**Read shared rule 7f before anything else in this file.** This is the third of the three
approved templates that promises an attachment the transport has no field for, and on this
module the enclosure has a property the other two do not:

> **Burkham has named it in its own answer to "What's your guarantee?"**

`docs/reference/burkham-wickmont-marketing-plan-intake.md` §1.6: *"No guarantee of approval or
dollar amount. What is guaranteed: engagement architecture (Blueprint deliverables, Buildout
deliverables, Placement workflow with written per-app authorization, **ongoing Capital Command
Brief**)."* The Brief is not a courtesy that lapses quietly. **It is one of four things Burkham
tells prospects it does guarantee**, and this module is the approved autonomous act by which it
is supposed to arrive.

**Two other properties make this module unlike the rest of the six, and both compound the
first:** it is the only *recurring* send, and it is a send to a list. §1 and §2.

## 1. WHAT IT DOES

Sends one fixed email to one named person: the Capital Command Brief cover note.

Subject: *"This quarter's Capital Command Brief"*. Body, in full:

> This quarter's Capital Command Brief is attached.
>
> It is written to be read in ten minutes and acted on in one conversation.

That is the entire message. One statement about an enclosure and one about how to read it.

**Who receives it.** A client with an engagement — §3.3 of the marketing-plan intake files this
under *"Post-engagement client comms (Capital Command Brief, etc.)"*, worker-autonomous in a
Pass state, *"templated deliverables against approved format"*. In Part 6's stage vocabulary
that is **Engagement Active** and **Retained** (Stack Management or Advisory), the far end of
the funnel: a client on an ongoing retainer, paying Burkham now, for whom the Brief is part of
what the retainer buys.

**What that recipient believes when this arrives.** Not what a prospect believes, and the
difference is the whole of it. **They are not being persuaded. They are being served.** A
quarterly brief arriving on schedule is the visible form of an ongoing engagement working — it
is, for a Stack Management client between placements, quite possibly the only thing that
arrives that quarter. They open it expecting the document, not a note about one.

**And they have a longer memory than any other recipient on this Forge.** They will get this
next quarter and the quarter after. A cover note with nothing attached is not an isolated
mistake to them; it is the second or third time, and it is happening to something they were
told was guaranteed.

**This is the only send of the six that repeats**, and repetition changes what every other fact
in this manual means. Shared rule 7c — nothing is written — is an inconvenience on a one-off
send. Here it means **nobody can answer whether this client received last quarter's**, and that
question is contractual rather than curious. §2.

**One refusal pair and one required state**, exactly as the canonical manual sets out. Nothing
about them is different here.

## 2. WHAT IT DOES NOT DO

### It does not attach the Brief

**Shared rule 7f.** No attachment field at any layer — not `sendEmailSchema`, not
`SendEmailOptions`, not any provider call. The string *"attachment"* does not occur in the
route, the sender or its types.

**A successful send delivers one sentence saying a document is attached, with no document.**
The route answers 200, the adapter answers `sent: true`, the ledger records a call, and the
client is the first to notice.

**And here the missing enclosure lands against a stated guarantee.** §1.6's answer to *"What's
your guarantee?"* names the ongoing Capital Command Brief as one of four things Burkham
guarantees. **A quarter in which the cover goes out and the Brief does not is a documented
failure of something the firm put in writing to win the engagement**, and
`compliance/own-claims-and-pricing-v1` records that there is **no safe harbour** — no disclosure
rescues a claim a reasonable consumer would be misled by. §8.

**The decision that retires this is a §4.5 decision**, exactly as for the other two: the copy
changes and returns through the two-founder gate, the transport grows an attachment path, or
these templates stop being autonomous sends. **None of the three is an agent's, and none is this
manual's.** `docs/blocking.md` B33 finding 3.

### It cannot tell you whether this client got the last one

Nothing is written in FunnelForge on this path (shared rule 7c): no `EmailQueue` row, no
`EmailEvent` row, nothing. **So there is no quarter-by-quarter record of who received the
Brief, on either side.**

**On the other five sends that is a reporting gap. Here it is the record of a promise.** *"Ongoing
Capital Command Brief"* is a commitment over time, and the question it produces — *has this
client had every Brief they were promised* — is answerable only by reading The Office's ledger
rows for this module, one per call, and nobody has built anything that does. Shared rule 5 says
the ledger is the entire per-agent record; it is also, here, the entire record of a contractual
deliverable.

**And nothing prevents a client being skipped.** The module has no view of a list, no view of a
quarter, and no view of who was sent to last time. A client omitted from this quarter's list is
omitted silently, and the omission is invisible on both sides until they ask.

### It does not distribute, and this is a send to a list

**It sends to the one address in `recipient_email`.** A quarterly Brief to the client base is
the caller making one call per client, exactly as `distribute_referrer_briefing` is — and
everything that manual's §4 and §6 say about pacing, per-recipient outcomes and resuming
applies here unchanged. `POST /api/emails/broadcast` exists in FunnelForge and **is not bound to
any module**, deliberately, because a broadcast module would be one grant covering a list
nobody named.

**Read `funnelforge-distribute-referrer-briefing.md` §4 for the loop.** It is not repeated here.
Two differences in what it means:

**The recipients are clients, not partners.** A misaddressed partner briefing reaches somebody
at a bank. **A misaddressed Brief reaches a stranger holding a document about Burkham's view of
the capital market, sent to them as though they were a paying client** — and the address it went
to was supplied by whoever built the list, not by anything the module can check.

**The list is the client base at a moment in time**, and it changes between quarters as
engagements start and end. §8 has the part that matters: an engagement that ended does not stop
the address working.

### The rest

**It does not tell you whether an email was sent.** `sent: true` is a constant. Shared rule 1.
Read `upstream.status`.

**It does not produce, hold, name, version or see the Brief.** It has no view of whether one
exists this quarter, whether it is finished, or whether it is the right quarter's. **A
correct-looking call announces a document the module has never encountered**, and on a recurring
send that includes announcing last quarter's as though it were this quarter's.

**It does not know which quarter it is.** *"This quarter's"* is a fixed string. There is no
date, no period and no merge field in the copy (shared rule 7a; count `templates.py` — zero
occurrences of any `{{...}}`). **A Brief cover sent in error three months late says "this
quarter's" and is wrong, and nothing in the message or the response would show it.**

**It does not check that the recipient still has an engagement.** No lookup, no status, no
gate. §8.

**It does not vary by recipient.** Every client receives the identical two sentences. There is
no per-client version and `context` changes nothing (shared rule 7a).

**It does not know whether it has already sent.** Shared rule 8. Within a quarter, a client can
be sent this twice and neither side can discover the first.

## 3. WHAT EACH INPUT MEANS

Identical to `funnelforge-send-intake-acknowledgment.md` §3 — `recipient_email` and
`compliance_state` required, `recipient_first_name` and `context` accepted and inert,
`template_id` read by nothing. Three notes are specific to this module.

**There is no input for the quarter and no input for the Brief.** Not a period, not a date, not
a document, not a version, not a URL. The copy's *"This quarter's"* is a literal and the agent
cannot make it specific. **An agent looking for where to say which Brief this is has not
misread the schema; there is nowhere.**

**`context` will be reached for to carry the quarter or a document link, and it does nothing.**
Shared rule 7a. The client receives the same two sentences. An agent that fills it and then
reports the Brief as identified or linked has reported a property of a message no recipient will
see.

**`compliance_state` is §3.3's state for this message, and on this module it is a state for a
recurring act rather than a one-off one.** §3.3 pairs the Brief's worker autonomy with its
opposite — *"Human review (Needs Review state) if compliance state slips"* — so the state is the
mechanism by which the quarterly send stops being autonomous. **One state, obtained once, covers
one quarter's identical message and no more.** Carrying last quarter's `pass` forward, because
the copy has not changed, is composing a state; the copy is not what the state is about.

## 4. THE CORRECT SEQUENCE

**For one recipient, the sequence is `funnelforge-send-intake-acknowledgment.md` §4. For the
quarterly run, which is what this module is for, the loop is
`funnelforge-distribute-referrer-briefing.md` §4** — establish the list and that it is current,
one compliance state for the message, one call per recipient paced deliberately, read
`upstream.status` on every call, keep the per-recipient outcome, and report counts rather than
completion. Neither is repeated here. **Four steps are this module's own.**

1. **Establish that this quarter's Brief exists and is the approved one**, from a person or a
   system that can see it. The module cannot, and the copy says *"this quarter's"* regardless.
2. **Establish how the clients actually receive it**, before sending anything. This module will
   not deliver it. If nobody has answered that, the cover must not go out — it starts a clock on
   a document with no route to the client.
3. **Establish that every address on the list still has an engagement.** §8. The module does not
   check and the address does not expire when the engagement does.
4. **Record, outside FunnelForge, which clients were sent to this quarter.** Nothing else will,
   and this is the record that makes *"has this client had every Brief"* answerable next
   quarter. On the referrer briefing this step protects a run; **here it protects a stated
   guarantee**, and it is the same step.

**Step 2 is the one that cannot be repaired afterwards**, and it is the same step
`funnelforge-send-deliverable-cover.md` §4 turns on. Once a client has read *"This quarter's
Capital Command Brief is attached"*, the question of how they get it is already live and already
answered wrongly. **The honest moment to say a Brief cannot be attached is before a quarter's
worth of clients are told it was.**

## 5. WHAT FAILURE LOOKS LIKE

**Both tables in `funnelforge-send-intake-acknowledgment.md` §5 apply unchanged**, and
`funnelforge-distribute-referrer-briefing.md` §5 applies to the run — a 429 is the expected
failure on a loop, a 500 is a failed recipient rather than a partial distribution, and each call
answers only about itself. Two things are specific to this module.

**A `200` is the failure with consequences here, and no status carries it.** Every code in both
tables describes something that did not happen. The `200` describes something that did — a cover
note was accepted — and it is the answer under which the client is worst off, because they now
believe a guaranteed quarterly deliverable arrived. **The only failure that reaches the client is
the successful one.**

**A partial run is a partial quarter, and it does not close.** Twenty-eight of forty clients
sent to is not *"the Brief went out"*; it is twelve engaged clients who did not receive
something they were promised, and — because nothing is written (shared rule 7c) — **the twelve
are identifiable only from the caller's own notes.** If those notes were not kept, the shortfall
is not recoverable at all, and next quarter's run has no way to see that it is now two Briefs
behind for those clients.

## 6. RETRY VS ESCALATE

**On a timeout: stop and escalate. Do not retry. Do not check first.** Shared rule 9. Nothing is
written, so no query can establish whether the first attempt landed.

**Escalate the recipient, not the quarter.** A timeout on one address is one unresolved client;
the rest of the list is unaffected and the run continues with that one named, held and handed to
a person. An agent that abandons the run on one timeout has turned one unknown into a whole
quarter's unsent Briefs — `funnelforge-distribute-referrer-briefing.md` §6 makes the same point
about the same shape.

**A 429 is a wait, and continuing is correct.** Honour `retryAfter` from the body and resume at
the refused recipient — nothing was sent to them, so resuming is not a retry. **Do not restart
the list from the top**, which sends a second copy to everybody already done. Read shared rule
4c: the bucket is shared, so a refusal is not evidence about this agent's pacing.

**A 500 across every recipient is an escalation about FunnelForge, not about the list.** Today
that is the state, and the message names its own cause. **Do not work through the whole client
base collecting identical 500s first — the second one is enough to know.** It goes to whoever
operates the deployment.

**The missing enclosure is a refusal to proceed, not an escalation and not a retry.** If a
person asks for the Brief to go out and the agent knows nothing can be attached, **it says so
before the run**, to the person who asked. The decision belongs to whoever owns the §4.5
template review. Raising it after a quarter's worth of clients have received a cover note for a
guaranteed document is the failure mode worth naming.

## 7. NEVER

All of `funnelforge-send-intake-acknowledgment.md` §7 applies, and
`funnelforge-distribute-referrer-briefing.md` §7's rules about runs — never report a run as
complete without a per-recipient count, never restart from the top. Eight more are this
module's.

**Never say the Brief was sent, delivered, provided, released or made available.** Shared rule
7f. A cover note was accepted by a provider. The document was not attached, because it could not
have been.

**Never report the quarter as served.** *"This quarter's Brief has gone out"* over a run of
accepted cover notes is a statement about a guaranteed deliverable, and it is false in two
independent ways at once: the enclosure was not attached, and the count is not the list.

**Never describe, summarise, quantify or preview what the Brief says.** The module has no access
to it. An agent that characterises Burkham's market view or what it can currently place is
composing a claim about Burkham's own service with nothing behind it — the same rule
`funnelforge-distribute-referrer-briefing.md` §7 applies to the partner briefing, and for the
same reason.

**Never claim a client received a previous quarter's Brief.** Nothing records it. §2. If
somebody asks, the true answer is that no such record exists on either side and that the only
trace is one ledger row per call in The Office.

**Never send this to somebody whose engagement has ended.** The module will accept it and the
address will work. §8.

**Never carry a compliance state forward from a previous quarter because the copy has not
changed.** §3. The state is about sending this message now, to these clients, not about the
words.

**Never put the quarter, a period, a link or a document reference in `context` and then report
the Brief as identified.** Nothing in `context` reaches the client. Shared rule 7a.

**Never send a client two in one quarter, including after an unknown outcome.** Shared rule 8;
nothing can discover the first. A recurring send is the one where a duplicate reads as a system
that has lost track of its own schedule — to a retained client, which is the audience whose
confidence the retainer depends on.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT, `own_claims_discipline_required`) — **the
governing entry for this module**, ahead of the outbound-contact entry that governs the set,
because what is at risk here is a promise Burkham made about its own service.

**The guarantee is the finding.** §1.6 answers *"What's your guarantee?"* by naming four things,
and the ongoing Capital Command Brief is one of them. **This module is the approved autonomous
act by which that guaranteed deliverable reaches a client, and it cannot carry it** (shared rule
7f). The entry's standard is *"whether a reasonable consumer would be misled"*, and it states
that there is **NO SAFE HARBOUR**: *"Unlike TILA or FCRA there is no disclosure that makes a
deceptive claim acceptable."* A cover note asserting an attachment that is not there, for a
document the firm has said it guarantees, is the plainest instance of that on this Forge.

**The copy's second sentence sits on the entry's own dividing line, and it is worth reading
precisely rather than waving through.** *"It is written to be read in ten minutes and acted on
in one conversation."* The entry's classification rule is: **a firm-scale factual claim about
aggregate activity is permitted; a claim that shifts a prospective client's expectation about
their own outcome is not — including when it is true.** *"Written to be read in ten minutes"* is
a property of the artifact and falls squarely inside the entry's permitted deliverable promise —
*"a readiness assessment with named components, in a stated format"*. *"Acted on in one
conversation"* is closer to the line: it is a statement about what this reader will be able to
do. **It is not a banned claim under any of the entry's listed examples** — it names no approval,
no amount, no timeline to funding and no likelihood — **and it is the sentence a reader should
know the §4.5 review had to place.** An agent adds nothing to it and cannot (shared rule 7a);
what it must not do is extend it, and *"one conversation with us"* is the extension available.

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR, `outbound_contact_boundary_required`) —
*"Any Burkham-initiated contact with an individual, any channel."* Applied to a client with a
live engagement, the three-part test is satisfied on all three legs: **A**, an active
engagement; **B**, the address they gave; **C**, contact about the engagement they are in.

**The failure case is the one the module cannot see, and it is specific to a recurring send.**
The entry's part A reads *"an active engagement, or a former client inside an 18-month
lookback"*. **An engagement ends; the address on the list does not.** A client who rolled off
Stack Management stays inside the lookback for eighteen months and then leaves it, and **nothing
on this path marks either boundary** — not the module, not the adapter, not FunnelForge, and not
the list, which is whatever the caller supplied. A quarterly send is precisely the mechanism by
which a former client keeps receiving mail for years after their engagement closed, one quarter
at a time, with nobody deciding to continue it. That is the entry's own erosion note — *"it
erodes without anyone deciding to cross it"* — in its most literal form. **§4 step 3 exists for
this and it is a human's check, not a field.**

**`compliance/client-interest-standard-v1`** (UDAAP, `client_interest_standard_required`) —
*"Any client-facing claim about approval, cost or outcome."* The approved copy makes none, and
the agent cannot add one (shared rule 7a). Named because the audience is retained clients making
continuing decisions about what to place and when, and a sentence about what the Brief means for
their own capital position is the obvious thing to reach for around the send.

**`compliance/estimate-not-offer-v1`** (STATE_COMMERCIAL_FINANCING_DISCLOSURE;
MCA_DISCLOSURE_CA_SB1235) — **named for the reason `funnelforge-distribute-referrer-briefing.md`
§8 names it about its own enclosure, and the reasoning transfers exactly.** A quarterly capital
brief written to be *acted on* is the artifact that would carry a rate, a term or an amount about
a lender product to a client who may be in a disclosure state. **It cannot reach anyone through
this module, because it cannot be attached.** **That is not a control and must not be read as
one.** It is a defect that happens to suppress an exposure, and the day somebody adds an
attachment path the exposure arrives with it, ungated. Stated before that change rather than
after.

**`compliance/facilitator-not-broker-v1`** (STATE_LENDER_LICENSURE, `facilitator_status_required`)
— *"Every engagement, in every state, from intake through placement."* A quarterly brief to
retained clients about what Burkham sees and can place is where a facilitator's standing
description of itself accumulates. The approved copy characterises nothing; **the agent's
exposure is in what it says around the send**, and §7 forbids previewing the contents.

**`compliance/consumer-privacy-rights-v1`** (CCPA; STATE_PRIVACY_COMPREHENSIVE) — the address is
personal data about an identified person, subject to access and deletion rights. The module
writes nothing (shared rule 7c), so it adds no record to answer such a request from — and on a
recurring send that cuts the other way too: **a client who asked to stop receiving the Brief
leaves no mark this path can read**, and the removal is executed by Compliance & Evidence
through the routes §6.5 names, none of which this module touches.

**No FCRA entry and no GLBA entry apply.** §6.3 caps FunnelForge at anonymous browsing data and
named-contact marketing PII. This module handles an address; **the Brief itself never passes
through FunnelForge**, which is the architecture working rather than a gap.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** the `send_brief_cover` binding and its
declarations, `_send_approved` and the closed-over template id, the two refusals, the request
body, the constant `sent: True`, and the `brief_cover` subject and html verbatim from
`templates.py`, including the absence of any merge field in it — counted in this repository, not
taken on report.

**Inherited, measured by P-16 on 9 September 2026:** the absence of any attachment field in
`sendEmailSchema`, `SendEmailOptions` and every provider call; the `broadcast` route's existence
and shape; the empty `RESEND_API_KEY` and the `EmailSender` startup log; the 429 body and
headers; the `leadId`-conditional `EmailEvent` write. Transcripts in the shared rules.
**P-16b did not probe a running FunnelForge**; `docs/forge-adapter.md` trap #4 is the standing
note about what a source reading is worth against a call.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** §1.6 (the four guaranteed
things, including the ongoing Capital Command Brief), §3.3 (post-engagement client comms,
worker-autonomous in Pass and human review when the state slips), §4.5 and §4.6 (the template,
its scope, the two-founder gate, and templated deliverable covers as autonomous sends), Part 6's
stage table (Engagement Active and Retained, and the roll-off into Stack Management), and §6.5
(the removal routes).

**From `packs/compliance-library/burkham-wickmont.yaml`:** the classification rule, the
deliverable-promise rule and the no-safe-harbour statement in `own-claims-and-pricing-v1`; the
three-part test, the 18-month lookback and the erosion note in `outbound-contact-boundary-v1`.
**Both entries are committed and readable**, which corrects shared rule 10's closing paragraph —
see `docs/blocking.md` B38.

## OPEN

**Nothing records that a guaranteed quarterly deliverable was delivered.** §2. *"Ongoing Capital
Command Brief"* is a commitment over time and the only trace of any instance of it is one
ledger row per call in The Office. **Whether a contractual recurring deliverable should be
discharged by a surface that keeps no schedule and no history is a question nobody has asked**,
and it is sharper than the same question about a one-off send.

**Nobody owns the client list on this path.** `funnelforge-distribute-referrer-briefing.md` OPEN
raises this about the partner list; it is the same hole and it is worse here, because the client
list has an entry and an exit condition — an engagement starting and ending — that the address
does not follow. §8.

**When a former client stops receiving the Brief.** The 18-month lookback is a compliance
boundary, the engagement's end is a commercial one, and the quarterly list is neither. Nothing
on this path marks any of the three. Recorded because a recurring send is how the gap between
them becomes years rather than months.

**Whether an autonomous send whose whole subject is an enclosure should be grantable at all.**
The same question `funnelforge-send-deliverable-cover.md` OPEN raises, and V31's refusal (shared
rule 8) currently prevents the grant for an unrelated reason — `at_most_once` with no
idempotency key. **Two refusals pointing the same way, only one of them deliberate.**
