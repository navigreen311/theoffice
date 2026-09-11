"""The approved copy, guarded against the promises B43 removed and the two still open.

WHAT THESE TESTS ARE
====================

`docs/blocking.md` B43 ruled two of the four findings against
`adapters/funnelforge/templates.py` on 10 September 2026 and left two open. The tests here
are in three groups and the groups behave differently on purpose:

**REMOVED - these fail if a promise comes back.** D-6's *"attached"* and D-1's *"reply"* are
gone from every autonomous template. The copy sits behind the §4.5 two-founder gate, so the
way it comes back is not malice, it is somebody restoring a sentence that reads like an
improvement. These tests make that fail with the reason attached.

**STILL OPEN - these assert a defect that has not been ruled.** D-2 and D-3 are
characterisations: they pin the unkeepable promise as it stands, name B43, and fail if it is
edited in either direction. A test asserting the *fixed* copy would fail today, and a test
asserting nothing would let the next reader delete the evidence a pending decision rests on.

**COST OF THE REMOVALS - these pin what the ruling left behind.** Three templates now
announce a document the recipient cannot obtain, and one send offers no remedy at all. B43
records those as findings rather than as finished work. If somebody later supplies a
delivery channel, these tests fail and B43's open items can close - which is the intent.

WHY NO SUBSTITUTE CHANNEL WAS WRITTEN IN
========================================

The only Burkham channel documented anywhere in this repository is
`privacy@burkhamwickmont.com` with `burkhamwickmont.com/privacy-request` - the §6.5 removal
desk, not a place to ask for a Blueprint. Naming any other address would have been inventing
a fact, which is the error this whole run exists to correct.
`test_no_approved_body_names_an_undocumented_channel` enforces that.

MEASURED, NOT ASSUMED
=====================

    apps/api/src/modules/emails/routes.ts imports `emailSender` from
    `@funnelforge/email-engine` - NOT from `apps/api/src/services/email/multi-provider.ts`,
    which carries `replyTo` and `attachments` and is reached only by a barrel re-export and
    `services/email/test-sender.ts`.

    apps/email-engine/src: zero occurrences of "attach" in any case across its nine .ts
    files, and no Reply-To. `send()` branches into a separate `sendAMPEmail()` with its own
    provider handling.

    `personalizeContent` substitutes {{firstName}}, {{lastName}}, {{email}} and
    {{fullName}} unconditionally, plus one {{key}} per `to.data` entry, and leaves an
    unmatched tag in the body verbatim.
"""

from __future__ import annotations

import re

import pytest

from adapters.funnelforge.modules import MODULES
from adapters.funnelforge.templates import APPROVED_TEMPLATES, autonomous_template_ids

B43 = (
    "See docs/blocking.md B43, ruled 10 September 2026. Restoring this sentence would "
    "re-promise something the send path cannot do - the transport was not changed, only "
    "the copy was."
)

OPEN = (
    "This sentence is evidence for an OPEN item in docs/blocking.md B43. If the §4.5 gate "
    "has now ruled it, update B43 and this test together - do not delete one of them."
)

#: The three whose enclosure promise D-6 removed. They now say "is ready".
FORMER_ENCLOSURE_TEMPLATES = {"deliverable_cover", "brief_cover", "referrer_briefing"}

#: The only Burkham channel documented anywhere in this repository - marketing plan §6.5.
#: It is the removal desk. Any other address in an approved body is invented.
DOCUMENTED_CHANNELS = {"privacy@burkhamwickmont.com"}

ALWAYS_SUBSTITUTED = {"firstName", "lastName", "email", "fullName"}
MERGE_TAG = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _autonomous() -> dict[str, str]:
    ids = autonomous_template_ids()
    return {t.template_id: t.html for t in APPROVED_TEMPLATES.values() if t.template_id in ids}


def _all() -> dict[str, str]:
    return {t.template_id: t.html for t in APPROVED_TEMPLATES.values()}


# ============================================================ REMOVED - must not return


@pytest.mark.parametrize("template_id", sorted(autonomous_template_ids()))
def test_no_autonomous_body_promises_an_attachment(template_id: str):
    """D-6, ruled and removed. The send path has no attachment field at any layer.

    `apps/email-engine/src` contains no occurrence of "attach" in any case, and adding one
    is a second transport rather than a schema field - which is the reason the copy changed
    instead of the transport.
    """
    html = APPROVED_TEMPLATES[template_id].html
    assert "attach" not in html.lower(), (
        f"{template_id} promises an attachment again. {B43}"
    )


@pytest.mark.parametrize("template_id", sorted(autonomous_template_ids()))
def test_no_autonomous_body_tells_the_recipient_to_reply(template_id: str):
    """D-1, ruled and removed. There is no Reply-To on the path these sends use.

    The adapter sends no `from`, so a reply addresses `hello@funnelforge.ai` - shared rule
    7b. Every reply instruction here directed a client to an address that is not Burkham's.
    """
    html = APPROVED_TEMPLATES[template_id].html
    assert "reply" not in html.lower(), (
        f"{template_id} instructs a reply again, and a reply still does not reach "
        f"Burkham. {B43}"
    )


def test_the_three_former_cover_notes_say_ready_rather_than_attached():
    """The specific replacement, pinned so a revert is visible as a revert."""
    for template_id in sorted(FORMER_ENCLOSURE_TEMPLATES):
        html = APPROVED_TEMPLATES[template_id].html.lower()
        assert "is ready" in html, f"{template_id} no longer says 'is ready'. {B43}"


def test_engagement_letter_cover_keeps_its_attachment_promise_deliberately():
    """The fourth `attached` sentence was left, and that is the ruling, not an oversight.

    `engagement_letter_cover` is `human_approve`: bound to no module, refused at import by
    `assert_bindable` and at call by `refuse_unless_autonomous`. §4.5 routes it through
    Deliverable Approval Workflow (Console module 3.4), where a human sends it and can
    genuinely enclose the letter. This transport's missing field is not a defect in a
    template this transport never sends.
    """
    template = APPROVED_TEMPLATES["engagement_letter_cover"]
    assert "attached" in template.html.lower(), (
        "engagement_letter_cover's promise was removed. It is sent by a human through "
        "Console module 3.4, not by this transport, so the attachment field this adapter "
        "lacks is not a defect in it. " + B43
    )
    assert template.approval_scope == "human_approve"
    assert template.template_id not in autonomous_template_ids()
    assert template.template_id not in {
        b.template_id for b in MODULES.values() if b.template_id is not None
    }


# ================================================================ STILL OPEN - D-2, D-3


def test_scheduling_confirmation_still_points_at_details_it_does_not_contain():
    """D-2, open. No transport ruling can make this true.

    Reply-To would not fix it and an attachment field would not fix it: the body is a fixed
    string with no merge field, so "below" refers to nothing on every send. It was not
    removed with D-1 and D-6 because it was not ruled with them.
    """
    html = APPROVED_TEMPLATES["scheduling_confirmation"].html
    assert "details are below" in html.lower(), OPEN
    assert not MERGE_TAG.search(html), (
        "a merge field appeared in scheduling_confirmation. Check it against "
        "test_no_approved_body_carries_an_unsubstituted_merge_tag first: an unmatched tag "
        "ships to the client verbatim."
    )


def test_scheduling_confirmation_still_promises_a_calendar_invitation():
    """D-2, open. No module on this Forge emits an `.ics`, and the transport could not
    carry one: as a file it is an attachment, which is what D-6 just established is a
    second transport."""
    assert "calendar invitation" in APPROVED_TEMPLATES["scheduling_confirmation"].html.lower(), OPEN


def test_no_approved_body_carries_a_link_or_an_unsubscribe():
    """D-3, open. §6.5 puts a one-click unsubscribe in every marketing email.

    There is also nowhere on this path for such a link to point: FunnelForge implements
    unsubscribe per *sequence enrolment* only, and an approved send creates no enrolment and
    no EmailEvent (shared rule 7c). So D-3 was never a copy-only fix.
    """
    for tid, html in _all().items():
        assert "<a" not in html.lower(), f"{tid} grew a link. {OPEN}"
        assert "unsubscribe" not in html.lower(), f"{tid} grew an unsubscribe. {OPEN}"


# ==================================================== COST OF THE REMOVALS - B43 findings


def test_three_templates_announce_a_document_with_no_way_to_obtain_it():
    """B43's first cost finding, pinned. These three should not be sent in this state.

    Each now says a document is ready and carries no link, no address and no enclosure.
    There is no portal URL anywhere in the inventory and `context` cannot add one (7a).
    **If this test fails because a channel was added, that is B43 closing** - update it.
    """
    for template_id in sorted(FORMER_ENCLOSURE_TEMPLATES):
        html = APPROVED_TEMPLATES[template_id].html
        assert "is ready" in html.lower()
        assert "<a" not in html.lower() and not EMAIL.search(html), (
            f"{template_id} now names a way to obtain the document. That closes half of "
            "B43's cost finding - update B43 rather than only this test."
        )


def test_the_scheduling_confirmation_now_offers_no_remedy():
    """B43's second cost finding. D-1 removed the only remedy this template offered.

    *"If the time no longer works, reply here and we will move it"* was the sole route a
    client had to change a confirmed appointment, over a reply channel that did not reach
    Burkham, on a Forge with no reschedule module. Removing it made the message honest and
    left the client nowhere to go, which is why B43 records this template as one that
    should not be sent until D-2 is ruled.
    """
    html = APPROVED_TEMPLATES["scheduling_confirmation"].html
    assert "reply" not in html.lower()
    assert "we will move it" not in html.lower()
    assert not EMAIL.search(html) and "<a" not in html.lower(), (
        "scheduling_confirmation now names a remedy channel. Update B43's cost finding."
    )
    assert not any("reschedul" in b.summary.lower() for b in MODULES.values()), (
        "a reschedule module now exists; B43's remedy finding can close."
    )


def test_the_follow_up_still_asks_the_recipient_to_act_with_no_channel_to_act_on():
    """B43's third cost finding, and the sharpest of the three.

    `followup_no_engagement` is the one approved send that answers no act of the
    recipient's, and *"say so and we will leave it there"* is the recipient asking not to be
    contacted again. It never used the word "reply", so D-1 did not touch it - but the
    channel it depended on is the one D-1 removed everywhere else, and it has no link, no
    address and no record (7c writes nothing). `outbound-contact-boundary-v1`'s escalation
    trigger 4 is written for exactly this moment and there is no record to update.
    """
    html = APPROVED_TEMPLATES["followup_no_engagement"].html
    assert "say so" in html.lower(), OPEN
    assert "reply" not in html.lower()
    assert not EMAIL.search(html) and "<a" not in html.lower(), (
        "followup_no_engagement now names a channel. That is B43's sharpest cost finding "
        "closing - update B43."
    )


# ============================================ invariants that hold whatever B43 decides


def test_no_approved_body_names_an_undocumented_channel():
    """No approved body may name an address this repository cannot source.

    The marketing plan §6.5 documents exactly one Burkham address. Anything else in a body
    is invented - and inventing a channel is how three of B43's four findings came to exist
    in the first place.
    """
    for tid, html in _all().items():
        for address in EMAIL.findall(html):
            assert address.lower() in DOCUMENTED_CHANNELS, (
                f"{tid} names {address!r}, which is not documented anywhere in this "
                f"repository. The only documented Burkham channel is "
                f"{sorted(DOCUMENTED_CHANNELS)} (marketing plan §6.5)."
            )


def test_no_approved_body_carries_an_unsubstituted_merge_tag():
    """`personalizeContent` leaves an unmatched `{{tag}}` in the body verbatim, and
    `context` is optional on every send handler. So a body containing `{{date}}` mails a
    literal `{{date}}` to a client whenever the caller omits it."""
    for tid, html in _all().items():
        for tag in MERGE_TAG.findall(html):
            assert tag in ALWAYS_SUBSTITUTED, (
                f"{tid} uses a merge tag {tag!r} that is substituted only if the caller "
                f"supplies context[{tag!r}]. `context` is optional, and an unmatched tag "
                f"is delivered to the recipient verbatim. Safe tags: "
                f"{sorted(ALWAYS_SUBSTITUTED)}."
            )


@pytest.mark.parametrize("template_id", sorted(autonomous_template_ids()))
def test_every_autonomous_template_is_bound_to_exactly_one_module(template_id: str):
    """The findings above are only meaningful if each id they name is copy some module
    actually sends."""
    bound = [m for m, b in MODULES.items() if b.template_id == template_id]
    assert len(bound) == 1, f"{template_id} is bound to {bound}"
