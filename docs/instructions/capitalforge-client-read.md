# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `client_read`
**Endpoints:** 6 GETs under `/api/clients/:clientId` and `/api/v1/clients/:clientId`
**Permission:** `business:read`
**Version:** 1.4 — drafted 2 September 2026, against CapitalForge `fcc46ab`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Sections 1, 2 and 3 govern most of what this module returns, and they are not repeated here.

**This module was thirteen endpoints until 2 September 2026.** `/owners`, `/timeline` and `/ach-authorization` are now `client_read_pii`; the four `/credit/*` are `client_read_credit`. Each has its own grant and its own manual. A `client_read` grant reaches none of them.

## 1. WHAT IT DOES

Reads the firm's own records about a client engagement — identity, documents, product acknowledgments, compliance checks, repayment schedule.

Six separate calls, one module:

| Endpoint | Returns |
|---|---|
| `GET /` | The business profile |
| `GET /documents` | Documents in the vault for this business |
| `GET /acknowledgments` | Product acknowledgments signed by the client |
| `GET /compliance` | Compliance checks, with a score computed from them |
| `GET /compliance/status` | The same, without a total |
| `GET /repayment` | Active repayment plan, schedule, and cards approaching APR expiry |

They share a blast radius: all read, none write, none contact anyone, **and none returns regulated data about a natural person.** That last point is the boundary that separates this module from its two siblings.

The writes on the same URL prefix — `client_profile_update`, `client_compliance_run`, `client_consent_request` — are separate modules with their own grants. A `client_read` grant is not a grant to any of them.

## 2. WHAT IT DOES NOT DO

It does not write. No row changes, nothing is sent, nothing is recorded — including no record that the read happened.

It does not prove anything about the client's situation. It reports what Burkham has on file. See shared rule 1.

It does not verify the client exists. That already happened. The mount guard runs before any handler here, so by the time a handler executes the client is known to exist and to belong to the caller's tenant.

**It does not return owners, credit or the ACH authorisation.** Those are `client_read_pii` and `client_read_credit`. An agent holding only this grant that needs them must say so rather than inferring them from what it can see.

## 3. WHAT THE INPUTS MEAN

| Input | Meaning |
|---|---|
| `clientId` (path) | The client. Guaranteed to exist and to be the caller's by the time a handler runs |

No other input. Nothing here takes a query parameter.

**Both mount paths are the same router.** `/api/clients/:clientId` and `/api/v1/clients/:clientId` are identical. Anything true of one is true of the other.

## 4. THE CORRECT SEQUENCE

There is none. The six are independent reads with no ordering requirement and no state between them.

What matters is what happens after. A read gathering context for a placement, a submission or a recommendation feeds a decision — and shared rule 1 governs everything the read returns from that point on.

## 5. WHAT FAILURE LOOKS LIKE

**Read the error code, never the status alone.** A 404 carries two unrelated meanings on this router and the status cannot tell them apart.

| Code | Meaning |
|---|---|
| `NOT_FOUND` | No such client, or not yours. From the mount guard, before any handler runs |
| `CLIENT_NOT_FOUND` | Same, from `GET /` — a delete racing the guard |

Both mean the same thing here: **stop.** There is nothing to report about. Neither is an absence in the sense of shared rule 1 — an absent client is a fact about the world, not about the records.

| Response | Meaning |
|---|---|
| 200 | The read ran. Check the body before reporting it as a result |
| 403 | The caller lacks `business:read` |
| 404 | No such client. Stop |
| 500 | Includes a missing tenant context, which surfaces here rather than as a 401 |

**Empty results are real answers, not errors.** `/documents` and `/acknowledgments` carry a basis when empty — `no_documents_on_record`, `no_acknowledgments_on_record`. Report it. Shared rules 2 and 3.

`/compliance` and `/compliance/status` return a `complianceScore` computed from whatever checks exist. **A score computed from no checks is not a passing score.** Read `checks` before reporting the number.

`/repayment` returns `nextPayment: null` when there is no active plan. That is no plan on record, not a client with nothing to pay.

## 6. RETRY VS ESCALATE

**Retry freely.** All six are pure reads. Nothing is written, nothing is sent, and a retry after a timeout costs nothing and duplicates nothing.

This is a property of this module, not of the URL prefix. It does not extend to `client_compliance_run` or `client_consent_request` — the first persists a check per call, the second sends an email per call.

## 7. NEVER

**Never act on an absence.** The single most important rule for this module. No documents, no acknowledgments, no repayment plan — each is a fact about Burkham's records. An agent that turns one into a claim about the client has manufactured a finding.

**Never report an empty result without its basis.** Shared rule 2.

**Never paraphrase a basis.** Shared rule 3. `no_documents_on_record` is the answer; "nothing on file for this client" is a summary and "the client has not provided documents" is a judgement.

**Never read a compliance score without its checks.** A score over an empty check list is arithmetic, not a compliance state.

**Never present this data as verified.** It is what was recorded. Documents carry `sha256Hash` and `cryptoTimestamp`, but **this module does not verify them** — the fields are returned as stored. Verification happens in the compliance manifest.

**Never infer what you cannot read.** Shared rule 1b. If a decision needs owners, credit or the ACH authorisation, this grant does not reach them. Say so, and do not reason toward them from what is visible.

## 8. WHICH LAWS THIS TOUCHES

`compliance/consumer-privacy-rights-v1` — every record readable here is personal data subject to access and deletion requests, even though none of it is a natural-person identifier.

`compliance/fair-treatment-in-routing-v1` — where a read feeds a routing or recommendation decision, everything that entry says about inputs applies to what this module returns.

**No bureau entry applies.** `compliance/bureau-report-handling-v1` governs `client_read_credit`, not this module. Nothing here is bureau-derived.

**On sensitivity.** This is the least sensitive of the three read modules by design: business-level facts and the firm's own records about the engagement. That is why it carries `business:read` alone, and why a grant to it is not a step towards the other two.

## PROVENANCE

**From the code, read at `fcc46ab`:** the six endpoints and their permission, the mount guard as the tenancy boundary, the two 404 codes, the bases on `/documents` and `/acknowledgments`, the `/v1` alias, the compliance score being computed from whatever checks exist.

**Decided by the founder, 2 September 2026:** the three-way split and its boundary — regulated data about a natural person, not sensitivity in general; `auto_execute` for all three reads; report-and-continue on an absence.

**Split from `client_read` 1.2 on 2 September 2026, updated to 1.4 the same day** when the last empty results gained a basis and shared rules 1a and 1b were added.

**Split note.** §§2, 4 and 6 are inherited unchanged. §§1, 3, 5, 7 and 8 are narrowed to the six endpoints this grant reaches, and every reference to `/owners`, `/timeline`, `/ach-authorization` and `/credit/*` is removed — an agent holding this grant should not be reading about endpoints it cannot call.

## OPEN

**The 404 carries two meanings across the router.** On this module both mean "no such client", so the ambiguity does not bite here — it bites on `client_read_pii`, where `ACH_AUTHORIZATION_NOT_FOUND` shares the status. Recorded here so the three manuals agree.

**`client_reassign` is defined and not built.** `advisorId` and `status` were removed from the update surface on 2 September and no endpoint replaces them yet. `status` in particular needs transition rules before an endpoint exists.
