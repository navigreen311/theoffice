# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `distribute_referrer_briefing`
**Endpoint:** `POST /api/emails/send` (via the adapter's `POST /distribute_referrer_briefing`)
**Template:** `referrer_briefing` — closed over, not a parameter
**Version:** 1.0 — drafted 9 September 2026, against `adapters/funnelforge/` at `ac6475c` and
the running FunnelForge stack
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first, and
`funnelforge-send-intake-acknowledgment.md` second — that is the canonical manual for the six
approved sends, and everything it says about the request shape, the two refusals, the adapter
failure table and the retry rule holds here unchanged. **This manual covers only what is
different**, and three things are.

**The three differences, stated before anything else:**

1. **The recipient is not a client.** It is a banker or loan officer on a distribution list,
   who has never engaged Burkham and may never.
2. **The name says "distribute" and the operation sends to one address.** A distribution is
   the caller calling this N times, and N calls is where the rate limit stops being
   theoretical. §4 and §6.
3. **The briefing is described as attached and cannot be attached.** Shared rule 7f.

**This is also the module V31 names.** P-13 measured it: apply the nine registry rows and V31
goes NOT_RUN to FAIL, naming `distribute_referrer_briefing` at `auto_execute` as a mutating
`at_most_once` module. It is first alphabetically among the seven, not worst among them — the
refusal covers all seven equally and is correct for all seven. Shared rule 8.

## 1. WHAT IT DOES

Sends one fixed email to one referring partner: the quarterly briefing cover note.

Subject: *"Quarterly briefing for referring partners"*. Body, in full:

> The quarterly briefing for referring partners is attached, covering what we are seeing in
> the market and what we are able to place.

That is the entire message. One sentence, one claim, one reference to an enclosure.

**Who receives it.** A referring partner on the banker distribution list — SBA preferred
lenders, commercial-bank business banking officers, CDFI loan officers, online-lender
partnerships (`docs/reference/burkham-wickmont-marketing-plan-intake.md` Part 2.2). The
briefing is part of what a declining bank gets back for a handoff, and Part 2.5 is emphatic
about what it is not: **there is no fee, no revenue share, no referral fee, no per-lead fee.**
The briefing is goodwill and intelligence, and it is deliberately not compensation.

## 2. WHAT IT DOES NOT DO

**It does not attach the briefing.** Shared rule 7f, and this is the module where the sentence
and the transport contradict each other most directly, because the enclosure is the entire
purpose of the message. The send path has no attachment field at any layer —
`sendEmailSchema`, `SendEmailOptions`, and every provider call. A successful send delivers one
sentence saying a document is attached, with no document.

**It does not distribute.** It sends to the one address in `recipient_email`. `POST
/api/emails/broadcast` exists in FunnelForge, takes `businessId`, `subject` and `body`, and
**is not bound to any module** — deliberately, because a broadcast module would be one grant
covering a list nobody named. So a quarterly distribution is the caller making one call per
partner, and the module has no view of the list, no view of how many have been done, and no
view of whether it has already sent to this address.

**It does not know the distribution list.** The list is not in FunnelForge on this path and is
not an input. Whoever calls supplies the addresses.

**It does not report progress.** Nothing accumulates. Twenty-eight successful calls and
twenty-eight failed ones are indistinguishable from the module's side, because nothing is
written (shared rule 7c) and each call answers only about itself.

**It does not vary by recipient.** Every partner receives the identical sentence. There is no
per-institution version, no merge field, and `context` changes nothing (shared rule 7a). The
*"8-page tailored version"* Part 2.4 describes — the Decline-Flow Banker-Side Briefing — is a
different artifact and this module does not produce, attach or reference it.

**It does not tell you whether an email was sent.** `sent: true` is a constant. Shared rule 1.

**It does not check whether this partner still wants it.** No suppression list, no opt-out
check, no prior-send check. A banker who asked to be removed last quarter receives it again if
their address is passed again.

## 3. WHAT EACH INPUT MEANS

Identical to `send_intake_acknowledgment` §3: `recipient_email` and `compliance_state` are
required, `recipient_first_name` and `context` are accepted and change nothing, `template_id`
is read by nothing. Two notes specific to this module:

**`recipient_email` is a business address at another institution.** That changes nothing
mechanically and everything about the cost of getting it wrong. A misaddressed acknowledgment
reaches a stranger; a misaddressed partner briefing reaches somebody at a bank, from a firm
that bank refers clients to.

**`compliance_state` still means §3.3's categorical state for this message.** It is not a
statement about the briefing document, which this module never sees and cannot send. An agent
must not read a `pass` as clearance for the attachment's contents.

## 4. THE CORRECT SEQUENCE

For one recipient, the sequence is `send_intake_acknowledgment` §4 unchanged. **For a
distribution — which is what this module is for — three more steps sit around it:**

1. **Establish the list, and establish that it is current.** Not from this module. An address
   that was on the list a quarter ago is not evidence it is on the list now.
2. **Obtain one categorical compliance state for the message**, once. It is the same message
   to everybody.
3. **Call once per recipient, and pace deliberately.** Shared rule 4: 3 per second and 30 per
   minute at tier FREE, in a bucket shared with every other agent and every other FunnelForge
   module. **A forty-partner distribution cannot complete in under about eighty seconds even
   with the whole budget**, and the whole budget is not available.
4. **Read `upstream.status` on every single call.** Not on a sample, not on the first.
5. **Keep the per-recipient outcome.** The module writes nothing; if the caller does not hold
   which addresses succeeded, nobody can ever know. This is the step most easily skipped and
   the one that makes step 6 possible.
6. **Report the distribution as what it was: a count of accepted sends, a count of refusals
   with their reasons, and the addresses in each.** Never as "the briefing went out."

**On a 429 mid-distribution: stop, wait `retryAfter`, and resume at the recipient that was
refused.** Nothing was sent to that recipient — the rate-limit hook refuses before the route
runs — so resuming at it is not a retry. **Do not skip forward** past the refused address, and
do not restart the list from the beginning, which would send a second copy to everybody
already done. §6.

## 5. WHAT FAILURE LOOKS LIKE

The tables in `funnelforge-send-intake-acknowledgment.md` §5 apply unchanged. Three things are
different in what they mean here:

**`429 RATE_LIMIT_EXCEEDED` is the expected failure on this module**, where on the others it
is an edge case. It is the only one of the six sends whose normal use is a loop.
`limit: 3, retryAfter: 1` is the per-second burst; `limit: 30` with a larger `retryAfter` is
the per-minute window. Shared rule 4a — one code, two budgets, and the body is the only way to
tell them apart.

**`500 SEND_FAILED` is not a partial distribution — it is a failed recipient.** Each call is
independent. A 500 on the eleventh address says nothing about the ten before it, and the ten
before it say nothing about whether a provider now exists. Today it is every address, because
no provider is configured (shared rule 3).

**A `200` on this module is the most misleading success in the set**, because of 7f. It means
a provider accepted a one-sentence email that says a briefing is attached. It does not mean a
briefing was delivered, and the recipient will notice the difference before anyone at Burkham
does.

## 6. RETRY VS ESCALATE

**On a timeout: stop and escalate. Do not retry.** Shared rule 9, and the reasoning is sharper
here than on a client send. A duplicate acknowledgment is an embarrassment; a duplicate
quarterly briefing to a bank's business banking officer is a firm that cannot keep track of
its own correspondence, sent to the party whose confidence the entire decline-flow loop
depends on.

**Escalate the recipient, not the distribution.** A timeout on one address is one unresolved
address. The remaining addresses are unaffected and the distribution continues — with that one
named, held, and handed to a person. An agent that abandons the whole run on one timeout has
turned one unknown into thirty-nine unsent briefings.

**A 429 is a wait, and it is the one case where continuing is correct.** Honour `retryAfter`
from the body and resume at the refused recipient. Read shared rule 4c before concluding
anything about pacing: the bucket is shared, so a refusal at recipient three does not mean the
pacing is wrong.

**A 500 across every recipient is an escalation about FunnelForge, not about the list.** Today
that is the state, and the message names the cause. It goes to whoever operates the
deployment. Do not work through forty addresses collecting forty identical 500s first — the
second one is enough to know.

**The attachment problem is not an escalation an agent resolves and it is not a reason to
stop.** If a person asks for the briefing to go out and the agent knows nothing can be
attached, the honest act is to say so before sending, not to send and report success. That is
a refusal to proceed, addressed to the person who asked, and it belongs to whoever owns the
§4.5 template review.

## 7. NEVER

All of `funnelforge-send-intake-acknowledgment.md` §7 applies. Seven more are specific to
this module.

**Never say the briefing was sent, delivered, or provided.** Shared rule 7f. A cover sentence
was accepted by a provider. No document was attached, because none can be.

**Never report a distribution as complete without a per-recipient count.** "The quarterly
briefing has gone out" over a run containing eleven 429s is a false statement that nothing
downstream can detect, because nothing is written.

**Never restart a distribution from the top.** Every recipient already reached would receive a
second copy, and there is no way to withdraw one. Resume where it stopped.

**Never characterise the briefing as compensation, consideration, a benefit conferred for
referrals, or anything a referral produced.** Part 2.5 makes no-fee the load-bearing
structural choice — no revenue share, no referral fee, no per-lead fee, at any level — and
describing the briefing as something a partner earns by sending clients is exactly the
characterisation that choice exists to prevent.

**Never send it to somebody who is not on the distribution list**, and never add an address
because it seems like it belongs. The list is a decision made elsewhere.

**Never send it to a client, an applicant or a prospect.** It is written for referring
institutions and says *"what we are able to place"*, which is a statement about Burkham's
capability to a professional audience. To an applicant it reads as a claim about their
prospects.

**Never quantify, summarise or preview what the briefing says.** The module has no access to
the document. An agent that describes the market view or what Burkham can place is composing a
claim about Burkham's own service with nothing behind it.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR) — *"Any Burkham-initiated contact with
an individual, any channel."* A banker is an individual. The entry applies exactly as it does
to a client send, and the shared rules record the open Pack question about propagating its
flag to this Forge.

**`compliance/reg-z-advertising-boundary-v1`** (REG_Z_ADVERTISING, runtime flag
`trigger_term_disclosure_required`) — *"Any content reaching a person who has not engaged
Burkham that states a rate, a payment, a term or a fee."* **This is the entry that separates
this module from the five client sends**, because its recipients are, by definition, people
who have not engaged Burkham.

**The approved sentence states no rate, no payment, no term and no fee, so it stays inside the
entry.** That is a property of the copy and the agent cannot change it (shared rule 7a).

**The document would be where the risk lives — and the document cannot be sent.** A quarterly
briefing *"covering what we are seeing in the market and what we are able to place"* is
exactly the artifact that would carry a rate or a term to an unengaged audience. Shared rule 7f
means it never reaches anyone through this module. **That is not a control and must not be
read as one.** It is a defect that happens to suppress an exposure, and the day somebody adds
an attachment path the exposure arrives with it, ungated. Stated here so it is on the record
before that change rather than after.

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT) — *"what we are able to place"* is a claim
about Burkham's own capability, made to a professional audience that will act on it. The §4.5
review that admitted this template is where the entry was applied.

**`compliance/facilitator-not-broker-v1`** — *"Every engagement, in every state, from intake
through placement."* The recipient is a bank. What Burkham is, and is not, in the referral
relationship is the thing the whole arrangement rests on, and a message to a referring
institution is where a mischaracterisation would do the most damage. The agent adds nothing to
the message and therefore cannot mischaracterise it — but it can mischaracterise the message,
and §7 forbids that.

**REFERRAL_FEE_REGULATION, `referral_fee_permitted_in_state`, `library_gap: true`.** The Pack
declares this obligation and admits no library entry exists for it. **So an agent asked
anything about the commercial terms of the referral relationship has nothing authoritative to
read.** The answer is in Part 2.5 of the marketing-plan intake and it is "there is no fee",
but that is a reference document rather than a compliance entry, and the gap is real.

**No FCRA entry applies, and Part 2.6 is the reason worth naming.** The declining bank does
not send Burkham the applicant's credit data, financial statements or file — the applicant
brings their own through the intake form. So nothing in the referral relationship, and nothing
in this module, is bureau-derived.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** the binding, `_send_approved`, the closed
template id, the request body, the constant `sent: True`, and the `referrer_briefing` copy
verbatim from `templates.py`.

**Read from FunnelForge's source:** the absence of any attachment field in `sendEmailSchema`,
`SendEmailOptions` and every provider call; the `broadcast` route's existence and shape; the
global rate-limit hook and its `general` category.

**Measured on the running containers, 9 September 2026:** the 429 body and headers, and the
empty provider list. Transcripts in the shared rules.

**Measured by P-13:** V31 going NOT_RUN to FAIL on this module id when the nine registry rows
land.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** Part 2.2 (who the
partners are), Part 2.4 (what they get back, including the separate 8-page tailored briefing),
Part 2.5 (no fee, and why), Part 2.6 (what the bank does not send).

## OPEN

**Nobody owns the distribution list on this path.** The module takes one address per call and
has no view of a list; The Office has no list either. Whether a quarterly distribution should
be driven from a list a Forge holds, or from one a human hands over per run, is undecided, and
the answer changes what "the briefing went out" can ever mean.

**The 8-page tailored Decline-Flow Banker-Side Briefing has no module and is not this
template.** Part 2.4 describes it as a separate quarterly artifact, per institution. Whether
it is ever an autonomous send is a §4.5 question nobody has asked; today its absence from the
module list is the gate working, exactly as the engagement letter cover's is.

**A per-recipient send with no per-recipient record is a distribution that cannot be
audited.** Shared rule 7c means FunnelForge holds nothing; The Office's ledger holds one row
per call, which is the record — but reading forty ledger rows to answer "did the briefing go
out this quarter" is not a thing anybody has built. Recorded rather than answered.
