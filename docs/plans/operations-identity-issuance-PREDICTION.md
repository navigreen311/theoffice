# Issuing operations' 12 identities — prediction, written before the act

**7 September 2026.** Second department. Written under the two process fixes the banking
round produced: a **full** before-snapshot rather than the fields expected to move, and
every prediction aimed at the path that actually evaluates it.

## Full state before

```
office_agent_identity      17          revocation                  1
village_agent             186          shift_assignment            4
agent_forge_grant           6          proposal                    2
certification               7          incident                   26
venture_forge_manifest     13          audit_log                1340
agent_call_ledger          12

identities by department:  banking 14, engineering 3
village_agent operations, active: 12

Gate 2 validator
  V13  PASS      100 of 360 review-minutes used
  V24  NOT_RUN   evaluated at Gate 4.5 against appointment output
  V29  PASS      3 position(s) name a real department
  V30  PASS      3 department(s) have seats for what the Pack asks

Gate 4.5 path — appointment
  capacity  free=0  allocated=0  produced_uncertified=14
  Acquisition Analyst      need 3  unfilled 3  {}
  Buyer Network Manager    need 2  unfilled 2  {}
  Deal Underwriter         need 2  unfilled 2  {never_certified: 14}
```

Every table is here, including the nine nothing should touch. That is the fix: the claim
needing evidence most is *"nothing else happened"*, and banking's snapshot could not
support it.

## Why operations differs from banking, and what that should show

Banking carried two positions, both needing 2, against 0 candidates. Operations carries
**Intake Concierge (2)** and **Stack Manager (1)** — and Stack Manager needing only **1**
is the reason to predict carefully here.

Greenstone's operations position is **Buyer Network Manager (2)**, which is the one
operations actually feeds in this Pack. Burkham's Intake Concierge and Stack Manager are
in a Pack that is **not published** — Burkham exists only as draft YAML, absent from
`business_pack`. So the Gate 4.5 numbers below move only for Greenstone.

**Stated because it is the trap in this round:** the reason for choosing operations —
a position needing only 1 — belongs to a Pack no gate will evaluate. Predicting Burkham's
arithmetic would be predicting about something nothing runs.

## Predictions

### 1. Buyer Network Manager gains 12 candidates, all uncertified — **and stays unfilled**

**Predicted:** `Buyer Network Manager  need 2  unfilled 2  {never_certified: 12}`.

Its `source_department` is `operations`; `_candidates` will now return 12. None holds Unit
A on `buyer_match`, `assign_contract`, `place_call` or `transcribe_call`, nor Unit B on
operations. `unfilled` stays **2**.

The observable change is `{}` → `{never_certified: 12}` — the position moving from *nobody
exists* to *twelve exist, none certified*, which is precisely what banking's Deal
Underwriter did.

### 2. `produced_not_yet_certified` — **14 → 26**

Predicted: it counts identities that exist and are uncertified across the venture, so it
gains all 12. **This is the number to watch**: if it moves by anything other than 12, the
count is not what the name says.

### 3. Acquisition Analyst — **unchanged, `{}` and unfilled 3**

Its department is `research`, which gains nothing. A prediction that must hold, or
`_candidates` is not filtering by department.

### 4. V30, V29, V13 — **all unchanged**

V30 reads the Village roster: operations stays at 12 seats. V29 checks names, not people.
V13 counts approvals from positions and tiers.

**`100 of 360 review-minutes used`, character-identical**, is the specific claim.

### 5. Nothing else moves — **now scoreable**

Predicted **identical**: `agent_forge_grant 6`, `certification 7`,
`venture_forge_manifest 13`, `agent_call_ledger 12`, `revocation 1`, `shift_assignment 4`,
`proposal 2`, `incident 26`.

`office_agent_identity` 17 → **29**. `audit_log` **1340 → 1352** — one
`office_identity_issued` per agent, and nothing else.

The audit delta is the sharpest test in this round: **exactly 12**. More means issuance
does something beyond issuing.

### 6. The mortality path — still unscored, and still untested

Unchanged from banking: a departure among the 12 should suspend the identity and revoke
zero grants, because `_revoke_departed` acts only on agents holding live grants.

Twenty-six uncertified identities will exist afterwards and none holds a grant, so the
path stays untested until an agent that holds one departs. Worth stating that issuing more
identities does not move this closer to being tested.

## What would falsify the framing

- `produced_not_yet_certified` moving by other than 12 → the counter is not per-identity.
- Acquisition Analyst gaining candidates → `_candidates` is not filtering by department.
- `audit_log` moving by other than 12 → issuance has a side effect not in its docstring.
- Any of the nine untouched tables moving → `issue_identity` is not inert.
- V13 changing → approvals depend on who fills a position, not only on the position.

---

# Results — scored 7 September 2026

**12 issued, 0 refused.** Every prediction correct, including the five that were
unscoreable in the banking round.

```
table                       before  after  delta
  office_agent_identity         17     29    +12   <-- moved
  audit_log                   1340   1352    +12   <-- moved
  village_agent                186    186     +0
  agent_forge_grant              6      6     +0
  certification                  7      7     +0
  venture_forge_manifest        13     13     +0
  agent_call_ledger             12     12     +0
  revocation                     1      1     +0
  shift_assignment               4      4     +0
  proposal                       2      2     +0
  incident                      26     26     +0

V13  PASS   100 of 360 review-minutes used      (character-identical)
V29  PASS   3 position(s) name a real department
V30  PASS   3 department(s) have seats for what the Pack asks

capacity  free=0  allocated=0  produced_uncertified=26     (14 -> 26, exactly +12)
  Acquisition Analyst      need 3  unfilled 3  {}
  Buyer Network Manager    need 2  unfilled 2  {never_certified: 12}
  Deal Underwriter         need 2  unfilled 2  {never_certified: 14}
```

**The process fix earned itself immediately.** Nine tables at delta 0 is the claim
banking's snapshot could not support, and it is now evidence rather than assertion.
`audit_log +12` exactly means issuance did one thing per agent and nothing else.

## What two departments show that one did not

Three positions, three different underlying states, and the appointment artifact
distinguishes all of them:

| position | department | state |
|---|---|---|
| Acquisition Analyst | `research` | nobody exists — `{}` |
| Buyer Network Manager | `operations` | twelve exist, none certified |
| Deal Underwriter | `banking` | fourteen exist, none certified |

The amended entry 11, confirmed a second time and more sharply. Only Gate 4.5's summary
line flattens these into one sentence.
