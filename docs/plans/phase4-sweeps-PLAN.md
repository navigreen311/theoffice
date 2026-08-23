# Phase 4, increment 1 — Continuous Verification (the sweeps) — PLAN

Blueprint Phase 4: "backup/restore drill · monthly reconciliation sweep", plus Gates 13,
14 and 15. Master prompt Part 13 and Part 15.

## Why this first, of everything in Phase 4

Phase 4 is "remaining seven Forges · remaining ventures · console breadth · backup/restore
drill · monthly reconciliation sweep". The Forges and most ventures are blocked on access
that does not exist yet. The console is a UI over things that already work.

**The sweeps are not.** They close a gap I have flagged at the end of every phase so far,
in the same words each time:

- Phase 0.1: "the chain makes tampering *detectable*, not preventable.
  `audit_log_verify_chain()` must be run on a schedule or it proves nothing — **no
  scheduler exists**."
- Phase 2: "staleness recompute is called explicitly, not scheduled. **Nothing runs it
  when a Forge's `api_version` changes** — a scheduled sweep is needed before this is
  trustworthy in production."
- Phase 3.3: "**nothing schedules rotations.** `rotate()` exists and is tested; no
  scheduler calls it at a real boundary."

Three controls that are real code, fully tested, and currently inert. A control nobody
runs is a control that exists in the repository and not in the system. That is worth
closing before adding more surface area to govern.

---

## Mini-PRD

**Problem.** The Office has controls whose correctness depends on someone running them,
and nothing does. Worse, there is no way to tell the difference between "the chain
verified this morning" and "the chain has not been verified since March" — both present
as an absence of incidents.

**Success metrics.**
1. Each sweep runs, records evidence, and raises an incident on a real finding.
2. A sweep that has **never run** is distinguishable from one that ran clean.
3. A sweep result **expires**. "The last verification passed" is meaningless without
   "and it ran three hours ago."
4. Gate 15 blocks while any `UNDECLARED` in-use module is undispositioned.
5. The restore drill actually restores, and the hash chain verifies in the restored copy.

---

## Design decisions

### A stale pass is not a pass

Every sweep kind declares a `max_age`. `sweep_freshness()` reports, per kind:
`never_run` | `fresh` | `stale` | `failing`.

`never_run` and `stale` are **not** green. This is the same rule as the validator's
`NOT_RUN`, and for the same reason: an absence of findings from a check that did not run
is not evidence of anything, and reporting it as healthy is how a broken sweep survives
for a quarter.

### Evidence, not verdicts

Each run records a `findings` payload and a `denominator` — how many things were checked.
"Chain OK" is not a result; "chain verified over 41,882 entries" is. Same rule as the
flush evidence and the coverage denominators.

### Sweeps are serialised and idempotent

One advisory lock per sweep kind. Two concurrent reconciliation sweeps would both create
pending dispositions for the same module, and a human would resolve one of them.

### Gate 15 blocks on undispositioned UNDECLARED

Part 15. An `UNDECLARED` module found in the ledger creates a `manifest_disposition` row
in state `pending`. A human resolves it to `declared`, `revoked` or `accepted_risk` —
with a reason. **The sweep fails while any remain pending**, so an undeclared call cannot
be quietly absorbed by time passing.

`accepted_risk` exists deliberately. Without it the only way to clear a finding someone
has decided to live with is to mislabel it, and a disposition vocabulary that forces a
lie produces a register nobody trusts.

### The restore drill restores

Part 13 requires a "quarterly tested drill". A drill that mocks the restore tests the
mock. This one runs `pg_dump`, creates a scratch database, restores into it, and asserts
`audit_log_verify_chain()` passes **in the restored copy** — which is the only property
that matters, since the ledger is the sole per-agent record.

Skipped with a stated reason when `pg_dump` is unavailable, never silently passed.

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| W1 | chain sweep passes on an intact chain and reports the count | denominator |
| W2 | chain sweep fails and raises a CRITICAL incident on tampering | detection works |
| W3 | chain sweep reports a nonzero `tail_gap` without failing | advisory stays advisory |
| W4 | staleness sweep flips certs and raises an incident naming affected grants | Phase 2 gap closed |
| W5 | staleness sweep is a no-op on a fresh world | no false positives |
| W6 | reconciliation finds an `UNDECLARED` in-use module and opens a disposition | Gate 15 |
| W7 | Gate 15 **fails** while a disposition is pending | the block |
| W8 | Gate 15 passes once dispositioned, and the reason is recorded | resolution |
| W9 | a disposition cannot be resolved without a reason and a human | accountability |
| W10 | `never_run` is not reported as healthy | |
| W11 | a sweep older than its `max_age` reports `stale`, not `fresh` | a stale pass is not a pass |
| W12 | concurrent sweeps of one kind do not double-open dispositions | advisory lock |
| W13 | restore drill dumps, restores, and verifies the chain in the copy | Gate 13 |

## Out of scope

The console (Part 17) and the scheduler daemon itself — this increment provides a CLI
entry point that a cron or a systemd timer invokes. Choosing the scheduler is a
deployment decision and 0.6 is still blocked.
