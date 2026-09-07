# FunnelForge and AnimaForge — the agent-facing surface

**Proposal, 7 September 2026. Nothing bound, nothing built.** Read this before committing
to a module count for either Forge.

Sources: `docs/reference/burkham-wickmont-marketing-plan-intake.md` §3.3, §3.4, §4.5,
§4.6, §6.2, §6.3; `burkham-wickmont-operations-console/docs/reference/blueprint-v2.md`
§4.5; FunnelForge's Prisma schema and `apps/api/src/services/content/`.

---

## The condition, first, because it decides the shape

**A single `send_approved_template` module is only safe if the module itself refuses.**

One grant would cover every approved template. That is acceptable *only* when the handler
declines, on its own, to send:

- a template whose approval scope is not Village-autonomous, and
- any message whose categorical compliance state is not **Pass**.

Not the caller's job. Not a convention. The handler's, verified by tests that call it with
a human-approve template and a non-Pass state and assert refusal — the same reason
`assign_contract` validates signers rather than accepting what the service stores
unexamined.

**That is the condition. Everything below turns on whether it can be met.**

---

## It cannot be met today

Both facts the gate needs are **absent from FunnelForge**.

### A template carries no approval scope

`model EmailTemplate` — `name`, `subject`, `body`, `content`, `htmlContent`,
`type` (*"marketing, transactional, etc."*), `category`, `isActive`, `metadata Json`.

`isActive` is on/off. Nothing distinguishes *"Village autonomous, Pass state"* from
*"Human approve send"* — the distinction §4.5 draws across its seven V1 templates, where
six are autonomous and the engagement letter cover email is not.

`OutreachTemplate` and `SMSTemplate` are the same shape.

### The compliance state does not exist

§3.3 says the categorical state — **Pass / Pass with Findings / Needs Review / Fail** —
*"determines the routing"*. FunnelForge's schema contains no such state. No
`needs_review`, no `pass_with_findings`, no equivalent under any spelling.

### The approval machinery that does exist is a different thing

`ApprovalWorkflow` and `ApprovalRequest` are FunnelForge's own content-approval chain:
`contentTypes`, `stages`, `escalationRules`, and `autoPublishOnFinalApproval` — publish
*after* a human approval completes. That is the opposite direction from *"this template
may be sent with no human involved"*.

There is no Marketing Claim Library in FunnelForge. The phrase appears nowhere in the
schema or the services.

**So template-gating is not implementable as a FunnelForge-side control.** It would
require FunnelForge to learn two facts it has no field for.

---

## What is implementable today: the adapter is the gate

Module-gating works **now**, without any FunnelForge change, because of a property the
adapter already has: *the adapter's keys are the spelling of record*
(`docs/forge-adapter.md`).

Bind one module per autonomous template. **The handler hardcodes its template id**; the
agent supplies only recipient and context and cannot name a template. The approval scope
is then expressed by *which modules exist* — a template that is not autonomous simply has
no module, and an agent has no way to reach it.

This inverts the earlier reading. Template-gating looked cheaper because §4.5 says the
template inventory should grow; but the gate has to live somewhere, and the only place
that can hold it today is the module list.

### Proposed surface — six modules

From §4.5's inventory and §4.6's autonomous categories:

| module | template | mutating | idempotency |
|---|---|---|---|
| `send_intake_acknowledgment` | Decline-Flow Handoff intake acknowledgment | yes | `at_most_once` |
| `send_scheduling_confirmation` | Blueprint scheduling confirmation | yes | `at_most_once` |
| `send_deliverable_cover` | Blueprint deliverable cover email | yes | `at_most_once` |
| `send_followup_no_engagement` | Post-Blueprint no-engagement follow-up | yes | `at_most_once` |
| `send_brief_cover` | Capital Command Brief cover email | yes | `at_most_once` |
| `distribute_referrer_briefing` | Referrer quarterly briefing | yes | `at_most_once` |

**`at_most_once` throughout, and not defensively.** An email leaves the system and reaches
a person; a retry sends a second one. There is no de-duplication to verify because there
is no idempotency key in `EmailQueue` — it has `templateId`, `recipient`, `status`,
`scheduledAt`, and nothing that would recognise a repeat.

**Not bound:** the engagement letter cover email. §4.5 puts it at *human approve send*
through Deliverable Approval Workflow, which is Console module 3.4 — not connected to the
bridge. It gets no module, which is the whole point of module-gating.

### Three more acts, different in kind

| module | § | mutating | note |
|---|---|---|---|
| `schedule_blueprint_call` | §3.3 | yes | worker-autonomous Pass state; a booking, not an email |
| `capture_contact` | §6.2 | yes | newsletter signup / gated download — the named-contact PII FunnelForge is allowed to hold |
| `read_funnel_analytics` | §6.2 | no | anonymous browsing and pixel data, aggregated, no PII |

**Nine modules total.** Not 73, and not four.

### What §6.2 and §6.3 cap permanently

FunnelForge holds **anonymous browsing data and named-contact marketing PII only** — no
credit data, no Plaid data, no financial statements, nothing FCRA-regulated. §6.3 makes it
architectural rather than policy: *"FunnelForge cannot query Console for credit data to
segment marketing sequences."*

So no FunnelForge module can ever read underwriting data. That bounds the surface for
good, not just for V1.

### The cost of module-gating, stated

§4.5: *"the number of approved templates should grow as patterns solidify."* Under
module-gating each new autonomous template is a Pack edit, a registry row, a manifest row
and a certification.

That is real friction, and it is not obviously wrong — §4.5 also says *"the review gate on
new templates is strict (APPROVED list additions require both founders)"* and *"better to
route to human than to add a marginal template."* A process that makes adding a template
deliberate is aligned with that, not fighting it.

### What would make template-gating viable later

Two fields upstream, and then one module replaces six:

1. a per-template approval scope on `EmailTemplate` — autonomous vs human-approve;
2. a compliance state that the send path can read and refuse on.

Both are FunnelForge changes. Neither is The Office's to make, and until they exist the
refusal cannot be written, so the module must not be written either.

---

## AnimaForge — two facts that do not resolve each other

**Both are true and neither overrides the other.**

**It is in the first wave by founder decision.** AnimaForge is named in blueprint §4.5
Marketing Ops as a content-production dependency, alongside SelfPublisherForge and
VideoEditForge, and it is in the estate as a Forge to be bridged.

**V1's marketing plan gives it nothing to do.** No agent-facing act in the intake document
produces video or generated creative. Everything creative is human-authored: Dream 100
outreach (§3.3, §4.5 — *"human-authored per contact"*), the newsletter and founder essay
(§4.5 — *"Human-authored"*), the briefing webinar (§3.3 — *"Human-run"*). The worker's
share is distribution of content a human produced.

**So the proposed count for AnimaForge in V1 is zero.**

### The two facts are not the same kind of fact

§3.4's ban on `place_call` is a **ruling** — explicit, reasoned, with a V1.5 revisit
condition. Nothing comparable exists for AnimaForge.

**Zero here is inferred from what the intake does not say**, and absence of an act is
weaker evidence than a stated prohibition. The marketing plan may simply not be the
document that scopes video work, and a scope that lives in someone's head is not the same
as a scope that was decided against.

**This is a scoping question, not something to settle from the absence.** Recorded so that
neither fact quietly overrides the other: not "AnimaForge is out of the first wave" — the
founder decision says otherwise — and not "AnimaForge needs modules" — the plan names no
act. Both stand until ruled.
