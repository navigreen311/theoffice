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
The 27 rules handle meaning: cross-references, capacity arithmetic, whether a declared
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

## Three rules read the world, not the document

**V2 (Gate 0), V6, V11.** A Pack that *declares* a Forge is bridged proves nothing —
that is precisely the state Gate 0 exists to catch. There is a test asserting a Pack
cannot declare itself bridged.

"Bridge operational" means all three of: registered in `forge_registry`, health not
RED, **and** a `forge_tenant_credential` exists. Healthy is not the same as reachable;
a Forge with no credential is one the broker cannot authenticate to however green its
health looks.

Without a connection these report **`NOT_RUN`, never `PASS`**. Part 10.1 says NOT_RUN
must never be reported as a failure; the converse matters just as much here.
`ValidationReport.passed` is False when anything is NOT_RUN.

V24 is deferred to Gate 4.5 — appointment output does not exist at Gate 2 — and is
reported as NOT_RUN rather than silently passed.

## Every FAIL rule has a must-fail fixture

Blueprint §5 test strategy. The must-fail half is the half that matters: a rule with
only a must-pass fixture is a rule nobody has watched fire, and a rule that has never
fired might not. The failure mode is a green Pack validation that checked nothing.

`test_no_rule_lacks_a_must_fail_case` fails the build if a rule ships without one.

Mutations are applied to a deep copy of the **real** Greenstone Pack, so each fixture is
realistic in every respect except the one thing being broken.

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

*Last verified: 2026-08-23.*

- **The seven generators do not exist yet** (increment 2). The Pack validates; nothing
  consumes it.
- **Shift assignment and PHI flush** are increment 3.
- **`content_hash: PENDING_AUTHORING`** in the Greenstone Pack. V12 checks presence,
  not that the hash matches authored instructions — that reconciliation belongs with
  the Curriculum generator.
- **No Pack Editor UI** (Part 17).
