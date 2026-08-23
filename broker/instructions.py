"""Forge Operating Instructions — authoring, versioning, staleness, diff.

Part 6.1. These are not documentation. They are the curriculum agents are educated on
and the thing SimForge tests against, and `content_hash` is what binds a certification
to a specific text. Rewrite the instructions and every certification against the old
text becomes stale — which is the entire point, and why the hash is computed in the
database rather than accepted from a caller.

Exactly one instruction set per module is live at a time. Two would make "the current
content_hash" ambiguous, and staleness is defined by comparison against it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

REQUIRED_SECTIONS = (
    "what_it_does",
    "what_it_does_not_do",
    "inputs",
    "correct_sequence",
    "failure_signatures",
    "retry_vs_escalate",
    "never_do",
    "compliance_coupling",
)


class InstructionError(Exception):
    """Authoring refused. Not an OfficeError: this is a human authoring action,
    not a step in the agent call path, and conflating the two would put authoring
    mistakes into the agent audit trail as call refusals."""


@dataclass(frozen=True, slots=True)
class Instruction:
    forge_id: str
    module_id: str
    instruction_version: str
    forge_api_version: str
    version_sensitivity: str
    content_hash: str
    content: dict[str, Any]


def validate_sections(content: dict[str, Any]) -> None:
    """Reject an incomplete curriculum before the database has to.

    The CHECK constraint is the control; this exists to name *which* section is
    missing, because 'violates constraint instruction_has_all_sections' does not
    tell an author what to write.
    """
    missing = [s for s in REQUIRED_SECTIONS if s not in content]
    if missing:
        raise InstructionError(
            f"instructions are missing required section(s): {', '.join(missing)}. "
            f"Part 6.1 requires all of: {', '.join(REQUIRED_SECTIONS)}"
        )
    empty = [s for s in REQUIRED_SECTIONS if not content[s]]
    if empty:
        raise InstructionError(
            f"section(s) present but empty: {', '.join(empty)}. "
            "An empty failure_signatures section teaches nothing about the case "
            "that matters."
        )


async def author(
    conn: AsyncConnection,
    *,
    forge_id: str,
    module_id: str,
    instruction_version: str,
    forge_api_version: str,
    content: dict[str, Any],
    authored_by: uuid.UUID,
    version_sensitivity: str = "major.minor",
    sensitivity_rationale: str | None = None,
) -> Instruction:
    """Publish a new instruction version, superseding the current live one.

    Supersede-then-insert in one transaction: between the two statements there is
    no live instruction set for the module, and a concurrent staleness recompute
    would see zero and mark everything stale.
    """
    validate_sections(content)

    if version_sensitivity == "major.minor.patch" and not (sensitivity_rationale or "").strip():
        raise InstructionError(
            "version_sensitivity 'major.minor.patch' requires a rationale: it "
            "decertifies every agent on this module at every patch release."
        )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "UPDATE forge_operating_instruction SET superseded_at = now() "
            "WHERE forge_id = %s AND module_id = %s AND superseded_at IS NULL",
            (forge_id, module_id),
        )
        await cur.execute(
            """
            INSERT INTO forge_operating_instruction
              (forge_id, module_id, instruction_version, forge_api_version,
               version_sensitivity, sensitivity_rationale, content, content_hash,
               authored_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, '', %s)
            RETURNING content_hash
            """,
            (
                forge_id, module_id, instruction_version, forge_api_version,
                version_sensitivity, sensitivity_rationale, Jsonb(content), authored_by,
            ),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None

    return Instruction(
        forge_id=forge_id,
        module_id=module_id,
        instruction_version=instruction_version,
        forge_api_version=forge_api_version,
        version_sensitivity=version_sensitivity,
        content_hash=row["content_hash"],
        content=content,
    )


async def live(
    conn: AsyncConnection, *, forge_id: str, module_id: str
) -> Instruction | None:
    """The instruction set currently in force for this module."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM forge_operating_instruction "
            "WHERE forge_id = %s AND module_id = %s AND superseded_at IS NULL",
            (forge_id, module_id),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return Instruction(
        forge_id=row["forge_id"],
        module_id=row["module_id"],
        instruction_version=row["instruction_version"],
        forge_api_version=row["forge_api_version"],
        version_sensitivity=row["version_sensitivity"],
        content_hash=row["content_hash"],
        content=row["content"],
    )


async def diff(
    conn: AsyncConnection,
    *,
    forge_id: str,
    module_id: str,
    from_version: str,
    to_version: str,
) -> dict[str, list[str]]:
    """Which sections changed between two versions.

    Section-level rather than line-level on purpose: the question an author and a
    reviewer actually ask is "did the never-do list change", and a line diff
    buries that answer in reformatting.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT instruction_version, content FROM forge_operating_instruction "
            "WHERE forge_id = %s AND module_id = %s AND instruction_version = ANY(%s)",
            (forge_id, module_id, [from_version, to_version]),
        )
        rows = {r["instruction_version"]: r["content"] for r in await cur.fetchall()}

    for v in (from_version, to_version):
        if v not in rows:
            raise InstructionError(f"no instruction version {v!r} for this module")

    before, after = rows[from_version], rows[to_version]
    keys = set(before) | set(after)
    return {
        "changed": sorted(k for k in keys if k in before and k in after
                          and before[k] != after[k]),
        "added": sorted(k for k in keys if k not in before),
        "removed": sorted(k for k in keys if k not in after),
    }
