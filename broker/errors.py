"""The refusal taxonomy.

Every way the call path can refuse has a named type. A refusal that surfaces as a
generic exception is a refusal nobody can write an alert on, and the ledger's
`status_code` would be the only record of why an agent was stopped.

`OfficeError.audit_event` is the `event_type` written to `audit_log` when the
refusal happens, so the audit trail names the reason in a queryable field rather
than only inside a message string.
"""

from __future__ import annotations


class OfficeError(Exception):
    """Base for every refusal in the call path."""

    audit_event: str = "call_refused"
    status_code: int = 403

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def as_subject(self) -> dict[str, object]:
        """Audit `subject` payload. Never include a credential value."""
        return {"error": type(self).__name__, "message": self.message, **self.context}


class NotGranted(OfficeError):
    """No live grant for this agent x forge x module x venture."""

    audit_event = "call_refused_not_granted"


class NotCertified(OfficeError):
    """A grant exists but is missing Unit A or Unit B certification.

    Invariant 6: certification is the grant condition, not advisory metadata.
    """

    audit_event = "call_refused_not_certified"


class IdentityInactive(OfficeError):
    """The agent identity is suspended, revoked, or retired."""

    audit_event = "call_refused_identity_inactive"


class AuditUnavailable(OfficeError):
    """The pre-call audit write failed on a compliance-flagged action.

    Fail closed. Master prompt Part 13: never fail open.
    """

    audit_event = "call_refused_audit_unavailable"
    status_code = 503


class EscalateToHuman(OfficeError):
    """An at_most_once operation was retried. Never auto-retry these."""

    audit_event = "call_escalated_at_most_once_replay"
    status_code = 409


class UnknownForge(OfficeError):
    """No row in forge_registry, or no row in forge_module_registry."""

    audit_event = "call_refused_unknown_forge"
    status_code = 404


class ModuleExcluded(OfficeError):
    """The module is recorded in forge_module_exclusion and must never be granted.

    This is a registry-level fact, not an agent-level one: it outranks every
    per-agent refusal, because no agent may hold this and the reason has nothing
    to do with which agent asked.

    The database refuses the grant INSERT outright. This exists for the grant that
    predates the exclusion, or was written by a superuser, and to turn a constraint
    violation into an audited reason.
    """

    audit_event = "call_refused_module_excluded"
    status_code = 403


class CredentialUnavailable(OfficeError):
    """The credential ref did not resolve.

    The ref is safe to report. The value is never in the message.
    """

    audit_event = "call_refused_credential_unavailable"
    status_code = 503


class ForgeUnreachable(OfficeError):
    """The Forge could not be contacted.

    Master prompt Part 13: agents being unable to reach Forges is correct
    behaviour when the broker is down, not an outage to route around.
    """

    audit_event = "call_failed_forge_unreachable"
    status_code = 502


class GrantNotActivated(OfficeError):
    """The grant exists and is certified, but has not been activated.

    Part 11: Gate 7 issues grants inactive; Gate 11 activates them against a valid
    sign-off. Distinct from `NotGranted` because the fix is different - this agent is
    correctly appointed and the venture has not finished provisioning.

    Named separately for the same reason every other refusal is: "not granted" would
    send an operator looking for a missing grant that is sitting right there.
    """

    audit_event = "call_refused_grant_not_activated"


class Revoked(OfficeError):
    """An active revocation covers this call.

    Carries the scope, because "your grant was revoked" and "the whole Forge is
    revoked" call for different responses from the agent's operator.
    """

    audit_event = "call_refused_revoked"


class ManifestViolation(OfficeError):
    """The module is not in the venture's Forge Manifest at all.

    Blocked rather than merely recorded: a call to something nobody declared is
    the case the manifest exists to catch.
    """

    audit_event = "call_refused_undeclared_module"


class RequiresApproval(OfficeError):
    """Trust tier is below auto_execute; a proposal was created instead.

    Not a failure. The agent asked to act, the tier said a human decides, and a
    proposal now exists. It is an exception because the call did not happen and
    the caller must not treat an absent Forge response as a successful one.
    """

    audit_event = "call_deferred_to_proposal"
    status_code = 202

    def __init__(self, message: str, proposal_id: object, **context: object) -> None:
        super().__init__(message, proposal_id=str(proposal_id), **context)
        self.proposal_id = proposal_id


class RateLimited(OfficeError):
    """Per-agent or per-Forge token bucket is empty."""

    audit_event = "call_refused_rate_limited"
    status_code = 429


class BudgetExceeded(OfficeError):
    """A rung of the Part 12 cost ladder stopped this call."""

    audit_event = "call_refused_budget_exceeded"
    status_code = 402


class NotAuthorized(OfficeError):
    """The actor lacks the authority for this governance action.

    Distinct from NotGranted: that is an agent without a grant, this is a human
    without the role - e.g. a venture operator attempting a Forge-wide revocation.
    """

    audit_event = "governance_action_refused_not_authorized"
