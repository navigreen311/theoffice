"""Entry 48 - a qualification is a third kind of change, and the exception must stay narrow.

`_predated_tightenings` handled two error shapes and refused everything else, in terms:

    "A wrong type or a failed validator is a document that disagrees with the schema,
     not one that is older than it."

**That refusal was correct until there was one.** B21 added a field that was not there
(`missing`); B23 renamed one (`extra_forbidden` + `missing`). Entry 48 is the first change
where the field is PRESENT, POPULATED, and means exactly what it always meant - only the
required spelling moved, from `client_read` to `capitalforge/client_read`. That arrives as
a validator failure, which the guard refused by design.

So the guard keeps its rule and gains one named exception: an error the validator itself
marks `unqualified_module_ref`, at a path `V3_QUALIFICATIONS` names. The validator makes
the distinction once, where the values are in hand, and the matcher reads the signal
rather than re-deriving it - a second derivation is a second place to disagree.

## What these tests protect

**The narrowness, not the exception.** Widening a guard is easy and it is the wrong half
of the job: the widened path passes, and nothing asks what it stopped refusing. So the
disqualifying cases outnumber the explaining one, and the sharpest of them is
`capitalforge/client_read/extra` - a value at the SAME field, in the SAME position, which
no revision of v3 ever accepted. If that reports as *old*, the exception has swallowed the
rule and the ledger is telling a reader to run a migration that cannot help.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from broker import packs

PACK_PATH = Path(__file__).resolve().parents[2] / "packs" / "burkham-wickmont.draft.yaml"
FIELD = "forge_modules_operated"


def current() -> dict[str, Any]:
    """Today's Pack, parsed. Every fixture below is this document, minus one migration."""
    return yaml.safe_load(PACK_PATH.read_text(encoding="utf-8"))


def dump(raw: dict[str, Any]) -> str:
    return yaml.safe_dump(raw, sort_keys=False)


def as_written_before_the_qualification(raw: dict[str, Any]) -> dict[str, Any]:
    """Today's Pack as the revision before entry 48 would have written it.

    Constructed by stripping the forge from each entry - not by transcribing an old Pack -
    so the only difference from the current file is the qualification itself. The
    assertions check that claim rather than trusting it.
    """
    out = copy.deepcopy(raw)
    for position in out["positions_required"]:
        position[FIELD] = [m.split("/", 1)[1] for m in position[FIELD]]
    return out


def test_a_bare_module_list_is_recognised_as_predating_the_qualification() -> None:
    """The explaining case, and the only one in this file."""
    with pytest.raises(packs.PackPredatesTighteningError) as caught:
        packs.parse_only(dump(as_written_before_the_qualification(current())))

    predates = caught.value.predates
    assert len(predates) == 1, [c.label for c in predates]
    change = predates[0]
    assert isinstance(change, packs.SchemaQualification)
    assert change.field_path == ("positions_required", FIELD)
    assert change.error_type == "unqualified_module_ref"

    message = str(caught.value)
    assert "entry 48" in message
    assert "2026-09-14" in message
    # The discriminator travels with the diagnosis, so a reader learns the RULE rather
    # than this instance of it.
    assert "QUALIFY WHERE THE FIELD DOES NOT ALREADY CARRY THE FORGE" in message.upper()
    # And it says the field is there, because "absent from 5 entries" would send a reader
    # looking for a missing key.
    assert "PRESENT" in message.upper()


def test_a_three_part_reference_is_malformed_and_not_old() -> None:
    """**The test that proves the exception stayed narrow.**

    Same field, same position, same validator - and a value no revision of v3 ever
    accepted. It must report as a malformed document, because telling a reader to
    republish would send them to a migration that cannot help: there is no earlier
    revision under which `capitalforge/client_read/extra` was correct.
    """
    raw = current()
    raw["positions_required"][0][FIELD] = ["capitalforge/client_read/extra"]

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw))

    assert not isinstance(caught.value, packs.PackPredatesTighteningError), (
        "a three-part module reference was diagnosed as a Pack that predates the "
        "qualification. It does not predate anything - no revision of v3 accepted it - "
        "and the diagnosis sends the reader to republish, which cannot help. The "
        "exception has swallowed the rule it was carved out of."
    )
    assert "not a schema-v3 Business Pack" in str(caught.value)


def test_a_bare_list_mixed_with_a_real_defect_is_malformed() -> None:
    """One unexplained error disqualifies the whole diagnosis, unchanged.

    A row that predates the qualification AND carries something genuinely wrong is a
    document to inspect. Reporting it as merely old is the same false confidence B27
    removed, pointing the other way.
    """
    raw = as_written_before_the_qualification(current())
    raw["positions_required"][0]["headcount"] = 0  # never valid at any revision

    with pytest.raises(packs.PackStoreError) as caught:
        packs.parse_only(dump(raw))
    assert not isinstance(caught.value, packs.PackPredatesTighteningError)


def test_the_ledger_entry_is_not_decoration() -> None:
    """Remove the entry and the same document reports as malformed.

    The mirror of the rename test's guard: this asserts the diagnosis comes from the
    LEDGER rather than from the error type alone. Without it, a future qualification
    could be recognised by a signal nobody registered.
    """
    raw = dump(as_written_before_the_qualification(current()))
    without = tuple(
        c for c in packs.V3_SCHEMA_CHANGES if not isinstance(c, packs.SchemaQualification)
    )
    original_all, original_quals = packs.V3_SCHEMA_CHANGES, packs.V3_QUALIFICATIONS
    try:
        packs.V3_SCHEMA_CHANGES = without  # type: ignore[misc]
        packs.V3_QUALIFICATIONS = ()  # type: ignore[misc]
        with pytest.raises(packs.PackStoreError) as caught:
            packs.parse_only(raw)
        assert not isinstance(caught.value, packs.PackPredatesTighteningError), (
            "the document was diagnosed as old with no ledger entry explaining it, so "
            "the diagnosis is coming from the error type alone. The path must be one the "
            "ledger names."
        )
    finally:
        packs.V3_SCHEMA_CHANGES = original_all  # type: ignore[misc]
        packs.V3_QUALIFICATIONS = original_quals  # type: ignore[misc]


def test_todays_pack_parses() -> None:
    """The control. If this fails the fixtures above prove nothing."""
    assert packs.parse_only(PACK_PATH.read_text(encoding="utf-8")) is not None
