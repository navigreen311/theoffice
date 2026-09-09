"""The FunnelForge adapter's HTTP surface: `GET /_modules` and `POST /{module_id}`.

`docs/forge-adapter.md`, *"What an adapter is, and is not"*, and this file tries to be
exactly that and nothing more:

  **It decides nothing.** By the time a request arrives The Office has checked the grant,
  certification, revocation, shift, manifest, budget, tier and rate limit, and written an
  audit entry. Nothing here re-checks any of it. The two refusals in `gate.py` are the
  documented exception and the reason is written there: The Office holds neither fact, so
  they are not a second copy of anything.

  **It refuses only a caller who cannot present the tenant credential.** Authentication,
  not authorization.

  **It fails closed when unconfigured.** No credential configured returns 503 with a body
  that says so - trap #9: *"an adapter that is not configured must not answer like one
  whose credential was refused."* 401 means the credential was wrong; 503 means there is
  nothing to check it against, and collapsing the two sends whoever is debugging to
  rotate a credential that was never the problem.

  **Its logs must actually emit.** `_log` checks its own effective level at import and
  the health body reports it, because CRE Forge's adapter formatted identity lines into
  a root logger sitting at WARNING with no handlers and dropped every one of them.

HEADERS ARE COPIED FROM `broker/executor.py`, NOT INFERRED
==========================================================

Trap #3 cost a silently-absent correlation id: the first adapter read
`X-Office-Trace-Id`, FastAPI bound it to `None` on every request, and the call returned
200. **A header read under the wrong name does not fail; it reads as absent.** So the
names below are imported from `broker.executor` rather than typed again - a rename there
now breaks this at import instead of at correlation time.

That import is the one place this adapter touches The Office's code. It is a constant, not
behaviour.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from adapters.funnelforge.gate import Refused
from adapters.funnelforge.modules import MODULES, manifest
from adapters.funnelforge.upstream import UpstreamCall
from broker.executor import (
    HEADER_AGENT,
    HEADER_IDEMPOTENCY,
    HEADER_TRACE,
    HEADER_VENTURE,
)

_log = logging.getLogger("funnelforge.adapter")

#: What The Office presents. `forge_registry.auth_model` for FunnelForge is `bearer`
#: because that is all FunnelForge has - a user JWT, verified by `server.decorate
#: ('authenticate')`. See `upstream.py`: there is no API-key path anywhere in its
#: middleware, so there is no tenant credential to broker and the token is a user's.
TENANT_CREDENTIAL_ENV = "FUNNELFORGE_TENANT_TOKEN"

#: Where FunnelForge's API answers. Service DNS, not a host port: the fifteen containers
#: publish none. `funnelforge-api` resolves as `api` on `ff-docker_funnelforge-network`.
UPSTREAM_BASE_ENV = "FUNNELFORGE_API_BASE"
UPSTREAM_BASE_DEFAULT = "http://api:3001"

#: The Forge's own correlation id, returned on every answer. The Office stores it as
#: `agent_call_ledger.forge_side_ref`, and that pair is what makes a call traceable from
#: either end - both sides return 200 without it, so it is asserted in the tests.
HEADER_FORGE_REQUEST = "X-Forge-Request-Id"


def tenant_credential() -> str | None:
    """The configured credential, or None. Never the value in a table."""
    return os.environ.get(TENANT_CREDENTIAL_ENV) or None


def upstream_base() -> str:
    return os.environ.get(UPSTREAM_BASE_ENV) or UPSTREAM_BASE_DEFAULT


class HttpUpstream:
    """Performs an `UpstreamCall` against FunnelForge's API with the brokered token."""

    def __init__(self, client: httpx.AsyncClient, token: str) -> None:
        self._client = client
        self._token = token

    async def __call__(self, call: UpstreamCall) -> dict[str, Any]:
        res = await self._client.request(
            call.method,
            f"{upstream_base()}{call.path}",
            json=call.body,
            params=call.query,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        try:
            body = res.json()
        except ValueError:
            # A 200 with an unparseable body is not a success. FunnelForge's own
            # /docs/json answers 200 with zero bytes, so this is not hypothetical.
            body = {"raw": res.text}
        return {"status": res.status_code, "body": body}


def _unconfigured() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": "ADAPTER_NOT_CONFIGURED",
                "message": (
                    f"{TENANT_CREDENTIAL_ENV} is not set, so this adapter has nothing to "
                    "authenticate against and will not serve its surface "
                    "unauthenticated. This is NOT a refused credential - do not rotate "
                    "anything. See docs/forge-adapter.md trap #9."
                ),
            }
        },
    )


def build_app() -> FastAPI:
    app = FastAPI(title="FunnelForge Office adapter")
    router = APIRouter()

    @router.get("/_modules")
    async def modules(
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        """The dispatch map's keys and shapes, authenticated like a module call.

        `broker/forge_modules.read` sends the same credential here as to a module, and
        `scripts/verify_forge_modules.py` is what spends the answer.
        """
        configured = tenant_credential()
        if configured is None:
            return _unconfigured()
        if authorization != f"Bearer {configured}":
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHENTICATED", "message": "bad token"}},
            )
        return JSONResponse(status_code=200, content=manifest())

    @router.post("/{module_id}")
    async def dispatch(
        module_id: str,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        request_id = str(uuid.uuid4())
        headers = {HEADER_FORGE_REQUEST: request_id}

        configured = tenant_credential()
        if configured is None:
            response = _unconfigured()
            response.headers[HEADER_FORGE_REQUEST] = request_id
            return response
        if authorization != f"Bearer {configured}":
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "UNAUTHENTICATED", "message": "bad token"}},
                headers=headers,
            )

        binding = MODULES.get(module_id)
        if binding is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "MODULE_NOT_BOUND",
                        "message": (
                            f"{module_id!r} is not dispatched. The dispatch map is the "
                            "spelling of record; a second spelling does not quietly work."
                        ),
                    }
                },
                headers=headers,
            )

        try:
            payload = await request.json()
        except ValueError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        # The identity stamp, logged before the call so a refusal is attributable too.
        _log.info(
            "office call module=%s agent=%s venture=%s trace=%s idem=%s request=%s",
            module_id,
            request.headers.get(HEADER_AGENT),
            request.headers.get(HEADER_VENTURE),
            request.headers.get(HEADER_TRACE),
            request.headers.get(HEADER_IDEMPOTENCY),
            request_id,
        )

        async with httpx.AsyncClient() as client:
            upstream = HttpUpstream(client, configured)
            try:
                result = await binding.handler(payload, upstream)
            except Refused as refused:
                # 422, not 400: the request was well formed and the handler declined it.
                # The code and the reason both travel, so the ledger row says which
                # refusal fired rather than that something went wrong.
                _log.warning(
                    "refused module=%s code=%s request=%s",
                    module_id,
                    refused.code,
                    request_id,
                )
                return JSONResponse(
                    status_code=422,
                    content={
                        "error": {"code": refused.code, "message": refused.reason}
                    },
                    headers=headers,
                )

        return JSONResponse(status_code=200, content=result, headers=headers)

    app.include_router(router)
    return app


def logging_is_effective() -> bool:
    """Whether `_log.info` would actually emit. CRE Forge's did not.

    Reported rather than fixed here: an adapter that reconfigures the host application's
    logging is an adapter with a side effect nobody asked for. Whoever deploys this reads
    the answer and configures the host.
    """
    return _log.isEnabledFor(logging.INFO) and bool(logging.getLogger().handlers)
