# Phase 3, increment 3 — Shift Assignment and the Verified PHI Flush — PLAN

Blueprint Phase 3, final increment. Master prompt Part 7.5 and Part 8.

**The PHI wall is temporal, not spatial.** There is one Village. MedLink's PHI must
never reach Collingswood's FunnelForge CDP — and the same agent may serve both across
consecutive shifts. So the wall runs at the shift boundary, inside a single agent.

---

## Mini-PRD

**Problem.** `shift_assignment` exists as a table with a `flush_completed_at` column
that nothing writes and nothing reads. There is no working memory, nothing tags PHI,
nothing flushes, nothing verifies, and nothing blocks. The most consequential isolation
control in the platform is currently a column comment.

Worse: the call path never checks that a call's `venture_id` matches the agent's current
shift. An agent holding grants for two ventures can serve both inside one shift today —
which is precisely the mid-shift switching Part 7.5 forbids.

**Success metrics.**
1. Working memory cannot be written without a data classification.
2. A shift boundary flushes PHI-tagged memory, verifies zero remain, and audits both.
3. **A failed flush blocks the next assignment** — not logs and continues.
4. A call whose venture does not match the agent's open shift is refused.
5. The flush runs regardless of certification state.

---

## Design decisions

### Tagged at write, never inferred at flush

Part 8: "PHI tagged at write time, not inferred at flush time."

`data_classification` is `NOT NULL` **with no default**, so a caller cannot write memory
without deciding what it is. Inferring at flush time means scanning content with a
heuristic, and a heuristic that misses once has leaked PHI across a venture boundary
permanently. The classification is also the only thing the flush reads — it never looks
at content, because content it can read is content it could get wrong.

### The boundary is one operation, in the stated order

Part 7.5: "flushed and flush verified → grants re-resolved for the incoming venture →
venture context switched → audit entry written."

Ordering matters at every step. Flush before re-resolve, so the outgoing venture's data
is gone before the incoming venture's authority exists. Verify before switch, so a
failed flush has nothing to switch into. Audit last, because the audit records what
happened, and an audit written first would record an intention.

### A failed flush blocks, and blocking is structural

Not a flag someone checks. `assign_shift` queries the agent's most recent ended shift and
refuses when `flush_verified` is false. The check is in the one function that creates
assignments, so there is no second path that forgets it.

### Uninterruptible means the agent cannot reach it

"Mandatory clear at every boundary, agent-uninterruptible."

The flush is not exposed through `OfficeClient`. An agent's only path to anything is the
client library, and the library has no flush, no skip and no defer. A test asserts the
client's public surface contains nothing that could cancel a boundary.

### Enforced regardless of certification state

"This is a control, not a competence claim." A revoked, suspended or never-certified
agent still flushes. Tying the flush to certification would mean the agents most likely
to have made a mess are the ones least likely to clean it up.

### One venture per shift, enforced in the call path

The schema already forbids overlapping shifts. Nothing yet forbids a call for a venture
the agent is not currently on-shift for. Adding that gate is what makes the rule
enforceable rather than declarative:

```
 1. trace_id
 2. resolve grant
 3. revocation scopes
 3a. SHIFT BOUNDARY CHECK        <- new
 4. manifest ...
```

After revocation because a revoked agent should be told it is revoked, not told it is on
the wrong shift. Before the manifest because serving the wrong venture is a boundary
violation whatever the module is.

**Accepted cost, stated in the source and repeated here:** an agent whose venture queue
empties mid-shift idles until the boundary. Recoverable by tuning shift length. Not
traded against isolation.

---

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| S1 | memory cannot be written without a classification | tagged at write |
| S2 | flush removes PHI-tagged rows and leaves others | it flushes the right thing |
| S3 | flush verification counts before and after, and records evidence | verified, not asserted |
| S4 | a verified flush permits the next assignment | happy path |
| S5 | an unflushed prior shift **blocks** the next assignment | Part 8, the core control |
| S6 | a failed flush blocks even when `flush_completed_at` is set | verified ≠ attempted |
| S7 | flush runs for a revoked agent | control, not competence claim |
| S8 | both flush and boundary are audited | |
| S9 | a call for a venture other than the open shift is refused | one venture per shift |
| S10 | a call with no open shift at all is refused | no unscoped calls |
| S11 | `OfficeClient` exposes nothing that can skip a boundary | uninterruptible |
| S12 | rotate() performs the four steps in the stated order | Part 7.5 |
| S13 | non-PHI ventures are not exempt | uniform rule, not conditional |

---

## Out of scope

The Deputy cushion and rest-day rotation are Village mechanics (Part 7.4) — The Office
allocates within them and does not override them, so scheduling policy stays out.
Cross-venture referral consent (Part 8) is console work.
