# Blocking — what must exist before Burkham Wickmont serves a client

Not deferred. Deferred items are in `capitalforge/docs/decisions/deferred.md` and
each one has a reason it can wait. **Nothing on this page can wait**, because each
is a thing the system currently claims and does not have.

The distinction matters more than the list. A deferred item is work not yet done.
An item here is a **capability the vocabulary already assumes** — ten operating
instructions, the Business Pack and the compliance library all use words that mean
nothing until these exist, so every document that reads correctly today is
overstating the system until they do.

---

## B1. Approving a proposal does not execute it

**Every Burkham position is `trust_tier_ceiling: propose`.** All five. So `propose`
is not one path among several — it is the only tier any Burkham agent will ever
hold, and it is the tier that does not complete.

What works: a call below `auto_execute` is refused, a `proposal` row is written
with the payload and trace, and `POST /api/proposals/{id}/decide` records an
approval. Verified end to end on 3 September 2026 against `scan_communication` —
no Forge call, no ledger row on either side, nothing written at CapitalForge.

What does not exist: **any path from an approved proposal to the call it
describes.** `proposals.mark_executed` — the function that links an approved
proposal to the call that carried it out — has no production caller. Only its
tests call it.

So an operator approves a proposal and nothing happens. The proposal sits
`approved` forever, which is indistinguishable from a queue that has not reached
it yet.

**Interim state, 3 September 2026.** The refusal now names the gap instead of
saying "a proposal was created", and `proposals.decide` stamps the same fact into
`decision_reason` on every approval. That makes the gap unmistakable. It does not
close it.

**What "tier vocabulary means nothing" refers to.** Ten operating instructions
declare `Trust tier: propose`. The Pack sets five ceilings to `propose`. The
compliance library is written around a human approving before an agent acts.
Every one of those is describing a workflow whose last step is not built.

**Blocks:** any Burkham agent doing anything. There is no tier at which an agent
can complete an act — `auto_execute` is not granted anywhere in this Pack, and
`propose` stops at the proposal.

---

## B2. Nine operating instructions exist as files and none is authored

`forge_operating_instruction` holds live rows for simforge (2), cre-forge (4) and
voiceforge (2). **CapitalForge has none.** All nine manuals are markdown in
`docs/instructions/` and have never been loaded.

Three consequences, and the third is the one that was hiding:

1. **V11 fails for every CapitalForge module**, which is Gate 2 blocked.
2. **Unit A certification has nothing to bind to.** A certification is earned
   against an instruction's `content_hash`; with no instruction, the bootstrap
   used a synthesised hash that corresponds to no text.
3. **Staleness could not fire.** `recompute_staleness` skipped any cert whose
   module had no live instruction, so a certification bound to nothing was the one
   thing that could never go stale. Fixed 3 September 2026 — a Unit A cert with no
   live instruction is now `stale_instructions`, and the call path refuses it.

**That fix stopped the bridge dispatching, which is the correct state.** The
adapter, manifest, credential, venture-to-tenant map and the ledger join on both
sides are all proved and that evidence stands. What is no longer true is that a
CapitalForge module can be called, and it should not be until a real instruction
exists to certify against.

**Blocks:** Gate 2, and every grant.

---

## B3. No SimForge verdict for any CapitalForge module

Every CapitalForge certification was written by a script. They carry
`simforge_verdict IS NULL` and a `scenario_pack_ref` beginning `NO SCENARIO RUN -`.
See `certification.md`, which carries this above the fold.

**Blocks:** a real client. Not the bridge — a bootstrap was the right call to prove
the plumbing — but the two must not be confused, and a bootstrapped certification
looks identical to an earned one everywhere except that column.

---

## What is NOT on this page

**`lender_match` and `build_packet`.** They have no implementation under any
spelling, and the Pack declares both at `criticality: hard` with a role defined
around `lender_match`. That is blocking for the *Pack as written*, but the fix is
a ruling — build them, or take them out the way `bureau_pull` and `readiness_score`
were on 1 September — rather than work. It is not on this list because nobody
should do it without deciding first.

**`statement_pull` and `portfolio_health`.** Routes exist and are bindable. What is
missing is a manual, which is authorship, not engineering.
