# FORGE OPERATING INSTRUCTION

**Forge:** CapitalForge
**Module:** `submit_application`
**Endpoint:** `POST /api/applications/:id/submit`
**Trust tier:** `propose`
**Idempotency:** `at_most_once`
**Version:** 1.0 — drafted 3 September 2026, against CapitalForge #88
**Status:** draft, pending Compliance Review Board

> **No `Permission:` line, and that is the finding rather than an omission.**
> `POST /api/applications/:id/submit` carries `tenantMiddleware` and nothing else —
> no `requirePermission`. The permission that names this act, `application:submit`,
> is checked in a different file on a different route: `application.routes.ts:115`
> guards `POST /businesses/:id/applications`, which **creates**. Its own refusal
> message says "permission to create applications".
>
> So the permission named for submitting gates creating, and submitting is gated by
> the six-on-paper/five-enforced ladder in §3 and by tenancy — not by role. Any
> authenticated member of the tenant who satisfies the gates can submit, `readonly`
> and `client` included.
>
> This is recorded, not fixed. See the appendix.

Read foi-shared-rules.md first. Rules 1, 5, 6 and 7 govern most of this.

Decisions are recorded in capitalforge/docs/decisions/submit-application.md. Suitability facts belong to suitability_check and are cited, not restated.

## 1. WHAT IT DOES

Submits a prepared application to a lender, after five gates.

Submission is a second act, and the API refuses to collapse it into creation. Creating an application already submitted is 422 SUBMIT_IS_A_SEPARATE_ACT.

That is not tidiness. The controls are keyed to an application that exists — a signed acknowledgment against it, a per-application consentCapturedAt, a maker recorded on it. The create path knew it could not have captured per-application consent — it set consentCapturedAt: null under a comment saying so, and submitted anyway. Gating it would have run the consent check against a record whose consent cannot yet exist.

PUT /api/applications/:id/status is the same chain by a different name.

## 2. WHAT IT DOES NOT DO

No agent presses this button. Preparation is Level 1; submission is Level 3. The middleware refuses a Level 1 agent's attempt to submit directly, and maker_checker is the gate that enforces it — see §3.

It does not prepare the application. Everything on the form arrived before this call, under compliance/application-truthfulness-v1.

It does not decide approval. The status machine continues to approved/declined and nothing here touches that.

## 3. THE GATES — SIX ON PAPER, FIVE ENFORCED

All five run concurrently and every one is tenant-scoped in the query, not by an argument about who calls it. A gate that passes on another business's record is a wrong decision rather than a disclosure.

Gate    Checks
product_reality    A signed acknowledgment exists
consent_captured    Per-application consent, via consentCapturedAt
suitability    noGoTriggered && !overriddenBy
kyb_kyc_verified    Verification on record
maker_checker    The approver is not the maker

maker_checker is the control Burkham's compliance library leans on. compliance/application-truthfulness-v1 says no agent submits — an agent prepares, a human presses the button — and this gate is the mechanism. It requires an approvedByUserId naming a real second user who is not the recorded maker.

Until 1 September the submit route did not run it. The gate existed on a path nobody used.

product_reality is one record doing two jobs

The signed acknowledgment this gate checks is the same row behind clientAcknowledgedAprRisk in suitability_check. Here it is a submission gate; there it is an input to a score. One row, two modules, two jobs — so a missing acknowledgment shows up twice, and fixing it clears both.

The sixth gate cannot fire

cu_membership_disclosure runs only when issuerType === 'credit_union'. CardApplication carries an issuer name and no issuer type column, so nothing anywhere can produce that value.

Five gates run. A manual saying six would be naming a control as though it were enforced — which is the failure this document exists to prevent.

fee_schedule is required by a constant and enforced by nothing

It is one of two entries in PRE_SUBMISSION_REQUIRED and no gate reads it. It now renders on the compliance panel with that stated, so the gap is visible rather than silent.

Either it becomes a gate or the constant stops calling it required. Both cannot stand. docs/decisions/submit-application.md entry 2.

## 4. THE SUITABILITY GATE — CITED, NOT RESTATED

Three facts belong to suitability_check and are recorded in docs/decisions/suitability.md. Read them there:

Fact    Where
An override records a decision and does not rewrite the verdict — overriddenBy is the signal    entry 4
The gate does not block on an unassessed gate — decided, not omitted    entry 2a
The override is resolved through the business and the tenant    entry 4

The consequence here: an unassessable gate blocks nothing at submission. Nothing records an advisor's debt-service confirmation, and blocking on it would refuse every client for a reason no client can cure.

## 5. WHAT FAILURE LOOKS LIKE

Response    Meaning
422 with failedGates    One or more gates refused. The names are in details
422 SUBMIT_IS_A_SEPARATE_ACT    An attempt to create an application already submitted
422 INVALID_TRANSITION    Not in a submittable status — including already submitted
404    No such application, or not yours

A refusal names the gates. failedGates tells a caller which controls refused, not merely that submission was refused. Report the names — "submission refused" alone discards the answer.

A gate refusal is the control working. It is not a transient failure and it is not a reason to try a different route. There is no different route.

## 6. RETRY VS ESCALATE

Never retry. Escalate.

The call flips status, stamps submittedAt, writes an audit row and emits APPLICATION_SUBMITTED to the ledger.

A second call is refused by the state machine — 422 INVALID_TRANSITION, "Cannot submit application in 'submitted' status". There is no idempotency key. The refusal is the protection, not de-duplication: the retry does not become harmless, it becomes impossible.

So a timeout leaves a question a retry cannot answer. Read the application's status. If it is submitted, the call landed.

## 7. NEVER

Never submit. An agent prepares and stages; a human presses the button. §3.

Never supply approvedByUserId from the agent's own identity or the maker's. That is the gate, and defeating it defeats the rule the compliance library is built on.

Never retry. Read the status.

Never treat a 422 naming maker_checker as a transient failure. It is the control working.

Never report a gate refusal without its failedGates. Shared rule 2 — the names are the basis.

Never read "five gates passed" as "six gates passed." The sixth cannot fire, and fee_schedule is required by a constant that nothing enforces.

Never create an application already submitted. The API refuses, and the refusal is the point.

## 8. WHICH LAWS THIS TOUCHES

compliance/application-truthfulness-v1 — the entry this module exists under. Every never in it applies at the moment of submission: no estimated values, no characterisation the client did not confirm, no signature on the client's behalf, and the conflict-surfacing rule where sources disagree. maker_checker is the mechanism behind its central claim.

compliance/client-interest-standard-v1 — a submission is a placement. That entry is explicit that can this client raise capital and should they are different questions, and the gates answer only the first.

compliance/bureau-report-handling-v1 — figures from a bureau report may be entered on the form; the report itself may not be attached.

## PROVENANCE

From the code, read 3 September 2026: the five enforced gates and their tenant scoping, the sixth's unreachable condition, failedGates in the refusal, the state machine refusing a second submit, SUBMIT_IS_A_SEPARATE_ACT.

Decided by the founder, 1–3 September 2026, recorded in docs/decisions/submit-application.md: the submit route runs the same gates as the status path; creation cannot be submission; the sixth gate is recorded inert rather than faked; fee_schedule is displayed pending a decision.

## OPEN

cu_membership_disclosure cannot fire. It needs an issuer type, and no column records one. A data-model decision, not a bug.

fee_schedule is required by a constant and enforced by nothing. Gate it or stop claiming it. Entry 2.

Three dead controls were found by one lint rule — hasConsent, hasAck, hasFeeSchedule, each queried, computed and discarded. The check had been reporting them into a stream where warnings do not fail a build. Worth knowing what else that stream carries.

## APPENDIX A — VERIFICATION, 3 September 2026

Checked against CapitalForge at the merge of #88.

**Confirmed.** The endpoint, the single submission path (the create path now refuses
`status:'submitted'` with `422 SUBMIT_IS_A_SEPARATE_ACT`), `at_most_once`, and the
five enforced gates.

**Correction — the Permission line was removed.** The manual as drafted carried none,
and that was right: the route has no `requirePermission`. An earlier attempt to file
this manual added `application:write`, which does not exist as a permission constant
at all. Removed rather than corrected to `application:submit`, because writing any
permission on this manual would state that something checks it.

**What this costs the bridge.** The Office adapter mints an internal token scoped to
each module's declared permissions, so `client_read` cannot reach `/owners` — refused
by CapitalForge's own RBAC. **For this module that mechanism is decorative.** No
`requirePermission` runs on the submit route, so the token's scope constrains nothing
and the only things standing between a brokered call and a submitted application are
the five gates and the trust tier on the grant.

The manual declares `propose`, which is the mitigation: at `propose` the call becomes
a proposal and a human approves it before anything is submitted. **That tier is doing
real work here, not belt-and-braces.** An `auto_execute` grant on this module would be
an agent submitting applications with no role check anywhere in the path.

**Not fixed here.** Adding a permission guard to a live submission route is a change to
CapitalForge's behaviour, not to the bridge, and it would refuse callers who can submit
today. Recorded so the decision is made deliberately.

