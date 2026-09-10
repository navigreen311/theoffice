# P-17 — Gate 7 asks the revocation table, not a column nothing writes

**Written before the change. Nothing above the score line is edited afterwards.**

---

## The finding, restated from what I read rather than from the card

`_gate_7` (`broker/provisioning.py:478`) counts a venture's grants with

```sql
FROM agent_forge_grant WHERE venture_id = %s AND revoked_at IS NULL
```

and blocks the run if any of them has `activated_at IS NOT NULL`.

**Verified independently, and the coordinator's claim holds with one correction.**

*Nothing in the broker writes `agent_forge_grant.revoked_at`.* Searched every `.py`,
`.sql`, `.ts`, `.tsx` and `.md` in the tree for `UPDATE agent_forge_grant` (multiline,
so a statement split across string literals cannot hide) and for `SET revoked_at`:

| writer | table |
|---|---|
| `broker/humans.py:346` | `office_human_role` |
| `broker/knowledge.py:131,145` | `playbook_share` |
| `tests/isolation/test_phi_flush.py:248` | `office_agent_identity` |
| `tests/contract/test_call_path.py:108` | **`agent_forge_grant` — a test fixture** |
| `tests/contract/test_module_exclusion.py:104` | **`agent_forge_grant` — a test fixture** |

The only two writers of `agent_forge_grant.revoked_at` in the repository are test
fixtures simulating a revocation the product cannot perform. The single production
`UPDATE agent_forge_grant` is `provisioning.py:1457`, and it sets `activated_at`.
The only trigger on the table is `agent_forge_grant_exclusion_guard` (0030), which its
own migration docstring says is BEFORE INSERT.

**The correction: the column is not empty in the live database, and no code put the
values there.** Measured read-only against `OFFICE_ADMIN_DSN`:

```
 venture_id       | grants | active | revoked_at NOT NULL
 burkham-wickmont |      4 |      4 |                   2
 greenstone       |      2 |      2 |                   0
```

Two `burkham-wickmont` grants carry a `revoked_at` set on 2026-09-03 at 14:24 and
14:45. `audit_log` over that window holds `forge_call_intent`, `office_identity_issued`
and `shift_assigned` — **no revocation event of any kind**, and the `revocation` table
holds exactly one row ever, a `greenstone` venture-scope revocation that was reinstated.

So the column is worse than dead. It is **hand-written out of band**: no reason, no
named human, no audit row, no blast radius — every ritual §1.4 requires, absent — and
`WHERE revoked_at IS NULL` then reports that hand-edit to fourteen read sites in
`broker/` alone as though
it were the authority state of a grant. That is what Gate 7 is currently reading.

I also checked a guess before making it: I assumed the partial index on
`(office_agent_id, forge_id, module_id) WHERE revoked_at IS NULL` was **unique**, which
would have made the column load-bearing for grant re-issue. `pg_indexes` says it is
not. `ix_grant_lookup` and `ix_grant_lookup_active` are both plain indexes. The column
carries no uniqueness duty. (Caveat 14, caught on myself.)

## What the real source is

`broker/revocation.py` — `revocation` rows, four scopes, broadest wins, consulted live,
never cached. `check_revocations` is what the call path asks
(`client/office_client.py:248`), and `_CHECK_SQL` is the one true spelling of the rule.

`blast_radius` already carries a **second** spelling of the same four scopes, with a
comment admitting it and a test binding the two together. I am not adding a third.

## The design

1. Extract the four-scope predicate out of `_CHECK_SQL` into a helper that takes the
   four target expressions as SQL text, so the same string serves both cardinalities:
   `%(agent_id)s` for one call, `g.office_agent_id` for a set of grants.
2. Add **one** new function to `broker/revocation.py`:
   `covered_grants(conn, venture_id) -> dict[grant_id, ActiveRevocation]`, built from
   that helper and ordered by the same breadth ranking, so the reported scope is the
   broadest one — the same answer `check_revocations` would give per grant.
3. `_gate_7` counts grants, subtracts the covered ones from `active`, and reports the
   subtraction in its evidence. The blocking condition is unchanged: any *live* active
   grant still blocks.

No migration. No schema change. No data change.

## Predictions, each falsifiable

**P1.** The three call-site properties hold: an `agent_module`, an `agent`- and a
`venture`-scoped active revocation each stop their grant counting toward Gate 7's
`already_active`, and a `forge`-scoped one would too, by the same predicate.

**P2.** `reinstate()` round-trips: the same grant counts again afterwards, because
`reinstated_at IS NULL` is inside the shared predicate rather than re-typed.

**P3.** **An active, unrevoked grant still BLOCKS.** If this one goes green while P1
goes green, the gate widened and the package failed regardless of the other results.

**P4.** Gate 7 still passes on zero grants, and on grants that exist but are inactive.

**P5.** `test_gate_5_issues_grants_inactive` (`tests/provisioning/test_pipeline.py:428`)
keeps passing unchanged — it asserts `evidence["already_active"] == 0`, and I add keys
rather than rename that one.

**P6.** The golden snapshots are untouched. I checked: all seven are generator
artifacts (`greenstone_*.json`); none contains gate evidence. `already_active` appears
in exactly two files in the tree, both listed above.

**P7.** Test count rises by the number of tests I add and nothing else moves. Baseline
1332, 0 failed.

**P8 — the one I expect to be wrong about.** `docs/provisioning.md:106` quotes the
`is_assignable` definition including `revoked_at IS NULL`, and is **not** on my MAY
MODIFY list. So this package ships with a doc that still describes the column as the
revocation control. I predict that is the only documentation drift the change creates,
and I will name it rather than fix it.

## The ruling I owe on the dead column — stated before I build, so the build cannot
## shape the answer

**Neither "make it a cache" nor "vestigial".** It is a **third thing**, and the third
thing is the reason to keep it and stop reading it:

- It must **not** become a cache of `revocation`. §1.4 and this module's own header
  refuse that in writing: *"a venture-wide revocation must apply to grants issued after
  it was declared. Storing it on the grant would silently miss both."* A trigger that
  stamped `revoked_at` on revoke would be exactly the design that header rejects, and
  it would make Gate 7 look fixed while a venture-scope revocation issued before a
  grant still missed it.
- It is not vestigial either, because **somebody used it**, twice, in production, three
  days into Phase 0. A column with live hand-written values is in use whether or not
  any code writes it.

So: `revoked_at` is a **manual tombstone with no ritual attached**, and its defect is
that fourteen read sites in `broker/` spell it "live grant". The proposal is *narrowing*, not removal:
a follow-up package makes `revocation` the only answer to "is this grant live", audits
the two existing hand-written rows into it, and then — separately, with a migration —
`revoked_at` either gets a NOT-a-revocation comment or goes. **Not in this package.**
`broker/grants.py:221` reads the same column and has the same dead branch; it is the
same finding and it is on my MUST NOT TOUCH list, so it is recorded and left alone.

---

## SCORE — written after, nothing above this line edited

**Eight predictions, seven clean, one improved on. Nothing above this line was edited
after the build except one count, corrected before any code was written: "twelve read
sites" became "fourteen", measured rather than estimated.**

| # | claim | result |
|---|---|---|
| **P1** | three scopes stop a grant counting | **BETTER THAN PREDICTED.** All **four** are tested, not three. `forge` was going to ship asserted-by-construction, which is the shape this project keeps finding defects in, so it got a test: `test_a_forge_scoped_revocation_stops_every_grant_against_that_forge`, and `test_the_broadest_scope_is_the_one_reported` pins the ordering. |
| **P2** | `reinstate()` round-trips | **HELD.** `test_reinstating_a_revocation_makes_the_grant_count_again` — PASSED then BLOCKED, same run, same grants. |
| **P3** | an active unrevoked grant still BLOCKS | **HELD, and measured against the old code rather than argued.** Stashing `provisioning.py` and re-running gives `AssertionError: assert 'blocked' == 'passed'` on the scope tests — the tests fail on the *verdict*, so they are about the defect and not about the three evidence keys I added. Read from the run. |
| **P4** | zero grants and inactive grants still pass | **HELD.** Two tests; the zero-grant one asserts the whole evidence dict, so a key appearing or changing shape is a failure rather than a silence. |
| **P5** | `test_pipeline.py:428` keeps passing untouched | **HELD.** 75 passed in `tests/provisioning/`, that file unmodified. |
| **P6** | golden snapshots untouched | **HELD.** `git status` lists five paths, all on the allowed list; no snapshot among them. |
| **P7** | count rises by exactly the tests added | **HELD, exactly.** 1332 → **1342**, +10, which is the ten tests in the new file. 0 failed. |
| **P8** | `docs/provisioning.md:106` is the only doc drift | **HELD.** The other two Gate 7 mentions — `docs/plans/provisioning-PLAN.md:59` and `docs/plans/unit-a-verdict-ingest-PREDICTION.md:62` — describe the *rule*, which did not move. Named in the B35 closure, not edited. |

**The ruling on `revoked_at` was written before the build and did not change.** It was
also the part of this package that most wanted to be wrong the easy way: a trigger
stamping `revoked_at` on revoke would have made Gate 7 look fixed, passed every test in
the file, and still missed a venture-scope stop declared before a grant — which is the
precise failure `broker/revocation.py`'s header was written to prevent.

**What the build taught that the prediction did not contain.** The `revocation` table has
a foreign key onto `office_agent_identity`, and `wipe_venture` does not reach it — so a
revocation left behind by one test fails the *next* test in a teardown, naming a
constraint instead of a cause. Cost one confused run. The contract suite already clears
the table for the same reason; this file now does too, in an autouse fixture that says
why.
