# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge  **Module:** `record_consent`  **Endpoint:** `POST /api/businesses/:id/consent`
**Version:** 1.4 — corrected 3 September 2026, against CapitalForge `1d6c7c8`
**Corrected at 1.4:** §2 named six submission gates and four SMS gates. Five are enforced and five run. See Appendix D.
**Corrected at 1.3:** the read-back prohibition moved from §5 to §7, where a prohibition belongs — see Appendix C.
**Renamed at 1.2:** the module id was `consent_grant` in 1.1. `record_consent` is what the Burkham Pack declares and what the adapter now dispatches. See Appendix B.
**Status:** draft, pending Compliance Review Board

> Authored by Ivan. Stored here as the source text; it becomes an enforced
> instruction only when loaded through `broker.instructions.author()` into
> `forge_operating_instruction`, which is what validator rule V11 reads. V11
> currently names ten modules with no instruction authored, and this is one of
> them.
>
> A fact-check against `1d6c7c8` follows the text, in **APPENDIX — VERIFICATION**.
> Four corrections are proposed there and are NOT applied above; the document is
> Ivan's and pending Board review.

---

## 1. WHAT IT DOES

Records that a business has consented to being contacted on a specific channel for a specific purpose.

**The agent records consent. It does not obtain it.**

Obtaining consent happens in a defined human process with reviewed language. TCPA prior-express-written-consent carries content requirements — who the seller is, what the person is agreeing to receive, that consent is not a condition of purchase — and an agent generating that language conversationally means the disclosure varies per conversation and nobody reviewed it. If a complaint arrives, Burkham would be defending prose an agent produced.

So the agent's job is narrow and it is a filing job: **do not file a record without proof.**

## 2. WHAT IT DOES NOT DO

**It does not make the consent valid.** Recording that consent exists and the consent being legally sufficient are different facts. The module records a claim.

**It does not permit contact.** Sending an SMS passes **five** gates in order — phone on record, Do Not Call list, TCPA consent, resolvable timezone, quiet hours. This module writes gate 3. The other four still stand.

**It does not unblock a submission.** `submit_application` runs its own chain of **five enforced gates** — product reality, consent captured, suitability, KYB/KYC and maker-checker. A sixth, credit-union membership disclosure, is declared and **cannot fire**: it runs only when `issuerType === 'credit_union'` and `CardApplication` carries an issuer name with no issuer type column, so nothing anywhere can produce that value. See `capitalforge-submit-application.md` §4, and the open question recorded in `docs/decisions/submit-application.md` entry 5 — this is not a tidy gap.

These are two unrelated chains for two different acts. The five above govern sending a message; the five here govern submitting an application. A record written here satisfies neither on its own.

**It does not check the channel against what is on record.** SMS consent records cleanly for a business with no phone number, and the gate then answers contactable. The mismatch surfaces only at dispatch, as a `no_phone` block. A successful call is not a statement that the business is reachable on that channel.

**It does not verify who consented.** Nothing confirms the consenting party is who they were said to be.

**It does not touch the Do Not Call list.** Neither granting nor revoking through this API adds or removes a DNC entry. Only an inbound STOP does.

**It does not expire.** Consent recorded in 2024 renders identically to consent recorded yesterday. Whether it should expire is a policy question the module does not answer.

**It does not survive number reassignment.** A business gives up a number, the number is reassigned to someone else, and the record still says consented. Nothing in the system connects those events.

## 3. WHAT EACH INPUT MEANS

| Field | Meaning |
|---|---|
| `businessId` (path) | The business consenting. Must belong to the calling tenant |
| `channel` | Where contact may happen: `voice` · `sms` · `email` · `partner` · `document` |
| `consentType` | What was agreed to: `tcpa` · `data_sharing` · `referral` · `application` · `product_reality` |
| `evidenceRef` | Where the consent actually happened. **Required by this instruction** |
| `metadata` | Free-form. Records who supplied the evidence reference |

`ipAddress` is accepted by the schema and dropped by the route. The stored value is the caller's address — brokered, that is The Office, not the consenting party. **Do not treat that field as evidence of anything.** `evidenceRef` is the only field carrying proof.

`evidenceRef` is required here even though the API accepts its absence. An evidenceRef must identify a specific artifact, be retrievable later by somebody who was not present, and carry when the consent happened. A reference nobody can resolve looks like provenance and is not.

**OPEN — artifact types are not decided.** What a valid evidenceRef points at — a call recording id, a signed document, a portal timestamp — has not been specified. Until it is, an agent uses the reference supplied by the human who obtained the consent and records who supplied it. Do not invent a format.

**`product_reality` satisfies nothing.** It is in the enum, and no channel requires it. The product-reality gate reads `ProductAcknowledgment` rows through a different endpoint entirely. Recording it here has no effect on any gate.

## 4. THE CORRECT SEQUENCE

Before recording, all of these must be true:

1. The business exists and belongs to this tenant
2. A human obtained the consent through the defined process
3. An artifact exists that `evidenceRef` identifies
4. The channel matches something on record — SMS consent for a business with no phone number is a record that can never be acted on

The agent trusts the artifact rather than verifying it, and that is the design. Resolving a recording id or fetching a document is a capability that does not exist. So the agent trusts what the human supplies — and records who supplied it, because "the agent recorded what a human handed it" is a defensible chain and "the agent recorded a string" is not.

After recording, one ledger row is written — `consent.captured`, aggregated on the business. No `AuditLog` row, unlike `submit_application`, which writes one explicitly.

**Nothing is notified.** The event bus has zero subscribers at runtime. Revocation appears to cascade only because `dispatchSmsCampaign` queries the table at send time, not because anything reacts to an event.

**Recording consent here does not advance an application.** The `consent_captured` gate on submission reads the per-application `consentCapturedAt`, stamped by the `pending_consent` transition. A draft that never passed through `pending_consent` fails that gate with a reason, however much business-level consent exists. Draft to submitted directly no longer works.

## 5. WHAT FAILURE LOOKS LIKE

| Response | Meaning |
|---|---|
| `201` | A row was written. Nothing more |
| `400` | `channel` or `consentType` is not in the enum |
| `404` | Not a business you can act on |
| `500` | A genuine failure. State unknown |

A 404 is deliberately ambiguous. "Does not exist" and "belongs to another tenant" return the same response, because distinguishing them would tell an unauthorised caller which business IDs are real. Read it as **not a business you can act on** and report exactly that.

A 201 means **recorded** and nothing else. Not that the consent is valid, not that the reference resolves, not that anyone may now be contacted. Report it in those words.


## 6. RETRY VS ESCALATE

**On timeout: stop and escalate. Do not retry. Do not check first.**

The asymmetry decides it. Two identical calls create two active rows, both landing in the compliance audit export — two consent grants for one act of consenting, with no way to tell which is real. That is a permanent defect in a record a regulator may read. Missing consent is a gap a human closes in a minute by asking again.

Check-then-retry is a race. Between the check and the retry the original write can land. That is a distributed-systems primitive in an agent runbook, built to save a phone call.

A human checks whether the row exists and either records it or moves on. Five minutes, no ambiguity.

**DEFECT — the API is not idempotent.** The gate reads the most recent active record, so the effect is idempotent; the record is not. If the endpoint returned the existing row for the same business, channel, consentType and evidenceRef within a window, this entire runbook decision would disappear. Raised separately; sizing requested.

## 7. NEVER

**Never obtain consent.** Only record consent a human obtained.

**Never record without an `evidenceRef`** identifying a retrievable artifact that carries when the consent happened.

**Never record a channel that was not named.** A human saying "they agreed to texts" authorises `sms` and nothing else. An agent that also records `voice` has manufactured consent for a call nobody agreed to — and it will look identical to real consent in the audit export.

**Never record a purpose that was not named.** Handed "they said we could contact them", an agent has to pick a `consentType`, and picking is inventing.

**Never backdate.** The timestamp is when the record was made, not when consent was given. Asked to record it as of the 14th, refuse — that is falsifying a compliance artifact.

**Never record consent relayed by a third party.** "The office manager said the owner is fine with it" is not consent. Only the consenting party consents.

**Never re-record to refresh.** Consent that looks stale is a question for a human about whether new consent is needed, not a new row with today's date pointing at an old artifact.

**Never retry a timeout.** Escalate.

**Never read the record back to verify it.** An agent that fetches the row has confirmed a row exists, which it already knew. There is nothing honest to verify against, and the check is theatre.

**Never treat a 201 as permission to contact.**

**Never assume revoking stops the contact.** An API revoke writes no DNC entry.

The failure mode here is not malice — it is helpfulness. Every one of these is something an agent would do while trying to be useful, and every one produces a record indistinguishable from a real one.

## 8. WHICH LAWS THIS TOUCHES

**TCPA** — this module writes the record that a TCPA defence would rest on.

**UNVERIFIED.** The code enforces an 8am–9pm recipient-local send window. That is a fact about the code, read from it. Whether it satisfies TCPA, and whether the content requirements for prior express written consent are met by Burkham's obtaining process, are claims requiring a citation to the regulation or an FCC source. Neither has been verified. **Do not state TCPA compliance in any client-facing output.**

**`compliance/call-recording-consent-v1`** — where consent was captured on a recorded call, that recording is itself governed. Explicit consent, every party, every join.

**`compliance/outbound-contact-boundary-v1`** — scoped. Recording consent is not outbound contact and does not invoke the three-part test. But the consent being recorded may have been obtained during contact that did. A valid record of consent obtained impermissibly is still a problem, and recording it cleanly does not fix it.

**`compliance/consumer-privacy-rights-v1`** — a consent record is personal data about a person, subject to access and deletion requests.

**`compliance/application-truthfulness-v1`** — that entry says no agent submits: an agent prepares and a human presses the button. Maker-checker is the mechanism, and until 1 September the submit route did not run it. It does now, and the route requires an `approvedByUserId` naming a real second user who is not the maker.

**OPEN — deletion versus evidence.** A consent record is personal data subject to deletion, and the evidence a TCPA defence would need. Those pull opposite ways. An agent has no authority to delete one; deletion of compliance evidence is a human decision with legal input. Named here rather than answered.

## PROVENANCE

**From the code, read at `147af3b`:** the endpoint and its responses, the enum values, `ipAddress` being dropped, the four-gate dispatch order, the non-idempotent write, `product_reality` satisfying no channel, the 404 ambiguity, the absent DNC entry on API revoke.

**Decided by the founder, 1 September 2026:** recording rather than obtaining; `evidenceRef` required; escalate rather than retry; the never list; trusting the artifact by design.

**Unverified:** every TCPA claim.

## CHANGES SINCE 1.0

Written against `147af3b`; this revision is against `1d6c7c8`, after a sweep of all twelve modules Burkham declares.

1. The two open questions are answered. The write emits one `consent.captured` ledger row and notifies nothing; the channel is not checked against what is on record.
2. The submit chain is named and separated from the send chain. A manual carrying "gate 3 of 4" without that distinction reads as though this module sits on the submission path. It does not.
3. Submission now reads per-application `consentCapturedAt`. Anything stating that recording consent here unblocks a submission was true before 1 September and is not now.
4. Revocation preserves grant-time evidence. The metadata merge is per record inside a transaction, so `grantedByIp`, the granting actor and caller metadata survive. The revoking actor is recorded separately as `revokedByActorId`.
5. The STOP path publishes `CONSENT_REVOKED` like the API path, having previously published nothing.
6. `spend_evidence_export` is the twentieth entry on the module exclusion list.
7. The dropped `ipAddress` is unchanged and remains documented as known.

---

# APPENDIX — VERIFICATION

Checked against `capitalforge@1d6c7c8` on 1 September 2026. Everything in §1–§8 was
read against the source; what follows is only what did not match.

**Confirmed accurate** and worth naming because they are the load-bearing claims:
the endpoint and both enums; `ipAddress` accepted and dropped; the four-gate
dispatch order and the 8am–9pm recipient-local window (`QUIET_HOURS_START = 8`,
`QUIET_HOURS_END = 21`); the six submit gates; `consent_captured` reading the
per-application `consentCapturedAt`; one `consent.captured` ledger row and no
`AuditLog` row; zero event-bus subscribers at runtime; two identical calls
creating two active rows; an API revoke writing no DNC entry;
`revokedByActorId`; and `spend_evidence_export` as exclusion twenty.

### Four proposed corrections

**1. §5 omits 401.** `consent.routes.ts` answers `401 UNAUTHORIZED` —
"Tenant context is required." — at three places, before any other check. A table
that enumerates failure should carry it, or an agent meeting a 401 has no row to
read. Suggested: `401 — no tenant context. The call never reached the module.`

**2. §4 overstates the ledger row.** "one ledger row is written" is what happens
when nothing goes wrong. `_publishEvent` wraps `publishAndPersist` in a
try/catch and logs without rethrowing — *"event bus failures must not block
consent writes"*. So a 201 does not guarantee the ledger row exists, and the
consent row can exist without it. Suggested: *"one ledger row is written when
the bus is reachable; the write is best-effort and a failure is logged, not
raised. A 201 does not guarantee it."* This matters more than it reads: §5 tells
an agent a 201 means "recorded and nothing else", and the ledger row is the part
most likely to be assumed.

**3. §3 `metadata` is not purely free-form.** `grantConsent` spreads caller
metadata and then writes `actorId` and `grantedByIp` over the top, so a caller
supplying either key has it silently replaced. Suggested: *"Free-form, except
`actorId` and `grantedByIp`, which the service writes itself. Do not supply
those keys — they will be overwritten."*

**4. §2 "credit-union membership disclosure" is unreachable.** It is genuinely
the sixth gate in `checkAll`, and it can never fire: it is enforced only when
`issuerType === 'credit_union'` is passed, `CardApplication` has an `issuer`
name and no issuer *type* column, and neither caller passes the argument. Listing
it among six without that note is the shape this whole review has been about — a
control named as though it were enforced. Suggested: keep it in the list and add
*"— which cannot currently fire; nothing supplies the issuer type."*

### One observation, not a correction

§2 "It does not expire" is correct: nothing writes `status: 'expired'`. Two
dashboards (`dashboard-action-queue`, `dashboard-nav-counts`) *query* for expired
consents, so there are two surfaces that will show an empty list forever. Not a
defect in this module, and worth knowing before somebody reads that empty list as
"no consent has expired" rather than "nothing can expire".

## APPENDIX B — THE NAME, AND THE ENDPOINT THAT IS NOT IN THIS MODULE
*3 September 2026*

### The rename

This manual was written at 1.1 as `consent_grant`. The Burkham Pack declares
`record_consent`, and the CapitalForge adapter dispatches under that name, so
this manual is what changed.

The adapter's dispatch keys are the spelling of record for a Forge: the registry
row, the Pack's `modules_expected` and the exclusion list all have to use them or
they do not resolve. Renaming the module would therefore have edited three
artifacts to fix nothing, since the Pack's name was already workable. A name
changes when the name is the problem.

**It is not always the manual that gives way.** `client_lookup` in the same Pack
became `client_read`, `client_read_pii` and `client_read_credit` — there the name
*was* the problem, because one id cannot address three grants carrying three
different permission sets.

### The re-consent email is not in this module, and is not a module

`POST /api/clients/:clientId/consent/request` sends a client an email asking them
to re-consent. **It exists, it works, and no agent can reach it.**

It is a different act from what this module does. This module records that
consent was given; that endpoint contacts a person. A single grant covering both
would let an agent authorised to file a consent record send mail to a client
instead — and the client would receive it believing a human at the firm decided
to write.

**It is deliberately not a separate module either**, which was the first answer
and the wrong one. A module id exists so that something can be granted. Nobody
has decided an agent may send this mail, so giving it an id would create a
registry row, a manual and a grantable surface for an act with no decision behind
it. The absence is the decision.

**What keeps it out** is not the name but the binding: this module binds one
operation and that operation is the write to the consent table. There is no view
that reaches the email, and the adapter's test suite exercises every operation on
every module and asserts that none of them builds that path.

**If it is ever granted**, it gets its own id, its own manual, and its own
decision recorded first — in that order. Until then an agent that needs a client
re-contacted says so and a person does it.

## APPENDIX C — §5 CORRECTED AT 1.3, 3 September 2026

**What changed.** "Do not read the record back to verify" was in §5, WHAT FAILURE
LOOKS LIKE. It is a prohibition, not a failure signature — nothing about it
describes what a failure looks like — and it now sits in §7 with the other nevers.

**Why it was found.** This module is being authored into
`forge_operating_instruction`, where §5 becomes `failure_signatures` and §7 becomes
`never_do`. Mapping the sections onto the eight fields is what surfaced a sentence
sitting under the wrong heading — the value of a schema being that things have to
go somewhere specific.

**Nothing was added or reworded.** The sentence is unchanged and it is still in the
manual. Only the section changed.

## APPENDIX D — §2 CORRECTED AT 1.4, 3 September 2026

Found by a targeted audit of every manual's §2 for asserted protections, run after
`submit-application.md` was found claiming a middleware that does not exist.

**§2 said `submit_application` runs six gates.** It named credit-union membership
disclosure among them. That gate **cannot fire** — `submit-application.md` §4 has
said so since it was written, and this manual asserted the opposite.

The direction is what makes it serious. An omission leaves an agent uncertain; an
assurance makes it confident and wrong. And an agent reading *this* manual has no
path to the correction: the contradicting statement is in a different manual it may
hold no grant for.

**§2 said an SMS passes four gates.** It passes five — `no_phone`, `dnc`,
`no_consent`, `unknown_timezone`, `quiet_hours`. The four named were right and in
the right order; an unnamed fifth sits between consent and quiet hours. Wrong in the
safe direction, and wrong the same way.

**The gate that cannot fire is not closed by this edit.** A dead branch where a
required control should be is a question about the product, not about a manual —
six credit unions are on file as active placement targets offering business cards,
and the disclosure is declared `required: true`. Raised in
`docs/decisions/submit-application.md` entry 5. Until that is answered, this manual
states the gap rather than implying it was decided.
