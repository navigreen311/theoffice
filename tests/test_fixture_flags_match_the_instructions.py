"""The fixture's flags must agree with the manual the module actually has - entry 105.

`tests/world.py` gave every module of a Forge ONE flag list. That is how five CRE Forge
modules came to imply `tsr_disclosure_required`: a telemarketing-disclosure duty on a
property search, a comps pull, an underwriting calculation, a buyer ranking and a
contract draft. **Nobody read five modules and got five wrong answers - nobody read a
module.**

Nothing caught it, and each check had a good reason: the verifier confirms a row resolves
against the adapter and never touches this column; V6 and V32 compare module ids; V28
resolves the ref, which exists because Greenstone wrote it. **The artefact that disagreed
was the manual** - all five authored CRE Forge instructions say
`compliance_coupling: ["no_framework_applies"]` - and nothing compared the two.

This is that comparison. It reads the real manuals out of
`scripts/author_cre_forge_instructions.py`, which is where they are written, so it needs
no database and cannot pass because a fixture agrees with itself.
"""

from __future__ import annotations

from scripts.author_cre_forge_instructions import MANUALS
from tests.world import CRE_MODULES, FORGE_ID, MODULE_FLAGS

#: What an authored manual says when no framework reaches the module.
NO_FRAMEWORK = "no_framework_applies"


def test_every_cre_forge_module_has_a_manual_here():
    """The comparison is only as good as its coverage, so the coverage is asserted."""
    assert set(MANUALS) == set(CRE_MODULES), (
        "the fixture and the authored manuals disagree about which modules exist: "
        f"{sorted(set(CRE_MODULES) ^ set(MANUALS))}"
    )


def test_a_fixture_module_carries_no_flag_its_manual_says_does_not_apply():
    """The defect, as a property.

    A manual saying `no_framework_applies` and a registry row implying a framework are
    two answers to one question, and the row is the one the runtime reads: it reaches
    `effective_compliance_flags`, routes approvals to the compliance officer, and until
    entry 105 decided whether a failed audit write halted the call.
    """
    wrong: list[str] = []
    for module_id, manual in sorted(MANUALS.items()):
        coupling = list(manual["compliance_coupling"])
        fixture_flags = MODULE_FLAGS[(FORGE_ID, module_id)]
        if NO_FRAMEWORK in coupling and fixture_flags:
            wrong.append(
                f"{FORGE_ID}/{module_id}: manual says {NO_FRAMEWORK}, fixture implies "
                f"{fixture_flags}"
            )

    assert not wrong, "\n".join(wrong)


def test_a_fixture_module_carries_every_flag_its_manual_claims():
    """The other direction, which has never been the failing one.

    Every wrong flag found in this system so far has been a flag ADDED, never one left
    off - `broker/compliance_couplings.py` says so. Asserting both directions is what
    makes that a measurement rather than a habit.
    """
    missing: list[str] = []
    for module_id, manual in sorted(MANUALS.items()):
        coupling = {f for f in manual["compliance_coupling"] if f != NO_FRAMEWORK}
        fixture_flags = set(MODULE_FLAGS[(FORGE_ID, module_id)])
        if coupling - fixture_flags:
            missing.append(
                f"{FORGE_ID}/{module_id}: manual claims {sorted(coupling)}, fixture "
                f"implies {sorted(fixture_flags)}"
            )

    assert not missing, "\n".join(missing)


def test_the_fixture_does_not_give_a_forge_one_list_for_every_module():
    """The shape of the defect, not just its instances.

    A per-Forge blanket is why one wrong reading became five wrong rows, and why the
    same shape put Greenstone's flag on two SimForge modules. VoiceForge's two modules
    legitimately share a flag - both touch a recorded call - so this asserts that the
    map is keyed per module rather than that its values differ.
    """
    assert all(isinstance(key, tuple) and len(key) == 2 for key in MODULE_FLAGS), (
        "MODULE_FLAGS is keyed (forge_id, module_id): a flag belongs to a module"
    )
    assert {module for forge, module in MODULE_FLAGS if forge == FORGE_ID} == set(
        CRE_MODULES
    ), "every CRE Forge module names its own flags, even when the answer is none"
