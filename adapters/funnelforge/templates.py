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
            "<p>If anything has changed in the meantime, reply to this message and it "
            "will reach the same people.</p>"
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
            "<p>If the time no longer works, reply here and we will move it.</p>"
        ),
        approval_scope="village_autonomous",
        section="3.3 / 4.5",
    ),
    "deliverable_cover": ApprovedTemplate(
        template_id="deliverable_cover",
        name="Blueprint deliverable cover email",
        subject="Your Blueprint is ready",
        html=(
            "<p>Your Blueprint is attached. It sets out what we found and what we "
            "recommend, in the order we would act on it.</p>"
            "<p>Questions are welcome; reply here and they reach the team that wrote "
            "it.</p>"
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
            "<p>This quarter's Capital Command Brief is attached.</p>"
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
            "<p>The quarterly briefing for referring partners is attached, covering "
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
