"""cre-forge declares its couplings, and the vocabulary says whose it is.

RULED 22 SEPTEMBER 2026 (decisions entries 160 and 161)
=======================================================

    160. *"cre-forge's coupling declarations are registered from its manuals. Use the
         four NoFramework drafts as written. For assign_contract, register nothing and
         record it as a pending counsel question: whether a Nevada wholesaling
         assignment requires a licence."*

    161. *"The framework vocabulary is Burkham's and records that it is. FRAMEWORKS
         names its provenance, and a NoFramework decision for a venture whose
         frameworks were never surveyed says so in its reason."*

THE TWO THAT CARRY THE RULINGS
==============================

    `test_assign_contract_refuses_rather_than_returning_empty` - because `[]` is an
    answer, and it is the one answer nobody here is entitled to give.

    `test_an_unsurveyed_venture_cannot_declare_no_framework_without_saying_so` - because
    the caveat is what stops "no framework applies" being read as more than it is.

No database. These are statements about a module-level declaration that `_validate()`
checks at import, which is the point: a bad declaration is an ImportError.
"""

from __future__ import annotations

import pytest

from broker import compliance_couplings as couplings

CRE_MODULES = ("property_lookup", "comp_analysis", "buyer_match", "underwrite_deal")


# ------------------------------------------------------------------ entry 160

@pytest.mark.parametrize("module_id", CRE_MODULES)
def test_the_four_modules_imply_no_flag(module_id: str):
    """The four drafts, as written.

    Each returns `[]` - but an `[]` that `_validate()` has checked has a reason behind
    it, which is the whole difference from the eight wrong rows entry 153 measured.
    """
    assert couplings.flags_for("cre-forge", module_id) == []


@pytest.mark.parametrize("module_id", CRE_MODULES)
def test_each_declaration_carries_a_reason(module_id: str):
    decl = couplings.CRE_FORGE[module_id]
    assert isinstance(decl.couplings, couplings.NoFramework)
    assert decl.couplings.why.strip(), "an empty reason is the default entry 153 banned"


def test_assign_contract_refuses_rather_than_returning_empty():
    """**THE RULING.** *"For assign_contract, register nothing."*

    Not `[]`. An empty list is the answer *no framework applies*, and it is an answer
    nobody is entitled to give for a module that assigns a real estate contract for a
    fee in a state whose licensing statute nobody in this repository has read.

    A refusal at the call site is the only shape that cannot be mistaken for the answer
    later.
    """
    with pytest.raises(couplings.CouplingError) as raised:
        couplings.flags_for("cre-forge", "assign_contract")

    message = str(raised.value)
    assert "Nevada" in message
    assert "licence" in message
    assert "assign_contract" in message


def test_the_pending_question_leads_with_the_question():
    """It reads as something to ask counsel, not as a finding.

    The text carries context after the question, which is useful - but the question is
    first. A pending item whose opening sentence is a statement is one somebody has
    started answering, and the order is the cheapest way to keep that visible.
    """
    text = couplings.PENDING_COUNSEL[("cre-forge", "assign_contract")]
    assert "?" in text, "a pending counsel item is a question"
    assert text.index("?") < text.index("."), (
        "the question must come before any statement of fact; a pending item that "
        "opens with an assertion is an answer somebody wrote while it was open"
    )


def test_a_module_is_never_both_declared_and_pending():
    """Two places to look would mean two answers, and one of them silently winning."""
    for (forge_id, module_id) in couplings.PENDING_COUNSEL:
        declared = couplings.DECLARATIONS.get(forge_id, {})
        assert module_id not in declared, (
            f"{forge_id}/{module_id} is both declared and pending counsel"
        )


def test_its_manual_says_no_framework_and_this_ruling_overrides_that():
    """**Load-bearing, and the uncomfortable half of entry 160.**

    All five manuals in `scripts/author_cre_forge_instructions.py` carry
    `compliance_coupling: ["no_framework_applies"]`. The ruling took four of them as
    written and overrode the fifth. This asserts that the override is real, so a later
    sweep that "fixes the inconsistency" by registering the manual's reading has to
    argue with a failing test rather than with a comment.
    """
    from scripts.author_cre_forge_instructions import MANUALS

    assert MANUALS["assign_contract"]["compliance_coupling"] == ["no_framework_applies"]
    assert ("cre-forge", "assign_contract") in couplings.PENDING_COUNSEL


# ------------------------------------------------------------------ entry 161

def test_frameworks_names_its_provenance_where_the_map_is():
    """*"FRAMEWORKS names its provenance."* In the module, not only in the ledger.

    Read from the source above the map rather than from a docstring, because the reader
    this is for is somebody scrolling to `FRAMEWORKS` to look a flag up - and a
    provenance note they have to go elsewhere for is one they will not see.
    """
    import inspect

    source = inspect.getsource(couplings)
    header = source[: source.index("FRAMEWORKS: dict")]
    assert "Burkham" in header, "the map does not say whose vocabulary it is"
    assert "SURVEYED" in header, "the map does not point at what records the narrowing"


def test_only_burkham_has_been_surveyed():
    """One member, and cre-forge's venture is not it.

    The list is short because the survey is: Burkham Wickmont's frameworks were written
    down, and no other venture's have been.
    """
    assert frozenset({"burkham-wickmont"}) == couplings.SURVEYED
    assert couplings.FORGE_VENTURE["capitalforge"] in couplings.SURVEYED
    assert couplings.FORGE_VENTURE["cre-forge"] == "greenstone"
    assert "greenstone" not in couplings.SURVEYED


@pytest.mark.parametrize("module_id", CRE_MODULES)
def test_every_cre_reason_carries_the_unsurveyed_caveat(module_id: str):
    """*"...says so in its reason."*

    Greenstone is not in SURVEYED, so each of these reasons must narrow itself. Without
    the caveat the record claims more than was decided: what was decided is that none of
    Burkham's twenty flags applies, and the gap between that and "no framework applies"
    is the size of every Nevada real-estate statute nobody has read.
    """
    why = couplings.CRE_FORGE[module_id].couplings.why
    assert couplings.UNSURVEYED_CAVEAT in why


def test_an_unsurveyed_venture_cannot_declare_no_framework_without_saying_so():
    """**THE RULING, made unskippable.** `_validate()` is the control, so it is called.

    A test that only read the four existing reasons would pass for as long as nobody
    added a fifth. This builds a declaration that omits the caveat and requires the
    refusal.
    """
    bad = {
        "some_module": couplings.ModuleCouplings(
            couplings=couplings.NoFramework(why="No framework applies to this."),
        )
    }
    with pytest.raises(couplings.CouplingError) as raised:
        couplings._validate_forge("cre-forge", bad)

    assert couplings.UNSURVEYED_CAVEAT in str(raised.value)


def test_a_surveyed_venture_needs_no_caveat():
    """The other side, so the check is about the survey and not about the words.

    capitalforge is Burkham's, Burkham is surveyed, and "no framework applies" there
    means what it says.
    """
    fine = {
        "some_module": couplings.ModuleCouplings(
            couplings=couplings.NoFramework(why="No framework applies to this."),
        )
    }
    couplings._validate_forge("capitalforge", fine)  # does not raise


def test_the_map_holds_the_flag_greenstones_pack_declares():
    """`tsr_disclosure_required`, missing while the map claimed to hold every flag.

    `packs/greenstone.yaml` declares it at `market.compliance_surface` and propagates
    it. The map had no entry, and its own comment said it had them all.
    """
    assert couplings.FRAMEWORKS["tsr_disclosure_required"] == "FTC_TSR"


def test_capitalforge_is_unchanged():
    """**Load-bearing.** Entries 160 and 161 add a Forge and a caveat; they do not
    revisit a single declaration Burkham's Forge already carries."""
    assert couplings.flags_for("capitalforge", "record_consent") == [
        "recording_consent_required", "privacy_request_handling",
    ]
