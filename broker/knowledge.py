"""The four knowledge bases Part 6 names and Phase 3 did not build.

Forge Operating Instructions live in `broker/instructions.py` and are the model for
these: a table with a screen over it is a filing cabinet, and 6.1 became curriculum
because of one property - `content_hash` binds certification, so republishing
decertifies. Each store here has its own equivalent, and the property is the reason the
store exists rather than a nicety on top of it.

  * **Playbooks** are invisible outside their venture until somebody consents in
    writing. The read path takes a venture and resolves shares; there is no unscoped
    read to forget to filter.
  * **Compliance entries** carry all six of Part 6.3's fields or they do not exist, and
    `entry_ref` is what a Pack's `library_entry_ref` resolves against - which is what
    turns V4 from a claim into a check.
  * **Personas** can be written here and not read back. `office_app` holds no SELECT on
    `persona_body`, so the absence is a privilege error rather than a missing function.
  * **Historical records** are append-only at the database, and something writes them
    on day one. A store nobody writes to is Phase 4.1's inert control in a new costume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class KnowledgeError(Exception):
    """The store refused. The message says which rule."""


# ============================================================ 6.2 business playbooks

@dataclass(frozen=True, slots=True)
class Playbook:
    playbook_id: uuid.UUID
    venture_id: str
    title: str
    lifecycle_stage: str | None
    playbook_version: str
    content_hash: str
    content: dict[str, Any]
    shared_from: str | None = None
    """Set when this playbook reached the reader through a share, not by ownership."""


async def author_playbook(
    conn: AsyncConnection,
    *,
    venture_id: str,
    title: str,
    playbook_version: str,
    content: dict[str, Any],
    authored_by: uuid.UUID,
    lifecycle_stage: str | None = None,
) -> Playbook:
    """Publish a playbook version, superseding the live one with the same title."""
    if not title.strip():
        raise KnowledgeError("a playbook needs a title")
    if not content:
        raise KnowledgeError("a playbook with no content is a title")

    playbook_id = uuid.uuid4()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "UPDATE business_playbook SET superseded_at = now() "
            "WHERE venture_id = %s AND title = %s AND superseded_at IS NULL",
            (venture_id, title),
        )
        await cur.execute(
            """
            INSERT INTO business_playbook
              (playbook_id, venture_id, title, lifecycle_stage, content, content_hash,
               playbook_version, authored_by)
            VALUES (%s, %s, %s, %s, %s, '', %s, %s)
            RETURNING content_hash
            """,
            (playbook_id, venture_id, title, lifecycle_stage, Jsonb(content),
             playbook_version, authored_by),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None
    return Playbook(
        playbook_id=playbook_id, venture_id=venture_id, title=title,
        lifecycle_stage=lifecycle_stage, playbook_version=playbook_version,
        content_hash=row["content_hash"], content=content,
    )


async def share_playbook(
    conn: AsyncConnection,
    *,
    playbook_id: uuid.UUID,
    to_venture_id: str,
    shared_by: uuid.UUID,
    reason: str,
) -> None:
    """Part 6.2: opt-in only, and the opt-in is a row with a reason on it.

    A share with no reason is a share nobody can review later, and cross-venture
    disclosure is exactly the decision somebody will want reviewed.
    """
    if not reason.strip():
        raise KnowledgeError("sharing a playbook across ventures requires a reason")

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT venture_id FROM business_playbook WHERE playbook_id = %s",
            (playbook_id,),
        )
        owner = await cur.fetchone()
        if owner is None:
            raise KnowledgeError(f"no playbook {playbook_id}")
        if owner[0] == to_venture_id:
            raise KnowledgeError(
                "a venture already sees its own playbooks; sharing one to itself would "
                "create a share row that means nothing and can later be revoked to no "
                "effect"
            )
        await cur.execute(
            """
            INSERT INTO playbook_share
              (playbook_id, to_venture_id, shared_by, reason)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (playbook_id, to_venture_id) DO UPDATE
            SET revoked_at = NULL, shared_at = now(),
                shared_by = EXCLUDED.shared_by, reason = EXCLUDED.reason
            """,
            (playbook_id, to_venture_id, shared_by, reason),
        )
    await conn.commit()


async def revoke_share(
    conn: AsyncConnection, *, playbook_id: uuid.UUID, to_venture_id: str
) -> None:
    """Withdraw consent. The row stays, so the history of who saw what survives."""
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE playbook_share SET revoked_at = now() "
            "WHERE playbook_id = %s AND to_venture_id = %s AND revoked_at IS NULL",
            (playbook_id, to_venture_id),
        )
    await conn.commit()


async def playbooks_for(conn: AsyncConnection, venture_id: str) -> list[Playbook]:
    """Everything this venture may see: its own, plus what has been shared to it.

    One query with the share join built in, deliberately. A function that returned all
    playbooks and left scoping to the caller would work correctly every time until the
    one call site that forgot, and that call site would look exactly like the others.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT p.playbook_id, p.venture_id, p.title, p.lifecycle_stage,
                   p.playbook_version, p.content_hash, p.content,
                   CASE WHEN p.venture_id = %s THEN NULL ELSE p.venture_id END
                     AS shared_from
            FROM business_playbook p
            LEFT JOIN playbook_share s
              ON s.playbook_id = p.playbook_id
             AND s.to_venture_id = %s
             AND s.revoked_at IS NULL
            WHERE p.superseded_at IS NULL
              AND (p.venture_id = %s OR s.playbook_id IS NOT NULL)
            ORDER BY p.venture_id, p.title
            """,
            (venture_id, venture_id, venture_id),
        )
        return [
            Playbook(
                playbook_id=r["playbook_id"], venture_id=r["venture_id"],
                title=r["title"], lifecycle_stage=r["lifecycle_stage"],
                playbook_version=r["playbook_version"],
                content_hash=r["content_hash"], content=r["content"],
                shared_from=r["shared_from"],
            )
            for r in await cur.fetchall()
        ]


async def list_shares(conn: AsyncConnection) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT s.playbook_id::text AS playbook_id, p.title, p.venture_id AS from_venture,
                   s.to_venture_id, s.reason, s.shared_at, s.revoked_at
            FROM playbook_share s JOIN business_playbook p USING (playbook_id)
            ORDER BY s.shared_at DESC
            """
        )
        return [dict(r) for r in await cur.fetchall()]


# =========================================================== 6.3 compliance library

REQUIRED_ENTRY_FIELDS = (
    "framework",
    "jurisdiction",
    "applicability_rule",
    "agent_behavior_implication",
    "escalation_trigger",
    "citation",
)


async def author_compliance_entry(
    conn: AsyncConnection,
    *,
    entry_ref: str,
    framework: str,
    jurisdiction: list[str],
    applicability_rule: str,
    agent_behavior_implication: str,
    escalation_trigger: str,
    citation: str,
    authored_by: uuid.UUID,
    runtime_flag: str | None = None,
) -> str:
    """Part 6.3's six fields, checked here as well as by the table.

    Checked twice on purpose: the constraint is the control and cannot be argued with,
    and this raises a message that names the missing field rather than surfacing a check
    constraint violation an operator has to decode.
    """
    values = {
        "framework": framework,
        "jurisdiction": jurisdiction,
        "applicability_rule": applicability_rule,
        "agent_behavior_implication": agent_behavior_implication,
        "escalation_trigger": escalation_trigger,
        "citation": citation,
    }
    missing = [
        name for name in REQUIRED_ENTRY_FIELDS
        if not (values[name] if isinstance(values[name], list) else str(values[name]).strip())
    ]
    if missing:
        raise KnowledgeError(
            f"a compliance entry needs all six of Part 6.3's fields; missing: "
            f"{', '.join(missing)}. An entry with a citation and no behavioural "
            "implication is a reference nobody can act on."
        )
    if not entry_ref.strip():
        raise KnowledgeError("entry_ref is what a Pack resolves against; it is required")

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO compliance_library_entry
              (entry_ref, framework, jurisdiction, applicability_rule,
               agent_behavior_implication, escalation_trigger, citation, runtime_flag,
               authored_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entry_ref) DO UPDATE
            SET framework = EXCLUDED.framework,
                jurisdiction = EXCLUDED.jurisdiction,
                applicability_rule = EXCLUDED.applicability_rule,
                agent_behavior_implication = EXCLUDED.agent_behavior_implication,
                escalation_trigger = EXCLUDED.escalation_trigger,
                citation = EXCLUDED.citation,
                runtime_flag = EXCLUDED.runtime_flag,
                updated_at = now()
            """,
            (entry_ref, framework, jurisdiction, applicability_rule,
             agent_behavior_implication, escalation_trigger, citation, runtime_flag,
             authored_by),
        )
    await conn.commit()
    return entry_ref


async def compliance_entries(conn: AsyncConnection) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT entry_ref, framework, jurisdiction, applicability_rule, "
            "       agent_behavior_implication, escalation_trigger, citation, "
            "       runtime_flag, authored_at, updated_at "
            "FROM compliance_library_entry ORDER BY entry_ref"
        )
        return [dict(r) for r in await cur.fetchall()]


async def resolve_entry_refs(
    conn: AsyncConnection, refs: list[str]
) -> tuple[list[str], list[str]]:
    """Which of these refs exist. Returns (resolved, unresolved).

    Both halves, because "3 of 5 resolved" and "3 resolved" are different reports and
    only one of them tells you to go and write something.
    """
    if not refs:
        return [], []
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT entry_ref FROM compliance_library_entry WHERE entry_ref = ANY(%s)",
            (refs,),
        )
        found = {r[0] for r in await cur.fetchall()}
    return sorted(found), sorted(set(refs) - found)


async def flags_with_entries(conn: AsyncConnection) -> set[str]:
    """Runtime flags the library can explain."""
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT runtime_flag FROM compliance_library_entry "
            "WHERE runtime_flag IS NOT NULL"
        )
        return {r[0] for r in await cur.fetchall()}


# =============================================================== 6.4 persona library

async def author_persona(
    conn: AsyncConnection,
    *,
    venture_id: str,
    persona_name: str,
    target_persona: str,
    persona_version: str,
    persona_body: dict[str, Any],
    authored_by: uuid.UUID,
) -> uuid.UUID:
    """Write a persona. There is deliberately no function that reads one back.

    Part 6.4 is one line - "SimForge only, never production" - and the enforcement is a
    column privilege rather than the absence of a getter: `office_app` holds INSERT on
    `persona` and no SELECT on `persona_body`. Someone adding a read function later gets
    a privilege error, not a leak.
    """
    if not persona_body:
        raise KnowledgeError("a persona with an empty body teaches SimForge nothing")

    persona_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE persona SET superseded_at = now() "
            "WHERE venture_id = %s AND persona_name = %s AND superseded_at IS NULL",
            (venture_id, persona_name),
        )
        await cur.execute(
            """
            INSERT INTO persona
              (persona_id, venture_id, persona_name, target_persona, persona_version,
               persona_body, body_hash, authored_by)
            VALUES (%s, %s, %s, %s, %s, %s, '', %s)
            """,
            (persona_id, venture_id, persona_name, target_persona, persona_version,
             Jsonb(persona_body), authored_by),
        )
    await conn.commit()
    return persona_id


async def persona_index(
    conn: AsyncConnection, venture_id: str | None = None
) -> list[dict[str, Any]]:
    """Names, targets and hashes. **Never bodies** - the role cannot read them."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT persona_id::text AS persona_id, venture_id, persona_name, "
            "       target_persona, persona_version, body_hash, authored_at "
            "FROM persona "
            "WHERE superseded_at IS NULL AND (%s::text IS NULL OR venture_id = %s) "
            "ORDER BY venture_id, persona_name",
            (venture_id, venture_id),
        )
        return [dict(r) for r in await cur.fetchall()]


# ============================================================ 6.5 historical records

async def record(
    conn: AsyncConnection,
    *,
    record_type: str,
    summary: str,
    venture_id: str | None = None,
    detail: dict[str, Any] | None = None,
    actor_type: str = "system",
    recorded_by: uuid.UUID | None = None,
) -> int:
    """Append one institutional fact.

    Append-only at the database, so this is the only way in and there is no way back
    out. `summary` is required because a record nobody can read at a glance is an
    archive rather than a memory.
    """
    if not summary.strip():
        raise KnowledgeError("a historical record needs a summary")

    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO historical_record
              (venture_id, record_type, summary, detail, actor_type, recorded_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING record_id
            """,
            (venture_id, record_type, summary, Jsonb(detail or {}), actor_type,
             recorded_by),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None
    return int(row[0])


async def history(
    conn: AsyncConnection, *, venture_id: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT record_id, venture_id, record_type, summary, detail, actor_type, "
            "       recorded_by, occurred_at, recorded_at "
            "FROM historical_record "
            "WHERE (%s::text IS NULL OR venture_id = %s) "
            "ORDER BY occurred_at DESC, record_id DESC LIMIT %s",
            (venture_id, venture_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


__all__ = [
    "KnowledgeError",
    "Playbook",
    "author_compliance_entry",
    "author_persona",
    "author_playbook",
    "compliance_entries",
    "flags_with_entries",
    "history",
    "list_shares",
    "persona_index",
    "playbooks_for",
    "record",
    "resolve_entry_refs",
    "revoke_share",
    "share_playbook",
]
