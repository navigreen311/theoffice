"""V39 — the sum no Pack could take, because no Pack can see another.

WHAT IT IS FOR, IN ONE NUMBER THAT WAS TRUE FOR THREE WEEKS

    Decisions entry 94 section 5 recorded Ivan at sixteen hours a day - six in Greenstone,
    six in Burkham, four more proposed - and noted, as a measured fact, that **nothing
    anywhere sums a person across ventures, which is why neither total has ever been
    refused.** Coverage is declared inside one venture's Pack and no Pack can see another.

WHY IT COULD NOT BE WRITTEN UNTIL NOW

    The only thing that resolves a Pack name to a person is `office_human.display_name`.
    Two things had to be true first, and neither was:

      migration 0040   two accounts could hold one display name, so the key was not a key
      the rename       one person held two names - "Ivan Green" in Burkham's Pack and
                       "Ivan" in Greenstone's - so a name-keyed sum saw two people, each
                       comfortably under their own total

    `test_two_spellings_of_one_name_are_not_two_people` is the second of those, pinned. It
    is the failure mode entry 96 named when it said the obstacle was identity, and it fails
    silently: two halves of one person, each under the ceiling, no warning anywhere.
"""

from __future__ import annotations

import json
import uuid

import psycopg
import pytest

from broker.db import connection
from generators.pack import load_pack
from generators.validator import validate
from tests.world import PACK_PATH

OTHER = "burkham-wickmont"
AUTHOR = uuid.UUID("00000000-0000-5000-8000-00000000f39a")


def _account(admin: psycopg.Connection, name: str, total: float | None) -> uuid.UUID:
    human_id = uuid.uuid4()
    with admin.cursor() as cur:
        cur.execute(
            """
            INSERT INTO office_human
              (human_id, display_name, email, auth_method, status, created_at, origin,
               daily_total_hours)
            VALUES (%s, %s, %s, 'bearer_token', 'active', now(), 'test_fixture', %s)
            """,
            (human_id, name, f"v39-{human_id}@example.invalid", total),
        )
    admin.commit()
    return human_id


def _live_pack(admin: psycopg.Connection, venture: str, capacity: list[dict]) -> None:
    """A live Pack for another venture, carrying only what V39 reads."""
    parsed = {"human_capacity": capacity}
    with admin.cursor() as cur:
        cur.execute("DELETE FROM business_pack WHERE venture_id = %s", (venture,))
        cur.execute(
            """
            INSERT INTO office_human
              (human_id, display_name, email, auth_method, status, created_at, origin)
            VALUES (%s, 'V39 Pack Author', 'v39-author@example.invalid',
                    'bearer_token', 'active', now(), 'test_fixture')
            ON CONFLICT (human_id) DO NOTHING
            """,
            (AUTHOR,),
        )
        cur.execute(
            """
            INSERT INTO business_pack
              (venture_id, pack_version, schema_version, yaml_source, parsed,
               content_hash, authored_by, status)
            VALUES (%s, '9.9.9', 3, 'fixture', %s, 'fixture', %s, 'live')
            """,
            (venture, json.dumps(parsed), AUTHOR),
        )
    admin.commit()


def _entry(name: str, hours: float, *, source: str | None = None) -> dict:
    provenance = {"basis": "declared", "established_by": name, "detail": "x" * 25}
    if source is not None:
        provenance = {"basis": "measured", "established_by": name,
                      "detail": "x" * 25, "source": source}
    return {"human_name": name, "coverage_hours": hours, "provenance": provenance}


@pytest.fixture
def clean_packs(admin: psycopg.Connection):
    yield
    with admin.cursor() as cur:
        cur.execute("DELETE FROM business_pack WHERE pack_version = '9.9.9'")
        cur.execute("DELETE FROM office_human WHERE origin = 'test_fixture'")
    admin.commit()


def _greenstone_naming(name: str, hours: float):
    """The real Pack carrying ONE human: the person under test.

    The other entry is dropped rather than kept, because V39 reports on everyone a Pack
    names and Greenstone's compliance officer has no account in a disposable world - so
    every assertion here would be read past a true warning about somebody else. The rule
    still sees a real Pack; it just sees one person in it.
    """
    pack = load_pack(PACK_PATH)
    operator = next(h for h in pack.human_capacity if h.role == "venture_operator")
    return pack.model_copy(
        update={
            "human_capacity": [
                operator.model_copy(update={
                    "human_name": name,
                    "coverage_hours": hours,
                    "review_hours": hours,
                    "countersign_hours": 0.0,
                    "other_hours": 0.0,
                    "backup_human": None,
                })
            ]
        }
    )


async def test_over_the_total_warns_and_names_each_ventures_share(admin, clean_packs):
    """Eight declared elsewhere plus four here, against a total of eight.

    The message has to carry all four things a reader needs to act: who, what each venture
    asked of them, what they said their day holds, and which of those figures is an
    assertion rather than a measurement. A warning that says only "over" sends somebody
    looking through two Packs to find out by how much and where.
    """
    _account(admin, "Portfolio Person", 8.0)
    _live_pack(admin, OTHER, [_entry("Portfolio Person", 8.0)])
    pack = _greenstone_naming("Portfolio Person", 4.0)

    async with connection() as conn:
        report = await validate(pack, conn)
    v39 = report.get("V39")

    assert v39.verdict.value == "WARN"
    assert "Portfolio Person" in v39.message
    assert "burkham-wickmont 8h" in v39.message
    assert "greenstone 4h" in v39.message
    assert "daily total of 8h" in v39.message
    assert "4h over" in v39.message
    # ONLY BURKHAM. Ruled 2026-09-16: a founder's own declaration IS a source for that
    # founder's hours, and Greenstone's provenance cites the ruling entries behind its
    # figures. What stays flagged is a number with no ruling and no measurement behind it -
    # which is Burkham's six-hour block, copied wholesale from Greenstone's (B20, B21).
    assert "Unsourced declarations: burkham-wickmont." in v39.message
    assert "greenstone" not in v39.message.split("Unsourced declarations:")[1]
    # And it says what it could not see.
    assert "Ventures with no live Pack are not counted" in v39.message


async def test_within_the_total_passes(admin, clean_packs):
    """Four and four against eight. The same two Packs, one hour fewer."""
    _account(admin, "Portfolio Person", 8.0)
    _live_pack(admin, OTHER, [_entry("Portfolio Person", 4.0)])
    pack = _greenstone_naming("Portfolio Person", 4.0)

    async with connection() as conn:
        report = await validate(pack, conn)
    v39 = report.get("V39")

    assert v39.verdict.value == "PASS", v39.message
    assert "fits their declared daily total" in v39.message


async def test_two_spellings_of_one_name_are_not_two_people(admin, clean_packs):
    """**The failure this rule waited for the rename to avoid, pinned so it cannot return.**

    One person, eight hours in each of two Packs, a declared total of eight. Spelled the
    same way in both, that is sixteen against eight and a warning. Spelled "Ivan Green" in
    one and "Ivan" in the other - which is exactly how the two live Packs read until
    2026-09-16 - the sum splits, each half is under, and **nothing is reported at all.**

    So the test asserts the silence is gone: with one spelling the rule fires, and the
    second half of the test shows what the old state produced, which is a PASS for a person
    working sixteen hours.
    """
    _account(admin, "Ivan Green", 8.0)
    _live_pack(admin, OTHER, [_entry("Ivan Green", 8.0)])

    async with connection() as conn:
        matched = await validate(_greenstone_naming("Ivan Green", 8.0), conn)
        split = await validate(_greenstone_naming("Ivan", 8.0), conn)

    assert matched.get("V39").verdict.value == "WARN"
    assert "16h across 2 venture(s)" in matched.get("V39").message

    # The old state. The second spelling matches no account, so the rule cannot add the
    # halves - and it says so by name rather than passing quietly, which is the one thing
    # that makes the split visible at all.
    message = split.get("V39").message
    assert split.get("V39").verdict.value == "WARN"
    assert "'ivan'" in message
    assert "matches no account" in message
    assert "16h" not in message, (
        "the two spellings must not have been summed; that is what the rename fixed, "
        "not something the rule can do on its own"
    )


async def test_a_person_with_no_declared_total_is_named_not_assumed(admin, clean_packs):
    """A missing total is reported. Assuming twenty-four, or eight, would be the constant
    this repository spent a week removing, one column over."""
    _account(admin, "Untotalled Person", None)
    _live_pack(admin, OTHER, [_entry("Untotalled Person", 8.0)])
    pack = _greenstone_naming("Untotalled Person", 8.0)

    async with connection() as conn:
        report = await validate(pack, conn)
    v39 = report.get("V39")

    assert v39.verdict.value == "WARN"
    assert "has declared no daily total" in v39.message
    assert "daily-total route" in v39.message


async def test_a_sourced_declaration_is_not_flagged_even_when_it_is_over(
    admin, clean_packs
):
    """`unsourced` means nothing named behind the number, not merely over the total.

    Both sides carry a source here - Burkham a measurement, Greenstone the ruling entries
    its real Pack cites - so the overage is reported and nothing is flagged. **The warning
    about hours and the flag about provenance are two findings, and this is the case that
    separates them.**
    """
    _account(admin, "Sourced Person", 8.0)
    _live_pack(
        admin, OTHER,
        [_entry("Sourced Person", 8.0, source="Timed across 40 reviews in August")],
    )
    pack = _greenstone_naming("Sourced Person", 4.0)

    async with connection() as conn:
        report = await validate(pack, conn)
    v39 = report.get("V39")

    assert v39.verdict.value == "WARN"
    assert "4h over" in v39.message
    assert "Every declaration behind that names a source." in v39.message
    assert "Unsourced declarations" not in v39.message


async def test_greenstones_ruling_citation_counts_as_a_source(admin, clean_packs):
    """Ruling 2, on the real Pack rather than a constructed one.

    Greenstone's two capacity entries are `basis: declared` and cite decisions entries for
    the hours. A founder's own ruling is a source for that founder's hours, so neither is
    flagged - while Burkham's six-hour block, which cites nothing, still is.
    """
    from generators.pack import load_pack as _load

    real = _load(PACK_PATH)
    assert [h.human_name for h in real.human_capacity] == ["Ivan Green", "Ira Green"]
    for entry in real.human_capacity:
        assert entry.provenance.basis == "declared"
        assert "decisions.md entry" in (entry.provenance.source or ""), (
            f"{entry.human_name}'s hours cite no ruling, so V39 will flag them"
        )


def test_v39_is_a_warning_and_the_trigger_for_making_it_block_is_recorded():
    """Ruled 2026-09-16: it warns until Burkham publishes its real hours.

    Asserted rather than left in prose, because "it will become blocking" is the kind of
    sentence that survives the thing it was waiting for. If somebody makes it FAIL, this
    fails with it and they have to come and read why it was a warning.
    """
    from generators.validator import _WORLD_RULES, Severity

    severity, description, _fn = _WORLD_RULES["V39"]
    assert severity is Severity.WARN
    assert "daily total" in description

    from generators import validator

    source = validator.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "becomes blocking when Burkham's Pack publishes" in text, (
        "the trigger that turns this into a FAIL left the code"
    )
