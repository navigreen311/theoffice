# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `client_read_pii`
**Endpoints:** 3 GETs under `/api/clients/:clientId` and `/api/v1/clients/:clientId`
**Permission:** `business:read` **and** `business:read:pii`
**Version:** 1.3 — drafted 2 September 2026, against CapitalForge `ebe3f5d`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Sections 1, 2 and 3 govern most of what this module returns, and they are not repeated here.

**This is the most sensitive read grant in CapitalForge.** It returns identifiers belonging to named people. Grant it narrowly.

## 1. WHAT IT DOES

Reads natural-person identifiers attached to a client.

| Endpoint | Returns |
|---|---|
| `GET /owners` | Beneficial owners: names, ownership percentages, titles, email, dates of birth, addresses, **the last four digits of the SSN**, KYC status |
| `GET /timeline` | Ledger events for this client, whose payloads carry **consent evidence references and IP addresses** |
| `GET /ach-authorization` | The bank authorisation on file |

Three separate calls, one module. They share a blast radius: all read, none write, none contact anyone, and **each returns data about a person rather than about a business.**

`/ach-authorization` is here by decision rather than by formal category. It is an authorisation against a business account — but on a small business the owner and the business are effectively the same person, and personal guarantees are everywhere in this venture. The formal distinction does not survive contact with the product.

The rest of the client file is `client_read`. Credit is `client_read_credit`. A grant to this module is not a grant to either.

## 2. WHAT IT DOES NOT DO

It does not write. No row changes, nothing is sent, nothing is recorded — including no record that the read happened. **Reading a date of birth leaves no trace.**

It does not prove anything about the client's situation. It reports what Burkham has on file. See shared rule 1.

It does not verify the client exists. That already happened. The mount guard runs before any handler here, so by the time a handler executes the client is known to exist and to belong to the caller's tenant.

**It does not return the full social security number.** `/owners` returns `ssnLast4`. The full `ssn` column exists on the record and was returned until 2 September 2026; the select is explicit now, so a column added to `BusinessOwner` cannot silently join the response.

## 3. WHAT THE INPUTS MEAN

| Input | Meaning |
|---|---|
| `clientId` (path) | The client. Guaranteed to exist and to be the caller's by the time a handler runs |

No other input. Nothing here takes a query parameter.

**Both mount paths are the same router.** `/api/clients/:clientId` and `/api/v1/clients/:clientId` are identical. Anything true of one is true of the other.

## 4. THE CORRECT SEQUENCE

There is none. The three are independent reads with no ordering requirement and no state between them.

What matters is what happens after. A read gathering context for a placement, a submission or a recommendation feeds a decision — and shared rule 1 governs everything the read returns from that point on.

## 5. WHAT FAILURE LOOKS LIKE

### The 403 is the failure to expect

**A 403 here means the caller holds `business:read` but not `business:read:pii`, and it is the most likely failure this module produces.**

Until 2 September 2026 there was no permission gate on this router at all. A `readonly` session and a `client` portal session reached dates of birth, IP addresses and the ACH authorisation with exactly the same permission as an advisor, because one permission covered a legal name and a social security number alike. Neither role holds `business:read:pii` now, so both get 403 on all three endpoints.

**A 403 is not an absence.** It says nothing about whether owners exist, whether an authorisation is on file, or anything else about the client. Shared rule 1 does not apply to it, and an agent that reports "no owners on file" after a 403 has manufactured a finding out of its own lack of permission. Report the 403 as what it is: this grant does not reach this data.

### The 404 carries two unrelated meanings

**Read the error code, never the status alone.**

| Code | Meaning |
|---|---|
| `NOT_FOUND` | No such client, or not yours. From the mount guard, before any handler runs |
| `ACH_AUTHORIZATION_NOT_FOUND` | The client exists. No authorisation is on file |

This is where shared rule 1 inverts if the code is ignored. `NOT_FOUND` is a fact about the world — there is no such client. `ACH_AUTHORIZATION_NOT_FOUND` is a fact about the records. An agent that treats the first as the second reports "no ACH authorisation on file" about a client that does not exist.

On `ACH_AUTHORIZATION_NOT_FOUND`: report "no ACH authorisation on file for this client" and continue. It is not a blocker for a read. It blocks anything that would *use* the authorisation, and that is a different call.

On `NOT_FOUND`: stop. There is nothing to report about.

| Response | Meaning |
|---|---|
| 200 | The read ran. Check the body before reporting it as a result |
| 403 | The caller lacks `business:read:pii`. See above — this is the expected failure |
| 404 | Read the code |
| 500 | Includes a missing tenant context, which surfaces here rather than as a 401 |

**Empty results are real answers, not errors.** `/owners` carries `basis: 'no_owners_on_record'` when empty. Report it. Shared rules 2 and 3.

`/timeline` returns `[]` with `meta.total` and no basis. Report it as no events recorded, and do not infer why.

## 6. RETRY VS ESCALATE

**Retry freely.** All three are pure reads. Nothing is written, nothing is sent, and a retry after a timeout costs nothing and duplicates nothing.

This is a property of this module, not of the URL prefix. It does not extend to `client_compliance_run` or `client_consent_request` — the first persists a check per call, the second sends an email per call.

## 7. NEVER

**Never act on an absence.** No owners recorded, no authorisation on file, no timeline events — each is a fact about Burkham's records. An agent that turns one into a claim about the client has manufactured a finding.

**Never treat a 403 as an absence.** It is the failure this module produces most often and it means the grant does not reach the data, not that the data is not there.

**Never report an empty result without its basis.** Shared rule 2.

**Never paraphrase a basis.** Shared rule 3. `no_owners_on_record` is the answer; "the client has not provided owner details" is a judgement about the client.

**Never treat a 404 on `/ach-authorization` as the client not existing.**

**Never carry this data further than the answer requires.** A date of birth read to answer one question does not become context for the next. Ownership percentages, addresses and `ssnLast4` should not appear in a summary, a log line, a message to a client, or anything handed to a third party. If a downstream step needs them, that step needs its own grant.

**Never reconstruct an identifier.** `ssnLast4` is four digits by design. Combining it with anything else to narrow the full number is the disclosure this module exists to prevent.

**Never present this data as verified.** It is what was recorded. `kycStatus` on an owner records the outcome of a check that ran; it is not a re-verification at read time.

## 8. WHICH LAWS THIS TOUCHES

`compliance/consumer-privacy-rights-v1` — **the governing entry for this module.** Every record here is personal data about a named individual, subject to access and deletion requests. Reading it is a processing activity.

`compliance/fair-treatment-in-routing-v1` — where a read feeds a routing or recommendation decision, everything that entry says about inputs applies. Dates of birth and addresses are exactly the inputs that entry exists to keep out of a routing decision.

**Note — what is behind this grant.**

`/owners` returns beneficial owner names, ownership percentages, dates of birth, addresses and `ssnLast4`.

`/timeline` returns ledger events whose payloads carry consent evidence references and IP addresses.

Eight handlers on this router were cross-tenant readable until 1 September 2026 and are now behind the mount guard. Until 2 September there was no permission gate at all. **This module is the reason both were fixed**, and the grant is now a deliberate act rather than a side effect of reading a client's name.

## PROVENANCE

**From the code, read at `ebe3f5d`:** the three endpoints and their permissions, the explicit select on `/owners` and its column list, the two 404 codes, the basis on `/owners`, the absence of a basis on `/timeline`, the mount guard, the `/v1` alias.

**Decided by the founder, 2 September 2026:** the three-way split and its boundary; `/ach-authorization` belonging here despite being formally a business authorisation; `auto_execute` with narrow grants rather than `propose`; withholding `business:read:pii` from `readonly` and `client`.

**Split from `client_read` 1.2 on 2 September 2026.** §§2, 4 and 6 are inherited unchanged. §5 leads with the 403 by founder instruction: both affected roles previously reached this data with an advisor's permission, and it is the failure an agent will actually hit.

## OPEN

**The 404 carries two meanings and only the error code separates them.** A 200 with an explicit empty state and a basis — matching what `client_read_credit`'s `/credit/recommendations` already does — would make them distinguishable by shape rather than by reading a code correctly. Raised for CapitalForge; this manual documents current behaviour.

**`/timeline` has no basis on an empty result.** `/owners` gained one on 2 September; `/timeline` did not, and adding it would make shared rule 2 uniform across this module.

**Nothing records that this data was read.** §2 states it as a fact about the module. Whether a read of dates of birth and IP addresses should leave an audit trail is a policy question nobody has answered, and the absence is invisible from the response.
