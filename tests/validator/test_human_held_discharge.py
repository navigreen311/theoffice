"""V34 — a human-held obligation needs a current discharge.

The rule exists because `HumanHeld` alone is a cheap escape, and that was measured
rather than supposed: with the type landed and V34 unwritten, Burkham reached
32 PASS / 0 FAIL and Gate 2 cleared for a venture whose referral obligation nobody had
verified (`docs/decisions.md` entry 26).

So these tests are not decoration. **Every one of them asserts a way the escape could
reopen**, and the pairing matters more than any single case: a rule that only ever
answers "no discharge → FAIL" would also pass if it answered that unconditionally.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from broker.db import connection
from generators.pack import BusinessPack, load_pack
from generators.validator import Verdict, validate
from tests.conftest import requires_db

pytestmark = [requires_db, pytest.mark.db]

BURKHAM = Path(__file__).resolve().parents[2] / "packs" / "burkham-wickmont.draft.yaml"
GREENSTONE = Path(__file__).resolve().parents[2] / "packs" / "greenstone.yaml"

FLAG = "referral_fee_permitted_in_state"

#: A discharge names a real `office_human` — an absent id would name nobody, which is
#: the `origin=human` problem. The tests create their own rather than borrowing a row
#: from a development database, so they do not depend on data nobody guarantees.
#: `origin='test_fixture'` rather than `'human'`: the column exists to keep a
#: fixture-created person distinguishable from a real one, which is the same
#: distinction a discharge is about.
HUMAN = uuid.UUID("00000000-0000-5000-8000-0000000d1c04")


@pytest.fixture
def burkham() -> BusinessPack:
    return load_pack(BURKHAM)


@pytest.fixture
def no_discharges(admin: psycopg.Connection):
    """The state every venture starts in, and the state Burkham is in today."""
    with admin.cursor() as cur:
        cur.execute("DELETE FROM obligation_discharge WHERE venture_id = 'burkham-wickmont'")
        cur.execute(
            """
            INSERT INTO office_human
              (human_id, display_name, email, auth_method, status, created_at, origin)
            VALUES (%s, 'Discharge Test Operator', 'discharge-test@example.invalid',
                    'mfa_only', 'active', now(), 'test_fixture')
            ON CONFLICT (human_id) DO NOTHING
            """,
            (HUMAN,),
        )
    admin.commit()
    yield
    with admin.cursor() as cur:
        cur.execute("DELETE FROM obligation_discharge WHERE venture_id = 'burkham-wickmont'")
    admin.commit()


def _file_discharge(
    admin: psycopg.Connection,
    *,
    scope: list[str],
    expires_in_days: int,
    verified_days_ago: int = 1,
    basis: str = "Reviewed the referral agreement and confirmed the fee is permitted.",
) -> None:
    # `verified_days_ago` exists because the schema refuses `expires_at <= verified_at`.
    # An expired discharge is one verified in the past whose window has since closed -
    # not one that expired before it was written, which is not a state at all.
    now = datetime.now(timezone.utc)
    verified = now - timedelta(days=verified_days_ago)
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO obligation_discharge
              (discharge_id, venture_id, runtime_flag, jurisdiction_scope,
               library_entry_ref, citation, discharged_by, role_discharged_as,
               artifact_kind, artifact_hash, basis, verified_at, expires_at)
            VALUES (%s, 'burkham-wickmont', %s, %s, 'compliance/referral-fee-v1',
                    'NV Rev. Stat. 645F', %s, 'venture operator', 'counsel_memo',
                    'sha256:0000', %s, %s, %s)
            """,
            (uuid.uuid4(), FLAG, scope, HUMAN, basis,
             verified, now + timedelta(days=expires_in_days)),
        )
    admin.commit()


async def test_v34_fails_when_no_discharge_exists(burkham, no_discharges):
    """Burkham today. The obligation is declared human-held and nobody has verified it.

    **This is a FAIL, not a NOT_RUN.** An absent row is an answer. Three NOT_RUNs were
    misread as "not checked yet" in the week this was built; a fourth that meant "no
    discharge required" would read as permission.
    """
    async with connection() as conn:
        report = await validate(burkham, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.FAIL, result.message
    assert FLAG in result.message
    assert "no discharge record exists" in result.message


async def test_v34_does_not_report_not_run_when_it_could_ask(burkham, no_discharges):
    """The distinction the rule's docstring is about, asserted rather than described."""
    async with connection() as conn:
        report = await validate(burkham, conn)

    assert report.get("V34").verdict is not Verdict.NOT_RUN


async def test_v22_still_passes_while_v34_fails(burkham, no_discharges):
    """The split, and the reason for it.

    A missing discharge must never arrive as "a flag no scenario exercises" — that is
    V22's sentence and it names the wrong problem. Whoever reads this failure should be
    sent to a person, not to an author.
    """
    async with connection() as conn:
        report = await validate(burkham, conn)

    assert report.get("V22").verdict is Verdict.PASS
    assert report.get("V34").verdict is Verdict.FAIL
    assert FLAG not in report.get("V22").message.split("human-held")[0]


async def test_v34_passes_with_a_current_discharge_covering_the_footprint(
    burkham, no_discharges, admin
):
    """The only state that clears it, and it is a human act rather than a code change."""
    geographies = [g.strip() for g in burkham.market.target_geographies if g.strip()]
    _file_discharge(admin, scope=geographies, expires_in_days=180)

    async with connection() as conn:
        report = await validate(burkham, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.PASS, result.message


async def test_v34_fails_on_an_expired_discharge(burkham, no_discharges, admin):
    """"Verified in 2026" and "verified" are different claims, and `expires_at` is what
    keeps them apart."""
    geographies = [g.strip() for g in burkham.market.target_geographies if g.strip()]
    _file_discharge(admin, scope=geographies, verified_days_ago=400, expires_in_days=-1)

    async with connection() as conn:
        report = await validate(burkham, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.FAIL, result.message
    assert "expired" in result.message


async def test_v34_fails_when_the_discharge_does_not_reach_the_venture(
    burkham, no_discharges, admin
):
    """The "new state" trigger, which is the one that is not time-based.

    A discharge that cannot express its own scope silently keeps covering ground it
    never examined. This asserts it does not.
    """
    _file_discharge(admin, scope=["Nevada"], expires_in_days=180)

    async with connection() as conn:
        report = await validate(burkham, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.FAIL, result.message
    assert "does not reach" in result.message


async def test_v34_says_nothing_to_discharge_rather_than_passing_silently():
    """Greenstone declares no human-held obligation.

    A pass with nothing to check must be distinguishable from a pass that checked
    something — the distinction P-09 drew when its own V33 passed against an empty
    table. The verdict is the same; the message is not, and the message is the part a
    reader acts on.
    """
    greenstone = load_pack(GREENSTONE)

    async with connection() as conn:
        report = await validate(greenstone, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.PASS
    assert "nothing to discharge" in result.message


async def test_a_blank_basis_is_refused_by_the_schema(admin, no_discharges):
    """Not by a code path somebody can forget to call.

    A discharge without a sentence saying what was verified is the accidental-empty
    problem `NoFramework` was built to refuse: nothing can tell a considered discharge
    from a row added to make a rule go quiet.
    """
    with pytest.raises(psycopg.errors.CheckViolation):
        _file_discharge(admin, scope=["Nevada"], expires_in_days=180, basis="   ")
    admin.rollback()
