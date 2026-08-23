"""Grant resolution — the authorization decision, made fresh on every call.

Master prompt §1.4: revocation is "checked per call at the broker, never cached.
A revoked agent's next call fails, not its next session."

That sentence rules out every cache, including a short-TTL one. There is no
`@lru_cache` here and there must never be. With no front desk to stop and no
queue to drain, this query *is* the kill switch.

One query answers four questions at once, because splitting them invites a caller
to check three and forget the fourth:

  1. Does the identity exist and is it `active`?
  2. Is there a grant for this agent x forge x module x venture?
  3. Is that grant un-revoked?
  4. Are BOTH certification units present?

The Forge and module are read from the registry in the same round trip - nothing
about which Forge is bridged first may be hardcoded (see CLAUDE.md).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.errors import IdentityInactive, NotCertified, NotGranted, UnknownForge


@dataclass(frozen=True, slots=True)
class ResolvedGrant:
    """Everything the call path needs, resolved together and consistently."""

    grant_id: uuid.UUID
    office_agent_id: uuid.UUID
    agent_name: str
    forge_id: str
    module_id: str
    venture_id: str
    trust_tier: str
    base_url: str
    api_version: str
    auth_model: str
    credential_mode: str
    credential_ref: str
    idempotency_support: str
    is_mutating: bool
    compliance_flags: tuple[str, ...]

    @property
    def is_compliance_flagged(self) -> bool:
        """Whether a failed audit write must fail closed rather than degrade."""
        return bool(self.compliance_flags)


_RESOLVE_SQL = """
SELECT
    g.grant_id,
    g.office_agent_id,
    g.trust_tier,
    g.operation_cert_ref,
    g.dept_context_cert_ref,
    g.revoked_at              AS grant_revoked_at,
    i.agent_name,
    i.status                  AS identity_status,
    r.base_url,
    r.api_version,
    r.auth_model,
    r.credential_mode,
    c.credential_ref,
    m.idempotency_support,
    m.is_mutating,
    m.compliance_flags_implied
FROM agent_forge_grant g
JOIN office_agent_identity i ON i.office_agent_id = g.office_agent_id
JOIN forge_registry       r ON r.forge_id        = g.forge_id
JOIN forge_module_registry m ON m.forge_id = g.forge_id AND m.module_id = g.module_id
LEFT JOIN forge_tenant_credential c ON c.forge_id = g.forge_id
WHERE g.office_agent_id = %(agent_id)s
  AND g.forge_id        = %(forge_id)s
  AND g.module_id       = %(module_id)s
  AND g.venture_id      = %(venture_id)s
ORDER BY g.granted_at DESC
LIMIT 1
"""


async def resolve_grant(
    conn: AsyncConnection,
    *,
    office_agent_id: uuid.UUID,
    forge_id: str,
    module_id: str,
    venture_id: str,
) -> ResolvedGrant:
    """Resolve authorization, or raise the specific reason it was refused.

    Raises a distinct type per refusal so the caller audits *why*, not merely
    *that*. Ordering is deliberate: identity state is reported before grant
    state, because a suspended agent with a valid grant is a different incident
    from an active agent with none.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _RESOLVE_SQL,
            {
                "agent_id": office_agent_id,
                "forge_id": forge_id,
                "module_id": module_id,
                "venture_id": venture_id,
            },
        )
        row = await cur.fetchone()

    if row is None:
        # Distinguish "this Forge/module is not registered" from "this agent has
        # no grant for it" - they are different failures with different fixes.
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT 1 FROM forge_module_registry WHERE forge_id = %s AND module_id = %s",
                (forge_id, module_id),
            )
            known = await cur.fetchone()
        if known is None:
            raise UnknownForge(
                "forge or module is not registered",
                forge_id=forge_id,
                module_id=module_id,
            )
        raise NotGranted(
            "no grant for this agent, forge, module and venture",
            forge_id=forge_id,
            module_id=module_id,
            venture_id=venture_id,
        )

    if row["identity_status"] != "active":
        raise IdentityInactive(
            f"agent identity is {row['identity_status']}",
            identity_status=row["identity_status"],
        )

    if row["grant_revoked_at"] is not None:
        raise NotGranted(
            "grant is revoked",
            grant_id=str(row["grant_id"]),
            revoked_at=row["grant_revoked_at"].isoformat(),
        )

    if row["operation_cert_ref"] is None or row["dept_context_cert_ref"] is None:
        raise NotCertified(
            "grant is missing a certification unit and is not assignable",
            operation_cert=row["operation_cert_ref"] is not None,
            dept_context_cert=row["dept_context_cert_ref"] is not None,
        )

    if row["credential_ref"] is None:
        raise UnknownForge(
            "forge has no tenant credential registered", forge_id=forge_id
        )

    return ResolvedGrant(
        grant_id=row["grant_id"],
        office_agent_id=row["office_agent_id"],
        agent_name=row["agent_name"],
        forge_id=forge_id,
        module_id=module_id,
        venture_id=venture_id,
        trust_tier=row["trust_tier"],
        base_url=row["base_url"],
        api_version=row["api_version"],
        auth_model=row["auth_model"],
        credential_mode=row["credential_mode"],
        credential_ref=row["credential_ref"],
        idempotency_support=row["idempotency_support"],
        is_mutating=row["is_mutating"],
        compliance_flags=tuple(row["compliance_flags_implied"] or ()),
    )
