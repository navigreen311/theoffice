# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `client_read_credit`
**Endpoints:** 4 GETs under `/api/clients/:clientId` and `/api/v1/clients/:clientId`
**Permission:** `business:read` **and** `business:read:credit`
**Version:** 1.5 — corrected 3 September 2026, against CapitalForge `fcc46ab`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Sections 1, 2 and 3 govern most of what this module returns, and they are not repeated here.

**Everything this module returns is bureau-derived, and `compliance/bureau-report-handling-v1` governs what may be done with it.** Reading it here does not widen that.

## 1. WHAT IT DOES

Reads credit data on file for a client.

| Endpoint | Returns |
|---|---|
| `GET /credit/business` | Business credit profiles — PAYDEX and equivalents |
| `GET /credit/personal` | Personal credit profiles — FICO |
| `GET /credit/history` | Every bureau pull, stamped, for **one** profile type |
| `GET /credit/recommendations` | Recommendations derived from the latest pull |

Four separate calls, one module. They share a blast radius: all read, none write, none contact anyone, and all four are governed by the same compliance entry.

The rest of the client file is `client_read`. Owners, timeline and the ACH authorisation are `client_read_pii`. A grant to this module is not a grant to either.

## 2. WHAT IT DOES NOT DO

It does not write. No row changes, nothing is sent, nothing is recorded — including no record that the read happened. **Reading a credit file leaves no trace.**

**A brokered call is the exception, and it is not this module's doing.** A call arriving through The Office writes one `ledger_events` row per call — `office.module.called`, keyed by the trace id The Office also records — whatever the module does, reads included. That is an access record about the brokered call, not a business event about the client, and it is not visible to anything reading this module's output. A human's call through the UI behaves exactly as the sentence above describes.

It does not pull credit. Everything here is a profile somebody already pulled. **An empty result is not a low score; it is no pull on record.**

It does not prove anything about the client's situation. It reports what Burkham has on file. See shared rule 1.

It does not verify the client exists. That already happened. The mount guard runs before any handler here, so by the time a handler executes the client is known to exist and to belong to the caller's tenant.

**It does not estimate.** `/credit/recommendations` attaches no point-impact figures, because predicting a score change needs a model this system does not have. An agent must not present a recommendation as quantified.

## 3. WHAT THE INPUTS MEAN

| Input | Meaning |
|---|---|
| `clientId` (path) | The client. Guaranteed to exist and to be the caller's by the time a handler runs |
| `profileType` (query, `/credit/history`) | `personal` or `business`. Required, deliberately |

`profileType` is the most likely first-call error in this module. It is not defaulted, and the reason is that personal and business scores run on different scales — FICO 300–850, PAYDEX 0–100. The endpoint once returned both in one series, so a PAYDEX of 80 sat beside a FICO of 762 under the same `month` and a caller plotting one axis read a 682-point collapse.

A call without it fails with 400. **That is the control working**, not a fault to route around by guessing a value.

**Both mount paths are the same router.** `/api/clients/:clientId` and `/api/v1/clients/:clientId` are identical. Anything true of one is true of the other.

## 4. THE CORRECT SEQUENCE

The four calls have no ordering requirement between them and no state to carry — any one can be made without any other. What has an order is what surrounds a read:

1. **Read.** One call, or several in any order. `/credit/history` requires `profileType`; a 400 there is the control working, not a fault to route around.
2. **Distinguish a 403 from an absence before reporting anything.** A 403 means this grant does not reach the credit file. It says nothing about whether a profile exists. Shared rule 1a, and it is the failure this module produces most often.
3. **Check every empty result for a declared basis before reporting it.** `no_credit_profile_on_record`, `no_business_credit_profile_on_record`, `no_personal_credit_profile_on_record`. Shared rules 2 and 3.
4. **Where the read is gathering context rather than answering a question, apply shared rule 1 to everything it returned — and `compliance/fair-treatment-in-routing-v1` as well.** An absence in a credit file is a fact about the records, and it does not stay neutral once it enters a placement decision.

Step 4 is the one that carries, and it carries further here than anywhere else in the family. An absence entering a placement decision as a negative fact is a client refused for a record that was never created.

## 5. WHAT FAILURE LOOKS LIKE

### The 403 is the failure to expect

**A 403 here means the caller holds `business:read` but not `business:read:credit`, and it is the most likely failure this module produces.**

Until 2 September 2026 there was no permission gate on this router at all. A `readonly` session and a `client` portal session reached bureau data with exactly the same permission as an advisor, because one permission covered a legal name and a credit file alike. Neither role holds `business:read:credit` now, so both get 403 on all four endpoints.

**A 403 is not an absence — shared rule 1a, which was written for this case.** It says nothing about whether a credit profile exists or what it contains. An agent that reports "no credit profile on record" after a 403 has manufactured a finding out of its own lack of permission, and it is a finding about somebody's creditworthiness. Report the refusal as a refusal — "this grant does not reach the client's credit file" — then stop or ask for the grant.

### Everything else

| Response | Meaning |
|---|---|
| 200 | The read ran. Check the body before reporting it as a result |
| 400 | `profileType` is missing or is not `personal` or `business` |
| 403 | The caller lacks `business:read:credit`. See above — this is the expected failure |
| 404 | `NOT_FOUND` from the mount guard: no such client, or not yours. Stop |
| 500 | Includes a missing tenant context, which surfaces here rather than as a 401 |

A 404 is unambiguous on this module — there is no per-record 404 here, unlike `client_read_pii`.

**Empty results are real answers, not errors.**

`/credit/recommendations` returns `[]` with `basis: 'no_credit_profile_on_record'` when nobody has pulled this client's credit. That basis is the answer. Shared rules 2 and 3.

`/credit/business` and `/credit/personal` carry `no_business_credit_profile_on_record` and `no_personal_credit_profile_on_record`. No pull of that type is on record. Report the basis.

**None of these means the client has poor credit, thin credit, or no credit.** It means nobody pulled it, or nobody pulled that type. This is shared rule 1 in the place it does the most damage: an absence in a credit file, entering a placement decision as a negative fact, is a client refused for a record that was never created.

## 6. RETRY VS ESCALATE

**Retry freely.** All four are pure reads. Nothing is written, nothing is sent, no bureau is contacted, and a retry after a timeout costs nothing and duplicates nothing.

This is a property of this module, not of the URL prefix. It does not extend to `client_compliance_run` or `client_consent_request` — the first persists a check per call, the second sends an email per call.

## 7. NEVER

**Never act on an absence.** No credit profile, no history, no recommendations — each is a fact about Burkham's records. An agent that turns one into a claim about the client's creditworthiness has manufactured a finding, and it is the most consequential finding this system can manufacture.

**Never treat a 403 as an absence.** Shared rule 1a. It is the failure this module produces most often, and reporting it as a credit finding is the worst available outcome for this module.

**Never report an empty result without its basis.** Shared rule 2. `no_credit_profile_on_record` is the answer.

**Never paraphrase a basis.** Shared rule 3. "Insufficient credit information" is a judgement; "thin file" is a bureau term this system has not applied.

**Never quantify a recommendation.** No point-impact figure exists to attach. "This could raise the score 25–40 points" is a claim this system cannot support and once made.

**Never read `/credit/history` without `profileType`**, and never combine the two profile types into one series. They are different scales, and a chart that mixes them shows a collapse that did not happen.

**Never render this as Burkham's own assessment.** It is what a bureau reported and what this system recorded. `compliance/bureau-report-handling-v1` is explicit: never shared outside the client's authorised viewers, never attached to a lender packet, never presented as Burkham's assertion of creditworthiness.

**Never present this data as verified.** A profile is a pull stamped with `pulledAt`. Nothing re-verifies it at read time, and an old pull reads exactly like a recent one unless the timestamp is carried with it.

## 8. WHICH LAWS THIS TOUCHES

`compliance/bureau-report-handling-v1` — **the governing entry for this module.** All four endpoints return bureau-derived data. Never shared outside the client's authorised viewers, never attached to a lender packet, never rendered as Burkham's own assertion of creditworthiness. Reading it here does not widen what may be done with it.

`compliance/fair-treatment-in-routing-v1` — this module returns exactly the inputs that entry governs. Where a read feeds a routing or recommendation decision, everything it says about inputs applies, including to absences.

`compliance/consumer-privacy-rights-v1` — every record readable here is personal data subject to access and deletion requests.

**Note — what is behind this grant.** A credit file is the single most consequential record in a client's engagement: it decides placement, it is the basis of every eligibility answer, and a wrong reading of it is a decision made about somebody's business. Until 1 September 2026 these four endpoints were cross-tenant readable; until 2 September there was no permission gate at all.

## PROVENANCE

**From the code, read at `fcc46ab`:** the four endpoints and their permissions, `profileType` being required and why, the basis on `/credit/recommendations`, the absence of point-impact estimates, the `{ scores: [] }` shape, the mount guard, the `/v1` alias.

**Decided by the founder, 2 September 2026:** the three-way split and its boundary; `auto_execute` with narrow grants rather than `propose`; withholding `business:read:credit` from `readonly` and `client`.

**Split from `client_read` 1.2 on 2 September 2026, updated to 1.4 the same day** when the last empty results gained a basis and shared rules 1a and 1b were added.

**Split note.** §§2, 4 and 6 are inherited unchanged. §5 leads with the 403 by founder instruction: both affected roles previously reached bureau data with an advisor's permission, and it is the failure an agent will actually hit.

## OPEN

**Nothing records that a credit file was read.** §2 states it as a fact about the module. Whether reading bureau data should leave an audit trail is a policy question nobody has answered, and `compliance/bureau-report-handling-v1` may already require one.

**A profile's age is not surfaced.** `pulledAt` is on the record, but nothing marks a pull as stale, and an eighteen-month-old score reads exactly like one from this morning. Whether there is a staleness threshold is a product decision.

## APPENDIX — CORRECTED AT 1.5, 3 September 2026

Two corrections, both made while authoring this module into
`forge_operating_instruction`, and both the same corrections its sibling
`client_read` took at 1.5 and 1.6.

**§2 said the read leaves no record.** True of a human's call through the UI, and no
longer true of a brokered one: the CapitalForge Office adapter writes one access
record per call, reads included. The module still writes nothing of its own. §2 now
states the difference — the property is right for a person clicking and wrong for an
autonomous agent reading a client's file.

**§4 said "there is none" and then described a sequence.** A reader looking for a
sequence stopped at the first sentence. It now states the steps it was describing.
The endpoints remain independent, unordered and stateless with respect to each
other; what is ordered is the discipline around a read.

Writing "no required ordering" as a one-item list would have satisfied the
curriculum's `validate_sections` by turning a stated absence into a step — the move
this manual set warns about everywhere else.
