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

## B4. SimForge's own certification was issued by nothing, and could not have been otherwise

On 4 September 2026 The Office made its first brokered call to SimForge. It required a
Unit A and a Unit B certification, and both are bootstraps:

    unit A   agent x simforge x gate_result    attested_by = 'bootstrap'
    unit B   engineering x simforge            attested_by = 'bootstrap'
             rubric_version = 'phase0.9-simforge'
             simforge_verdict IS NULL

Same shape as B3, and one degree worse in a way worth stating plainly.

### The circularity

A Unit A certification answers *"may this agent operate this module?"*, and the thing that
answers it is a SimForge scenario run. **The module here is SimForge's own.** So the
certification that permits the first call to SimForge would have to come from SimForge,
which cannot be called until the certification exists.

There is no ordering of those two events that is not a bootstrap. This is not a corner
that was cut; it is the base case of a recursive definition, and the only honest thing to
do with it is write it down where somebody will find it.

### Why that circularity is the argument FOR scenarios, not against them

The tempting reading is that a certification which cannot be earned proves the requirement
is ceremonial. It proves the opposite.

Every other certification in this system is supposed to mean *an agent was put through
scenarios it could fail and did not*. This one means **a human decided**. Those two things
are indistinguishable in the `certification` table except for one column — which is exactly
why `attested_by` was added on 3 September, and exactly why B3 exists. If the distinction
did not matter, there would be nothing to record here.

The moment SimForge can run a scenario pack against its own `gate_result` module, this row
should be replaced by one that column can vouch for. Until then, an agent holds
`auto_execute` on a Forge because somebody said so.

### What retires it

**A SimForge scenario pack for `simforge/gate_result`, run by a DIFFERENT SimForge
instance than the one being certified.** That is the part that is not obvious: running the
pack on the same instance certifies the thing against itself, which is where this entry
started. A second instance — a staging deployment, or a container the CI job starts — is
what makes the verdict mean something, because the certifier and the certified are then
two systems that can disagree.

That is also the strongest argument yet for SimForge having a deployment. It has never had
one (`simforge/docs/adr/ADR-0045`), and this is the first requirement that a compose file
on a developer's laptop cannot satisfy.

**Until then:** the row says `bootstrap` and carries its reason. A reader who filters
`attested_by = 'simforge'` will not find it, which is the whole point of that column.

**Blocks:** nothing today — the bridge is proved, and a bootstrap was the right call to
prove plumbing, exactly as B3 says. It blocks **any claim that SimForge is certified**, and
it will block a real client for the same reason B3 does.

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
