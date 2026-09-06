# Business Pack and the Validator — Phase 3, increment 1

Gates 1 and 2 of the provisioning pipeline. The Pack is the input artifact a human
authors; the validator is what refuses a bad one.

## Run it

```bash
.venv/Scripts/python -m generators validate packs/greenstone.yaml
.venv/Scripts/python -m generators validate packs/greenstone.yaml --no-db
```

Exits 1 on any FAIL **or** NOT_RUN. NOT_RUN is non-zero deliberately: a Pack whose
bridge check could not run has not been validated, and a green exit code would say
otherwise.

## Shape vs. meaning

Pydantic handles shape — required fields, types, enums — and fails at load.
The 33 rules handle meaning: cross-references, capacity arithmetic, whether a declared
framework resolves to a runtime flag.

They are separate because the two failures read differently to an author. A missing
`venture_name` is a typo. "Projected daily approvals exceed reviewer capacity" is a
design problem with the venture, and reporting it alongside a YAML indentation error
buries it.

`extra="forbid"` on every model: a Pack with `positons_required` fails loudly rather
than producing a venture with no positions and no explanation.

## The report is not a boolean

Every rule yields id, severity, verdict and a message naming the offending value. A
validator that answers `False` sends an author looking; this one says:

```
V13 FAIL: 400 projected approvals need 2000 review-minutes against 360 available
          (0.6 x coverage). Trust tiers become decorative above this.
```

Order is `V1..V27` numerically, so two runs of the same Pack produce byte-identical
reports and a snapshot diff is never import-order noise.

## Some rules read the world, not the document

**V2 (Gate 0), V6, V11, V28, V29, V30, V31, V32, V33.** A Pack that *declares* a Forge is
bridged proves nothing — that is precisely the state Gate 0 exists to catch. There is a
test asserting a Pack cannot declare itself bridged.

"Bridge operational" means all three of: registered in `forge_registry`, health not
RED, **and** a `forge_tenant_credential` exists. Healthy is not the same as reachable;
a Forge with no credential is one the broker cannot authenticate to however green its
health looks.

Without a connection these report **`NOT_RUN`, never `PASS`**. Part 10.1 says NOT_RUN
must never be reported as a failure; the converse matters just as much here.
`ValidationReport.passed` is False when anything is NOT_RUN.

V24 is deferred to Gate 4.5 — appointment output does not exist at Gate 2 — and is
reported as NOT_RUN rather than silently passed.

## V30 is not a capacity check — Gate 4.5 is

Two questions that sound like one:

| | asks | needs | when |
|---|---|---|---|
| **V30** (WARN) | is the department **large enough at all** for the headcount requested? | the department's total size | Gate 2 |
| **Gate 4.5** (V24) | are those seats **uncommitted** — is anybody actually free? | appointment output | after appointment |

A Pack wanting 20 researchers from a department of 14 is wrong on its face and should be
caught while somebody is still editing it. That is all V30 does.

**Nobody should read a V30 pass as "there are people free."** It compares against total
headcount and knows nothing about who is already allocated; a department of 14 with all
14 committed elsewhere passes V30 and fails Gate 4.5. Greenstone is the standing example
of the pair disagreeing — it passed the Gate 2 estimate and failed Gate 4.5 on real
reviewer-minutes.

## A rule that compared nothing must not pass — count what you checked

**This has now happened twice, in two codebases, from the same two lines of code.** It is
the most likely way a new rule is wrong, so it is written here rather than only in the fix.

### The shape

```python
    over = [
        f"{name} wants {count} of {seats[name]}"
        for name, count in wanted.items()
        if name in seats and count > seats[name]     # <- filter
    ]
    if over:
        return (False, ...)
    return (True, f"{len(wanted)} department(s) have seats")   # <- count
```

Two independent defects, and either alone is enough:

1. **The filter can empty the comparison set.** `if name in seats` silently drops every
   subject that could not be looked up. A rule whose subjects all fail the filter compares
   nothing, reaches the bottom, and returns `True`.

2. **The count comes from the wrong list.** `len(wanted)` is what was *asked about*, not
   what was *compared*. So the message does not merely overstate — it reports the number
   of things the rule skipped as the number it verified.

Together they produce a confident sentence that is the exact inverse of the truth. V30
answered **"3 department(s) have seats for what the Pack asks"** about three departments
the Village does not have. Not one of the three was compared to anything.

### Why the filter looks correct when you write it

`if name in seats` reads as defensive: it avoids a `KeyError`. And it does. What it also
does is convert *"I could not check this"* into *"this had nothing wrong with it"*, and
those two are not the same claim. The `KeyError` you avoided was the rule telling you it
had a subject it could not evaluate.

### The rule

**Split the subjects into checked and unchecked, and let each decide something
different.**

```python
    checked   = {k: v for k, v in wanted.items() if k in seats}
    unknown   = sorted(set(wanted) - set(checked))

    if over_capacity(checked):    return (False, ...)      # the rule's actual finding
    if not checked:               return (None,  ...)      # NOT_RUN, never PASS
    message = f"{len(checked)} checked"                    # count the compared list
    if unknown:  message += f"; {len(unknown)} not checked ({...})"
    return (True, message)
```

Three obligations, in order of how often they are missed:

- **Count the compared list, never the wanted list.** If those two numbers can differ,
  reporting the wrong one is reporting the opposite of what happened.
- **Zero comparisons is `None` — NOT_RUN — not `True`.** A rule that examined no subject
  has not passed; it has not run. `ValidationReport.passed` already treats NOT_RUN as not
  passing, so this costs nothing and is the honest verdict.
- **A partial check names the half it skipped**, and points at the rule that owns it.
  V30 defers to V29, which is the FAIL that says those departments do not exist.

### Where else this has happened

**The Village, `1c43c529`** — *"a validator that examines zero subjects must fail, not
pass"*, the same defect in a different validator, found first and fixed there.

**V30 here**, found on 6 September the first time the Village was running and the rule
could actually reach a department list. It had been NOT_RUN for its whole life, so its
pass path had never executed against real data.

That second point is the part worth carrying: **a rule that has only ever been NOT_RUN has
never had its pass path run.** Reading it proves nothing about it. When a world rule
becomes reachable for the first time, treat its first PASS as unverified until you have
seen it compare something.

### Testing it

The must-fail fixture in the next section proves the FAIL path. It does not touch this.
A world rule needs a third case: **a subject the world does not contain**, asserting
NOT_RUN. `test_v30_does_not_pass_when_no_department_could_be_checked` is that test, and
it fails against the version this section describes.

## Every FAIL rule has a must-fail fixture

Blueprint §5 test strategy. The must-fail half is the half that matters: a rule with
only a must-pass fixture is a rule nobody has watched fire, and a rule that has never
fired might not. The failure mode is a green Pack validation that checked nothing.

`test_no_rule_lacks_a_must_fail_case` fails the build if a rule ships without one.

Mutations are applied to a deep copy of the **real** Greenstone Pack, so each fixture is
realistic in every respect except the one thing being broken.

## V32 does not trust the database either

V6 resolves a Pack's modules against `forge_module_registry`. Both sides of that
comparison are things a human wrote — a Pack's `modules_expected` is a list somebody
typed, and a registry row is a row somebody typed — so V6 compares two claims and can
find a typo. The Burkham Pack declared twelve CapitalForge modules; three of them did not
exist, all three were found by hand, and `lender_match` had been granted `auto_execute`
over a capability that was not there.

**V32 asks the Forge.** Every adapter serves `GET {base_url}/_modules`, which returns
`sorted(MODULES)` over its dispatch map. That answer is derived rather than asserted: a
name is in it if and only if a handler is bound to it. It is the only artefact in the
path with that property, which is why the rule reaches for it instead of for a row.

**What a PASS proves, and `render()` prints it:** a handler is bound to the name. Not
that it works, and not that it does what the name says. It automates the half of the
conformance question that was already being done by hand and does not touch the other
half — `readiness_score` is bound, answers 200, mutates nothing, and scores a business
from query parameters it never reads. That class is found by reading the source, and it
lives in `forge_module_exclusion`.

**NOT_RUN is the expected verdict today.** No CapitalForge adapter exists, so all twelve
of the Burkham Pack's modules are unresolved and Gate 2 blocks. That is neither a FAIL —
nothing about the Pack is known to be wrong — nor a PASS. `report.passed` is already
False on any NOT_RUN, and this is the rule that makes that discipline earn its keep.

A probe (`OPTIONS {base_url}/{module_id}`) is the fallback where an adapter exists
without a manifest. It is calibrated per run against an id that cannot exist, and reports
NOT_RUN rather than PASS if that id does not 404 — which is what a catch-all
`POST /{module_id}` dispatcher does, so the fallback usually refuses to answer. That is
the intended behaviour: an uncalibrated probe is a green light generator.

`scripts/verify_forge_modules.py --check` is the same question outside a Pack, for CI. It
never deletes a row and never invents one: a module that stopped resolving is reported
so a human can revoke the grant, and a module the Forge dispatches that the registry has
never heard of is reported rather than added, because a Forge does not get to enlarge its
own agent-facing surface.

## V11 asks whether the module the curriculum teaches exists

V11 had two questions, and both were about the document: are instructions authored for
every module a position operates, and do they teach anything (a `content_hash` computed
over `"what_it_does": "Documented."` is a valid hash of nothing).

Neither asks whether there is anything on the other end. `cre-forge/generate_loi` had a
live instruction that `curriculum_quality.assess` rated `state=complete`, for a module
CRE Forge has never dispatched — no service, no route, no letter-of-intent among its four
contract templates. V11 passed it.

**This one reaches past the Pack.** SimForge trains an agent against that text and issues
a certification carrying its `content_hash`. Afterwards a certification for a module with
no handler reads exactly like a certification for a real one: the row is there, the hash
resolves, the agent is certified, and nothing downstream can tell the two apart. V32
refuses a Pack that *declares* a module the Forge does not dispatch; this is the same
refusal one table over, on the path that ends in a certification rather than a grant.

So V11 now resolves each taught module against the Forge's `_modules` manifest and fails
when one is absent. A missing or hollow instruction still outranks an unreachable Forge —
a document nobody wrote is a finding without asking anybody — and where the Forge cannot
be asked at all, V11 reports NOT_RUN rather than passing on the two questions it could
answer.

The `generate_loi` instruction and its registry row were deleted together on 2026-09-02.
Instructions are normally superseded rather than deleted, because `superseded_at` keeps
the answer to "certified on what, exactly" readable; the reasoning for deleting this one
is in `docs/instruction-deletions.md`.

## V33: one instruction, one content_hash

Two live instructions on the same Forge may not share a `content_hash`.

A certification is bound to `instruction_content_hash`, and that column exists to answer
one question — certified on what, exactly. All five live `cre-forge` instructions were
byte-identical, written at the same second by the same author, carrying **one** hash
between them, with no module's own name appearing anywhere in its own text. Every one
said "Performs one operation against the Forge and returns its result", which is true of
any module; `underwrite_deal`'s said it "does not write to any other system", and it
upserts a `DealAnalysis` row.

**This is the class `curriculum_quality.assess` is structurally unable to see.** That
assessor reads one document and asks whether it teaches anything — it was built to catch
`"what_it_does": "Documented."` — and it rated all five `complete`, correctly by its own
lights. The text is real prose and it does not go nowhere. It is simply not about any
particular module, and no reading of one document in isolation can establish that. Two
documents can, and comparing hashes is the cheapest possible way to do it.

Superseded rows are excluded. A superseded instruction keeps its hash so the
certifications citing it stay readable, and it is not competing to describe a module.

## V31 asks whether a tier is survivable

A module can resolve perfectly and still be wrong to run with nobody watching. V31
refuses `auto_execute` over a module the registry records as `is_mutating` **and**
`idempotency_support = at_most_once`.

That is the shape `regulator_dossier_export` is written around: every call mints an
`exportId`, writes a row and emits an event, so a retry after a timeout produces a second
export of the same inquiry and the audit trail then shows two. Its sibling
`compliance_manifest_assemble` mints nothing and retries freely — same permission, same
reader, opposite handling. An agent is the caller least likely to go looking for the
first `exportId` before minting a second, and an unattended agent is the one with nobody
to stop it.

`key` and `natural` both pass: a retry the Forge de-duplicates is a retry the audit trail
survives. The finding is the tier over that module, not the module.

**A FAIL outranks an unresolved module.** If one module is refused and another has no
registry row, V31 reports the refusal. A defect that has been found does not stop being
found because something else could not be checked.

**And a hand-written row cannot produce a PASS.** `is_mutating` is what this rule turns
on, and the first run of `scripts/verify_forge_modules.py` against the live CRE adapter
corrected `property_lookup` from `TRUE` to `FALSE` — the one module anybody had ever
called had been recorded as a writer, by hand, and it is a search. A row that
understates mutation is the one that hands an unattended agent a writer, so a clean
answer resting on `verification_method = 'hand'` is NOT_RUN and names the verifier. A
refusal still stands on such a row: blocking on a claim that might be wrong is the safe
direction, passing on one is not.

## V13 arithmetic

```
projected_approvals x median_review_minutes  <=  coverage_hours x 60 x 0.6
```

The 0.6 is Part 14's utilisation factor. A human reviewing for 100% of their coverage
hours does nothing else, and a trust tier backed by a saturated reviewer is a rubber
stamp waiting to happen.

Approvals are estimated conservatively — one per headcount per agent-day for every
position below `auto_execute`. Under-estimating here produces a green check on a
reviewer who is already saturated.

## Two findings from the first run

The validator caught both of these on its own Pack, which is the point of it:

**V22 was wrong.** It compared scenario coverage against *framework names*
(`FTC_TSR`), but "compliance flag" means the `runtime_flag` (`tsr_disclosure_required`)
everywhere else in the system — positions, bindings, and `agent_call_ledger`. The
framework name never appears at runtime, so the rule was unsatisfiable by construction.
Fixed to compare against runtime flags.

**The Greenstone Pack declared VoiceForge but no position operated it** (V25 WARN),
while its scenarios clearly had agents placing recorded calls. Fixed the Pack.

## Gate 0 blocks Greenstone today — as specified

Greenstone's operating Forge is **CRE Forge**. The bridge is going to **CapitalForge**
first. Running the validator against the real database right now:

```
V2 FAIL: bridge not operational: cre-forge: not in forge_registry...
         Gate 0 blocks provisioning against a Forge the bridge does not reach.
```

That is the validator working, not a defect. It clears when CRE Forge is bridged, or
immediately if the first venture becomes Burkham Wickmont against CapitalForge.

## Known gaps

*Last verified: 2026-09-02.*

- **No CapitalForge adapter.** V32 is NOT_RUN for every CapitalForge module, and will be
  until one exists. The contract it must serve is in `docs/forge-adapter.md`.
- **The seven generators do not exist yet** (increment 2). The Pack validates; nothing
  consumes it.
- **Shift assignment and PHI flush** are increment 3.
- **`content_hash: PENDING_AUTHORING`** in the Greenstone Pack. V12 checks presence,
  not that the hash matches authored instructions — that reconciliation belongs with
  the Curriculum generator.
- **No Pack Editor UI** (Part 17).
