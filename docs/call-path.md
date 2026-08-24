# The Call Path — broker and client library

Blueprint deliverables 0.4 and 0.5. Master prompt §3 calls this "the single most
important code path in the system."

## What it does

An agent needs CapitalForge to parse a bank statement. Today there is no path: every
Forge holds one tenant-scoped key and knows nothing about individual agents.

**Office-brokered identity** closes that without touching any Forge. The Office issues
each agent an identity, holds the Forge's existing tenant credential, and presents it
on the agent's behalf **while stamping which agent made the call**.

What the agent experiences: it decides, it calls, it acts immediately, it is
accountable, and it can be revoked in one second. Nothing queues. No human intervenes.

## Order of operations

The order *is* the design. Each step exists because doing it later, or not at all,
loses something specific.

```
client.OfficeClient.call()
  1. trace_id             correlates Village → Office → Forge
  2. resolve grant        live query; never cached
  3. idempotency key      derived from (task_id, module_id, payload)
  4. at_most_once guard   escalate instead of retrying
  5. AUDIT WRITE          before the Forge is touched; fail closed if flagged
  6. execute              tenant credential presented, agent stamped
  7. ledger write         always — success, Forge error, or unreachable
```

### Why revocation is a live query

Master prompt §1.4: "checked per call at the broker, never cached. A revoked agent's
next call fails, not its next session."

That rules out every cache, including a short-TTL one. With no queue to drain and no
front desk to stop, this query **is** the kill switch. There is no `@lru_cache` in
`broker/grants.py` and there must never be.

`test_revoking_the_grant_fails_the_very_next_call` revokes *between two calls on the
same client instance*. Revoking before the client is constructed would pass even if
the grant were cached forever — so the test is written the other way round on purpose.

One query answers four questions together, because splitting them invites a caller to
check three and forget the fourth: identity is `active`, a grant exists, it is
un-revoked, and **both** certification units are present.

### Why audit is before and ledger is after

The audit entry records **intent**. It must exist even if the Forge call then crashes
the process. The ledger row records **outcome**.

A call that appears in audit with no ledger row is exactly the signal incident
response needs. Collapsing both into one post-call write would erase it.

`test_audit_is_written_before_the_forge_is_contacted` counts audit rows *from inside
the stub Forge*, at the moment it is reached. Counting afterwards cannot distinguish
"written before" from "written after".

### Fail closed, but only where it matters

Master prompt Part 13: fail closed on compliance-flagged actions, durable-queue
otherwise.

| Audit write fails | Module has compliance flags | Result |
|---|---|---|
| yes | yes | `AuditUnavailable`, Forge **never** contacted |
| yes | no | call proceeds |

Halting every call on an audit outage turns a logging problem into a total outage. A
flagged action halts because proceeding unrecorded is the thing the flag exists to
prevent. Flags come from `forge_module_registry.compliance_flags_implied`, so the
decision is data-driven and needs no venture Pack.

Flags active at call time are written to the ledger, so a later flag change cannot
retroactively rewrite what applied when the call was made.

### Idempotency is derived, not random

`sha256(task_id | module_id | payload_hash)`. A fresh uuid per attempt would make every
retry look like a new call and defeat the `at_most_once` guard entirely.

Only `at_most_once` modules are special: a replay escalates to a human rather than
being retried (master prompt Part 16). `key` and `natural` modules may safely repeat.

## Secrets

`forge_tenant_credential.credential_ref` holds a **vault path, never a value**.

`broker/credentials.py` is the only place a credential value exists in the process.
`Credential` wraps it so an accidental f-string or log line prints
`<Credential ref='env://...' value=REDACTED>`. That is a guardrail against the
realistic mistake, not a security boundary — anything holding the object can call
`.reveal()`. The point is that revealing it must be deliberate and greppable.

`test_credential_value_never_reaches_the_ledger_or_audit` asserts the value appears in
neither table. Payloads are hashed, never stored: the ledger is append-only and
long-lived, so putting request bodies in it would make every retention and PHI
obligation apply to the audit store itself.

## Forge-agnostic by construction

Nothing in `broker/` or `client/` names a Forge. Base URL, API version, auth model,
credential mode, idempotency class and compliance flags are all rows in
`forge_registry` and `forge_module_registry`.

Which Forge is bridged first is configuration. This is the same structural requirement
as the brokered→native credential swap (master prompt §1.6), and it is why that swap
is a config change rather than a rewrite.

## Refusal taxonomy

Every refusal has a named type, and every one writes an audit entry naming the reason
in a queryable field rather than only inside a message string.

| Exception | Meaning | Audit event |
|---|---|---|
| `NotGranted` | no live grant, or the grant is revoked | `call_refused_not_granted` |
| `NotCertified` | grant missing Unit A or Unit B | `call_refused_not_certified` |
| `IdentityInactive` | identity suspended, revoked, or retired | `call_refused_identity_inactive` |
| `UnknownForge` | Forge or module not registered | `call_refused_unknown_forge` |
| `AuditUnavailable` | audit failed on a flagged action | `call_refused_audit_unavailable` |
| `EscalateToHuman` | `at_most_once` replay | `call_escalated_at_most_once_replay` |
| `CredentialUnavailable` | credential ref did not resolve | `call_refused_credential_unavailable` |
| `ForgeUnreachable` | Forge could not be contacted | `call_failed_forge_unreachable` |

A Forge answering 500 is **not** an exception — it is an outcome, and outcomes belong
in the ledger. Only an inability to *reach* the Forge raises, because that is the case
where there is no outcome to record. `status_code IS NULL` in the ledger is what
distinguishes "never reached" from "answered with an error".

## Environment

| Variable | Purpose |
|---|---|
| `OFFICE_APP_DSN` | runtime DSN. **Must** be the `office_app` role — append-only is enforced by role, so an owner DSN silently removes the control |
| `OFFICE_ADMIN_DSN` | migrations and tests only |
| `STUB_FORGE_TOKEN` | test-only fake credential |
| `VAULT_ADDR` / `VAULT_TOKEN` | Phase 0.3, not yet implemented |

## Run

```bash
./scripts/bootstrap.sh                    # lint, type check, migrate, test
.venv/Scripts/python -m pytest tests/contract -q
```

## Known gaps

*Last verified: 2026-08-23.*

- **Network policy does not exist** (Phase 0.6, blocked on a deployment target). Until
  it does, the client library is a **convention, not a control** — an agent that
  constructs its own HTTP call bypasses everything here. Saying so plainly is more
  useful than pretending otherwise.
- **Forge-side attribution.** A Forge sees the tenant credential and the
  `X-Office-Agent-Id` header. Per-agent attribution on the Forge side is the Forge's to
  implement; until it does, Forge logs attribute everything to the tenant and the Office
  ledger is the only per-agent record. Stated in the master prompt as a known weakness
  and not hidden here.
- **`usd_cost` is never populated.** The budget ladder reads real spend correctly and
  nothing writes any — the stub Forge reports no usage. Cost attribution needs Forge
  responses that report token counts.
- **Proposal execution is manual.** Approving a proposal marks it; nothing replays the
  approved payload through the call path. Deliberately not built until there was a human
  queue to trigger it — there is one now, so this is the next thing here.

*Closed since this list was written:* Vault is implemented (`VaultCredentialResolver`,
KV v2, no environment fallback on any path). `trust_tier` **is** enforced — a tier below
`auto_execute` creates a proposal and raises `RequiresApproval`. Rate limiting is in
`broker/limits.py` and runs in the path. `manifest_match` does real three-way
reconciliation against a generated Forge Manifest.
