"""Shared test fixtures.

Two connections, deliberately:

  admin  - superuser. Used to set up fixtures and to SIMULATE AN ATTACKER for the
           tamper tests. Never the subject of an append-only assertion; a
           superuser bypasses role grants, so asserting against it would prove
           nothing.

  app    - the office_app role. This is the one the broker uses at runtime, and
           the only one whose permissions are worth asserting.

Tests that mix them up are the easy way to ship a false green here.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import psycopg
import psycopg.types.json
import pytest
import pytest_asyncio

from broker import account_origin
from broker.db import close_pool

# The suite runs against its OWN database when one is configured.
#
# It empties `office_human`, the Forge registry and every venture-scoped table, which is
# correct - a suite that left rows behind would be a suite whose next run depended on
# its last. Pointed at the development database, that is also the reason a browser
# session dies every time the tests run, which happened four times before this existed.
#
# `OFFICE_TEST_ADMIN_DSN` / `OFFICE_TEST_APP_DSN` take precedence. Falling back to the
# development pair keeps a bare checkout working and keeps CI unchanged, but the
# fallback announces itself rather than quietly destroying somebody's data.
TEST_ADMIN_DSN = os.environ.get("OFFICE_TEST_ADMIN_DSN")
TEST_APP_DSN = os.environ.get("OFFICE_TEST_APP_DSN")

ADMIN_DSN = TEST_ADMIN_DSN or os.environ.get("OFFICE_ADMIN_DSN")
APP_DSN = TEST_APP_DSN or os.environ.get("OFFICE_APP_DSN")

USING_DEV_DATABASE = bool(ADMIN_DSN) and not TEST_ADMIN_DSN


def pytest_configure(config: pytest.Config) -> None:
    """Say it out loud when the suite is about to empty the development database.

    The parameter must be called `config`: pytest matches hook arguments by NAME against
    the hookspec, so renaming it to `_config` to satisfy an unused-argument lint makes
    pytest refuse to load this file at all. It did, and the suite did not run.
    """
    if USING_DEV_DATABASE and not os.environ.get("OFFICE_TEST_DB_WARNING_OK"):
        print(
            "\n  NOTE: no OFFICE_TEST_ADMIN_DSN is set, so this suite is running "
            "against the\n"
            "  development database and will empty it. Any console session you have "
            "open will\n"
            "  stop working. `./scripts/dev-up.sh` restores it, or run "
            "`./scripts/bootstrap.sh`\n"
            "  once to create a separate test database.\n"
        )

# Every table that references a Forge or one of its modules, in deletion order.
# One list, because this has bitten four times: each phase adds another referencing
# table, and a fixture that hard-codes its own list silently goes stale.
FORGE_DEPENDENTS = (
    "certification",
    "forge_operating_instruction",
    "curriculum_submission",
    "venture_forge_manifest",
    "manifest_disposition",
    "proposal",
    "agent_forge_grant",
    "forge_tenant_credential",
    "forge_module_registry",
    # No FK, so ordering is irrelevant here - but a test forge that left its
    # exclusions behind would make the NEXT test's grant fail for a reason
    # belonging to the last one.
    "forge_module_exclusion",
)


def drop_forge(conn: psycopg.Connection, forge_id: str) -> None:
    """Delete a Forge and everything that references it, in order."""
    with conn.cursor() as cur:
        for table in FORGE_DEPENDENTS:
            cur.execute(
                f"DELETE FROM {table} WHERE forge_id = %s",
                (forge_id,),
            )
        cur.execute("DELETE FROM forge_registry WHERE forge_id = %s", (forge_id,))
    conn.commit()


# Every table scoped to a venture, in deletion order: children before the rows they
# reference. One list, for the same reason `FORGE_DEPENDENTS` is one list.
#
# This one was added after a new suite hardcoded its own three-table version and
# `business_pack` could not be deleted because a `provisioning_run` still referenced it
# - a failure that only appeared when the console smoke script had run first and left a
# run behind. That is exactly the staleness the comment above predicts, so the answer is
# the same: one list, used by everyone, updated when a phase adds a table.
VENTURE_DEPENDENTS = (
    # Append-only tables first; they need their guard trigger disabled, which is why
    # they are named separately below rather than being deleted in this loop.
    "provisioning_gate_result",
    # Venture-scoped, and it leaks between tests without this: one suite's drill is
    # evidence a later suite's attestation reads, so a department nobody escalated for
    # could be attested verified (entry 149). It has no `forge_id`, so it belongs in
    # this list and not in FORGE_DEPENDENTS - which is where it went first.
    "escalation_record",
    "provisioning_run",
    "signoff_record",
    "curriculum_submission",
    "agent_working_memory",
    "shift_assignment",
    "agent_forge_grant",
    "manifest_disposition",
    "venture_forge_manifest",
    "venture_budget",
    "proposal",
    "revocation",
    # Venture-scoped, and never wiped until 2026-09-16 because only Burkham declared a
    # human-held obligation and its tests cleared the rows by hand. Item F gave
    # Greenstone one, and a discharge left behind references an `office_human` that
    # twenty-four contract suites delete wholesale - so the leak surfaced as a foreign
    # key error in suites that touch neither table.
    "obligation_discharge",
    # The same shape as the line above, and found the same way. Venture-scoped since
    # migration 0039, and never wiped because nothing referenced an account until entry
    # 162 gave `authored_by` a foreign key - at which point the world's two entries held
    # their author's row down and `DELETE FROM office_human` failed in suites that touch
    # neither table.
    "compliance_library_entry",
    "persona",
    "business_playbook",
    "business_pack",
)

# Guarded by an append-only trigger. A superuser can disable it; office_app never can,
# which is the point of the guard and the reason these are separated here.
VENTURE_APPEND_ONLY = (
    ("historical_record", "historical_record_append_only"),
    ("incident_resolution", "incident_resolution_append_only"),
    ("agent_call_ledger", "agent_call_ledger_append_only"),
    # Entry 166. A declaration of simulation is not deleted: the gates that deferred on
    # it read this row, and leaving is the named act. A test venture still has to be
    # resettable, so the guard comes down here like the other three.
    ("venture_simulation", "venture_simulation_is_not_deleted"),
)


def wipe_venture(conn: psycopg.Connection, venture_id: str) -> None:
    """Remove everything belonging to one venture, in an order the FKs allow.

    Superuser only. `incident_resolution` has no `venture_id` of its own, so it is
    cleared through its incident - and before it, because the resolution references the
    detection.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM provisioning_gate_result WHERE run_id IN "
            "(SELECT run_id FROM provisioning_run WHERE venture_id = %s)",
            (venture_id,),
        )
        for table, trigger in VENTURE_APPEND_ONLY:
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        cur.execute(
            "DELETE FROM incident_resolution WHERE incident_id IN "
            "(SELECT incident_id FROM incident WHERE venture_id = %s)",
            (venture_id,),
        )
        cur.execute("DELETE FROM incident WHERE venture_id = %s", (venture_id,))
        cur.execute("DELETE FROM historical_record WHERE venture_id = %s", (venture_id,))
        cur.execute("DELETE FROM agent_call_ledger WHERE venture_id = %s", (venture_id,))
        # Entry 166. Inside the guarded block rather than in the loop below, because the
        # loop runs after the triggers go back up.
        #
        # Entry 167's certifications go FIRST: a simulation certification names the
        # declaration that permitted it, `certification` has no `venture_id` of its own,
        # and the foreign key points this way. This is the only thing that reaches a
        # venture's certifications through `wipe_venture`, which is why it is spelled
        # out rather than folded into the loop.
        cur.execute(
            "DELETE FROM certification WHERE simulation_ref IN "
            "(SELECT simulation_id FROM venture_simulation WHERE venture_id = %s)",
            (venture_id,),
        )
        cur.execute(
            "DELETE FROM venture_simulation WHERE venture_id = %s", (venture_id,)
        )
        for table, trigger in VENTURE_APPEND_ONLY:
            cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")

        for table in VENTURE_DEPENDENTS:
            if table == "provisioning_gate_result":
                continue
            cur.execute(f"DELETE FROM {table} WHERE venture_id = %s", (venture_id,))

        # `department_attestation` LAST, and with its guard down.
        #
        # Append-only by trigger for everyone including the owner (entry 147), so a test
        # venture could never be reset and rows from one suite would be in force for
        # every later one - which is how `post_gate_result` came to be called from a
        # suite that has no attestations in it.
        #
        # Its dependents go first: `curriculum_submission` above is venture-scoped and
        # deleted in the loop, and an attested `certification` is not - it carries no
        # venture_id - so it is cleared through the attestations it names, which is the
        # only venture this venture's departments belong to.
        cur.execute("ALTER TABLE department_attestation DISABLE TRIGGER USER")
        cur.execute(
            "DELETE FROM certification WHERE attestation_ref IN "
            "(SELECT attestation_id FROM department_attestation WHERE venture_id = %s)",
            (venture_id,),
        )
        cur.execute(
            "DELETE FROM department_attestation WHERE venture_id = %s", (venture_id,)
        )
        cur.execute("ALTER TABLE department_attestation ENABLE TRIGGER USER")
    conn.commit()


if TEST_APP_DSN:
    # `broker.db` builds its pool from `Settings`, which reads OFFICE_APP_DSN. Without
    # this the fixtures would set up one database and the code under test would query
    # another - and every assertion about a row somebody just inserted would fail for a
    # reason that looks like a bug in the code rather than in the harness.
    os.environ["OFFICE_APP_DSN"] = TEST_APP_DSN
if TEST_ADMIN_DSN:
    os.environ["OFFICE_ADMIN_DSN"] = TEST_ADMIN_DSN

requires_db = pytest.mark.skipif(
    not ADMIN_DSN or not APP_DSN,
    reason="OFFICE_ADMIN_DSN and OFFICE_APP_DSN must be set (see .env.example)",
)


@pytest.fixture(scope="session")
def admin_dsn() -> str:
    assert ADMIN_DSN, "OFFICE_ADMIN_DSN not set"
    return ADMIN_DSN


@pytest.fixture(scope="session")
def app_dsn() -> str:
    assert APP_DSN, "OFFICE_APP_DSN not set"
    return APP_DSN


@pytest.fixture
def admin(admin_dsn: str) -> Iterator[psycopg.Connection]:
    """Superuser connection. Autocommit off; rolled back after each test."""
    with psycopg.connect(admin_dsn) as conn:
        yield conn
        conn.rollback()


@pytest.fixture
def app(app_dsn: str) -> Iterator[psycopg.Connection]:
    """The runtime role. Its privileges are the thing under test."""
    with psycopg.connect(app_dsn) as conn:
        yield conn
        conn.rollback()


async def force_role(
    conn, human_id, role: str, venture_id: str | None = None
) -> None:
    """Write a role row `grant_role` would refuse. Entry 206.

    **Only for the suites that test the DETECTION of a state the grant path forbids.**
    `grant_role` refuses `ivan` to a non-human account, and four controls exist to find
    that state anyway: the access-overview concentration banner, `staffing`'s refusal,
    `sync-roster`'s refusal, and the audit view's fixture tag. The state did not stop
    being possible - 128 rows held it on the day of the ruling and a direct write still
    can - so a detector with no way to be exercised is a detector nobody can trust.

    Raw SQL on purpose: going through `grant_role` would be going through the check.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO office_human_role (human_id, role, venture_id, granted_by) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (human_id, role, venture_id, human_id),
        )
    await conn.commit()


def origin_for(role: str | None) -> str:
    """The account origin a role requires. Entry 206.

    `ivan` is refused to anything but a human account, so a suite that needs founder
    authority declares one - the same move `declare_author` makes for entry 162, and for
    the same reason: the account's nature is visible in the test rather than inferred
    from a display name.

    Every other role stays a fixture. `assert_named_human` is what guards the acts that
    name a signer, and it is unchanged.
    """
    return account_origin.HUMAN if role == "ivan" else account_origin.TEST_FIXTURE


def declare_author(
    conn: psycopg.Connection, human_id: uuid.UUID, display_name: str = "Test Author"
) -> uuid.UUID:
    """An account a compliance entry may name as its author. Entry 162.

    *"A compliance entry names a real author. `authored_by` must resolve to an
    `origin='human'` account."* Before that ruling every test here passed a bare UUID
    that matched no row at all, which is the same thing Greenstone's two library entries
    do and the reason nobody noticed they did it.

    **`origin = 'human'`, declared and not guessed.** Entry 151's rule is that origin is
    stated at creation; it does not say a test may never state `human`. A test that has
    to exercise a rule about people needs an account the rule accepts, and declaring it
    is what makes the account's nature visible in the test rather than inferred from a
    display name - which is the whole of 151.

    Idempotent, and callers delete it themselves. It is not auto-wiped, because a test
    that leaves one behind should say so in its own teardown rather than rely on a
    fixture to tidy up after a rule about accountability.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO office_human (human_id, display_name, email, auth_method, "
            "                          origin, token_hash) "
            "VALUES (%s, %s, %s, 'bearer_token', 'human', %s) "
            "ON CONFLICT (human_id) DO NOTHING",
            # The FULL hex, not a prefix: the ids these tests use differ only in their
            # last characters, and a prefix collided on the email unique index.
            (human_id, display_name, f"{human_id.hex}@author.invalid",
             f"author-{human_id.hex}"),
        )
    conn.commit()
    return human_id


def rely_on_entry(
    conn: psycopg.Connection, *, venture_id: str, entry_ref: str,
    approver: uuid.UUID,
) -> uuid.UUID:
    """Approve an entry and record a counsel review, so it may be relied on.

    RULED 22 SEPTEMBER 2026, entry 165: *"An entry is relied on only when approved and
    counsel-reviewed."* Before that ruling, writing an entry was enough for Gate 6 to
    treat its flag as explained and for V28 to pass a Pack citing it.

    **`approver` is a parameter with no default**, because entries 163 and 164 say the
    approver and the recorder are never the author - so a caller has to have a second
    person in hand, and a helper that invented one would hide the rule it exists to
    satisfy. `declare_author` makes the account.

    SQL rather than the domain functions, like the rest of this module: these fixtures
    run on the admin connection. The CHECKs still apply, so a caller that passes the
    author fails here rather than producing a row that breaks a later test.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE compliance_library_entry
               SET status = 'approved',
                   approved_by = %(approver)s,
                   approved_at = now(),
                   counsel_reviewed_at = now(),
                   counsel_reviewer_name = 'Marta Reyes',
                   counsel_reviewer_firm = 'Reyes & Okonkwo LLP',
                   counsel_recorded_by = %(approver)s,
                   counsel_recorded_at = now(),
                   counsel_claims_confirmed = %(claims)s
             WHERE venture_id = %(venture_id)s AND entry_ref = %(entry_ref)s
            """,
            {
                "approver": approver,
                "claims": psycopg.types.json.Jsonb(["the applicability rule as written"]),
                "venture_id": venture_id,
                "entry_ref": entry_ref,
            },
        )
        assert cur.rowcount == 1, f"no entry {entry_ref!r} for {venture_id!r} to rely on"
    conn.commit()
    return approver


def undeclare_author(conn: psycopg.Connection, *human_ids: uuid.UUID) -> None:
    """Remove accounts `declare_author` made."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM office_human WHERE human_id = ANY(%s)", (list(human_ids),))
    conn.commit()


@pytest.fixture
def clean_audit(admin: psycopg.Connection) -> Iterator[None]:
    """Empty audit_log and reset the sequence, so chain assertions start at genesis.

    Uses ALTER TABLE ... DISABLE TRIGGER because the append-only guard is doing
    exactly its job here. Superuser-only; never available to office_app.
    """
    _truncate_audit(admin)
    yield
    _truncate_audit(admin)


def _truncate_audit(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE audit_log DISABLE TRIGGER audit_log_append_only")
        cur.execute("DELETE FROM audit_log")
        cur.execute("ALTER TABLE audit_log ENABLE TRIGGER audit_log_append_only")
        cur.execute("ALTER SEQUENCE audit_log_audit_id_seq RESTART WITH 1")
    conn.commit()


@pytest.fixture
def seed_forge(admin: psycopg.Connection) -> Iterator[tuple[str, str]]:
    """A registered Forge and module, for grant and ledger tests."""
    forge_id = f"test-forge-{uuid.uuid4().hex[:8]}"
    module_id = "parse_document"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO forge_registry
              (forge_id, display_name, base_url, api_version, auth_model,
               credential_mode, health_status)
            VALUES (%s, 'Test Forge', 'https://example.invalid', '1.2.0',
                    'bearer', 'brokered', 'GREEN')
            """,
            (forge_id,),
        )
        cur.execute(
            """
            INSERT INTO forge_module_registry
              (forge_id, module_id, module_name, idempotency_support, is_mutating)
            VALUES (%s, %s, 'Parse Document', 'key', TRUE)
            """,
            (forge_id, module_id),
        )
    admin.commit()
    yield forge_id, module_id
    drop_forge(admin, forge_id)


@pytest.fixture
def seed_agent(admin: psycopg.Connection) -> Iterator[uuid.UUID]:
    """An active agent identity."""
    agent_id = uuid.uuid4()
    ref = f"test-agent-{agent_id.hex[:8]}"
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO office_agent_identity
              (office_agent_id, village_agent_ref, agent_name, department, status)
            VALUES (%s, %s, 'Test Agent', 'AI & Data Science', 'active')
            """,
            (agent_id, ref),
        )
    admin.commit()
    yield agent_id
    with admin.cursor() as cur:
        # Everything that references the identity, before the identity itself.
        cur.execute("DELETE FROM agent_forge_grant WHERE office_agent_id = %s", (agent_id,))
        # Working memory references the shift, so it must go before the shift does.
        cur.execute(
            "DELETE FROM agent_working_memory WHERE office_agent_id = %s", (agent_id,)
        )
        cur.execute("DELETE FROM shift_assignment WHERE office_agent_id = %s", (agent_id,))
        # certification was missing from this list until 3 September 2026. The
        # comment above claimed the list was complete and it was not - no test had
        # written a Unit A row against this agent and left it standing, so the
        # foreign key was never exercised. The first test that did failed in
        # teardown, which reads as a broken test rather than a broken fixture.
        cur.execute("DELETE FROM certification WHERE office_agent_id = %s", (agent_id,))
        for table in ("revocation", "proposal"):
            cur.execute(
                f"DELETE FROM {table} WHERE office_agent_id = %s",
                (agent_id,),
            )
        cur.execute("DELETE FROM office_agent_identity WHERE office_agent_id = %s", (agent_id,))
    admin.commit()


def insert_audit(
    conn: psycopg.Connection,
    event_type: str = "test_event",
    actor_type: str = "system",
    subject: str = '{"k": "v"}',
) -> int:
    """Insert one audit entry and return its assigned audit_id."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (event_type, actor_type, actor_id, venture_id, subject)
            VALUES (%s, %s, %s, 'test-venture', %s::jsonb)
            RETURNING audit_id
            """,
            (event_type, actor_type, str(uuid.uuid4()), subject),
        )
        row = cur.fetchone()
    assert row is not None
    conn.commit()
    return int(row[0])


def verify_chain(conn: psycopg.Connection) -> tuple[bool, int, int | None, str]:
    """Chain verdict: (ok, checked_count, first_break_audit_id, reason)."""
    with conn.cursor() as cur:
        cur.execute("SELECT ok, checked_count, first_break_audit_id, reason "
                    "FROM audit_log_verify_chain()")
        row = cur.fetchone()
    assert row is not None
    return bool(row[0]), int(row[1]), row[2], str(row[3])


def tail_gap(conn: psycopg.Connection) -> int:
    """How far the sequence has advanced beyond max(audit_id).

    Nonzero means the newest entries were deleted, or that many inserts rolled
    back. Advisory, never a verdict on its own.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT tail_gap FROM audit_log_verify_chain()")
        row = cur.fetchone()
    assert row is not None
    return int(row[0])


@pytest_asyncio.fixture(autouse=True)
async def _reset_connection_pool() -> AsyncIterator[None]:
    """Close the broker connection pool after every test, everywhere.

    The pool is a process-level global, and pytest-asyncio gives each test its own
    event loop - so a pooled connection created in one test's loop is invalid in the
    next. Resetting it per test is the only reliable answer.

    This lives in the ROOT conftest rather than per-directory because it has to apply
    to *every* suite. It was originally per-directory, and `tests/validator` and
    `tests/golden` use the pool without one: they left a pool bound to a dead loop,
    and the first test of the next suite failed with an error about a closed loop that
    had nothing to do with it. A cleanup that only some directories perform is worse
    than none, because the failure lands somewhere else.
    """
    yield
    await close_pool()
