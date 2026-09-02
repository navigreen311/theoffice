# Operating instructions that were deleted, and why

An operating instruction is not ordinary documentation. SimForge trains against it, an
agent is certified against its `content_hash`, and `certification.instruction_content_hash`
is what a later reader uses to answer "certified on what, exactly". Deleting one destroys
the answer to that question for every certification bound to it.

So instructions are not deleted for being wrong. A wrong one is superseded — `superseded_at`
is set, the row stays, and the certifications that cite it can still be read.

This file is for the other case: an instruction that should never have existed, where
leaving it would make a certification **indistinguishable from a real one afterwards**.
Each entry records what was deleted, what it said, and what made deletion the right act
rather than superseding.

---

## `cre-forge` / `generate_loi` — deleted 2026-09-02

**What it was.** One live row, `instruction_version` 1.0.0, `forge_api_version` 1.4.0,
authored 2026-08-25 09:54:58 -07:00 by `00000000-0000-5000-8000-00000000aaaa`,
`content_hash` `9711528544710550fb27127765aa0b83953fbea56c4543644019e5d0c12483e6`,
never superseded.

**Certifications bound to it at deletion: none.**

**Why it was deleted rather than superseded.** CRE Forge does not dispatch `generate_loi`
and never has. There is no letter-of-intent service, no route, and no LOI among its four
contract templates — purchase agreement, assignment, addendum, disclosure. The module was
found by V32 on 2026-09-02 and cut from the Greenstone Pack the same day.

A superseded instruction says *this is how the module used to work*. There is no module.
The row said how to operate a capability that does not exist, and SimForge would have
trained an agent against it and issued a certification carrying its hash. Afterwards, a
certification for a module with no handler reads exactly like a certification for a real
one — the ledger has a row, the hash resolves, the agent is certified. Nothing downstream
can tell the two apart. That is the thing worth preventing, and superseding does not
prevent it.

**What it said, verbatim.** The whole document, because "an instruction was deleted" is
not a record of what was lost:

```json
{
  "what_it_does": "Performs one operation against the Forge and returns its result. The result is data for the agent to act on in a later step, never an action in itself.",
  "what_it_does_not_do": "Does not retry on the agent's behalf, does not write to any other system, and does not decide what happens next. Nothing here is a commitment to a third party.",
  "inputs": {
    "venture_id": "Which venture this call belongs to. Scopes the grant and the ledger entry.",
    "idempotency_key": "Stable across retries of the same task. A new key is a new call, not a retry of the old one."
  },
  "correct_sequence": [
    "Confirm the grant is assignable for this module before calling.",
    "Call the module once with a stable idempotency key.",
    "Read the result; escalate rather than repeating on a 4xx."
  ],
  "failure_signatures": {
    "timeout": "No response inside the deadline. The call may still have landed - re-send only with the same idempotency key.",
    "rate_limited": "429 with Retry-After. Wait the stated interval; do not retry immediately.",
    "silent_partial": "A 200 with fewer results than requested. The upstream index is incomplete rather than empty."
  },
  "retry_vs_escalate": "Retry a 5xx twice with backoff. Escalate any 4xx to a human: a 4xx means the request was wrong, and repeating it will not make it right.",
  "never_do": [
    "Never re-submit after a 200.",
    "Never generate a new idempotency key to force a retry."
  ],
  "compliance_coupling": ["tsr_disclosure_required"]
}
```

**Read that text again, because the other four are the same text.** All five `cre-forge`
instructions — `property_lookup`, `comp_analysis`, `underwrite_deal`, `buyer_match` and
this one — were byte-identical, carried **one** `content_hash` between them, and were
written at the same second by the same author. No module's own name appears anywhere in
its own instruction. Nothing above is about generating a letter of intent, and nothing
above is about searching for a property either.

So this deletion removed a document, and it removed no information: the same words are
still on file four times over. That is a separate finding and it is recorded in
`docs/gaps.md`-style form in the CHANGELOG for 2026-09-02 — a certification's
`instruction_content_hash` currently cannot distinguish which of the five modules an
agent was certified on, because there is only one hash.

**The registry row went with it.** `forge_module_registry (cre-forge, generate_loi)` was
deleted in the same transaction; the foreign key from `forge_operating_instruction` is
what had blocked removing it on 2026-09-02, and is why this file exists.

**What now refuses this shape.** V11 was extended the same day: an instruction whose
module does not resolve against the Forge's own `_modules` manifest fails the Pack, the
same way V32 fails a Pack that declares one. Curriculum for a module that does not exist
is now a Gate 2 failure rather than something found by hand.
