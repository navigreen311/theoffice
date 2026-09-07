# Issuing banking's 14 identities — prediction, written before the act

**7 September 2026.** Recorded before issuing, so the result can be scored against it. A
wrong prediction is the point of going one department at a time.

Banking chosen because Diagnostic Analyst and Placement Strategist both draw on it, so
there is a real position to appoint into.

## State before

```
office_agent_identity, active            3      (all engineering)
village_agent, banking, active          14
office_agent_identity, banking           0

V29  PASS   3 position(s) name a real department
V30  PASS   3 department(s) have seats for what the Pack asks
```

## The path audit, first — nothing assumes a small number

Asked before issuing, because `sync_roster`'s suspension path has only ever run against
three identities and at fourteen it does real work on the first mortality roll.

| step | shape | at 14 | at 186 |
|---|---|---|---|
| mark departed | `UPDATE village_agent ... WHERE ref = ANY(%s)` | set-based | set-based |
| suspend identities | `UPDATE office_agent_identity ... WHERE ref = ANY(%s)` | set-based | set-based |
| revoke grants | one `revocation.revoke` per departed agent **holding grants**, each computing `blast_radius` | 0 queries — new identities hold no grants | linear, one round-trip each |
| audit subject | `changes` carries every change, uncapped | trivial | already survived a 186-agent import |

**No small-number assumption anywhere.** The revocation loop is linear rather than
constant, which is a cost and not a defect, and it does nothing at all for an agent
holding no grants — which every newly issued identity is.

**One defect found, and it is mine.** `broker/sync_roster.py:272` carries an orphaned
comment — *"An identity whose agent changed department follows it…"* — wrongly indented,
sitting after `_revoke_departed`, describing an UPDATE that was moved above the departure
block during the D3 work. The code it described is intact at line 240; only the comment
was left behind. Syntactically harmless, misleading to read. Not fixed here — it is
unrelated to this act and belongs in its own change.

## Predictions

### 1. V30's banking number — **no change**

**Predicted: V30 still PASS, same message, same numbers.**

V30 reads `depts.seats()`, which resolves to the Village's `/api/org/departments` and
counts roster positions. Issuing an Office identity does not change the Village roster.
Banking stays at 14 seats before and after.

**This is the entry 14 mismatch made visible.** The number that moves is the one V30 does
not read.

### 2. V24 and Gate 4.5 — **the arithmetic moves, and the message may not**

Appointment's `_candidates` selects `FROM office_agent_identity WHERE status = 'active'
AND department = %s`. Banking goes from **0 candidates to 14**.

**Predicted:** Diagnostic Analyst (2) and Placement Strategist (2) stop being unfillable
*for lack of anyone existing* and become unfillable *for lack of certification* — the 14
new identities hold no Unit A or Unit B certification for any CapitalForge module.

So V24 should still report unfilled positions, **for a different reason than before**, and
entry 11 predicts the message will not say which: `CandidateShortfall` carries
`never_certified` per agent and V24's message drops it.

**The scoreable claim:** V24's text before and after will be materially the same while the
cause has changed completely. If the message does distinguish them, entry 11 is wrong and
that is worth knowing.

### 3. V13 / approvals — **no change**

V13 counts approvals from positions and tiers, not from who fills them. Predicted
identical.

### 4. The mortality path — **does nothing**

Predicted: the first departure among the 14 suspends an identity and revokes **zero**
grants, because `_revoke_departed` only acts on agents holding live grants and these hold
none.

The path will run for the first time at 14 rows and do nothing visible. **That is the
prediction most worth being wrong about** — if it does something, the reason matters more
than the outcome.

### 5. Nothing else moves

No grants, no manifest rows, no Pack change, no certifications. An identity is inert; it
makes an agent *appointable* and confers nothing.

## What would falsify the framing

- V30's number changing → `seats()` reads something other than the Village roster, and
  entry 14 is wrong about which population it measures.
- V24 naming certification → entry 11's "the symptom names the wrong cause" is already
  fixed and the record is stale.
- Any grant, manifest row or ledger row appearing → issuance is not inert, and
  `issue_identity`'s docstring is wrong about what it does.

---

# Results — scored 7 September 2026, after issuing

**14 issued, 0 refused.** `office_agent_identity` active 3 → 17, of which 14 banking.
Every issuance wrote an `office_identity_issued` audit entry naming the human.

**Two of four scored predictions were wrong, and they are the reason this document
exists.** A prediction doc that only survives when it was right teaches nothing.

## 1. V30's banking number — no change ✅

`3 department(s) have seats for what the Pack asks`, character-identical before and after.
Fourteen agents became appointable and the rule that reports on seats did not move.

Entry 14 demonstrated rather than argued.

## 2. V24 — ✗ wrong, and wrong in the method

Predicted: V24 would still report unfilled positions, for a changed reason.

Actual: `V24 [NOT_RUN] evaluated at Gate 4.5 against appointment output, which does not
exist at Gate 2.`

**V24 does not run at Gate 2 at all.** It is in `GATE_45_RULES`. I knew that — it is
written into `validator.py`, and I have described it in two earlier records — and I still
framed the prediction against a `validate()` call and read the result as though it had
been evaluated.

**Knowing a fact and testing against it are different acts.** That is the whole of this
miss, and it is what the protocol caught.

Run against the path that actually evaluates it, the substance was right:

```
Deal Underwriter:      need 2, unfilled 2, candidates-with-shortfall 14
                              14 x never_certified
Acquisition Analyst:   need 3, unfilled 3, candidates-with-shortfall 0
Buyer Network Manager: need 2, unfilled 2, candidates-with-shortfall 0

capacity: free=0  allocated=0  produced_not_yet_certified=14
```

Banking moved from *nobody exists* to *fourteen exist, none certified*, and
`produced_not_yet_certified` moved 0 → 14.

## 3. Entry 11's claim — ✗ wrong, and the truth is better

Predicted, on entry 11's authority: the message would not distinguish "nobody exists" from
"nobody is certified".

**It does.** `PositionAppointment.requires_certification` carries **14 ×
`never_certified`** on Deal Underwriter and **0** on the other two positions, and the
escalation reports all three capacity numbers separately.

So an operator reading the artifact can tell the two apart today. Entry 11 said the
information was dropped on the way up; it is not. What flattens is Gate 4.5's **summary
line**. Narrower defect, different fix — a message change rather than a missing signal.

Entry 11 is amended, and the class it belongs to is named there.

## 4. Mortality path — unscored

No departure occurred. The prediction stands untested: a departure among the 14 should
suspend the identity and revoke **zero** grants, because `_revoke_departed` acts only on
agents holding live grants and these hold none.

## 5. "Nothing else moves" — ⚠ unscoreable, and that is a process failure

Predicted no grants, certifications, manifest rows or ledger rows would appear.

Current totals — 6 grants, 7 certifications, 13 manifest rows, 12 ledger rows — are all
consistent with prior work rather than with issuance, and no grant or certification audit
event fired during it.

**But I cannot score it, because I recorded a before-snapshot of only the fields I
expected to move**: identities, banking headcount, V29 and V30. The four tables the
prediction was actually about were never captured.

---

# Two process fixes, adopted for the remaining departments

**1. Capture the full before-snapshot, not the fields you expect to move.**

The point of a baseline is the things that were not supposed to change. A snapshot scoped
to the expected movement can confirm a prediction and can never falsify the part that
matters most — "nothing else happened" — which is exactly the claim that most needs
evidence.

**2. Run each prediction against the path that actually evaluates it.**

V24 is a Gate 4.5 rule. Testing it through a Gate 2 `validate()` call produced a NOT_RUN
that said so plainly, and the prediction was scored against a result that was never a test
of it.

Both fixes apply to operations, administration and marketing.

## What the exercise was worth

Fourteen identities took one call. The prediction took longer and produced three things
the identities did not: a demonstration that V30 does not read the population it appears
to (entry 14, now shown rather than argued), a correction to entry 11 that narrows a
recorded defect from "signal missing" to "summary flattens", and two protocol fixes found
by getting it wrong.

Per-department was the right call. All 186 at once would have moved every number
simultaneously and none of the above would have been attributable.
