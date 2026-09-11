# FORGE OPERATING INSTRUCTION

**Forge:** FunnelForge
**Module:** `send_intake_acknowledgment`
**Endpoint:** `POST /api/emails/send` (via the adapter's `POST /send_intake_acknowledgment`)
**Template:** `intake_acknowledgment` — closed over, not a parameter
**Version:** 1.0 — drafted 9 September 2026, against `adapters/funnelforge/` at `ac6475c` and
the running FunnelForge stack
**Status:** draft, pending Compliance Review Board

> **AMENDED 10 SEPTEMBER 2026 — THE APPROVED COPY CHANGED UNDER `docs/blocking.md` B43.**
> The §4.5 gate ruled on B43's D-6 (the attachment promise) and D-1 (the reply instruction)
> and **removed both from the copy rather than building the transport**, because carrying
> them needs a second email transport in FunnelForge and *"that shouldn't happen as a side
> effect of an attachment promise"*. The body quoted in §1 below is the current one.
>
> **SUPERSEDED BY THE RULING:** every passage describing the second paragraph's reply instruction. **That paragraph is gone.** D-1 removed it.
>
> **What did not change: the transport.** Every statement in this manual about what the send
> path cannot do is still true, and every rule in §7 still stands — an agent must not say by
> hand what the copy no longer says. **What changed is only that the copy no longer says it.**
>
> **This is the template the ruling damaged least.** *"someone will be in touch about next steps"* already told the recipient to expect inbound contact, so removing the reply instruction leaves a message that still works.


Read `funnelforge-approved-send-rules.md` first. Rules 1, 3, 4, 7, 8 and 9 govern most of what
this module does and are not repeated here.

**This is the canonical manual for the six approved sends.** The other five differ in the
approved copy, the occasion and the recipient, and in nothing else — the request shape, the
refusals, the failure signatures and the retry rule are identical. Where one of the other five
has no manual yet, this one plus the shared rules is what an author starts from.

**Nothing this module sends can be delivered today.** No email provider is configured on the
running FunnelForge (shared rule 3), so every call reaches `500 SEND_FAILED` — and the adapter
answers `200` with `sent: true` over the top of it (shared rule 1). That is the first thing to
know about this module and it is stated here rather than left to §5.

## 1. WHAT IT DOES

Sends one fixed email to one named person: the Decline-Flow Handoff intake acknowledgment.

The copy is fixed and it is short. Subject: *"We have your details - Burkham Wickmont"*. Body,
in full:

> Thank you for the details you sent through. They are with our team and someone will be in
> touch about next steps.

**The agent chooses the recipient. It does not choose, edit, vary or extend the message.** The
template id is closed over in the handler (`_send_approved("intake_acknowledgment")`), the
subject and HTML come from `adapters/funnelforge/templates.py`, and there is no code path by
which a caller reaches a different body. That is the whole design: the module list is the
approved list, and this module *is* the approval for this one message.

**Who receives it.** An applicant a bank has declined, who was handed off to Burkham through
the Handoff Toolkit and has just submitted the Decline-Flow Handoff Intake form
(`docs/reference/burkham-wickmont-marketing-plan-intake.md` Part 2). They have consented
explicitly to Burkham holding their information; they have not yet been assessed, quoted,
priced or accepted.

**Two refusals run inside the handler on every call**, after The Office has already resolved
the grant, with no caller-supplied way past them:

| refusal | when |
|---|---|
| `TEMPLATE_NOT_AUTONOMOUS` / `TEMPLATE_NOT_APPROVED` | the bound template is not `village_autonomous` in `templates.py` at call time |
| `COMPLIANCE_STATE_ABSENT` / `COMPLIANCE_STATE_NOT_PASS` | `compliance_state` is anything other than the exact string `pass` |

The first cannot fire while this module is bound as it is — `assert_bindable` refuses the
binding at import. It runs anyway, per call, so that a template downgraded from autonomous to
human-approve stops being sendable **at the next call rather than at the next deploy**.

## 2. WHAT IT DOES NOT DO

**It does not tell you whether an email was sent.** `sent: true` is a constant. Shared rule 1.
Read `upstream.status`.

**It does not resolve a template.** There is no send-from-template route in FunnelForge at
all; `POST /api/emails/templates` is a routing 404 and the SDK that declares it is describing
an API that does not exist. Shared rule 6. **A report saying the acknowledgment template was
fetched or looked up is false.**

**It does not personalise.** `recipient_first_name` and `context` reach FunnelForge and change
nothing, because the approved copy contains no merge field. Shared rule 7a. The applicant
receives the same two paragraphs whoever they are.

**It does not send from Burkham.** With no `from` supplied the sender is
`FunnelForge <hello@funnelforge.ai>`. Shared rule 7b. The subject line says Burkham Wickmont
and the envelope does not.

**It does not record anything in FunnelForge.** No `EmailQueue` row, no `EmailEvent` row —
the `EmailEvent` write is conditional on a `leadId` the adapter never sends. Shared rule 7c.
**Nothing on the FunnelForge side will ever be able to say this applicant was acknowledged.**

**It does not create, find or update a lead.** It takes an email address and sends to it. If
the applicant is not in FunnelForge, this module does not put them there — that is
`capture_contact`, with its own grant and its own manual.

**It does not confirm the applicant's details were received by anyone.** The copy says the
details *"are with our team"*. The module has no view of Console, of the Consent &
Authorization Center, or of whether any human has the file. **The message asserts a state of
the world the module cannot see.** If that assertion is wrong, sending this makes it worse.

**It does not check the recipient against anything.** No suppression list, no opt-out list, no
prior-send check, no bounce history. FunnelForge has an opt-out surface; this path does not
consult it.

**It does not know whether it has already sent.** Nothing is written (7c), so no second call
can discover the first. Shared rule 8.

## 3. WHAT EACH INPUT MEANS

| Field | Meaning |
|---|---|
| `recipient_email` | **Required.** The applicant's address. The only field that changes what happens |
| `compliance_state` | **Required, and must be exactly `pass`.** §3.3's categorical state for this message |
| `recipient_first_name` | Accepted, forwarded as `to.firstName`, **and changes nothing** |
| `context` | Accepted, forwarded as `to.data`, **and changes nothing** |
| `template_id` | **Read by nothing.** The handler never consults the payload for it |

**`compliance_state` is supplied by the caller because FunnelForge holds no such state**, and
that is the fact that makes it dangerous. §3.3's four states — Pass, Pass with Findings, Needs
Review, Fail — determine the routing, and only `pass` permits an unattended send. The check is
written as `state == "pass"`, so **absent is refused exactly as hard as `fail`**: a missing key
is the most likely way a caller gets this wrong, and a `state != "pass"` check would have let
`None` through.

**The agent does not decide this value.** It carries a state that a compliance process
produced. An agent that supplies `"pass"` because it believes the message is fine has replaced
a categorical review with its own judgement, and the refusal it defeated was the only place
that judgement was checked.

**`context` is the field most likely to be misused, precisely because it is accepted.** It
looks like a way to tell the applicant something — a reference number, a date, a name. It is
not. The approved body has no merge fields, so a `context` of any shape produces the identical
email. An agent that puts information there and then reports having communicated it has
reported something that did not happen.

**Absent `recipient_email` or `compliance_state` is refused before any call is made**, as
`422 ARGUMENT_MISSING` naming the field. Empty string counts as absent.

## 4. THE CORRECT SEQUENCE

1. **Establish that the applicant submitted the intake form and that a human wants them
   acknowledged.** This module does not observe the form submission and cannot infer it.
2. **Obtain the categorical compliance state for this message from the process that produces
   it.** Do not compose it.
3. **Call once**, with `recipient_email` and `compliance_state`.
4. **Read `upstream.status`.** Not `sent`. Shared rule 1.
5. **Report what the status says, in the status's own terms** — `200` means a provider
   accepted the message, `500 SEND_FAILED` means it did not, `422` means the handler declined,
   `429` means nothing was sent and the call was refused before the route ran.
6. **Do not call again.** Whatever the answer. Shared rules 8 and 9; the exception for a 429
   is a wait, and it is in §6.

**Step 4 is the one that carries.** Every other step in this list can be got right while step
4 is skipped, and the result is a confident report of an email that does not exist. Today, on
the running stack, that is the outcome of **every** correct-looking call.

## 5. WHAT FAILURE LOOKS LIKE

### From the adapter

| Response | Meaning |
|---|---|
| `503 ADAPTER_NOT_CONFIGURED` | `FUNNELFORGE_TENANT_TOKEN` is unset. **Not a refused credential — do not rotate anything** |
| `401 UNAUTHENTICATED` | The presented token does not match the configured one |
| `404 MODULE_NOT_BOUND` | This spelling is not in the dispatch map. Not a FunnelForge 404 |
| `422` + `error.code` | The handler declined. `ARGUMENT_MISSING`, `ARGUMENT_INVALID`, `COMPLIANCE_STATE_ABSENT`, `COMPLIANCE_STATE_NOT_PASS`, `TEMPLATE_NOT_AUTONOMOUS`, `TEMPLATE_NOT_APPROVED` |
| `200` | **The handler ran.** Says nothing about the send. Read `upstream.status` |

The 503 and the 401 are deliberately different answers, and collapsing them sends whoever is
debugging to rotate a credential that was never the problem.

### From FunnelForge, at `upstream.status`

| Status | Body | Meaning |
|---|---|---|
| `200` | `{"success":true,"data":{"messageId":...}}` | A provider accepted it |
| `400` | `VALIDATION_ERROR` | Zod refused the body. In practice: `recipient_email` is not an email |
| `401` | `FST_JWT_NO_AUTHORIZATION_IN_HEADER` | The brokered token did not reach the route |
| `429` | `RATE_LIMIT_EXCEEDED` | Refused before the route ran. **Nothing was sent.** Shared rule 4 |
| `500` | `SEND_FAILED` | The provider layer answered `success: false` |

**`500 SEND_FAILED` is the answer to expect today, and its message names the cause:** *"No
email provider configured. Set RESEND_API_KEY, SENDGRID_API_KEY, AWS_SES_*, or SMTP_*
environment variables."* Shared rule 3. It is a configuration fact about FunnelForge, not a
fault in the request, and it will not be fixed by changing anything about the call.

**A `400 VALIDATION_ERROR` carries only the first Zod issue.** `error.errors[0].message` is
what travels. If more than one field is wrong, the response names one of them.

**There is no 404 from FunnelForge on this module.** The send route does not look anything up.
A 404 from this module is the adapter's `MODULE_NOT_BOUND` and means a spelling problem, not a
missing recipient.

**A 422 is an answer, not a crash.** It carries the machine code and the reason, both, and
they reach the ledger. Report the code — `COMPLIANCE_STATE_NOT_PASS` and
`COMPLIANCE_STATE_ABSENT` are different facts and need different people.

## 6. RETRY VS ESCALATE

**On a timeout: stop and escalate. Do not retry. Do not check first.** Shared rule 9.

There is nothing to check. Nothing is written in FunnelForge (§2), so no query anywhere can
tell an agent whether the first attempt reached a provider. "Verify, then resend" is verifying
against nothing, and the failure it would produce — an applicant receiving the same
acknowledgment twice, from a firm they have just been referred to — is visible, permanent and
in Burkham's own correspondence.

**A 429 is a wait, not a retry.** The rate-limit hook refuses before the route runs, so the
outcome is unambiguous: nothing was sent. Honour `retryAfter` from the body. Read shared rule
4c before concluding anything about pacing — the bucket is shared across every agent and every
FunnelForge module, so a refusal is not evidence that this agent called too often.

**A 500 is an escalation, and today it is a *specific* escalation.** `SEND_FAILED` with the
no-provider message is not a transient fault and not the agent's to fix. It goes to whoever
operates the FunnelForge deployment, named as a configuration gap, and the report says the
acknowledgment was **not** sent. It does not go to a compliance reviewer, and it is not
retried in an hour in the hope that it clears.

**A 422 is not an escalation to the same person as a 500.** `COMPLIANCE_STATE_NOT_PASS` goes
to whoever produced the state. `ARGUMENT_MISSING` goes back to whoever composed the call. Both
are refusals with a reason attached, and the reason is the routing.

## 7. NEVER

**Never report a send from `sent: true`.** It is a constant. Shared rule 1, and on the stack
running today this single mistake produces a false report on every call.

**Never retry a send.** Shared rules 8 and 9. There is no idempotency key on the path and no
way to discover a prior attempt.

**Never check whether it already sent.** There is nothing to check. An agent that queries
FunnelForge to find out has confirmed only that nothing was written, which it already knew.

**Never supply `compliance_state` from the agent's own reading of the message.** The value
carries a categorical state a process produced. Composing it defeats the only control that
exists for it, and the refusal it defeats is the one the whole module was designed around.

**Never treat an absent `compliance_state` as permissive.** It is refused as hard as `fail`,
by design, and an agent that adds `"pass"` to make a `COMPLIANCE_STATE_ABSENT` go away has
done the thing the check was written to prevent.

**Never put information in `context` and then report having communicated it.** The approved
body has no merge fields. Nothing in `context` reaches the applicant.

**Never describe the sender as Burkham.** It is `FunnelForge <hello@funnelforge.ai>` unless
somebody configures otherwise. Shared rule 7b.

**Never restate, summarise or paraphrase the message as if it said more than it does.** It
says the details are with the team and someone will be in touch. It does not say when, does
not say by whom, does not confirm receipt of any document, and promises nothing about the
outcome.

**Never send this to someone who has not submitted the intake form.** The copy thanks them for
details they sent; sending it to a banker, a prospect, or an applicant who was handed a URL
and never used it is a message about an act that did not happen.

**Never send this as a substitute for an answer.** An applicant chasing a decision does not
need a second acknowledgment. Re-sending it is the module's easiest misuse because it is
always available and always looks like progress.

**Never send it twice for any reason.** Including a first attempt whose outcome is unknown.
Escalate instead.

## 8. WHICH LAWS THIS TOUCHES

**`compliance/outbound-contact-boundary-v1`** (FTC_TSR) — *"Any Burkham-initiated contact with
an individual, any channel."* This module is Burkham-initiated contact with an individual. It
is the governing entry. Shared rule 10 records the open question about whether it should
appear in the Pack's `compliance_flags_propagated` for this Forge; nothing here changes that.

**`compliance/own-claims-and-pricing-v1`** (FTC_ACT) — the copy is a statement Burkham makes
about its own service. The review that admitted this template to the approved list is where
that entry was applied, and an agent adds nothing to the claim and cannot.

**ECOA and FCRA notices are on the intake form, not on this message.** Part 2.8 of the
marketing-plan intake places those notices in the Decline-Flow Handoff Intake form, alongside
the referral disclosure and the explicit consent capture, and marks them
`[COMPLIANCE REVIEW PENDING]`. **This module sends an acknowledgment after that form, and
carries none of them.** Stated so that an agent does not treat this email as the notice, and
does not treat its delivery as evidence that any notice was given.

**No FCRA entry applies to what this module handles.** It handles an email address. §6.3 caps
FunnelForge at anonymous browsing data and named-contact marketing PII — no credit data, no
financial statements, nothing bureau-derived. Part 2.6 is emphatic in the same direction from
the other side: the declining bank does not send Burkham the applicant's file, and the
applicant brings their own data through the intake form.

**`compliance/consumer-privacy-rights-v1`** — the recipient's address is personal data about a
person, subject to access and deletion rights. The module writes nothing, so it adds no record
to answer such a request from; The Office's ledger row is the only one it creates.

## PROVENANCE

**Read from `adapters/funnelforge/` at `ac6475c`:** `_send_approved` and its closure, the two
refusals and their exact codes, the request body, the constant `sent: True`, `_require` and its
`ARGUMENT_MISSING`, and the approved copy verbatim from `templates.py`.

**Read from FunnelForge's source:** `sendEmailSchema` and its Zod messages, the
`leadId`-conditional `EmailEvent` write, the synchronous `emailSender.send()` call, and
`EmailSender.initializeProviders()`.

**Measured on the running containers, 9 September 2026:** the empty `RESEND_API_KEY`, the
`EmailSender: Available providers:` line with nothing after it, and the 429 shape. See the
shared rules for the transcripts.

**From `docs/reference/burkham-wickmont-marketing-plan-intake.md`:** Part 2 — who the
recipient is, how they arrive, what the banker does and does not send, and where the ECOA and
FCRA notices live.

## OPEN

**The copy asserts something the module cannot see.** *"They are with our team and someone
will be in touch about next steps."* Whether the details reached Console, whether anyone is
assigned, and whether anyone will in fact be in touch are facts in a different system. An
autonomous send that makes a factual claim about a state it cannot observe is a shape worth a
decision, and nobody has made one. Recorded rather than answered.

**No suppression check exists on this path.** An applicant who has opted out of Burkham
contact would receive this, because the send route consults nothing. Whether an approved
transactional acknowledgment should honour a marketing opt-out is a policy question; that it
*cannot* today is a fact about the route.

**Whether a send module should be grantable before a delivery record exists.** Nothing in
FunnelForge or The Office records that a message arrived, bounced or was complained about.
Shared rule 11.
