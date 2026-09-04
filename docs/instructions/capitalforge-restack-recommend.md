# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `restack_recommend`
**Endpoints:** 3 GETs — two on `/api/restack`, one on `/api/v1/dashboard`
**Version:** 1.4 — corrected 3 September 2026, against CapitalForge `f20a81b`
**Status:** draft, pending Compliance Review Board

Read `foi-shared-rules.md` first. Rules 1, 1a and 2 govern most of what this module returns and are not repeated here.

The reasoning behind every rule below is in `capitalforge/docs/decisions/restack-recommend.md`. Where this manual says a thing is deliberate, that file says why.

## 1. WHAT IT DOES

Answers whether a client is ready for another round of funding.

| Endpoint | Returns |
|---|---|
| `GET /api/restack/check/:businessId` | One client, with the basis for the verdict |
| `GET /api/restack/eligible` | The tenant's eligible clients, with counts |
| `GET /api/v1/dashboard/restack-opportunities` | The same scan, presented for a dashboard |

These are different endpoints, not one router mounted twice. Unlike `client_read`, there is no `/v1` alias here.

**One rule set.** Two surfaces once answered this question differently — `>= 70` against `> 70`, ninety days from the last application against the last completed round, utilisation checked or not. A client scoring exactly 70 was eligible on one and invisible on the other. The engine is now the single copy and the dashboard presents it.

## 2. WHAT IT DOES NOT DO

It does not write. All three are pure reads. Nothing is recorded, including no record that the question was asked.

**It does not forecast.** There is no estimated additional credit and no pipeline value. Both existed until 1 September and were deleted with nothing in their place — the figure was the previous round's *target* multiplied by 0.75, a number derived from nothing. Nothing in this system predicts what a client will be approved for.

It does not measure recovery. See §6.

It does not decide. An eligible verdict is an assessment, not an instruction. Placement is a separate act with its own gates.

**It does not narrow, filter or scope.** `eligible` and `restack-opportunities` take no parameters at all — no path segment, no query string, no body. They answer for the calling tenant's whole active population, and an agent that wants a subset filters the answer rather than the request. See §3.

## 3. WHAT EACH INPUT MEANS

| Input | Meaning |
|---|---|
| `businessId` (path) | **`check` only.** The business to assess |
| tenant | **Not caller-supplied.** Read from the token. The only input `eligible` and `restack-opportunities` have |

**Two of the three endpoints take no parameters at all** — no path segment, no query string, no body. They answer for the calling tenant's whole active population, and the tenant comes from the token.

That is the single most important thing to know about this module's inputs: **an agent cannot narrow, filter or scope these two calls.** What comes back is everything the tenant has, and a caller that wants a subset filters the answer rather than the request.

## 4. WHAT COMES BACK

### `check/:businessId` — one client

`reasons` is **always populated, on both verdicts.** Five entries, one per criterion, phrased as findings either way — "Utilization 22% is within limit" as readily as "exceeds 40% max".

It is not an error list. An agent that reads `reasons` only when `eligible` is false reports a pass with no basis.

Three fields are three-state, and the nulls do not mean the same thing:

| Field | Null means | Effect |
|---|---|---|
| `readinessScore` | Never assessed | **Blocks** |
| `currentUtilization` | No credit profile on record | **Blocks** |
| `daysSinceLastApp` | No prior applications | **Passes** — eligible for a first round |

A fourth field is nullable and ambiguous: `lastCompletedRoundAt` — the dashboard's `last_funded_date` — is null both when there is no completed round and when a completed round carries no `completedAt`. Two states, one null, on a field presented as a date. **Do not report it as "never funded."**

This is the trap in the module, and it is deliberate. Two nulls block, one passes, and the difference is shared rule 1 exactly: never having applied is a fact about the client. An unpulled credit file is a fact about Burkham's records. The first is information; the second is a gap.

**Do not generalise "null blocks."**

### `eligible` — the tenant scan

Returns **only eligible clients.** Ineligible ones are dropped, not returned with `eligible: false`. So `total` is not a denominator.

Three counts make it readable, and `notAssessedCount` is not optional context:

| Count | Means |
|---|---|
| `activeCount` | All active clients |
| `evaluatedCount` | Those with an assessed score at or above 70 |
| `notAssessedCount` | Those with no score at all |

The scan pre-filters with a `>=` that excludes nulls, so an unassessed client never appears in this scan in any form. `notAssessedCount` is the only evidence they exist. "3 clients are ready to re-stack" reported without it is 3 out of an unstated population.

**The three counts do not partition.** `activeCount` is the whole population; the other two are subsets that do not meet. A client assessed at 65 is in neither — assessed, below the floor, with no count of its own. "3 eligible of 40, 12 never assessed" leaves 25 clients derivable only by subtraction.

### `restack-opportunities` — the dashboard

The same scan with renamed keys, plus the three counts. It carries **no `reasons`, and of the five criteria only the readiness score** — utilisation, days since last application, the active count and the in-progress round are all absent. You cannot tell from this surface why anyone qualified.

It is a list to act on, not a basis to report from. An agent asked to justify an opportunity calls `check/:businessId` per client.

## 5. THE CORRECT SEQUENCE

The three calls have no ordering between them — any one can be made without any other. What has an order is how a verdict is read and what may be said from it:

1. **Pick the endpoint that carries a basis.** `check/:businessId` returns `reasons`; the dashboard surface does not. An opportunity seen on the dashboard is not justified until `check` has been called for it.
2. **Read `reasons` on both verdicts, not only on a refusal.** It is always populated, five entries, phrased as findings either way. An agent that reads it only when `eligible` is false reports a pass with no basis.
3. **Read each null for what it is, and never generalise "null blocks."** `readinessScore: null` means never assessed and blocks. `currentUtilization: null` means no credit profile on record and blocks. `daysSinceLastApp: null` means no prior applications and **passes**. Two block, one passes, and the difference is shared rule 1: never having applied is a fact about the client; an unpulled credit file is a fact about Burkham's records.
4. **On a scan, read `notAssessedCount` before reporting `total`.** `eligible` returns only eligible clients, so `total` is not a denominator, and an unassessed client is invisible in that scan by construction. Shared rule 7.
5. **Report the verdict as an assessment, never as an instruction.** An eligible verdict is not a recommendation to place. Placement is a separate act with its own gates, and the readiness score is a fundability floor rather than a recovery measure — see §6.

Step 3 is the trap this module is built around, and step 5 is the one that carries furthest: everything here feeds a decision somebody else owns.

## 6. THE READINESS SCORE IS A FUNDABILITY FLOOR, NOT A RECOVERY MEASURE

`fundingReadinessScore` is computed at onboarding and measures **fundability** — revenue, business age, industry risk, credit, leverage. This module asks whether a client has **recovered enough to stack again**.

Those are not the same question. A client who has never borrowed and a client who has just worked through a hardship can score identically on fundability while being in completely different positions for a re-stack.

Using it here is deliberate and it is deliberately a **floor**: a client who is not fundable at all should not re-stack either.

**The recovery test is the other four criteria** — days since last application, utilisation, active applications, and a round already in progress. Those carry the recovery signal. The score carries only *fundable at all*.

An agent must not report a readiness score as a recovery assessment.

**Known limitations of the score itself, recorded in `docs/gaps.md`:**

Its debt component is worth 10 points and no caller has ever supplied either input — no column exists for either. Every score is effectively **out of 90**, compared against thresholds written for 100.

**Four** different thresholds are read off this one column: 70 here, 70 and 40 in the scorer's own track selection, 75 and 55 on the client detail card, 75 to start Round 2. A client scoring 72 clears this engine's readiness floor and cannot start Round 2 according to the button that would act on it.

## 7. WHAT FAILURE LOOKS LIKE

| Response | Where | Meaning |
|---|---|---|
| 200 | all three | Ran. Read the body |
| 400 `INVALID_PARAMS` | check | Tenant context missing — not a missing business id, which cannot happen |
| 400 `AUTH_REQUIRED` | eligible | The same condition, a different code |
| 404 `BUSINESS_NOT_FOUND` | check | No such business in this tenant |
| 500 | one code each | `RESTACK_CHECK_FAILED` / `RESTACK_SCAN_FAILED` / `RESTACK_FETCH_FAILED` |

**The 404 is new behaviour and the old behaviour was worse.** Until 1 September a missing business returned **200** with `eligible: false`, `businessName: 'Unknown'`, `reasons: ['Business not found']` and `recommendedRoundNumber: 1` — a complete-looking verdict, including a round recommendation, about a client that did not exist. An agent that learned that shape must unlearn it. A 404 here is not a refusal; it is an absence of subject.

**One condition has three answers.** A missing tenant context is 400 `INVALID_PARAMS` on check, 400 `AUTH_REQUIRED` on eligible, and **500 `RESTACK_FETCH_FAILED`** on the dashboard, where it throws a plain error into the catch-all. An agent must not read the dashboard's 500 as an outage without checking.

The dashboard's 500 is reachable for the first time. A failed query used to answer `success: true`, `opportunities: []` and a pipeline value of zero, with a fresh timestamp saying the answer was current. An outage was indistinguishable from a tenant with nobody ready.

An empty `opportunities` array now means what it says.

## 8. RETRY VS ESCALATE

**Retry freely.** All three are pure reads.

This does not extend to the document. `restack_opportunity_summary` in `document-gen` calls the same engine and produces a client-facing letter. That is a different blast radius and is not part of this grant.

## 9. NEVER

**Never generalise "null blocks."** Two of the three nulls block and one passes. The rule is shared rule 1, not the null.

**Never report an eligible verdict without its `reasons`.** They are present on both verdicts and they are the basis.

**Never report a count from `eligible` without `notAssessedCount`.** Shared rule 7. An unassessed client is invisible in that scan by construction.

**Never report a readiness score as a recovery assessment.** §6.

**Never report `readinessScore: null` as a low score, a zero, or a weak profile.** It means nobody has assessed this client — most often because nobody has pulled their credit.

Until 2 September the engine said "Readiness score 53 is below threshold of 70" about exactly those clients — an assessment stated as fact, in the prose an advisor reads, about somebody nobody had assessed. That sentence cannot occur now and an agent must not reconstruct it.

**Never quote a pipeline figure.** None exists. If a caller asks for one, say that nothing in this system forecasts approval amounts.

**Never justify an opportunity from the dashboard surface.** It carries no basis. Call `check/:businessId`.

**Never treat a 404 as a refusal.** There is no client to refuse.

## 10. WHICH LAWS THIS TOUCHES

`compliance/client-interest-standard-v1` — the UDAAP entry. This module answers *can this client raise more capital*, and that entry is explicit that it is not the same question as *should they*. An eligible verdict is not a recommendation to place. Recommended scope is distinct from eligible scope, and this module reports the second.

`compliance/bureau-report-handling-v1` — `currentUtilization` is read straight from a credit profile and `readinessScore` embeds a credit band. Both are bureau-derived, and the entry governs what may be done with them.

`compliance/fair-treatment-in-routing-v1` — a re-stack verdict routes a client toward or away from further capital. The disparate-impact discipline applies to what this module returns and to what is done with it.

**Note — no permission gate.** Neither router carries a permission check beyond authentication. Any authenticated user in the tenant — including `readonly` and `client` — receives `currentUtilization` and `readinessScore`. Those are the two roles `business:read:credit` was deliberately withheld from on 2 September. This is not the same data as `/credit/*`, but it is derived from it.

## PROVENANCE

**Corrected in 1.1, from a fact-check against `f20a81b`:** the dashboard does carry the readiness score; unassessed clients were never scored zero — the score was 53 and the sentence said so; the three counts do not partition; the 400 on check is a missing tenant context, not a missing id; four thresholds, not three; `lastCompletedRoundAt` is ambiguous.

**From the code, read on 2 September 2026:** the three surfaces and their mounts, `reasons` on both verdicts, the three-state fields and which block, the scan counts and the `>=` null exclusion, every failure code, the absence of a permission gate.

**Decided by the founder, 1–2 September 2026 and recorded in `docs/decisions/restack-recommend.md`:** one rule set with the engine as the single copy; the forecast deleted with nothing replacing it; missing data blocks rather than skips; a count travels with its denominator; a missing business throws; the score used as a declared fundability floor.

## OPEN

**No permission gate.** `readonly` and `client` reach bureau-derived figures here that they were deliberately denied on `/credit/*`. A policy decision.

**`restack_opportunity_summary` is on the wrong module.** It calls this engine and produces a client-facing document — a different blast radius from three reads, and by the module-id rules it belongs elsewhere.

**Four thresholds, one column, no shared definition.** 70 here, 70 and 40 in the scorer's track selection, 75 and 55 on the client detail card, 75 to start Round 2 — and a client scoring 72 clears this engine's readiness floor and is blocked at the button that acts on it. Recorded in `docs/gaps.md` §3n.

**The score is out of 90.** Its debt component is unearnable and no data source exists. Recorded, not fixed — `docs/gaps.md` §3m.

## CLOSED SINCE THIS VERSION WAS DRAFTED

**A fifth writer, in a migration script — FIXED in CapitalForge `f77e3fb`, after `f20a81b`.**

`scripts/migrate-data.ts` wrote `fundingReadinessScore ?? 0` into the migrated payload, and the import wrote that zero to the column, so a migrated business with no score landed as a score of zero — the state this module tells agents cannot exist. It now carries an absent score through as null; a *genuine* zero is still preserved as zero.

Retained here rather than deleted because the defect is reachable in any database migrated before `f77e3fb`. An agent encountering `readinessScore: 0` on a client with no credit profile should treat the number as suspect rather than as an assessment, and say so.

## APPENDIX A — §3 ADDED AT 1.2, §2 AT 1.3, 3 September 2026

**Why.** This manual's §3 was WHAT COMES BACK — the response, not the request. The
curriculum's `inputs` field would have been written from the route code, which is
the exception the manual-is-the-source principle cannot afford.

**The finding it makes visible.** Two of the three endpoints take no parameters at
all. That is easy to write as an empty row and easy to read as an omission, and it
is neither: an agent cannot narrow, filter or scope `eligible` or
`restack-opportunities`, and a caller wanting a subset filters the answer rather
than the request.

**Nothing here is new.** Sections renumbered: the old §§3–8 are now §§4–9. The two
`docs/gaps.md` references (§3m, §3n) point into another document and were left
alone.

**Added at 1.3.** The no-parameters fact is now in §2 as well as §3. It is a
capability limit, and §2 is where an agent looks for those — §3 says what the inputs
mean, which is not the same as saying there are none to give.

**Added at 1.4 — §5 THE CORRECT SEQUENCE.** This manual had no sequence section; its
§5 was the readiness-score explanation, which is context rather than steps. It was
the seventh of seven manuals to need this before authoring, and the template in
`foi-shared-rules.md` now says what the section is for so an eighth does not.

Nothing here is new. Every step is lifted from §§2, 4, 5 and 9. Sections
renumbered: the old §§5–9 are now §§6–10.
