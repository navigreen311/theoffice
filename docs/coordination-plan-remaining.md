# Coordination Plan — Remaining Work, 11 September 2026

**Run 2.** Thirteen packages (P-00 coordinator + twelve), four repositories, peak concurrency nine.

Run 1's plan is `docs/coordination-plan-gate45.md`. This one supersedes nothing in it; it covers
what remained after Gate 4.5's wave landed.

---

## Part 0 — Package count, and what reading the repo changed

### Thirteen packages, not thirty

Sixteen discrete tasks. Two are decisions rather than builds, one is an operator action, one is
already done and needs only verification. Twelve are buildable.

**Forcing thirty would mean splitting one file four ways.** The real concentration is
`adapters/funnelforge/templates.py` — four separate findings land in it — and the whole point of
this plan is that it is owned by exactly one package.

**Peak true concurrency is nine.** Everything else is blocked by a dependency or a ruling.

### Four findings were assigned to the wrong repository, and reading the source is what caught it

The remaining-work document describes the FunnelForge findings from the outside. Read against the
source, four of them are not in FunnelForge at all.

| Finding | Stated | Actually |
|---|---|---|
| D-5 — `sent` / `booked` / `captured` are literals | FunnelForge | **theoffice** `adapters/funnelforge/modules.py:143,185,215` |
| D-2 — `scheduling_confirmation` promises contents | FunnelForge | **theoffice** `adapters/funnelforge/templates.py` |
| D-3 — no template carries an unsubscribe link | FunnelForge | **theoffice** `adapters/funnelforge/templates.py` |
| D-1 / D-6 — "reply" and "attached" in the copy | FunnelForge | **split** — the promise is theoffice's copy, the carrier is FunnelForge's transport |

**The approved copy is The Office's; the transport is FunnelForge's.** `APPROVED_TEMPLATES` lives
in `adapters/funnelforge/templates.py` and is imported by `modules.py` and `gate.py`. Four
`attached` and three `reply` mentions are in that file. A plan that sent four agents into
FunnelForge to edit copy that is not there would have produced four empty PRs and one collision.

### And a fifth correction, smaller but it changes what a ruling costs

D-1 and D-6 say there is *"no attachment field in the schema, the types, or any provider call."*
**That is not true of the provider layer.** `apps/api/src/services/email/multi-provider.ts` carries
both — `EmailMessage.replyTo` and `EmailMessage.attachments`, mapped by all four providers
(Resend `reply_to`/`attachments`, SendGrid, Mailgun `h:Reply-To`/`attachment`, Postmark `ReplyTo`).

What is missing is one layer up: `sendEmailSchema` in `apps/api/src/modules/emails/routes.ts`
accepts `to, from, subject, html, text, preheader, tags, leadId` and **neither field**, and the
handler does not pass them on.

**So carrying an attachment is plumbing through two layers, not building support.** That is the
cost Ivan asked for before ruling on GAP-2, and it is materially cheaper than the finding implies.

### Repo facts that would have broken five package cards

- **FunnelForge's trunk is `master`, not `main`.** Remote `navigreen311/funnelforge`.
- pnpm + turbo monorepo, `apps/*`, vitest at root.
- Path confirmed: `C:\Users\ivann\Projects\funnelforge`.

---

## Part 1 — Remaining Work Inventory

| ID | Title | Repo | Cx | Depends |
|---|---|---|---|---|
| **T-001** | A0 — the eight probes against a second model | simforge | M | — |
| **T-002** | A1 — the battery gains a caller and a cadence | simforge | L | T-001 |
| **T-003** | B40 — `live_grants` counts every grant ever issued | theoffice | L | — |
| **T-004** | C decision — idempotency key or nothing | **RULED: yes** | — | — |
| **T-005** | C build — the send path gains an idempotency key | funnelforge | L | T-011, T-007t |
| **T-006** | C land — the deferred Pack patch | theoffice | M | T-005 |
| **T-007c** | D-1 copy — three templates say "reply" | theoffice | S | — |
| **T-007t** | D-1 transport — no Reply-To on `/api/emails/send` | funnelforge | M | — |
| **T-008** | D-2 — `scheduling_confirmation` promises contents and an invitation | theoffice | M | — |
| **T-009** | D-3 — no approved template carries an unsubscribe link | theoffice | M | — |
| **T-010** | D-4 — shared rule 10 says the Compliance Library ships empty | theoffice | S | — |
| **T-011** | D-5 — the adapter reports its own execution as the outcome | theoffice | L | — |
| **T-012c** | D-6 copy — four templates promise an attachment | theoffice | M | RULING |
| **T-012t** | D-6 transport — no attachment field on the send route | funnelforge | M | — |
| **T-013** | D-7 — the booking route mails the client, ungated | funnelforge | M | — |
| **T-014** | D-8 — `rate_limited` exception, verify only | funnelforge | S | — |
| **T-015** | E — an unmounted bridge answers 401, not 404 | capitalforge | M | — |
| **T-016** | F — restart The Office API | **OPERATOR ACTION** | S | — |

### Out of scope for packaging

- **T-004** — ruled by Ivan: **yes, the idempotency key.** The alternative stays refused:
  `auto_execute` is the only tier that makes a call, so a softened tier is a module nothing can
  invoke and V31 passes vacuously over a surface that never calls anything.
- **T-016** — a live process, not a build. Note that **port 8090 has two listeners**:
  `0.0.0.0:8090` is a VAF container, `127.0.0.1:8090` is The Office. `docker ps` names the
  wildcard bind only and will tell you 8090 is VAF's — half right.

### Context that binds every package

**SimForge's own `gate_result` certification is a human-issued bootstrap and the row says so
(B4).** Burkham's first certifications will be issued by a system whose own certification was
granted by a person. What retires it is a scenario pack run by a *different* SimForge instance.
**No package may describe a first green verdict as more than this.** Binding on P-02.

### [GAP: …]

- **[GAP-1]** If the second model also fails, the ADR-0051 amendment is **Ivan's to rule on**.
  P-01 surfaces it with the number and does not draft it.
- **[GAP-2]** T-012's shape is a ruling. P-07 surfaces both costs and **stops**. Ivan's lean is
  *remove the promise from the copy* rather than build attachment support; the cost of the
  alternative is now measured — two layers of plumbing, not new capability.
- **[GAP-3]** FunnelForge has no `blocking.md` equivalent. P-00 rules: FunnelForge findings are
  recorded in **theoffice's `docs/blocking.md`**, because that is where the adapter, the copy and
  the manuals already live and where every other FunnelForge finding was recorded.

---

## Part 2 — Shared-File Risk Map

### theoffice — where the real concentration is

| File | Touched by | Strategy |
|---|---|---|
| **`adapters/funnelforge/templates.py`** | T-007c, T-008, T-009, T-012c — **four findings** | **P-07 owns exclusively.** This is the file that would have been split four ways |
| `adapters/funnelforge/modules.py` | T-011 | **P-06 owns exclusively** |
| `docs/blocking.md` | every theoffice package, plus FunnelForge's per GAP-3 | **Numbers allocated at dispatch** (Caveat 18). See P-00 |
| `PARALLEL_BUILD.md` | run record | **Coordinator only** |
| `broker/app.py`, `roster.py`, `ventures.py`, `proposals.py` | T-003 | **P-03 owns exclusively** |
| `docs/instructions/funnelforge-approved-send-rules.md` | T-010 | **P-04 owns exclusively** |
| `packs/burkham-wickmont.draft.yaml` | T-006 | **P-05 owns**, via `land_funnelforge_position.py` only — never hand-applied |
| `adapters/funnelforge/gate.py` | imports `APPROVED_TEMPLATES` | **Stable interface — nobody modifies.** P-07 changes the copy, not the gate |

### funnelforge

| File | Touched by | Strategy |
|---|---|---|
| `apps/api/src/modules/emails/routes.ts` | T-007t, T-012t, T-005 | **P-08 owns the carriers; P-09 adds the key after.** Serialized — same schema and handler |
| `apps/api/src/modules/scheduling/routes.ts` | T-013 | **P-10 owns exclusively.** Different module from P-08 — genuinely parallel |
| `apps/api/src/services/email/multi-provider.ts` | already carries both fields | **Stable interface — nobody modifies.** Plumb to it, do not change it |
| `.env`, `RESEND_API_KEY` | T-011 reports it | **NEVER edited by any package.** Report empty; do not set |

### capitalforge

| File | Touched by | Strategy |
|---|---|---|
| `tenantMiddleware` / the `/api/office/*` mount | T-015 | **P-12 owns exclusively.** Sole package in the repo |
| `.env.example` | states behaviour the code contradicts | **P-12 owns** — decides code, doc, or both, and says which |

### simforge

| File | Touched by | Strategy |
|---|---|---|
| `docs/calibration/first-battery-run-2026-09-10.md` | T-001 | **P-01 appends only.** The two retractions stay |
| `services/cadence/registry.py` | T-002 | **P-02 owns exclusively** |
| `apps/api/src/services/operation/battery.py`, `rubric.py` | ADR-0052's surface | **Stable interface — nobody modifies.** P-02 consumes the outcome shape |

---

## Part 3 — Package Design

| P | Title | Repo | Tasks | Depends | Order |
|---|---|---|---|---|---|
| **P-00** | Allocation, baseline, run record | all | — | — | 1 |
| **P-01** | A0 — the eight probes against Claude 3.5 Sonnet | simforge | T-001 | P-00 | 2 |
| **P-02** | A1 — the battery gains a cadence | simforge | T-002 | P-01 | 11 |
| **P-03** | B40 — `live_grants` asks the revocation table | theoffice | T-003 | P-00 | 9 |
| **P-04** | The Compliance Library is not empty | theoffice | T-010 | P-00 | 6 |
| **P-05** | C land — the deferred Pack patch | theoffice | T-006 | P-09 | 13 |
| **P-06** | The adapter stops reporting its own execution as the outcome | theoffice | T-011 | P-00 | 3 |
| **P-07** | Four promises the approved copy makes | theoffice | T-007c, T-008, T-009, T-012c | P-00 | 8 |
| **P-08** | The send route carries Reply-To and attachments | funnelforge | T-007t, T-012t | P-00 | 5 |
| **P-09** | The send path gains an idempotency key | funnelforge | T-005 | P-06, P-08 | 12 |
| **P-10** | The booking route's ungated client mail | funnelforge | T-013 | P-00 | 4 |
| **P-11** | `rate_limited` exception — verify | funnelforge | T-014 | P-00 | 7 |
| **P-12** | E — an unmounted bridge answers 404 | capitalforge | T-015 | P-00 | 10 |

Full cards are in the dispatch prompts. The binding constraints per package:

- **P-01** — read the calibration doc first; it carries two retracted readings. **Assert every
  probe is non-empty before measuring.** Reach for no attribute with a default. Report the split
  **by class**, not as a mean. Do not schedule anything.
- **P-02** — must not post a certification off a run that observed nothing. ADR-0052 already makes
  the outcome honest; consume it, do not re-solve it.
- **P-03** — rides alone. `covered_grants()` answers per venture; three of six counters aggregate
  across ventures. `_live_grants` in `tests/contract/test_departure_revokes.py` is the shape the
  production queries want.
- **P-05** — the binding hunk lands **first** because **V31 reads `forge_dependencies`** to decide
  which Forges to query. An earlier note claimed the opposite; retracted in three places. Gate 2
  must reach 0 FAIL — if it does not, stop, do not soften a rule.
- **P-06** — merges before P-09 across repos. **You cannot add an idempotency key to a send path
  whose return value lies about whether the send happened** — the key would be correct and the
  thing it protects would still report success over a 500.
- **P-07** — surfaces T-012's two costs and **stops**. Does not choose.
- **P-11** — if it is already complete, close with a no-op PR saying so. A package that correctly
  delivers nothing is a success.

---

## Part 4 — Dependency Graph & Merge Order

```
                                P-00
                                  │
   ┌──────┬──────┬──────┬─────────┼──────┬──────┬──────┬──────┐
   │      │      │      │         │      │      │      │      │
 P-01   P-03   P-04   P-06      P-07   P-08   P-10   P-11   P-12
 (A0)   (B40)  (rule) (adapter) (copy) (carr) (book) (verif)(capf)
   │                    │         │      │
   ▼                    └────┬────┘      │
 P-02                        │           │
(cadence)                    └─────┬─────┘
   │                               ▼
   ▼                             P-09
certification                (idempotency)
   │                               │
   ▼                               ▼
Gate 4.5 clears                  P-05
                            (the Pack patch)
```

**Two chains, and they are not equally important.**

- **The certification critical path is `P-01 → P-02`** — two packages, and everything the
  remaining-work document calls blocking runs through it.
- **The longest chain is `P-06/P-08 → P-09 → P-05`** — and it **gates nothing**. Long because
  findings converge, not because it matters.

**Start immediately, zero waiting — nine:** P-01, P-03, P-04, P-06, P-07, P-08, P-10, P-11, P-12.

---

## Part 5 — Coordinator Package (P-00)

**Ledger allocation** — `docs/blocking.md` is written by every package and "zero file overlap" is
never achievable for it. Two packages both claimed B38 on 10 September.

| Package | Allocation |
|---|---|
| P-03 | amends **B40** — no new number |
| P-04 | **B41** |
| P-06 | **B42** |
| P-07 | **B43** |
| P-08 | **B44** |
| P-09 | **B45** |
| P-10 | **B46** |
| P-11 | **B47** (no-op if verification passes) |
| P-12 | **B48** |
| P-05 | **B49** |
| P-01 | simforge **ADR-0053** (reserved) |
| P-02 | simforge **ADR-0054** (reserved) |

**GAP-3 ruled:** FunnelForge findings are recorded in theoffice's `docs/blocking.md`. That is where
the adapter, the copy and the manuals live, and where every prior FunnelForge finding was recorded.

**Smoke baseline** — the recorded normalised hash is `50f95788f3f35a37256f9fe30383378164a98708c98d2acc475fc94ba0f33f80`,
over the documented eight failures and one could-not-run. The normalisation recipe: extract the
`console-smoke.sh` step, strip the leading timestamp column, drop Chromium stderr and DevTools
lines, mask 8-hex ids and the issued-token prefix.

---

## Part 6 — Per-Package Prompt Template

The paste-ready template is `docs/coordination-plan-remaining-template.md`.

---

## Part 7 — Merge, Test & Push Protocol

**One coordinator. Never parallel merges into main. Ever.**

1. Pull latest trunk for that repo — **`main` for theoffice/simforge/capitalforge, `master` for
   funnelforge.**
2. **Verify checks by content, not by count.** Capture Smoke, prove the capture non-empty,
   normalise, diff against the recorded baseline. A PR with the same number of red checks but
   different text is **rejected**. Five PRs on 10 September had identical red counts; one had a
   ninth failure it introduced itself, and only the text diff caught it.
3. Squash-merge. Run the full suite.
4. Green → push → append to `PARALLEL_BUILD.md` → next.
5. Red → revert, hand back with the failing output, move to the next non-blocking PR.
6. **Re-check dependents' mergeability after each merge.** A stale `UNKNOWN` is not a `MERGEABLE`.

**Attribution discipline.** Before reporting a failure as a package's fault, establish that it is.
The suites run against a shared Postgres and leftover state has produced that misattribution more
than once. A test that passes in isolation proves nothing about a full-suite failure, and a
baseline taken *after* a failing run compares two database states as much as two code states.

**Halt and escalate to Ivan:**
- a critical-path package (P-01, P-02) fails twice — halt the entire run
- P-05 cannot reach Gate 2 = 0 FAIL
- any package proposes weakening V11, V22, V31, V32 or V33
- two packages claim the same ledger number — allocation failed, re-dispatch rather than renumber

Every merge appends: package ID · PR link · merge SHA · test results with exit codes · Smoke
verdict (baseline-identical / divergent-with-diff) · timestamp.
