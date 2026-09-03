"""Declared x Required x In-Use, and the Forge estate behind it.

The Forge Map's subtitle promised a three-way diff and the table had one column. Worse,
the three states came from one place: a `venture_forge_manifest` row was both the
declaration and the requirement, so the diff it claimed to show could not exist. The
sources are genuinely different and only one of them was being read:

    Declared     the Pack's `forge_dependencies.forge_bindings[].modules_expected`
    Required     Generator 5.6 output, in `venture_forge_manifest.is_required`
    In-Use       `agent_call_ledger`, last 30 days

Reading Declared from the live Pack is also what makes the page useful today. The
generators have never run - every provisioning run has been aborted at gate 4 - so
`venture_forge_manifest` is empty and the table rendered nothing at all. The Pack declares
three Forges and nine modules right now, and the honest reading of that is not "nothing
declared": it is that everything is declared, nothing is required yet, and the gap between
those two is the whole finding.
"""

from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

# The four handlers, from Part 15. Each names what happens, because a classification
# nobody acts on is a label.
MISMATCH = {
    "DECLARED_NOT_REQUIRED": (
        "warn",
        "Declared in the Pack and not required by the workflow. Warns: the engagement "
        "is carrying a dependency nothing asks for.",
    ),
    "REQUIRED_NOT_DECLARED": (
        "bad",
        "Required by the workflow and absent from the Pack. Fails the Pack at Gate 3.5 "
        "- an agent would need a module the engagement never declared.",
    ),
    "IN_USE_NOT_REQUIRED": (
        "bad",
        "Being called and required by nothing. Raises a HIGH incident and throttles: "
        "this is the shape of an agent doing work nobody asked for.",
    ),
    "REQUIRED_NOT_IN_USE_30D": (
        "warn",
        "Required and not called in thirty days. Flags for review - either the workflow "
        "changed or something is quietly failing.",
    ),
    "MATCHED": ("ok", "Declared, required, and in use."),
}

# The Forge estate, from the master prompt and CLAUDE.md. Declared here beside the code
# that reads it, exactly as `ventures.PORTFOLIO` is, because four of these have never
# been registered and a page that only lists what the database knows cannot say that a
# Forge is missing.
#
# What is NOT hardcoded is the status of any of them: bridged, instructed and healthy are
# all computed against what exists, so this cannot go on claiming a Forge is unbridged
# after somebody bridges it.
ESTATE = [
    {"forge_id": "cre-forge", "display_name": "CRE Forge",
     "note": "Greenstone's operating Forge. Bridged first under blueprint J4."},
    {"forge_id": "simforge", "display_name": "SimForge",
     "note": "Certification and scenario runs. Every agent meets it before production."},
    {"forge_id": "voiceforge", "display_name": "VoiceForge",
     "note": "Outbound calling and transcription. Carries recording-consent flags."},
    {"forge_id": "capitalforge", "display_name": "CapitalForge",
     "note": "Burkham Wickmont's Forge. Ivan's decision 2026-08-22 puts the bridge "
             "here first, superseding blueprint J4."},
    {"forge_id": "paf", "display_name": "PAF",
     "note": "No bridge and no operating instructions yet."},
    {"forge_id": "medlink-pro", "display_name": "MedLink Pro Forge",
     "note": "Carries PHI. Phase 4 by decision - the temporal PHI wall raises the cost "
             "of every mistake, so it is bridged last."},
    {"forge_id": "funnelforge", "display_name": "FunnelForge",
     "note": "No bridge and no operating instructions yet."},
    {"forge_id": "visionaudioforge", "display_name": "VisionAudioForge",
     "note": "No bridge and no operating instructions yet."},
]


async def reconcile(conn: AsyncConnection, venture_id: str) -> dict[str, Any]:
    """The three-way diff for one venture, and why it is empty if it is."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT parsed FROM business_pack "
            "WHERE venture_id = %s AND status = 'live' LIMIT 1",
            (venture_id,),
        )
        pack_row = await cur.fetchone()

        await cur.execute(
            """
            SELECT forge_id, module_id, is_required, criticality, module_gap
            FROM venture_forge_manifest WHERE venture_id = %s
            """,
            (venture_id,),
        )
        manifest = {(r["forge_id"], r["module_id"]): dict(r) for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT forge_id, module_id, count(*) AS calls
            FROM agent_call_ledger
            WHERE venture_id = %s AND ts_start > now() - interval '30 days'
            GROUP BY forge_id, module_id
            """,
            (venture_id,),
        )
        in_use = {(r["forge_id"], r["module_id"]): int(r["calls"]) for r in await cur.fetchall()}

        # Why there is no manifest, in the terms of the thing that stopped. "Generator
        # 5.6 produces these rows from a Pack" is the mechanism; the reader needs the
        # cause.
        await cur.execute(
            """
            SELECT current_gate, status, count(*) AS n
            FROM provisioning_run WHERE venture_id = %s
            GROUP BY current_gate, status ORDER BY n DESC
            """,
            (venture_id,),
        )
        runs = [dict(r) for r in await cur.fetchall()]

    parsed = (pack_row or {}).get("parsed") or {}
    bindings = (parsed.get("forge_dependencies") or {}).get("forge_bindings") or []

    declared: dict[tuple[str, str], dict[str, Any]] = {}
    for binding in bindings:
        forge = binding.get("forge")
        for module in binding.get("modules_expected") or []:
            declared[(forge, module)] = {
                "criticality": binding.get("criticality"),
                "api_version": binding.get("api_version"),
                "credential_mode": binding.get("credential_mode"),
            }

    rows: list[dict[str, Any]] = []
    required_count = 0
    in_use_count = 0
    for key in sorted(set(declared) | set(manifest) | set(in_use)):
        forge_id, module_id = key
        is_declared = key in declared
        entry = manifest.get(key)
        is_required = bool(entry and entry["is_required"])
        calls = in_use.get(key, 0)

        # Order matters: the most serious classification wins, because a row can be
        # several of these at once and the reader needs the one that acts.
        if calls and not is_required:
            mismatch = "IN_USE_NOT_REQUIRED"
        elif is_required and not is_declared:
            mismatch = "REQUIRED_NOT_DECLARED"
        elif is_required and calls == 0:
            mismatch = "REQUIRED_NOT_IN_USE_30D"
        elif is_declared and not is_required:
            mismatch = "DECLARED_NOT_REQUIRED"
        else:
            mismatch = "MATCHED"

        required_count += 1 if is_required else 0
        in_use_count += 1 if calls > 0 else 0

        tone, meaning = MISMATCH[mismatch]
        rows.append({
            "forge_id": forge_id,
            "module_id": module_id,
            "declared": is_declared,
            "required": is_required,
            "calls_30d": calls,
            "criticality": (declared.get(key) or {}).get("criticality")
            or (entry or {}).get("criticality"),
            "module_gap": bool(entry and entry["module_gap"]),
            "mismatch": mismatch,
            "tone": tone,
            "meaning": meaning,
        })

    blocked = None
    if not manifest:
        stalled = [r for r in runs if r["status"] in ("aborted", "rejected")]
        worst = max(stalled, key=lambda r: r["n"]) if stalled else None
        if worst:
            total = sum(r["n"] for r in stalled if r["current_gate"] == worst["current_gate"])
            blocked = (
                f"No provisioning run has passed gate {worst['current_gate']}, so the "
                f"generators have never produced a manifest for this venture. "
                f"{total} run{'s' if total != 1 else ''} "
                f"{'have' if total != 1 else 'has'} stopped at that gate."
            )
        else:
            blocked = (
                "No provisioning run has reached the generators, so no manifest exists "
                "for this venture yet."
            )

    return {
        "venture_id": venture_id,
        "rows": rows,
        "declared_count": len(declared),
        "required_count": required_count,
        "in_use_count": in_use_count,
        "blocked_reason": blocked,
        "handlers": [
            {"mismatch": name, "tone": tone, "meaning": meaning}
            for name, (tone, meaning) in MISMATCH.items()
            if name != "MATCHED"
        ],
    }


async def matrix(conn: AsyncConnection) -> dict[str, Any]:
    """Ventures x Forges: the blast-radius view, and the upgrade-impact map.

    Read a column to answer "if VoiceForge goes down, which ventures halt" - which is the
    question a Forge release note raises, and the one nothing on this page could answer.
    Criticality comes from the Pack, so `hard` means the Pack said `fallback_behavior:
    halt` rather than somebody's impression.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT venture_id, parsed FROM business_pack WHERE status = 'live'"
        )
        packs = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT venture_id, forge_id, count(*) AS calls
            FROM agent_call_ledger
            WHERE ts_start > now() - interval '30 days'
            GROUP BY venture_id, forge_id
            """
        )
        volume = {(r["venture_id"], r["forge_id"]): int(r["calls"]) for r in await cur.fetchall()}

        await cur.execute(
            "SELECT forge_id, health_status, credential_mode, api_version FROM forge_registry"
        )
        registry = {r["forge_id"]: dict(r) for r in await cur.fetchall()}

    forges = sorted({f["forge_id"] for f in ESTATE} | set(registry))
    cells = []
    for pack in packs:
        parsed = pack["parsed"] or {}
        bindings = {
            b.get("forge"): b
            for b in (parsed.get("forge_dependencies") or {}).get("forge_bindings") or []
        }
        for forge in forges:
            binding = bindings.get(forge)
            cells.append({
                "venture_id": pack["venture_id"],
                "forge_id": forge,
                "declared": binding is not None,
                "criticality": (binding or {}).get("criticality"),
                "fallback": (binding or {}).get("fallback_behavior"),
                "calls_30d": volume.get((pack["venture_id"], forge), 0),
                "health": (registry.get(forge) or {}).get("health_status"),
            })

    return {
        "ventures": [pack["venture_id"] for pack in packs],
        "forges": forges,
        "cells": cells,
    }


async def estate(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Every Forge the portfolio names, bridged or not.

    The map only ever showed the Forges one venture declared, so a Forge with no bridge
    was indistinguishable from a Forge that does not exist. Four of the eight are in that
    state right now, and that is a fact about the portfolio rather than an absence of
    data.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT forge_id, display_name, health_status, credential_mode, "
            "       api_version, last_health_check, deprecation_date "
            "FROM forge_registry"
        )
        registry = {r["forge_id"]: dict(r) for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT forge_id, count(*) AS modules,
                   count(*) FILTER (WHERE superseded_at IS NULL) AS live
            FROM forge_operating_instruction GROUP BY forge_id
            """
        )
        instructions = {r["forge_id"]: dict(r) for r in await cur.fetchall()}

        # What each Pack pinned, so a live version that has moved past it can be named.
        await cur.execute(
            "SELECT venture_id, parsed FROM business_pack WHERE status = 'live'"
        )
        pinned: dict[str, set[str]] = {}
        for row in await cur.fetchall():
            parsed = row["parsed"] or {}
            for binding in (parsed.get("forge_dependencies") or {}).get("forge_bindings") or []:
                if binding.get("forge") and binding.get("api_version"):
                    pinned.setdefault(binding["forge"], set()).add(binding["api_version"])

    known = {f["forge_id"] for f in ESTATE}
    out = []
    for entry in [*ESTATE, *({"forge_id": f, "display_name": f, "note": ""}
                             for f in registry if f not in known)]:
        forge_id = entry["forge_id"]
        live = registry.get(forge_id)
        pins = sorted(pinned.get(forge_id, set()))
        drifted = bool(live and pins and live["api_version"] not in pins)
        out.append({
            **entry,
            "bridged": live is not None,
            "health": (live or {}).get("health_status"),
            "credential_mode": (live or {}).get("credential_mode"),
            "api_version": (live or {}).get("api_version"),
            "last_health_check": (live or {}).get("last_health_check"),
            "deprecation_date": (live or {}).get("deprecation_date"),
            "instruction_modules": (instructions.get(forge_id) or {}).get("live", 0),
            "pinned_versions": pins,
            # A live version past what a Pack pinned invalidates certifications bound to
            # the instructions written for the pinned one.
            "version_drift": drifted,
        })
    return out
