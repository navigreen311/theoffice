"""Every compliance flag names its framework and says why the module implies it.

The registry pass that wrote these got eight of nine rows wrong and every check in
the system stayed green: verify_forge_modules checks that a row RESOLVES, not that
its values are right, and the Pack validator compares module ids rather than flags.

These tests are the check that did not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from broker import compliance_couplings as cc

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "packs" / "burkham-wickmont.draft.yaml"


def test_every_flag_carries_a_sentence():
    """The whole point. A flag without a reason is a flag nobody read for."""
    for module_id, decl in cc.CAPITALFORGE.items():
        if isinstance(decl.couplings, cc.NoFramework):
            assert decl.couplings.why.strip(), module_id
            continue
        for coupling in decl.couplings:
            assert coupling.why.strip(), f"{module_id}/{coupling.flag}"
            # A sentence, not a label. The failure mode is a plausible-looking
            # value, so a two-word justification is the same defect restated.
            assert len(coupling.why.split()) >= 8, (
                f"{module_id}/{coupling.flag}: {coupling.why!r} is too short to be "
                "a reason. Say why THIS module implies it."
            )


def test_every_exclusion_carries_a_reason():
    """A flag left off without a stated reason reads as forgotten."""
    for module_id, decl in cc.CAPITALFORGE.items():
        for excluded in decl.excluded:
            assert excluded.why.strip(), f"{module_id}/{excluded.flag}"


def test_no_module_declares_an_empty_list_by_default():
    """An empty list is a claim that no framework applies.

    Four of the nine rows were empty by accident and nothing could tell that apart
    from a considered none. `NoFramework` is how a considered none is written.
    """
    for module_id, decl in cc.CAPITALFORGE.items():
        if isinstance(decl.couplings, cc.NoFramework):
            continue
        assert decl.couplings, (
            f"{module_id}: empty couplings tuple. Use NoFramework(why=...) if no framework applies."
        )


def test_flags_resolve_against_the_pack():
    """A flag no Pack declares cannot propagate, so it couples nothing."""
    declared = set(re.findall(r"runtime_flag:\s*([a-z_]+)", PACK.read_text(encoding="utf-8")))
    assert declared, "no runtime_flag entries found in the Pack"

    for module_id, decl in cc.CAPITALFORGE.items():
        for flag in decl.flags:
            assert flag in declared, f"{module_id}: {flag!r} is in no Pack"


def test_the_framework_map_covers_every_pack_flag():
    """FRAMEWORKS is what makes the sentence sayable - name the framework."""
    declared = set(re.findall(r"runtime_flag:\s*([a-z_]+)", PACK.read_text(encoding="utf-8")))
    missing = sorted(declared - set(cc.FRAMEWORKS))
    assert not missing, f"flags with no framework recorded: {missing}"


def test_a_module_with_no_declaration_raises_rather_than_defaulting():
    """The failure that produced four empty rows.

    Returning [] for an unknown module writes 'no framework applies' into the
    database as though somebody had decided it.
    """
    with pytest.raises(cc.CouplingError):
        cc.flags_for("capitalforge", "lender_match")

    with pytest.raises(cc.CouplingError):
        cc.flags_for("cre-forge", "property_lookup")


def test_the_two_flags_that_were_wrong_are_recorded_as_excluded():
    """Both were plausible inferences standing in for a reading.

    Recorded rather than merely absent, so the next author finds the reasoning
    instead of re-deriving the same wrong answer.
    """
    consent = cc.CAPITALFORGE["record_consent"]
    assert "per_connection_authorization_required" in {e.flag for e in consent.excluded}
    assert "per_connection_authorization_required" not in consent.flags

    credit = cc.CAPITALFORGE["client_read_credit"]
    assert "per_pull_authorization_required" in {e.flag for e in credit.excluded}
    assert "per_pull_authorization_required" not in credit.flags

    submit = cc.CAPITALFORGE["submit_application"]
    assert "per_application_authorization_required" in {e.flag for e in submit.excluded}
    assert "per_application_authorization_required" not in submit.flags


def test_a_flag_is_never_both_coupled_and_excluded():
    for module_id, decl in cc.CAPITALFORGE.items():
        overlap = set(decl.flags) & {e.flag for e in decl.excluded}
        assert not overlap, f"{module_id}: {overlap}"
