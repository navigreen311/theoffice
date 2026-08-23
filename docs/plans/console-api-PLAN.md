# Console, increment 1 — Human Identity and the Operations API — PLAN

Master prompt Part 17 (Administration Console) and Part 14 (Human Capacity, Identity and
Separation of Duties).

## Why this before any UI

`broker/` is a library. The client library calls its functions in-process; there are no
HTTP routes and **no human identity at all**. Every governance action built so far —
revoke, reinstate, decide a proposal, resolve a disposition, reverse a hard cap — takes a
`UUID` for the actor and trusts the caller about the role.

A Next.js app on top of that is a mockup. Worse, it would be a mockup that looks like a
control surface.

So this increment builds what the console is a *view over*: humans who exist, roles that
are checked, and an API whose authority is **narrower than the domain's, never wider**.

## The design risk, stated plainly

The console is the most dangerous thing in this repository to build carelessly.

Every control so far is enforced in a guarded function: revocation checks authority,
disposition demands a reason, `assign_shift` refuses an unflushed predecessor,
certification is a live state. **An API that reaches past those functions to the tables
would undo all of it** — and it would look like a feature while doing so.

Two rules follow, and both are tested:

1. **The API calls the same guarded functions the domain uses.** It never issues its own
   `UPDATE`. There is no second path to a table.
2. **There is no endpoint for things a human must not do directly.** No writing a
   certification state, no clearing a flush, no editing the ledger, no setting a trust
   tier past its certified ceiling. `test_the_api_is_not_a_bypass` enumerates them.

The console is a client of The Office, not a back door into it.

---

## Human identity (Part 14)

| Table | Purpose |
|---|---|
| `office_human` | who exists, how they authenticate, token **hash** never token |
| `office_human_role` | `venture_operator` \| `compliance_officer` \| `ivan`, optionally scoped to a venture |
| `signoff_record` | Gate sign-offs, **bound to an artifact hash** |

**Artifact-hash binding is the point of `signoff_record`.** Part 14: "artifact change
voids signature." A sign-off records the hash of what was signed; if the artifact changes,
the signature is void by comparison rather than by somebody remembering to revoke it.
Same principle as certification staleness.

**Role scoping.** A venture operator is an operator *of a venture*, not of the platform.
`office_human_role.venture_id` scopes it; `NULL` means all ventures and is what Ivan
holds. A venture operator cannot revoke in a venture they do not operate — which the
domain's authority matrix could not express, because it only ever saw a role string.

`ASSUMPTION` — **bearer tokens, not SSO.** Part 14 declares `auth_method: sso_mfa |
mfa_only`, and real SSO is an external provider that does not exist yet (same class as
Vault, Phase 0.3). The column records the intended method; the API authenticates a hashed
bearer token. To change: implement the OIDC exchange and keep everything downstream.

---

## API surface

**Read** — the screens are views over these:
`/health` (control freshness) · `/agents` · `/agents/{id}` · `/ventures` ·
`/ventures/{id}/capacity` (the three numbers) · `/ventures/{id}/forge-map` ·
`/ventures/{id}/gates` · `/audit` · `/audit/chain` · `/incidents` · `/proposals` ·
`/dispositions` · `/instructions/{forge}/{module}`

**Write** — each delegates to its guarded function and enforces role *and* venture scope:
`POST /revocations` · `POST /revocations/{id}/reinstate` ·
`POST /proposals/{id}/decide` · `POST /dispositions/resolve` ·
`POST /instructions` · `POST /ventures/{id}/reverse-hard-cap` (Ivan only) ·
`POST /signoffs`

**Deliberately absent**, and asserted absent by a test: anything that writes a
certification state, clears a flush, assigns a shift bypassing the flush check, edits the
ledger or audit log, or grants a tier above the certified ceiling.

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| A1 | an unauthenticated request is refused | |
| A2 | a suspended human is refused | status is live, not cached in a token |
| A3 | a venture operator cannot act in a venture they do not operate | scope, not just role |
| A4 | `forge` revocation requires Ivan; operator and compliance officer refused | Part 1.4 matrix |
| A5 | reinstatement needs the same authority as revocation | no undoing a superior's stop |
| A6 | a disposition through the API still requires a reason | the guarded function, not a second path |
| A7 | a sign-off binds to the artifact hash | |
| A8 | changing the artifact **voids** the signature | Part 14 |
| A9 | SoD: `distinct_humans` refuses a second gate signed by the same human | |
| A10 | **the API exposes no route that writes certification, flush, ledger or audit** | not a bypass |
| A11 | every write endpoint is audited with the human as actor | humans sign, not agents |
| A12 | the three capacity numbers are served from the real generator | no parallel implementation |

## Out of scope

The Next.js console itself (increment 2). Real SSO. Pack authoring UI.
