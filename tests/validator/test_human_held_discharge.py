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
from datetime import UTC, datetime, timedelta
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
    """Burkham as authored: its obligation is `pending_activation`."""
    return load_pack(BURKHAM)


@pytest.fixture
def burkham_live() -> BusinessPack:
    """Burkham with the obligation moved to `live_unverified`.

    The Pack declares `pending_activation`, so the tests about a DUE obligation have to
    say which state they are about rather than inherit it. Stripping the declaration
    here is what "the trigger fired" looks like from the validator's side: the
    obligation is live, and a discharge is now required.
    """
    pack = load_pack(BURKHAM)
    entry = next(
        c for c in pack.market.compliance_surface
        if c.runtime_flag == FLAG and c.human_held is not None
    )
    assert entry.human_held is not None
    object.__setattr__(entry.human_held, "pending_activation", None)
    return pack


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
    now = datetime.now(UTC)
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


async def test_v34_fails_when_no_discharge_exists(burkham_live, no_discharges):
    """Burkham today. The obligation is declared human-held and nobody has verified it.

    **This is a FAIL, not a NOT_RUN.** An absent row is an answer. Three NOT_RUNs were
    misread as "not checked yet" in the week this was built; a fourth that meant "no
    discharge required" would read as permission.
    """
    async with connection() as conn:
        report = await validate(burkham_live, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.FAIL, result.message
    assert FLAG in result.message
    assert "no discharge record exists" in result.message


async def test_v34_does_not_report_not_run_when_it_could_ask(burkham_live, no_discharges):
    """The distinction the rule's docstring is about, asserted rather than described."""
    async with connection() as conn:
        report = await validate(burkham_live, conn)

    assert report.get("V34").verdict is not Verdict.NOT_RUN


async def test_v22_still_passes_while_v34_fails(burkham_live, no_discharges):
    """The split, and the reason for it.

    A missing discharge must never arrive as "a flag no scenario exercises" — that is
    V22's sentence and it names the wrong problem. Whoever reads this failure should be
    sent to a person, not to an author.
    """
    async with connection() as conn:
        report = await validate(burkham_live, conn)

    assert report.get("V22").verdict is Verdict.PASS
    assert report.get("V34").verdict is Verdict.FAIL
    assert FLAG not in report.get("V22").message.split("human-held")[0]


async def test_v34_passes_with_a_current_discharge_covering_the_footprint(
    burkham_live, no_discharges, admin
):
    """The only state that clears it, and it is a human act rather than a code change."""
    geographies = [g.strip() for g in burkham_live.market.target_geographies if g.strip()]
    _file_discharge(admin, scope=geographies, expires_in_days=180)

    async with connection() as conn:
        report = await validate(burkham_live, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.PASS, result.message


async def test_v34_fails_on_an_expired_discharge(burkham_live, no_discharges, admin):
    """"Verified in 2026" and "verified" are different claims, and `expires_at` is what
    keeps them apart."""
    geographies = [g.strip() for g in burkham_live.market.target_geographies if g.strip()]
    _file_discharge(admin, scope=geographies, verified_days_ago=400, expires_in_days=-1)

    async with connection() as conn:
        report = await validate(burkham_live, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.FAIL, result.message
    assert "expired" in result.message


async def test_v34_fails_when_the_discharge_does_not_reach_the_venture(
    burkham_live, no_discharges, admin
):
    """The "new state" trigger, which is the one that is not time-based.

    A discharge that cannot express its own scope silently keeps covering ground it
    never examined. This asserts it does not.
    """
    _file_discharge(admin, scope=["Nevada"], expires_in_days=180)

    async with connection() as conn:
        report = await validate(burkham_live, conn)

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


# --------------------------------------------------------- pending_activation

async def test_v34_passes_on_pending_activation_without_any_discharge(
    burkham, no_discharges
):
    """The one state that passes without a discharge, and the one that could become
    the escape in a fourth costume.

    It passes because no verification is DUE - not because the obligation was
    discharged. The message has to carry that difference, since a pass that cannot
    distinguish "verified" from "not yet due" is the shape V34 exists to refuse one
    level up.
    """
    async with connection() as conn:
        report = await validate(burkham, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.PASS, result.message
    assert "pending_activation" in result.message
    assert "no verification is due until" in result.message
    # The trigger itself, not a summary of it: a reviewer checks the condition, and
    # they can only do that if the verdict tells them what it is.
    assert "Module 8.2" in result.message


async def test_v34_still_fails_when_a_live_obligation_has_no_discharge(
    burkham_live, no_discharges
):
    """The regression guard for `pending_activation`.

    The new state must not make every human-held obligation pass. The same Pack with
    the declaration stripped - which is what "the trigger fired" looks like from the
    validator's side - must fail exactly as it did before the state existed.
    """
    async with connection() as conn:
        report = await validate(burkham_live, conn)

    result = report.get("V34")
    assert result.verdict is Verdict.FAIL, result.message
    assert "no discharge record exists" in result.message


def test_the_schema_refuses_a_trigger_nobody_could_check():
    """`min_length` catches the empty string and the one-word placeholder.

    It cannot judge whether a condition is checkable - that is a semantic question
    about the world, and a validator pretending to answer it would assert something it
    cannot know. The reviewer does that, and `PendingActivation`'s docstring says so.
    What the schema can refuse is a trigger that is not a sentence at all.
    """
    import pydantic

    from generators.pack import PendingActivation

    with pytest.raises(pydantic.ValidationError):
        PendingActivation(activates_when="", deferred_to="V1.5")
    with pytest.raises(pydantic.ValidationError):
        PendingActivation(activates_when="soon", deferred_to="V1.5")
    with pytest.raises(pydantic.ValidationError):
        PendingActivation(activates_when="Module 8.2 activates and a relationship forms",
                          deferred_to="")


# ------------------------------------------------- capacity provenance (B20/B21)

def test_every_capacity_entry_declares_where_its_numbers_came_from():
    """Both Packs, all four entries. **The old entries are not exempt.**

    A field that new entries must fill while existing ones sit exempt documents nothing,
    and filling the four that already existed is what retires B20 and B21 by construction
    rather than by trust.
    """
    for path in (BURKHAM, GREENSTONE):
        pack = load_pack(path)
        assert pack.human_capacity, path
        for h in pack.human_capacity:
            assert h.provenance is not None, f"{path} {h.human_name}"
            assert h.provenance.basis in ("declared", "inherited", "measured")
            assert h.provenance.established_by.strip()
            assert len(h.provenance.detail.strip()) >= 20


def test_burkham_no_longer_borrows_greenstone_capacity():
    """B20's condition, from the other side.

    Burkham's block used to be `inherited`, byte-for-byte Greenstone's, and this test
    asserted that the borrowing was at least recorded. On 2026-09-08 Ivan Green declared
    Burkham's own two reviewers, so the thing being guarded flipped: the assertion is no
    longer that the copy is labelled, it is that there is no copy left to label.

    Kept rather than deleted because a removed test is a guard nobody misses. If somebody
    reintroduces a borrowed capacity block, this fails and names B20.
    """
    pack = load_pack(BURKHAM)
    for h in pack.human_capacity:
        assert h.provenance.basis == "declared", (
            f"{h.human_name}: Burkham declares its own reviewers now - an `inherited` "
            f"basis here means somebody re-borrowed a capacity block. See B20."
        )
        assert h.provenance.source is None
        assert "greenstone" not in h.provenance.detail.lower()


def test_burkham_states_its_v13_margin_where_a_reader_meets_it_first():
    """A pass with twelve minutes in it should not read like capacity.

    120 projected daily approvals x the coverage-weighted 3.5 minutes is 420 review
    minutes against 432 available. One more workflow step, or one more position below
    `auto_execute`, and V13 fails. Nothing in the rule output says how close it is - a
    PASS looks identical at 12 minutes of margin and at 12 hours - so the Pack says it,
    above the entries rather than buried under them.
    """
    text = BURKHAM.read_text(encoding="utf-8")
    block = text.split("human_capacity:", 1)[1].split("- human_name:", 1)[0]
    assert "twelve minutes" in block.lower()
    assert "420" in block and "432" in block


def test_burkham_names_the_v14_weakness_it_satisfies():
    """The Pack should know its own weak point.

    Two compliance officers naming each other satisfies V14 - which checks only that
    `backup_human` is non-empty - while making both critical-role backups the same two
    people. That is the arrangement V14 looks like it exists to catch, and it is stated
    in the provenance rather than left for a reader to notice.
    """
    pack = load_pack(BURKHAM)
    names = [h.human_name for h in pack.human_capacity]
    assert [h.backup_human for h in pack.human_capacity] == list(reversed(names)), (
        "the two reviewers back each other up, which is the arrangement being disclosed"
    )
    disclosure = " ".join(h.provenance.detail.lower() for h in pack.human_capacity)
    assert "v14" in disclosure and "b24" in disclosure


def test_greenstone_declares_its_numbers_declared_not_measured():
    """B21's finding, in the file rather than only in the record.

    Nothing measured them. Recording them as `measured` would be the false value a
    schema that cannot express an honest absence invites - which is the pattern this
    field is the third application of.
    """
    pack = load_pack(GREENSTONE)
    for h in pack.human_capacity:
        assert h.provenance.basis == "declared", h.human_name


def test_inherited_without_a_named_source_is_refused():
    """`historical` is the cheap escape wearing a third costume."""
    import pydantic

    from generators.pack import CapacityProvenance

    ok = dict(established_by="Ivan",
              detail="Copied when the Pack was authored so the comparison was like for like.")
    for bad in (None, "historical", "legacy"):
        with pytest.raises(pydantic.ValidationError):
            CapacityProvenance(basis="inherited", source=bad, **ok)
    # A named, checkable source is accepted.
    CapacityProvenance(basis="inherited",
                       source="packs/greenstone.yaml human_capacity block", **ok)


def test_a_provenance_that_says_nothing_is_refused():
    """The field exists to refuse this, not to hold it."""
    import pydantic

    from generators.pack import CapacityProvenance

    with pytest.raises(pydantic.ValidationError):
        CapacityProvenance(basis="declared", established_by="I", detail="x" * 25)
    with pytest.raises(pydantic.ValidationError):
        CapacityProvenance(basis="declared", established_by="Ivan", detail="asserted")
