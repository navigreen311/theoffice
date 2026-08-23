"""Forge execution — where the tenant credential is presented and the agent is stamped.

This is the whole trick of brokered identity. The Forge sees its own tenant key,
exactly as it does today, and additionally sees `X-Office-Agent-Id` telling it
*which* agent is behind the call. No Forge has to change for the bridge to exist.

The Forge cannot yet be trusted to *enforce* anything from those headers - it has
no per-principal model. They are attribution, and the Office ledger remains the
authoritative per-agent record until `credential_mode` becomes `native`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from broker.credentials import Credential
from broker.errors import ForgeUnreachable
from broker.grants import ResolvedGrant

HEADER_AGENT = "X-Office-Agent-Id"
HEADER_VENTURE = "X-Office-Venture"
HEADER_TRACE = "X-Office-Trace"
HEADER_IDEMPOTENCY = "Idempotency-Key"
HEADER_API_VERSION = "X-Office-Forge-Api-Version"


@dataclass(frozen=True, slots=True)
class ForgeResponse:
    status_code: int
    body: Any
    forge_side_ref: str | None
    latency_ms: int


def build_headers(
    grant: ResolvedGrant,
    credential: Credential,
    trace_id: uuid.UUID,
    idem_key: str | None,
) -> dict[str, str]:
    """Identity stamp plus the tenant credential.

    `auth_model` comes from `forge_registry`, so adding a Forge that authenticates
    differently is a row, not a branch in the call path.
    """
    headers = {
        HEADER_AGENT: str(grant.office_agent_id),
        HEADER_VENTURE: grant.venture_id,
        HEADER_TRACE: str(trace_id),
        HEADER_API_VERSION: grant.api_version,
        "Content-Type": "application/json",
    }
    if idem_key:
        headers[HEADER_IDEMPOTENCY] = idem_key

    if grant.auth_model == "bearer":
        headers["Authorization"] = f"Bearer {credential.reveal()}"
    elif grant.auth_model == "api_key":
        headers["X-Api-Key"] = credential.reveal()
    else:
        raise ForgeUnreachable(
            f"unsupported auth_model {grant.auth_model!r}",
            forge_id=grant.forge_id,
            auth_model=grant.auth_model,
        )
    return headers


async def execute(
    grant: ResolvedGrant,
    credential: Credential,
    payload: Any,
    *,
    trace_id: uuid.UUID,
    idem_key: str | None,
    client: httpx.AsyncClient,
    timeout: float,
) -> ForgeResponse:
    """POST to the Forge module endpoint.

    A non-2xx response is returned, not raised: a Forge saying 422 is a real
    outcome that belongs in the ledger. Only an inability to *reach* the Forge
    raises, because that is the case where there is no outcome to record.
    """
    url = f"{grant.base_url.rstrip('/')}/{grant.module_id}"
    headers = build_headers(grant, credential, trace_id, idem_key)

    try:
        response = await client.post(url, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        # str(exc) may contain the URL but never a header value.
        raise ForgeUnreachable(
            f"could not reach forge: {type(exc).__name__}",
            forge_id=grant.forge_id,
            module_id=grant.module_id,
        ) from exc

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text}

    forge_ref = response.headers.get("X-Forge-Request-Id")
    latency_ms = int(response.elapsed.total_seconds() * 1000)

    return ForgeResponse(
        status_code=response.status_code,
        body=body,
        forge_side_ref=forge_ref,
        latency_ms=latency_ms,
    )
