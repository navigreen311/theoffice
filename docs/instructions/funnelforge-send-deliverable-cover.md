# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `send_deliverable_cover`
**Endpoint:** `POST /api/emails/send` (via the adapter's `POST /send_deliverable_cover`)
**Template:** `deliverable_cover` — closed over, not a parameter
**Version:** 1.0 — drafted 10 September 2026 by P-16b, against `adapters/funnelforge/` at
`ac6475c`
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first, and
`funnelforge-send-intake-acknowledgment.md` second — the request shape, the two refusals, the
adapter failure table and the retry rule are identical here and are not repeated. **This manual
covers the occasion, the recipient, the approved copy and the compliance entries that copy
touches.**

**Read shared rule 7f before anything else in this file.** This is one of the three approved
templates that promises an attachment the transport has no field for, and on this module the
enclosure is not a supplement to the message — **it is the thing the client paid for.**

**The one-line version:** a client pays $497 or $997 for a written diagnostic, and this module
is the act by which Burkham's own funnel defines that diagnostic as delivered. It delivers a
two-paragraph cover note and no diagnostic.

## 1. WHAT IT DOES

Sends one fixed email to one named person: the Blueprint deliverable cover note.

Subject: *"Your Blueprint is ready"*. Body, in full:

> Your Blueprint is attached. It sets out what we found and what we recommend, in the order we
> would act on it.
>
> Questions are welcome; reply here and they reach the team that wrote it.

That is the entire message.

**Who receives it.** A client who paid for the Funding Readiness Score Blueprint and has since
sat through the 60-minute Blueprint call — Burkham's first and, until this point, only human
contact with them (`docs/reference/burkham-wickmont-marketing-plan-intake.md` Part 5). They are
at the hinge of the engagement: Part 6's stage table defines the transition **Blueprint Paid →
Blueprint Delivered** as *"60-minute Blueprint call completed AND written Blueprint deliverable
sent"*, and the next transition, to Engagement Signed, is what the Blueprint exists to inform.

**What that recipient believes when this arrives.** That the diagnostic they bought is in the
message. Not that it is coming, not that it is being prepared — the subject says ready and the
first three words say attached. **They will open the mail to read it.** And what the Blueprint
routes them to is not a small matter: Part 2.1 step 5, *"Blueprint output routes them to
Buildout, Placement, or refer-out"*, and §6.5, *"Fee schedule exhibit is delivered as part of
the Blueprint deliverable."* **So the missing enclosure is also the missing fee exhibit**, and
that has a consequence beyond disappointment — see §8.

**This is the most consequential false report available on this Forge**, and shared rule 7f
says so in those terms. *"The Blueprint has been sent to the client"* is one sentence away from
any successful call, it is what a person asking about this module wants to hear, and it is not
true.

**One refusal pair and one required state**, exactly as the canonical manual sets out. Nothing
about them is different here.

## 2. WHAT IT DOES NOT DO

### It does not attach the Blueprint

**Shared rule 7f.** There is no attachment field at any layer of this path — not in
`sendEmailSchema`, not in `SendEmailOptions`, not in `sendViaResend`, `sendViaSendGrid`,
`sendViaSES` or `sendViaSMTPBasic`. The string *"attachment"* does not occur, in any case, in
the route, the sender or its types.

**And there is no substitute route.** The copy does not say the Blueprint is linked, available
or ready for download — it says attached. There is no URL field on this path either, so an
agent cannot honour the sentence a different way and must not describe it as having been
honoured a different way.

**What a client receives on a successful send is two paragraphs telling them to read something
that is not there**, from a firm they paid several hundred dollars, at the moment the firm's
own funnel records their deliverable as delivered.

**This is the same defect `distribute_referrer_briefing` carries and it is not equally severe.**
There the enclosure is goodwill intelligence to a professional audience; here it is the
purchased artifact, and its absence is a failure to deliver a paid service rather than a
missing courtesy. Both are recorded in `docs/blocking.md` B33 finding 3, and the decision that
retires them is a §4.5 decision — the copy changes and returns through the two-founder gate,
the transport grows an attachment path, or these templates stop being autonomous sends.
**None of the three is an agent's to make, and none of them is this manual's.**

### It does not give the client a way to reach the team that wrote it

*"Questions are welcome; reply here and they reach the team that wrote it."* They do not.

**The adapter sends no `from`**, so the envelope is `FunnelForge <hello@funnelforge.ai>`
(shared rule 7b, measured), and **no Reply-To can be set**: the two enumerations of
`sendEmailSchema` in this repository — shared rule 7f and the `EMAILS_SEND` comment in
`adapters/funnelforge/upstream.py` — contain no such field, and with no Reply-To a reply
addresses the From.

**So a client's questions about their Blueprint go to `hello@funnelforge.ai`**, which is not
Burkham's mailbox, is not the team that wrote the Blueprint, and is not watched by anything in
The Office.

**The sentence is doing real work in the copy and that is why it matters.** A cover note for a
diagnostic that routes a client toward a paid engagement is offering the one channel by which
the client can push back, ask what a finding means, or say they disagree. `docs/blocking.md`
B38 records this across the three templates that say *"reply"*; here the reply is the client's
only stated route to a human after the only human conversation they have had.

### The rest

**It does not tell you whether an email was sent.** `sent: true` is a constant. Shared rule 1.
Read `upstream.status`.

**It does not produce, hold, name, version or see the Blueprint.** The module takes an email
address and a compliance state. It has no view of whether a Blueprint exists, who wrote it,
whether it is finished, or whether it is the right client's. **A correct-looking call announces
a document the module has never encountered.**

**It does not deliver the fee schedule exhibit.** §6.5 places the exhibit inside the Blueprint
deliverable, and the deliverable is the thing that is not attached. §8.

**It does not carry a decline-to-engage explanation, and cannot.** Part 6's enforcement point 2
is explicit: where the Blueprint call surfaces a disqualifier, *"Blueprint deliverable is still
sent (client paid for it), with a clear explanation of why engagement is not offered and a
referral-out where appropriate."* **This template contains no such explanation and no field can
add one** — the approved copy has no merge field and `context` changes nothing (shared rule 7a).
So in the decline-to-engage case this module is the wrong vehicle, and using it produces a
warm two-paragraph note about recommendations *"in the order we would act on it"* to somebody
Burkham has decided not to act with.

**It does not record delivery for the evidence vault.** Part 7's retention rules keep the
Blueprint deliverable in the Compliance Evidence Vault per Pack module 7.1, including for
Blueprint-paid non-clients. **This module writes nothing anywhere** (shared rule 7c), so a
successful send is not evidence that a deliverable reached anybody, and the vault is filled by
some other act.

**It does not advance a stage.** Nothing here updates a funnel stage, a Console record or a
CRM. Part 6's *Blueprint Delivered* transition is a definition somebody applies, not a state
this module sets.

**It does not know whether it has already sent.** Shared rule 8. A client can be sent this
twice and neither side can discover the first.

## 3. WHAT EACH INPUT MEANS

Identical to `funnelforge-send-intake-acknowledgment.md` §3 — `recipient_email` and
`compliance_state` required, `recipient_first_name` and `context` accepted and inert,
`template_id` read by nothing. Three notes are specific to this module.

**There is no input for the Blueprint.** No file, no path, no id, no URL, no title, no version.
That is not an omission in the payload — it is the shape of the whole path, and it is why §2 is
a property of the design rather than a bug in a call. **An agent looking for where to put the
document has not misread the schema; there is nowhere.**

**`context` is where a document reference will be attempted, and it does nothing.** Shared rule
7a: `context` arrives as `to.data` and is substituted only into `{{key}}` merge fields, of
which the approved copy has none. An agent that puts a link, a filename or a version in
`context` has produced the identical email and may then report the Blueprint as referenced. It
was not.

**`compliance_state` is §3.3's state for *this message*, not for the Blueprint.** The Blueprint
is a written diagnostic containing findings and recommendations, and whatever review it went
through is its own. A `pass` on the cover note is not clearance of the document's contents, and
an agent must not read it as one — particularly here, where the document the state does not
cover is the entire substance of the communication.

## 4. THE CORRECT SEQUENCE

1. **Establish that the Blueprint exists and is finished**, from a person or a system that can
   see it. The module cannot and will send the cover regardless.
2. **Establish how the client is actually going to receive it**, before sending anything. This
   module will not deliver it. If nobody has answered that question, the cover note must not go
   out, because it starts a clock on a document that has no route to the client.
3. **Establish whether this is a decline-to-engage delivery.** §2. If it is, this template is
   the wrong one and no field on it can carry the explanation Part 6 requires.
4. **Obtain the categorical compliance state** for the message from the process that produces
   it. Do not compose it, and do not treat it as covering the Blueprint.
5. **Call once**, with `recipient_email` and `compliance_state`.
6. **Read `upstream.status`.** Not `sent`. Shared rule 1.
7. **Report the send and the absent enclosure in the same sentence.** A `200` means a provider
   accepted a cover note. **It does not mean the Blueprint was sent, delivered, provided,
   released or made available**, and every one of those words is available to an agent that
   stops at step 6.
8. **Do not call again.** Shared rules 8 and 9; the 429 exception is in §6.

**Step 2 is the step this module adds and it comes before the call, not after it.** The other
sends can be reported honestly after the fact. This one cannot be made honest after the fact:
once the client has read *"Your Blueprint is attached"*, the question of how they get it is
already live and already answered wrongly. **The honest moment to say a Blueprint cannot be
attached is before the client is told it was.**

## 5. WHAT FAILURE LOOKS LIKE

**Both tables in `funnelforge-send-intake-acknowledgment.md` §5 apply unchanged.** Same route,
same codes, same bodies. Two things about what they mean here are different.

**A `200` is the failure worth naming on this module, and it is not a failure the response
reports.** Every code in both tables describes something that did not happen. The `200`
describes something that did — a cover note was accepted — and it is the answer under which the
client is worst off, because they now believe a document arrived. **The only failure with
consequences on this module is the successful one**, and no status anywhere carries it.

**`500 SEND_FAILED` is, today, the state that protects the client from that**, and it must not
be described as protection. It is a missing environment variable (shared rule 3). It suppresses
an outcome nobody decided to suppress, and the day somebody sets a provider variable the
suppression lifts with no review, no announcement and no change anywhere in this repository.

## 6. RETRY VS ESCALATE

**On a timeout: stop and escalate. Do not retry. Do not check first.** Shared rule 9. Nothing
is written in FunnelForge, so no query can establish whether the first attempt landed.

**The duplicate here is a specific embarrassment.** A client receiving *"Your Blueprint is
attached"* twice, from a firm they paid, with nothing attached either time, is the example
shared rule 9 uses when it explains the asymmetry — *"a client receiving the same Blueprint
cover twice is a visible defect in Burkham's own correspondence"*. It is worse than an unsent
cover, which a person closes in a minute by sending it deliberately.

**A 429 is a wait, not a retry.** Refused before the route ran; nothing was sent. Honour
`retryAfter` from the body, and read shared rule 4c before concluding anything about pacing.

**A 500 is an escalation about FunnelForge's configuration**, named as such, to whoever operates
the deployment, and the report says the cover note was **not** sent. It does not go to a
compliance reviewer and it is not retried in an hour.

**The attachment problem is not an escalation and it is not a retry — it is a refusal to
proceed.** If a person asks for the Blueprint to go out and the agent knows nothing can be
attached, **it says so before sending**, to the person who asked. That is the whole of the
agent's role here. The decision belongs to whoever owns the §4.5 template review, and an agent
that sends first and explains afterwards has converted a decision somebody could have made into
a client who has already been told.

## 7. NEVER

All of `funnelforge-send-intake-acknowledgment.md` §7 applies. Eight more are this module's.

**Never say the Blueprint was sent, delivered, provided, released, shared or made available.**
Shared rule 7f. A cover note was accepted by a provider. The document was not attached, because
it could not have been.

**Never report the deliverable stage as reached.** Part 6 defines *Blueprint Delivered* as the
call completed **and the written deliverable sent**. A `200` on this module satisfies neither
half of that, and an agent that reports the stage has moved a client forward in a funnel on the
strength of an email that contained nothing.

**Never describe, summarise, quantify or preview what the Blueprint says.** The module has no
access to it. *"It sets out what we found and what we recommend"* is the copy's sentence, not a
statement the agent can extend, and an agent that characterises the findings is composing a
claim about a document it has never read.

**Never tell a client to reply to this message with questions**, and never report that the
client has a channel to the team that wrote the Blueprint. The reply reaches
`hello@funnelforge.ai`. §2.

**Never put a link, a filename, a version or a document reference in `context` and then report
the Blueprint as referenced.** Nothing in `context` reaches the client. Shared rule 7a.

**Never use this template for a decline-to-engage delivery.** §2. It carries none of the
explanation Part 6 requires, and its second sentence — recommendations *"in the order we would
act on it"* — is actively wrong for a client Burkham has declined to act with.

**Never treat a `pass` compliance state on this message as review of the Blueprint.** They are
different artifacts, reviewed by different processes, and only one of them is in front of the
module.

**Never send this before somebody has established how the client actually receives the
document.** §4 step 2. This is the module where sending first and solving afterwards costs the
most, because the client's belief is created by the send itself.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT, `own_claims_discipline_required`) — **the
governing entry for this module**, ahead of the outbound-contact entry that governs the set,
because everything at risk here is content.

**The entry permits precisely what this copy attempts.** *"DELIVERABLE PROMISES ARE PERMITTED.
The Blueprint may promise its own contents: a readiness assessment with named components, in a
stated format, by a stated date. It may not promise a funding outcome, a score movement, or a
time to funding. The client receives an artifact, not a prediction."* **The copy stays inside
that line and does so carefully** — *"what we found and what we recommend"* describes the
artifact's contents; it names no approval, no amount, no timeline and no likelihood. Under the
entry's classification rule — does the statement shift what this reader expects about their own
result — it does not. The §4.5 review that admitted the template is where that was applied, and
**an agent adds nothing to the claim and cannot** (shared rule 7a).

**And then the client receives an artifact only in the sense that the entry's last sentence
promises one.** The permitted claim is permitted because a document follows it. **No document
follows it.** The entry records that there is **no safe harbour** — the standard is whether a
reasonable consumer would be misled, and no disclosure rescues a claim that does. *"Your
Blueprint is attached"*, sent with nothing attached, is the plainest case of that on this
Forge. **The remedy is a §4.5 decision, not an agent's, and the agent's obligation is the
narrow one in §7: never repeat the claim as though it were kept.**

**`compliance/client-interest-standard-v1`** (UDAAP, `client_interest_standard_required`) —
*"Any client-facing claim about approval, cost or outcome."* The approved copy makes none. The
entry is named here rather than waved past because of **where the Blueprint sits**: its output
routes the client to Buildout, Placement or refer-out (Part 2.1 step 5), and the cover note is
the wrapper on that routing. A client asking *"so what does it say I should do"* is asking a
question the agent must not answer from this module, and answering it would be a claim about
their outcome made with nothing behind it.

**The fee exhibit is the sharpest instance and it belongs here.** §6.5 delivers the all-in fee
schedule exhibit **as part of the Blueprint deliverable**, and `own-claims-and-pricing-v1`
draws a hard line across pricing: baseline Blueprint pricing is public and quotable, but
**engagement-specific pricing** — which tier, which success-fee schedule, which credits, which
protective terms — *"requires the all-in fee exhibit presented and signed first"*. **So the
document this module fails to attach is a precondition of the conversation that comes next.**
A client who did not receive the exhibit cannot be quoted an engagement, and an agent that
believes the deliverable went out will believe that gate is behind them. Recorded because it is
the one consequence of the attachment defect that is not merely reputational.

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR, `outbound_contact_boundary_required`) —
*"Any Burkham-initiated contact with an individual, any channel."* The three-part test is
satisfied without difficulty: **A**, an active engagement with an affirmative initiating action
and a payment behind it; **B**, the address the client supplied; **C**, the entry's own example
— *"A Blueprint client may be contacted about their Blueprint"*, and this is that. **What the
test does not license is the next message.** The entry is explicit that a Blueprint client is
not thereby cross-sellable, and the agent could not add a sentence to this one anyway.

**`compliance/facilitator-not-broker-v1`** (STATE_LENDER_LICENSURE, `facilitator_status_required`)
— *"Every engagement, in every state, from intake through placement."* The Blueprint recommends
a path and, for many clients, that path is Placement. **How the deliverable is characterised is
where a facilitator starts sounding like a broker**, and the approved copy does not characterise
it at all — *"what we recommend, in the order we would act on it"* is process, not placement.
The agent's exposure is in what it says *around* the send, and §7 governs that.

**`compliance/estimate-not-offer-v1`** (STATE_COMMERCIAL_FINANCING_DISCLOSURE;
MCA_DISCLOSURE_CA_SB1235) — **named, and the reason is the same one
`funnelforge-distribute-referrer-briefing.md` §8 gives about its own enclosure.** A Blueprint
that assesses readiness and routes toward placement is exactly the artifact that could carry a
number about a lender product to a client in a disclosure state. **It cannot reach anyone
through this module, because it cannot be attached.** **That is not a control and must not be
read as one.** It is a defect that happens to suppress an exposure, and the day somebody adds an
attachment path the exposure arrives with it, ungated and unreviewed. Stated before that change
rather than after.

**`compliance/consumer-privacy-rights-v1`** (CCPA; STATE_PRIVACY_COMPREHENSIVE) — the address is
personal data about an identified person, subject to access and deletion rights. The module
writes nothing, so it adds no record to answer such a request from; The Office's ledger row is
the only one it creates. Part 7's retention schedule for Blueprint-paid non-clients is
discharged elsewhere, by whatever puts the deliverable in the Evidence Vault — **not by this**.

**No FCRA entry and no GLBA entry apply.** §6.3 caps FunnelForge at anonymous browsing data and
named-contact marketing PII. This module handles an address. **The Blueprint itself is a
different matter and it is not on this path**: it is a diagnostic over the eight components,
built from data the client authorised elsewhere, and nothing about it passes through
FunnelForge — which is the architecture working, not a gap.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** the `send_deliverable_cover` binding and its
declarations, `_send_approved` and the closed-over template id, the two refusals, the request
body, the constant `sent: True`, and the `deliverable_cover` subject and html verbatim from
`templates.py`.

**Derived in this repository, and labelled as derived rather than measured:** that no Reply-To
can be set on this path. Two independent enumerations of `sendEmailSchema` exist here — shared
rule 7f and the `EMAILS_SEND` comment in `adapters/funnelforge/upstream.py` — and neither
contains such a field. **P-16b did not probe a running FunnelForge**; `docs/forge-adapter.md`
trap #4 is the standing note about what that is worth.

**Inherited, measured by P-16 on 9 September 2026:** the absence of any attachment field in
`sendEmailSchema`, `SendEmailOptions` and every provider call; the empty `RESEND_API_KEY` and
the `EmailSender` startup log; the 429 body and headers. Transcripts in the shared rules.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** Part 2.1 step 5 (what the
Blueprint output routes to), Part 5 (the Blueprint call as first human touch), Part 6's stage
table (the *Blueprint Delivered* definition) and its enforcement point 2 (decline-to-engage),
§6.5 (the fee schedule exhibit inside the deliverable), Part 7 (Evidence Vault retention for
Blueprint-paid non-clients), and §4.5 (the template, its scope and the two-founder gate).

**From `packs/compliance-library/burkham-wickmont.yaml`:** the deliverable-promise rule, the
classification rule, the no-safe-harbour statement and the two-tier pricing rule in
`own-claims-and-pricing-v1`; the three-part test in `outbound-contact-boundary-v1`. **Both
entries are committed and readable**, which corrects shared rule 10's closing paragraph — see
`docs/blocking.md` B38.

## OPEN

**Nothing has decided how a client actually receives their Blueprint.** This module is the only
approved autonomous act named for the delivery, and it cannot perform it. Whether the document
travels by a human's mail client, a Console surface, a portal, or a transport FunnelForge grows
later is undecided, and until it is decided **the cover note has no companion**. Recorded as the
question that makes the §4.5 decision urgent rather than tidy.

**Whether an autonomous send whose whole subject is an enclosure should be grantable at all.**
V31 already refuses this module at the only tier that calls (shared rule 8), for an unrelated
reason — `at_most_once` with no idempotency key. **The two refusals point the same way and only
one of them is deliberate.** If the idempotency question is ever solved upstream, this module
becomes grantable while the enclosure question is still open, and nothing in the pipeline would
notice.

**Where a client's questions go.** `hello@funnelforge.ai` is not Burkham's and is not the team
that wrote the Blueprint. Whether it is monitored at all is not knowable from this repository.
`docs/blocking.md` B38.
