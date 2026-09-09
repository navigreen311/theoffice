# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `capture_contact`
**Endpoint:** `POST /api/leads/capture`
**Version:** 1.0 — drafted 9 September 2026, against `adapters/funnelforge/` at `ac6475c` and
the running FunnelForge stack
**Status:** draft, pending Compliance Review Board

Read `funnelforge-approved-send-rules.md` first. Rules 1, 2, 4 and 5 govern this module. Rules
3, 6, 7, 8 and 9 are about the six sends and **do not** apply here — this module is
`natural`, not `at_most_once`, and its retry rule is the opposite of theirs.

**This module sends no email and can cause one.** A new lead is auto-enrolled in the
business's active `WELCOME` email sequence, through a path no module gates and no approved-
template refusal touches. That is §2 and it is the reason this manual exists in the shape it
does. It is one of two such holes in the nine; the other is
`funnelforge-schedule-blueprint-call.md` §2.

**It is one of only two modules V31 permits at `auto_execute`**, the other being
`read_funnel_analytics`. That is because it is `natural` — a retry updates the same lead
rather than creating a second one — and the classification was read out of
`apps/api/src/modules/leads/routes.ts`, not out of the route's name.

## 1. WHAT IT DOES

Records a named marketing contact against a Burkham business: a newsletter signup or a gated-
download requester. §6.2's named-contact PII, and the only PII FunnelForge is permitted to
hold.

**Find, then update or create**, keyed on `(email, businessId)`:

- **Found** — the existing `Lead` is updated. See §2 for what "updated" means, because it is
  narrower than it sounds.
- **Not found** — a `Lead` is created with `status: 'NEW'` and `score: 0`, **and the welcome
  sequence fires.** §2.

That key is why the module is `natural` rather than `at_most_once`. Calling twice with the
same email and business does not produce two leads.

## 2. WHAT IT DOES NOT DO

### It does not avoid enrolling the contact in an email sequence

**On a new lead only, the route looks up the business's `emailSequence` where
`type: 'WELCOME'` and `isActive: true`, and calls `sequenceProcessor.enrollLead`.** If such a
sequence exists, the contact begins receiving it. **Nothing in The Office gated that, and no
approved-template refusal ran on any of it.** Module-gating stops an agent naming a send; it
does not stop a non-send module triggering one.

**The enrolment is wrapped in a `try/catch` that logs and does not rethrow.** So a failed
enrolment is invisible in the response, and a successful one is equally invisible. **The 200
says nothing about whether the contact was enrolled, or in what.**

**What closes the hole is operational, and nobody currently checks it.** It closes by there
being no `isActive` `WELCOME` sequence on the Burkham business. That is a row in FunnelForge
that somebody can set at any time, from FunnelForge's own UI, with no visibility from The
Office. **Before this module is used, somebody should read that row.** The manual cannot tell
you what it says.

**This matters more than a general "a side effect exists".** Part 2.8 of
`docs/reference/burkham-wickmont-marketing-plan-intake.md` states the rule for the applicant
path in absolute terms: *"Applicant is never enrolled without affirmative consent. No
pre-checked boxes. No implied opt-in."* §6.4 says named-contact PII is *"retained while
subscribed and opted-in"*. **There is no consent field on this route, no consent argument on
this module, and no consent check anywhere on the path.** The affirmative consent, where it
exists, was captured by the form the contact filled in — and this module has no view of that
form and no way to require it.

### The rest

**It does not clear, correct or remove anything.** The update is a merge and only a merge:

```js
firstName: body.firstName || lead.firstName,
lastName:  body.lastName  || lead.lastName,
phone:     body.phone     || lead.phone,
tags:      body.tags ? [...new Set([...lead.tags, ...body.tags])] : lead.tags,
customFields: { ...(lead.customFields || {}), ...(body.customFields || {}) }
```

**An absent or empty value never overwrites an existing one, and tags are a set union.** So
this module **cannot remove a tag, cannot blank a wrong first name, and cannot correct a
misspelling to nothing.** It can only add or replace with a non-empty value. An agent asked to
"remove the wrong tag" or "clear that field" must say the module cannot, rather than calling
it and reporting success.

**It does not record most of the named-contact record §6.2 describes.** That record is *"name,
email, business name, business industry, business size band, one-line context"*. The adapter
sends `businessId`, `email`, `firstName`, `lastName`, `phone`, `source` and `tags`. It never
populates `customFields`, which is the route's only home for the rest. **Business name,
industry, size band and the one-line context cannot be written through this module.**

**It does not tell you whether the lead was new.** The route answers `isNew: !body.funnelId`
— derived from whether a funnel id was supplied, not from whether a lead was created. The
adapter never sends `funnelId`, **so this field is always `true` from The Office**, on a
created lead and an updated one alike. The adapter does not promote it into its own answer,
but the whole upstream envelope travels back: **it is visible at
`upstream.body.data.isNew` and it is a constant.** Read it as nothing. Shared rule 1's
sibling — a field that is present in the shape and absent from the outcome.

**It does not write an analytics event.** `FORM_SUBMIT` is created only when both `funnelId`
and `pageId` are supplied, and the adapter sends neither. **A contact captured through The
Office does not appear in `read_funnel_analytics`'s conversion rate**, though it does appear
in `totalLeads`.

**It does not tell you whether a contact was recorded.** `captured: true` is a constant.
Shared rule 1. Read `upstream.status`.

**It does not check consent, suppression, or a prior opt-out.** No field, no lookup, nothing.

**It does not unsubscribe, purge or honour a deletion request.** §6.4 requires purging named-
contact PII within 60 days of an opt-out. **No module on this Forge can do it**, and this one
in particular only ever adds.

**It does not verify the business exists** before writing. It attempts the write and the
foreign key refuses it. §5.

## 3. WHAT EACH INPUT MEANS

| Field | Meaning |
|---|---|
| `business_id` | **Required.** The Burkham business. Half the identity key |
| `email` | **Required.** The other half. Also the update key — a different address is a different lead |
| `first_name` | Optional. **Merged, never cleared** |
| `last_name` | Optional. **Merged, never cleared** |
| `phone` | Optional. **Merged, never cleared.** See below |
| `source` | Optional. Defaults to `"the-office"` on the adapter side |
| `tags` | Optional list. **Union, never removal** |

**There is no `compliance_state` on this module, and its absence is a decision.** §3.3's
categorical state governs what is *sent to* a person; this records that a person asked to hear
from us. Refusing a capture on a compliance state would drop the record of a request while the
request still happened, which is worse than holding it. **Do not read the absence as this
module being unregulated** — read §8.

**`email` is the identity, so a typo creates a second contact rather than correcting the
first.** And because the update path can never clear a field, the wrong record cannot be
emptied afterwards through this module.

**`phone` deserves its own note.** §6.2's named-contact inventory is *"name, email, business
name, business industry, business size band, one-line context"*. **A phone number is not on
it.** The route accepts one, the adapter forwards one, and the column exists — so a phone
number can be written into FunnelForge's marketing tier through this module even though the
declared scope for that tier does not name it. A phone number is also the field that turns a
marketing record into a contactable channel governed by the TSR and by
`compliance/outbound-contact-boundary-v1`. **Do not supply one unless somebody has decided
that FunnelForge holds phone numbers**, and record who decided.

**`source` defaults to `"the-office"`,** so every contact captured this way is identifiable as
agent-captured in FunnelForge's own data. That is useful and it is the only provenance the
lead row carries — the ledger row in The Office is the rest of it (shared rule 5).

**`tags` are permanent from this module's side.** Add only tags somebody has decided belong on
this contact indefinitely.

**Absent `business_id` or `email` is refused before any call**, as `422 ARGUMENT_MISSING`.

## 4. THE CORRECT SEQUENCE

1. **Establish that this person asked to hear from Burkham, and where they asked.** The module
   records a request; it does not observe one. §8.
2. **Establish whether the business has an active `WELCOME` sequence**, because a new capture
   will start it and nothing in the response will say so. §2. This is a question for a person
   with FunnelForge access; it is not answerable from The Office.
3. **Call once**, with `business_id` and `email` and whatever else has been decided.
4. **Read `upstream.status`.** Not `captured`. Shared rule 1.
5. **On `200`, read `upstream.body.data.leadId`** — that is the lead. Ignore `isNew` beside
   it; it is a constant. §2.
6. **Report the capture as a capture and not as a subscription, a consent, or a welcome.** What
   is known is that a lead row now exists or was merged into. What was sent to the person, if
   anything, is not visible from here.

**Retrying is permitted and it is safe.** §6. That is the one place this module differs from
every other mutating module on this Forge, and it follows from the `(email, businessId)` key,
not from a policy.

## 5. WHAT FAILURE LOOKS LIKE

### From the adapter

The table in `funnelforge-send-intake-acknowledgment.md` §5 applies. The only refusal code
reachable here is `ARGUMENT_MISSING` — **there is no compliance refusal and no template
refusal on this module.**

### From FunnelForge, at `upstream.status`

| Status | Body | Meaning |
|---|---|---|
| `200` | `{"success":true,"data":{"leadId":...,"isNew":true}}` | A lead exists. `isNew` is a constant |
| `400` | `VALIDATION_ERROR` | Zod refused the body — in practice, `email` is not an email |
| `429` | `RATE_LIMIT_EXCEEDED` | Refused before the route ran. **Nothing was written.** Shared rule 4 |
| `500` | `P2003` foreign key | **The `business_id` does not exist.** See below |
| `500` | anything else | Unhandled. State unknown |

**The `P2003` 500 is the informative one and it has been measured twice.** P-13 probed it on
9 September 2026 and P-16 reproduced it the same day:

```json
{"statusCode":500,"code":"P2003","error":"Internal Server Error",
 "message":"Invalid `prisma.lead.create()` invocation: Foreign key constraint violated:
            `Lead_businessId_fkey (index)`"}
```

**It means the binding reached the database and the business id is not a business.** It is a
bad argument answered as a server error, because the route has no business-existence check
that would have produced a 404. Report it as *no such business*, not as a FunnelForge outage,
and do not retry it — the id will not become valid.

**A `500` on the *update* path is a different and worse thing**, because the lead was found,
so the failure is after the lookup and the outcome is unknown. The `P2003` code is how you
tell: it can only come from the create.

**There is no 404 anywhere on this module.** The route does not look a business up before
writing.

**A `429` here is unusual and it is shared.** This module is called once per contact, not in
a loop — but the bucket is shared with every other agent and every other FunnelForge module
(shared rule 4c), so a refusal is not evidence about this module's own pacing.

## 6. RETRY VS ESCALATE

**Retry a timeout. This is the one mutating module on this Forge where that is correct, and
the reason is a key rather than a policy.**

The route finds on `(email, businessId)` before it writes. A second call after a timeout finds
whatever the first one created and updates it. There is no second lead, no duplicate, and
nothing to reconcile. That is what `idempotency_support: "natural"` means here and it was read
out of the handler.

**Three things a retry still cannot undo, and they are why "retry freely" is not the whole
rule:**

1. **If the first call created the lead, the welcome sequence already fired.** A retry does
   not fire it again — the enrolment is on the create branch only — but it does not withdraw
   it either. The email is out.
2. **A retry cannot correct anything.** The merge only ever adds (§2). A retry with better
   values will fill blanks and will not fix a wrong non-empty value.
3. **A retry with a different email is not a retry.** It is a second contact.

**On a `P2003` 500: do not retry. Escalate to whoever knows the business id.** It is a bad
argument and repetition will not improve it.

**On any other 500: retry once, then escalate.** The state is unknown, and unlike a send, a
second attempt cannot make it worse — the key protects it. If the second attempt also fails,
the question is about FunnelForge and belongs to whoever operates it.

**On a 429: wait `retryAfter` from the body, then call again.** Nothing was written. Shared
rule 4c before concluding anything about pacing.

**Escalate rather than retry when the request itself is in question** — a phone number nobody
authorised (§3), a tag nobody decided, an address that may be a typo. The module cannot
reverse any of those, so the moment to stop is before the call.

## 7. NEVER

**Never report a capture from `captured: true`.** It is a constant. Shared rule 1.

**Never report `isNew`.** It is `true` on every call The Office makes and it does not mean the
lead was new. §2.

**Never say the contact was subscribed, opted in, or has consented.** This module records a
contact. It captures no consent, checks none, and has no field for one. Consent, where it
exists, lives in the form the person filled in and in Console's Consent & Authorization
Center — not here.

**Never say the contact was welcomed, or that a sequence started.** The enrolment is
conditional on a sequence row this module cannot see, and its failure is swallowed. §2.
*"A lead record now exists; whether a welcome sequence started is not visible from here"* is
the true statement.

**Never capture somebody who did not ask.** Every other prohibition on this list is about
reporting. This one is about the act. §6.2's scope is *opted-in* named contacts, and a
capture is the record of a request — an agent that captures a name it found somewhere has
manufactured the request, and if a WELCOME sequence is active that person now receives mail.

**Never use this to "clean up" a record.** It cannot remove a tag, cannot clear a field, and
cannot delete anything. An agent that calls it to fix a record and reports success has
reported an act the module is incapable of.

**Never supply a phone number without a decision behind it.** §3. It is outside §6.2's
declared inventory for this tier and it creates a contactable channel.

**Never put credit, financial or underwriting detail in any field.** §6.3 makes the marketing
and underwriting tiers architecturally separate — FunnelForge holds no credit data, no Plaid
data, no financial statements, nothing FCRA-regulated. `tags` and a name field are free text
and the architecture cannot stop an agent typing into them. **Writing "declined by Chase" into
a tag puts underwriting-scope data in the marketing tier**, and the separation §6.3 relies on
is the reason the marketing tier is out of FCRA scope at all.

**Never assume a capture suppresses anything.** §6.3 permits one-way flow — Console can tell
FunnelForge a prospect became a client, for suppression of prospect-side sequences. This
module is not that flow and triggers none of it.

**Never capture the same person under two addresses to "make sure".** The key is the email.
Two addresses are two leads, two possible welcome enrolments, and no way to merge them.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/consumer-privacy-rights-v1`** (CCPA, and STATE_PRIVACY_COMPREHENSIVE for VA, CO,
CT, UT) — **the governing entry.** This module writes personal data about an identifiable
person into a system, which is a processing activity, and it is the only one of the nine that
creates a durable PII record. §6.4 requires purging named-contact PII within 60 days of an
opt-out or unsubscribe. **No module on this Forge can purge, unsubscribe, or read the record
back.** A privacy request touching a contact captured here is answered by a person with
database access. That asymmetry — an agent may create the record and cannot honour a right
over it — is the thing to carry.

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR) — *"Any Burkham-initiated contact with
an individual, any channel."* **This module is not contact, and it can produce contact**, via
the welcome sequence (§2). The entry reaches the mail that enrolment sends, and that mail is
not on the approved list, was not reviewed under §4.5, and no refusal in the adapter touches
it. Naming the coupling is the point: the compliance surface reaches an act the module list
does not gate.

The same entry is the reason `phone` matters (§3). A recorded phone number is a channel, and
a channel governed here is one the TSR reaches.

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT) — reached only through the welcome
sequence's content, which nobody at Burkham reviewed and which this module does not choose. It
is named so that the absence of a review is on the record.

**No FCRA entry applies, and §6.3 is why that is a design property rather than an
observation.** *"FCRA 'user' and 'furnisher' obligations attach to entities that handle credit
report data. Keeping marketing tier out of credit data means marketing tier is out of FCRA
scope."* **The separation is what keeps this module out of FCRA scope, and the separation is
maintained by what people write into free-text fields.** §7 exists to protect it.

**No GLBA entry applies.** Nothing here touches a Plaid connection or financial account data.

**`compliance/estimate-not-offer-v1` and `compliance/reg-z-advertising-boundary-v1` are scoped
out, deliberately.** This module writes a record; it presents nothing to anyone and states no
rate, payment, term or fee. Reg Z's advertising boundary would reach the welcome sequence's
content if that content carried a trigger term — which is a question about a sequence nobody
has read, not about this module.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** `_capture_contact`, the fields it forwards
and the ones it does not, the `"the-office"` source default, the deliberate absence of a
compliance refusal and the docstring's reason for it, the `natural` declaration and the
comment recording that it was read from the route rather than the name, and the constant
`captured: True`.

**Read from FunnelForge's source (`apps/api/src/modules/leads/routes.ts`):** the
find-on-`(email, businessId)`, the `||` merge semantics and the tag set-union, the create
branch's `status: 'NEW'` and `score: 0`, the `WELCOME` sequence lookup with `isActive: true`
and its swallowing `try/catch`, the `funnelId && pageId` condition on the analytics event, and
`isNew: !body.funnelId`.

**Measured, 9 September 2026:** the `P2003` foreign-key 500 — by P-13 first and reproduced by
P-16 — and the rate-limit behaviour. Transcripts in the shared rules and in
`docs/plans/funnelforge-binding-RECORD.md`.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** §6.2's named-contact
inventory, §6.3's architectural separation and its one-way flow, §6.4's retention and purge
rules, and Part 2.8 on affirmative consent.

## OPEN

**Nobody has read the Burkham business's `WELCOME` sequence row.** §2. Whether an active one
exists decides whether this module sends email, and it is answerable in a minute by somebody
with FunnelForge access. It is not answerable from The Office and it is not answered here.

**The welcome sequence's content has never been reviewed under §4.5.** If one is active, an
agent's capture starts a series of emails to a named person, over Burkham's name, that no
founder approved. That is the same gap `funnelforge-schedule-blueprint-call.md` records for
the appointment confirmation, and neither is closable from The Office.

**An agent can create a PII record it cannot honour a privacy right over.** §8. Whether a
create-only surface should be grantable before a delete path exists is a question the nine-
module surface raises and does not answer.

**The module cannot write most of the record §6.2 defines.** §2. Whether that is a gap to
close by populating `customFields`, or a scope decision to state, has not been asked.
