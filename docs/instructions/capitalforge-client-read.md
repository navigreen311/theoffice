# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `client_read`
**Endpoints:** 13 GETs under `/api/clients/:clientId` and `/api/v1/clients/:clientId`
**Version:** 1.2 — drafted 2 September 2026, against CapitalForge `45ae041`
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
| 403 | The caller lacks `business:read` |
| 500 | Includes a missing tenant context, which surfaces here rather than as a 401 |

This module requires `business:read`, and nothing finer. That is a floor rather than a considered ceiling: `/owners` and `/credit/*` return the most sensitive data in the system and are gated identically to the endpoint returning a client's name. A stricter split is proposed and not built — see `docs/callable-modules.md`.

**Empty results are real answers, not errors:**

Every empty result carries a basis. `no_credit_profile_on_record`, `no_owners_on_record`, `no_documents_on_record`, `no_acknowledgments_on_record`. Report it. Shared rules 2 and 3.

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

`/owners` returns beneficial owner names, ownership percentages, dates of birth, addresses and the last four digits of the SSN. The full `ssn` column was returned until 2 September 2026 and is not returned now; the select is explicit, so a column added to `BusinessOwner` cannot silently join the response.

`/timeline` returns ledger events whose payloads carry consent evidence references and IP addresses.

Eight handlers here were cross-tenant readable until 1 September 2026 and are now behind the mount guard, and the router requires `business:read` since 2 September. But `business:read` does not distinguish `/owners` from `GET /` — within this module the grant is still the only control separating a name from a date of birth.

## PROVENANCE

**From the code, read at `3d93cff`:** the thirteen endpoints, the mount guard as the tenancy boundary, `profileType` being required and why, the 404 on `/ach-authorization`, the declared basis on `/credit/recommendations`, the absence of point-impact estimates, the `/v1` alias.

**Decided by the founder, 2 September 2026:** report-and-continue on the 404; the basis rule; the never list; splitting `client_read` from the three write modules.

**Corrected in 1.2, after three OPEN items were fixed at `45ae041`:** the router now requires `business:read` and can return 403; all four empty results carry a basis; the full `ssn` column is no longer returned.

**Corrected in 1.1, from a fact-check against `3d93cff`:** the 404 section, which had the inversion backwards; `consent` removed from §1, since no consent endpoint is among the thirteen; the 403 and 422 rows removed; the basis rule scoped to the one endpoint that carries a basis; `/timeline` and the full `ssn` column added to §8.

## OPEN

**The 404 carries two meanings and only the error code separates them.** A 200 with an explicit empty state and a basis — matching what `/credit/recommendations` already does — would make them distinguishable by shape rather than by reading a code correctly. Raised for CapitalForge; this manual documents current behaviour.

**`business:read` does not distinguish a name from a social security number.** A three-way split is proposed and not built — `client_read` for business facts, `client_read_pii` for `/owners` and `/timeline`, `client_read_credit` for the four `/credit/*`. The boundary is whether the response is regulated data about a natural person, not whether it is sensitive in general. All three would stay `auto_execute`: making a read wait for a human trains people to approve without looking, and does not reduce what a grant holder can see. The control is who holds the grant.

**`/ach-authorization` sits on the boundary.** It returns a bank authorisation for a business rather than a natural person, so it falls in `client_read` — but an account authorisation reads as personal to most people. If it moves, it moves to `client_read_pii`.

**`client_reassign` is defined and not built.** `advisorId` and `status` were removed from the update surface on 2 September and no endpoint replaces them yet. `status` in particular needs transition rules before an endpoint exists.

---

# APPENDIX — VERIFICATION OF 1.2

Checked against `45ae041`, which 1.2 names, and re-checked against `ebe3f5d`, committed the same day.

## The three 1.1 corrections all landed

`business:read` and the 403 row, all four bases, and `ssnLast4` in place of the full column are each stated correctly in 1.2 and each matches `45ae041`. §8's closing paragraph carries the sharpened version of the old argument — *"`business:read` does not distinguish `/owners` from `GET /`"* — which was exactly right at `45ae041`.

## THE SPLIT IS BUILT, WHICH CHANGES FOUR STATEMENTS

1.2 describes the split as proposed and not built. It was built at `ebe3f5d` on founder instruction, with one change to the proposal.

### 1. There are three module ids, not one

`client_read` is no longer thirteen endpoints. `client_read_pii` and `client_read_credit` are separate ids with separate permissions, and a `client_read` grant now reaches **six** endpoints rather than thirteen: `/`, `/documents`, `/acknowledgments`, `/compliance`, `/compliance/status`, `/repayment`.

This affects the header, §1, §5 and the second OPEN item. **A manual describing thirteen endpoints under one id now describes a grant that does not exist.**

### 2. `/ach-authorization` moved, and the manual predicted the wrong outcome

1.2's OPEN says: *"It returns a bank authorisation for a business rather than a natural person, so it falls in `client_read` — but an account authorisation reads as personal to most people. If it moves, it moves to `client_read_pii`."*

It moved. The founder's reasoning, recorded because it generalises beyond this endpoint: on a small business the owner and the business are effectively the same person, and personal guarantees are everywhere in this venture, so the formal distinction does not survive contact with the product.

`/ach-authorization` requires `business:read:pii`.

### 3. Two roles lost access, deliberately

`business:read:pii` and `business:read:credit` are held by super admin, tenant admin, compliance officer and advisor. **`readonly` and `client` hold neither.**

Both previously reached dates of birth and bureau data with exactly the same permission as an advisor. A `readonly` or `client` session now gets **403** on `/owners`, `/timeline`, `/ach-authorization` and all four `/credit/*`. That is a new failure mode the manual does not mention, and the one an agent is most likely to actually meet.

### 4. The 403 row must name which permission

§5 says "403 — The caller lacks `business:read`". There are now three permissions and three ways to earn a 403, and the response names the missing one.

**Proposed row:** *"403 — the caller lacks `business:read`, or `business:read:pii` for `/owners`, `/timeline` and `/ach-authorization`, or `business:read:credit` for the four `/credit/*`. The body names the missing permission."*

## What did not change

The 404 overloading and its OPEN item; `client_reassign`; `profileType`; the basis rule; every NEVER; §§2, 4, 6; and all three compliance entries in §8. §8's sensitivity note is still correct and is now enforced rather than only documented.

## Recommended for 1.3

The cleanest shape is **three manuals**, not one with three sections. A grant names one id, and a manual an agent reads should describe what that grant reaches and nothing else. `client_read` keeps most of this text; `client_read_pii` and `client_read_credit` inherit §§2–4, 6 and 7 wholesale and differ in §1, §5 and §8.

If that is too much for now, a 1.3 of this manual carrying the four corrections above is honest and usable — provided the header stops saying thirteen endpoints under one id.

**One thing worth carrying into every other manual**, now recorded in `docs/callable-modules.md` as a rule rather than a note: all three ids are `auto_execute`. Making a read wait for a human trains people to approve without looking and does not reduce what a grant holder can see, because the grant already decided that. For a read, the control is who holds the grant. `propose` is for calls that change something or reach somebody.

**And the second rule, which nearly caught us here:** path depth is not evidence of blast radius. `/credit/*` looked like a natural group because of the path and happens to be one — but `/timeline` sits at the top level and belongs with `/owners`, while `/repayment` sits at the top level and belongs with the business facts. Grouping by prefix would have put `/timeline` in the wrong module and nothing would have failed.
