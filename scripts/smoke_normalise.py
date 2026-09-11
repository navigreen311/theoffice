"""Normalise a `console-smoke` job log to the text the merge gate compares.

WHY THIS IS A SCRIPT AND NOT A PARAGRAPH
========================================

    `PARALLEL_BUILD.md` recorded the baseline hash with a prose recipe beside it -
    "strip the timestamp column, drop Chromium stderr, mask run-specific ids". P-06
    followed that prose carefully and got a different hash, then had to fall back on a
    ten-line diff to reach a verdict. Its conclusion was right and the gate was not
    verifiable: the number could only be reproduced by the shell history that produced
    it.

    That is the run's own recurring defect - **a finding recorded without the instrument
    that produced it** - committed by the coordinator, in the artifact every package is
    required to check against. PR #140 did it with the battery probes; P-00 did it here.
    Caveat 19's rule applies to the guard as much as to the measurement: name the thing
    you are comparing, from the system, before you compare it.

WHAT IS REMOVED, AND WHY EACH
=============================

    the step             everything before `Run ./scripts/console-smoke.sh` and after the
                         exit line is setup and teardown, and changes with the runner
    the timestamp column GitHub prefixes every line with an ISO-8601 stamp
    Chromium stderr      D-Bus and GCM noise, emitted in a nondeterministic ORDER - the
                         reason a line-count comparison is not enough
    DevTools listening   carries a per-run websocket UUID
    8-hex ids            run, proposal, grant and incident ids, minted per run
    the issued token     an 8-char prefix of a freshly issued console token

    Nothing else is touched. The FAIL lines, the check names and the totals are compared
    byte for byte, which is the point: five PRs on 10 September had identical red counts
    and one had a ninth failure it had introduced itself.

USAGE
=====

    python scripts/smoke_normalise.py <raw-log>            # emit normalised text
    python scripts/smoke_normalise.py <raw-log> --hash     # emit sha256 only
    python scripts/smoke_normalise.py <raw-log> --check    # exit 0 if it matches BASELINE

    Fetch the raw log with:
        gh api repos/navigreen311/theoffice/actions/jobs/<job-id>/logs > smoke.raw

    `--check` refuses an empty capture rather than reporting a mismatch, because an empty
    file hashes to something and that something is not a verdict.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

#: The documented failure: eight FAILs and one could-not-run, from the run recorded in
#: `PARALLEL_BUILD.md`. A PR whose normalised step hashes to this has introduced nothing.
BASELINE = "50f95788f3f35a37256f9fe30383378164a98708c98d2acc475fc94ba0f33f80"

_STEP_START = "##[group]Run ./scripts/console-smoke.sh"
_STEP_END = "Process completed with exit code"

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
_CHROMIUM = re.compile(r"^ {4}(DevTools listening|\[\d+:\d+:|$)")
_HEX8 = re.compile(r"\b[0-9a-f]{8}\b")
_TOKEN = re.compile(r"issued [A-Za-z0-9]{8}\.\.\.")


def normalise(raw: str) -> str:
    """The job log in, the compared text out."""
    lines: list[str] = []
    inside = False
    for line in raw.splitlines():
        stripped = _TIMESTAMP.sub("", line)
        if _STEP_START in stripped:
            inside = True
        if not inside:
            continue
        lines.append(stripped)
        if _STEP_END in stripped:
            break

    kept = [ln for ln in lines if not _CHROMIUM.match(ln)]
    masked = [_TOKEN.sub("issued <token>...", _HEX8.sub("<id>", ln)) for ln in kept]
    return "\n".join(masked) + "\n"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    path = pathlib.Path(sys.argv[1])
    mode = sys.argv[2] if len(sys.argv) > 2 else ""

    raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        # Refused rather than hashed. An empty capture produces a stable digest and no
        # verdict, which is how a fetch failure becomes a "divergence".
        print(f"REFUSED: {path} is empty - the capture failed, this is not a mismatch")
        return 2

    text = normalise(raw)
    if _STEP_START not in text:
        print(f"REFUSED: no console-smoke step found in {path}")
        return 2

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    if mode == "--hash":
        print(digest)
        return 0
    if mode == "--check":
        ok = digest == BASELINE
        print(f"{'MATCH' if ok else 'DIVERGENT'}  {digest}")
        if not ok:
            print(f"baseline  {BASELINE}")
            print("Diff the normalised text against the baseline before concluding "
                  "anything - a divergence is a finding, not a verdict.")
        return 0 if ok else 1

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
