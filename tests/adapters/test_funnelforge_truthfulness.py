"""B42 - a handler answers what came back, never that it ran.

`adapters/funnelforge/modules.py` returned `sent: True`, `booked: True` and `captured: True`
as literals, and `app.py` wraps a handler's return in a 200 without consulting it. Against the
FunnelForge running on 9 September 2026 - `RESEND_API_KEY` present and empty, so
`POST /api/emails/send` answers `500 SEND_FAILED` - the adapter answered:

    {"template_id": "intake_acknowledgment", "sent": true,
     "upstream": {"status": 500, "body": {"success": false, ...}}}

B33 Finding 1 raised it, and shared rule 1 of the nine manuals is an instruction to agents to
disregard the flag. **This file is the assertion that there is no longer a flag to disregard.**

WHAT THESE TESTS CAN AND CANNOT SHOW
====================================

`docs/forge-adapter.md` trap #4 stands: a test with an injected upstream asserts the adapter
against itself and cannot tell you the binding reaches the thing the manual describes. It does
not need to here. The claim under test is entirely the handler's own - *given* an answer, what
does the handler say about it - so the stub is the whole input and there is no upstream to be
wrong about. That is the same ground `test_funnelforge_gate.py` stands on for the refusals.

THE 200 CASE IS ASSERTED AS HARD AS THE 500 CASE, AND THAT IS THE POINT
======================================================================

A flag derived from `upstream.status` would pass a 500-only test and would still be the
adapter collapsing a status, FunnelForge's envelope `success` field and the domain outcome
into one bit that reads as a delivery. The decision to delete rather than derive, with its
reasons, is in `modules.py` and in B42. Changing it means changing these tests on purpose,
rather than discovering afterwards that a word came back.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.funnelforge.modules import MODULES, OUTCOME_CLAIM_KEYS
from adapters.funnelforge.upstream import UpstreamCall

#: The body FunnelForge returns today for every one of the six approved sends. Copied from
#: the measurement in B33 Finding 2 rather than invented, so the regression below is the
#: response that was actually observed.
SEND_FAILED: dict[str, Any] = {
    "success": False,
    "error": {
        "code": "SEND_FAILED",
        "message": (
            "No email provider configured. Set RESEND_API_KEY, SENDGRID_API_KEY, "
            "AWS_SES_*, or SMTP_* environment variables."
        ),
    },
}


class StubUpstream:
    """Answers one canned envelope, in the shape `HttpUpstream.__call__` returns."""

    def __init__(self, answer: dict[str, Any]) -> None:
        self.answer = answer
        self.calls: list[UpstreamCall] = []

    async def __call__(self, call: UpstreamCall) -> dict[str, Any]:
        self.calls.append(call)
        return self.answer


#: One valid payload per bound module, so every handler is exercised rather than a
#: representative one. Trap #4's lesson is that fifteen correct bindings sat beside two wrong
#: ones; here three of three handlers carried the defect.
PAYLOADS: dict[str, dict[str, Any]] = {
    "send_intake_acknowledgment": {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    },
    "send_scheduling_confirmation": {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    },
    "send_deliverable_cover": {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    },
    "send_followup_no_engagement": {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    },
    "send_brief_cover": {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    },
    "distribute_referrer_briefing": {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    },
    "schedule_blueprint_call": {
        "business_id": "office-probe",
        "appointment_slug": "blueprint-call",
        "client_name": "A Client",
        "client_email": "client@example.invalid",
        "date": "2026-10-01",
        "time": "10:00",
        "compliance_state": "pass",
    },
    "capture_contact": {
        "business_id": "office-probe",
        "email": "contact@example.invalid",
    },
    "read_funnel_analytics": {},
}


def test_every_bound_module_has_a_payload_here() -> None:
    """A parametrised test over a partial list quietly stops covering.

    `sorted(MODULES)` drives the assertions below, so a tenth module with no payload here
    would raise `KeyError` inside the assertion it was meant to satisfy, which reads as that
    assertion breaking. This one says which list is short.
    """
    assert set(PAYLOADS) == set(MODULES), sorted(set(MODULES) ^ set(PAYLOADS))


def test_the_three_literals_the_defect_was_are_named_in_the_set() -> None:
    """The guard is only a guard if it names the thing that actually happened."""
    assert {"sent", "booked", "captured"} <= OUTCOME_CLAIM_KEYS


@pytest.mark.parametrize("module_id", sorted(MODULES))
async def test_no_handler_claims_an_outcome_over_a_500(module_id: str) -> None:
    """The live defect. Every handler, not a representative one."""
    answer = {"status": 500, "body": SEND_FAILED}
    upstream = StubUpstream(answer)

    result = await MODULES[module_id].handler(dict(PAYLOADS[module_id]), upstream)

    claimed = sorted(OUTCOME_CLAIM_KEYS & set(result))
    assert not claimed, (
        f"{module_id} answered {claimed} beside an upstream 500. That is the adapter "
        "reporting its own execution as the outcome of the thing it executed - B33 "
        "Finding 1, fixed in B42. The evidence is at upstream.status; do not restate it "
        "as a word."
    )
    assert any(value is answer for value in result.values()), (
        f"{module_id} did not pass the upstream envelope back untouched. Deleting the flag "
        "is only safe because the status and body travel whole in its place."
    )


@pytest.mark.parametrize("module_id", sorted(MODULES))
async def test_no_handler_claims_an_outcome_over_a_200_either(module_id: str) -> None:
    """The half that a status-derived flag would still pass.

    A 2xx from FunnelForge means its API accepted the request. It does not mean an email
    reached a person, an appointment exists, or a lead row was written - and `sent`, `booked`
    and `captured` are exactly those three sentences. The word cannot be made true by a
    function of the status, so the field is the status.
    """
    answer = {"status": 200, "body": {"success": True, "data": {"id": "whatever"}}}
    upstream = StubUpstream(answer)

    result = await MODULES[module_id].handler(dict(PAYLOADS[module_id]), upstream)

    claimed = sorted(OUTCOME_CLAIM_KEYS & set(result))
    assert not claimed, (
        f"{module_id} answered {claimed} beside an upstream 200. A flag that is true only "
        "when the upstream succeeded is still the adapter deciding, and it carries less "
        "than upstream.status already carries in the same object. See B42 for why this is "
        "deletion rather than derivation."
    )
    assert any(value is answer for value in result.values())


async def test_the_exact_shape_b33_recorded_no_longer_occurs() -> None:
    """The regression, named after the defect so a reader arrives here from the blocker."""
    upstream = StubUpstream({"status": 500, "body": SEND_FAILED})

    result = await MODULES["send_intake_acknowledgment"].handler(
        dict(PAYLOADS["send_intake_acknowledgment"]), upstream
    )

    assert "sent" not in result
    assert result["upstream"]["status"] == 500
    assert result["upstream"]["body"]["error"]["code"] == "SEND_FAILED"


@pytest.mark.parametrize(
    "module_id",
    sorted(m for m, b in MODULES.items() if b.template_id is not None),
)
async def test_a_send_still_names_the_approved_copy_it_used(module_id: str) -> None:
    """Deleting the outcome claim does not delete the facts about the handler's own act.

    `template_id` and `template_name` say which approved copy left this adapter. That is a
    statement about what the handler did, which it observed, and it is the distinction
    `OUTCOME_CLAIM_KEYS` draws - not "return less", but "return nothing you did not see".
    """
    binding = MODULES[module_id]
    upstream = StubUpstream({"status": 500, "body": SEND_FAILED})

    result = await binding.handler(dict(PAYLOADS[module_id]), upstream)

    assert result["template_id"] == binding.template_id
    assert result["template_name"]
    assert len(upstream.calls) == 1
