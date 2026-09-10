"""Clear the two Phase 0 hand-set `revoked_at` tombstones on Burkham's grants.

Calls `broker.revocation.clear_grant_tombstone`, which is where the act and its audit
entry live. This file only chooses the targets and prints what happened; it deliberately
holds no logic of its own, so the recorded `written_by` — `broker.revocation` — is true.

Dry run by default. `--apply` to write.
"""

import asyncio
import sys

sys.path.insert(0, ".")
import broker  # noqa: F401  - Windows selector event loop policy
from broker import revocation
from broker.db import connection

VENTURE = "burkham-wickmont"
REASON = (
    "Hand-set during Phase 0 bootstrapping and never a declared revocation. Confirmed "
    "by Ivan on 2026-09-10 as his own, and cleared. The original stamp carried no "
    "revocation row and no audit event, so nothing recorded why the grant stopped or "
    "who stopped it - this entry is the first record of either the stop or its removal. "
    "See blocking.md B37."
)


async def main(apply: bool) -> None:
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT g.grant_id, g.forge_id, g.module_id, g.revoked_at, a.agent_name
                FROM agent_forge_grant g
                LEFT JOIN office_agent_identity a USING (office_agent_id)
                WHERE g.venture_id = %s AND g.revoked_at IS NOT NULL
                ORDER BY g.revoked_at
                """,
                (VENTURE,),
            )
            rows = await cur.fetchall()

        if not rows:
            print(f"no tombstoned grants for {VENTURE} - nothing to do")
            return

        print(f"{len(rows)} tombstoned grant(s) for {VENTURE}:\n")
        for grant_id, forge_id, module_id, revoked_at, agent_name in rows:
            print(f"  {forge_id}/{module_id}")
            print(f"    agent   {agent_name}")
            print(f"    grant   {grant_id}")
            print(f"    revoked {revoked_at}")
            print("    -> cleared; resolve_grant stops refusing it\n")

        if not apply:
            print("DRY RUN - nothing written. Re-run with --apply.")
            return

        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT human_id FROM office_human WHERE email = %s",
                ("ivannextlevel@yahoo.com",),
            )
            ivan = (await cur.fetchone())[0]

        for grant_id, forge_id, module_id, _revoked_at, agent_name in rows:
            cleared = await revocation.clear_grant_tombstone(
                conn,
                grant_id=grant_id,
                cleared_by=ivan,
                venture_id=VENTURE,
                reason=REASON,
            )
            print(f"{'cleared' if cleared else 'NOTHING TO CLEAR'}: "
                  f"{forge_id}/{module_id}  {agent_name}")

        await conn.commit()
        print("\ncommitted")


asyncio.run(main("--apply" in sys.argv))
