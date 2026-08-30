"""Command-line entry point for the broker package.

    python -m broker serve                  # the Operations API
    python -m broker sweep                  # the three routine sweeps
    python -m broker sweep --restore-drill  # plus Gate 13, quarterly
    python -m broker health                 # freshness of every control
    python -m broker human create --name … --email …   # the FIRST human only

`serve` exists rather than `uvicorn broker.app:app` because **uvicorn explicitly
installs `WindowsProactorEventLoopPolicy` on Windows**, overriding the selector policy
`broker/__init__.py` sets - and psycopg's async driver cannot run on Proactor. The
symptom is not an error: the server starts, accepts connections, and every request hangs
until the client times out, with the real cause in a log line uvicorn prints once at
startup. Running the server with `loop="none"` leaves our policy alone.

Designed to be invoked by cron or a systemd timer. `health` exits non-zero when any
control is `never_run`, `stale` or `failing`, so a monitor can watch the exit code
rather than parse the output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import broker  # noqa: F401  - imported for its event-loop policy side effect
from broker import audit, humans, sweeps
from broker.db import connection


async def _sweep(include_restore_drill: bool) -> int:
    results = await sweeps.run_all(include_restore_drill=include_restore_drill)
    if not results:
        print("no sweeps ran; another process holds every lock", file=sys.stderr)
        return 1

    failed = 0
    for kind, result in sorted(results.items()):
        marker = "ok " if result.passed else "FAIL"
        print(f"{marker} {kind}: {result.status} over {result.denominator} item(s)")
        for key, value in sorted(result.findings.items()):
            if value not in (None, [], {}, 0, False):
                print(f"       {key}: {value}")
        if not result.passed:
            failed += 1
    return 1 if failed else 0


async def _health() -> int:
    async with connection() as conn:
        report = await sweeps.freshness(conn)

    unhealthy = [k for k, v in report.items() if not v["healthy"]]
    for kind, state in sorted(report.items()):
        marker = "ok " if state["healthy"] else "!! "
        print(f"{marker} {kind}: {state['state']}")
        print(f"       {json.dumps({k: v for k, v in state.items() if k != 'state'})}")

    if unhealthy:
        print(
            f"\nUNHEALTHY: {', '.join(sorted(unhealthy))}. "
            "never_run and stale are not passes - an absence of findings from a check "
            "that did not run is not evidence.",
            file=sys.stderr,
        )
        return 1
    return 0


def _serve(host: str, port: int, reload: bool) -> int:
    """Run the Operations API without letting uvicorn replace the event-loop policy.

    `loop="none"` is the important argument. uvicorn's default loop setup calls
    `asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())` on Windows, and
    psycopg's async driver cannot use Proactor - so every database-backed request hangs
    rather than failing, which is considerably harder to diagnose than a crash.
    """
    import uvicorn

    if reload:
        # Reload needs uvicorn to own the process, so the policy has to be set in the
        # child. UVICORN_LOOP is not a thing; use the programmatic path either way.
        print(
            "reload is not supported here: it requires uvicorn to own the event loop, "
            "which is exactly what this command avoids on Windows.",
            file=sys.stderr,
        )
        return 2

    config = uvicorn.Config(
        "broker.app:app", host=host, port=port, loop="none", log_level="info"
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
    return 0


async def _bootstrap_human(name: str, email: str, role: str) -> int:
    """Create the first human. Refuses once any human exists.

    The bootstrap problem: every route that creates a human requires a human to
    authenticate as, so the first one cannot come from the API. The alternative - an
    unauthenticated route that works "only when the table is empty" - is a permanent
    backdoor wearing a bootstrap label, and one that is reachable from the internet the
    moment the table is emptied.

    A CLI on the host is honest instead. Shell access to the VM is already total
    authority over this system, so this adds nothing anyone in that position lacked.
    It refuses once a human exists so that it stays a bootstrap tool rather than
    becoming a standing way to mint administrators without an audit trail naming who
    granted the role.

    The token is printed once. That is the only time it exists in readable form.
    """
    async with connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT count(*) FROM office_human")
            row = await cur.fetchone()
        existing = int(row[0]) if row else 0

        if existing:
            print(
                f"refusing: {existing} human(s) already exist. This command bootstraps "
                "the first one only.\n"
                "Create further humans through the console, where the audit log records "
                "who granted the role.",
                file=sys.stderr,
            )
            return 1

        human_id, token = await humans.create_human(
            conn, display_name=name, email=email
        )
        # granted_by is the human themselves, and only here. Every later grant names a
        # different granter because `assert_may_grant` forbids granting to yourself -
        # this row is the documented exception, and it is visible as one.
        await humans.grant_role(
            conn, human_id=human_id, role=role, granted_by=human_id
        )
        await audit.write_event(
            event_type="bootstrap_human_created",
            actor_type="human", actor_id=human_id, venture_id=None,
            subject={"display_name": name, "email": email, "role": role,
                     "via": "cli bootstrap, self-granted"},
        )

    print(f"created {name} <{email}> with role {role}")
    print(f"human_id: {human_id}")
    print(f"token:    {token}")
    print("\nThis token is shown once and cannot be recovered. Store it now.")
    return 0


async def _bootstrap_phase0(venture_id: str, ref: str | None, confirm: bool) -> int:
    """Put one agent on the path so the first real call can be made.

    Reports what it would do unless `--confirm` is given. The thing being issued is
    authority to call a Forge, and that should never happen as a side effect of running
    a command to see what it does.
    """
    from broker import bootstrap_phase0, humans
    from broker.db import connection

    async with connection() as conn:
        try:
            actor = await humans.attributable_actor(conn)
        except humans.NoAttributableActorError as exc:
            print(f"bootstrap-phase0: {exc}")
            return 1

        human = await humans.get_human(conn, actor)
        if human is None:
            print("bootstrap-phase0: the attributed account could not be loaded")
            return 1

        try:
            detail = await bootstrap_phase0.plan(conn, ref=ref)
        except bootstrap_phase0.BootstrapError as exc:
            print(f"bootstrap-phase0: {exc}")
            return 1

        agent = detail["agent"]
        print(
            f"Agent    {agent['agent_name']} ({agent['village_agent_ref']}) · "
            f"{agent['department']} · {agent['role_key']}"
        )
        print(f"Forge    {detail['forge_id']} {detail['forge']['api_version']} "
              f"· {detail['forge']['health_status']} · {detail['forge']['base_url']}")
        print(f"Module   {detail['module_id']} at tier {detail['tier']}")
        print(f"Actor    {human.display_name}")
        print(f"Venture  {venture_id}")

        if not confirm:
            print(
                "\nNothing was written. Re-run with --confirm to issue the identity, "
                "two certifications, one grant and one shift.\n"
                "Every row is marked as a Phase 0 bootstrap: it is what makes the first "
                "call possible, not evidence that the provisioning ladder was run."
            )
            return 0

        try:
            result = await bootstrap_phase0.apply(
                conn, human=human, venture_id=venture_id, ref=ref, confirmed=True
            )
        except bootstrap_phase0.BootstrapError as exc:
            print(f"bootstrap-phase0: {exc}")
            return 1
        except Exception as exc:
            print(f"bootstrap-phase0 failed: {type(exc).__name__}: {exc}")
            return 1

    print("\nIssued.")
    for key in ("office_agent_id", "grant_id", "unit_a_cert", "unit_b_cert", "shift_id"):
        print(f"  {key:18} {result[key]}")
    return 0


async def _sync_roster(confirm: bool) -> int:
    """Diff the Village roster against The Office, and apply only when told to.

    Run without `--confirm` this reads both sides and prints what would change. That is
    the normal way to run it: the destructive half of a sync is a departure, which
    revokes whatever grants the departed agent held, and nobody should discover that
    from a summary printed after the fact.
    """
    from broker import sync_roster
    from broker.db import connection

    async with connection() as conn:
        try:
            diff = await sync_roster.diff(conn)
        except sync_roster.SyncError as exc:
            print(f"sync-roster: {exc}")
            return 1

        print(f"Village {diff.village_total} agents · Office {diff.office_total} known")
        if diff.empty:
            print("No change.")
            return 0

        for kind, heading in (
            ("new", "New in the Village"),
            ("departed", "Gone from the Village"),
            ("department", "Changed department"),
            ("role", "Changed role"),
            ("reporting", "Changed manager"),
        ):
            rows = diff.of(kind)
            if not rows:
                continue
            print(f"\n{heading} ({len(rows)})")
            for change in rows[:40]:
                print(f"  {change.agent_name:28} {change.detail}")
            if len(rows) > 40:
                print(f"  ... and {len(rows) - 40} more")

        if not confirm:
            print(
                "\nNothing was applied. Re-run with --confirm to write these changes.\n"
                "A departure revokes the grants that agent held."
            )
            return 0

        # The audit entry names a person, and a real one. This used to be "the oldest
        # active account holding ivan", which the one real account won by being oldest
        # while 222 fixtures held the same role.
        from broker import humans

        try:
            actor = await humans.attributable_actor(conn)
        except humans.NoAttributableActorError as exc:
            print(f"sync-roster: {exc}")
            return 1

        # Every failure path returns non-zero. The first run of this command hit a
        # CHECK constraint and the shell still saw 0, because the only thing standing
        # between an exception and a zero exit was an unhandled traceback - which a pipe
        # or a wrapper swallows. A command that writes to the identity table must not be
        # able to report success it did not have.
        try:
            result = await sync_roster.apply(conn, actor=actor, confirmed=True)
        except sync_roster.SyncError as exc:
            print(f"sync-roster: {exc}")
            return 1
        except Exception as exc:
            print(
                f"sync-roster failed: {type(exc).__name__}: {exc}\n"
                "Nothing was written - the roster and its audit entry are one "
                "transaction, so a failure rolls both back."
            )
            return 1

        print(f"\nApplied. {result['new']} new, {result['departed']} departed.")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="broker")
    sub = parser.add_subparsers(dest="command", required=True)

    srv = sub.add_parser("serve", help="Run the Operations API")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8080)
    srv.add_argument("--reload", action="store_true")

    s = sub.add_parser("sweep", help="Run the verification sweeps")
    s.add_argument(
        "--restore-drill",
        action="store_true",
        help="Also run Gate 13. Dumps and restores into a scratch database.",
    )
    sub.add_parser("health", help="Report freshness of every control")

    hb = sub.add_parser(
        "human", help="Bootstrap the first human. Refuses once one exists."
    )
    hb_sub = hb.add_subparsers(dest="human_command", required=True)
    hc = hb_sub.add_parser("create", help="Create the first human and print a token")
    hc.add_argument("--name", required=True)
    hc.add_argument("--email", required=True)
    hc.add_argument(
        "--role", default="ivan", choices=("ivan", "compliance_officer",
                                           "venture_operator"),
    )

    sr = sub.add_parser(
        "sync-roster",
        help="Diff the Village roster against The Office; apply with --confirm",
    )
    sr.add_argument(
        "--confirm",
        action="store_true",
        help="Apply the diff. Without this the command only reports what would change.",
    )

    bp = sub.add_parser(
        "bootstrap-phase0",
        help="Issue one identity, certification pair, grant and shift for the first call",
    )
    bp.add_argument(
        "--venture", default="greenstone", help="Venture the grant and shift are for"
    )
    bp.add_argument(
        "--agent", default=None,
        help="Village agent ref. Defaults to the lowest-ranked active engineer.",
    )
    bp.add_argument(
        "--confirm", action="store_true",
        help="Actually issue. Without this the command only reports what it would do.",
    )

    args = parser.parse_args()
    if args.command == "serve":
        return _serve(args.host, args.port, args.reload)
    if args.command == "sweep":
        return asyncio.run(_sweep(args.restore_drill))
    if args.command == "health":
        return asyncio.run(_health())
    if args.command == "sync-roster":
        return asyncio.run(_sync_roster(args.confirm))
    if args.command == "bootstrap-phase0":
        return asyncio.run(
            _bootstrap_phase0(args.venture, args.agent, args.confirm)
        )
    if args.command == "human":
        return asyncio.run(_bootstrap_human(args.name, args.email, args.role))
    return 2


if __name__ == "__main__":
    sys.exit(main())
