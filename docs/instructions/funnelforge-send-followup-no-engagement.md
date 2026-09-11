# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `send_followup_no_engagement`
**Endpoint:** `POST /api/emails/send` (via the adapter's `POST /send_followup_no_engagement`)
**Template:** `followup_no_engagement` — closed over, not a parameter
**Version:** 1.0 — drafted 10 September 2026 by P-16b, against `adapters/funnelforge/` at
`ac6475c`
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first, and
`funnelforge-send-intake-acknowledgment.md` second — the request shape, the two refusals, the
adapter failure table and the retry rule are identical here and are not repeated. **This manual
covers the occasion, the recipient, the approved copy and the compliance entries that copy
touches.**

**One sentence separates this module from the other five sends, and everything below follows
from it:**

> **It is the only approved send that answers no act of the recipient's.**

An acknowledgment answers a form. A confirmation answers a booking. A cover note answers a
purchase. A partner briefing answers a standing distribution somebody joined. **This one is
sent because the recipient did nothing**, and *"the recipient did nothing"* is not an initiating
action. It is Burkham initiating contact into silence, which is the exact territory
`compliance/outbound-contact-boundary-v1` exists to govern — and it is the only one of the six
where that entry's three-part test does real work rather than being satisfied on arrival. §8.

**And its second sentence makes a promise about future silence that nothing in this stack can
keep.** §2.

## 1. WHAT IT DOES

Sends one fixed email to one named person: the post-Blueprint no-engagement follow-up.

Subject: *"Following up on your Blueprint"*. Body, in full:

> We wanted to check in on the Blueprint we sent through. There is no obligation either way -
> if the timing is wrong, say so and we will leave it there.

One paragraph. It is the shortest of the six client-facing bodies and the most carefully
written: no ask, no offer, no price, no deadline, and an explicit release.

**Who receives it.** A client who paid $497 or $997 for the Funding Readiness Score Blueprint,
sat the 60-minute call, received the deliverable, and **has not signed an engagement.**
`docs/reference/burkham-wickmont-marketing-plan-intake.md` Part 6 puts that transition at 3–30
days with a 60-day fee-credit window behind it, and names the reasons it stalls: *"Client
shopping other firms; fee objection; timing objection; found a bank yes elsewhere."*

**What that recipient believes when this arrives.** That is the sentence that makes this module
teachable, and it has two halves that pull in opposite directions.

**They are a paying customer, not a lead**, and they know it. They bought something, they got
it, and they have not decided. The copy is written for exactly that person: it treats the
silence as a decision that is theirs to make, and offers to stop.

**And they are being contacted about a purchase they have finished.** From their side, the
transaction is complete. Whatever comes next is Burkham asking for something. **So the release
in the second clause is the part they will read**, and it is the part that has to be true —
*"if the timing is wrong, say so and we will leave it there"* is a promise about what Burkham
will do next, made to somebody who has already paid and owes nothing.

**Nothing in this stack can keep it.** §2, and it is the most consequential thing in this
manual.

**One refusal pair and one required state**, exactly as the canonical manual sets out. Nothing
about them is different here.

## 2. WHAT IT DOES NOT DO

### It cannot honour "we will leave it there"

**The promise is a commitment to stop contacting.** Four separate absences defeat it, and they
are cumulative rather than alternatives.

**The reply does not reach Burkham.** The adapter sends no `from`, so the envelope is
`FunnelForge <hello@funnelforge.ai>` (shared rule 7b, measured), and no Reply-To can be set —
the two enumerations of `sendEmailSchema` in this repository, shared rule 7f and the
`EMAILS_SEND` comment in `adapters/funnelforge/upstream.py`, contain no such field. **So the
client says so, and says it to FunnelForge.** `docs/blocking.md` B38.

**There is no unsubscribe link in the message.** §6.5 of the marketing-plan intake states the
removal mechanism plainly — *"Unsubscribe link in every marketing email (one-click)"* — and the
approved html for this template, like all six, **contains no link of any kind.** Count it in
`adapters/funnelforge/templates.py`: there is not one `<a>` element in the inventory. The
adapter supplies no `preheader` and no list-unsubscribe. **The single stated one-click route out
is absent from the one send of the six that most plainly needs it.**

**Nothing consults a suppression list before sending.** Shared rule 7c and the canonical manual
§2: this path checks no opt-out surface, no prior-send record, no bounce history and no
do-not-contact preference. FunnelForge has an opt-out surface; the send route does not look at
it.

**And nothing records that the client asked.** Nothing is written in FunnelForge on this path
at all (shared rule 7c) — no `EmailQueue` row, no `EmailEvent` row. **So a client who does
reach somebody and says "leave it there" leaves no mark this Forge can ever read**, and the
next quarter's Capital Command Brief cover, or a second follow-up, has nothing to check against.

**Put together: the message offers a release, misdirects the reply that would claim it, omits
the one-click alternative, consults nothing before sending and records nothing after.** That is
not four small gaps. It is a written promise with no mechanism behind it, made in Burkham's
name, to a customer, in the one message of the six that is not transactional.

### It does not know that a Blueprint was sent

*"the Blueprint we sent through."* The module has no view of whether one was.

**And there is a specific reason to doubt it**: `send_deliverable_cover` cannot attach a
Blueprint (shared rule 7f), so a client whose deliverable went out through the approved path
received a cover note and no document. **This follow-up then asks them to check in on something
they may never have received.** An agent that sends this without establishing that the client
actually holds their Blueprint has compounded one failure with a second that reads as
indifference.

### The rest

**It does not tell you whether an email was sent.** `sent: true` is a constant. Shared rule 1.
Read `upstream.status`.

**It does not know how many times it has been sent.** Nothing is written (shared rule 7c) and
there is no idempotency key (shared rule 8). **So "a follow-up" can become a sequence and
nothing on either side counts.** This is the module where that matters most: the same message
sent three times to somebody who asked to be left alone is precisely the erosion
`compliance/outbound-contact-boundary-v1` names — *"'Just a few warm calls to the referral
list' is how this boundary erodes, and it erodes without anyone deciding to cross it."*

**It does not carry the fee-credit window.** Part 6 records a 60-day credit toward Buildout or
Placement. **The copy does not mention it and cannot** — no merge field, `context` inert
(shared rule 7a). An agent must not tell the client the window is open, because the message did
not, and because `own-claims-and-pricing-v1` puts engagement-specific pricing behind the fee
exhibit.

**It does not personalise, does not send from Burkham, does not record anything in FunnelForge,
and does not resolve a template.** Shared rules 7a, 7b, 7c and 6.

## 3. WHAT EACH INPUT MEANS

Identical to `funnelforge-send-intake-acknowledgment.md` §3 — `recipient_email` and
`compliance_state` required, `recipient_first_name` and `context` accepted and inert,
`template_id` read by nothing. Three notes are specific to this module.

**There is no input for how long it has been, how many follow-ups have gone, or whether the
client asked to be left alone.** All three are facts an agent must establish before calling and
none of them is a field. **The module will send this on the first day and on the fifth attempt
with the identical call**, and the response will be identical too.

**`context` will be reached for here to soften the ask** — a name, a date, a reference to what
the Blueprint recommended. It changes nothing (shared rule 7a). The client receives the same
one paragraph. **An agent that fills it and then reports having referred to the client's
findings has reported a property of a message no recipient will see.**

**`compliance_state` is §3.3's categorical state for this message and it is doing more work here
than on any other send.** On the transactional five, a `pass` clears copy that answers something
the recipient did. Here it is the only place anybody asks whether contacting this person at all
is appropriate — whether they have already declined, already asked to be left, or already had
three of these. **The state carries that judgement and the agent does not.** Composing it, or
supplying `"pass"` to clear a `COMPLIANCE_STATE_ABSENT`, defeats the only control that stands
between a customer and an unbounded follow-up sequence.

## 4. THE CORRECT SEQUENCE

1. **Establish that the client actually received their Blueprint**, not merely that
   `send_deliverable_cover` returned a 200. §2. If they did not, the premise of the message is
   false and the follow-up is not the right act.
2. **Establish whether this person has already been followed up, and how often.** Not from this
   module — nothing here records or reads it. If nobody can answer, that is the answer: it is
   not known, and it goes in the report rather than being assumed to be zero.
3. **Establish whether they have asked not to be contacted**, by any route — a reply, a call, a
   remark on the Blueprint call, a `privacy@burkhamwickmont.com` request. This path consults
   none of them. **A standing do-not-contact instruction has legal force and nothing overrides
   it**; it is held where a human can see it, not where this module can.
4. **Obtain the categorical compliance state** from the process that produces it. Do not compose
   it. §3.
5. **Call once**, with `recipient_email` and `compliance_state`.
6. **Read `upstream.status`.** Not `sent`. Shared rule 1.
7. **Report the send, and report that the client has no working way to opt out of it.** §2. A
   `200` here means a provider accepted a message that invites a reply which does not reach
   Burkham and carries no unsubscribe link.
8. **Record, outside FunnelForge, that this client has now had one.** Nothing else will. This is
   the step that makes step 2 possible for whoever comes next, and skipping it is how a single
   follow-up becomes a sequence nobody authorised.
9. **Do not call again.** Shared rules 8 and 9; the 429 exception is in §6.

**Steps 2, 3 and 8 are the ones this module adds, and all three are about a fact the module
cannot hold.** The other sends fail by misreporting what happened. This one fails by repeating,
and it repeats because the count lives nowhere.

## 5. WHAT FAILURE LOOKS LIKE

**Both tables in `funnelforge-send-intake-acknowledgment.md` §5 apply unchanged.** Same route,
same codes, same bodies. Two things about what they mean here are different.

**`422 COMPLIANCE_STATE_NOT_PASS` is the refusal to expect on this module**, where on the
transactional five it is an edge case. This is the send whose appropriateness is genuinely in
question every time, so a state that is not `pass` is the control working rather than an
obstacle. **It goes back to whoever produced the state, unchanged, and it is not re-attempted
with a different value.**

**A `200` says a commercial message reached a provider and nothing about whether it should
have.** Every other status in both tables is about the mechanics. The judgement this module
actually turns on — has this person been contacted enough, and did they ask not to be — has no
status code anywhere, produces no refusal, and will never appear in a response body. **It is
carried entirely by `compliance_state` and by whoever set it.**

## 6. RETRY VS ESCALATE

**On a timeout: stop and escalate. Do not retry. Do not check first.** Shared rule 9, and here
the asymmetry is not the usual one.

**A duplicate follow-up is worse than a duplicate transactional message, and it is worse in
kind.** A second acknowledgment is clumsy. **A second unsolicited check-in on a purchase the
customer has finished, after the first one offered to leave them alone, contradicts the message
itself.** The client is now being chased by a firm that told them in writing it would stop if
asked — and the reply by which they would have asked went to `hello@funnelforge.ai`.

**So the escalation on a timeout is not "did this send".** It is: *this client's follow-up is in
an unknown state, nobody may send another until a person has established whether the first
arrived, and there is no query that establishes it.* Hand over the name.

**A 429 is a wait, not a retry.** Refused before the route ran; nothing was sent. Honour
`retryAfter` from the body, and read shared rule 4c — the bucket is shared, and a refusal here
is not evidence about this agent's pacing.

**A 500 is an escalation about FunnelForge's configuration**, to whoever operates the
deployment, and the report says the follow-up was **not** sent. **Do not queue it for a retry
in an hour**: a missing provider variable does not clear on its own, and a follow-up that
arrives late is not the same message as one that arrives on time.

**A client's request to be left alone is an escalation, immediately, and it goes to a person.**
It cannot be honoured by this module, cannot be recorded by it, and cannot be checked by it. It
goes to whoever runs Compliance & Evidence, which §6.5 names as the department that executes
removals — with the client's address, the request as they worded it, and the fact that nothing
in FunnelForge now holds it.

## 7. NEVER

All of `funnelforge-send-intake-acknowledgment.md` §7 applies. Nine more are this module's.

**Never send this to somebody who has asked not to be contacted.** The module will accept the
call. Nothing between the agent and the provider will refuse it. **The check exists nowhere
except before the call.**

**Never report that the client can opt out of this message.** There is no unsubscribe link in
it and the reply does not reach Burkham. §2.

**Never treat the copy's release as a mechanism.** *"say so and we will leave it there"* is a
sentence, not a suppression list. An agent that reports the client as having been offered a way
out has described the words rather than the system.

**Never send a second one without establishing what happened to the first.** Nothing records
it, which is the reason to establish it rather than the reason to skip it.

**Never send this as a sequence, a cadence, a drip or a nudge series.** §4.5 approved one
template for one occasion. Nothing in the module, the adapter or FunnelForge caps the count,
and the absence of a cap is not permission.

**Never characterise this as an offer, a reminder of an offer, or a last chance.** The copy
makes no offer, states no deadline and mentions no credit window. Adding any of those is a
claim about cost or outcome the agent has composed.

**Never tell the client the fee-credit window is still open.** §2. The message does not say it,
`own-claims-and-pricing-v1` puts engagement-specific pricing behind the fee exhibit, and the
agent has no view of the window.

**Never ask what they decided, or report their silence as a decision.** The copy asks nothing.
Silence after this message is silence, and reporting it as a declined engagement records an
outcome nobody stated.

**Never send this to somebody whose Blueprint did not actually reach them.** §2. *"the Blueprint
we sent through"* is the premise, and shared rule 7f is a standing reason to check it.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR, runtime flag
`outbound_contact_boundary_required`) — *"Any Burkham-initiated contact with an individual, any
channel."* **The governing entry, and this is the one module of the six where working through
its three-part test changes what an agent does.**

The entry is categorical: **NO OUTBOUND CONTACT WITHOUT ALL THREE.** Applied here:

- **A — the relationship exists.** Satisfied, and by the strongest form the entry names. The
  recipient bought the Blueprint; the entry accepts *"an active engagement, or a former client
  inside an 18-month lookback"*, and a Blueprint client is inside it. **The lookback is a
  boundary and this module cannot see it.** Part 7 retains Blueprint-paid non-client PII for 24
  months; the entry's contact permission runs 18. **There is a six-month band in which the
  address is still held and contact is no longer authorised**, and nothing on this path
  distinguishes it. That is the check an agent must make before calling, and it is made from a
  date nobody supplies to this module.
- **B — the channel is authorised.** Satisfied. They gave the address at intake and email is
  what they gave.
- **C — the purpose matches the reason.** Satisfied for *this* message and nothing beyond it.
  The entry's example is the case: *"A Blueprint client may be contacted about their Blueprint,
  not cross-sold a partner's product."* **The approved copy is about their Blueprint and about
  nothing else, and the agent cannot add to it (shared rule 7a) — that is the control.** What
  the agent *can* do is misdescribe the send afterwards, and reporting this as outreach about
  Buildout or Placement claims a purpose the initiating action never authorised.

**The entry's escalation trigger 4 is written for what this message invites**, and it does not
work here: *"When the recipient indicates they did not expect the contact — 'how did you get my
information', 'I never signed up', 'take me off your list'. End the call, update the record."*
**There is no record to update on this path** (shared rule 7c), and the indication arrives at a
mailbox that is not Burkham's. §2.

**And the entry reaches email explicitly.** Its own applicability note says it is *"Broader than
TSR by design. TSR reaches telephone contact; CAN-SPAM reaches email; UDAAP reaches any
commercial contact. Rather than run three tests, one test governs all outbound channels."* Its
citation names 15 U.S.C. § 7701 et seq. **So the missing unsubscribe link is inside this entry's
scope, not outside it**, and §6.5's *"unsubscribe link in every marketing email"* is the firm's
own stated mechanism for the removal CAN-SPAM's ten-business-day SLA runs against.

**Whether this send is a commercial message or a transactional one is the question underneath
all of that, and nobody has answered it.** The other five answer an act the recipient took;
this one does not. **It is the one of the six where the answer is not obvious, and it is the one
with no unsubscribe link.** Recorded as OPEN rather than decided — it is a §4.5 and Compliance
Review Board question, not an agent's and not this manual's.

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT, `own_claims_discipline_required`) —
*"Anything Burkham says about its own service, results or pricing."* **The copy is unusually
clean under this entry and it is worth saying why**, because the discipline is instructive. It
states no figure, makes no comparison, offers no likelihood, and — under the entry's
classification rule, *does the statement shift what this reader expects about their own result*
— it says nothing about the reader's outcome at all. *"There is no obligation either way"* is a
statement about Burkham's own terms and it is true.

**The exposure is not in the copy. It is in the promise the copy makes and the stack breaks.**
The entry records that there is **no safe harbour** — the standard is whether a reasonable
consumer would be misled, and no disclosure rescues a claim that does. *"say so and we will
leave it there"*, said by a firm with no suppression check, no working reply path and no record
of the request, is a claim about Burkham's own conduct. §2. **A §4.5 matter, not an agent's**,
and the agent's obligation is the narrow one in §7: never describe the release as a mechanism.

**`compliance/client-interest-standard-v1`** (UDAAP, `client_interest_standard_required`) —
*"Any client-facing claim about approval, cost or outcome."* The approved copy makes none. The
entry is named because this is the send at which somebody would most want one added — the
client is deciding, and a sentence about what engaging would get them is the obvious thing to
reach for. **The agent cannot add it (shared rule 7a) and must not say it around the send
either.**

**`compliance/consumer-privacy-rights-v1`** (CCPA; STATE_PRIVACY_COMPREHENSIVE) — the recipient
is a Blueprint-paid non-client with PII retained 24 months (Part 7) and full access, deletion
and correction rights. **§6.5's removal mechanism is four routes wide and this module touches
none of them**, and its deletion SLA is 45 days. The module writes nothing, so it adds no record
to answer a request from — and, more to the point here, **no record that a request was made.**

**No FCRA entry and no GLBA entry apply.** §6.3 caps FunnelForge at anonymous browsing data and
named-contact marketing PII. This module handles an address.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** the `send_followup_no_engagement` binding
and its declarations, `_send_approved` and the closed-over template id, the two refusals, the
request body, the constant `sent: True`, the `followup_no_engagement` subject and html verbatim
from `templates.py`, and **the absence of any `<a>` element or merge field in any of the seven
inventory entries** — counted in this repository, not taken on report.

**Derived in this repository, and labelled as derived rather than measured:** that no Reply-To
can be set on this path. Two independent enumerations of `sendEmailSchema` exist here — shared
rule 7f and the `EMAILS_SEND` comment in `adapters/funnelforge/upstream.py` — and neither
contains such a field. **P-16b did not probe a running FunnelForge**; `docs/forge-adapter.md`
trap #4 is the standing note about what a schema reading is worth against a call.

**Inherited, measured by P-16 on 9 September 2026:** the empty `RESEND_API_KEY` and the
`EmailSender` startup log, the 429 body and headers, the `leadId`-conditional `EmailEvent`
write, and the absent tenant credential. Transcripts in the shared rules.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** Part 6's stage table and
its stall reasons (3–30 days, the 60-day credit window, shopping / fee / timing / a bank yes),
Part 7's retention schedule for Blueprint-paid non-clients (24 months), §6.5 (the four removal
routes, the one-click unsubscribe in every marketing email, the CAN-SPAM and CCPA SLAs, and
Compliance & Evidence as the department that executes removals), and §4.5 (the template, its
scope and the two-founder gate).

**From `packs/compliance-library/burkham-wickmont.yaml`:** the three-part test, the 18-month
lookback, escalation trigger 4, the erosion note and the CAN-SPAM citation in
`outbound-contact-boundary-v1`; the classification rule and the no-safe-harbour statement in
`own-claims-and-pricing-v1`. **Both entries are committed and readable**, which corrects shared
rule 10's closing paragraph — see `docs/blocking.md` B38.

## OPEN

**Whether this send is commercial or transactional, and therefore whether it needs an
unsubscribe link.** §8. It is the only one of the six that answers no act of the recipient's and
the only one where the question is genuinely open. **It is also the one with no link.** A §4.5
and Compliance Review Board question; recorded rather than answered.

**Nothing bounds how many follow-ups a client may receive.** Not the module, not the adapter,
not FunnelForge, and not The Office. §4 steps 2 and 8 push the count into a human's records
because there is nowhere else to put it. **Whether an autonomous send with no cap and no memory
should be grantable at all is the question this module raises**, and V31's refusal (shared rule
8) currently prevents it for an unrelated reason.

**The six-month band between the 18-month contact lookback and the 24-month retention window.**
§8. The address is still held and contact is no longer authorised, and no field, refusal or
record on this path marks the boundary. Recorded because the two numbers come from two
documents and nobody has put them side by side before.

**Where a client's "leave it there" goes.** `hello@funnelforge.ai`, which is not Burkham's and
is not watched by anything in The Office. `docs/blocking.md` B38.
