"""The ordering B33 states, asserted rather than restated.

    the registry rows land before or with the patch, never after, or V31 goes mute.

That sentence has been in `docs/blocking.md` since 2026-09-09 with nothing behind it. It
is true, and each half of it is measured below out of the validator's own
`unattended_writes` rather than quoted - so if V31's handling of an unresolved module
ever changes, the sentence stops being true here first and loudly, rather than in a Pack
six weeks later. The last test enforces it: the position cannot be committed into the
Pack without a receipt saying the rows went first.

WHY THIS FILE AND NOT `tests/adapters/test_funnelforge_rows.py`
==============================================================

That file already reads the held patch, and says why: *"a patch nothing checks is a patch
that stops applying, and the record's promise that it can be re-applied would then be a
claim with nothing behind it."* It then reads the module names out of it with
`splitlines()`.

**The patch had stopped applying and that check could not see it.** `splitlines()` is
indifferent to carriage returns, so the names came out fine while
`git apply docs/plans/funnelforge-position-DEFERRED.patch` returned *"patch does not
apply"* on every Windows checkout - the file is stored LF and `* text=auto` gave it CRLF,
and `git apply` compares context byte for byte. The guard checked the payload; the
property it was protecting was appliability. `test_the_deferred_patch_still_applies`
below is the missing half, and it is here rather than there so the two are not confused
for one check.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from adapters.funnelforge.modules import manifest
from generators.pack import BusinessPack, load_pack
from generators.validator import ModuleShape, unattended_writes
from scripts.land_funnelforge_position import (
    ANCHORS,
    BINDING_MARKER,
    POSITION_MARKER,
    split_hunks,
)

ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / "packs" / "burkham-wickmont.draft.yaml"
PLAN_PATH = ROOT / "docs" / "plans" / "funnelforge-position-PLAN.md"
RECEIPT_PATH = ROOT / "docs" / "plans" / "funnelforge-landing-receipt.json"
FORGE = "funnelforge"
POSITION = "Marketing Operations Coordinator"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


# ------------------------------------------------------------------------- helpers


def _apply_in(tmp_path: Path, only: str | None = None) -> Path:
    """Insert the plan's two blocks into a throwaway copy of the Pack; return the copy.

    **Was `git apply` against a held `.patch` until 14 September 2026.** The patch was
    retired because a diff matches three lines of context and goes stale silently: this
    helper's own history records the patch having stopped applying while the check meant
    to notice could not see it. The plan's blocks carry an ANCHOR instead - one whole
    line, required to appear exactly once - so a Pack whose shape moved stops the
    insertion with a message rather than landing it in the wrong place.

    The insertion is the script's, imported rather than reimplemented. A helper that
    re-derived it would assert against its own copy of the behaviour, which is trap #4
    in `docs/forge-adapter.md` one layer up.
    """
    (tmp_path / "packs").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "packs" / PACK_PATH.name
    target.write_text(PACK_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    binding, position = split_hunks(PLAN_PATH.read_text(encoding="utf-8"))
    text = target.read_text(encoding="utf-8")
    pairs = [(binding, BINDING_MARKER), (position, POSITION_MARKER)]
    if only is not None:
        # One block alone, for the ordering tests: landing the binding without the
        # position is step 1 of the sequence and has to be reachable on its own.
        pairs = [(b, m) for b, m in pairs if only in b]
        assert len(pairs) == 1, f"{only!r} selected {len(pairs)} blocks"
    for block, marker in pairs:
        anchor = ANCHORS[marker]
        assert [ln for ln in text.splitlines() if ln == anchor] == [anchor], (
            f"anchor {anchor!r} is not unique in the Pack, so the plan's {marker!r} "
            "block cannot be placed deterministically. This is the failure the anchors "
            "exist to make loud - a diff would have guessed."
        )
        text = text.replace(anchor, block.rstrip() + "\n\n" + anchor, 1)
    target.write_text(text, encoding="utf-8")
    return target


def _plan_is_held() -> bool:
    """True while the plan's edits are still on the shelf rather than in the Pack."""
    return POSITION not in {
        p.position_title for p in load_pack(PACK_PATH).positions_required
    }


held_only = pytest.mark.skipif(
    not _plan_is_held(),
    reason="the planned edit has landed; there is no held plan left to re-apply",
)


def _pack_with_the_position(tmp_path: Path) -> BusinessPack:
    """The Pack as it stands once the held edit is in it - from wherever it lives now.

    Resolved rather than located, for the reason `tests/adapters/test_funnelforge_rows.py`
    gives for `declaration()`: a test that reads only the patch goes quiet the day the
    patch lands, and the assertions below are worth *more* after landing than before.
    `test_the_patch_with_the_rows_makes_v31_refuse_seven` in particular is the pin on the
    seven refusals; it must keep holding once the position is real.
    """
    on_disk = load_pack(PACK_PATH)
    if POSITION in {p.position_title for p in on_disk.positions_required}:
        return on_disk
    return load_pack(_apply_in(tmp_path))


def _adapter_shapes() -> dict[tuple[str, str], ModuleShape]:
    """What `register_funnelforge_modules.py --confirm` puts in the registry.

    Built from the adapter's own manifest rather than from literals, so this cannot
    drift into asserting a shape FunnelForge does not serve - which is the failure
    `tests/world.py` records for the CRE fixture.
    """
    return {
        (FORGE, entry["module_id"]): ModuleShape(
            is_mutating=entry["is_mutating"],
            idempotency_support=entry["idempotency_support"],
            verification_method="adapter_manifest",
        )
        for entry in manifest()["modules"]
    }


# ------------------------------------------------------------- the patch still works


def test_every_plan_anchor_is_unique_in_the_pack() -> None:
    """The plan's two blocks can each be placed in exactly one spot.

    **REPLACES `test_the_deferred_patch_still_applies`, 14 September 2026.** That test
    guarded the property a `.patch` needs - appliability - by running `git apply --check`.
    The plan is not a diff and `git apply` cannot read it, but the property it protected
    still matters and has an exact equivalent: a block is placed above a named anchor
    line, so the plan is landable precisely while every anchor appears once.

    This is a stronger guarantee than the one it replaces. A diff matches three lines of
    context and can land at a wrong offset when the Pack shifts near them; an anchor that
    has moved or duplicated stops the insertion with a message naming it.
    """
    pack_lines = PACK_PATH.read_text(encoding="utf-8").splitlines()
    for marker, anchor in ANCHORS.items():
        hits = [ln for ln in pack_lines if ln == anchor]
        assert len(hits) == 1, (
            f"anchor {anchor!r} for the {marker!r} block appears {len(hits)} times in "
            f"{PACK_PATH.name}; it must appear exactly once. The Pack's shape moved - "
            "update the anchor in the plan deliberately rather than letting the lander "
            "guess which occurrence was meant."
        )

def test_the_plan_blocks_parse_as_yaml() -> None:
    """Each block is well-formed YAML of the shape its destination expects.

    **REPLACES `test_the_patch_is_stored_with_unix_line_endings`, 14 September 2026.**
    That test existed because `git apply` compares context byte for byte and a CRLF
    checkout made it refuse the whole patch - a real failure that cost two days. Nothing
    in the plan path is byte-compared, so the pin it guarded is no longer load-bearing.

    What replaces it is the check the plan path actually needs: the blocks are spliced
    into a Pack as text, so a block that is not valid YAML produces a Pack that will not
    load, and the failure would surface at `load_pack` rather than here.
    """
    binding, position = split_hunks(PLAN_PATH.read_text(encoding="utf-8"))

    parsed_binding = yaml.safe_load(binding)
    assert isinstance(parsed_binding, list) and len(parsed_binding) == 1, parsed_binding
    assert parsed_binding[0]["forge"] == FORGE
    assert len(parsed_binding[0]["modules_expected"]) == 9

    parsed_position = yaml.safe_load(position)
    assert isinstance(parsed_position, list) and len(parsed_position) == 1, parsed_position
    assert parsed_position[0]["position_title"] == POSITION
    assert parsed_position[0]["trust_tier_ceiling"] == "auto_execute"
    assert len(parsed_position[0]["forge_modules_operated"]) == 9

@held_only
def test_the_split_loses_nothing(tmp_path: Path) -> None:
    """Landing in two halves must land the same Pack as landing in one.

    The script's whole method is that the edit has always been two independent blocks.
    If the reader dropped or duplicated a line, the ordering would be enforced over a
    Pack nobody authored.

    **No longer runs `git apply`, 14 September 2026.** The halves are inserted by the
    same anchor-based code the lander uses, which is what makes this an assertion about
    the landing path rather than about a diff that no longer exists.
    """
    binding_block, position_block = split_hunks(PLAN_PATH.read_text(encoding="utf-8"))
    assert binding_block and position_block

    halves = tmp_path / "halves"
    _apply_in(halves, only=BINDING_MARKER)
    # Step 3 of the sequence, against the Pack step 1 already edited.
    target = halves / "packs" / PACK_PATH.name
    text = target.read_text(encoding="utf-8")
    anchor = ANCHORS[POSITION_MARKER]
    assert [ln for ln in text.splitlines() if ln == anchor] == [anchor]
    target.write_text(
        text.replace(anchor, position_block.rstrip() + "\n\n" + anchor, 1),
        encoding="utf-8",
    )

    whole = _apply_in(tmp_path / "whole")
    assert target.read_text(encoding="utf-8") == whole.read_text(encoding="utf-8"), (
        "landing the two blocks separately produced a different Pack from landing them "
        "together. The ordering the lander enforces would then be enforced over a Pack "
        "nobody authored."
    )


@needs_git
@held_only
def test_the_binding_half_alone_leaves_v31_with_nothing_to_read(tmp_path: Path) -> None:
    """Step 1 of the landing cannot mute V31, which is why it is step 1.

    V31 examines only the modules a position operates at `auto_execute`, and the binding
    hunk declares no position - so with it applied and no rows anywhere the rule has nothing
    to say about FunnelForge at all: not a silence about a declaration, an absence of one.

    NOT because V31 ignores `forge_dependencies`. It reads it - validator.py:1150-1152 scopes
    the `forge_module_registry` query to the Forges named there - and that is the second half
    of why this is step 1: without the binding, step 2's rows are outside the query and V31
    would report NOT_RUN with all nine of them written.
    """
    binding_block, _ = split_hunks(PLAN_PATH.read_text(encoding="utf-8"))
    pack = load_pack(_apply_in(tmp_path, only=BINDING_MARKER))

    assert POSITION not in {p.position_title for p in pack.positions_required}
    refusals, unresolved = unattended_writes(pack, {})
    assert not [r for r in refusals + unresolved if FORGE in r or POSITION in r]


# ------------------------------------------------- the two halves of B33's sentence


@needs_git
def test_the_patch_without_the_rows_makes_v31_mute(tmp_path: Path) -> None:
    """*"or V31 goes mute"* - here is the mechanism, out of the rule itself.

    `unattended_writes` resolves each module the position operates against
    `forge_module_registry`. No row means no `ModuleShape`, which means the module lands
    in `unresolved` and never reaches the `unsafe_unattended` test. With **every** module
    unresolved there are no refusals, and `_v31_unattended_writes` returns NOT_RUN.

    NOT_RUN is not a pass and blocks Gate 2 - but it blocks it saying *nothing verified
    is known about the shape of these modules*, which is a missing measurement, whose
    remedy is to run a script. The truth is a refused declaration, whose remedy is an
    idempotency key or a lower tier. Same verdict count, opposite meaning, different
    owner.
    """
    pack = _pack_with_the_position(tmp_path)
    refusals, unresolved = unattended_writes(pack, {})

    assert refusals == []
    assert len(unresolved) == 9
    assert all(POSITION in u for u in unresolved)


@needs_git
def test_the_plan_with_the_rows_makes_v31_refuse_only_the_booking(tmp_path: Path) -> None:
    """*"the registry rows land before or with the position"* - here is what that buys.

    **INVERTED 14 September 2026, and the inversion is the point of the test.** It was
    `..._makes_v31_refuse_seven`, pinning seven refusals so that "a change at either end -
    the adapter restating a shape, or the Pack quietly dropping the tier - shows up as a
    diff here with a person having to say why."

    **It worked exactly as designed.** Changing the adapter's seven `at_most_once`
    declarations to `key` turned this red, and this docstring is the person saying why.

    The reason is not in this repository. FunnelForge PR #160 merged 2026-09-12 04:55 UTC
    and gave the send path an idempotency store: an atomic Redis claim, answered from its
    record on a repeat, failing closed on a 503 rather than sending. `at_most_once` was
    true when it was written and stopped being true two days before anybody here read it.

    **`key` and not `natural`, because the header is optional there** - an unkeyed repeat
    still sends twice. That makes the declaration a claim about the CALL PATH, which is
    why `adapters/funnelforge/app.py` now forwards `Idempotency-Key` and
    `tests/adapters/test_funnelforge_idempotency_hop.py` asserts it survives the hop. The
    declaration and the forwarding are one fact.

    So V31 refuses nothing, and the pin moves rather than disappearing: this now fails if
    anything drifts back to `at_most_once`, or if a tenth module arrives unexamined.
    """
    pack = _pack_with_the_position(tmp_path)
    refusals, unresolved = unattended_writes(pack, _adapter_shapes())

    assert unresolved == [], (
        "a module the position operates has no registry row, so V31 cannot speak about "
        "it. That is the silence the landing order exists to prevent."
    )
    # CORRECTED 14 September 2026, from `..._refuse_nothing`. The first inversion said
    # V31 refuses nothing, on the strength of seven declarations changed in one
    # replace-all. Six of those seven were right: they post to EMAILS_SEND, which PR #160
    # gave a store. `schedule_blueprint_call` posts to SCHEDULING_BOOK, which never reads
    # the header, so it is `at_most_once` and V31 refuses `auto_execute` over it.
    #
    # The plan declares it `propose` in `module_trust_tiers` for exactly this reason, so
    # the LANDED Pack is not refused - but `unattended_writes` reads the ceiling, so the
    # refusal is visible here and that is the point of the assertion.
    assert [r for r in refusals if "schedule_blueprint_call" in r], (
        f"V31 refuses {refusals}, and schedule_blueprint_call is not among them. It is "
        "mutating and `at_most_once` - a repeat books a second appointment - so a rule "
        "that does not refuse it under an unattended ceiling has stopped reading the "
        "shape it exists to read."
    )
    others = [r for r in refusals if "schedule_blueprint_call" not in r]
    assert others == [], (
        f"V31 also refuses {others}. Every other module posts to EMAILS_SEND, "
        "`capture_contact` has a natural key, `read_funnel_analytics` mutates nothing. A "
        "refusal here means an email-path declaration drifted back to `at_most_once`."
    )

    shapes = _adapter_shapes()
    unsafe = sorted(
        m for (_f, m), sh in shapes.items() if sh.idempotency_support == "at_most_once"
    )
    assert unsafe == ["schedule_blueprint_call"], (
        f"{unsafe} declare `at_most_once`. Exactly one should. If FunnelForge's email "
        "path genuinely lost its idempotency store this test is right and the plan's "
        "`module_trust_tiers` are now wrong - fix the plan, not this assertion."
    )


# ---------------------------------------------- the half of the order git can enforce


def test_the_position_is_not_in_the_pack_without_a_landing_receipt() -> None:
    """The ordering, enforced against whatever is committed.

    `scripts/land_funnelforge_position.py` writes the receipt as the last step of a
    landing that put the rows in first. Applying the patch by hand skips that, so the
    Pack carries the position and no receipt accounts for it, and this fails naming the
    rule. **That is the difference between the ordering being documented and the
    ordering being enforced**: the wrong order can still be typed, and it can no longer
    be committed.

    It is scoped to this Pack and this Forge on purpose.
    `packs/burkham-wickmont.split.draft.yaml` carries `auto_execute` positions of its
    own that predate all of this, and a rule written wide enough to catch those would be
    a rule about a decision nobody in this package made.
    """
    pack = load_pack(PACK_PATH)
    funnelforge_modules = {
        m
        for b in pack.forge_dependencies.forge_bindings
        if b.forge == FORGE
        for m in b.modules_expected
    }
    unattended = {
        m
        for p in pack.positions_required
        if p.trust_tier_ceiling == "auto_execute"
        for m in p.forge_modules_operated
        if m in funnelforge_modules
    }
    if not unattended:
        assert not RECEIPT_PATH.exists(), (
            f"{RECEIPT_PATH.name} records a landing that is not in the Pack. Either the "
            "Pack edit was reverted and the receipt was left behind, or the receipt was "
            "written by something other than the landing script."
        )
        return

    assert RECEIPT_PATH.exists(), (
        f"{PACK_PATH.name} operates {len(unattended)} {FORGE} module(s) at auto_execute "
        f"and there is no {RECEIPT_PATH.name}.\n\n"
        "B33: the registry rows land before or with the patch, never after, or V31 goes "
        "mute. A receipt is what says the rows went first. Revert the Pack edit and run "
        "scripts/land_funnelforge_position.py --confirm, which does both in one command."
    )
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    recorded = receipt.get("modules", {})
    missing = sorted(unattended - set(recorded))
    assert not missing, (
        f"the landing receipt does not account for {', '.join(missing)}, which the Pack "
        "operates at auto_execute. The position outran the rows for those modules."
    )
    hand = sorted(m for m in unattended if recorded.get(m) == "hand")
    assert not hand, (
        f"{', '.join(hand)} were registered by hand. V31 will not pass on a hand-written "
        "row and the landing this receipt describes did not produce evidence."
    )
