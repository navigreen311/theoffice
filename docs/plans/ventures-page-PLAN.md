# Ventures page — PLAN

The page shows five columns and none of them answers the question a reader opens it to
ask: **where is this venture, and can it go live.** Pipeline state is a venture's most
important attribute and it appears nowhere.

---

## The one real modelling decision

Everything else here is presentation. This is not.

A venture has always been **an engagement, not a table** — derived from grants, manifest
rows or a budget. That was right, and it is why `/api/ventures` could exist at all
before anything was provisioned. But the brief asks for two things it cannot support:

- **a draft venture** — created, named, with no Pack yet;
- **`archived` and `winding down`** — states nothing can derive.

So a `venture` table is added, holding **only what cannot be derived**: slug, display
name, category, environment, lifecycle state, who created it. The Pack stays the source
of truth for everything it declares. When a Pack exists, its `identity.venture_name` and
`identity.category` win — the table's copies are what a draft has *before* there is a
Pack to read.

The alternative was a stub Pack for drafts. `BusinessPack` is `Strict` and rejects
anything incomplete, so a stub would mean filling a dozen required fields with invented
values — and an invented `monthly_usd_cap` is exactly the kind of number V18 exists to
stop a venture reaching production with.

Draft ventures cannot receive grants, appointments or a budget. Enforced by there being
nothing to grant against: no Pack means no manifest and no runtime config.

## Status, derived from what actually happened

One pill, from this ladder, first match wins:

| Status | Derived from |
|---|---|
| `archived` | `venture.lifecycle_state` |
| `winding down` | `venture.lifecycle_state`, or the Pack's `operating_status` |
| `draft` | no live Pack |
| `blocked at gate N` | the venture's latest provisioning run, blocked |
| `validating` | Pack exists and the validator reports a FAIL |
| `in certification` | a run has passed Gate 8 |
| `awaiting sign-off` | a run is `awaiting_human` at Gate 10 |
| `live` | a run completed, or assignable grants exist |

**`blocked at gate N` always names the gate.** "Blocked" alone tells a reader nothing
they can act on.

With no provisioning run there is still a truthful answer: Gate 0 and Gate 1 can be
evaluated from the world directly, which is how Greenstone reports *blocked at gate 0 —
the bridge to CRE Forge does not exist* without anybody having started a run.

## The blocked reason is computed, never a lookup table

The brief gives three example sentences. One of them — "structural PHI flush is not
built" — **is no longer true**; the flush shipped in Phase 3.3. That is the argument
against hardcoding them: a table of blocker strings is right the day it is written and
wrong afterwards, which is the rot Gate 6's knowledge-base list had.

So the sentence comes from the validator's own message for the rule that failed. V2's
message already names the Forge and why it does not resolve.

## The portfolio panel

Five ventures are named in the master prompt; one is authored. The other four must be
**visible as absent**, because absence that looks like health is the failure this
console exists to avoid — the same principle as the Compliance page's banner.

The roster lives beside the code that uses it with its source named, and the panel
computes which of them are missing rather than asserting it, so it cannot claim a
venture is unauthored once somebody authors it.

## Spend is not measured, and the page must say so

`usd_cost` is never populated — the stub Forge reports no usage. A spend bar reading
`$0 of $4,000` would be read as "nothing spent" when it means "nothing measured". Those
are different, and only one of them is evidence.

So the strip shows the cap, states that attribution is not wired, and the burn-down bar
renders only when there is real spend to render.

## Acceptance tests

| # | Test |
|---|---|
| V1 | a draft venture is created, is `draft`, and holds no grants |
| V2 | the slug is derived, editable at creation, immutable after |
| V3 | creation is audited with the human as actor |
| V4 | **`blocked at gate N` names the gate and the specific blocker** |
| V5 | the blocker text comes from the validator, not a lookup table |
| V6 | every metric carries a denominator |
| V7 | the four unauthored ventures are reported as missing |
| V8 | authoring one removes it from the missing panel |
| V9 | archiving is reversible only by an explicit un-archive, and is audited |
| V10 | a venture with no budget reads `unmetered`, not `$0` |
