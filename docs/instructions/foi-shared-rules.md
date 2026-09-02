# FORGE OPERATING INSTRUCTIONS — SHARED RULES

Every module manual references this. Nothing here is module-specific.

Written 2 September 2026. These rules exist because the same defect kept appearing in different modules, and restating them per manual is how they drift.

## 1. AN ABSENCE IS A FACT ABOUT THE RECORDS, NOT ABOUT THE WORLD

No authorisation on file. No credit profile. No owners recorded. No recommendations. None of these is a fact about the client.

An agent that reads no ACH authorisation and concludes *this client has not authorised ACH* has converted a gap in the records into a claim about the world.

This matters most when a read is gathering context for another action rather than answering a question. Answering is bounded — fetch, report, stop. Context becomes an input to a decision, and an absence entering a decision as a negative fact is how a missing record turns into a conclusion nobody reached.

Never act on an absence. Report it and let a human decide what it means.

### 1a. A REFUSAL IS NOT AN ABSENCE

A 403 says nothing about whether the data exists. It is a fact about the agent, not about the records and not about the world.

An agent that receives a 403 on a credit endpoint and reports "no credit profile on record" has manufactured a finding out of its own lack of permission — and it is a finding about somebody's creditworthiness.

Report the refusal as a refusal: "this grant does not reach the client's credit file." Then stop, or ask for the grant. Never substitute an answer.

The same holds for a timeout, a 500, and an unreachable service. None of them is evidence about the subject.

### 1b. NEVER INFER WHAT YOU CANNOT READ

Where a decision needs data this grant does not reach, say so. Do not reason toward it from what is visible.

A module split into narrower grants creates this failure mode by construction: an agent that could once read owners and credit together now holds one and can see the shape of the other's absence. That shape is not information.

## 2. REPORT THE BASIS, NEVER THE EMPTINESS ALONE

Where a result is empty and carries a stated basis, the basis is the answer.

```
[] with basis: 'no_credit_profile_on_record'
```

Report: "No credit recommendations — no credit profile on record for this client."

Not: "No recommendations."

The difference is what an advisor does next. *No recommendations* invites "so they're not eligible for anything." *No credit profile on record* invites "let's pull their credit."

## 3. NEVER PARAPHRASE A BASIS INTO A CONCLUSION

`no_credit_profile_on_record` says nothing about the client's credit.

An agent rendering it as "we don't have enough information to recommend anything" has softened a precise statement into a vague one — and vague statements get read as judgements.

Pass the basis through as stated. If it needs explaining, explain it alongside; do not replace it.

## 4. THE STATES THIS APPLIES TO

The same rule governs every one of these, wherever they appear:

| State | Means |
|---|---|
| `no_*_on_record` | nothing was recorded, not that nothing exists |
| `not_assessed` / `unassessable` | nobody has evaluated this |
| `not_yet_measured` | the measurement has not been taken |
| `unresearched_default` | a figure supplied by a person, unverified against the issuer |
| `assumed_default` | a value nobody supplied |
| `unconfigured` | a rule exists with a threshold nobody set |
| `not_applicable` | there was nothing to check, distinct from checking and passing |
| `unverifiable` | it could have been checked and the evidence to check it is absent |
| `CapabilityState: no_data` | the thing works and holds nothing |
| `CapabilityState: not_built` | the thing does not exist |

`not_applicable` and `passed` are different answers. So are `no_data` and `not_built`. An agent must not collapse either pair.

## 5. A SUCCESS RESPONSE MEANS WHAT IT SAYS AND NOTHING MORE

A 201 means a row was written. It does not mean the thing the row describes is valid, that a downstream event fired, or that anything was notified.

A 200 on a computed answer means the computation ran. It does not mean every input was present — check for a declared basis, an unconfigured list, or a count of what could not be evaluated.

Where a module reports what it could not do, that report is part of the answer. Dropping it makes a partial answer look complete.

## 6. WHEN A CALL TIMES OUT

Consult the module manual. There is no general rule, because the right action depends on whether a retry duplicates something a person reads.

Where the manual says escalate, escalate. Do not check-then-retry — between the check and the retry the original write can land.

## 7. WHAT AN AGENT NEVER DOES, IN ANY MODULE

- Never supply a value the module was going to record about a third party. A verdict, an assessment, an attestation, an actor id — if the module records it, the module derives it.
- Never backdate. A timestamp records when something was recorded.
- Never retry a call whose manual does not say it is safe to retry.
- Never report a count without its denominator where one is offered. "3 eligible" and "3 eligible of 40, 12 never assessed" are different answers.
- Never report a refusal, a timeout or an error as a finding about the subject. Rule 1a.
- Never reason toward data this grant does not reach. Rule 1b.
