# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `client_read`
**Endpoints:** 13 GETs under `/api/clients/:clientId` and `/api/v1/clients/:clientId`
**Version:** 1.0 — drafted 2 September 2026, against CapitalForge `3d93cff`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Sections 1, 2 and 3 govern most of what this module returns, and they are not repeated here.

## 1. WHAT IT DOES

Reads a client's file — identity, owners, credit, documents, acknowledgments, consent, compliance state, repayment, ACH authorisation, timeline.

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

| Response | Meaning |
|---|---|
| 200 | The read ran. Check the body for a declared basis before reporting it as a result |
| 400 | A required parameter is missing — chiefly `profileType` |
| 403 | Missing the permission the endpoint requires |
| 404 | Depends on the endpoint. See below |
| 422 | `/consent/request` only: no owner on file |

**A 404 here does not mean the client does not exist.** The mount guard already proved it does. On `/ach-authorization` it means no authorisation is on file — a fact about the records, not about the client, and shared rule 1 applies.

Report it as "no ACH authorisation on file for this client" and continue. It is not a blocker for a read. It blocks anything that would *use* the authorisation, and that is a different call.

**Three empty results are real answers, not errors:**

- `/owners` returning `[]` — no owners are recorded
- `/credit/recommendations` returning `[]` with `basis: 'no_credit_profile_on_record'` — nobody has pulled this client's credit
- `/documents`, `/acknowledgments` returning `[]` — nothing on file

Each is reported by its basis, never as emptiness alone. Shared rules 2 and 3.

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

**Note.** `/owners` returns beneficial owner names, ownership percentages, dates of birth, addresses and encrypted SSN. Eight handlers in this module were cross-tenant readable until 1 September 2026 and are now behind the mount guard. The data is as sensitive as anything in the system and the grant should reflect that.

## PROVENANCE

**From the code, read at `3d93cff`:** the thirteen endpoints, the mount guard as the tenancy boundary, `profileType` being required and why, the 404 on `/ach-authorization`, the declared basis on `/credit/recommendations`, the absence of point-impact estimates, the `/v1` alias.

**Decided by the founder, 2 September 2026:** report-and-continue on the 404; the basis rule; the never list; splitting `client_read` from the three write modules.

**Raised, not resolved:** the 404 overloading two meanings — see below.

## OPEN

**The 404 carries two meanings.** "No authorisation on file" and "no such client" return the same status, and only the mount guard's existence tells a consumer which applies. That is knowledge, not shape.

A 200 with an explicit empty state and a basis — matching what `/credit/recommendations` already does — would make the two distinguishable without the consumer having to know how the router is mounted. Raised for CapitalForge; this manual documents the current behaviour.

**`client_reassign` is defined and not built.** `advisorId` and `status` were removed from the update surface on 2 September and no endpoint replaces them yet. `status` in particular needs transition rules before an endpoint exists.

---

# APPENDIX — VERIFICATION

Checked against CapitalForge `3d93cff` on 2 September 2026. Every claim in the manual above was traced to code. **Corrections are proposed here, not applied above** — the manual is the author's.

Nine claims are exact and load-bearing: the thirteen endpoints, the `/v1` alias being the same router, `profileType` required and its reason, the FICO/PAYDEX scale collapse, no point-impact estimates, no write and no audit record of the read, pure-read retry safety, `no_credit_profile_on_record` as the literal basis string, and the mount guard as the tenancy boundary.

Seven corrections follow, in the order I would make them.

## A. `consent` is listed as something this module reads. It is not.

§1 says the module reads "identity, owners, credit, documents, acknowledgments, **consent**, compliance state, repayment, ACH authorisation, timeline."

There is no consent endpoint among the thirteen. `consentRecord` is never queried in `client-detail.routes.ts`. The only consent-related handler on this router is `POST /consent/request`, which is `client_consent_request` — a different module, and a write that sends email.

An agent told `client_read` returns consent will look for it, not find it, and may reach for the write. **Proposed:** strike `consent` from the list.

## B. There is no 403. The router has no permission middleware.

§5 lists "403 — Missing the permission the endpoint requires."

`clientDetailRouter` installs no `requirePermissions` or `requirePermission`, and none is applied to it at the mount. Compare `documentRouter`, which gates its handlers on `PERMISSIONS.COMPLIANCE_READ` explicitly. Authentication is assumed: `getTenantId` throws `'Tenant context is missing — authentication middleware did not run.'` if `req.tenant` is absent, which surfaces as a **500**, not a 401 or 403.

Two consequences worth the author's attention:

- The 403 row should be struck, or replaced with "**500** — authentication middleware did not run. This is a deployment fault, not a permission denial."
- More importantly: **this module has no permission gate of its own.** Everything protecting it is the tenancy guard and whatever authenticates upstream. Given §8's note that `/owners` returns dates of birth and SSN, that is worth stating in the manual rather than leaving to inference — and worth raising as a defect in CapitalForge.

## C. Three of the four "empty results" have no basis to report.

§5 lists four empty results and says "Each is reported by its basis, never as emptiness alone."

Only one emits a basis. `basis:` appears in exactly two places in the file, both in `/credit/recommendations`: `'no_credit_profile_on_record'` when there is no pull, and `'latest_credit_profile'` when there is.

`/owners`, `/documents` and `/acknowledgments` return `meta: { total: 0 }` and nothing else. There is no basis string for an agent to pass through, so the instruction cannot be followed for three of the four cases as written.

**Proposed:** say what is true — one endpoint declares a basis; the other three return `meta.total` and the agent must supply the sentence itself ("no owners are recorded for this client"), which is still shared rule 2 in spirit but is a different instruction. **And raise for CapitalForge:** adding `basis` to the other three would make the rule uniform and is a small change.

## D. The 404 claim needs one qualification, and it is the important one.

§5 says "**A 404 here does not mean the client does not exist.** The mount guard already proved it does."

That is right about the handlers and wrong about what a consumer sees. Two things:

1. **The guard itself returns 404** — `{ code: 'NOT_FOUND', message: 'No business found with id …' }` — for a client that does not exist or belongs to another tenant. It is emitted for the same URL, before any handler. So a 404 from `/api/clients/:clientId/...` **can** mean "no such client", and an agent that treats every 404 as "no record of this type" will misread a genuinely missing client as an empty result.
2. `GET /` retains its own `CLIENT_NOT_FOUND` 404 (`client-detail.routes.ts:257`). Unreachable behind the guard, kept as defence against a delete racing the guard and against the router being mounted without it. Present in the code an agent's tooling may be generated from.

The distinguishing signal exists and it is the **error code**, not the status: `NOT_FOUND` (guard, no such client) / `CLIENT_NOT_FOUND` (handler, no such client) / `ACH_AUTHORIZATION_NOT_FOUND` (client exists, no authorisation).

**Proposed:** replace the blanket sentence with the code table. This is the single correction I would make first — the current wording tells an agent to treat a real "client not found" as an absence, which is shared rule 1 inverted.

## E. The 422 row belongs to a different module.

§5 lists "422 — `/consent/request` only: no owner on file." `/consent/request` is not one of the thirteen. No 422 arises from this module.

**Proposed:** strike it, or mark it explicitly as a cross-reference to `client_consent_request`.

## F. "Eight handlers … cross-tenant readable until 1 September 2026" — correct, and worth naming.

Verified at `a34cd2d` (2026-09-01 12:18 PDT), which names all eight: `/owners`, `/ach-authorization`, `/credit/personal`, `/credit/business`, `/credit/history`, `/credit/recommendations`, `/acknowledgments`, `/timeline`. Five siblings — `/`, `/repayment`, `/compliance`, `/compliance/status`, `/documents` — already carried `tenantId`. The router-level gate was generalised to the mount table 10 minutes later at `1aa2ad6`, which closed six further reads elsewhere.

Two additions the author may want:

- **`/timeline` reads ledger events "whose payloads carry consent evidence references and IP addresses"** (from `a34cd2d`). §8 names `/owners` as the sensitive endpoint; `/timeline` is the second one and is not mentioned.
- **`/owners` returns the `ssn` column, not only `ssnLast4`.** The query is `findMany({ where: { businessId } })` with no `select`, so every column is returned. The manual says "encrypted SSN", which is accurate — but a reader may assume a truncated field is returned. **Raise for CapitalForge:** an explicit `select` on this handler is a five-minute change and closes the gap between "the grant is sensitive" and "the response is minimal."

## G. "Documents carry `sha256Hash` and `cryptoTimestamp` where verification is possible" — true, but nothing verifies them here.

§7's last line is right that the fields exist on `Document`. It may read as though this module checks them. It does not: verification runs in `ComplianceDossierService._verifyDocumentTimestamp`, and `GET /documents` returns rows unverified, with no `timestampIntegrity` field.

**Proposed:** "Documents carry `sha256Hash` and `cryptoTimestamp`, but **this module does not verify them** — the fields are returned as stored. Verification happens in the compliance manifest."

## One thing outside the manual's scope, for the record

The commit that closed the tenancy holes says "Seventeen handlers hang off this router." I count sixteen at `3d93cff` — 13 GETs, 1 PATCH, 2 POSTs. Either one was removed since, or the count was off. It does not affect the manual, which says thirteen GETs and is correct.
