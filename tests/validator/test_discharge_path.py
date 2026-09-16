"""Filing a discharge through the route entry 110 refused to work around.

ENTRY 110 STOPPED, AND THIS IS WHAT IT WAS WAITING FOR

    Two blockers, both closed here. There was no operator surface - the only writers were
    test fixtures, and `office_app` held SELECT - so the remaining path was hand SQL over
    the admin DSN, which writes no audit event. And the table could not say "not
    counsel-reviewed": the caveat could only go in `basis`, `citation` or `artifact_kind`,
    and V34 reads none of them, so a founder-policy row would have been indistinguishable
    from one a lawyer signed.

WHAT THE TWO STATUSES DO, AND WHY IT IS TWO RULES

    founder_policy     V34 PASSES - the obligation is discharged, by somebody entitled to
                       decide - and V41 WARNS at Gate 2 for as long as it stands.
    counsel_reviewed   V34 passes and V41 is quiet. `counsel_reviewed_at` says when.

    V34 answers "is it discharged". V41 answers "on whose authority". They have different
    verdicts, so they are different rules - the same reason V34 is not part of V22.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from broker import discharges
from broker.db import connection
from generators.pack import load_pack
from generators.validator import validate
from tests.world import PACK_PATH

FLAG = "recording_consent_required"
VENTURE = "greenstone"


@pytest.fixture
def filer(admin: psycopg.Connection):
    """A named human to attribute a filing to, and a clean table."""
    human_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute("DELETE FROM obligation_discharge WHERE venture_id = %s", (VENTURE,))
        cur.execute(
            """
            INSERT INTO office_human
              (human_id, display_name, email, auth_method, status, created_at, origin)
            VALUES (%s, 'Discharge Filer', 'filer@example.invalid', 'mfa_only',
                    'active', now(), 'test_fixture')
            """,
            (human_id,),
        )
    admin.commit()
    yield human_id
    with admin.cursor() as cur:
        cur.execute("DELETE FROM obligation_discharge WHERE venture_id = %s", (VENTURE,))
        cur.execute("DELETE FROM office_human WHERE human_id = %s", (human_id,))
    admin.commit()


def _greenstone_live_only():
    """The Pack with the TSR entry's pending_activation left alone.

    `recording_consent_required` is the live obligation; the TSR one is pending and neither
    rule should have anything to say about it. Using the real Pack keeps that true.
    """
    return load_pack(PACK_PATH)


async def _file(filer_id, **overrides):
    kwargs = dict(
        venture_id=VENTURE,
        runtime_flag=FLAG,
        jurisdiction_scope=["NV"],
        library_entry_ref="compliance/nv-two-party-consent-v1",
        citation="NRS 200.620",
        discharged_by=filer_id,
        role_discharged_as="venture operator",
        artifact_kind="founder_policy_memo",
        artifact_hash="sha256:test",
        basis="Every recorded call opens with a consent request; without consent the call "
              "is not recorded.",
        status="founder_policy",
    )
    kwargs.update(overrides)
    async with connection() as conn:
        return await discharges.file_discharge(conn, **kwargs)


# ------------------------------------------------------------ the two passing states

async def test_founder_policy_passes_v34_and_is_named_by_v41(filer):
    """**Ruling 1: it satisfies V34, but never silently.**

    A founder is entitled to decide, so the obligation IS discharged and Gate 2 is not
    blocked by it. What must not happen is a clean Gate 2 - that would mean two different
    things and a reader could not tell which.
    """
    await _file(filer)

    async with connection() as conn:
        report = await validate(_greenstone_live_only(), conn)

    v34 = report.get("V34")
    v41 = report.get("V41")

    assert v34.verdict.value == "PASS"
    assert "founder policy, not counsel-reviewed" in v34.message, (
        "V34's PASS must say which authority answered, or it reads as a legal opinion"
    )

    assert v41.verdict.value == "WARN"
    assert FLAG in v41.message
    assert "FOUNDER POLICY" in v41.message
    assert "Gate 2 is not blocked by this" in v41.message
    assert "counsel_reviewed_at" in v41.message, "the warning must say how to clear itself"

    # A WARN, so the gate is not blocked - which is the half of the ruling that is easy to
    # lose when somebody later decides the warning is important.
    assert "V41" not in [r.rule_id for r in report.failures]


async def test_counsel_reviewed_passes_with_no_warning(filer):
    """Ruling 1's other half: setting `counsel_reviewed_at` clears it.

    The warning is not a complaint about the policy. It is the outstanding question about
    the policy, and it goes when the question is answered.
    """
    await _file(
        filer, status="counsel_reviewed", counsel_reviewed_at=datetime.now(UTC)
    )

    async with connection() as conn:
        report = await validate(_greenstone_live_only(), conn)

    assert report.get("V34").verdict.value == "PASS"
    assert "founder policy" not in report.get("V34").message
    assert report.get("V41").verdict.value == "PASS"
    assert "no discharge here rests on founder policy alone" in report.get("V41").message


async def test_v41_is_silent_when_there_is_no_discharge_at_all(filer):
    """An undischarged obligation is V34's finding, not V41's.

    A rule reporting "no founder policy" for an obligation nobody has discharged would be
    agreeing with a failure - the shape V34's own docstring refuses when it says a missing
    discharge must never arrive as V22's sentence.
    """
    async with connection() as conn:
        report = await validate(_greenstone_live_only(), conn)

    assert report.get("V34").verdict.value == "FAIL"
    assert report.get("V41").verdict.value == "PASS"


# ------------------------------------------------------------------- superseding

async def test_a_new_discharge_supersedes_the_old_and_the_old_stays_readable(
    filer, admin
):
    """Append-only. A discharge is never edited; it is replaced and the record survives."""
    first = await _file(filer)
    second = await _file(
        filer, status="counsel_reviewed", counsel_reviewed_at=datetime.now(UTC)
    )

    assert second["superseded"] == [first["discharge_id"]]

    with admin.cursor() as cur:
        cur.execute(
            "SELECT discharge_id, status, superseded_at FROM obligation_discharge "
            "WHERE venture_id = %s ORDER BY verified_at",
            (VENTURE,),
        )
        rows = cur.fetchall()

    assert len(rows) == 2, "the superseded row must still be there"
    assert str(rows[0][0]) == first["discharge_id"] and rows[0][2] is not None
    assert str(rows[1][0]) == second["discharge_id"] and rows[1][2] is None


# --------------------------------------------------------------------- refusals

@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"status": "probably_fine"}, "not a discharge status"),
        ({"status": "counsel_reviewed"}, "needs counsel_reviewed_at"),
        (
            {"counsel_reviewed_at": datetime.now(UTC)},
            "founder_policy carries no counsel_reviewed_at",
        ),
        ({"jurisdiction_scope": []}, "at least one jurisdiction"),
        ({"jurisdiction_scope": ["   "]}, "at least one jurisdiction"),
        ({"basis": "   "}, "needs a basis"),
    ],
)
async def test_the_refusals(filer, overrides, expected):
    with pytest.raises(discharges.DischargeError, match=expected):
        await _file(filer, **overrides)


async def test_an_unknown_filer_is_refused(filer):
    """`discharged_by` names a real account. An absent id records an actor as though it
    acted - the `origin=human` problem migration 0032 named."""
    with pytest.raises(discharges.DischargeError, match="no account"):
        await _file(filer, discharged_by=uuid.uuid4())


# ---------------------------------------------------- an unaudited write is impossible

def test_the_application_role_cannot_edit_a_discharge(app: psycopg.Connection, admin, filer):
    """**The grant is the control, not a convention.**

    0042 gives `office_app` INSERT, SELECT and `UPDATE (superseded_at)` - nothing else. So
    a bug or a future route cannot rewrite a `basis`, move a `counsel_reviewed_at`, or
    change a `status` from founder policy to counsel-reviewed without anybody knowing. The
    only way those values change is a new row through the route, which writes an event.

    DELETE is not granted either: a discharge that could vanish is a discharge whose
    absence means nothing.
    """
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO obligation_discharge
              (discharge_id, venture_id, runtime_flag, jurisdiction_scope,
               library_entry_ref, citation, discharged_by, role_discharged_as,
               artifact_kind, artifact_hash, basis, verified_at, expires_at, status)
            VALUES (%s, %s, %s, ARRAY['NV'], 'ref', 'cite', %s, 'venture operator',
                    'memo', 'sha256:x', 'a basis', now(), now() + interval '1 day',
                    'founder_policy')
            """,
            (uuid.uuid4(), VENTURE, FLAG, filer),
        )
    admin.commit()

    for statement in (
        "UPDATE obligation_discharge SET status = 'counsel_reviewed'",
        "UPDATE obligation_discharge SET basis = 'rewritten'",
        "UPDATE obligation_discharge SET counsel_reviewed_at = now()",
        "DELETE FROM obligation_discharge",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), app.cursor() as cur:
            cur.execute(statement)
        app.rollback()

    # And the one write it IS granted, because superseding needs it.
    with app.cursor() as cur:
        cur.execute("UPDATE obligation_discharge SET superseded_at = now()")
    app.rollback()
