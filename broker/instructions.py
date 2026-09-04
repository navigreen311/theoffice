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

#: Part 6.1's eight, enforced by a CHECK constraint on the table.
#:
#: TWO OF THESE ARE ROUTINELY WRITTEN AS SOMETHING ELSE, and every CapitalForge
#: manual authored so far - seven of seven - needed one or both fixed first. That is
#: a section title reading as an invitation to write something adjacent, not seven
#: authors making seven mistakes. See docs/certification.md.
#:
#:   correct_sequence  THE ORDERED STEPS AN AGENT TAKES. Not context, not what comes
#:                     back, not what the section is about. Six manuals opened it
#:                     with "there is none" and then described a sequence in the
#:                     paragraph underneath.
#:
#:   inputs            THE PARAMETERS A CALLER SUPPLIES AND WHAT EACH MEANS. Not
#:                     what comes back. Include what the caller does NOT supply and
#:                     where it comes from instead - a tenant read from the token
#:                     decides what the call can reach, and an agent that thinks it
#:                     can set one is wrong about the module.
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


# ------------------------------------------------------------------- the directory

async def directory(conn: AsyncConnection) -> dict[str, Any]:
    """Every module with instructions, assessed by what those instructions contain.

    `authored` meant a row exists. The live cre-forge set satisfies that with
    `"what_it_does": "Documented."` and 234 certifications across the portfolio bound to
    its hash, so the column said `authored` about a document that teaches nothing.

    Also reports the Forges that have no instruction set at all. No agent can be
    certified to operate a module on one of them, and a page listing only the Forges it
    found cannot say which it did not.
    """
    from broker.curriculum_quality import assess

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT i.forge_id, i.module_id, i.instruction_version, i.forge_api_version,
                   i.version_sensitivity, i.sensitivity_rationale, i.content,
                   i.content_hash, i.authored_at,
                   h.display_name AS author,
                   m.module_name, m.is_mutating, m.idempotency_support,
                   m.compliance_flags_implied,
                   r.api_version AS forge_current_version, r.health_status,
                   count(c.cert_id) FILTER (
                     WHERE c.state = 'certified'
                   ) AS certifications
            FROM forge_operating_instruction i
            LEFT JOIN office_human h ON h.human_id = i.authored_by
            LEFT JOIN forge_module_registry m
                   ON m.forge_id = i.forge_id AND m.module_id = i.module_id
            LEFT JOIN forge_registry r ON r.forge_id = i.forge_id
            LEFT JOIN certification c
                   ON c.instruction_content_hash = i.content_hash
                  AND c.forge_id = i.forge_id AND c.module_id = i.module_id
            WHERE i.superseded_at IS NULL
            GROUP BY i.forge_id, i.module_id, i.instruction_version,
                     i.forge_api_version, i.version_sensitivity,
                     i.sensitivity_rationale, i.content, i.content_hash, i.authored_at,
                     h.display_name, m.module_name, m.is_mutating,
                     m.idempotency_support, m.compliance_flags_implied,
                     r.api_version, r.health_status
            ORDER BY i.forge_id, i.module_id
            """
        )
        rows = [dict(r) for r in await cur.fetchall()]

        # Modules the registry knows that nobody has written instructions for. No agent
        # can be certified to operate one, so the gap is the point rather than a
        # rounding error in a count.
        await cur.execute(
            """
            SELECT m.forge_id, m.module_id, m.module_name
            FROM forge_module_registry m
            WHERE NOT EXISTS (
              SELECT 1 FROM forge_operating_instruction i
              WHERE i.forge_id = m.forge_id AND i.module_id = m.module_id
                AND i.superseded_at IS NULL
            )
            ORDER BY m.forge_id, m.module_id
            """
        )
        unwritten = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            "SELECT forge_id, api_version, health_status FROM forge_registry "
            "ORDER BY forge_id"
        )
        forges = [dict(r) for r in await cur.fetchall()]

    modules: list[dict[str, Any]] = []
    for row in rows:
        quality = assess(row["content"])
        # `version_sensitivity` decides when a Forge release invalidates certification.
        # `major.minor` means a minor bump does it, so a Forge that has moved past the
        # version this was authored against has already invalidated it.
        stale_forge = _forge_moved_past(
            row["forge_api_version"],
            row["forge_current_version"],
            row["version_sensitivity"],
        )
        modules.append({
            "forge_id": row["forge_id"],
            "module_id": row["module_id"],
            "module_name": row["module_name"],
            "instruction_version": row["instruction_version"],
            "forge_api_version": row["forge_api_version"],
            "forge_current_version": row["forge_current_version"],
            "version_sensitivity": row["version_sensitivity"],
            "sensitivity_rationale": row["sensitivity_rationale"],
            "content_hash": row["content_hash"],
            "authored_at": row["authored_at"].isoformat() if row["authored_at"] else None,
            "author": row["author"],
            "is_mutating": row["is_mutating"],
            "idempotency_support": row["idempotency_support"],
            "compliance_flags_implied": row["compliance_flags_implied"],
            "certifications": int(row["certifications"] or 0),
            "quality": quality,
            "stale_forge": stale_forge,
            # The finding this page exists for: a certification is a statement about a
            # document, and this document says nothing.
            "certifications_on_hollow": (
                int(row["certifications"] or 0) if quality["teaches_nothing"] else 0
            ),
        })

    by_forge: dict[str, dict[str, Any]] = {}
    for forge in forges:
        mine = [m for m in modules if m["forge_id"] == forge["forge_id"]]
        missing = [u for u in unwritten if u["forge_id"] == forge["forge_id"]]
        by_forge[forge["forge_id"]] = {
            "forge_id": forge["forge_id"],
            "api_version": forge["api_version"],
            "health_status": forge["health_status"],
            "modules": mine,
            "unwritten": missing,
            "written": len(mine),
            "total": len(mine) + len(missing),
            "stub": len([m for m in mine if m["quality"]["state"] in ("stub", "missing")]),
            "thin": len([m for m in mine if m["quality"]["state"] == "thin"]),
        }

    hollow = [m for m in modules if m["quality"]["teaches_nothing"]]
    return {
        "forges": list(by_forge.values()),
        "modules": modules,
        "unwritten": unwritten,
        "totals": {
            "modules_with_instructions": len(modules),
            "forges_with_instructions": len(
                {m["forge_id"] for m in modules}
            ),
            "forges_registered": len(forges),
            "complete": len([m for m in modules if m["quality"]["state"] == "complete"]),
            "thin": len([m for m in modules if m["quality"]["state"] == "thin"]),
            "hollow": len(hollow),
            "modules_without_instructions": len(unwritten),
            # The number that matters: certifications resting on a document that
            # teaches nothing.
            "certifications_on_hollow": sum(
                m["certifications_on_hollow"] for m in modules
            ),
        },
    }


def _forge_moved_past(
    authored_against: str | None, current: str | None, sensitivity: str | None
) -> str | None:
    """Whether the Forge has released past the point this curriculum tolerates.

    `major.minor` means a minor release invalidates certification; `major` means only a
    major one does. Returns the reason when it has moved, `None` when it has not - a
    boolean would lose the version numbers, which are the only useful part.
    """
    if not authored_against or not current or authored_against == current:
        return None

    def parts(version: str) -> list[int]:
        out = []
        for piece in version.split("."):
            try:
                out.append(int(piece))
            except ValueError:
                out.append(0)
        return [*out, 0, 0, 0][:3]

    was, now = parts(authored_against), parts(current)
    depth = {"major": 1, "major.minor": 2, "major.minor.patch": 3}.get(
        sensitivity or "major.minor", 2
    )
    if was[:depth] != now[:depth]:
        return (
            f"authored against {authored_against}; the Forge is on {current}, and "
            f"sensitivity is {sensitivity}"
        )
    return None


async def certifications_on(
    conn: AsyncConnection, forge_id: str, module_id: str, content_hash: str
) -> list[dict[str, Any]]:
    """The agents certified against this exact text.

    Named rather than counted, because "2 agents are certified against a stub" is a
    number and "Ada Sourcing and Bram Records are" is a list of people whose
    certifications have to be redone.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT c.office_agent_id::text AS office_agent_id, i.agent_name,
                   i.department, c.state, c.certified_tier, c.updated_at
            FROM certification c
            LEFT JOIN office_agent_identity i
                   ON i.office_agent_id = c.office_agent_id
            WHERE c.forge_id = %s AND c.module_id = %s
              AND c.instruction_content_hash = %s
            ORDER BY i.agent_name
            """,
            (forge_id, module_id, content_hash),
        )
        return [dict(r) for r in await cur.fetchall()]
