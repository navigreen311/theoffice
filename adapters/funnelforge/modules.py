"""The dispatch map. Nine modules, and the map is the naming authority.

`docs/forge-adapter.md`, *"The adapter's keys are the spelling of record"*: a module id
is the address, because `broker/executor.py` builds the URL as `{base_url}/{module_id}`.
Three things resolve against these keys - a Pack's `modules_expected` (V32),
`forge_module_registry` (`scripts/verify_forge_modules.py`), and
`broker/module_exclusions.py`. A second spelling does not quietly work; it fails to
resolve and V32 says so.

WHAT IS DERIVED AND WHAT IS DECLARED
====================================

`module_id` is derived: a name is in `sorted(MODULES)` if and only if a handler is bound
to it. You cannot add the name without adding the function.

`is_mutating` and `idempotency_support` are **declared here, at the binding site**. They
are still somebody's word - better-placed word than a registry row, because they travel
with the handler, but word. Say which is which when reporting them.

THE SIX SEND MODULES ARE SIX MODULES ON PURPOSE
===============================================

They call one upstream route with one difference between them: the approved copy. A
reader will want to collapse them into one module taking a template id. **That is the
design the proposal refused**, and the reason is the whole architecture: one module
taking a template id means one grant covering every template, and the grant then
authorizes a parameter it never sees. The module list is the approved list. Six approved
autonomous templates, six modules; the seventh template in `templates.py` is
`human_approve` and has no module, which is what module-gating looks like when it works.

The price of that is six steps per new template and two of them are not automatable.
It is written down in `docs/plans/funnelforge-binding-RECORD.md` rather than discovered
by whoever adds template number seven.

V31 REFUSES SEVEN OF THESE NINE AT THE ONLY TIER THAT CALLS
===========================================================

Read this before wondering why the binding does not produce calls.

Seven modules below are `is_mutating=True, idempotency_support="at_most_once"`. V31
(`generators/validator.py`) refuses `auto_execute` over exactly that shape, and
`auto_execute` is the only tier that reaches a Forge at all - step 7 of the client
library turns anything below it into a proposal and makes no HTTP call.

So: **seven of the nine cannot today be granted at a tier that makes a call.** That is
not a defect in this binding and it must not be fixed by softening a declaration. An
email leaves the system and reaches a person; a retry sends a second one, and `EmailQueue`
has no idempotency key that would recognise a repeat. `at_most_once` is the truth, V31 is
correct to refuse it, and the finding belongs upstream in FunnelForge - an idempotency
key on the send path is what would change it. Sized and recorded in the binding record.

`capture_contact` (natural) and `read_funnel_analytics` (non-mutating) are the two V31
permits.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from adapters.funnelforge import upstream
from adapters.funnelforge.gate import Refused, assert_bindable, assert_sendable
from adapters.funnelforge.templates import APPROVED_TEMPLATES
from adapters.funnelforge.upstream import Upstream, UpstreamCall

Handler = Callable[[dict[str, Any], Upstream], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class Binding:
    """A handler plus the two shape fields the manifest states for it."""

    handler: Handler
    is_mutating: bool
    idempotency_support: str
    summary: str
    upstream_route: str
    template_id: str | None = None
    """The approved template this module sends, for the six that send one.

    Present so `/_modules` can state it and so a reader of the registry can see which
    module carries which template without opening this file. `None` for the three acts
    that are not sends.
    """


def _require(payload: dict[str, Any], *names: str) -> list[Any]:
    """Refuse a missing argument by name rather than raising KeyError into a 500."""
    missing = [n for n in names if payload.get(n) in (None, "")]
    if missing:
        raise Refused(
            "ARGUMENT_MISSING",
            f"required argument(s) absent: {', '.join(missing)}",
        )
    return [payload[n] for n in names]


def _send_approved(template_id: str) -> Handler:
    """Build the handler for one approved template.

    THE TEMPLATE ID IS CLOSED OVER, NOT READ FROM THE PAYLOAD. There is no code path by
    which a caller reaches a different template: `payload` is never consulted for it, so
    an agent that supplies `template_id` in the body is supplying a field nothing reads.

    Both refusals still run on every call. That is not belt-and-braces on a closed-over
    constant - `assert_sendable` re-reads the *scope* of that template from
    `APPROVED_TEMPLATES` at call time, so a template downgraded from autonomous to
    human-approve stops being sendable at the next call rather than at the next deploy.
    """
    assert_bindable(template_id)

    async def handler(payload: dict[str, Any], call: Upstream) -> dict[str, Any]:
        # THE DESIGN CONDITION. Inside the handler, before anything leaves, on every
        # call, with no caller-supplied way past it.
        assert_sendable(template_id, payload.get("compliance_state"))

        (recipient,) = _require(payload, "recipient_email")
        template = APPROVED_TEMPLATES[template_id]
        context = payload.get("context") or {}
        if not isinstance(context, dict):
            raise Refused("ARGUMENT_INVALID", "context must be an object")

        answer = await call(
            UpstreamCall(
                method="POST",
                path=upstream.EMAILS_SEND,
                body={
                    "to": {
                        "email": recipient,
                        "firstName": payload.get("recipient_first_name"),
                        "data": context,
                    },
                    "subject": template.subject,
                    "html": template.html,
                    "tags": ["the-office", f"template:{template_id}"],
                },
            )
        )
        return {
            "template_id": template_id,
            "template_name": template.name,
            "sent": True,
            "upstream": answer,
        }

    return handler


async def _schedule_blueprint_call(
    payload: dict[str, Any], call: Upstream
) -> dict[str, Any]:
    """§3.3's Blueprint call booking. A booking, not an email.

    Worker-autonomous in a Pass state, so it carries the compliance refusal even though
    it sends no template. The template refusal does not apply: there is no template.
    Writing one anyway - against a fabricated id - would be a control that tests nothing.
    """
    from adapters.funnelforge.gate import refuse_unless_pass

    refuse_unless_pass(payload.get("compliance_state"))
    business_id, slug, name, email, date, time = _require(
        payload,
        "business_id",
        "appointment_slug",
        "client_name",
        "client_email",
        "date",
        "time",
    )
    answer = await call(
        UpstreamCall(
            method="POST",
            path=upstream.SCHEDULING_BOOK.format(business_id=business_id, slug=slug),
            body={
                "clientName": name,
                "clientEmail": email,
                "clientPhone": payload.get("client_phone"),
                "date": date,
                "time": time,
                "notes": payload.get("notes"),
            },
        )
    )
    return {"booked": True, "upstream": answer}


async def _capture_contact(payload: dict[str, Any], call: Upstream) -> dict[str, Any]:
    """§6.2's newsletter signup / gated download. The named-contact PII FunnelForge holds.

    No compliance refusal: §3.3's state governs what is *sent to* a person, and this
    records that a person asked to hear from us. Refusing a capture on a compliance state
    would drop the record of a request while the request still happened, which is worse
    than holding it.

    `isNew` is deliberately not returned - see `upstream.py`, the field is derived from
    whether a funnel id was supplied and does not mean what it says.
    """
    business_id, email = _require(payload, "business_id", "email")
    answer = await call(
        UpstreamCall(
            method="POST",
            path=upstream.LEADS_CAPTURE,
            body={
                "businessId": business_id,
                "email": email,
                "firstName": payload.get("first_name"),
                "lastName": payload.get("last_name"),
                "phone": payload.get("phone"),
                "source": payload.get("source") or "the-office",
                "tags": payload.get("tags") or [],
            },
        )
    )
    return {"captured": True, "upstream": answer}


async def _read_funnel_analytics(
    payload: dict[str, Any], call: Upstream
) -> dict[str, Any]:
    """§6.2's anonymous browsing and pixel data, aggregated. The only read of the nine.

    §6.3 caps this permanently: FunnelForge holds no credit data, no Plaid data, no
    financial statements, nothing FCRA-regulated, and *"cannot query Console for credit
    data to segment marketing sequences."* So no FunnelForge module will ever read
    underwriting data - that bounds this surface for good, not just for V1.
    """
    query = {}
    for key in ("start_date", "end_date"):
        value = payload.get(key)
        if value:
            query[key.replace("_", "")] = str(value)
    answer = await call(
        UpstreamCall(
            method="GET", path=upstream.ANALYTICS_DASHBOARD, query=query or None
        )
    )
    return {"analytics": answer}


#: THE DISPATCH MAP. `sorted(MODULES)` is the manifest; never a literal list beside it.
MODULES: dict[str, Binding] = {
    "send_intake_acknowledgment": Binding(
        handler=_send_approved("intake_acknowledgment"),
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Send the Decline-Flow Handoff intake acknowledgment.",
        upstream_route=f"POST {upstream.EMAILS_SEND}",
        template_id="intake_acknowledgment",
    ),
    "send_scheduling_confirmation": Binding(
        handler=_send_approved("scheduling_confirmation"),
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Send the Blueprint scheduling confirmation.",
        upstream_route=f"POST {upstream.EMAILS_SEND}",
        template_id="scheduling_confirmation",
    ),
    "send_deliverable_cover": Binding(
        handler=_send_approved("deliverable_cover"),
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Send the Blueprint deliverable cover email.",
        upstream_route=f"POST {upstream.EMAILS_SEND}",
        template_id="deliverable_cover",
    ),
    "send_followup_no_engagement": Binding(
        handler=_send_approved("followup_no_engagement"),
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Send the post-Blueprint no-engagement follow-up.",
        upstream_route=f"POST {upstream.EMAILS_SEND}",
        template_id="followup_no_engagement",
    ),
    "send_brief_cover": Binding(
        handler=_send_approved("brief_cover"),
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Send the Capital Command Brief cover email.",
        upstream_route=f"POST {upstream.EMAILS_SEND}",
        template_id="brief_cover",
    ),
    "distribute_referrer_briefing": Binding(
        handler=_send_approved("referrer_briefing"),
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Distribute the referrer quarterly briefing.",
        upstream_route=f"POST {upstream.EMAILS_SEND}",
        template_id="referrer_briefing",
    ),
    "schedule_blueprint_call": Binding(
        handler=_schedule_blueprint_call,
        is_mutating=True,
        idempotency_support="at_most_once",
        summary="Book a Blueprint call against a public appointment type.",
        upstream_route=f"POST {upstream.SCHEDULING_BOOK}",
    ),
    "capture_contact": Binding(
        handler=_capture_contact,
        # find-then-update-or-create keyed on (email, businessId) - read out of
        # `apps/api/src/modules/leads/routes.ts`, not out of the route's name. A retry
        # updates the same lead, so `natural` rather than `at_most_once`.
        is_mutating=True,
        idempotency_support="natural",
        summary="Record a newsletter signup or gated-download contact.",
        upstream_route=f"POST {upstream.LEADS_CAPTURE}",
    ),
    "read_funnel_analytics": Binding(
        handler=_read_funnel_analytics,
        is_mutating=False,
        idempotency_support="natural",
        summary="Read aggregated funnel analytics. No named contacts.",
        upstream_route=f"GET {upstream.ANALYTICS_DASHBOARD}",
    ),
}

#: `docs/forge-adapter.md`: the `_` prefix belongs to the adapter's own endpoints, and a
#: module named `_modules` would shadow the manifest. Asserted beside the dict rather
#: than written down in a document only.
assert not any(name.startswith("_") for name in MODULES), (
    "module ids must not start with '_': that prefix is the adapter's own, and a module "
    "named _modules would shadow the manifest"
)


def manifest() -> dict[str, Any]:
    """What `GET /_modules` answers. Derived from the dispatch map, never a literal.

    `test_manifest_is_derived_from_the_dispatch_map` fails the build if a literal list
    appears beside the dict. The reason is in `docs/forge-adapter.md`: this is the only
    answer in the whole path that is not a declaration, and a list maintained alongside
    throws that away while keeping the authority of having come from the Forge.

    `modules` is a list of OBJECTS, not names. `broker/forge_modules._parse_modules`
    accepts both, and answering with names leaves `shapes = None` - which makes
    `scripts/verify_forge_modules.py` print *"states no module shapes, so is_mutating and
    idempotency_support stay as written and unverified"* and leaves the registry copy
    that V31 spends unchecked. The two extra keys per entry are ignored by that parser
    and read by humans; CapitalForge's manifest states extras the same way.
    """
    return {
        "forge": "funnelforge",
        "modules": [
            {
                "module_id": module_id,
                "is_mutating": binding.is_mutating,
                "idempotency_support": binding.idempotency_support,
                "summary": binding.summary,
                "upstream_route": binding.upstream_route,
                "template_id": binding.template_id,
            }
            for module_id, binding in sorted(MODULES.items())
        ],
    }
