"""The approved template inventory, and why it lives here instead of in FunnelForge.

READ THIS BEFORE ADDING A TEMPLATE
==================================

`docs/plans/funnelforge-animaforge-surface-PROPOSAL.md` established that FunnelForge
holds neither fact the send gate needs: `EmailTemplate` carries `type`, `category`,
`isActive` and `metadata`, and `isActive` is on/off; there is no compliance state under
any spelling. That was read out of the Prisma schema on 7 September 2026 and it still
holds - `packages/database/prisma/schema.prisma`, `model EmailTemplate`, line 10515.

**A second fact was found on 9 September 2026 and it is stronger than the first: there
is no send-from-template path in FunnelForge at all.**

    POST /api/emails/send        takes `to`, `subject`, `html`. No templateId.
    POST /api/emails/broadcast   takes `businessId`, `subject`, `body`. No templateId.
    POST /api/emails/templates   404. The SDK declares template CRUD
                                 (`packages/sdk-js/src/resources/emails.ts`);
                                 `apps/api/src/modules/emails/routes.ts` implements
                                 none of it. Probed live against the running container:
                                 {"message":"Route POST:/api/emails/templates not
                                 found","error":"Not Found","statusCode":404}
    EmailQueue.templateId        written by four call sites, read by none. The sender
                                 is the BullMQ `email-send` queue and it carries
                                 rendered content, not a template reference.

So the proposal's phrase *"the handler hardcodes its template id"* cannot mean an id
FunnelForge would resolve. There is nothing on the other side to resolve it against.

What survives is the design, not the mechanism: the approved content is the thing under
review, so the approved content lives where review happens - in this file, in git,
behind the same two-founder gate §4.5 asks for. The handler sends the body it was bound
to and cannot be asked for another. FunnelForge is the transport.

**That is a consequence worth stating plainly rather than burying:** the approved-copy
library for autonomous send is this module, not a FunnelForge table. If FunnelForge ever
grows a per-template approval scope and a readable compliance state, this file is what
gets deleted - and the six modules collapse to one, exactly as the proposal describes.

WHAT THE COPY NO LONGER PROMISES - B43, RULED 10 SEPTEMBER 2026
===============================================================

**The copy below was changed under a §4.5 ruling. Do not restore what was removed.**
`docs/blocking.md` B43 carries the reasoning; `tests/adapters/test_funnelforge_approved_copy.py`
fails loudly if any removed promise returns.

Four findings stood against these bodies. Two were ruled and applied here; two are open.

    D-6  RULED - REMOVED. Three bodies said a document was *"attached"* and the send path
         has no attachment field. `deliverable_cover`, `brief_cover` and
         `referrer_briefing` now say *"is ready"*.
    D-1  RULED - REMOVED. Three bodies told the recipient to *"reply"* and there is no
         Reply-To on the path these sends actually use, so a reply reached
         `hello@funnelforge.ai` rather than Burkham (shared rule 7b). The instruction is
         gone from `intake_acknowledgment`, `scheduling_confirmation` and
         `deliverable_cover`.
    D-2  OPEN. `scheduling_confirmation` still says *"the details are below"* over a body
         with no merge field, and still promises a calendar invitation nothing here
         produces.
    D-3  OPEN. No body carries an unsubscribe link, and there is nowhere on this path for
         one to point.

**Ivan's reasoning, because it decides the next case as well as this one:** a second
transport plus a separate `sendAMPEmail()` branch is *"choosing which transport FunnelForge
has, and that shouldn't happen as a side effect of an attachment promise."* Keeping the
promise would have forced an architectural decision about FunnelForge's email transport as
a consequence of a line of marketing copy. **That decision is not refused - it is separated.**

**`engagement_letter_cover` still says "attached", and that is deliberate.** It is
`human_approve`, bound to no module, and refused at import by `assert_bindable` and at call
by `refuse_unless_autonomous`. §4.5 routes it through Deliverable Approval Workflow (Console
module 3.4), where a human sends it and can genuinely enclose the letter. **It is not sent by
this transport, so this transport's missing field is not a defect in it.** Removing its
promise would apply a constraint from a path it never takes.

WHAT THE REMOVALS COST, RECORDED WHERE THE COPY IS
==================================================

**Three of these templates now announce a document the recipient has no way to obtain.**
There is no link in any approved body, no portal URL anywhere in the inventory, and
`context` cannot add one - shared rule 7a, and see the merge-field note below. The only
Burkham channel documented anywhere in this repository is `privacy@burkhamwickmont.com`
with `burkhamwickmont.com/privacy-request`, both of which are the §6.5 removal desk and
neither of which is a place to ask for a Blueprint.

**So B43 records three templates that should not be sent in this state**, and the gate
cannot enforce that because the gate checks approval scope and compliance state, not whether
a message leaves the reader anywhere to go. Read B43 before binding an agent to
`send_deliverable_cover`, `distribute_referrer_briefing` or `send_followup_no_engagement`.

WHY NO MERGE FIELD MAY BE ADDED HERE
====================================

`personalizeContent` replaces `{{firstName}}`, `{{lastName}}`, `{{email}}` and
`{{fullName}}` unconditionally, and one `{{key}}` per `to.data` entry - but an unmatched tag
is **left in the body verbatim**. `context` is optional on every send handler, so a body
containing `{{date}}` would deliver a literal `{{date}}` to a client whenever the caller
omitted it. That is why D-2 was not answered by making *"the details are below"* true.

THE TRANSPORT FACT THESE RULINGS REST ON, READ FROM THE RECEIVING SIDE
======================================================================

`apps/api/src/services/email/multi-provider.ts` does carry `replyTo` and `attachments` and
does map them per provider - **and it is not on this path.**
`apps/api/src/modules/emails/routes.ts` imports `emailSender` from
`@funnelforge/email-engine`, a different sender: `apps/email-engine/src` holds no occurrence
of "attach" in any case and no Reply-To across its nine TypeScript files, its
`SendEmailOptions` is `to`/`from`/`content`/`tags`/`metadata`, and its `send()` branches into
a separate `sendAMPEmail()` with its own provider handling. **D-1 and D-6 were therefore the
same missing field on the same sender, which is why one ruling closed both.**
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: §4.5 draws exactly one line across its template inventory, and it is not a spectrum.
#: `village_autonomous` may be sent with nobody in the path. `human_approve` may not,
#: and routes through Deliverable Approval Workflow (Console module 3.4), which is not
#: connected to the bridge.
ApprovalScope = Literal["village_autonomous", "human_approve"]


@dataclass(frozen=True, slots=True)
class ApprovedTemplate:
    """One entry on the APPROVED list, with the scope §4.5 assigned it."""

    template_id: str
    name: str
    subject: str
    html: str
    approval_scope: ApprovalScope
    section: str
    """Where in the marketing-plan intake this template and its scope are stated."""


#: §4.5's V1 inventory: seven templates, six autonomous and one not.
#:
#: **The seventh is here on purpose.** `engagement_letter_cover` is `human_approve`, has
#: no module, and would be unreachable even if this dict were empty - module-gating
#: already stops it. It is in the inventory anyway so the handler's refusal has a real
#: template to refuse rather than a fabricated one, and so a test can name it. A control
#: whose only test input is invented is a control tested against the tester's
#: imagination.
APPROVED_TEMPLATES: dict[str, ApprovedTemplate] = {
    "intake_acknowledgment": ApprovedTemplate(
        template_id="intake_acknowledgment",
        name="Decline-Flow Handoff intake acknowledgment",
        subject="We have your details - Burkham Wickmont",
        html=(
            "<p>Thank you for the details you sent through. They are with our team and "
            "someone will be in touch about next steps.</p>"
        ),
        approval_scope="village_autonomous",
        section="3.3 Decline-Flow Handoff / 4.5",
    ),
    "scheduling_confirmation": ApprovedTemplate(
        template_id="scheduling_confirmation",
        name="Blueprint scheduling confirmation",
        subject="Your Blueprint call is confirmed",
        html=(
            "<p>Your Blueprint call is confirmed. The details are below, and a calendar "
            "invitation follows separately.</p>"
        ),
        approval_scope="village_autonomous",
        section="3.3 / 4.5",
    ),
    "deliverable_cover": ApprovedTemplate(
        template_id="deliverable_cover",
        name="Blueprint deliverable cover email",
        subject="Your Blueprint is ready",
        html=(
            "<p>Your Blueprint is ready. It sets out what we found and what we "
            "recommend, in the order we would act on it.</p>"
        ),
        approval_scope="village_autonomous",
        section="4.5",
    ),
    "followup_no_engagement": ApprovedTemplate(
        template_id="followup_no_engagement",
        name="Post-Blueprint no-engagement follow-up",
        subject="Following up on your Blueprint",
        html=(
            "<p>We wanted to check in on the Blueprint we sent through. There is no "
            "obligation either way - if the timing is wrong, say so and we will leave "
            "it there.</p>"
        ),
        approval_scope="village_autonomous",
        section="4.5",
    ),
    "brief_cover": ApprovedTemplate(
        template_id="brief_cover",
        name="Capital Command Brief cover email",
        subject="This quarter's Capital Command Brief",
        html=(
            "<p>This quarter's Capital Command Brief is ready.</p>"
            "<p>It is written to be read in ten minutes and acted on in one "
            "conversation.</p>"
        ),
        approval_scope="village_autonomous",
        section="4.5",
    ),
    "referrer_briefing": ApprovedTemplate(
        template_id="referrer_briefing",
        name="Referrer quarterly briefing",
        subject="Quarterly briefing for referring partners",
        html=(
            "<p>The quarterly briefing for referring partners is ready, covering "
            "what we are seeing in the market and what we are able to place.</p>"
        ),
        approval_scope="village_autonomous",
        section="4.5 / 6.2",
    ),
    "engagement_letter_cover": ApprovedTemplate(
        template_id="engagement_letter_cover",
        name="Engagement letter cover email",
        subject="Your engagement letter",
        html="<p>Your engagement letter is attached for signature.</p>",
        # NOT autonomous. §4.5 routes this through Deliverable Approval Workflow -
        # Console module 3.4, which is not connected to the bridge. It has no module,
        # and the handler refuses it a second time if one is ever bound by mistake.
        approval_scope="human_approve",
        section="4.5 (human approve send)",
    ),
}


def autonomous_template_ids() -> frozenset[str]:
    """The ids the handler will send. Derived, so it cannot disagree with the table."""
    return frozenset(
        t.template_id
        for t in APPROVED_TEMPLATES.values()
        if t.approval_scope == "village_autonomous"
    )
