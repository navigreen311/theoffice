"""The two refusals, in the handler, where the design condition puts them.

THE CONDITION, RESTATED SO IT IS NOT PARAPHRASED AWAY
=====================================================

`docs/plans/funnelforge-animaforge-surface-PROPOSAL.md`:

    A single `send_approved_template` module is only safe if the module itself refuses.
    One grant would cover every approved template. That is acceptable *only* when the
    handler declines, on its own, to send a template whose approval scope is not
    Village-autonomous, and any message whose categorical compliance state is not Pass.
    Not the caller's job. Not a convention. The handler's.

**A grant-level check is not this control.** A grant says an agent may call a module; it
does not say what the module then does with the arguments. Both refusals below run after
the grant has already been resolved, on every call, with no way for a caller to opt out
of them - because the caller is the party the refusal is about.

WHY THIS FILE EXISTS AT ALL, GIVEN `docs/forge-adapter.md`
=========================================================

That document says an adapter *decides nothing*, and it is right about the thing it is
describing: an adapter must not re-check the grant, the certification, the shift or the
manifest, because The Office already did and the second copy is the one nobody audits.

These two checks are a different kind. They are not a second authorization system; they
are the *only* one for these two facts, because The Office's tables hold neither. There
is no column anywhere in The Office recording that a marketing template may be sent
unattended, and none recording a message's §3.3 compliance state. A control that exists
in exactly one place is not a duplicate of anything.

Said the other way: if these moved to the grant, the module would have to accept a
template id as an argument, and then the grant would be authorizing a parameter it never
sees. That is the design the proposal refused.

FAIL CLOSED, AND WHY THAT IS THE INTERESTING HALF
=================================================

§3.3 says the categorical state - Pass / Pass with Findings / Needs Review / Fail -
*"determines the routing"*. FunnelForge holds no such state, so it arrives in the call
payload, from The Office side, which means it can also **not** arrive.

An absent state is refused exactly as hard as `fail`. This is the half that gets written
wrong: a `state != "pass"` check reads as complete and passes `None` straight through in
most languages people actually write, and a missing key is the most likely way a caller
gets this wrong. So the check is written as `state == PASS`, once, and everything else -
absent, empty, misspelled, a new value §3.3 grows later - is a refusal with a reason.
"""

from __future__ import annotations

from adapters.funnelforge.templates import APPROVED_TEMPLATES, autonomous_template_ids

#: §3.3's four categorical states, verbatim, lowercased for comparison. The list is here
#: so a reader can see that three of the four are refusals; the code never enumerates it.
COMPLIANCE_STATES = ("pass", "pass_with_findings", "needs_review", "fail")

#: The one that permits an unattended send. Not `in {...}` of the acceptable ones: a set
#: of acceptable values grows by accident, and this one must grow by decision.
PASS = "pass"


class Refused(Exception):  # noqa: N818 - see below
    """The handler declined. Carries the machine code and the reason a human needs.

    A refusal is an answer, not a crash: the adapter turns it into a 422 with both
    fields, so the ledger row and the Forge's own log record *why* rather than a bare
    status. `docs/forge-adapter.md` trap #9 is the same lesson from the other side - an
    unconfigured adapter that answers like a refused credential loses the distinction
    that matters.

    N818 is suppressed rather than obeyed, for the reason `pyproject.toml` already gives
    three times - `broker/errors.py`, `broker/shifts.py`, `broker/escalation.py`: this
    taxonomy is named for the domain event, so `raise Refused(...)` reads as what
    happened and `RefusedError` would be noise on a class whose only job is to be caught
    by name. Those three are per-file-ignores; this is a line-level `noqa` because
    `pyproject.toml` is a shared config file and out of P-13's scope.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def refuse_unless_autonomous(template_id: str) -> None:
    """REFUSAL ONE: the template's approval scope must be Village-autonomous.

    Three outcomes, and the middle one is the whole point:

        unknown id      refused. Nothing was approved under that name.
        human_approve   refused. §4.5 routes it through a human and this is not one.
        autonomous      permitted.

    The middle case is reachable in exactly one way: somebody binds a module to a
    template that is not autonomous. Module-gating is supposed to prevent that by
    construction, and this refusal is what makes "supposed to" checkable - the module
    list is the outer gate and this is the inner one, and a design that has only the
    outer one is a design whose gate is a naming convention.
    """
    template = APPROVED_TEMPLATES.get(template_id)
    if template is None:
        raise Refused(
            "TEMPLATE_NOT_APPROVED",
            f"{template_id!r} is not on the approved list. The approved list is "
            "adapters/funnelforge/templates.py, and additions require both founders "
            "(§4.5).",
        )
    if template.approval_scope != "village_autonomous":
        raise Refused(
            "TEMPLATE_NOT_AUTONOMOUS",
            f"{template_id!r} is approved at {template.approval_scope!r}, not "
            "village_autonomous. §4.5 routes it through Deliverable Approval Workflow "
            "(Console module 3.4), which is not connected to the bridge. An agent may "
            "not send it and no module may bind it.",
        )


def refuse_unless_pass(compliance_state: object) -> None:
    """REFUSAL TWO: the message's categorical compliance state must be Pass.

    Everything that is not the string `pass` is refused, including `None`. See the
    module docstring: absent is refused as hard as `fail`, because absent is how this
    goes wrong in practice.
    """
    if compliance_state == PASS:
        return
    if compliance_state is None:
        raise Refused(
            "COMPLIANCE_STATE_ABSENT",
            "no compliance_state was supplied. §3.3's categorical state determines the "
            "routing, and FunnelForge holds no such state, so the caller must state it. "
            "An absent state is refused exactly as a failing one is: this handler will "
            "not infer Pass from silence.",
        )
    raise Refused(
        "COMPLIANCE_STATE_NOT_PASS",
        f"compliance_state is {compliance_state!r}. Only {PASS!r} permits an unattended "
        f"send; §3.3's other states ({', '.join(s for s in COMPLIANCE_STATES if s != PASS)}) "
        "route to a human.",
    )


def assert_sendable(template_id: str, compliance_state: object) -> None:
    """Both refusals, in the order a reader would ask them.

    Template first: an unapproved template is refused whatever the compliance state, and
    reporting the template problem is more useful than reporting a state problem on a
    message that was never going to be sent.
    """
    refuse_unless_autonomous(template_id)
    refuse_unless_pass(compliance_state)


def assert_bindable(template_id: str) -> None:
    """Import-time guard: a module may only be bound to an autonomous template.

    Runs when `modules.py` is imported, so binding a send module to
    `engagement_letter_cover` fails the build rather than failing the first call. The
    per-call refusal above still stands; this one exists so the mistake is caught by
    anything that imports the adapter, including `ruff`-clean CI that never makes a call.
    """
    if template_id not in autonomous_template_ids():
        raise AssertionError(
            f"module bound to {template_id!r}, which is not village_autonomous. "
            "Module-gating means the module list IS the approved list; binding a "
            "non-autonomous template would make the module list say something false."
        )
