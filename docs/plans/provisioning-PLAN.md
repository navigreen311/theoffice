# Pack Store and Provisioning Pipeline — PLAN

Master prompt Part 11 (the 17 gates) and Part 17 (Pack Editor, Provisioning Console).

This is the backend the last console increment named as missing. Two of the three
unbuilt screens are blocked on exactly this.

---

## What a provisioning run is

A **state machine over gates**, not a script. Each gate has a blocking condition, and the
run stops at the first one that blocks. Gates are not skippable and not reorderable —
Gate 5 issues grants and Gate 2 is the validator, so a run that could jump would issue
grants for a Pack nobody validated.

| Gate | Automatable now | Blocks on |
|---|---|---|
| 0 Bridge operational | yes | any `hard` Forge the bridge does not reach |
| 1 Pack authored | yes | no live Pack for this venture |
| 2 Pack Validator | yes | any FAIL, or any NOT_RUN |
| 3 Generators 1–6 | yes | generator error |
| 3.5 Manifest reconciliation | yes | `REQUIRED_NOT_DECLARED`, `hard` + `module_gap` |
| **4 Human review** | **no — waits** | operator has not reviewed |
| 4.5 Capacity & budget | yes | approvals > capacity, unfilled positions |
| 5 Sandbox grants issued | yes | provisioning failure |
| 6 KBs seeded, instructions indexed | partly | a module with no instructions |
| 7 Engagement registered, **grants inactive** | yes | a grant already active |
| 8 Curriculum → SimForge | yes | submission failure |
| **9 Readiness Gate** | **no — blocked** | SimForge does not exist |
| **9.5 Held-out adversarial** | **no — blocked** | the partition does not exist |
| **10 Named-human sign-off** | **no — waits** | missing signature, SoD violation, **voided signature** |
| 11 Production grants activated | yes | Gate 10 signature absent or void |
| 12 Live | yes | — |

## Three decisions that carry the whole design

### A human gate waits. It does not pass.

Gates 4 and 10 return `awaiting_human`, which is neither a pass nor a failure. A pipeline
that auto-advances through a human review gate is a pipeline without human review, and
the tell is that it still *reports* having one.

`awaiting_human` is a distinct verdict from `passed` and from `blocked` for the same
reason `NOT_RUN` is distinct from `PASS` and `FAIL` everywhere else in this system.

### Gates 9 and 9.5 are BLOCKED, not skipped

SimForge has no instance and the held-out partition does not exist. A run reaches Gate 8,
submits a curriculum, and **stops** — reporting that certification cannot be verified
rather than proceeding as if it had been.

This is Gate 0's philosophy applied to certification: no engagement provisions against a
capability that does not exist. Skipping them would produce a venture that reads as
fully provisioned and has never been certified for anything.

### Grants are issued inactive and activated only against a valid signature

Part 11 Gate 7: "agents appointed but **grants inactive**". Gate 11: "production grants
activated".

Today `agent_forge_grant` has no such distinction — a grant written at Gate 5 is live
immediately, so "sandbox provisioning" would hand agents production authority nine gates
early. So `activated_at` is added, and **`is_assignable` requires it**.

Gate 11 then refuses unless Gate 10 holds a signature **bound to the current artifact
hash**. Edit the Pack after signing and the artifacts change, the hash changes, the
signature voids by comparison, and Gate 11 refuses. That is what Part 14's artifact-hash
binding is *for*, and this is the first place it does real work.

## Schema

| Table | Purpose |
|---|---|
| `business_pack` | YAML source + parsed JSONB + `content_hash` computed in the database. One live version per venture. |
| `provisioning_run` | one per attempt: venture, pack version, current gate, status, artifacts hash |
| `provisioning_gate_result` | one row per gate attempt, with evidence. Append-only. |
| `agent_forge_grant.activated_at` | NULL until Gate 11 |

`content_hash` is computed by trigger, exactly as instruction hashes are: a supplied hash
is a claim, a computed one is a fact.

## Acceptance tests

| # | Test | Asserts |
|---|---|---|
| P1 | a Pack round-trips through the store with a computed hash | |
| P2 | one live Pack per venture; authoring supersedes | |
| P3 | a run stops at the first blocking gate and names it | not a script |
| P4 | gates cannot be skipped or reordered | |
| P5 | Gate 2 blocks a Pack with a FAIL | |
| P6 | **Gate 4 returns `awaiting_human`, not `passed`** | the core rule |
| P7 | recording a review advances past Gate 4 | |
| P8 | **Gates 9/9.5 report `blocked`, never `skipped` or `passed`** | |
| P9 | Gate 5 issues grants with `activated_at IS NULL` | |
| P10 | an inactive grant is **not assignable**, so the call path refuses it | the control, not the flag |
| P11 | Gate 11 refuses without a Gate 10 signature | |
| P12 | **an artifact change voids the signature and the run refuses again** | Part 14 doing real work |
| P13 | Gate 11 activates grants once the signature is valid | |
| P14 | every gate result records evidence | |
| P15 | a run is auditable end to end | |

## What changed against this plan while building it

Four things. Recorded here rather than quietly absorbed, because each was a defect the
plan did not anticipate.

**Gate 9 was going to be hardcoded BLOCKED. It reads the certification record instead.**
Hardcoding it made Gates 10, 11 and 12 unreachable code — the activation control this
whole increment exists to build would have shipped with no execution path and no test
that it works. Gate 9 now checks, per grant, that Unit A and Unit B are `certified` and
carry a SimForge PASS. An empty deployment still blocks there, arrived at from evidence
rather than asserted.

**Gate 9.5 became a port.** It is the one fact The Office genuinely cannot record. One
method, one string, one shipped implementation (`PartitionAbsent`) that reports the truth
about this deployment. Production behaviour is unchanged; the tests can now reach Gate 12.

**P12 split in two.** Gate 10 catches a void signature before Gate 11 ever runs, so Gate
11's own re-check needed its own test — a gate that trusts its predecessor's recorded
verdict can be reached by any path that sets the predecessor's state.

**`provisioning_run.artifacts_hash` was never written**, so a completed run could not say
what it provisioned. And there was no way to abandon a run, which would have left a
venture permanently blocked behind a signature that was never coming — `abort_run` exists
now, and deliberately does not touch grants.

## Out of scope

The Pack Editor and Provisioning Console screens — this increment unblocks them.
Real SimForge. The four missing knowledge bases (Gate 6 reports the gap rather than
pretending).
