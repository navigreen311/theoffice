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
import subprocess
from pathlib import Path

import pytest

from adapters.funnelforge.modules import manifest
from generators.pack import BusinessPack, load_pack
from generators.validator import ModuleShape, unattended_writes
from scripts.land_funnelforge_position import split_hunks

ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / "packs" / "burkham-wickmont.draft.yaml"
PATCH_PATH = ROOT / "docs" / "plans" / "funnelforge-position-DEFERRED.patch"
RECEIPT_PATH = ROOT / "docs" / "plans" / "funnelforge-landing-receipt.json"
FORGE = "funnelforge"
POSITION = "Marketing Operations Coordinator"

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


# ------------------------------------------------------------------------- helpers


def _apply_in(tmp_path: Path, patch_bytes: bytes) -> Path:
    """Apply a patch to a throwaway copy of the Pack and return the copy.

    Outside a repository on purpose. `git apply` resolves paths against the working
    directory, so this exercises the patch against the Pack's real current text without
    ever touching the checkout the test is running from.

    **Bytes end to end, and that is the whole point of the helper.** The first version of
    this took `str`, read the patch with `read_text` and encoded it here - and it passed
    against a deliberately CRLF-ed patch file, because `read_text` uses universal newlines
    and had already normalised the defect away before `git apply` could see it. A rot
    detector that launders its own input is the same mistake one layer up from the one it
    was written to catch. `text=False` matters for the same reason on the write side:
    Python's text mode rewrites line endings to CRLF into a pipe on Windows.
    """
    (tmp_path / "packs").mkdir(parents=True, exist_ok=True)
    target = tmp_path / "packs" / PACK_PATH.name
    target.write_bytes(PACK_PATH.read_bytes())
    proc = subprocess.run(
        ["git", "apply", "-"],
        cwd=tmp_path,
        input=patch_bytes,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return target


def _patch_is_held() -> bool:
    """True while the Pack edit is still on the shelf rather than in the Pack."""
    return POSITION not in {
        p.position_title for p in load_pack(PACK_PATH).positions_required
    }


held_only = pytest.mark.skipif(
    not _patch_is_held(),
    reason="the deferred edit has landed; there is no held patch left to re-apply",
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
    return load_pack(_apply_in(tmp_path, PATCH_PATH.read_bytes()))


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


@needs_git
@held_only
def test_the_deferred_patch_still_applies(tmp_path: Path) -> None:
    """The record promises `git apply` returns the position "exactly as authored".

    A promise about a command is checked by running the command, on the bytes on disk.
    This failed for the whole of 2026-09-09 to 2026-09-10 on any Windows checkout and
    nobody could see it, because the only test that read the patch read it as text.
    """
    check = subprocess.run(
        ["git", "apply", "--check", PATCH_PATH.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, (
        "the documented command `git apply "
        f"{PATCH_PATH.relative_to(ROOT).as_posix()}` does not apply to "
        f"{PACK_PATH.name} as it stands.\n{check.stderr}"
    )

    target = _apply_in(tmp_path, PATCH_PATH.read_bytes())
    pack = load_pack(target)
    assert POSITION in {p.position_title for p in pack.positions_required}
    assert FORGE in {b.forge for b in pack.forge_dependencies.forge_bindings}


@needs_git
def test_the_patch_is_stored_with_unix_line_endings() -> None:
    """`.gitattributes` pins `*.patch text eol=lf`; this is what that pin is for.

    Checked against git's own index rather than the working file, because the working
    file is allowed to be CRLF on a Windows checkout for every other file type and the
    thing that must not happen is a CRLF `.patch` reaching `git apply`. With the pin in
    place the two are the same; without it, only this assertion notices.
    """
    proc = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", PATCH_PATH.relative_to(ROOT).as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "eol: lf" in proc.stdout, (
        "docs/plans/*.patch is not pinned to LF. A patch checked out with CRLF is "
        f"refused whole by git apply.\n{proc.stdout}"
    )


@needs_git
@held_only
def test_the_split_loses_nothing(tmp_path: Path) -> None:
    """Landing in two halves must land the same Pack as landing in one.

    The script's whole method is that the patch has always been two independent hunks.
    If the splitter dropped or duplicated a line, the ordering would be enforced over a
    Pack nobody authored.
    """
    binding_patch, position_patch = split_hunks(PATCH_PATH.read_text(encoding="utf-8"))

    halves = tmp_path / "halves"
    _apply_in(halves, binding_patch.encode("utf-8"))
    proc = subprocess.run(
        ["git", "apply", "-"],
        cwd=halves,
        input=position_patch.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")

    whole = _apply_in(tmp_path / "whole", PATCH_PATH.read_bytes())
    assert (halves / "packs" / PACK_PATH.name).read_text(
        encoding="utf-8"
    ) == whole.read_text(encoding="utf-8")


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
    binding_patch, _ = split_hunks(PATCH_PATH.read_text(encoding="utf-8"))
    pack = load_pack(_apply_in(tmp_path, binding_patch.encode("utf-8")))

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
def test_the_patch_with_the_rows_makes_v31_refuse_seven(tmp_path: Path) -> None:
    """*"the registry rows land before or with the patch"* - here is what that buys.

    Seven of the nine are mutating and `at_most_once`: an email leaves the system and
    reaches a person, and `EmailQueue` has no idempotency key that would recognise a
    repeat. V31 refuses `auto_execute` over exactly that shape.

    **This test passing is not a defect being fixed. It is the defect becoming
    speakable.** The count is pinned so that a change at either end - the adapter
    restating a shape, or the Pack quietly dropping the tier - shows up as a diff here
    with a person having to say why.
    """
    pack = _pack_with_the_position(tmp_path)
    refusals, unresolved = unattended_writes(pack, _adapter_shapes())

    assert unresolved == []
    assert len(refusals) == 7
    permitted = {"capture_contact", "read_funnel_analytics"}
    assert not [r for r in refusals if any(name in r for name in permitted)], (
        "capture_contact is mutating with a natural key and read_funnel_analytics "
        "mutates nothing; V31 permits both and refusing them would be the rule "
        "over-reaching, not tightening."
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
