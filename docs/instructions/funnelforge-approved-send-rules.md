# FORGE OPERATING INSTRUCTIONS — FUNNELFORGE SHARED RULES

Every FunnelForge module manual references this. Nothing here is module-specific.

Written 9 September 2026 by P-16, against `adapters/funnelforge/` at `ac6475c` and against
the FunnelForge that is actually running — fifteen containers on
`ff-docker_funnelforge-network`, probed the same day.

**This file declares no Module header, so `scripts/check_module_manuals.py` prints a skip
line for it and moves on.** `foi-shared-rules.md` is exempt because its name is hard-coded in
that script's `SHARED` set; this one is not, and adding it is a one-line change outside
P-16's scope. The skip is a printed note, not a failure.

---

## 1. THE ADAPTER'S SUCCESS FLAG IS A CONSTANT. READ `upstream.status`

**This is the first rule because it is the one that makes every other rule reachable.**

Every FunnelForge module answers `200` from the adapter with a flag of its own:

```json
{"template_id": "intake_acknowledgment", "sent": true,
 "upstream": {"status": 500, "body": {"success": false,
   "error": {"code": "SEND_FAILED", "message": "No email provider configured. ..."}}}}
```

`sent`, `booked` and `captured` are **written as a literal `True` in the handler and returned
whatever the upstream answered** (`adapters/funnelforge/modules.py`; the dispatcher in
`app.py` wraps the handler's return in a 200 without consulting it). They mean *the handler
ran and made the call*. They do not mean an email left the system, an appointment exists, or
a contact was recorded.

**The truth is at `upstream.status`.** A `2xx` there is the only evidence the act happened.

An agent that reads the adapter's own flag and reports "the acknowledgment was sent" has
produced the exact answer the response was shaped to invite, and it will be wrong every time
FunnelForge refuses. **Today it is wrong on every send — see rule 3.**

**DEFECT, raised not fixed.** A handler that returns `sent: True` beside a 500 is reporting
its own execution as the outcome of the thing it executed. Fixing it means the handler reads
the status, and that is a change to `adapters/funnelforge/`, which is not P-16's. Recorded in
`docs/blocking.md` B33 and in every manual in this set.

## 2. HEADERS DO NOT REACH YOU

`HttpUpstream.__call__` returns `{"status": ..., "body": ...}` and discards the response
headers. Three consequences, and each is stated again where it bites:

- **`X-RateLimit-Limit` / `-Remaining` / `-Reset` are gone.** An agent cannot pace itself
  against a budget it cannot see. The only rate-limit signal that reaches it is the refusal
  itself (rule 4).
- **`Retry-After` is gone from the headers**, but the 429 *body* carries `retryAfter`. Use
  the body.
- **`X-Cache` is gone.** `read_funnel_analytics` cannot tell a fresh answer from a cached
  one. See `funnelforge-read-funnel-analytics.md` §5.

## 3. NO EMAIL PROVIDER IS CONFIGURED, AND THE LOG SAYS OTHERWISE

**Measured 9 September 2026 on the running `funnelforge-api` container, not inferred.**

`docker inspect funnelforge-api` reports `RESEND_API_KEY=` — **present and empty** —
`NODE_ENV=production`, no `EMAIL_CONSOLE_MODE`, and no SendGrid, SES or SMTP variable.

`EmailSender.initializeProviders()` (`apps/email-engine/src/services/email-sender.ts`) adds
a provider only under a truthy variable. An empty string is falsy in JavaScript. The console
fallback is added only when `NODE_ENV === 'development'` or `EMAIL_CONSOLE_MODE === 'true'`,
and neither holds.

So the provider list is empty, and `send()` falls through to:

```
{ success: false,
  error: 'No email provider configured. Set RESEND_API_KEY, SENDGRID_API_KEY,
          AWS_SES_*, or SMTP_* environment variables.' }
```

which `POST /api/emails/send` turns into **`500 SEND_FAILED`**.

**The container's own startup log, verbatim:**

```
EmailSender: Primary provider: console
EmailSender: Available providers:
```

**The first line is false and the second is the true one.** `primaryProvider` is computed as
`this.providers.find(p => p.enabled)?.provider || 'console'`, so `console` is what the field
falls back to when there is nothing to find; the send loop iterates `this.providers`, which
is empty, and never reaches console at all. A reader debugging a missing email meets a log
line saying mail is being printed to stdout, goes looking in the container's output, and
finds nothing — because nothing was printed either.

**What this means for an agent, stated plainly:** against the FunnelForge running today,
**every one of the six approved sends fails**, and the adapter reports `sent: true` over the
top of it (rule 1). An agent that does not read `upstream.status` will report six client
emails that do not exist.

**This is a configuration fact, not a permanent one.** It changes the moment somebody sets a
provider variable and restarts, and nothing in The Office can see that it changed. So the
rule is not "assume sends fail". The rule is: **read the status on every call, every time.**

## 4. THE RATE LIMIT IS REAL, IT IS SHARED, AND IT IS A CLASS THESE MODULES HAVE THAT CAPITALFORGE'S DO NOT

`docs/scenario-generation.md` §3 rules that `rate_limited` has no source in the eight Part
6.1 sections and that every module declares it `not_applicable`, because *"no manual describes
a rate limit, a quota, a 429 or a backoff, because with one exception none of these modules
has one."*

**FunnelForge is a second exception, and it was measured rather than argued.**

`apps/api/src/index.ts` registers a global `preHandler` hook that calls `rateLimitHook`
(`apps/api/src/services/rate-limit-service.ts`) on every route except `/health`. All four
routes these nine modules reach fall in the `general` category.

Probed from inside `ff-docker_funnelforge-network`, five rapid `POST /api/leads/capture`
calls carrying a non-existent `businessId`:

```
500 500 500 429 429
```

and the fourth response body, verbatim:

```json
{"success":false,"error":{"code":"RATE_LIMIT_EXCEEDED",
 "message":"Rate limit exceeded. Please retry after 1 seconds.",
 "tier":"FREE","category":"general","limit":3,"retryAfter":1}}
```

Headers on the permitted calls and on the refusal:

```
500  ->  x-ratelimit-limit: 30   x-ratelimit-remaining: 26   x-ratelimit-reset: 48
429  ->  x-ratelimit-limit: 3    x-ratelimit-remaining: 0    retry-after: 1
```

### Four things follow, and each is a rule

**4a. There are two budgets and one error code.** A per-minute window (`general`, 30/min at
tier FREE) and a per-second burst (3/sec at FREE). Both refuse with
`code: "RATE_LIMIT_EXCEEDED"`. **The only way to tell them apart is `limit` and
`retryAfter`** — `limit: 3, retryAfter: 1` is the burst; `limit: 30` with a larger
`retryAfter` is the window. The `X-RateLimit-Limit` header changes meaning between a
permitted response and a refusal, and it does not reach the agent anyway (rule 2).

`BURST_LIMIT_EXCEEDED` and `DAILY_QUOTA_EXCEEDED` exist in the source, in
`distributedRateLimitHook`, which is **imported by `index.ts` and never registered**. Those
codes cannot occur. An agent must not branch on them.

**4b. The tier is FREE unless somebody bought a plan.** `getUserTier` reads
`prisma.subscription` for the token's user and returns `FREE` unless a subscription exists
with `status: 'ACTIVE'`. Nothing in The Office knows or records which tier the brokered
account holds. **Assume 30 per minute and 3 per second until somebody reads that row.**

**4c. One bucket for the whole Village.** The key is `${identifier}:general`, where the
identifier is the token's user id — and there is no tenant credential (rule 5), so The
Office brokers one FunnelForge user's token. **Every agent, on every one of the nine modules,
spends the same counter.** A briefing distribution that paces itself perfectly can still be
refused because a different agent was reading analytics. **An agent that meets a 429 must not
conclude it was called too often.** It may have been called once.

**4d. There is no daily quota.** `checkEmailQuota`, `checkLeadQuota`, `checkSMSQuota` and
`checkAICredits` are exported by `rate-limit-service.ts` and **called from nowhere in the
API**. The tier table's 100-emails-per-day for FREE is not in force. Do not report a daily
allowance, and do not report a 429 as one.

## 5. THERE IS NO TENANT CREDENTIAL, SO FUNNELFORGE CANNOT TELL AGENTS APART

`server.decorate('authenticate', ...)` verifies a **user JWT**. `x-api-key` and `apiKey`
appear nowhere in the API's middleware or plugins. What The Office brokers is one user's
token.

So every agent's call is attributable, on the FunnelForge side, to a single account, and
FunnelForge's own audit trail cannot distinguish them. **The Office's ledger is the only
per-agent record** — one row per brokered call, keyed by the trace id and by the adapter's
`X-Forge-Request-Id`, which travels back as `forge_side_ref`.

Two consequences an agent carries: it shares a rate-limit bucket with everybody (4c), and
**nothing it does upstream is separable from anybody else's afterwards**. If a report needs
to say which agent sent something, that answer exists in The Office and does not exist in
FunnelForge.

## 6. THE APPROVED COPY IS A PYTHON MODULE IN GIT, NOT A FUNNELFORGE TABLE

There is no send-from-template path in FunnelForge. `POST /api/emails/templates` is a
**routing** 404 — the SDK declares template CRUD that the API does not implement.
`POST /api/emails/send` takes `to`, `subject` and `html`, with no `templateId`.
`EmailQueue.templateId` is written by four call sites and read by none.

So the approved inventory is `adapters/funnelforge/templates.py`, behind the same two-founder
review §4.5 asks for, and each send module is bound to exactly one entry by a closure.
**`template_id` in a request body is read by nothing.** A caller cannot reach a different
template, and an agent that supplies the field has supplied a field nothing reads.

**Never say a template was fetched, resolved, looked up or selected.** Nothing was. The body
that went out is the body the module was compiled with.

## 7. WHAT THE SIX SENDS ACTUALLY PUT ON THE WIRE

The adapter builds one call, and nothing about it varies with the caller except the
recipient:

```
POST /api/emails/send
{"to": {"email": <recipient_email>, "firstName": <recipient_first_name>, "data": <context>},
 "subject": <the template's subject>, "html": <the template's html>,
 "tags": ["the-office", "template:<template_id>"]}
```

**7a. `context` and `recipient_first_name` change nothing that is sent.** They arrive as
`to.data` and `to.firstName`, and `personalizeContent` substitutes `{{firstName}}`,
`{{lastName}}`, `{{email}}`, `{{fullName}}` and one `{{key}}` per `data` entry. **None of the
six approved subjects or bodies contains a merge field.** Read `templates.py` and count: zero
occurrences. So both fields are accepted, travel upstream, and have no effect on the message.
Treat them the way `capitalforge-record-consent.md` treats `ipAddress`: present in the shape,
absent from the outcome. **Never use `context` to add information to a message.** It is not a
way to say something the approved copy does not say, because it is not a way to say anything
at all.

**7b. The From address is FunnelForge's, not Burkham's.** The adapter sends no `from`, so
`EmailSender` uses `DEFAULT_FROM_EMAIL || 'hello@funnelforge.ai'` and
`DEFAULT_FROM_NAME || 'FunnelForge'`. The running container sets neither — it sets
`EMAIL_FROM=noreply@localhost`, a different variable that `EmailSender` does not read. So if
a provider is ever configured, the intake acknowledgment whose subject reads *"We have your
details - Burkham Wickmont"* arrives **from `FunnelForge <hello@funnelforge.ai>`**. Recorded
here because an agent asked what the client will see must not describe a Burkham sender.

**7c. Nothing is written in FunnelForge.** `POST /api/emails/send` creates an `EmailEvent`
row only `if (body.leadId)`, and the adapter never sends `leadId`. No `EmailQueue` row, no
`EmailEvent` row, nothing. **An approved send leaves no trace in FunnelForge's database.**
The Office ledger row is the entire record that the call was made. If a client asks whether
they were emailed, FunnelForge cannot answer.

**7d. The send is synchronous.** The route awaits `emailSender.send()` and answers from its
result. The BullMQ `email-send` queue is not on this path. A `200` from the route means a
provider accepted the message, not that it was queued for later.

**7e. `text` is generated.** The adapter supplies no plain-text part, so `stripHtmlToText`
derives one from the HTML. Nobody reviewed that derivation, and it is what a text-only client
will show.

**7f. THERE ARE NO ATTACHMENTS, AND THREE OF THE SIX APPROVED TEMPLATES SAY THERE ARE.**

The send path has no attachment support anywhere along it. `sendEmailSchema` accepts `to`,
`from`, `subject`, `html`, `text`, `preheader`, `tags` and `leadId`. `SendEmailOptions`
(`apps/email-engine/src/types.ts`) carries `to`, `from`, `content`, `tags` and `metadata`.
`sendViaResend`, `sendViaSendGrid`, `sendViaSES` and `sendViaSMTPBasic` each build a message
from `from`, `to`, `subject`, `html` and `text`. **The string "attachment" does not occur, in
any case, in the route, the sender or its types.** There is no field to put a file in and no
code that would carry one.

Three approved autonomous templates, and the unbound seventh, tell the recipient otherwise:

| template | module | the sentence |
|---|---|---|
| `deliverable_cover` | `send_deliverable_cover` | *"Your Blueprint is attached."* |
| `brief_cover` | `send_brief_cover` | *"This quarter's Capital Command Brief is attached."* |
| `referrer_briefing` | `distribute_referrer_briefing` | *"The quarterly briefing for referring partners is attached..."* |
| `engagement_letter_cover` | **none — human-approve** | *"Your engagement letter is attached for signature."* |

**So a successful send of any of those three delivers a message referring to a document that
is not there, and nothing on either side reports a problem.** The route answers 200, the
adapter answers `sent: true`, the ledger records a call, and the recipient reads a cover note
for a missing enclosure.

**This is a defect in the pairing of an approved template with a transport, and it is
nobody's yet.** The copy is right for a mail with an attachment; the route is a transactional
send with no enclosure. Fixing it is a §4.5 decision — either the copy changes and goes back
through the two-founder gate, or the transport grows an attachment path, or those three
templates are not autonomous sends at all. **None of those is an agent's choice, and none of
them is P-16's**: this manual set documents the code, and the copy is behind a review gate
this package does not sit on. Recorded in `docs/blocking.md` B33.

**For an agent, the rule is narrow and absolute: never say the document was sent.** A 200 on
`send_deliverable_cover` means a covering note was accepted by a provider. The Blueprint was
not attached to it, because it could not have been. An agent reporting *"the Blueprint has
been sent to the client"* has reported a delivery that did not occur, and it is the most
consequential false report available on this surface — a client told their Blueprint is on the
way, a partner told their briefing has gone out.

**It does not affect all six.** `intake_acknowledgment`, `scheduling_confirmation` and
`followup_no_engagement` mention no enclosure and are unaffected.

## 8. `at_most_once`, AND WHY V31 IS RIGHT TO REFUSE

The six sends and the booking are `is_mutating: true, idempotency_support: "at_most_once"`.

An email leaves the system and reaches a person. A retry sends a second one. `EmailQueue`
holds `templateId`, `recipient`, `status` and `scheduledAt` and nothing that would recognise
a repeat — and the send path does not write to it anyway (7c). There is no idempotency key
anywhere on the path.

V31 refuses `auto_execute` over exactly that shape, and `auto_execute` is the only trust tier
that reaches a Forge at all: anything below it becomes a proposal and makes no HTTP call.
**So seven of the nine cannot today be granted at a tier that makes a call.** That refusal is
correct and must not be dodged by softening a declaration at either end. What changes it is an
idempotency key on FunnelForge's send path, which is FunnelForge's to add.

For an agent this reduces to one rule: **never retry a send.** Rule 9.

## 9. RETRY VS ESCALATE, FOR EVERY SEND AND FOR THE BOOKING

**On a timeout: stop and escalate. Do not retry. Do not check first.**

The asymmetry decides it, and it is the one `capitalforge-record-consent.md` §6 sets out. Two
identical calls send two emails to the same person; a client receiving the same Blueprint
cover twice is a visible defect in Burkham's own correspondence, and there is no way to
withdraw one. A message that did not go out is a gap a human closes in a minute.

**Check-then-retry does not exist here.** There is nothing to check. Nothing is written in
FunnelForge (7c), so no query can tell an agent whether the first attempt landed. An agent
proposing to "verify and then resend" is proposing to verify against nothing.

**A 429 is the one exception, and it is a wait rather than a retry.** The call was refused by
a `preHandler` before the route ran, so nothing was sent and nothing is ambiguous. Honour
`retryAfter` from the body, and read 4c first: the bucket is shared, so a second refusal after
waiting is not evidence that this agent is going too fast.

**A 500 is not the exception.** `500 SEND_FAILED` means the provider layer answered
`success: false`, which today means no provider is configured (rule 3). A 500 from anywhere
else on the path leaves the outcome unknown, and unknown plus non-idempotent is an escalation.

## 10. WHICH LAWS THIS TOUCHES

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR, runtime flag
`outbound_contact_boundary_required`) — the Pack's `applies_when` reads *"Any
Burkham-initiated contact with an individual, any channel"*. **Every one of the six sends is
Burkham-initiated contact with an individual.** This is the governing entry for this module
set.

**OPEN, and named rather than resolved.** The deferred Pack edit declares
`compliance_flags_propagated: []` on the FunnelForge binding, on the stated grounds that none
of the four flags the CapitalForge binding propagates is about marketing contact. That
reasoning is sound about *those four* — `per_application_authorization_required`,
`per_pull_authorization_required`, `per_connection_authorization_required`,
`client_interest_standard_required`. `outbound_contact_boundary_required` is not among them
and is not addressed by it. Whether it should propagate is a Pack question; the Pack edit is
deferred and P-16 does not touch `packs/`, so this is recorded and not changed.
`broker/compliance_couplings.py` is why it is recorded at all: a flag absent because nobody
asked reads exactly like a flag absent because somebody decided.

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT) — *"Anything Burkham says about its own
service, results or pricing"*. The approved copy is such a statement. This is the entry the
§4.5 review gate enforces when it reviews a template, and it is why the copy lives behind
that gate rather than in a caller's argument.

**`compliance/client-interest-standard-v1`** (UDAAP) — *"Any client-facing claim about
approval, cost or outcome"*. None of the six approved bodies makes such a claim, which is a
property of the copy rather than of the module. An agent cannot add one (7a), and that is the
control.

**No FCRA entry applies, and no GLBA entry applies.** §6.3 caps FunnelForge permanently at
anonymous browsing data and named-contact marketing PII: no credit data, no Plaid data, no
financial statements, nothing FCRA-regulated, and FunnelForge *"cannot query Console for
credit data to segment marketing sequences."* Nothing any of these nine modules can reach is
bureau-derived or account-derived. Stated because a marketing surface inside a capital
business is exactly where somebody would reasonably look for one.

**CORRECTED 10 September 2026 by P-16b, and the correction itself corrected 10 September 2026
by P-04. The paragraph that stood here said the Compliance Library ships empty and that every
ref above names an entry an agent cannot read. That was wrong when it was written.**
`packs/compliance-library/burkham-wickmont.yaml` **holds nineteen entries** today. All eight
refs cited in this file and in the nine manuals resolve, checked against the file rather than
asserted - `test_funnelforge_manuals.py` now does that check on every run.

**The count and the commit are two facts and P-16b joined them wrongly.** Its correction read
*"holds nineteen entries and was committed on 31 August 2026 in `0bc65a1`"*, which pairs today's
count with the first commit. **At `0bc65a1` the file held seventeen.** It reached eighteen later
the same day, **fell to sixteen on 1 September** in `d58b074` when four template entries were
resolved in three directions - two written, one retired, one folded - and reached **nineteen on
3 September** in `de35f9a`. The load-bearing half is unchanged and is the half that matters: the
Library was **not empty on 31 August**, nine days before rule 10 was written, and it has not been
empty since. But an agent reading "nineteen, committed in `0bc65a1`" and going to look would find
seventeen, and a number that does not survive being checked teaches a reader to stop checking.

**"The Compliance Library" names two things that hold different numbers.** Burkham's *file* holds
nineteen. The *table* `compliance_library_entry` holds **twenty-one**, because it is keyed on
`entry_ref` with no venture column and is shared across ventures: the extra two,
`compliance/ftc-tsr-v2` and `compliance/nv-two-party-consent-v1`, are **Greenstone's**.
`scripts/load_compliance_library.py` documents this and upserts rather than truncating precisely
so that loading one venture's file cannot delete another's. When this file says nineteen it means
Burkham's file. **A ref resolving in that table is not evidence the entry is Burkham's** - that is
the same trap `broker/compliance_couplings.py` records under A REF THAT RESOLVES TELLS YOU NOTHING
ABOUT WHOSE IT IS.

**Where the error came from, because it will be met again.**
`packs/burkham-wickmont.draft.yaml` carries a comment above its `compliance_surface` block
saying `library_entry_ref` is omitted throughout and `library_gap: true` set instead *"because
the Compliance Library ships EMPTY"*. **The comment is stale and the rows beneath it are
current** - all but one now carry a `library_entry_ref`. P-16 read the comment rather than the
rows. **The same sentence appears a second time**, at `packs/burkham-wickmont.split.draft.yaml`,
which B38 did not name; a reader who corrects only the one B38 names leaves the other standing.
**And the library file's own header comment says `SIXTEEN ENTRIES`** - true on 1 September,
stale since 3 September, and wrong in the opposite direction to rule 10's original error. Three
stale counts, in three files, about one library. None is corrected here: `packs/` is not this
package's, and `docs/blocking.md` B41 records all three so the next reader of any of them reads
this first.

**So the rule is the opposite of what stood here: read the entry.**
`compliance/outbound-contact-boundary-v1` is not background for these six sends, it is a gate -
*"NO OUTBOUND CONTACT WITHOUT ALL THREE"*, being **A** a documented relationship, **B** the
channel the person actually gave, and **C** a purpose matching the initiating action, with an
eighteen-month former-client lookback and *"A REFERRAL IS NOT CONSENT"*. **It forbids sends these
modules would otherwise make.** The four manuals authored by P-16b apply it per module rather than
restating it; the five authored by P-16 predate this correction and cite the entry without leaning
on its test.

### 10a. WHICH ENTRY GATES WHICH SEND

**The gate does not bear equally on the six, and reading it as a formality on all six is the
error this table exists to prevent.** Every send is Burkham-initiated contact with an individual,
so `outbound-contact-boundary-v1` applies to all six; what differs is whether the occasion
*supplies* the evidence for A, B and C or whether the module is **blind to it**.

| send | outbound-contact-boundary-v1 | the other entries that bite |
|---|---|---|
| `intake_acknowledgment` | **Satisfied by the occasion.** The form submission is the documented initiating action (A), it supplied the email (B), and acknowledging it is the matching purpose (C). | `own-claims-and-pricing-v1`, `consumer-privacy-rights-v1` |
| `scheduling_confirmation` | **Satisfied by the occasion.** The booking is the initiating action and the confirmation is its matching purpose. | `own-claims-and-pricing-v1`, `estimate-not-offer-v1`, `client-interest-standard-v1` |
| `followup_no_engagement` | **Doing real work.** The initiating action may be months old, so A's eighteen-month lookback bears; and **C is the sharp one** - a follow-up whose purpose has drifted from the scope of what the person actually downloaded fails Part C however warm the lead is thought to be. Escalation trigger 4 is written for *"take me off your list"* and **there is no record to update** (rule 7c writes nothing). | `client-interest-standard-v1`, `own-claims-and-pricing-v1` |
| `deliverable_cover` | **Satisfied** by the active engagement; C matches, it is their own Blueprint. | `client-interest-standard-v1`, `estimate-not-offer-v1`, `facilitator-not-broker-v1` - and **7f**: the copy says the Blueprint is attached and nothing can attach it |
| `brief_cover` | **Marks a boundary the module cannot see.** A quarterly Brief goes to a recipient whose engagement may have ended, so whether the eighteen-month lookback is still open is the live question - **and nothing on this path reads engagement status.** C is the second question: a quarterly brief sits closer to cross-sell than to the original initiating action, and *"A Blueprint client may be contacted about their Blueprint, not cross-sold a partner's product"* is the entry's own example. | `client-interest-standard-v1`, `estimate-not-offer-v1`, `facilitator-not-broker-v1` - and **7f** |
| `referrer_briefing` | **Satisfied for the recipient, and the trap is conflating two people.** The recipient is the referring institution, with which Burkham has its own relationship. *"A REFERRAL IS NOT CONSENT"* governs contacting the person the partner **names**, not the partner - an agent that reads it as blocking this send has read it about the wrong party. | `facilitator-not-broker-v1`, `reg-z-advertising-boundary-v1`, `own-claims-and-pricing-v1` - and **REFERRAL_FEE_REGULATION is a real `library_gap`**, so nothing authoritative answers a question about the commercial terms |

**The two that most need reading are `followup_no_engagement` and `brief_cover`**, and they fail
differently: the follow-up's Part C is a judgement the agent can make from what it has, and the
Brief cover's Part A is a fact the module **cannot** reach. An agent cannot satisfy a test against
evidence that does not arrive, and shared rule 7c means nothing it sends leaves a record to check
afterwards either.

## 11. OPEN

**The tag `template:<id>` has never been accepted by a provider.** The adapter sends
`["the-office", "template:intake_acknowledgment"]`, and the Resend path maps each tag to
`{name: tag, value: 'true'}`. Whether a provider accepts a tag name containing a colon and an
underscore is **untested**, because no provider is configured (rule 3) and no send has ever
reached one. Recorded as a thing to watch on the first send after a provider is set, not
asserted as a defect.

**Nothing anywhere records that a message was delivered.** The Office ledger records that a
call was made. Delivery, bounce and complaint are provider facts, and with no provider there
is no channel by which they would arrive. Whether an autonomous send surface should be
granted before a delivery record exists is a question nobody has asked.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** the dispatch map and its declarations,
the two refusals and their codes, the closed-over template id, the request body each handler
builds, the constant success flags, and `HttpUpstream` discarding headers.

**Read from FunnelForge's source:** the global rate-limit hook and its category map, the
unregistered `distributedRateLimitHook`, the uncalled quota helpers, `EmailSender`'s provider
initialisation and its console fallback, `personalizeContent`, the `leadId`-conditional
`EmailEvent` write, and the synchronous send path.

**Measured on the running containers, 9 September 2026:** the empty `RESEND_API_KEY`, the
`EmailSender` startup log, the 429 body, and the rate-limit headers on both a permitted and a
refused call.

**Inherited from `docs/plans/funnelforge-binding-RECORD.md`:** the four route probes and
their bodies, the two 404 shapes, the empty `/docs/json`, the absent tenant credential, and
the dead ingress.
