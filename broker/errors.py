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
