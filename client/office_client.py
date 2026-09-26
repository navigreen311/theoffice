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
   2. resolve grant       live; identity active, grant live, both certs present
   3. revocation scopes   live; agent x module | agent | venture | forge
  3a. shift boundary      the call's venture must be the agent's on-shift venture
   4. manifest check      required | declared_only | UNDECLARED
   5. budget ladder       per-task | per-agent daily | soft | hard
   6. effective tier      grant tier, downgraded engagement-wide if soft-capped
   7. trust tier gate     below auto_execute -> proposal, and no Forge call
                          UNLESS a human already approved THIS act (entry 195)
   8. rate limit          per-agent AND per-Forge; both must admit
   9. idempotency key     derived, so a retry is recognisable as a retry
  10. at_most_once guard  these are never auto-retried; escalate instead
  11. AUDIT WRITE         BEFORE the Forge is touched; fail closed if flagged
  12. execute             broker presents the tenant credential, stamps the agent
  13. ledger write        always - success, Forge error, or unreachable

Why this order and not another:

  - Revocation precedes everything, so a revoked agent spends no rate-limit token
    and triggers no budget query. A kill switch that consumes resources on the way
    to refusing is not much of a kill switch.
  - The shift check follows revocation and precedes everything else: a revoked agent
    should be told it is revoked rather than told it is on the wrong shift, but
    serving the wrong venture is a boundary violation whatever the module is. This is
    what makes "one venture per agent per shift" enforceable rather than declarative -
    the schema forbids overlapping shifts, but nothing else stops an agent holding two
    ventures' grants from serving both inside one shift.
  - The manifest check precedes the tier gate, because calling an undeclared module
    is a violation regardless of what tier the caller holds.
  - Budget precedes the tier gate, because the soft cap *changes* the effective
    tier. Reversing them would let an auto_execute call slip through in the window
    where the venture had already crossed its soft cap.
  - Rate limiting is last of the gates, so refusals that cost nothing to detect
    happen before the one that mutates a bucket.

AN APPROVED PROPOSAL EXECUTES ON THE AGENT'S OWN RE-CALL (entry 195)
====================================================================

    There is no runner. The agent calls, is refused with `RequiresApproval`, a human
    decides, and the agent calls again with the same arguments. `idempotency_key` is
    derived from `task_id`, `module_id` and `payload`, so re-deriving it is how the
    agent proves it is asking for the same act - there is no approval token to present
    and therefore none to present for the wrong payload.

    **Exactly one step is skipped, and it is step 7.** Every other gate re-runs on the
    second call, against the world as it is then rather than as it was when the human
    looked: revocation, the shift boundary, the manifest, the budget, and `resolve_grant`
    itself, which is re-resolved before any of this. A human approving at 09:00 does not
    authorise a call by an agent revoked at 09:05.

    **A refusal at any of those is terminal.** The proposal goes to `failed` with the
    reason, and nothing retries it: the human approved an act in a world that has since
    changed, and what that needs is a new decision rather than another attempt.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from broker import (
    audit,
    budget,
    ledger,
    limits,
    manifest,
    proposals,
    revocation,
    shifts,
)
from broker.config import get_settings
from broker.credentials import CredentialResolver, build_resolver
from broker.db import connection
from broker.errors import (
    AuditUnavailable,
    EscalateToHuman,
    ForgeUnreachable,
    OfficeError,
    RequiresApproval,
)
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
class Governed:
    """What steps 3-8 concluded. Entry 195 added the second field.

    `approved_proposal_id` is the approval this call is acting on, or `None` on an
    ordinary call. It is carried out of `_govern` rather than looked up again later
    because two lookups could disagree, and the one that matters is the one the tier
    gate actually consulted.
    """

    manifest_match: str
    approved_proposal_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class CallResult:
    call_id: uuid.UUID
    trace_id: uuid.UUID
    status_code: int
    body: Any
    latency_ms: int
    idempotency_key: str
    manifest_match: str
    #: The approval this call acted on, or `None` when the agent acted on its own
    #: authority. Entry 195. Last, and defaulted, so every existing caller that
    #: constructs a `CallResult` positionally keeps working.
    approved_proposal_id: uuid.UUID | None = None


class OfficeClient:
    """The only supported way for an agent to reach a Forge."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient | None = None,
        resolver: CredentialResolver | None = None,
        enforce_shift: bool = True,
    ) -> None:
        settings = get_settings()
        self._http = http or httpx.AsyncClient()
        self._resolver = resolver or build_resolver(settings.credential_backend)
        self._timeout = settings.forge_timeout_seconds
        # Shift enforcement is on by default and is not something an agent can turn
        # off - there is no runtime path to this flag. It exists so tests that predate
        # shift assignment, and callers operating outside the shift system entirely,
        # can be explicit about it rather than silently exempt.
        self._enforce_shift = enforce_shift

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

        # 9, MOVED UP. Derived, so the same task+module+payload always yields the same
        # key - which is what lets the second call find the approval given for the
        # first. It is computed here rather than after `_govern` because both the tier
        # gate and every refusal handler below now need it, and deriving it twice would
        # be two spellings of the identity of an act.
        idem_key = ledger.idempotency_key(agent_ctx.task_id, module_id, payload)

        # 3-8. Governance. Every refusal below is audited by its own handler and
        # raises a named type, so an operator sees which gate stopped the call.
        try:
            governed = await self._govern(grant, agent_ctx, trace_id, payload, idem_key)
        except OfficeError as exc:
            await self._audit_refusal(exc, agent_ctx, trace_id, forge_id, module_id)
            await self._fail_approved(agent_ctx, idem_key, forge_id, module_id, exc)
            raise
        manifest_match = governed.manifest_match

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
            await self._fail_approved(
                agent_ctx, idem_key, forge_id, module_id, escalation
            )
            raise escalation

        # 5. Intent is recorded before the Forge is touched.
        try:
            await self._audit_intent(
                grant, agent_ctx, trace_id, call_id, idem_key,
                governed.approved_proposal_id,
            )
        except OfficeError as exc:
            await self._fail_approved(agent_ctx, idem_key, forge_id, module_id, exc)
            raise

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
                manifest_match=manifest_match,
            )
            await self._audit_refusal(exc, agent_ctx, trace_id, forge_id, module_id)
            # NOT `_fail_approved`. THE FORGE WAS REACHED, or reaching it was attempted
            # with the credential presented - `ForgeUnreachable` is raised from inside
            # `execute`, past the point where this call is indistinguishable from one
            # that landed. Marking the proposal `failed` would say the act did not
            # happen, and this path cannot know that. The proposal stays `approved` and
            # the ledger row carries what is actually known.
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
            manifest_match=manifest_match,
        )

        # 14. The approval is spent, AFTER the call. Entry 195: `mark_executed` moves
        # the row only from `approved`, so a third call finds nothing to act on and is
        # refused with a fresh `RequiresApproval` rather than repeating the act.
        if governed.approved_proposal_id is not None:
            await self._spend_approval(
                governed.approved_proposal_id, call_id, agent_ctx, trace_id, grant
            )

        return CallResult(
            call_id=call_id,
            trace_id=trace_id,
            approved_proposal_id=governed.approved_proposal_id,
            status_code=response.status_code,
            body=response.body,
            latency_ms=response.latency_ms,
            idempotency_key=idem_key,
            manifest_match=manifest_match,
        )

    # ---------------------------------------------------------------- internals

    async def _govern(
        self,
        grant: ResolvedGrant,
        agent_ctx: AgentContext,
        trace_id: uuid.UUID,
        payload: Any,
        idem_key: str,
    ) -> Governed:
        """Steps 3-8. Returns the ledger verdict and the approval being acted on.

        Raises the specific gate's error when a gate refuses. `RequiresApproval`
        is raised rather than returned so that a caller cannot mistake an absent
        Forge response for a successful one - a proposal was created, the action
        did not happen, and those must not look alike.
        """
        async with connection() as conn:
            # 3. Revocation - before anything that costs a token or a query.
            await revocation.check_revocations(
                conn,
                office_agent_id=agent_ctx.office_agent_id,
                forge_id=grant.forge_id,
                module_id=grant.module_id,
                venture_id=agent_ctx.venture_id,
            )

            # 3a. One venture per agent per shift, locked. Enforced here because a
            # grant scoped to a venture does not by itself stop an agent from serving
            # that venture during a shift assigned to a different one.
            if self._enforce_shift:
                await shifts.assert_on_shift_for(
                    conn,
                    office_agent_id=agent_ctx.office_agent_id,
                    venture_id=agent_ctx.venture_id,
                )

            # 4. Manifest. Raises on UNDECLARED; returns declared_only or required.
            manifest_result = await manifest.check(
                conn,
                venture_id=agent_ctx.venture_id,
                forge_id=grant.forge_id,
                module_id=grant.module_id,
                office_agent_id=agent_ctx.office_agent_id,
                trace_id=trace_id,
            )

            # 5. Budget ladder. Raises on a halting rung.
            budget_state = await budget.evaluate(
                conn,
                venture_id=agent_ctx.venture_id,
                office_agent_id=agent_ctx.office_agent_id,
                task_id=agent_ctx.task_id,
            )

            # 6/7. Effective tier, then the gate.
            soft_capped = bool(budget_state and budget_state.soft_capped)
            tier = proposals.effective_tier(grant.trust_tier, soft_capped=soft_capped)

            approved: dict[str, Any] | None = None
            if tier != proposals.AUTO_EXECUTE:
                # ENTRY 195. THE ONLY GATE AN APPROVAL SKIPS, AND ONLY THIS ONE.
                #
                # Looked up HERE rather than at the top of the call, so everything
                # above has already refused if it was going to. An approval does not
                # excuse a revocation, an ended shift, an undeclared module or a spent
                # budget; it answers one question - may this agent act at this tier -
                # and it is asked at the point that question is put.
                #
                # `approved_for` matches on the derived idempotency key, so the agent
                # asking again for the same act is what identifies the approval. There
                # is no token to present and nothing to present for a different payload.
                approved = await proposals.approved_for(
                    conn,
                    office_agent_id=agent_ctx.office_agent_id,
                    idempotency_key=idem_key,
                    forge_id=grant.forge_id,
                    module_id=grant.module_id,
                )

            if tier != proposals.AUTO_EXECUTE and approved is None:
                proposal_id = await proposals.submit(
                    conn,
                    office_agent_id=agent_ctx.office_agent_id,
                    venture_id=agent_ctx.venture_id,
                    forge_id=grant.forge_id,
                    module_id=grant.module_id,
                    task_id=agent_ctx.task_id,
                    trust_tier=tier,
                    payload=payload,
                    payload_hash=ledger.payload_hash(payload),
                    idempotency_key=ledger.idempotency_key(
                        agent_ctx.task_id, grant.module_id, payload
                    ),
                    trace_id=trace_id,
                )
                # THE REFUSAL NAMES THE GAP RATHER THAN IMPLYING A WORKFLOW.
                #
                # It used to say "a proposal was created", which is true and
                # misleading. A proposal is created, a human can approve it through
                # POST /api/proposals/{id}/decide, and then nothing happens:
                # `proposals.mark_executed` - the function that links an approved
                # proposal to the call that carried it out - has no production
                # caller. Only its tests call it.
                #
                # So an approved proposal is a dead letter. The old message let an
                # operator approve one and reasonably believe the act had been
                # authorised and would follow, and the silence afterwards looks
                # like a queue rather than a missing implementation.
                #
                # The call is still refused exactly as before and the proposal row
                # is still written - the intent, the payload and the trace are
                # worth keeping either way, and an operator who wants to act can
                # read the payload and do it by hand. What changes is that the
                # refusal says what will and will not happen next.
                raise RequiresApproval(
                    f"trust tier {tier!r} requires human approval. A proposal was "
                    "created; when a human approves it, CALL AGAIN with the same task, "
                    "module and payload and the act will be carried out. Nothing else "
                    "executes it - there is no runner, and every other gate re-runs on "
                    "that second call.",
                    proposal_id,
                    forge_id=grant.forge_id,
                    module_id=grant.module_id,
                    declared_tier=grant.trust_tier,
                    effective_tier=tier,
                    soft_capped=soft_capped,
                )

        # 8. Rate limit last of the gates: it mutates a bucket, and the refusals
        # above cost nothing to detect. Outside the `async with`, as it always was -
        # `limits` holds its own store.
        await limits.acquire(
            office_agent_id=agent_ctx.office_agent_id, forge_id=grant.forge_id
        )
        return Governed(
            manifest_match=manifest_result.match,
            approved_proposal_id=approved["proposal_id"] if approved else None,
        )

    async def _audit_intent(
        self,
        grant: ResolvedGrant,
        agent_ctx: AgentContext,
        trace_id: uuid.UUID,
        call_id: uuid.UUID,
        idem_key: str,
        approved_proposal_id: uuid.UUID | None = None,
    ) -> None:
        """Write the pre-call entry, failing closed on a MUTATING call.

        Master prompt Part 13 wrote this as "fail closed on compliance-flagged actions,
        durable-queue otherwise", and it keyed on the flags until 15 September. **Ivan's
        ruling moved it to `is_mutating`:** a mutating call fails if its audit write
        fails, flagged or not.

        The reason is in entry 105. The flags it keyed on were a development fixture's -
        one list per Forge, looped over every module - so `assign_contract`'s fail-closed
        property came from a row nobody had read, and correcting the flags would have
        removed it without anybody deciding to.

        A read still degrades. An unrecorded read is a gap in the log; an unrecorded
        write is a change to the world nobody can find.
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
                    # Entry 167: any surface showing a grant says which of its
                    # certifications are simulation-only, and the audit entry is the
                    # surface that survives. A call made while a department's context
                    # rested on a declaration rather than an exam has to read that way
                    # afterwards, when somebody is asking what the agent was cleared on.
                    "unit_b_simulation_only": grant.unit_b_simulation_only,
                    "idempotency_key": idem_key,
                    "task_id": agent_ctx.task_id,
                    # ENTRY 195. WHICH APPROVAL THIS CALL IS ACTING ON, on the entry
                    # that is written before the Forge is touched. `None` on an
                    # auto_execute call, and the difference between a call an agent
                    # made on its own authority and one a human authorised is the
                    # first thing anybody asks afterwards.
                    "approved_proposal_id": (
                        str(approved_proposal_id) if approved_proposal_id else None
                    ),
                },
            )
        except Exception as exc:
            if grant.must_fail_closed:
                raise AuditUnavailable(
                    "pre-call audit write failed on a mutating call; it does not happen "
                    "unrecorded",
                    forge_id=grant.forge_id,
                    module_id=grant.module_id,
                    is_mutating=grant.is_mutating,
                    compliance_flags=list(grant.compliance_flags),
                ) from exc
            # Read-only: proceed. Phase 1 replaces this with a durable queue;
            # until then the failure is visible only in broker logs, which is a
            # known gap rather than a design.

    async def _spend_approval(
        self,
        proposal_id: uuid.UUID,
        call_id: uuid.UUID,
        agent_ctx: AgentContext,
        trace_id: uuid.UUID,
        grant: ResolvedGrant,
    ) -> None:
        """Mark the approval executed and say so in the audit log. Entry 195.

        **Two writes, and the audit one is not best-effort.** `mark_executed` is what
        makes "once" true - it moves the row only from `approved` - and the event is
        what links a human's decision to the act that followed it. A call that happened
        with no record of which approval permitted it is the thing this whole path
        exists to avoid, so a failure here is raised rather than swallowed.

        The call has already happened by this point and the ledger row is already
        written, so raising does not un-make anything: it reports that the act is done
        and its authorisation could not be recorded, which is exactly what has occurred.
        """
        async with connection() as conn:
            await proposals.mark_executed(conn, proposal_id=proposal_id, call_id=call_id)
        await audit.write_event(
            event_type="proposal_executed",
            actor_type="agent",
            actor_id=agent_ctx.office_agent_id,
            venture_id=agent_ctx.venture_id,
            trace_id=trace_id,
            subject={
                "proposal_id": str(proposal_id),
                "call_id": str(call_id),
                "forge_id": grant.forge_id,
                "module_id": grant.module_id,
                "task_id": agent_ctx.task_id,
            },
        )

    async def _fail_approved(
        self,
        agent_ctx: AgentContext,
        idem_key: str,
        forge_id: str,
        module_id: str,
        exc: OfficeError,
    ) -> None:
        """A gate refused an act a human had approved. Terminal. Entry 195.

        **Best-effort, and deliberately so.** The refusal is already raised and already
        audited; this is bookkeeping on top of it. Failing here would replace a specific
        gate error - which is what the operator needs - with a database one.

        Ordinary on a first-pass call: there is no approved proposal and nothing moves.
        `mark_failed` reports that as `False` rather than raising, because "no approval
        to fail" is the common case rather than an error.
        """
        with contextlib.suppress(Exception):
            async with connection() as conn:
                approved = await proposals.approved_for(
                    conn,
                    office_agent_id=agent_ctx.office_agent_id,
                    idempotency_key=idem_key,
                    forge_id=forge_id,
                    module_id=module_id,
                )
                if approved is None:
                    return
                await proposals.mark_failed(
                    conn,
                    proposal_id=approved["proposal_id"],
                    error=f"{type(exc).__name__}: {exc}",
                )

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
        manifest_match: str,
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
            task_id=agent_ctx.task_id,
            manifest_match=manifest_match,
        )

    async def aclose(self) -> None:
        await self._http.aclose()


__all__ = [
    "AgentContext",
    "CallResult",
    "ForgeUnreachable",
    "OfficeClient",
]
