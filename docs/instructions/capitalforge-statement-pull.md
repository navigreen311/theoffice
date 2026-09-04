# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `statement_pull`
**Endpoints:** 5 GETs across `/api/businesses/:id/statements` and `/api/statements`
**Version:** 1.2 — drafted 4 September 2026, against CapitalForge `master`
**Status:** draft, pending Compliance Review Board
**Not yet a curriculum.** This manual cannot be authored into `forge_operating_instruction` until the CapitalForge adapter dispatches `statement_pull` — see the appendix.

Read `foi-shared-rules.md` first. Rules 1, 1a, 2 and 3 govern most of what this module returns and are not repeated here.

**First manual written against the corrected template** — see the appendix, which records what held and what did not.

## 1. WHAT IT DOES

Reads card statements already on file for a client, and the anomalies detected in them.

Five separate calls, one module:

| Endpoint | Returns |
|---|---|
| `GET /api/businesses/:id/statements` | Statements for one business |
| `GET /api/statements?client_id=` | The same records, addressed by query rather than by path |
| `GET /api/statements/:statementId` | One statement, with its normalised data |
| `GET /api/businesses/:id/statements/anomalies` | Anomaly reports for a business, filterable by severity |
| `GET /api/statements/:id/line-items` | What the record holds for one statement |

They share a blast radius: all read, none write, none contact anyone.

**The name is the boundary.** `statement_pull` is the reads. The same router carries `POST /businesses/:id/statements` (ingest), `POST .../reconcile`, `POST /statements/parse-email` and `POST /statements/disputes`. **None of those is in this module** and a `statement_pull` grant reaches none of them. Two more — `statement_anomaly_dismiss` and `statement_anomaly_step` — are in `forge_module_exclusion` and may never be granted at all; both answer 501.

**"Pull" does not mean fetch from an issuer.** Nothing here contacts a card issuer or a bank. Every statement was put on file by an ingest that happened earlier, and this module reads what that ingest left.

## 2. WHAT IT DOES NOT DO

It does not write. No row changes, nothing is sent, nothing is recorded by the module itself.

**A brokered call is the exception and it is not this module's doing.** A call arriving through The Office writes one `ledger_events` row per call — `office.module.called`, keyed by the trace id The Office also records — whatever the module does, reads included. That is an access record about the brokered call, not a business event about the client.

**It does not retrieve a statement from anywhere.** It reads `statement_records`. A statement that was never ingested is not late, missing or unavailable — it is absent from the records, and shared rule 1 governs what may be said about that.

**It does not parse a statement into transactions.** `/line-items` answers with what the record holds, and the record holds `normalizedData` as imported. **No transaction table exists and nothing parses a statement into one.** Until 2 September 2026 this returned five invented transactions — Office Depot $347.89, Delta Air Lines $1,245.00, AWS $2,890.42 — a payment, two fees and a reconciliation difference of $11.59 with "possible causes", identical for every statement id **including ids that do not exist**. An advisor reconciling against that was reconciling against fiction.

**It does not check that you may read these statements.** No permission guard runs on any of the eleven routes on this router — no `requirePermission` of any kind. Three of the five reads are scoped only by a tenant filter inside the service query.

Role is not consulted anywhere. Tenancy holds and these are reads, so the stakes are lower than on `submit_application`, where the same absence sits on a route that moves money — but an agent looking for what stops it should find the answer here rather than infer a guard from the fact that the other reads have one.

**It does not reconcile.** `reconciledAt` and its state are read here and set elsewhere.

## 3. WHAT EACH INPUT MEANS

| Input | Meaning |
|---|---|
| `:id` (path, business-scoped reads) | The business. Behind the mount guard — guaranteed to exist and be the caller's by the time a handler runs |
| `client_id` (query, `/api/statements`) | The same business, addressed differently. **Required** — its absence is `400 MISSING_PARAM`, not an unfiltered list |
| `:statementId` / `:id` (path, statement-scoped reads) | One statement. **Not** behind the mount guard; scoped by tenant inside the query |
| `severity` (query, anomalies) | Optional filter: `low`, `medium`, `high`, `critical`. **An unrecognised value falls back to no filter** rather than being refused — the response's `severityFilter` reports which was applied. See §6 |
| tenant | **Not caller-supplied.** Read from the token, and it is the only thing scoping three of the five reads |

**Two of the five reads are behind the mount guard and three are not.** `/api/businesses/:id/...` sits under `requireOwnedBusiness('id')`, installed in `api/routes/index.ts` before this router mounts. `/api/statements/...` does not — those are scoped only by the `tenantId` the service passes into its own query. The scoping is real in both cases; **the mechanism is different, and only one of them refuses before a handler runs.**

**`client_id` is required and its absence is refused.** That is deliberate: a statement list with no client named would be every statement in the tenant.

## 4. THE CORRECT SEQUENCE

The five calls have no ordering requirement between them and no state to carry. Three steps surround a read, and each one is worse done later than earlier:

1. **Pick the endpoint that carries what you need, before reading anything.** `/statements` and `/businesses/:id/statements` return the same records by different addresses; the anomaly report and `/line-items` return different things, and `/line-items` returns less than its name suggests. Choosing after reading means reading twice and reporting from whichever came back first.
2. **Compare `severityFilter` in the answer to the severity you sent, before reporting the count.** An unrecognised value falls back to no filter, so an unfiltered total comes back to a caller who asked for critical ones. The response reports the filter it applied; this step is reading it. Before the number is reported, because afterwards the count has already been attributed to the wrong question.
3. **Where the read is gathering context rather than answering a question, apply shared rule 1 to everything it returned — including what it did not find.** Last, because it applies to the whole result and cannot be done until there is one.

**Three, and no more.** The prohibitions that govern what may be said about statements are in §8, and they are not steps: a rule that applies whenever a shape comes back is not a rule about when to do something.

## 5. WHAT COMES BACK

**Statement lists** carry the records and a `total`. The two list endpoints read the same table by different addresses.

**`/line-items`** carries `normalizedData` as imported, `feesCharged` and `interestCharged`. **Not transactions, payments or a reconciliation difference** — those do not exist anywhere in this system.

**`feesCharged` and `interestCharged` are nullable and the null is not zero.** Null means the ingest did not record that figure. Reporting it as zero states that no fee was charged, which is a claim about the client's account that nothing here supports.

**The anomaly report** carries per-statement reports, a `statementCount`, a summed `totalAnomalies`, and **`severityFilter` — the filter actually applied, or `null` for none.** That last field is the one that makes the count interpretable; a total without it is a number with no question attached.

## 6. WHAT FAILURE LOOKS LIKE

| Response | Meaning |
|---|---|
| `200` | The read ran. Check the body before reporting it as a result |
| `400 MISSING_PARAM` | `client_id` was not supplied to `/api/statements` |
| `404 NOT_FOUND` | No such business, or no such statement, or not this tenant's |
| `500 INTERNAL_ERROR` | The read failed |

**A 404 does not distinguish "does not exist" from "not yours."** `BusinessNotFoundError` and `StatementNotFoundError` both map to it, and a statement belonging to another tenant is simply not found by a tenant-scoped query. Read it as **not a record you can reach** and report exactly that.

### An unrecognised `severity` is ignored — and the response says so

**The handler checks the value against four names and falls back to no filter.** So `severity=hgih` returns an unfiltered anomaly count to a caller who asked for critical ones.

**But the answer carries `severityFilter`, and it is the filter that was actually applied.** `severityFilter: null` on a response to a request that named a severity is the fallback, visible in the body:

```
{"reports":[], "statementCount":0, "totalAnomalies":0, "severityFilter":null}
```

So this is a **silent fallback with a visible answer**, not an undetectable one. The same shape as an empty result carrying a basis: the information is there and has to be read.

**Compare `severityFilter` to the value you sent before reporting any count.** If they disagree, the count is over everything.

The count itself is real — a real count of all anomalies — which is why it does not look wrong. What makes it wrong is the question it answers, and `severityFilter` is what tells you which question that was.

**`tenantId()` falls back to the string `'unknown'`** when `req.tenant` is absent. Every route on this router is behind the API authentication gate, so that fallback should be unreachable; if it is ever reached the queries scope to a tenant that does not exist and the answer is an empty list rather than an error. **An empty list from a caller with no tenant context is indistinguishable from a client with no statements.**

## 7. RETRY VS ESCALATE

**Retry freely.** All five are pure reads. Nothing is written, nothing is sent, and a retry after a timeout costs nothing and duplicates nothing.

This is a property of these five, not of the router. It does not extend to ingest, reconcile or dispute — each of those writes once per call, and `reconcile` refuses a second attempt with `409 ALREADY_RECONCILED`.

## 8. NEVER

**Never report an empty statement list as a fact about the client.** It means nobody ingested a statement. Shared rule 1.

**Never present `/line-items` as a transaction breakdown.** It is what was imported. No transaction table exists and nothing parses one.

**Never report `feesCharged: null` or `interestCharged: null` as zero.** Null is not recorded; zero is a claim about the account.

**Never report an anomaly count without the `severityFilter` the answer carries**, and never assume the filter you sent is the filter that was applied. An unrecognised value falls back to no filter and `severityFilter` says so.

**Never treat a 404 as "this statement does not exist."** It also means another tenant's.

**Never infer that a statement is late, missing or overdue from its absence here.** Nothing in this module knows an issuer's billing cycle.

**Never present a statement as verified.** It is what an ingest recorded. Nothing re-reads it from an issuer, and `normalizedData` is as imported.

## 9. WHICH LAWS THIS TOUCHES

`compliance/consumer-privacy-rights-v1` — statement records are personal data about a person's business account, subject to access and deletion requests.

`compliance/fair-treatment-in-routing-v1` — where a statement read feeds a routing or recommendation decision, everything that entry says about inputs applies to what this module returns, including to absences.

**No bureau entry applies.** A card statement is not a bureau report. `compliance/bureau-report-handling-v1` governs `client_read_credit` and `restack_recommend`, not this module — nothing here is bureau-derived.

## PROVENANCE

**From the code, read at `master` on 4 September 2026:** the five read endpoints and their two mount points, the absence of any permission guard on the router, the `tenantId()` fallback, the `MISSING_PARAM` refusal on `client_id`, the silent severity fallback, the nullable fee fields, and the `/line-items` comment recording what it used to return.

**Not yet decided:** whether `statement_pull` should be split the way `client_read` was. The anomaly report is a different act from reading a statement, and the argument for one grant is that both are reads over the same table with the same blast radius. Raised, not answered.

## APPENDIX A — WRITTEN AGAINST THE CORRECTED TEMPLATE, 4 September 2026

This is the first manual written after the two-line template fix, and it was drafted
to find out whether the fix worked. Half of it did.

**`inputs` held.** Five entries, every one a parameter a caller supplies or an
explicit not-caller-supplied, and no response field leaked in. The line — *the
parameters a caller supplies and what each means, not what comes back* — did the
work it was written for.

**`correct_sequence` drifted, and not back into the old failure.** The first draft
had five steps. Only the first was genuinely ordered; the rest were interpretive
rules that apply whenever a shape comes back, in any order. **Three of the five were
this manual's own §8 nevers restated as imperatives** — "read an empty list as a
fact about the records" against "never report an empty statement list as a fact
about the client", and two more of the same shape.

So the fix stopped the old failure — no manual now opens with "there is none" — and
did not stop a new one. It changed which wrong content the section attracted. For a
module of unordered pure reads there is very little genuine sequence, and
`never_do` material is the nearest thing to hand.

**The template gained three lines rather than one, and this section was rewritten to
three steps under them:**

- a step belongs only if doing it later would be worse than doing it earlier
- a module with two real steps gets two — a thin section is a fact about the module,
  not a gap to fill
- if a step is a `never` in different words it belongs in `never_do` only

Recorded here rather than only in the template, because the next author will read a
manual before reading a guidance document, and this one shows the failure it is
warning about.

## APPENDIX B — WHY THIS MANUAL IS NOT YET A CURRICULUM

**4 September 2026.** Authoring was attempted and refused:

```
insert or update on table "forge_operating_instruction" violates foreign key
constraint "forge_operating_instruction_forge_id_module_id_fkey"
DETAIL:  Key (forge_id, module_id)=(capitalforge, statement_pull) is not present
         in table "forge_module_registry".
```

**That is the constraint working, and the ordering it enforces is worth stating.**

    adapter binds it  →  `_modules` reports it  →  a registry row exists
                      →  an instruction can be authored

`statement_pull` is not bound in the CapitalForge adapter. The routes exist and are
real — five reads, described above, read from the code — but nothing dispatches
them under that name, so there is no registry row and a curriculum cannot point at
one.

**The workaround is the thing the Pack decision forbids.** Writing a registry row by
hand to satisfy the foreign key would register a name with nothing behind it, which
is exactly what `docs/decisions.md` entry 4 removed `lender_match` and
`build_packet` for. The constraint is stopping the same mistake one layer down.

**So the manual is complete and the curriculum waits on a binding.** That is a
CapitalForge change — an entry in the adapter's dispatch map, and the operations
that reach these five routes — and it is not made here.

**Nine of the ten CapitalForge manuals are curricula. This one and
`portfolio_health` are not, and both wait on the same thing.** V11 will keep naming
them until they are bound, which is V11 reporting the true state rather than a gap
in the manuals.

## APPENDIX C — CORRECTED AT 1.2, 4 September 2026

**§6 overstated the severity defect, and the correction matters more than the
defect.**

1.1 said an unrecognised `severity` returns an unfiltered count with *"nothing in
the response saying the filter did nothing"*, that *"nothing downstream can tell the
difference"*, and that the response *"does not carry the filter it applied."*

**All three are false.** The response carries `severityFilter`, set to the filter
actually applied or `null` for none. A caller who sends `hgih` gets
`severityFilter: null` and can tell immediately.

Found by calling the endpoint while binding the module — the answer had the field
in it.

**The defect is real and smaller than described:** a silent fallback whose answer is
visible if one field is read. That is the same shape as an empty result carrying a
basis, and this manual set has a rule for it already — read the basis. It is not the
undetectable trap 1.1 made it.

**This was written into a manual whose whole subject is claims that overstate what a
system does**, by an author who spent the preceding week cataloguing exactly that
error in other manuals. Recorded rather than quietly fixed, because a correction
that removes the evidence of the mistake teaches nothing.
