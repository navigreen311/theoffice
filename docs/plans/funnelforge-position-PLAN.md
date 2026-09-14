# Landing the FunnelForge binding and the Marketing Operations Coordinator

**This is an instruction, not a record. Neither edit below has been applied.**
`packs/burkham-wickmont.draft.yaml` carries no `funnelforge` binding and no Marketing
Operations Coordinator — measured 14 September 2026, both counts zero.

**It replaces `docs/plans/funnelforge-position-DEFERRED.patch`**, which held the same two
edits as a unified diff. The diff was deferred nine times and read on the ninth, by which
point the world it described had moved: it declares one `trust_tier_ceiling` for nine
modules, which was the only way to express autonomous send before per-module tiers landed,
and it cited a V31 refusal that had already expired. A diff carries context lines that go
stale silently; a document carries the decision, and whoever lands it edits the Pack.

`scripts/land_funnelforge_position.py` reads the two blocks below and applies them in the
one order that leaves V31 able to speak. **It is the enforcement, not a convenience** —
B39 records that the ordering rule was correct and unenforced from 9 September until the
script existed, restated in four places and runnable in none.

---

## Why `auto_execute` is correct now, and was not before

§4.5 calls these sends Village-autonomous: nobody in the path. `auto_execute` is the only
tier that reaches a Forge at all — step 7 of the client library turns anything below it
into a proposal and makes no HTTP call — so declaring `propose` would not be a cautious
autonomous send, it would be a different thing wearing its name.

**Until 12 September V31 was right to refuse it.** Seven of the nine are mutating, an
email leaves the system and reaches a person, and nothing on FunnelForge's send path could
recognise a repeat. `at_most_once` was the truth.

**FunnelForge PR #160 merged 2026-09-12 04:55 UTC and changed the fact.**
`apps/api/src/services/email/idempotency-store.ts` takes an atomic Redis claim
(`SET key value PX <ttl> NX`, holding across replicas), answers a repeat from its record,
fails closed with a 503 when Redis is unreachable, and matches Resend's 24-hour window so
a key cannot expire on one side while live on the other.

The header is **optional** there, so `key` rather than `natural`: an unkeyed repeat still
sends twice. `adapters/funnelforge/app.py` now forwards `Idempotency-Key` from The Office
to FunnelForge, and `tests/adapters/test_funnelforge_idempotency_hop.py` asserts it
survives the hop. The declaration and the forwarding are one fact.

**With the seven at `key`, V31 refuses nothing.** The position-wide ceiling is correct as
written, and no per-module split is needed.

---

## What still has to be true before this lands

| | |
|---|---|
| `funnelforge` in `forge_registry` | **absent** — no `base_url` while the ingress is dead |
| rows in `forge_module_registry` | **zero** — `scripts/register_funnelforge_modules.py` writes them |
| V11 / V23 | **pass** — nine manuals and their scenario sets are in `docs/instructions/` |
| V32 | **NOT_RUN** until the adapter is deployed and reachable, which is the correct answer |

**The order is not a preference.** With no binding, `funnelforge` is not in V31's Forge set,
so registry rows written first are never queried and the rule reports NOT_RUN *even with
all nine rows present*. The binding half is safe to land alone because `unattended_writes`
iterates `positions_required`, and with no FunnelForge position declared it examines no
module of that Forge.

---

## Block 1 — the binding

Insert into `forge_dependencies.forge_bindings`, immediately before the line
`  external_software:`.

```yaml
    - forge: funnelforge
      api_version: 1.0.0
      criticality: soft
      modules_expected:
        [send_intake_acknowledgment, send_scheduling_confirmation,
         send_deliverable_cover, send_followup_no_engagement,
         send_brief_cover, distribute_referrer_briefing,
         schedule_blueprint_call, capture_contact, read_funnel_analytics]
      # EMPTY BY DECISION, not by oversight. §6.2 and §6.3 cap FunnelForge at anonymous
      # browsing data and named-contact marketing PII - no credit data, no Plaid data,
      # no financial statements, nothing FCRA-regulated, and it cannot query Console for
      # credit data to segment sequences. None of this Pack's four runtime flags is
      # about marketing contact. `broker/compliance_couplings.py` records what a
      # plausible-but-wrong flag costs: it resolves, it passes every check, and it is
      # the wrong framework.
      compliance_flags_propagated: []
      fallback_behavior: queue
      rate_limit_policy: {max_rps: 2, burst: 5, backoff: exponential, on_429: queue}
      credential_mode: brokered
      cost_center: burkham-marketing
```

`criticality: soft` deliberately, not `hard`. A hard binding asserts the workflow cannot
run without it; Burkham's capital work runs whether or not a marketing email goes out, and
`fallback_behavior: queue` says what happens instead. The CapitalForge binding is `hard` on
two modules that do not exist, which is this failure from the other direction.

**Spelling:** every name is a key in `adapters/funnelforge/modules.py`. The adapter is the
naming authority and V32 resolves this list against it; a second spelling does not quietly
work.

**The seventh §4.5 template — the engagement letter cover email — is deliberately absent**
and has no module. It is *human approve send* through Deliverable Approval Workflow
(Console module 3.4), which is not connected to the bridge. Its absence is the gate
working, not an omission.

---

## Block 2 — the position

Insert into `positions_required`, immediately before the line `capacity_demand:`.

```yaml
  - position_title: Marketing Operations Coordinator
    reports_to: venture_operator
    duties:
      - Send approved marketing templates in a Pass compliance state
      - Book Blueprint calls against the published appointment types
      - Record newsletter and gated-download contacts, and read funnel analytics
    forge_modules_operated:
      [send_intake_acknowledgment, send_scheduling_confirmation,
       send_deliverable_cover, send_followup_no_engagement,
       send_brief_cover, distribute_referrer_briefing,
       schedule_blueprint_call, capture_contact, read_funnel_analytics]
    source_department: marketing        # Burkham calls this "Marketing Ops"
    compliance_flags_in_scope: []
    headcount: 1
    trust_tier_ceiling: auto_execute
    lifecycle_stages_owned: [Intake, Diagnostic, Placement]
```

**No `module_trust_tiers`, deliberately.** With all nine permitted by V31, one ceiling says
the same thing as nine identical per-module entries and says it once. Add them if a module
ever needs to differ — which is what the field is for, and is not the case today.

**`forge_modules_operated` is bare**, matching all 19 refs in both live Packs. Entry 48
ruled it should be qualified `forge_id/module_id` and that ruling is unexecuted; whoever
executes it changes this block with the other 19 rather than leaving it the twentieth.

---

## The sequence

1. apply **Block 1** — no position is declared yet, so V31 examines no module of this
   Forge and cannot go mute; this also puts `funnelforge` into V31's Forge set, which is
   what makes step 2's rows readable at all
2. `scripts/register_funnelforge_modules.py --confirm` — it reads `modules_expected` from
   the Pack, so it has a declared half only after step 1
3. verify nine rows exist and none is `verification_method = 'hand'`
4. apply **Block 2**
5. **re-read V31. NOT_RUN reverts both blocks and exits non-zero.**

Step 5 is the enforcement; steps 1–4 are only the method. It checks the property the
ordering exists to produce, so an ordering broken some future way is still caught.
**A V31 FAIL is kept, not reverted** — a refusal is an answer. A NOT_RUN is silence, and
silence is what the order exists to prevent.

Between steps 1 and 4 V6 FAILs for a few seconds: nine modules declared, no rows. That
window is real and step 2 closes it. The alternative window — position first — produces a
V31 that cannot speak, which is the one state B33 exists to prevent.
