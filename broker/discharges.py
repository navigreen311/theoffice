"""Filing a discharge: the operator surface migration 0032 named and nobody built.

0032's own comment said it: *"a discharge is filed by a named human through an operator
surface, never by a broker call, so office_app gets SELECT and nothing more."* The
reasoning was right and the surface did not exist, so for two weeks the only way to file
one was hand-run SQL over the admin DSN - which writes no audit event, and is exactly the
act entry 103 refused for the rename. Entry 110 stopped a filing rather than take it.

WHAT THIS REFUSES, AND WHY EACH

    an unknown status          only `founder_policy` and `counsel_reviewed` mean anything
                               to V34 and V41. A third value would pass the rules by not
                               matching either branch.
    reviewed with no date      "a lawyer read it" without saying when is the claim this
                               column exists to make checkable.
    a date under founder_policy the two cannot disagree. The check constraint refuses it
                               too; this refuses it with a sentence.
    an empty jurisdiction      a discharge that covers nowhere covers nothing, and V34
                               compares scope against the obligation's jurisdictions.
    a blank basis              the accidental-empty problem `NoFramework` was built for.
                               Nothing can tell a considered discharge from a row somebody
                               added to make a rule go quiet.
    an unknown filer           `discharged_by` is a real `office_human`. An absent id names
                               nobody, which is the `origin=human` problem: an actor
                               recorded as though it acted.

SUPERSEDING RATHER THAN EDITING

    The table is append-only. A new discharge for the same (venture, flag) stamps
    `superseded_at` on the current one and inserts itself; the old row stays readable, so
    "verified in 2026" and "verified" remain distinguishable afterwards.

    That is the one UPDATE this table needs, and 0042 grants `office_app` exactly it -
    `UPDATE (superseded_at)` and nothing else - so a bug elsewhere cannot rewrite a basis
    or move a review date.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

#: The two things a discharge can rest on. Neither is a default.
STATUSES = ("founder_policy", "counsel_reviewed")

#: Twelve months, which 0032 calls "a backstop, not the mechanism" - the events that
#: actually invalidate a discharge are a new state, an amended statute, and a changed
#: relationship, and each of those is a human act that supersedes the row.
DEFAULT_TERM_DAYS = 365


class DischargeError(Exception):
    """A filing that was refused. The message is for the person filing."""


async def file_discharge(
    conn: AsyncConnection,
    *,
    venture_id: str,
    runtime_flag: str,
    jurisdiction_scope: list[str],
    library_entry_ref: str,
    citation: str,
    discharged_by: uuid.UUID,
    role_discharged_as: str,
    artifact_kind: str,
    artifact_hash: str,
    basis: str,
    status: str,
    counsel_reviewed_at: datetime | None = None,
    term_days: int = DEFAULT_TERM_DAYS,
) -> dict[str, Any]:
    """File one, superseding whatever it replaces. Returns the new row's facts."""
    if status not in STATUSES:
        raise DischargeError(
            f"{status!r} is not a discharge status. It is {' or '.join(STATUSES)} - "
            "a third value would pass V34 and V41 by matching neither branch."
        )
    if status == "counsel_reviewed" and counsel_reviewed_at is None:
        raise DischargeError(
            "counsel_reviewed needs counsel_reviewed_at. 'A lawyer read it' without "
            "saying when is the claim this column exists to make checkable."
        )
    if status == "founder_policy" and counsel_reviewed_at is not None:
        raise DischargeError(
            "founder_policy carries no counsel_reviewed_at. The status and the date "
            "cannot disagree about whether a review happened."
        )

    scope = [j.strip() for j in jurisdiction_scope if j.strip()]
    if not scope:
        raise DischargeError(
            "a discharge needs at least one jurisdiction. One that covers nowhere covers "
            "nothing, and V34 compares this against the obligation's jurisdictions."
        )
    if not basis.strip():
        raise DischargeError(
            "a discharge needs a basis saying what was verified. Nothing can tell a "
            "considered discharge from a row somebody added to make a rule go quiet."
        )
    if term_days <= 0:
        raise DischargeError("a discharge expires after it is verified, not before.")

    now = datetime.now(UTC)
    discharge_id = uuid.uuid4()

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT display_name FROM office_human WHERE human_id = %s", (discharged_by,)
        )
        filer = await cur.fetchone()
        if filer is None:
            raise DischargeError(
                f"no account {str(discharged_by)[:8]}. A discharge names a real person; "
                "an absent id records an actor as though it acted."
            )

        # Supersede first, so the partial index on (venture_id, runtime_flag) WHERE
        # superseded_at IS NULL never sees two current rows - not even briefly.
        await cur.execute(
            "UPDATE obligation_discharge SET superseded_at = %s "
            "WHERE venture_id = %s AND runtime_flag = %s AND superseded_at IS NULL "
            "RETURNING discharge_id",
            (now, venture_id, runtime_flag),
        )
        superseded = [str(r["discharge_id"]) for r in await cur.fetchall()]

        await cur.execute(
            """
            INSERT INTO obligation_discharge
              (discharge_id, venture_id, runtime_flag, jurisdiction_scope,
               library_entry_ref, citation, discharged_by, role_discharged_as,
               artifact_kind, artifact_hash, basis, verified_at, expires_at,
               status, counsel_reviewed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                discharge_id, venture_id, runtime_flag, scope, library_entry_ref,
                citation, discharged_by, role_discharged_as, artifact_kind,
                artifact_hash, basis.strip(), now, now + timedelta(days=term_days),
                status, counsel_reviewed_at,
            ),
        )
    await conn.commit()

    return {
        "discharge_id": str(discharge_id),
        "venture_id": venture_id,
        "runtime_flag": runtime_flag,
        "jurisdiction_scope": scope,
        "status": status,
        "filed_by": filer["display_name"],
        "verified_at": now.isoformat(),
        "expires_at": (now + timedelta(days=term_days)).isoformat(),
        "superseded": superseded,
    }
