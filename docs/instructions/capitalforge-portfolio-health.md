# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `portfolio_health`
**Endpoint:** `GET /api/portfolio/health`
**Version:** 1.0 — drafted 4 September 2026, against CapitalForge `master`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Rules 1, 2 and 7 govern most of what this module returns and are not repeated here.

**This module returns nothing about an identifiable client**, and it is the only one in this set of which that is true. See §2 and §9 — it changes which compliance entries apply, in both directions.

## 1. WHAT IT DOES

Scores the health of a tenant's whole client portfolio, out of 100, with a letter grade and six components.

One call, one answer:

| | |
|---|---|
| `score` / `grade` | The portfolio score and its letter, **or null** |
| `assessed` | Whether a score was computed at all |
| `businessesAssessed` | The denominator. Every component divides by it |
| `notAssessedReason` | Present only when `assessed` is false |
| `components` | Six named percentages — Consent Completion, Acknowledgment Completion, Compliance Pass Rate, Approval Rate, Payment Performance, APR Management |
| `trend` | Direction, delta and previous score, **or null** |
| `actionItems` | Prioritised suggestions with a `potentialGain` |
| `computedAt` | When it was computed |

It reads seven tables to do it — businesses, card applications, compliance checks, consent records, funding rounds, payment schedules and product acknowledgments — and aggregates them. **It returns none of them.**

## 2. WHAT IT DOES NOT DO

**It does not identify anybody.** There is no business id, no legal name, and no client identifier anywhere in the result — not in the components and not in the action items, which carry only a priority, a title, a description and a `potentialGain`. An agent cannot learn from this module which client is the problem.

That is the module's defining property. Everything else in this manual follows from it.

It does not write. No row changes, nothing is sent, nothing is recorded by the module itself.

**A brokered call is the exception and it is not this module's doing.** A call arriving through The Office writes one `ledger_events` row per call — `office.module.called`, keyed by the trace id The Office also records — whatever the module does, reads included.

**It does not check that you may read this.** No permission guard runs on this route. What scopes it is the tenant read from the token, and role is not consulted. Same absence as `statement_pull` and `submit_application`, and the same note: an agent looking for what stops it should find the answer here.

**It does not assess a client.** A portfolio score is not a client score. Nothing here says anything about any individual business, and a low portfolio score does not identify a weak client any more than a high one identifies a strong one.

**It does not recommend an action for a client.** `actionItems` are portfolio-level: *improve consent completion*, and so on. They name no client and no client can be inferred from them.

**It does not forecast.** `potentialGain` is the score points a component could contribute if it reached 100%, computed from the current denominator. It is arithmetic about the score, **not a prediction about revenue, approvals or client outcomes.**

## 3. WHAT EACH INPUT MEANS

| Input | Meaning |
|---|---|
| tenant | **Not caller-supplied.** Read from the token. The only input this module has |

**There are no parameters.** No path segment, no query string, no body. The call answers for the calling tenant's whole portfolio and nothing narrows it.

That is the most important thing to know about this module's inputs: **an agent cannot scope, filter or date-bound this call.** A caller wanting a subset does not have one available — there is no per-client, per-segment or per-period view here, and constructing one from this answer is not possible because the answer carries no client.

## 4. THE CORRECT SEQUENCE

Two steps, and the order matters:

1. **Read `assessed` before reading `score`.** A null score is not a zero. `assessed: false` with a `notAssessedReason` means there was nothing to compute over — and `score: null` must never be rendered as `0` or as grade F.
2. **Report `businessesAssessed` with any figure taken from this module.** Every component is a percentage over that denominator, so a component percentage without it is a proportion with no population. Shared rule 7.

**Two, and no more.** The prohibitions on what may be said from this score are in §8. This module has one call and no ordering to get wrong beyond these.

## 5. WHAT COMES BACK

**`score: null` is the state to handle first.** Until it was fixed, a tenant with no businesses fell through the guards with every component at its initialiser of `0`, producing **a score of 0 and a grade of F** — so the first screen a new tenant saw said its portfolio was failing.

**"No clients yet" is not the bottom of the scale; it is off the scale.** `assessed` is what to branch on, and `notAssessedReason` says why.

**`trend` is nullable and its null is a different fact.** No trend means no previous score to compare against, not a flat trend. `direction: 'flat'` and `trend: null` are different answers and must not be reported alike.

**The six components are percentages over `businessesAssessed`.** A component at 100% across three businesses and one at 100% across three hundred are the same number and not the same fact.

**`potentialGain` is score arithmetic.** It is what a component would add if it reached 100%. It is not money, not approvals, and not a forecast.

## 6. WHAT FAILURE LOOKS LIKE

| Response | Meaning |
|---|---|
| `200` | Computed. **Read `assessed` before anything else** |
| `401 UNAUTHORIZED` | Authentication context missing |
| `500` | The computation failed |

**A 200 with `assessed: false` is the answer, not a failure.** It means the tenant has no businesses to assess. Report `notAssessedReason` and stop; do not report a score of zero, a grade, or a portfolio in poor health.

**There is no 404.** This module cannot be asked about something that does not exist — it takes no identifier. A tenant that exists always has an answer, and that answer is sometimes "nothing to assess."

## 7. RETRY VS ESCALATE

**Retry freely.** It is a pure read. Nothing is written, nothing is sent, and a retry after a timeout costs nothing and duplicates nothing.

`computedAt` is stamped per call, so two retries carry two timestamps over the same underlying data. That is a fact about when it was computed, not evidence that anything changed.

## 8. NEVER

**Never report `score: null` as zero, or as grade F.** It means nothing was assessed. Shared rule 1: an absence of clients is a fact about the records.

**Never report a component percentage without `businessesAssessed`.** Shared rule 7. A percentage over three businesses is not a portfolio finding.

**Never report `trend: null` as a flat trend.** No previous score is not "no change."

**Never attribute a portfolio score to a client.** This module names no client and none can be inferred. An agent that reads a low Payment Performance component and says a particular client is behind has invented the attribution.

**Never present `potentialGain` as money, approvals, or a forecast.** It is score points.

**Never use this to decide anything about an individual client.** It has no per-client view, and constructing one from this answer is not possible. If a decision needs a client's position, that is `client_read`, `client_read_credit` or `restack_recommend` — each with its own grant.

**Never present this as verified.** It is computed from what is on file at the moment of the call, and what is on file is whatever was recorded.

## 9. WHICH LAWS THIS TOUCHES

`compliance/consumer-privacy-rights-v1` — **the entry applies to what this module reads, not to what it returns.** It aggregates seven tables of personal data about named individuals, and reading personal data is a processing activity whatever the output shape. The score is not subject to an access request; the records it was computed from are.

**No fair-treatment entry applies, and that is a decision rather than an omission.** `compliance/fair-treatment-in-routing-v1` governs inputs to a routing or recommendation decision about a client. **This module returns no client, so nothing it returns can route one.** Every other read module in this set carries that entry because each returns something that feeds a decision about a specific business; this one cannot.

The `Approval Rate` component is the reason to check rather than assume: an approval-rate statistic across a client population is the shape a disparate-impact analysis uses. It is not one. It is a single tenant-wide percentage with no protected characteristic, no per-client breakdown and no comparison group, and reading it as a fairness measure would be reading something into it that is not there.

**No bureau entry applies.** Nothing here is bureau-derived; the module reads applications, consents, acknowledgments, compliance checks, funding rounds and payment schedules, and none of those is a consumer report.

## PROVENANCE

**From the code, read at `master` on 4 September 2026:** the single endpoint and its mount, the absence of a permission guard, the seven tables read, the six component names, the `assessed` / `notAssessedReason` third state and the comment recording why it exists, the nullable `trend`, and `ActionItem` carrying no client identifier.

**Verified by calling it** through the Office adapter before this manual was written, which is the ordering `docs/certification.md` now requires: bind the module, then write the manual.

## OPEN

**Whether a portfolio score should be readable by an agent at all** is not settled here. It is the only module in this set that answers about a population rather than a client, and the question of what an autonomous agent should do with a portfolio-level number — as opposed to a human reading a dashboard — has not been asked. Recorded rather than answered.
