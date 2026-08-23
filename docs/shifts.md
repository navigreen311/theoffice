# Shifts and the Verified PHI Flush — Phase 3, increment 3

**The PHI wall is temporal, not spatial.**

There is one Village. MedLink's PHI must never reach Collingswood's FunnelForge CDP —
and the same agent may serve both across consecutive shifts. So the wall runs at the
shift boundary, inside a single agent, rather than between two places.

Before this increment, `shift_assignment` existed as a table with a `flush_completed_at`
column that nothing wrote and nothing read. The most consequential isolation control in
the platform was a column comment.

---

## Tagged at write, never inferred at flush

`agent_working_memory.data_classification` is `NOT NULL` **with no default**. A caller
cannot write memory without deciding what it is.

Inferring at flush time means scanning content with a heuristic, and a heuristic that
misses once has leaked PHI across a venture boundary permanently. The flush reads **only
the classification** — never the content. Content it could read is content it could
misjudge, and the whole point of tagging at write time is that the flush does not have
to judge anything.

`content_ref` holds a reference, never a body. Working memory storing PHI bodies would
make this table the thing the PHI wall exists to protect.

Two classifications are destroyed at the boundary: `phi`, and `recording` — a call
recording in a two-party-consent state is the same shape of problem.

---

## Verified means checkable

`flush_evidence` records the classification counts **before and after**:

```json
{"before": {"internal": 1, "phi": 2, "public": 1, "recording": 1},
 "after":  {"internal": 1, "public": 1},
 "verified": true}
```

A boolean saying the flush succeeded is a claim. A count before and a count of zero
after is evidence a third party can check.

Verification is a **re-count after the delete**, not the delete's rowcount. A concurrent
write between delete and commit would leave PHI behind, and a rowcount cannot see that.

`flush_attempted_at` and `flush_verified` are separate columns because **attempted is not
verified**. A flush that ran and left PHI behind sets the first and not the second — and
the second is what unblocks the next assignment.

---

## A failed flush blocks. That is the wall.

Part 8: blocks, "rather than logging and continuing". The difference between those two
is the entire control.

The check lives in `assign_shift`, the one function that creates assignments, so there
is no second path that forgets it. It is not a flag someone remembers to consult.

**A non-PHI venture is not exempt.** Part 7.5: "including non-PHI ventures", because
"a single uniform rule is enforceable where a conditional one is not" — and the
condition is where the bug lives.

**The flush runs regardless of certification state.** Part 8: "this is a control, not a
competence claim." Tying it to standing would mean the agents most likely to have made a
mess are the ones least likely to clean it up. There is a test that flushes a *revoked*
agent.

---

## The boundary, in the order Part 7.5 states

```
flush -> verify -> re-resolve grants -> switch context -> audit
```

Every step's position is load-bearing:

- **Flush before re-resolve**, so the outgoing venture's data is gone before the incoming
  venture's authority exists.
- **Verify before switch**, so a failed flush has nothing to switch into. `rotate()`
  raises at the flush and creates no new shift — there is a test asserting zero new rows.
- **Audit last**, because an audit written first records an intention rather than an
  event.

The order is also written into the audit entry's `subject`, so a reader of the audit log
can check the sequence rather than trust it.

---

## Uninterruptible means unreachable

Part 8: "mandatory clear at every boundary, agent-uninterruptible."

An agent's only path to anything is `OfficeClient`. The library has no flush, no skip and
no defer — and a test asserts its public surface is exactly `{call, aclose}`. Anything
added there becomes reachable by an agent, so the test fails on any addition and forces
the question.

---

## One venture per shift, enforced in the call path

The schema already forbade **overlapping shifts** via a GiST exclusion constraint. That
is not the same rule.

An agent holding grants for two ventures could serve both inside a single shift simply by
passing a different `venture_id`: the grant resolves, every other gate passes, and the
temporal wall has a hole no constraint could see. Gate **3a** closes it:

```
 1. trace_id
 2. resolve grant
 3. revocation scopes
3a. SHIFT BOUNDARY        the call's venture must be the agent's on-shift venture
 4. manifest check
 ...
```

After revocation, because a revoked agent should be told it is revoked rather than told
it is on the wrong shift — those send whoever is watching to different investigations.
Before the manifest, because serving the wrong venture is a boundary violation whatever
the module is.

A call with **no** open shift is also refused. **Accepted cost, stated in §7.5 and worth
repeating:** an agent whose venture queue empties mid-shift idles until the boundary.
Recoverable by tuning shift length. Not traded against isolation.

---

## A bug this increment surfaced, unrelated to PHI

Two isolation tests failed **only when the whole suite ran together**, with an error
about a closed event loop that had nothing to do with them.

Cause: the broker connection pool is a process-level global, and pytest-asyncio gives
each test its own event loop, so a pooled connection is invalid in the next test. The
pool-reset fixture existed in two directories and not in `tests/validator` or
`tests/golden` — which use the pool. They left one bound to a dead loop, and the *next*
suite's first test paid for it.

Fixed in two places: `open_pool()` now recreates a pool that has been closed (handing
back a closed pool raises at the point of use rather than the point of closing, turning
a lifecycle mistake into a failure in unrelated code), and the reset fixture moved to the
**root** conftest. A cleanup that only some directories perform is worse than none,
because the failure lands somewhere else.

---

## Run

```bash
.venv/Scripts/python -m pytest tests/isolation -q
.venv/Scripts/python -m pytest tests/contract/test_shift_gate.py -q
```

## Known gaps

- **Nothing schedules rotations.** `rotate()` exists and is tested; no scheduler calls it
  at a real boundary. Until one does, the flush happens when someone asks for it.
- **Deputy cushion and rest-day rotation are Village mechanics** (Part 7.4). The Office
  allocates within them and does not override them, so scheduling policy is deliberately
  absent here.
- **Working memory is written by nobody in production.** The call path does not yet tag
  what it learns; `record_memory` is the interface waiting for it.
- **Deletion is a hard delete**, not crypto-shred. The Pack's `deletion_mechanism` is
  declared per data type and not yet honoured by the flush.
- **Cross-venture referral consent** (Part 8) is console work.
