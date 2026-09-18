"""Which build this process is running, and whether its checkout has moved past it.

WHY THIS IS ITS OWN MODULE
==========================

    It was a private function in `broker/app.py`, serving `/api/version` alone. The
    provisioning ladder needs the same answer and must not import the API to get it -
    a gate importing a FastAPI app to learn its own commit would make the ladder
    unrunnable from the CLI, which is how the sweeps and the smoke script run it.

WHAT A "STALE BUILD" IS, AND THE TWO SHAPES IT COMES IN
=======================================================

    Both of the incidents this module exists for were found by forensics, days later,
    because the only record was of what was SENT and never of what sent it.

        16 September    A server left running across a merge in its own checkout.
                        `/api/live` answered 200 while a route that had just landed
                        404ed - in the file, not in the process. Ten minutes lost to
                        a routing bug that was not one.
        17-18 September An API serving from a DIFFERENT checkout entirely (a worktree
                        detached at an older commit). It ran two provisioning runs to
                        Gate 8 on superseded answer keys and reported success both
                        times. Found only by asking `/api/version` by hand.

    The first is detectable from inside: the process holds a commit read at import and
    its own tree can be asked what HEAD is NOW, and the two can disagree. That is what
    `current` means here and it is the check `submitting_build_is_current` enforces.

    **The second is not detectable from inside, and pretending otherwise would be
    worse than recording it.** A process running a worktree's code faithfully reports
    that worktree's commit; nothing inside it knows another checkout exists. What
    closes that case is `root`: an evidence field naming the directory the code was
    imported from turns a day of forensics into one line a reader can see.

THE SAME ANCHOR, TWICE, ON PURPOSE
==================================

    `root` is `Path(__file__).parent.parent` - and so is
    `generators.scenario_content.default_root()`'s checkout candidate. Code and
    content travel together: a process cannot read one checkout's code and another's
    answer keys. That is why naming the root identifies both halves at once, and why
    `scenario_root` is recorded beside it rather than trusted to match.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

#: The checkout the code was imported from. Not the working directory: a process
#: started anywhere reads its content from beside its code, and the working directory
#: is what made the 17 September case look like it could not be the answer.
ROOT = Path(__file__).resolve().parent.parent

UNKNOWN = "unknown"


def _stamped() -> str:
    """`OFFICE_GIT_COMMIT`, which the image build sets. Empty in a working tree."""
    return os.environ.get("OFFICE_GIT_COMMIT", "").strip()


def _git_head(root: Path) -> str:
    """What `root`'s git says HEAD is now, or "" when it cannot be asked.

    Never raises. A build identity that can fail is an identity check that reports on
    itself - the same argument `/api/version` is built on.

    `.git` is tested with `exists()` rather than `is_dir()` because a worktree's `.git`
    is a FILE pointing at the main checkout's admin directory. Requiring a directory
    would report every worktree as unidentifiable, which is the exact configuration
    the 17 September incident ran on.
    """
    try:
        if not (root / ".git").exists():
            return ""
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _process_commit() -> str:
    """Which commit this process is running, or "unknown".

    **Read once, at import, because the answer cannot change while the process lives**
    - and a value that could change under a caller would be worse than none.

    `OFFICE_GIT_COMMIT` first, because an image has no `.git` and the build stamps it.
    A working tree falls back to asking git, which is what makes this useful in
    development.
    """
    return _stamped() or _git_head(ROOT) or UNKNOWN


#: Read at import. The number `/api/version` reports and the number a gate records.
PROCESS_COMMIT = _process_commit()

#: True when the commit came from the image stamp rather than from a git tree.
PROCESS_COMMIT_IS_STAMPED = bool(_stamped())


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    """What is running, where it came from, and whether its tree has moved past it."""

    commit: str
    """What this process is running. `unknown` when nothing could say."""

    checkout: str
    """What `root`'s git says HEAD is, read at the moment this was resolved. Empty in
    an image, which has no git tree to ask - see `comparable`."""

    root: str
    """The directory the code was imported from. **The field that would have closed
    the 17 September case on sight**, because nothing else distinguishes a checkout
    from a worktree of it."""

    stamped: bool
    """The commit came from `OFFICE_GIT_COMMIT`. An image, not a working tree."""

    @property
    def identified(self) -> bool:
        """Something could say which commit this is."""
        return self.commit != UNKNOWN and bool(self.commit)

    @property
    def comparable(self) -> bool:
        """There is a checkout to compare against.

        False for a stamped image build: an image has no tree, so there is nothing it
        could have drifted from and "not comparable" is the honest state rather than a
        failure. A working tree that cannot be asked - git missing, `.git` gone - is
        also not comparable, and `identified` is what refuses that case.
        """
        return not self.stamped and bool(self.checkout)

    @property
    def current(self) -> bool:
        """The process is running what its own checkout holds.

        **Not comparable reads as current**, deliberately. This property answers "has
        this tree moved past the process", and a build with no tree has not.
        """
        return not self.comparable or self.commit == self.checkout

    def as_evidence(self, *, scenario_root: str | None = None) -> dict[str, object]:
        """The block a gate records. Flat, so a reader greps one field name."""
        row: dict[str, object] = {
            "commit": self.commit,
            "checkout_head": self.checkout or None,
            "checkout_root": self.root,
            "stamped": self.stamped,
            "current": self.current,
        }
        if scenario_root is not None:
            # Recorded rather than derived, though it shares `ROOT`'s anchor. The two
            # agreeing is the claim; printing one and asserting the other is how a
            # reader ends up trusting a derivation instead of reading a measurement.
            row["scenario_root"] = scenario_root
        return row


def identity() -> BuildIdentity:
    """Resolve the current build identity. Cheap; asks git once."""
    return BuildIdentity(
        commit=PROCESS_COMMIT,
        checkout=_git_head(ROOT),
        root=str(ROOT),
        stamped=PROCESS_COMMIT_IS_STAMPED,
    )


def refusal(build: BuildIdentity) -> str | None:
    """Why this build may not submit anything, or None.

    ONE SENTENCE, AND IT NAMES BOTH COMMITS
    =======================================

        The reason is the whole deliverable. A block that says "stale build" sends a
        reader to `git log`; a block that says which two commits disagree and which
        directory they were read from ends the investigation where it starts.

    UNIDENTIFIED IS REFUSED, and that is `dev-all.sh`'s rule rather than a new one.
    Entry 123 changed that script from reporting `ok "live (build unverified)"` to
    calling it bad, because *"a build nobody could identify is not a build that was
    checked"*. A gate that submitted on `unknown` while the shell script refused to
    call the same process healthy would be two controls disagreeing about one fact.
    The image build stamps `OFFICE_GIT_COMMIT`, so reaching `unknown` means nobody
    stamped it, which is a defect rather than a configuration.
    """
    if not build.identified:
        return (
            "this build cannot be identified: neither OFFICE_GIT_COMMIT nor a git "
            f"tree at {build.root} could say which commit is running. A build nobody "
            "can identify is not a build that was checked (decisions entry 123), and "
            "what it submits cannot be traced to the content that produced it."
        )
    if not build.current:
        return (
            f"this process is running {build.commit[:12]} and its checkout at "
            f"{build.root} is at {build.checkout[:12]}. The tree has moved past the "
            "process, so what would be submitted is not what the checkout holds - "
            "and a curriculum is generated from files beside this code, not from the "
            "database. Restart the process before submitting."
        )
    return None
