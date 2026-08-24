# Operability — PLAN

Four gaps between "every screen exists" and "this can be operated". Named in that order
because the first one is why a deployed Office currently needs somebody with a shell.

---

## 1. Human and role management

**The gap:** there is no route that creates a human or grants a role. `create_human` and
`grant_role` exist in `broker/humans.py` and are called by tests and by
`console-smoke.sh`. On the deployment shipped last increment, **the second operator can
only be created by someone with a shell on the VM.**

This is the most privilege-sensitive surface in the console, so the rules are the point.

### Granting requires a strictly stronger role

`venture_operator(1) < compliance_officer(2) < ivan(3)`. You may grant a role **strictly
weaker than your own**. So `ivan` grants the other two, `compliance_officer` grants
`venture_operator`, and a `venture_operator` grants nothing.

Not "stronger or equal", which would let a `compliance_officer` mint another
`compliance_officer` and make the role self-propagating — at which point the hierarchy
describes nothing.

### Nobody grants themselves a role

Including `ivan`, who does not need to. The value is not that it stops an attack — a
holder of `ivan` has other paths — it is that **every role anyone holds was granted by
somebody else, and the audit log says who.** A self-grant is the one edge that breaks
that property, and it costs nothing to forbid.

The bootstrap CLI is the single, documented exception.

### The last active `ivan` cannot be suspended or demoted

Not a security control; an availability one. A system with no administrator cannot
appoint one, and the recovery is a shell on the database — which is the thing this whole
item exists to remove.

### Bootstrap is a CLI, not a route

`python -m broker human create --name … --email … --role ivan`, and it **refuses once any
human exists**. An unauthenticated route that creates the first human is a permanent
backdoor wearing a bootstrap label. A CLI on the host is honest: shell access is already
total, so this adds no authority anyone lacked.

### Tokens

Reissue replaces the hash and returns the plaintext once. A human may reissue their own;
`ivan` may reissue anyone's. That is token rotation, which the API has never had.

---

## 2. Reinstatement and incident resolution

Two write-only loops.

**Reinstatement.** `POST /api/revocations/{id}/reinstate` exists and is pinned. There is
no way to see what is revoked — no GET — so lifting one needs the id from a database
query. Adds `GET /api/revocations` and a screen.

**Incidents.** `/api/incidents` is GET-only, and `historical_record.record_type` includes
`incident_resolved` that **nothing writes** — a dangling enum, which is a smaller version
of the same rot Gate 6's hardcoded list had. Resolving requires a reason and writes the
historical record.

An incident is not deleted and its severity is not editable. Resolution is an append.

---

## 3. Sweep the stale gap documentation

Four `## Known gaps` sections describe a system that no longer exists:

| Doc | Claims | Actually |
|---|---|---|
| `call-path.md` | Vault not implemented | shipped last increment |
| `call-path.md` | trust tier "recorded, not enforced" | enforced — creates a proposal, raises `RequiresApproval` |
| `call-path.md` | no rate limiting | `broker/limits.py`, enforced in the path |
| `certification.md` | authoring UI does not exist | `/instructions` |
| `governance.md` | manifest rows hand-inserted; no Pack validator | generator 5.6 and 27 rules |

Each was true when written and nothing swept it after. A gap list that is wrong is worse
than none: it sends a reader to build something that exists, or to trust something that
does not.

**And a rule so it does not rot again:** a test asserts every doc's gap list carries a
`Last verified:` line, and the increment that changes behaviour is the increment that
updates it.

---

## 4. Pagination with denominators

`/api/audit` caps at 100 and says nothing about what it did not show. This project's own
rule is *report the denominator; no green check without a coverage count* — and the
screen that breaks it is the audit explorer, where "I looked and found nothing" is the
whole point.

Every list route that can grow without bound returns `{items, total, limit, offset}`.
The UI says **"showing 100 of 4,312"** and offers the next page. A truncated list that
looks complete is the same failure as a sweep that never ran looking green.

Applies to: audit, incidents, proposals, history. Not to registry-sized lists (forges,
ventures) that are bounded by the business.

---

## Acceptance tests

| # | Test |
|---|---|
| O1 | granting a role requires a strictly stronger role |
| O2 | **nobody can grant themselves a role, including `ivan`** |
| O3 | the last active `ivan` cannot be suspended or demoted |
| O4 | the bootstrap CLI refuses once a human exists |
| O5 | a reissued token works and **the old one stops working** |
| O6 | a suspended human is refused on their next request |
| O7 | revocations are listable and reinstatement lifts one |
| O8 | resolving an incident requires a reason and writes a historical record |
| O9 | **every paginated route reports a total larger than the page** |
| O10 | the UI states what it did not show |
| O11 | every doc gap list carries a `Last verified:` line |
