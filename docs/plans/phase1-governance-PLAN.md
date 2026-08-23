# Phase 1 — Governance in the Path — PLAN

**Blueprint Phase 1.** Trust-tier enforcement · manifest check with four mismatch
handlers · rate limiting per agent and per Forge · cost metering · four revocation
scopes · fail-closed audit (already shipped in Phase 0).

**Acceptance (blueprint, verbatim):** an agent at `propose` tier cannot execute — the
call produces a proposal, not a Forge action. An `UNDECLARED` call raises a HIGH
incident and throttles. Exceeding the per-task ceiling halts that task.

---

## Mini-PRD

**Problem.** Phase 0 built the path. Everything on it is currently permissive: a
`propose`-tier agent executes, an undeclared module is called without complaint,
nothing limits rate, nothing counts money, and revocation exists only at
agent × module. The guardrails are recorded but not enforced.

**Users.** Venture operators (revocation, proposal approval), compliance officers
(venture-wide revocation, incidents), Ivan (Forge-wide revocation, hard-cap reversal).

**Success metrics.**
1. A `propose`-tier agent produces a proposal row and **zero** Forge calls.
2. An `UNDECLARED` module call is blocked, raises a HIGH incident, and throttles.
3. All four revocation scopes stop a call, each requiring the right authority.
4. Per-task ceiling, per-agent daily cap, soft cap and hard cap each behave per Part 12.
5. Rate limits hold per agent and per Forge under concurrency.

---

## Blueprint gap found — the ledger cannot support its own cost ceiling

Part 12 mandates a **per-task USD ceiling** ("per-task ceiling → task halts") and the
Pack schema marks `per_task_usd_ceiling` required. But `agent_call_ledger` in
blueprint §2 carries **no task identifier** — only an `idempotency_key`, which is a
one-way hash of `(task_id, module_id, payload)` and cannot be grouped by task.

Per-task spend is therefore not computable from the ledger as specified.

**Fix:** add `task_id TEXT` to `agent_call_ledger` (migration 0006). Recorded here
rather than silently patched — the blueprint should be amended.

---

## Call path after this increment

```
 1. trace_id
 2. resolve grant                    live; identity + grant + both certs
 3. REVOCATION SCOPES                live; agent×module | agent | venture | forge
 4. MANIFEST CHECK                   required | declared_only | UNDECLARED
 5. BUDGET LADDER                    per-task | per-agent daily | soft | hard
 6. EFFECTIVE TRUST TIER             grant tier, downgraded if soft-capped
 7. TRUST TIER GATE                  not auto_execute -> proposal, no Forge call
 8. RATE LIMIT                       per-agent AND per-Forge token buckets
 9. idempotency + at_most_once guard
10. AUDIT WRITE (fail closed if flagged)
11. execute
12. ledger write
```

Order is load-bearing. Revocation precedes everything because a revoked agent must
not consume a rate-limit token or a budget check. The manifest check precedes the tier
gate because an undeclared call is a violation regardless of tier. Budget precedes tier
because the soft cap *changes* the effective tier.

---

## Design decisions

### Four revocation scopes (§1.4)

| Scope | Effect | Required authority |
|---|---|---|
| `agent_module` | one grant | venture_operator |
| `agent` | agent reaches no Forge | venture_operator |
| `venture` | all grants for the engagement | compliance_officer |
| `forge` | broker refuses all calls to that Forge | ivan |

A separate `revocation` table rather than more nullable columns on the grant: a
Forge-wide revocation is not a property of any one grant, and a venture-wide one must
apply to grants issued *after* it. Checked live on every call, same rule as §1.4.

Re-enable "requires a documented ritual and a named human" — enforced by a CHECK: a
reinstated row must carry `reinstated_by` and `reinstatement_reason`.

### Manifest — three states, four handlers (Part 15, §5.6)

| Situation | Ledger `manifest_match` | Action |
|---|---|---|
| in manifest, `required = true` | `required` | proceed |
| in manifest, `required = false` | `declared_only` | HIGH incident (`IN_USE_NOT_REQUIRED`), throttle, **proceed** — it was declared |
| not in manifest | `UNDECLARED` | HIGH incident, throttle, **block** |
| `required` but not declared | — | fails the Pack at Gate 3.5, not a runtime state |

`declared_only` proceeds because the venture *did* declare the module; the incident
records that nothing required it. `UNDECLARED` blocks because nobody declared it at
all. Blocking both would make a Pack's own declarations meaningless.

### Trust tier (§1.2, Part 12)

`auto_execute` executes. `propose` and `suggest` create a proposal row and return
without touching the Forge. Effective tier = grant tier, **downgraded to `propose` when
the venture is soft-capped** — Part 12's soft-cap rung is "all auto_execute downgrades
to propose across the engagement", which is a tier change, not a separate mechanism.

Proposals store the payload, because a proposal a human cannot inspect is not a
proposal. That payload inherits the venture's retention and PHI obligations; noted in
docs rather than assumed away.

Rubber-stamp detection (Part 14): `review_seconds` recorded per decision, and a
sub-5-second cluster raises a governance flag.

### Rate limiting (§1.7 step 9)

Token bucket in Postgres — per agent *and* per Forge, both must admit. No Redis: the
blueprint puts the queue on Postgres at v1, and a second datastore for counters would
be the same dependency by another name.

`SELECT ... FOR UPDATE` serialises bucket access. **Requires READ COMMITTED** — under
REPEATABLE READ the row re-read after the lock raises a serialization failure. Same
constraint as the audit chain; documented in one place.

Throttling from a manifest violation multiplies the bucket's refill rate by
`throttle_factor` until `throttled_until`.

### Budget ladder (Part 12)

| Rung | Trigger | Effect |
|---|---|---|
| per-task ceiling | task spend ≥ ceiling | that task halts |
| per-agent daily cap | agent spend today ≥ cap | agent paused |
| soft cap | venture MTD ≥ `soft_cap_pct` of monthly | `auto_execute` → `propose` engagement-wide |
| hard cap | venture MTD ≥ monthly cap | pause or throttle; Ivan-only reversal |

Spend is measured from the ledger before the call, not predicted. Exact pre-call cost
is unknowable; the honest enforcement is "you have already spent this much, so you may
not start another".

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| G1–G4 | each revocation scope blocks a call | four scopes |
| G5 | wrong authority cannot revoke at that scope | authority matrix |
| G6 | reinstatement without a named human + reason is rejected | documented ritual |
| G7 | revocation applies to a grant issued after it | venture scope is not per-grant |
| G8 | `required` module proceeds, ledger says `required` | manifest happy path |
| G9 | `declared_only` proceeds, HIGH incident raised, throttled | IN_USE_NOT_REQUIRED |
| G10 | `UNDECLARED` blocked, HIGH incident, throttled, Forge untouched | acceptance criterion 2 |
| G11 | `propose` tier → proposal row, zero Forge calls | acceptance criterion 1 |
| G12 | `suggest` tier → proposal row, zero Forge calls | |
| G13 | approving a proposal is what executes it | proposal lifecycle |
| G14 | sub-5s approval raises a governance flag | rubber-stamp detection |
| G15 | per-agent rate limit denies the (n+1)th call | rate limit |
| G16 | per-Forge ceiling denies across agents | global ceiling |
| G17 | throttle reduces the effective rate | manifest → throttle linkage |
| G18 | per-task ceiling halts that task, others unaffected | acceptance criterion 3 |
| G19 | per-agent daily cap pauses the agent | |
| G20 | soft cap downgrades auto_execute to propose | ladder rung 3 |
| G21 | hard cap pauses; only Ivan can reverse | ladder rung 4 |
| G22 | every refusal is audited with its own event type | governance is auditable |

---

## Out of scope

Manifest *generation* from a Pack (Phase 3 — the Generator layer). Incident
triage/disclosure workflow (Part 9, console). Approval UI. Cost attribution to LLM
tokens (needs Forge responses to report usage).
