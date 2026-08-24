# Governance in the Path — Phase 1

Phase 0 built the path. Everything on it was permissive: a `propose`-tier agent
executed, an undeclared module was called without complaint, nothing limited rate,
nothing counted money, and revocation existed only at agent × module.

Phase 1 is where the recorded guardrails become enforced ones.

## The gate order, and why it is that order

```
 1. trace_id
 2. resolve grant            identity active, grant live, both certs present
 3. REVOCATION SCOPES        agent×module | agent | venture | forge
 4. MANIFEST CHECK           required | declared_only | UNDECLARED
 5. BUDGET LADDER            per-task | per-agent daily | soft | hard
 6. EFFECTIVE TRUST TIER     grant tier, downgraded engagement-wide if soft-capped
 7. TRUST TIER GATE          below auto_execute → proposal, no Forge call
 8. RATE LIMIT               per-agent AND per-Forge; both must admit
 9. idempotency + at_most_once guard
10. AUDIT WRITE              before the Forge; fail closed if compliance-flagged
11. execute
12. ledger write
```

- **Revocation first**, so a revoked agent spends no rate-limit token and triggers no
  budget query. A kill switch that consumes resources on the way to refusing is not
  much of a kill switch.
- **Manifest before the tier gate**, because calling an undeclared module is a
  violation regardless of what tier the caller holds.
- **Budget before the tier gate**, because the soft cap *changes* the effective tier.
  Reversed, an `auto_execute` call slips through in the window where the venture has
  already crossed its soft cap.
- **Rate limit last of the gates**, because it mutates a bucket and every refusal
  above it costs nothing to detect.

---

## Revocation — four scopes (§1.4)

| Scope | Effect | Authority |
|---|---|---|
| `agent_module` | one grant | venture_operator |
| `agent` | agent reaches no Forge | venture_operator |
| `venture` | all grants for the engagement | compliance_officer |
| `forge` | broker refuses all calls to that Forge | ivan |

A stronger role may act at a weaker scope; the reverse is refused. **Reinstatement
requires the same authority as revocation** — otherwise a venture operator could undo
a compliance officer's venture-wide stop.

**Why a table, not columns on `agent_forge_grant`.** A Forge-wide revocation is not a
property of any single grant, and a venture-wide revocation must apply to grants
issued *after* it was declared. Stored on the grant, both cases are silently missed —
and the second is exactly how a revoked venture quietly comes back to life. There is a
test for precisely that: `test_venture_revocation_applies_to_a_grant_issued_afterwards`.

The **broadest** scope wins the report. An agent blocked by a Forge-wide revocation
should be told that, not told its own grant is gone; the two call for completely
different responses from whoever is watching.

Re-enable "requires a documented ritual and a named human" (§1.4) — enforced by a
CHECK constraint, so a reinstatement cannot be an anonymous `UPDATE`.

---

## Manifest — three states, four handlers (§5.6, Part 15)

Declared = a row exists. Required = `is_required`. In-Use = read from the ledger.

| Situation | `manifest_match` | Action |
|---|---|---|
| in manifest, required | `required` | proceed |
| in manifest, not required | `declared_only` | HIGH incident `in_use_not_required`, throttle, **proceed** |
| not in manifest | `UNDECLARED` | HIGH incident `undeclared_forge_call`, throttle, **block** |
| required but not declared | — | fails the Pack at Gate 3.5; not a runtime state |

`declared_only` proceeds because the venture **did** declare the module — the incident
records that nothing in the workflow required it. `UNDECLARED` blocks because nobody
declared it at all.

Blocking both would make a Pack's own declarations meaningless. Blocking neither would
make the manifest decorative. The asymmetry is the point.

Violations **throttle rather than block outright** (factor 0.1 for 15 minutes): the
goal is to slow a misbehaving agent while a human looks, not to take a venture down
over one bad module reference.

---

## Trust tiers and proposals (§1.2, Part 14)

`auto_execute` acts. `propose` and `suggest` create a proposal and touch no Forge.

Both lower tiers are kept distinct even though today's runtime effect is identical: a
proposal is an action awaiting approval, a suggestion is advice, and Part 10.1 requires
that tiers and states are never collapsed.

**Certified tier caps declared tier** (Part 10.1). The Pack declares a ceiling,
SimForge sets the actual, and the grant carries the lower. That reconciliation happens
at grant issuance — by the time the call path reads `grant.trust_tier` it is already
the effective ceiling, and the call path must not re-derive it.

Proposals **store the payload**, because a proposal a human cannot inspect is not a
proposal. ⚠ That column inherits the venture's retention and PHI obligations. A
`propose`-tier grant on a PHI-touching module puts PHI in `proposal.payload`, and the
venture's `data_retention` policy must cover it. Not yet enforced — Phase 3.

**Rubber-stamp detection** (Part 14): `review_seconds` is computed in the database from
`created_at`, so a caller cannot report a review time it did not take. Approvals under
five seconds raise a MEDIUM `rubber_stamp_approval` incident. A human clicking approve
in three seconds has not read a bank-statement payload, and a trust tier that is really
a click-through is worse than no tier at all, because it looks like oversight.

---

## Rate limiting

Token buckets in Postgres, per agent **and** per Forge — both must admit. An agent
within its own limit still cannot push a Forge past its global ceiling; a quiet Forge
does not entitle one agent to unlimited calls.

Token bucket rather than fixed window because the Pack declares `max_rps` *and*
`burst`, and a fixed window cannot express the difference. Postgres rather than Redis
because the blueprint puts the queue on Postgres at v1, and a counter store would be
the same operational dependency renamed.

**Agent bucket is debited first.** If the Forge ceiling then refuses, one agent token
has been spent on a call that did not happen. The reverse order over-charges the shared
Forge ceiling instead, penalising every other agent for one agent's excess. Charging
the individual is the better failure, and it is deliberate.

`SELECT ... FOR UPDATE` serialises bucket access and **requires READ COMMITTED** —
under REPEATABLE READ the post-lock re-read raises a serialization failure. Same
constraint as the audit chain (`docs/ledger.md`).

A throttle **extends but never shortens**: a second violation must not reset the clock
to something shorter than the first. Expired throttles stop applying without anyone
resetting them, so a forgotten throttle is not indistinguishable from a policy.

---

## Budget ladder (Part 12)

| Rung | Trigger | Effect |
|---|---|---|
| per-task ceiling | task spend ≥ ceiling | that task halts |
| per-agent daily cap | agent spend today ≥ cap | agent paused |
| soft cap | venture MTD ≥ `soft_cap_pct`% of monthly | `auto_execute` → `propose`, engagement-wide |
| hard cap | venture MTD ≥ monthly cap | pause or throttle; **Ivan-only** reversal |

Narrowest scope is checked first: a blown task should halt that task, not report the
venture cap it also happens to be under.

**Spend is measured, not predicted.** Exact pre-call cost is unknowable — the Forge has
not run and token counts do not exist until it has. The honest enforcement is "you have
already spent this much, so you may not start another", which means a single call can
carry a venture slightly past a cap. The alternatives are not enforcing at all, or
blocking on an estimate that will sometimes be wrong in the expensive direction.

**The rungs are independent.** Reversing a hard cap resumes work but does not clear the
soft cap — at 120% of a 100 cap the venture is still past 80%, so `auto_execute` stays
demoted. Tested explicitly.

**No budget row means unmetered, not zero.** Silently applying a default cap would halt
work for a reason nobody configured. Validator rule V18 makes budget caps a required
Pack field, so an unbudgeted venture cannot reach production.

---

## Incidents

An incident is a **detection**, not a workflow. Triage, containment, disclosure and
post-mortem live in the console (Part 9). Incident rows are append-only — `office_app`
holds INSERT and SELECT and nothing else. A later finding is a new incident referencing
the same `trace_id`, never an edit.

| Kind | Severity | Raised when |
|---|---|---|
| `undeclared_forge_call` | HIGH | module absent from the venture manifest |
| `in_use_not_required` | HIGH | module declared but not required |
| `rubber_stamp_approval` | MEDIUM | proposal approved in under 5 seconds |

---

## Refusal taxonomy added in Phase 1

| Exception | Audit event | HTTP |
|---|---|---|
| `Revoked` | `call_refused_revoked` | 403 |
| `ManifestViolation` | `call_refused_undeclared_module` | 403 |
| `RequiresApproval` | `call_deferred_to_proposal` | 202 |
| `RateLimited` | `call_refused_rate_limited` | 429 |
| `BudgetExceeded` | `call_refused_budget_exceeded` | 402 |
| `NotAuthorized` | `governance_action_refused_not_authorized` | 403 |

`RequiresApproval` is an exception rather than a return value because the call did not
happen. A caller must not be able to mistake an absent Forge response for a successful
one — a proposal exists, the action does not.

---

## Blueprint gap corrected

Part 12 mandates a per-task USD ceiling and the Pack schema marks
`per_task_usd_ceiling` required — but `agent_call_ledger` in blueprint §2 carries **no
task identifier**. `idempotency_key` is a one-way hash of `(task_id, module_id,
payload)` and cannot be grouped by task, so per-task spend is not computable as
specified.

`task_id TEXT` added in migration 0006. **The blueprint should be amended.**

---

## Known gaps

*Last verified: 2026-08-23.*

- **Rate limits use module defaults**, not the Pack's `rate_limit_policy`. Wiring that
  through is a small change nobody has needed yet.
- **`usd_cost` is never populated** — the stub Forge reports no usage. The ladder reads
  real spend correctly; nothing is currently writing any. Cost attribution needs Forge
  responses that report token counts.
- **Proposal execution is manual.** Approving marks the proposal; nothing yet replays
  it through the call path. The approved-payload replay path is deliberately not built
  until there is a human queue to trigger it.
- **`proposal.payload` retention is undefined.** See the PHI note above.
