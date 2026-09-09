"""The four FunnelForge operations these nine modules reach, and how they answered.

EVERY ROUTE BELOW WAS CALLED AND ITS RESPONSE BODY READ
=======================================================

`docs/forge-adapter.md` trap #4: *"Call every operation of every module against a running
Forge before you register a single row... `_modules` tells you a handler is bound; only a
real call tells you the binding reaches the thing the manual describes."* Two of
CapitalForge's seventeen operations were wrong while fifteen beside them were right, and
both were found this way.

Probed 9 September 2026 from inside `ff-docker_funnelforge-network`, because FunnelForge
publishes no host ports (see `docs/plans/funnelforge-binding-RECORD.md`). Bodies verbatim:

    POST /api/leads/capture
      {"businessId":"office-probe-nonexistent","email":"probe@example.invalid"}
      500 {"statusCode":500,"code":"P2003","error":"Internal Server Error",
           "message":"Invalid `prisma.lead.create()` invocation: Foreign key constraint
           violated: `Lead_businessId_fkey (index)`"}
      -> route, schema and handler all real; it reached the database and failed on a
         business id that does not exist. Short of a real id this is the strongest
         evidence available that the binding reaches the thing.

    POST /api/analytics/track
      {"funnelId":"office-probe-nonexistent","visitorId":"office-probe",
       "type":"PAGE_VIEW"}
      500 {"statusCode":500,"code":"P2003",... "AnalyticsEvent_funnelId_fkey (index)"}
      -> same shape. Reached the database.

    POST /api/scheduling/public/office-probe/blueprint-call/book
      {"clientName":"Probe","clientEmail":"probe@example.invalid",
       "date":"2026-10-01","time":"10:00"}
      404 {"success":false,"error":{"message":"Booking type not found or inactive"}}
      -> a DOMAIN 404, not a routing 404. The handler ran and looked for the
         appointment type. Compare the routing 404 below, which has a different shape.

    POST /api/emails/send            401 {"statusCode":401,
    GET  /api/analytics/dashboard         "code":"FST_JWT_NO_AUTHORIZATION_IN_HEADER",
                                          "error":"Unauthorized","message":"No
                                          Authorization was found in request.headers"}
      -> both authenticated. Bearer JWT; see AUTH below.

    POST /api/emails/templates
      404 {"message":"Route POST:/api/emails/templates not found","error":"Not Found",
           "statusCode":404}
      -> a ROUTING 404. `packages/sdk-js/src/resources/emails.ts` declares template CRUD
         and the API implements none of it. This is why `templates.py` holds the copy.

    GET  /docs/json                  200, zero bytes.
      -> Swagger is registered (`apps/api/src/index.ts`, `swaggerUi` at `/docs`) and the
         JSON document is empty. A 200 with an empty body is not a route list; the routes
         in this file were read out of `apps/api/src/modules/*/routes.ts` and then called.
         Recorded because "the API has OpenAPI" would have been true and useless.

AUTH: THERE IS NO TENANT CREDENTIAL
===================================

`server.decorate('authenticate', ...)` in `apps/api/src/index.ts` is the only auth
FunnelForge has on these routes, and it verifies a **user JWT**. There is no API-key
path: `x-api-key` and `apiKey` appear nowhere in the API's middleware or plugins.

So `forge_registry.auth_model` is `bearer`, and the credential The Office brokers is a
user's token rather than a tenant's. That is a real difference from CapitalForge and it
is not this adapter's to fix - it is recorded in the binding record as an open item,
because a brokered *user* credential means every agent's call is attributable to one
FunnelForge user account and FunnelForge's own audit trail cannot tell agents apart.
The Office ledger remains the per-agent record, which is what `broker/executor.py`
already says about `credential_mode: brokered`.

TWO SIDE EFFECTS THE MODULE LIST DOES NOT GATE
==============================================

Both found by reading the handlers, which is the half `_modules` and the two verifiers
can never see.

1. `POST /api/leads/capture` on a NEW lead auto-enrols it in the business's active
   `WELCOME` email sequence (`apps/api/src/modules/leads/routes.ts`). So `capture_contact`
   can cause email to be sent, through a path no module gates and no approved-template
   refusal touches. Module-gating stops an agent *naming* a send; it does not stop a
   non-send module *triggering* one.

2. That same route returns `isNew: !body.funnelId` - the flag is derived from whether a
   funnel id was supplied, not from whether the lead was new. A caller cannot learn from
   the response whether it created or updated. `capture_contact` therefore does not
   report it either, rather than passing on a field that does not mean what it says.

Neither is a defect in the binding and neither is The Office's to fix. Both are in the
binding record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class UpstreamCall:
    """One HTTP call to FunnelForge, as the handler built it.

    The handlers return these rather than performing them, and the app performs them.
    That split is not decoration: `docs/forge-adapter.md` trap #4 records that the
    CapitalForge adapter's unit tests asserted the request the adapter *built* and
    therefore could only ever confirm the assumption they were written from. Separating
    build from perform does not fix that - nothing in a unit test can - but it makes the
    built request an inspectable value, so the conformance evidence in this module's
    docstring is about calls of exactly this shape rather than about a different code
    path that happens to live nearby.
    """

    method: str
    path: str
    body: dict[str, Any] | None = None
    query: dict[str, str] | None = None


class Upstream(Protocol):
    """Whatever performs an `UpstreamCall`. The app supplies a real one."""

    async def __call__(self, call: UpstreamCall) -> dict[str, Any]:
        ...


#: `apps/api/src/index.ts`: `server.register(emailRoutes, { prefix: '/api/emails' })`.
#: The one send path that exists. Body per `sendEmailSchema`: `to.email` required,
#: `subject` and `html` required and non-empty, `from`/`text`/`tags`/`leadId` optional.
EMAILS_SEND = "/api/emails/send"

#: `server.register(schedulingRoutes, { prefix: '/api/scheduling' })`, public booking
#: route. Body requires exactly `clientName`, `clientEmail`, `date`, `time`;
#: `clientPhone` and `notes` optional. Path carries `businessId` and the type `slug`.
SCHEDULING_BOOK = "/api/scheduling/public/{business_id}/{slug}/book"

#: `server.register(leadRoutes, { prefix: '/api/leads' })`, public capture route.
#: Body requires `businessId` and `email`.
LEADS_CAPTURE = "/api/leads/capture"

#: `server.register(analyticsRoutes, { prefix: '/api/analytics' })`. Aggregated
#: dashboard over the caller's own businesses. §6.2's cap holds here: anonymous browsing
#: and pixel data, no named contacts in the response.
ANALYTICS_DASHBOARD = "/api/analytics/dashboard"
