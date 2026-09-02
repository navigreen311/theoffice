# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `client_read`
**Endpoints:** 13 GETs under `/api/clients/:clientId` and `/api/v1/clients/:clientId`
**Version:** 1.1 — drafted 2 September 2026, against CapitalForge `3d93cff`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Sections 1, 2 and 3 govern most of what this module returns, and they are not repeated here.

## 1. WHAT IT DOES

Reads a client's file — identity, owners, credit, documents, acknowledgments, compliance state, repayment, ACH authorisation, timeline.

Thirteen separate calls, one module. They share a blast radius: all read, none write, none contact anyone. The writes on the same URL prefix — `client_profile_update`, `client_compliance_run`, `client_consent_request` — are separate modules with their own grants. A `client_read` grant is not a grant to any of them.

## 2. WHAT IT DOES NOT DO

It does not write. No row changes, nothing is sent, nothing is recorded — including no record that the read happened.

It does not prove anything about the client's situation. It reports what Burkham has on file. See shared rule 1.

It does not verify the client exists. That already happened. The mount guard runs before any handler here, so by the time a handler executes the client is known to exist and to belong to the caller's tenant.

It does not estimate. `/credit/recommendations` attaches no point-impact figures, because predicting a score change needs a model this system does not have. An agent must not present a recommendation as quantified.

## 3. WHAT THE INPUTS MEAN

| Input | Meaning |
|---|---|
| `clientId` (path) | The client. Guaranteed to exist and to be the caller's by the time a handler runs |
| `profileType` (query, `/credit/history`) | `personal` or `business`. Required, deliberately |

`profileType` is the most likely first-call error in this module. It is not defaulted, and the reason is that personal and business scores run on different scales — FICO 300–850, PAYDEX 0–100. The endpoint once returned both in one series, so a PAYDEX of 80 sat beside a FICO of 762 under the same `month` and a caller plotting one axis read a 682-point collapse.

A call without it fails. That is the control working.

**Both mount paths are the same router.** `/api/clients/:clientId` and `/api/v1/clients/:clientId` are identical. Anything true of one is true of the other.

## 4. THE CORRECT SEQUENCE

There is none. The thirteen are independent reads with no ordering requirement and no state between them.

What matters is what happens after. A read gathering context for a placement, a submission or a recommendation feeds a decision — and shared rule 1 governs everything the read returns from that point on.

## 5. WHAT FAILURE LOOKS LIKE

**Read the error code, never the status alone.** A 404 on this module carries two unrelated meanings and the status cannot tell them apart.

| Code | Meaning |
|---|---|
| `NOT_FOUND` | No such client, or not yours. From the mount guard, before any handler runs |
| `CLIENT_NOT_FOUND` | Same, from `GET /` — a delete racing the guard |
| `ACH_AUTHORIZATION_NOT_FOUND` | The client exists. No authorisation is on file |

This is where shared rule 1 inverts if the code is ignored. `NOT_FOUND` is a fact about the world — there is no such client. `ACH_AUTHORIZATION_NOT_FOUND` is a fact about the records. An agent that treats the first as the second reports "no ACH authorisation on file" about a client that does not exist.

On `ACH_AUTHORIZATION_NOT_FOUND`: report "no ACH authorisation on file for this client" and continue. It is not a blocker for a read. It blocks anything that would *use* the authorisation, and that is a different call.

On `NOT_FOUND` or `CLIENT_NOT_FOUND`: stop. There is nothing to report about.

| Response | Meaning |
|---|---|
| 200 | The read ran. Check the body before reporting it as a result |
| 400 | A required parameter is missing — chiefly `profileType` |
| 404 | Read the code |
| 500 | Includes a missing tenant context, which surfaces here rather than as a 401 |

**THIS MODULE HAS NO PERMISSION GATE OF ITS OWN.** The router carries no permission middleware — unlike the document router, which requires `COMPLIANCE_READ`. Everything protecting `/owners` and `/credit/*` is the tenancy guard and upstream authentication. There is no 403 because nothing here can produce one.

**Empty results are real answers, not errors:**

- `/credit/recommendations` returns `[]` with `basis: 'no_credit_profile_on_record'` — nobody has pulled this client's credit. Report the basis. Shared rules 2 and 3.
- `/owners`, `/documents` and `/acknowledgments` return `[]` with `meta.total` and no basis string. Nothing distinguishes "none recorded" from any other reason for emptiness. Report them as "none on file" — do not infer why, and do not treat the absence as a finding about the client.

## 6. RETRY VS ESCALATE

**Retry freely.** All thirteen are pure reads. Nothing is written, nothing is sent, and a retry after a timeout costs nothing and duplicates nothing.

This is unusual in CapitalForge and it is a property of this module only. It does not extend to `client_compliance_run` or `client_consent_request` on the same URL prefix — the first persists a check per call, the second sends an email per call.

## 7. NEVER

**Never act on an absence.** The single most important rule for this module. No authorisation, no credit profile, no owners, no recommendations — each is a fact about Burkham's records. An agent that turns one into a claim about the client has manufactured a finding.

**Never report an empty result without its basis.** Shared rule 2.

**Never paraphrase a basis.** Shared rule 3. `no_credit_profile_on_record` is the answer; "insufficient information" is a judgement.

**Never quantify a recommendation.** No point-impact figure exists to attach.

**Never read `/credit/history` without `profileType`** and never combine the two profile types into one series. They are different scales.

**Never treat a 404 on `/ach-authorization` as the client not existing.**

**Never present this data as verified.** It is what was recorded. Documents carry `sha256Hash` and `cryptoTimestamp` where verification is possible; nothing else here is verified against anything.

## 8. WHICH LAWS THIS TOUCHES

`compliance/bureau-report-handling-v1` — `/credit/personal`, `/credit/business` and `/credit/history` return bureau-derived data. The entry governs what may be done with it: never shared outside the client's authorised viewers, never attached to a lender packet, never rendered as Burkham's own assertion of creditworthiness. Reading it here does not widen what may be done with it.

`compliance/fair-treatment-in-routing-v1` — where a read feeds a routing or recommendation decision, everything that entry says about inputs applies to what this module returns.

`compliance/consumer-privacy-rights-v1` — every record readable here is personal data subject to access and deletion requests.

**Note — two endpoints carry the most sensitive data in the system.**

`/owners` returns beneficial owner names, ownership percentages, dates of birth, addresses, and the full SSN column — the query has no `select`, so `ssn` is returned alongside `ssnLast4`.

`/timeline` returns ledger events whose payloads carry consent evidence references and IP addresses.

Eight handlers here were cross-tenant readable until 1 September 2026 and are now behind the mount guard. With no permission gate on the router, the grant is the only remaining control — and it should reflect what is behind it.

## PROVENANCE

**From the code, read at `3d93cff`:** the thirteen endpoints, the mount guard as the tenancy boundary, `profileType` being required and why, the 404 on `/ach-authorization`, the declared basis on `/credit/recommendations`, the absence of point-impact estimates, the `/v1` alias.

**Decided by the founder, 2 September 2026:** report-and-continue on the 404; the basis rule; the never list; splitting `client_read` from the three write modules.

**Corrected in 1.1, from a fact-check against `3d93cff`:** the 404 section, which had the inversion backwards; `consent` removed from §1, since no consent endpoint is among the thirteen; the 403 and 422 rows removed; the basis rule scoped to the one endpoint that carries a basis; `/timeline` and the full `ssn` column added to §8.

## OPEN

**The 404 carries two meanings and only the error code separates them.** A 200 with an explicit empty state and a basis — matching what `/credit/recommendations` already does — would make them distinguishable by shape rather than by reading a code correctly. Raised for CapitalForge; this manual documents current behaviour.

**Three endpoints return an empty array with no basis.** `/owners`, `/documents` and `/acknowledgments`. Adding one would make shared rule 2 uniform across the module.

**The router has no permission gate.** A policy decision, not a code one.

**`client_reassign` is defined and not built.** `advisorId` and `status` were removed from the update surface on 2 September and no endpoint replaces them yet. `status` in particular needs transition rules before an endpoint exists.

---

# APPENDIX — VERIFICATION OF 1.1

Checked against `3d93cff` on 2 September 2026, and re-checked against `45ae041` the same day.

## Every correction from the 1.0 appendix landed correctly

The seven proposed corrections are all present in 1.1 and all match the code at `3d93cff`. The §5 rewrite in particular is now the strongest section in the manual: it states the inversion in the direction that actually bites — *"an agent that treats the first as the second reports 'no ACH authorisation on file' about a client that does not exist"* — and gives the stop/continue rule per code. Nothing in 1.1 contradicts the code as of `3d93cff`.

## THREE STATEMENTS IN 1.1 WERE TRUE AT `3d93cff` AND ARE FALSE AT `45ae041`

Three of the OPEN items were fixed immediately after 1.1 was drafted, by founder instruction. **The manual is now behind the code by one commit**, and each of these is a claim an agent would act on.

### 1. The full SSN is no longer returned

**§8 says:** *"`/owners` returns … the full SSN column — the query has no `select`, so `ssn` is returned alongside `ssnLast4`."*

**At `45ae041`:** the query has an explicit `select` listing sixteen columns. `ssnLast4` is included; **`ssn` is not.** Nothing consumed the full number — no frontend component reads `.ssn`, and the only plaintext-SSN path in the system is the offboarding data export, which selects it deliberately and writes an audit row recording that the export contained them.

**Proposed replacement:** *"`/owners` returns beneficial owner names, ownership percentages, dates of birth, addresses and the last four digits of the SSN. The full `ssn` column was returned until 2 September 2026 and is not returned now; the select is explicit, so a column added to `BusinessOwner` does not silently join the response."*

### 2. The router has a permission gate

**§5 says:** *"THIS MODULE HAS NO PERMISSION GATE OF ITS OWN … There is no 403 because nothing here can produce one."* **The OPEN section repeats it.**

**At `45ae041`:** `clientDetailRouter.use(requirePermissions(PERMISSIONS.BUSINESS_READ))`. A caller without `business:read` now gets **403**.

This is the correction with the most consequence for an agent: 1.1 tells it no 403 can occur, so an agent seeing one will treat it as an unexpected failure rather than a missing permission it should report.

**Proposed replacement for §5:** restore a 403 row — *"403 — the caller lacks `business:read`"* — and replace the block with: *"This module requires `business:read`, and nothing finer. That is the floor rather than a considered ceiling: `/owners` and `/credit/*` return the most sensitive data in the system and are gated identically to the endpoint returning a client's name. A stricter split is proposed but not built — see `docs/callable-modules.md`."*

### 3. All four empty results now carry a basis

**§5 says:** *"`/owners`, `/documents` and `/acknowledgments` return `[]` with `meta.total` and no basis string."*

**At `45ae041`:** each returns `meta.basis` — `no_owners_on_record`, `no_documents_on_record`, `no_acknowledgments_on_record` when empty, and the record set read when not. Shared rule 2 is now uniform across the module.

**Proposed replacement:** fold all four into one bullet — *"Every empty result carries a basis. Report it. Shared rules 2 and 3."* — and strike the corresponding OPEN item.

## What did NOT change, and remains correctly documented

- The 404 overloading. §5's code table and the OPEN item both still hold; nothing about the status codes changed.
- `client_reassign` still defined and not built.
- Everything in §§1–4, 6, 7 and the rest of §8.

## One thing 1.1 says that the fixes make sharper rather than false

§8's closing line — *"With no permission gate on the router, the grant is the only remaining control"* — was the argument for the gate, and the gate now exists. But the sentence survives in a modified form worth keeping: **`business:read` does not distinguish `/owners` from `GET /`**, so within this module the grant is still the only control that separates a name from a date of birth. That is the split proposed in `docs/callable-modules.md` and not yet built.

**Recommend a 1.2** carrying the three replacements above. All three are one-paragraph edits, and the second is the one that would otherwise mislead an agent in production.
