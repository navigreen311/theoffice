"""The mandatory call path.

Master prompt §1.2: "The client library is not optional and not advisory. An agent
that constructs its own HTTP call to a Forge is bypassing every control in this
document."

That sentence is only true once network policy makes Forge endpoints unreachable
from agent runtime except through the broker (Phase 0.6, blocked on a deployment
target). Until then this library is a convention, and saying so plainly is more
useful than pretending otherwise.

Order of operations is the design. Each step exists because doing it later, or
not at all, loses something specific:

  1. trace_id            correlates Village -> Office -> Forge
  2. resolve grant       live; a revoked agent's NEXT call fails, not its next session
  3. idempotency key     derived, so a retry is recognisable as a retry
  4. at_most_once guard  these are never auto-retried; escalate instead
  5. AUDIT WRITE         BEFORE the Forge is touched; fail closed if flagged
  6. execute             broker presents the tenant credential, stamps the agent
  7. ledger write        always - success, Forge error, or unreachable

Phase 1 inserts manifest check, trust-tier enforcement and rate limiting between
steps 2 and 5. `trust_tier` is already recorded in the ledger so that enforcement
arrives with history behind it - but recording is not enforcing, and nothing here
yet stops a `propose`-tier agent from executing.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from broker import audit, ledger
from broker.config import get_settings
from broker.credentials import CredentialResolver, build_resolver
from broker.db import connection
from broker.errors import AuditUnavailable, EscalateToHuman, ForgeUnreachable, OfficeError
from broker.executor import ForgeResponse, execute
from broker.grants import ResolvedGrant, resolve_grant


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Who is calling, on whose behalf, for which unit of work."""

    office_agent_id: uuid.UUID
    venture_id: str
    task_id: str
    shift_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class CallResult:
    call_id: uuid.UUID
    trace_id: uuid.UUID
    status_code: int
    body: Any
    latency_ms: int
    idempotency_key: str


class OfficeClient:
    """The only supported way for an agent to reach a Forge."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient | None = None,
        resolver: CredentialResolver | None = None,
    ) -> None:
        settings = get_settings()
        self._http = http or httpx.AsyncClient()
        self._resolver = resolver or build_resolver(settings.credential_backend)
        self._timeout = settings.forge_timeout_seconds

    async def call(
        self,
        forge_id: str,
        module_id: str,
        payload: Any,
        *,
        agent_ctx: AgentContext,
    ) -> CallResult:
        trace_id = uuid.uuid4()
        call_id = uuid.uuid4()

        # 2. Authorization, resolved fresh. Never cached - this is the kill switch.
        try:
            async with connection() as conn:
                grant = await resolve_grant(
                    conn,
                    office_agent_id=agent_ctx.office_agent_id,
                    forge_id=forge_id,
                    module_id=module_id,
                    venture_id=agent_ctx.venture_id,
                )
        except OfficeError as exc:
            await self._audit_refusal(exc, agent_ctx, trace_id, forge_id, module_id)
            raise

        # 3. Derived, so the same task+module+payload always yields the same key.
        idem_key = ledger.idempotency_key(agent_ctx.task_id, module_id, payload)

        # 4. at_most_once endpoints are never auto-retried. Master prompt Part 16.
        if grant.idempotency_support == "at_most_once" and await ledger.has_prior_call(
            idem_key, agent_ctx.office_agent_id
        ):
            # Distinct name: `except ... as exc` above unbinds `exc` when its
            # block exits, so reusing it here reads as a live variable that is not.
            escalation = EscalateToHuman(
                "at_most_once module already called with this idempotency key; "
                "a human must decide whether to repeat it",
                forge_id=forge_id,
                module_id=module_id,
                idempotency_key=idem_key,
            )
            await self._audit_refusal(escalation, agent_ctx, trace_id, forge_id, module_id)
            raise escalation

        # 5. Intent is recorded before the Forge is touched.
        await self._audit_intent(grant, agent_ctx, trace_id, call_id, idem_key)

        # 6/7. Execute, then ledger the outcome whatever it was.
        ts_start = datetime.now(UTC)
        try:
            credential = await self._resolver.resolve(grant.credential_ref)
            response = await execute(
                grant,
                credential,
                payload,
                trace_id=trace_id,
                idem_key=idem_key,
                client=self._http,
                timeout=self._timeout,
            )
        except OfficeError as exc:
            await self._write_ledger(
                call_id=call_id,
                trace_id=trace_id,
                grant=grant,
                agent_ctx=agent_ctx,
                payload=payload,
                idem_key=idem_key,
                ts_start=ts_start,
                response=None,
            )
            await self._audit_refusal(exc, agent_ctx, trace_id, forge_id, module_id)
            raise

        await self._write_ledger(
            call_id=call_id,
            trace_id=trace_id,
            grant=grant,
            agent_ctx=agent_ctx,
            payload=payload,
            idem_key=idem_key,
            ts_start=ts_start,
            response=response,
        )

        return CallResult(
            call_id=call_id,
            trace_id=trace_id,
            status_code=response.status_code,
            body=response.body,
            latency_ms=response.latency_ms,
            idempotency_key=idem_key,
        )

    # ---------------------------------------------------------------- internals

    async def _audit_intent(
        self,
        grant: ResolvedGrant,
        agent_ctx: AgentContext,
        trace_id: uuid.UUID,
        call_id: uuid.UUID,
        idem_key: str,
    ) -> None:
        """Write the pre-call entry, failing closed when compliance flags apply.

        Master prompt Part 13: fail closed on compliance-flagged actions,
        durable-queue otherwise. An unflagged action degrades rather than halting,
        because halting every call on an audit outage converts a logging problem
        into a total outage. A flagged action halts, because proceeding without a
        record is the thing the flag exists to prevent.
        """
        try:
            await audit.write_event(
                event_type="forge_call_intent",
                actor_type="agent",
                actor_id=agent_ctx.office_agent_id,
                venture_id=agent_ctx.venture_id,
                trace_id=trace_id,
                subject={
                    "call_id": str(call_id),
                    "forge_id": grant.forge_id,
                    "module_id": grant.module_id,
                    "api_version": grant.api_version,
                    "trust_tier": grant.trust_tier,
                    "credential_mode": grant.credential_mode,
                    "compliance_flags": list(grant.compliance_flags),
                    "idempotency_key": idem_key,
                    "task_id": agent_ctx.task_id,
                },
            )
        except Exception as exc:
            if grant.is_compliance_flagged:
                raise AuditUnavailable(
                    "pre-call audit write failed on a compliance-flagged action",
                    forge_id=grant.forge_id,
                    module_id=grant.module_id,
                    compliance_flags=list(grant.compliance_flags),
                ) from exc
            # Unflagged: proceed. Phase 1 replaces this with a durable queue;
            # until then the failure is visible only in broker logs, which is a
            # known gap rather than a design.

    async def _audit_refusal(
        self,
        exc: OfficeError,
        agent_ctx: AgentContext,
        trace_id: uuid.UUID,
        forge_id: str,
        module_id: str,
    ) -> None:
        """Record why a call was refused.

        Best-effort by necessity: this runs on paths where the audit store may be
        exactly what failed. Raising here would replace a specific, actionable
        error with a generic one.
        """
        with contextlib.suppress(Exception):
            await audit.write_event(
                event_type=exc.audit_event,
                actor_type="agent",
                actor_id=agent_ctx.office_agent_id,
                venture_id=agent_ctx.venture_id,
                trace_id=trace_id,
                subject={"forge_id": forge_id, "module_id": module_id, **exc.as_subject()},
            )

    async def _write_ledger(
        self,
        *,
        call_id: uuid.UUID,
        trace_id: uuid.UUID,
        grant: ResolvedGrant,
        agent_ctx: AgentContext,
        payload: Any,
        idem_key: str,
        ts_start: datetime,
        response: ForgeResponse | None,
    ) -> None:
        ts_end = datetime.now(UTC)
        await ledger.write_call(
            call_id=call_id,
            trace_id=trace_id,
            office_agent_id=agent_ctx.office_agent_id,
            venture_id=agent_ctx.venture_id,
            shift_id=agent_ctx.shift_id,
            forge_id=grant.forge_id,
            module_id=grant.module_id,
            api_version=grant.api_version,
            ts_start=ts_start,
            ts_end=ts_end,
            latency_ms=response.latency_ms if response else None,
            # No status code means the Forge was never reached - distinct from a
            # Forge that answered with an error.
            status_code=response.status_code if response else None,
            trust_tier_at_call=grant.trust_tier,
            compliance_flags_active=list(grant.compliance_flags),
            idempotency_key=idem_key,
            forge_side_ref=response.forge_side_ref if response else None,
            payload_hash=ledger.payload_hash(payload),
        )

    async def aclose(self) -> None:
        await self._http.aclose()


__all__ = [
    "AgentContext",
    "CallResult",
    "ForgeUnreachable",
    "OfficeClient",
]
