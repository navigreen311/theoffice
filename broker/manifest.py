"""Forge Manifest reconciliation — three states, four handlers.

Master prompt §5.6 and Part 15. The manifest is the venture's Bill of Materials,
reconciled three ways:

  Declared  a row exists in venture_forge_manifest
  Required  that row has is_required = true
  In-Use    the module appears in agent_call_ledger

At call time only two of the three are knowable, and the outcome is one of:

| Situation                        | manifest_match | Action                        |
|----------------------------------|----------------|-------------------------------|
| in manifest, is_required = true  | required       | proceed                       |
| in manifest, is_required = false | declared_only  | HIGH incident, throttle, PROCEED |
| not in manifest                  | UNDECLARED     | HIGH incident, throttle, BLOCK |

`declared_only` proceeds because the venture *did* declare the module - the incident
records that nothing in the workflow required it (`IN_USE_NOT_REQUIRED`). `UNDECLARED`
blocks because nobody declared it at all. Blocking both would make a Pack's own
declarations meaningless; blocking neither would make the manifest decorative.

`REQUIRED_NOT_DECLARED` is not reachable at runtime - it fails the Pack at Gate 3.5,
before anything can call anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker import incidents, limits
from broker.errors import ManifestViolation

REQUIRED = "required"
DECLARED_ONLY = "declared_only"
UNDECLARED = "UNDECLARED"

# An undeclared or unrequired call is throttled rather than only logged: the point
# is to slow a misbehaving agent while a human looks, not to produce an alert that
# arrives after the damage.
THROTTLE_FACTOR = 0.1
THROTTLE_SECONDS = 900


@dataclass(frozen=True, slots=True)
class ManifestResult:
    match: str
    criticality: str | None
    incident_id: uuid.UUID | None


async def check(
    conn: AsyncConnection,
    *,
    venture_id: str,
    forge_id: str,
    module_id: str,
    office_agent_id: uuid.UUID,
    trace_id: uuid.UUID,
) -> ManifestResult:
    """Reconcile this call against the venture manifest.

    Raises ManifestViolation on UNDECLARED. Returns the ledger `manifest_match`
    value otherwise.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT is_required, criticality, module_gap FROM venture_forge_manifest "
            "WHERE venture_id = %s AND forge_id = %s AND module_id = %s",
            (venture_id, forge_id, module_id),
        )
        row = await cur.fetchone()

    if row is None:
        incident_id = await incidents.raise_incident(
            severity="HIGH",
            kind="undeclared_forge_call",
            venture_id=venture_id,
            office_agent_id=office_agent_id,
            forge_id=forge_id,
            module_id=module_id,
            trace_id=trace_id,
            detail={"manifest_match": UNDECLARED},
        )
        await limits.throttle_agent(office_agent_id, THROTTLE_FACTOR, THROTTLE_SECONDS)
        raise ManifestViolation(
            "module is not in the venture Forge Manifest",
            forge_id=forge_id,
            module_id=module_id,
            venture_id=venture_id,
            incident_id=str(incident_id),
        )

    if not row["is_required"]:
        incident_id = await incidents.raise_incident(
            severity="HIGH",
            kind="in_use_not_required",
            venture_id=venture_id,
            office_agent_id=office_agent_id,
            forge_id=forge_id,
            module_id=module_id,
            trace_id=trace_id,
            detail={"manifest_match": DECLARED_ONLY},
        )
        await limits.throttle_agent(office_agent_id, THROTTLE_FACTOR, THROTTLE_SECONDS)
        return ManifestResult(DECLARED_ONLY, row["criticality"], incident_id)

    return ManifestResult(REQUIRED, row["criticality"], None)
