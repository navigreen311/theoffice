"""Certification — two units, seven states, and staleness by comparison.

Part 10.1. Both units are required for assignment:

  Unit A  agent x forge x module    operation competence   operation rubric
  Unit B  department x forge        judgment in context    domain rubric

Department certification is necessary, never sufficient.

**States are never collapsed.** Two mappings matter more than the rest and are the kind
of thing a `verdict == "PASS"` check gets wrong by omission:

  TIMEOUT  -> in_training        never `certified`. A run that did not finish proved
                                 nothing, and treating "we ran out of time" as a pass
                                 is how an uncertified agent reaches a Forge.
  NOT_RUN  -> never_certified    never `failed`. Nothing was attempted; reporting that
                                 as a failure defames an agent and pollutes the metric
                                 that is supposed to show real failures.

**Staleness is a comparison, not a flag.** A cert stores the instruction hash and Forge
api_version it was tested against; freshness is computed against what is live now. That
means nobody has to remember to invalidate anything, which is the only way this stays
true after the sixth Forge is bridged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from psycopg import AsyncConnection
from psycopg.rows import dict_row

CERTIFIED = "certified"
STALE_INSTRUCTIONS = "stale_instructions"
STALE_FORGE = "stale_forge"
IN_TRAINING = "in_training"
NEVER_CERTIFIED = "never_certified"
FAILED = "failed"
REVOKED = "revoked"

# SimForge verdict -> Office certification state. Explicit rather than derived, so
# adding a verdict is a decision someone makes rather than a default that happens.
VERDICT_TO_STATE = {
    "PASS": CERTIFIED,
    "FAIL": FAILED,
    "TIMEOUT": IN_TRAINING,
    "NOT_RUN": NEVER_CERTIFIED,
    "IN_PROGRESS": IN_TRAINING,
    "REVOKED": REVOKED,
}

# Ordered weakest to strongest, for capping.
TIER_RANK = {"suggest": 1, "propose": 2, "auto_execute": 3}


class CertificationError(Exception):
    """A certification could not be recorded as asked."""


@dataclass(frozen=True, slots=True)
class CertState:
    cert_id: uuid.UUID | None
    unit: str
    state: str
    certified_tier: str | None

    @property
    def is_certified(self) -> bool:
        return self.state == CERTIFIED


def state_for_verdict(verdict: str) -> str:
    """Map a SimForge verdict to a certification state.

    Unknown verdicts raise rather than defaulting. A default here would silently
    turn an unrecognised SimForge response into whichever state the default was,
    and the safe-looking default (`failed`) is itself wrong for NOT_RUN.
    """
    try:
        return VERDICT_TO_STATE[verdict]
    except KeyError:
        raise CertificationError(
            f"unknown SimForge verdict {verdict!r}; refusing to guess a state. "
            f"Known verdicts: {', '.join(sorted(VERDICT_TO_STATE))}"
        ) from None


def cap_tier(declared: str, certified: str | None) -> str:
    """Certified tier caps declared tier (Part 10.1).

    None means uncertified, which is not a tier at all - the caller must not reach
    here with one, and returning the declared tier would silently un-cap it.
    """
    if certified is None:
        raise CertificationError("cannot cap a tier against an uncertified unit")
    return declared if TIER_RANK[declared] <= TIER_RANK[certified] else certified


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise CertificationError(f"not a pinned semver: {version!r}")
    major, minor, patch = (int(p) for p in parts)
    return major, minor, patch


def is_forge_version_stale(
    certified_against: str, current: str, sensitivity: str
) -> bool:
    """Whether a Forge version change invalidates a certification.

    | sensitivity        | 2.1.0 -> 2.1.5 | 2.1.0 -> 2.2.0 | 2.1.0 -> 3.0.0 |
    |--------------------|----------------|----------------|----------------|
    | major              | fresh          | fresh          | stale          |
    | major.minor        | fresh          | stale          | stale          |
    | major.minor.patch  | stale          | stale          | stale          |

    Any change is compared at the declared precision. A *downgrade* is stale too:
    the certification was earned against behaviour that is no longer what the Forge
    does, and which direction it moved is not the point.
    """
    a = _parse_semver(certified_against)
    b = _parse_semver(current)
    depth = {"major": 1, "major.minor": 2, "major.minor.patch": 3}[sensitivity]
    return a[:depth] != b[:depth]


async def record_result(
    conn: AsyncConnection,
    *,
    unit: str,
    forge_id: str,
    verdict: str,
    rubric_version: str,
    office_agent_id: uuid.UUID | None = None,
    module_id: str | None = None,
    department: str | None = None,
    certified_tier: str | None = None,
    instruction_content_hash: str | None = None,
    forge_api_version: str | None = None,
    score: float | None = None,
    threshold: float | None = None,
    scenario_pack_ref: str | None = None,
) -> CertState:
    """Record a SimForge verdict as a certification state.

    Upserts on the unit's natural key, so a re-certification replaces the prior
    verdict rather than accumulating rows that a reader would have to order
    correctly to interpret.
    """
    state = state_for_verdict(verdict)
    rubric_kind = "operation" if unit == "A" else "domain"

    if state == CERTIFIED and not (
        instruction_content_hash and forge_api_version and certified_tier
    ):
        raise CertificationError(
            "a certified result must record the instruction hash, Forge api_version "
            "and certified tier it was earned against; otherwise staleness is "
            "uncomputable and the certification is permanent by accident"
        )

    conflict = (
        "(office_agent_id, forge_id, module_id) WHERE unit = 'A'"
        if unit == "A"
        else "(department, forge_id) WHERE unit = 'B'"
    )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            INSERT INTO certification
              (cert_id, unit, office_agent_id, department, forge_id, module_id,
               state, certified_tier, instruction_content_hash, forge_api_version,
               rubric_kind, rubric_version, score, threshold, scenario_pack_ref,
               simforge_verdict)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT {conflict} DO UPDATE SET
              state = EXCLUDED.state,
              certified_tier = EXCLUDED.certified_tier,
              instruction_content_hash = EXCLUDED.instruction_content_hash,
              forge_api_version = EXCLUDED.forge_api_version,
              rubric_version = EXCLUDED.rubric_version,
              score = EXCLUDED.score,
              threshold = EXCLUDED.threshold,
              scenario_pack_ref = EXCLUDED.scenario_pack_ref,
              simforge_verdict = EXCLUDED.simforge_verdict,
              updated_at = now()
            RETURNING cert_id, unit, state, certified_tier
            """,
            (
                uuid.uuid4(), unit, office_agent_id, department, forge_id, module_id,
                state, certified_tier, instruction_content_hash, forge_api_version,
                rubric_kind, rubric_version, score, threshold, scenario_pack_ref,
                verdict,
            ),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None
    return CertState(row["cert_id"], row["unit"], row["state"], row["certified_tier"])


async def recompute_staleness(
    conn: AsyncConnection, *, forge_id: str, module_id: str | None = None
) -> list[uuid.UUID]:
    """Mark certifications stale against what is live now. Returns the ids changed.

    Only `certified` rows are considered: a `failed` cert does not become
    `stale_instructions` when the text changes, because it was never fresh. Doing
    otherwise would erase the distinction between "was good, now out of date" and
    "was never good".
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT c.cert_id, c.instruction_content_hash, c.forge_api_version,
                   i.content_hash AS live_hash, i.version_sensitivity,
                   r.api_version AS live_api_version
            FROM certification c
            JOIN forge_registry r ON r.forge_id = c.forge_id
            LEFT JOIN forge_operating_instruction i
                   ON i.forge_id = c.forge_id
                  AND i.module_id = c.module_id
                  AND i.superseded_at IS NULL
            WHERE c.state = 'certified'
              AND c.forge_id = %s
              AND (%s::text IS NULL OR c.module_id = %s)
            """,
            (forge_id, module_id, module_id),
        )
        rows = await cur.fetchall()

    changed: list[tuple[uuid.UUID, str]] = []
    for r in rows:
        if r["live_hash"] is not None and r["instruction_content_hash"] != r["live_hash"]:
            changed.append((r["cert_id"], STALE_INSTRUCTIONS))
            continue
        sensitivity = r["version_sensitivity"] or "major.minor"
        if is_forge_version_stale(
            r["forge_api_version"], r["live_api_version"], sensitivity
        ):
            changed.append((r["cert_id"], STALE_FORGE))

    if changed:
        async with conn.cursor() as cur:
            for cert_id, new_state in changed:
                await cur.execute(
                    "UPDATE certification SET state = %s, updated_at = now() "
                    "WHERE cert_id = %s",
                    (new_state, cert_id),
                )
        await conn.commit()

    return [cert_id for cert_id, _ in changed]
