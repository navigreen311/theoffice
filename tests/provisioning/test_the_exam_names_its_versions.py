"""An exam's identity carries the protocol and rubric versions it is set under.

RULED 21 SEPTEMBER 2026 (entry 143)
===================================

    *"An exam's identity carries the protocol version and the rubric version it is set
    under, beside the instruction and scenario hashes."*

WHAT THE RULING MEASURED
========================

    `assign_contract`'s standing verdict was graded under protocol 4.0.0 and rubric
    0.2.0, two protocol majors behind SimForge's checkout, and could not be re-examined
    because its ref never changed. Its answer key did not move between 18 and 20
    September, both runs minted the identical ref, `open_run` is idempotent on it, and
    the 20 September exam landed on the run already open - clock and rubric untouched.
    Gate 8 recorded `already_open: True` for that module and False for every other.

WHERE THE OFFICE LEARNS THEM, AND WHAT HAPPENS IF IT CANNOT
===========================================================

    From SimForge's `/api/version` - the route `SimForgeClient.build` already reads,
    unauthenticated, once per Gate 8. **Neither field is published there today**, so
    both read `None`, `mint_run_ref` omits the segment rather than defaulting it, and
    the gate says so in its own sentence. It warns and does not block, which is entry
    131's rule: this gate blocks on facts about us and reports facts about the
    counterpart.

THE LOAD-BEARING TESTS IN THIS FILE
===================================

    `test_an_absent_version_is_omitted_not_defaulted` and
    `test_the_warning_names_what_is_missing`. Every other test asserts a segment
    appears; a `mint_run_ref` that stamped a constant when it knew nothing would
    satisfy them all while minting refs that agree about exams that do not.
"""

from __future__ import annotations

import uuid

from broker import provisioning
from broker.simforge import mint_run_ref

VENTURE = "greenstone"
FORGE = "cre-forge"
HASH = "cacf28ef5ba0" + "0" * 52
KEY = "5c5e41247e52" + "0" * 52
AGENT = uuid.UUID("c8afb0e6-0000-4000-8000-000000000000")

#: SimForge's two constants as its checkout carries them, read 21 September 2026 from
#: `services/operation/battery.py` and `services/operation/rubric.py`. Used as VALUES a
#: probe might return, never asserted to be what SimForge runs - that is its fact.
PROTOCOL = "6.0.0"
RUBRIC = "0.4.0"


def _ref(**over) -> str:
    kwargs = {
        "venture_id": VENTURE, "forge_id": FORGE, "module_id": "assign_contract",
        "content_hash": HASH, "office_agent_id": AGENT, "scenario_hash": KEY,
    }
    kwargs.update(over)
    return mint_run_ref(**kwargs)


def _build(**over) -> dict:
    build = {
        "reachable": True, "differs": False,
        "started_commit": "a" * 40, "checkout_commit": "a" * 40,
        "app_version": "a" * 40,
        "response_protocol_version": PROTOCOL,
        "operation_rubric_version": RUBRIC,
    }
    build.update(over)
    return build


# ------------------------------------------------------------------ the identity

def test_both_versions_are_in_the_ref():
    ref = _ref(protocol_version=PROTOCOL, rubric_version=RUBRIC)
    assert ref.endswith(f":p{PROTOCOL}:r{RUBRIC}")


def test_a_rubric_bump_mints_a_different_ref():
    """The defect, in one assertion.

    `assign_contract`'s key did not change, so its ref did not change, so `open_run`
    returned the run opened under the older rubric. With the rubric in the identity the
    two exams are two runs.
    """
    was = _ref(protocol_version=PROTOCOL, rubric_version="0.2.0")
    now = _ref(protocol_version=PROTOCOL, rubric_version="0.3.0")
    assert was != now


def test_a_protocol_bump_mints_a_different_ref():
    """A reworded protocol is a different exam - SimForge's own ADR-0064 says so."""
    assert _ref(protocol_version="4.0.0") != _ref(protocol_version="6.0.0")


def test_a_department_ref_carries_them_too():
    """Unlike the scenario hash, which unit B must not pretend to have.

    A department run submits no curriculum and so names no answer key. It IS graded -
    `rubric_kind` is `domain` - so the collision this closes happens there as well.
    """
    ref = mint_run_ref(
        venture_id=VENTURE, forge_id=FORGE, module_id=None, department="research",
        content_hash=HASH, protocol_version=PROTOCOL, rubric_version=RUBRIC,
    )
    assert ref.endswith(f":p{PROTOCOL}:r{RUBRIC}")
    assert ":k" not in ref


def test_the_segments_are_prefixed_and_ordered():
    """`p` then `r`, after `k`, so a reader tells them apart without counting colons
    and a ref minted twice is byte-identical."""
    ref = _ref(protocol_version=PROTOCOL, rubric_version=RUBRIC)
    assert ref.split(":")[-3:] == [f"k{KEY[:12]}", f"p{PROTOCOL}", f"r{RUBRIC}"]


# ---------------------------------------------------- what happens if it cannot

def test_an_absent_version_is_omitted_not_defaulted():
    """**Load-bearing.** Entry 122's rule.

    A constant here would claim an exam was set under a version nobody read, and every
    ref would agree while the runs behind them did not - which is the defect, restated
    with a placeholder in it.
    """
    bare = _ref()
    assert ":p" not in bare
    assert ":r" not in bare
    assert bare.endswith(f":k{KEY[:12]}")


def test_one_version_alone_still_lands():
    """SimForge may publish one before the other. Neither is held back for the other."""
    assert _ref(rubric_version=RUBRIC).endswith(f":r{RUBRIC}")
    assert ":p" not in _ref(rubric_version=RUBRIC)


def test_a_ref_minted_before_the_ruling_still_resolves():
    """Every run already open keeps its shape - the rule every segment was added under.

    A ref that gained a segment retroactively would stop resolving to the run SimForge
    holds, and The Office would poll for a verdict against an identity that never
    existed.
    """
    assert _ref() == (
        f"office:{VENTURE}:{FORGE}:assign_contract@{str(AGENT)[:8]}:"
        f"{HASH[:12]}:k{KEY[:12]}"
    )


# -------------------------------------------------------------- what the gate says

def test_the_warning_names_what_is_missing():
    """**Load-bearing.** The whole of "what happens if it cannot" that a person sees.

    Warned, not blocked: this gate blocks on facts about us and reports facts about the
    counterpart (entry 131). A silent omission would leave the operator reading a clean
    gate result over an exam whose identity cannot say what graded it.
    """
    warning = provisioning._forge_build_warning(
        _build(response_protocol_version=None, operation_rubric_version=None)
    )
    assert warning is not None
    assert "protocol" in warning and "rubric" in warning
    assert "entry 143" in warning


def test_each_missing_version_is_named_on_its_own():
    """One name when one is missing, both when both are.

    Asserted on the named list rather than on the whole sentence: the consequence
    clause after it says "a rubric change will land on the run already open" whichever
    version is absent, because that is the consequence either way.
    """
    protocol_only = provisioning._forge_build_warning(
        _build(response_protocol_version=None)
    )
    assert protocol_only is not None
    assert "does not publish its protocol version, so" in protocol_only

    rubric_only = provisioning._forge_build_warning(
        _build(operation_rubric_version=None)
    )
    assert rubric_only is not None
    assert "does not publish its rubric version, so" in rubric_only

    both = provisioning._forge_build_warning(
        _build(response_protocol_version=None, operation_rubric_version=None)
    )
    assert both is not None
    assert "does not publish its protocol or its rubric version, so" in both


def test_a_forge_that_publishes_both_warns_about_nothing():
    """**The test that keeps the warning a finding rather than a fixture.** A version
    of this that always warned would satisfy every assertion above."""
    assert provisioning._forge_build_warning(_build()) is None


def test_a_stale_forge_that_also_publishes_neither_says_both():
    """Joined rather than first-match.

    Reporting only the stale build would send somebody to restart a service and
    conclude the gate was then clean, when the second fault survives the restart.
    """
    warning = provisioning._forge_build_warning(_build(
        differs=True, started_commit="b" * 40, checkout_commit="c" * 40,
        response_protocol_version=None, operation_rubric_version=None,
    ))
    assert warning is not None
    assert "moved past" in warning
    assert "entry 143" in warning


def test_a_forge_that_did_not_answer_says_only_that():
    """The one early return. Listing every field a silent Forge did not send would read
    as several faults where there is one."""
    warning = provisioning._forge_build_warning(
        {"reachable": False, "reason": "ConnectError: refused"}
    )
    assert warning == "the Forge did not say which build it is running"
