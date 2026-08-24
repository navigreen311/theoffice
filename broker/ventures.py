"""The venture directory: where each venture is, and what is stopping it.

The old directory answered five questions nobody was asking - agent count, grant count,
cap, whether a hard cap had been reversed. The question a reader opens this page with is
*where is this venture and can it go live*, and pipeline state appeared nowhere.

Two rules shape everything here.

**Status is derived from what actually happened**, not stored. A venture blocked at Gate
0 is blocked because the validator says the bridge does not reach its operating Forge,
not because a column says `blocked`. The only stored states are the two nothing can
derive: `archived`, and the draft that exists before a Pack does.

**The blocked reason is the validator's own message.** The brief that asked for this page
supplied three example blocker sentences and one of them - "structural PHI flush is not
built" - stopped being true when Phase 3.3 shipped. A table of blocker strings is
correct the day it is written and wrong afterwards, which is the rot Gate 6's hardcoded
knowledge-base list had. So the sentence comes from the rule that failed.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from broker.errors import OfficeError
from generators.pack import BusinessPack
from generators.validator import Verdict, validate


class VentureError(OfficeError):
    """The venture could not be created or changed as asked."""


# The portfolio, from the master prompt: "MedLink Pro Staffing (operating; HIPAA, HCQC)
# · Greenstone (launching; CRE wholesale; no PHI) · Collingswood & Co. (two-party
# consent, voice-cloning consent) · Burkham Wickmont (TILA, FCRA, ECOA, UDAAP, CROA,
# state lender licensure) · Cybersecurity venture (NRS 648 NV; blocked - CyberForge)".
#
# Declared knowledge, so it is declared here beside the code that uses it rather than
# inferred from a database that has never heard of four of them. What is NOT hardcoded
# is which are missing: that is computed against what exists, so this cannot go on
# claiming a venture is unauthored after somebody authors it.
PORTFOLIO = [
    {
        "slug": "medlink-pro",
        "display_name": "MedLink Pro Staffing",
        "category": "Healthcare staffing",
        "operating_status": "operating",
        "frameworks": ["HIPAA", "HCQC"],
        "note": "Carries PHI. The temporal PHI wall applies to every agent serving it.",
    },
    {
        "slug": "greenstone",
        "display_name": "Greenstone",
        "category": "Commercial real estate wholesaling",
        "operating_status": "launching",
        "frameworks": ["TWO_PARTY_CONSENT_RECORDING", "FTC_TSR"],
        "note": "No PHI and the smallest compliance surface, which is why it is first.",
    },
    {
        "slug": "collingswood",
        "display_name": "Collingswood & Co.",
        "category": "Outbound voice",
        "operating_status": "launching",
        "frameworks": ["TWO_PARTY_CONSENT_RECORDING", "VOICE_CLONING_CONSENT"],
        "note": "Voice cloning consent is a compliance surface no other venture has.",
    },
    {
        "slug": "burkham-wickmont",
        "display_name": "Burkham Wickmont",
        "category": "Capital operations",
        "operating_status": "launching",
        "frameworks": ["TILA", "FCRA", "ECOA", "UDAAP", "CROA"],
        "note": "State lender licensure on top of five federal frameworks.",
    },
    {
        "slug": "cyber",
        "display_name": "Cybersecurity venture",
        "category": "Cybersecurity services",
        "operating_status": "launching",
        "frameworks": ["NRS_648"],
        "note": (
            "Blocked before it starts: CyberForge is a module gap (J7), so this "
            "venture cannot pass Gate 3.5 whatever its Pack says."
        ),
    },
]

# Sixteen gates collapsed into six phases a reader can hold in their head. The mapping
# is the pipeline's own order, so a gate cannot land in the wrong phase by drift.
GATE_PHASES: list[tuple[str, tuple[str, ...]]] = [
    ("bridge", ("0",)),
    ("pack", ("1", "2")),
    ("generate", ("3", "3.5", "4", "4.5")),
    ("certify", ("5", "6", "7", "8", "9", "9.5")),
    ("sign off", ("10", "11")),
    ("live", ("12",)),
]

GATE_ORDER = [g for _phase, gates in GATE_PHASES for g in gates]


def slugify(name: str) -> str:
    """A slug from a display name. Lowercase, hyphenated, no repeats.

    Derived rather than typed, because a slug is a key: every venture-scoped table in
    this schema stores it as text, and a typo produces a second venture rather than an
    error. Editable at creation and immutable after, which the database enforces by
    making it the primary key.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise VentureError(f"{name!r} produces no slug; use letters or digits")
    return slug


@dataclass(frozen=True, slots=True)
class Phase:
    name: str
    state: str
    """`done` | `current` | `todo`."""


def phases_for(gate: str | None, *, live: bool) -> list[Phase]:
    """The six-segment bar. `gate` is where the run stopped, or None if none has run."""
    if live:
        return [Phase(name, "done") for name, _ in GATE_PHASES]

    index = GATE_ORDER.index(gate) if gate in GATE_ORDER else -1
    out: list[Phase] = []
    seen_current = False
    for name, gates in GATE_PHASES:
        last = GATE_ORDER.index(gates[-1])
        if index < 0:
            out.append(Phase(name, "todo"))
        elif index > last:
            out.append(Phase(name, "done"))
        elif not seen_current:
            out.append(Phase(name, "current"))
            seen_current = True
        else:
            out.append(Phase(name, "todo"))
    return out


async def create(
    conn: AsyncConnection,
    *,
    slug: str,
    display_name: str,
    category: str,
    environment: str,
    created_by: uuid.UUID,
) -> str:
    """Register a venture in draft.

    Draft means no Pack, which means no manifest, no runtime config and therefore
    nothing to grant against - the inability to receive grants is structural rather than
    a flag somebody checks.
    """
    if not display_name.strip():
        raise VentureError("a venture needs a display name")
    if not category.strip():
        raise VentureError("a venture needs a category")

    slug = slug.strip() or slugify(display_name)
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise VentureError(
            f"{slug!r} is not a valid slug: lowercase letters, digits and single "
            "hyphens. It is a database key, and a slug with a space is a different key "
            "from the one you typed."
        )

    async with conn.cursor() as cur:
        await cur.execute("SELECT 1 FROM venture WHERE slug = %s", (slug,))
        if await cur.fetchone() is not None:
            raise VentureError(f"a venture with slug {slug!r} already exists")

        await cur.execute(
            """
            INSERT INTO venture
              (slug, display_name, category, environment, lifecycle_state, created_by)
            VALUES (%s, %s, %s, %s, 'draft', %s)
            """,
            (slug, display_name.strip(), category.strip(), environment, created_by),
        )
    await conn.commit()
    return slug


async def set_lifecycle(
    conn: AsyncConnection,
    *,
    slug: str,
    state: str,
    actor: uuid.UUID,
) -> None:
    """Move a venture's lifecycle. Archiving is terminal until explicitly reopened."""
    if state not in ("draft", "active", "winding_down", "archived"):
        raise VentureError(f"unknown lifecycle state {state!r}")

    async with conn.cursor() as cur:
        if state == "archived":
            await cur.execute(
                "UPDATE venture SET lifecycle_state = 'archived', archived_at = now(), "
                "archived_by = %s WHERE slug = %s",
                (actor, slug),
            )
        else:
            await cur.execute(
                "UPDATE venture SET lifecycle_state = %s, archived_at = NULL, "
                "archived_by = NULL WHERE slug = %s",
                (state, slug),
            )
        if cur.rowcount == 0:
            raise VentureError(f"no venture {slug!r}")
    await conn.commit()


async def _status_for(
    conn: AsyncConnection,
    *,
    slug: str,
    registered: dict[str, Any] | None,
    pack: BusinessPack | None,
    run: dict[str, Any] | None,
    assignable_grants: int,
) -> dict[str, Any]:
    """Where this venture is, and what is stopping it.

    First match wins, and the order is the order a reader would ask the questions in.
    Nothing here reads a status column except the two states nothing can derive.
    """
    lifecycle = (registered or {}).get("lifecycle_state")

    if lifecycle == "archived":
        return {"status": "archived", "gate": None, "blocked_because": None}
    if lifecycle == "winding_down" or (
        pack and pack.identity.operating_status == "winding_down"
    ):
        return {"status": "winding down", "gate": None, "blocked_because": None}

    if pack is None:
        return {
            "status": "draft",
            "gate": None,
            "blocked_because": (
                "No Business Pack has been authored. Nothing can be generated, granted "
                "or appointed until one exists."
            ),
        }

    if run and run["status"] == "blocked":
        return {
            "status": f"blocked at gate {run['current_gate']}",
            "gate": run["current_gate"],
            "blocked_because": run["reason"],
        }
    if run and run["status"] == "awaiting_human" and run["current_gate"] == "10":
        return {"status": "awaiting sign-off", "gate": "10", "blocked_because": None}
    if run and run["status"] == "complete":
        return {"status": "live", "gate": "12", "blocked_because": None}
    if run and run["current_gate"] in ("8", "9", "9.5"):
        return {"status": "in certification", "gate": run["current_gate"],
                "blocked_because": None}

    if assignable_grants > 0:
        return {"status": "live", "gate": "12", "blocked_because": None}

    # No run, or a run in progress. The world still has an answer: Gate 0 and Gate 2 can
    # be evaluated directly, which is how a venture reports "blocked at gate 0 - the
    # bridge does not reach CRE Forge" without anybody having started a run.
    report = await validate(pack, conn)
    bridge = report.get("V2")
    if bridge.verdict is Verdict.FAIL:
        return {
            "status": "blocked at gate 0",
            "gate": "0",
            # The validator's own message, which already names the Forge and why it does
            # not resolve. A lookup table of blocker sentences would be right once.
            "blocked_because": (
                f"{bridge.message} No agent can be granted or appointed until the "
                "bridge reaches it."
            ),
        }
    if report.failures:
        first = report.failures[0]
        return {
            "status": "validating",
            "gate": "2",
            "blocked_because": (
                f"{len(report.failures)} validator rule(s) fail. "
                f"{first.rule_id}: {first.message}"
            ),
        }

    if run:
        return {"status": f"blocked at gate {run['current_gate']}",
                "gate": run["current_gate"],
                "blocked_because": run.get("reason")}

    return {
        "status": "blocked at gate 1",
        "gate": "1",
        "blocked_because": (
            "The Pack validates and no provisioning run has been started. Start one "
            "from the Provisioning console."
        ),
    }


async def directory(conn: AsyncConnection) -> dict[str, Any]:
    """Every venture, where it is, and what is missing from the portfolio."""
    from broker import packs  # local: packs imports generators, which imports this file

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT * FROM venture ORDER BY slug")
        registered = {r["slug"]: dict(r) for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT v.venture_id,
                   -- count(g.grant_id), not count(*). A LEFT JOIN that matches
                   -- nothing still produces one row with every g column NULL, and
                   -- `g.revoked_at IS NULL` is TRUE for it - so count(*) reported one
                   -- live grant for a venture that has none. Counting a column skips
                   -- the null row, which is the whole difference.
                   count(g.grant_id) FILTER (WHERE g.is_assignable) AS assignable_grants,
                   count(g.grant_id) FILTER (WHERE g.revoked_at IS NULL) AS live_grants,
                   count(DISTINCT g.office_agent_id) FILTER (WHERE g.is_assignable)
                     AS agents_appointed,
                   b.monthly_usd_cap, b.hard_cap_action, b.soft_cap_pct,
                   b.hard_cap_reversed_at
            FROM (SELECT DISTINCT venture_id FROM agent_forge_grant
                  UNION SELECT DISTINCT venture_id FROM venture_forge_manifest
                  UNION SELECT venture_id FROM venture_budget
                  UNION SELECT venture_id FROM business_pack
                  UNION SELECT slug FROM venture) v
            LEFT JOIN agent_forge_grant g ON g.venture_id = v.venture_id
            LEFT JOIN venture_budget b ON b.venture_id = v.venture_id
            GROUP BY v.venture_id, b.monthly_usd_cap, b.hard_cap_action,
                     b.soft_cap_pct, b.hard_cap_reversed_at
            ORDER BY v.venture_id
            """
        )
        rows = [dict(r) for r in await cur.fetchall()]

        await cur.execute(
            """
            SELECT DISTINCT ON (venture_id)
                   venture_id, status, current_gate
            FROM provisioning_run ORDER BY venture_id, started_at DESC
            """
        )
        runs = {r["venture_id"]: dict(r) for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT venture_id, max(ts) AS last_activity
            FROM audit_log WHERE venture_id IS NOT NULL GROUP BY venture_id
            """
        )
        activity = {r["venture_id"]: r["last_activity"] for r in await cur.fetchall()}

        await cur.execute(
            """
            SELECT venture_id, coalesce(sum(usd_cost), 0) AS spend
            FROM agent_call_ledger
            WHERE ts_start >= date_trunc('month', now())
            GROUP BY venture_id
            """
        )
        spend = {r["venture_id"]: float(r["spend"] or 0) for r in await cur.fetchall()}

        await cur.execute("SELECT entry_ref, runtime_flag FROM compliance_library_entry")
        library = [dict(r) for r in await cur.fetchall()]

    entry_refs = {e["entry_ref"] for e in library}
    library_flags = {e["runtime_flag"] for e in library if e["runtime_flag"]}

    # A gate result carries the reason a run stopped. Fetched per run rather than joined,
    # because there are a handful of ventures and the join is harder to read than the
    # loop.
    for venture_id, run in runs.items():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT reason FROM provisioning_gate_result r "
                "JOIN provisioning_run pr USING (run_id) "
                "WHERE pr.venture_id = %s AND r.gate = %s "
                "ORDER BY r.recorded_at DESC LIMIT 1",
                (venture_id, run["current_gate"]),
            )
            reason = await cur.fetchone()
        run["reason"] = reason["reason"] if reason else None

    out: list[dict[str, Any]] = []
    for row in rows:
        slug = row["venture_id"]
        stored = registered.get(slug)
        live_pack = await packs.live(conn, slug)
        pack = live_pack.pack if live_pack else None

        state = await _status_for(
            conn, slug=slug, registered=stored, pack=pack, run=runs.get(slug),
            assignable_grants=int(row["assignable_grants"]),
        )

        positions = sum(p.headcount for p in pack.positions_required) if pack else 0
        frameworks = []
        if pack:
            for surface in pack.market.compliance_surface:
                ref = surface.library_entry_ref
                flag = surface.runtime_flag
                frameworks.append({
                    "framework": surface.framework,
                    "wired": bool(flag) and (
                        (ref in entry_refs) or (flag in library_flags)
                    ),
                })

        out.append({
            "slug": slug,
            "display_name": (
                pack.identity.venture_name if pack
                else (stored or {}).get("display_name") or slug
            ),
            "category": (
                pack.identity.category if pack
                else (stored or {}).get("category") or "uncategorised"
            ),
            # PHI is a property of the frameworks a Pack declares, not a flag. HIPAA
            # is the one that brings the temporal wall with it; naming it explicitly
            # rather than pattern-matching means a new framework has to be considered
            # rather than silently matching or silently not.
            "carries_phi": any(
                f["framework"] in ("HIPAA", "HCQC") for f in frameworks
            ),
            "operating_forge": pack.forge_dependencies.operating_forge if pack else None,
            "registered": stored is not None,
            "has_pack": pack is not None,
            "pack_version": live_pack.pack_version if live_pack else None,
            **state,
            "phases": [
                {"name": p.name, "state": p.state}
                for p in phases_for(state["gate"], live=state["status"] == "live")
            ],
            "gate_index": (
                GATE_ORDER.index(state["gate"]) if state["gate"] in GATE_ORDER else -1
            ),
            "gate_total": len(GATE_ORDER),
            "positions_filled": int(row["agents_appointed"]),
            "positions_defined": positions,
            "live_grants": int(row["live_grants"]),
            "monthly_usd_cap": (
                float(row["monthly_usd_cap"]) if row["monthly_usd_cap"] else None
            ),
            "hard_cap_action": row["hard_cap_action"],
            "soft_cap_pct": row["soft_cap_pct"],
            "hard_cap_reversed_at": row["hard_cap_reversed_at"],
            "spend_this_month": spend.get(slug, 0.0),
            "frameworks": frameworks,
            "frameworks_wired": sum(1 for f in frameworks if f["wired"]),
            "last_activity": (
                activity[slug].isoformat() if activity.get(slug) else None
            ),
        })

    known = {v["slug"] for v in out}
    missing = [p for p in PORTFOLIO if p["slug"] not in known]

    live_count = sum(1 for v in out if v["status"] == "live")
    blocked = sum(1 for v in out if v["status"].startswith("blocked"))
    total_cap = sum(v["monthly_usd_cap"] or 0 for v in out)
    total_spend = sum(v["spend_this_month"] for v in out)

    async with conn.cursor() as cur:
        await cur.execute("SELECT count(*) FROM office_agent_identity")
        row2 = await cur.fetchone()
    agents_known = int(row2[0]) if row2 else 0

    return {
        "ventures": out,
        "missing": missing,
        "portfolio_size": len(PORTFOLIO),
        "scorecard": {
            "live": {"value": live_count, "denominator": len(out)},
            "agents_appointed": {
                "value": sum(v["positions_filled"] for v in out),
                "denominator": agents_known,
                "note": (
                    "of the agents The Office knows. The Village roster has not been "
                    "imported (Phase 0.2)."
                ),
            },
            "spend_this_month": {
                "value": total_spend,
                "denominator": total_cap,
                "note": (
                    "Cost attribution is not wired: Forges report no usage, so this "
                    "reads zero because nothing is measured rather than because "
                    "nothing was spent."
                ),
            },
            "blocked": {"value": blocked, "denominator": len(out)},
        },
    }


__all__ = [
    "GATE_PHASES",
    "PORTFOLIO",
    "VentureError",
    "create",
    "directory",
    "phases_for",
    "set_lifecycle",
    "slugify",
]
