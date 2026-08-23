# Phase 0.4 + 0.5 — Identity Broker and Client Library — PLAN

**Blueprint deliverables 0.4 and 0.5.** Master prompt §3 calls this "the single most
important code path in the system."

---

## Mini-PRD

**Problem.** No Village agent has ever reached a Forge. There is no path. Every Forge
holds one tenant-scoped key and knows nothing about individual agents.

**Solution.** The Office issues each agent an identity, holds the Forge's existing
tenant credential, and presents it on the agent's behalf **while stamping which agent
made the call**. What the agent experiences is: it decides, it calls, it acts
immediately, it is accountable, and it can be revoked in one second.

**Users.** Village agents (through the client library, which is the only path);
compliance and incident response (through the ledger the path writes).

**Success metrics.**
1. A call by a granted, certified, active agent reaches a Forge and produces a ledger
   row naming that agent.
2. Revoking the grant makes the agent's **immediate next call** fail — not its next
   session. Proven by revoking mid-test.
3. An audit entry exists **before** the Forge is contacted, not after.
4. An `at_most_once` module is never auto-retried.
5. No Forge identity is hardcoded anywhere in `broker/` or `client/`.

**Constraints.** Python 3.11, FastAPI, async. Forge-agnostic — CapitalForge is a row,
not an import. Credentials resolve by ref; the value never enters a log, an exception
message, or a ledger row.

---

## Scope boundary — deliberately narrow

Master prompt §3 shows the finished call path. Build order §1.7 puts steps 8–9 in
Phase 1. This increment implements Phase 0 only:

| Step | Phase 0 | Why |
|---|---|---|
| Resolve grant, live revocation check | **Yes** | 0.4 |
| Certification gate (both units) | **Yes** | Already structural in the schema |
| Manifest check | Phase 1 | Needs a venture Manifest; no Pack exists yet |
| Trust tier → proposal queue | Phase 1 | Needs a human approval queue that does not exist |
| Rate limiting | Phase 1 | 0.9 |
| Idempotency key + `at_most_once` guard | **Yes** | 0.5 |
| Audit before call, fail-closed | **Yes** | 0.5 |
| Broker executes, stamps identity | **Yes** | 0.4 |
| Ledger write | **Yes** | 0.5 |

Trust tier is **recorded** in the ledger (`trust_tier_at_call`) from this increment on,
so Phase 1 enforcement has the history it needs. Recording without enforcing is stated
here so nobody mistakes the column for a control yet.

---

## Architecture

```
Agent (Village)
    │ acts on its own initiative
    ▼
client.OfficeClient.call()          ← the mandatory path
    │ 1. new trace_id
    │ 2. resolve grant via broker      (live; never cached)
    │ 3. idempotency key
    │ 4. at_most_once replay guard
    │ 5. AUDIT WRITE  ← before the Forge is touched; fail-closed if flagged
    │ 6. broker.execute()
    │ 7. ledger write                  (always, success or failure)
    ▼
broker/  FastAPI
    │ · grants.resolve()      identity active + grant live + both certs present
    │ · credentials.resolve() vault ref → value, never logged
    │ · executor.execute()    injects X-Office-* headers
    ▼
Forge (row in forge_registry)
```

### Modules

| Module | Responsibility |
|---|---|
| `broker/errors.py` | the exception taxonomy — every refusal is a named type |
| `broker/config.py` | settings from env; no defaults that could reach a real Forge |
| `broker/db.py` | async connection pool |
| `broker/credentials.py` | `CredentialResolver` protocol + env-backed dev impl |
| `broker/grants.py` | `resolve_grant()` — one query, no cache |
| `broker/audit.py` | `write_event()`; raises rather than returns false |
| `broker/ledger.py` | `write_call()` |
| `broker/executor.py` | HTTP to the Forge with identity headers |
| `broker/app.py` | FastAPI routes |
| `client/office_client.py` | `OfficeClient.call()` — the ordered path above |

### Decisions

**Revocation is a live query, every call.** Not a cache with a TTL, not a
subscription. §1.4 says "checked per call at the broker, never cached", and the test
revokes between two calls on the same client instance and asserts the second fails.
A cache would pass a test that revokes before the client is constructed — so the test
is written the other way round on purpose.

**Audit before, ledger after.** The audit entry records *intent* and must exist even
if the Forge call then crashes the process. The ledger row records *outcome*. A call
that appears in audit with no ledger row is exactly the signal incident response
needs; collapsing them into one write after the call would erase it.

**Fail closed only when compliance flags are active.** §13: fail-closed on
compliance-flagged actions, durable-queue otherwise. Flags come from
`forge_module_registry.compliance_flags_implied`, so the decision is data-driven and
does not need the venture Pack that does not exist yet.

**Credential values never leave `credentials.py`.** They are passed to the executor and
used in a header. They are not stored, logged, put in exception messages, or returned
from any route. A test asserts the value cannot be found in the ledger or audit tables.

**The stub Forge is an in-process ASGI app.** No ports, no sleeps, no flaky teardown.
Contract tests drive it through `httpx.ASGITransport`.

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| B1 | Granted, certified, active agent → call succeeds, ledger row names the agent | success metric 1 |
| B2 | Revoke grant, then call on the **same client** → fails | revocation not cached |
| B3 | Suspend identity, then call → fails | identity status checked live |
| B4 | Grant missing either cert ref → `NotCertified` | invariant 6 in the path |
| B5 | No grant at all → `NotGranted`, and the refusal is audited | audited refusal |
| B6 | Audit row exists before the Forge is reached | ordering, via a Forge that asserts it |
| B7 | Audit write fails + module has compliance flags → `AuditUnavailable`, Forge never called | fail closed |
| B8 | Audit write fails + no compliance flags → call proceeds | degrade, not halt |
| B9 | `at_most_once` module, same idempotency key twice → `EscalateToHuman` | never auto-retry |
| B10 | `key` module, same key twice → allowed, both ledgered | only `at_most_once` is special |
| B11 | Forge returns 500 → ledger row written with the status | ledger records failure too |
| B12 | Credential value appears in no ledger or audit row | secret containment |
| B13 | Identity headers arrive at the Forge | stamping works |
| B14 | Two Forges registered → each routes to its own base URL | Forge-agnostic |

---

## Out of scope

Network policy (0.6 — needs the deployment target), Vault (0.3 — needs an instance),
identity issuance for the 106 agents (0.2 — needs the roster), trust-tier enforcement,
manifest check, rate limiting (all Phase 1).
