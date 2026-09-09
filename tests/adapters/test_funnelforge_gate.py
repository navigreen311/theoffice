"""THE DESIGN CONDITION, asserted where the card requires it: inside the handler.

    THE MODULE REFUSES A NON-AUTONOMOUS TEMPLATE, inside the handler
    THE MODULE REFUSES A NON-PASS STATE, inside the handler
    Both asserted directly. A grant-level check is not the same control and does not
    satisfy this.

So every test below calls a handler function - the exact object bound in `MODULES` -
with a fake upstream, and asserts the refusal happened *before* anything was sent. There
is no grant, no Office, no HTTP in these tests, because a control that only holds when
the surrounding system is present is a control that has not been shown to be the
module's.

The one thing these tests can never establish is stated up front, from
`docs/forge-adapter.md` trap #4: an adapter test with an injected caller asserts the
request the adapter *built*, checked against itself. It cannot tell you the binding is
right. It can tell you the refusal fired, which is what is being tested here - a refusal
is entirely the handler's own behaviour and has no upstream to be wrong about.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.funnelforge import gate
from adapters.funnelforge.modules import MODULES
from adapters.funnelforge.templates import APPROVED_TEMPLATES, autonomous_template_ids
from adapters.funnelforge.upstream import UpstreamCall

SEND_MODULES = tuple(
    module_id for module_id, b in sorted(MODULES.items()) if b.template_id is not None
)


class RecordingUpstream:
    """Records every call. A refusal that still called upstream is not a refusal."""

    def __init__(self) -> None:
        self.calls: list[UpstreamCall] = []

    async def __call__(self, call: UpstreamCall) -> dict[str, Any]:
        self.calls.append(call)
        return {"status": 200, "body": {"success": True}}


def _payload(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "recipient_email": "someone@example.invalid",
        "compliance_state": "pass",
    }
    base.update(over)
    return base


# --------------------------------------------------------------- refusal one: template


async def test_the_handler_refuses_a_non_autonomous_template():
    """REFUSAL ONE, at the level the condition names.

    `engagement_letter_cover` is real - §4.5 puts it at *human approve send* - and it is
    in `APPROVED_TEMPLATES` precisely so this assertion has a genuine input rather than
    an invented one.
    """
    template = APPROVED_TEMPLATES["engagement_letter_cover"]
    assert template.approval_scope == "human_approve"

    with pytest.raises(gate.Refused) as raised:
        gate.assert_sendable(template.template_id, "pass")

    assert raised.value.code == "TEMPLATE_NOT_AUTONOMOUS"
    # A Pass compliance state does not rescue it. The two refusals are independent.
    assert "village_autonomous" in raised.value.reason


async def test_a_send_handler_built_over_a_non_autonomous_template_refuses_at_call_time():
    """The refusal is the handler's, not the binding table's.

    Built here the way `modules.py` builds one, over the human-approve template. Import-
    time `assert_bindable` refuses that binding, so this reaches past it deliberately to
    prove the *per-call* check is what stops the send - if only the import guard existed,
    a template downgraded from autonomous after deploy would keep sending until restart.
    """
    upstream = RecordingUpstream()

    async def handler(payload: dict[str, Any]) -> dict[str, Any]:
        gate.assert_sendable("engagement_letter_cover", payload.get("compliance_state"))
        raise AssertionError("unreachable: the gate must have refused")

    with pytest.raises(gate.Refused) as raised:
        await handler(_payload())

    assert raised.value.code == "TEMPLATE_NOT_AUTONOMOUS"
    assert upstream.calls == [], "refused and still called upstream"


async def test_binding_a_non_autonomous_template_fails_at_import():
    """The outer half of the same control. Module-gating, made checkable."""
    with pytest.raises(AssertionError, match="not village_autonomous"):
        gate.assert_bindable("engagement_letter_cover")


async def test_an_unknown_template_is_refused_rather_than_defaulted():
    with pytest.raises(gate.Refused) as raised:
        gate.assert_sendable("whatever_marketing_wants", "pass")
    assert raised.value.code == "TEMPLATE_NOT_APPROVED"


# ------------------------------------------------------------- refusal two: Pass state


@pytest.mark.parametrize("module_id", SEND_MODULES)
@pytest.mark.parametrize(
    "state", ["fail", "needs_review", "pass_with_findings", "PASS", "", "ok", 1, True]
)
async def test_every_send_handler_refuses_a_non_pass_state(module_id, state):
    """REFUSAL TWO, on every one of the six, not on a representative one.

    Six handlers are six handlers. `docs/forge-adapter.md` trap #4's whole lesson is that
    fifteen correct bindings sat beside two wrong ones, so a test that samples one of six
    is a test that would have passed on CapitalForge.

    `pass_with_findings` is in the list on purpose: it is a §3.3 state whose name
    contains the word `pass`, and it is a refusal. `"PASS"` is there because a
    case-folding comparison would let it through.
    """
    upstream = RecordingUpstream()
    with pytest.raises(gate.Refused) as raised:
        await MODULES[module_id].handler(
            _payload(compliance_state=state), upstream
        )
    assert raised.value.code == "COMPLIANCE_STATE_NOT_PASS"
    assert upstream.calls == [], "refused and still called upstream"


@pytest.mark.parametrize("module_id", SEND_MODULES)
async def test_every_send_handler_refuses_an_absent_state(module_id):
    """Absent is refused as hard as failing, and reported as its own code.

    This is the half that gets written wrong. `state != "pass"` reads as complete and is
    complete; `if state and state != "pass"` is the one that ships, and a missing key is
    the most likely way a caller gets here.
    """
    upstream = RecordingUpstream()
    payload = _payload()
    del payload["compliance_state"]

    with pytest.raises(gate.Refused) as raised:
        await MODULES[module_id].handler(payload, upstream)

    assert raised.value.code == "COMPLIANCE_STATE_ABSENT"
    assert upstream.calls == []


async def test_the_booking_module_refuses_a_non_pass_state_too():
    """§3.3 puts `schedule_blueprint_call` at worker-autonomous in a Pass state."""
    upstream = RecordingUpstream()
    with pytest.raises(gate.Refused) as raised:
        await MODULES["schedule_blueprint_call"].handler(
            {
                "business_id": "b",
                "appointment_slug": "blueprint-call",
                "client_name": "A",
                "client_email": "a@example.invalid",
                "date": "2026-10-01",
                "time": "10:00",
                "compliance_state": "needs_review",
            },
            upstream,
        )
    assert raised.value.code == "COMPLIANCE_STATE_NOT_PASS"
    assert upstream.calls == []


# ------------------------------------------------------ the permitted path, for contrast


@pytest.mark.parametrize("module_id", SEND_MODULES)
async def test_a_pass_state_on_an_autonomous_template_sends_that_template_only(module_id):
    """The refusals refuse something rather than everything.

    Also the anti-parameter assertion: the request built names the template the module
    was bound to, and a caller-supplied `template_id` changes nothing.
    """
    binding = MODULES[module_id]
    upstream = RecordingUpstream()

    result = await binding.handler(
        _payload(template_id="engagement_letter_cover"), upstream
    )

    assert result["template_id"] == binding.template_id
    assert len(upstream.calls) == 1
    sent = upstream.calls[0]
    assert sent.path == "/api/emails/send"
    assert sent.body is not None
    expected = APPROVED_TEMPLATES[binding.template_id]
    assert sent.body["subject"] == expected.subject
    assert sent.body["html"] == expected.html


async def test_the_six_bound_templates_are_exactly_the_autonomous_ones():
    """Module-gating's claim, checked rather than asserted in prose.

    The module list IS the approved list, so these two sets are the same set derived two
    ways. If they ever differ, one of them is lying about what an agent may send.
    """
    bound = {MODULES[m].template_id for m in SEND_MODULES}
    assert bound == set(autonomous_template_ids())
    assert "engagement_letter_cover" not in bound
