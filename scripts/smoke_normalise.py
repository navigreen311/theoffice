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

B49 - THE HASH IS BROKEN BY A FETCH THIS SCRIPT DOES NOT DOCUMENT
=================================================================

    **Fetch it the way USAGE says and the hash was always correct.** `gh api
    .../jobs/<id>/logs` returns one BOM, at byte 0, on a `Current runner version:` line
    that precedes `_STEP_START` and is discarded before anything is hashed.

    **Fetch it with `gh run view --log` and the hash was never correct.** That command
    emits a BOM at the start of every STEP - twelve in the console-smoke job - and one of
    them opens the `##[group]Run ./scripts/console-smoke.sh` line itself. `_TIMESTAMP` is
    anchored with `^`, so that line missed the anchor while every line after it matched:
    the compared region began with a per-run timestamp, and the digest was unique to the
    run by construction. `--check` reported DIVERGENT on a clean run, every time.

    **So this is not an instrument that never worked. It is an instrument used through an
    undocumented port.** The convenient command was substituted for the documented one,
    it differs in a way nothing declared, and the difference was invisible because the
    number was not the thing being read.

    Nobody noticed because nobody was using the number. The verification protocol this
    script exists to serve had settled into `diff`-ing the FAIL lines of two normalised
    captures - a real comparison, and the one every merge this week was actually decided
    by. The hash was computed, seen to differ, and set aside each time.

    **The warning at the top of this file did not catch it, and the warning is about
    this.** It refuses a number reproducible only by the shell history that produced it.
    The digest had precisely that property - reproducible only if you fetched the log the
    same way - and the prose could not catch it, because a paragraph about reproducibility
    is not a check on reproducibility. That is the same defect one level up: the guard
    against unverifiable numbers was itself a paragraph.

    **Third instance of one shape this week**, and the others are real. Gate 7 passed
    because its input set was empty (entry 63); Gate 9's second refusal has never run
    because a prior branch always answered first (entry 76); `--check` was set aside for
    a diff that answered first. In all three, something reported for a long time without
    ever having discriminated - and in this one it was in the instrument being used to
    check the other two.

    Fixed by stripping the BOM per line rather than per file, so the answer no longer
    depends on which line the junk landed on.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

#: The documented failure: eight FAILs and one could-not-run. A PR whose normalised step
#: hashes to this has introduced nothing.
#:
#: **Re-recorded 2026-09-14 (B49), and this time from two runs rather than one.** The
#: previous value could not be reproduced from any capture, which is what B49 turned out
#: to be about. This one was taken from the documented fetch on two different runs -
#:
#:     job 104219635333   main    504ba1f-1     run 34917974505
#:     job 104227014142   branch  9aacd6f       run 34920396861
#:
#: - whose normalised text is byte-identical. **Two runs agreeing is what makes a number
#: a baseline; one run only ever produces a number.**
#:
#: It is specific to `gh api .../jobs/<id>/logs`, the fetch USAGE names. `gh run view
#: --log` renders the ANSI escape on the step's echoed command as the two characters
#: `^[` instead of the ESC byte, so that path has a different digest for the same job and
#: always will. Compare captures taken the same way, or compare the text and not the
#: number.
#:
#: **Re-recorded 2026-09-15 (decisions entry 87), by the same rule.** `c9f1f858` went stale
#: when #140 added V38: main's own Smoke run then differed on `(34)` -> `(35)` in two lines,
#: so every PR reported DIVERGENT and the check could not tell a regression from a rule
#: count. The new value also carries #142's one intended line, `8 declared` -> `6 declared`,
#: from Greenstone's VoiceForge manifest rows leaving. Two runs on the same commit:
#:
#:     job 104506941439   branch  8d455d0       run 35006348454 attempt 1
#:     job 104508683091   branch  8d455d0       run 35006348454 attempt 2
#:
#: byte-identical after normalisation, 432 lines, the same eight FAILs.
#:
#: **Re-recorded 2026-09-15 for PR #143 (decisions entry 91), by the same rule.** The one
#: intended line: `all 48 event types` -> `all 49`, from `forge_tenant_credential_removed`
#: joining the glossary. The first pair did NOT agree - the second run carried thirteen
#: `grep: unknown devices method` lines, because the token-leak check passed a random token
#: that began with "-" to grep as an option and silently checked nothing (fixed in d7688d4,
#: `grep -e`). Recorded from two runs after that fix:
#:
#:     job 104566985411   branch  d7688d4       run 35024155523 attempt 1
#:     job 104568439387   branch  d7688d4       run 35024155523 attempt 2
#:
#: byte-identical, 432 lines, no grep noise, the same eight FAILs.
#:
#: **Re-recorded 2026-09-15 for PR #144 (decisions entry 92), by the same rule.** The one
#: intended line: `named explicitly: Ivan, Dana` -> `named explicitly: Ivan, Ira Green`,
#: from Greenstone's compliance officer changing. Two runs on the same commit:
#:
#:     job 104579996735   branch  0a0a41e       run 35028138055 attempt 1
#:     job 104581275555   branch  0a0a41e       run 35028138055 attempt 2
#:
#: byte-identical, 432 lines, the same eight FAILs.
#:
#: **Re-recorded 2026-09-15 for PR #148 (decisions entry 99), by the same rule.** V2 now
#: asks each hard-bound Forge instead of reading a stored `health_status`, and the smoke
#: world's Forges are seeded at `example.invalid` with credential refs no runner can
#: resolve - so the demo venture now stops at Gate 0 with that reason rather than reaching
#: Gate 2. Five intended lines, all of them that one consequence:
#:
#:     stopped at gate 2 (blocked)      -> stopped at gate 0 (blocked), with the reason
#:     an unvalidated Pack says which   -> a failing Pack names the rules it fails
#:       rules could not run
#:     has passed gate 2                -> has passed gate 0
#:     13 of 13 audit rows              -> 11 of 11 - the run records fewer gate results
#:     13 fixture entries               -> 11
#:
#: Two runs on the same commit:
#:
#:     job 104615144821   branch  232b4d2       run 35039237755 attempt 1
#:     job 104616139575   branch  232b4d2       run 35039237755 attempt 2
#:
#: byte-identical, 432 lines, the same eight FAILs.
#:
#: **Re-recorded 2026-09-15 for PR #149, and this is the run where the script PASSES.**
#: `scripts/stub-forge.py` answers the manifest Gate 0 now asks for, so the demo venture
#: reaches Gate 4 instead of stopping at Gate 0 - and the eight FAILs, which were all
#: downstream of a ladder that never got that far, are gone. **0 FAILs, 0 NOT EXERCISED,
#: 433 lines.** Every changed line, against the immediately previous baseline:
#:
#:     + ==> Forges to ask at Gate 0, the stub's own two lines
#:     - stopped at gate 0 (blocked) / bridge not operational: ... credential ref did
#:       not resolve
#:     + stopped at gate 4 (awaiting_human) / operator review required
#:     - FAIL the Gate 4 review form did not render, and the four that followed it
#:     + the form rendered, the brief is expanded, the preserved copy is verbatim, a
#:       known downstream failure is stated before the human is asked to act
#:     - NOT EXERCISED downstream blocker banner
#:     - FAIL the raw evidence is gone entirely
#:     + the raw evidence is still reachable behind a toggle, and the V13 message keeps
#:       its utilisation-factor line
#:     - FAIL recording a review and advancing are still two unrelated controls
#:     + recording a review and advancing is one action
#:     - FAIL unevaluable rules with no gate named: ['V11', 'V32']
#:     + three states partition all 35 rules; every unevaluable rule names its gate
#:     - instructions are real and V11 says NOT_RUN   ->   + V11 says PASS
#:     - a failing Pack names the rules it fails      ->   + an unvalidated Pack says
#:       which rules could not run
#:     - has passed gate 0                            ->   + has passed gate 4
#:     - 11 of 11 audit rows / 11 fixture entries     ->   + 16 of 16 / 16
#:     - 1 check(s) could not run, 8 check(s) failed, ##[error]exit code 1
#:     + all checks passed
#:
#: Two runs on the same commit:
#:
#:     job 104619575261   branch  10df3b9       run 35040668570 attempt 1
#:     job 104620632483   branch  10df3b9       run 35040668570 attempt 2
#:
#: byte-identical after the region fix recorded above `_RUNNER_TAIL`, which those two
#: runs are what found: a passing step has no "Process completed with exit code" line, so
#: the old region ran on into the runner's teardown and two clean runs disagreed on 150
#: lines of node warnings and container ids. Both previous captures still reproduce their
#: recorded digests under the new anchors, so no red baseline moved.
#:
#: **Re-recorded 2026-09-15 for PR #151 (decisions entry 103), by the same rule.** The one
#: intended line: `all 49 event types` -> `all 50`, from `console_human_renamed` joining
#: the glossary. Still 433 lines, still passing. Two runs on the same commit:
#:
#:     job 104635243838   branch  d7035bb       run 35045789682 attempt 1
#:     job 104636111522   branch  d7035bb       run 35045789682 attempt 2
#:
#: **Re-recorded 2026-09-15 for PR #154 (decisions entry 106), by the same rule.** Five
#: lines, one cause: `simforge/run_scenario_pack` left the test world, because SimForge
#: does not dispatch it and the fixture was the last place it existed.
#:
#:     simforge (2 modules)            -> simforge (1 module)
#:     9 instruction(s) seeded         -> 8
#:     9 instruction sets assessed     -> 8, still 0 thin and 0 teaching nothing
#:     1 of 13 rows are test data      -> 1 of 12
#:     12 rows that are not fixtures   -> 11
#:
#: Two runs on the same commit:
#:
#:     job 104654251988   branch  d6bbae8       run 35051907452 attempt 1
#:     job 104654762310   branch  d6bbae8       run 35051907452 attempt 2
BASELINE = "55222979312af2df7ea7bb5de98fe2f3ad177229fcdc56653ab7ed28e16f8bec"

_STEP_START = "##[group]Run ./scripts/console-smoke.sh"

#: Where the compared region ends. TWO anchors, because the first only ever appeared on
#: a run that failed.
#:
#: `Process completed with exit code` is written by the runner when a step exits
#: non-zero. The smoke step had exited non-zero on every run since it was written - eight
#: FAILs by design - so that line was always there, and nothing noticed that a PASSING
#: step has no such line at all. When the Forges started answering and the script passed
#: for the first time, the region ran to the end of the job log and swallowed the
#: teardown: node deprecation warnings, a pip cache line, a temporary HOME path, the
#: Postgres service container's id and its startup log. **Two runs of a passing job then
#: disagreed on 150 lines of runner noise, none of it produced by the thing under test.**
#:
#: `Post job cleanup.` is the runner's first line after the step, pass or fail, so it is
#: the anchor that does not depend on the verdict. It is NOT appended - the region ends
#: with the script's own last line.
#:
#: **`##[endgroup]` is the anchor that looks right and is not.** The runner writes
#: `##[group]Run ./scripts/console-smoke.sh`, echoes the command and its environment,
#: and closes that group SIXTEEN LINES IN, before the script has printed anything. Ending
#: there would have hashed the env block and none of the output, and it would have
#: matched itself run after run - a stable digest of the wrong text.
_STEP_END = "Process completed with exit code"

#: Lines the RUNNER writes after the step's own output, none of them produced by the
#: thing under test. The region ends before the first of them. A list rather than a
#: pattern because each one earns its place by having appeared: the deprecation notices
#: are GitHub's, they change when GitHub changes them, and a baseline that moves because
#: a runner changed its wording is a gate nobody will trust.
_RUNNER_TAIL = (
    "Post job cleanup.",
    "Node 20 is being deprecated",
    "##[warning]Node.js 20",
)

_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z ")
_CHROMIUM = re.compile(r"^ {4}(DevTools listening|\[\d+:\d+:|$)")
_HEX8 = re.compile(r"\b[0-9a-f]{8}\b")
#: Console tokens are URL-safe base64, so the prefix can carry `_` and `-`. The first
#: version of this mask was `[A-Za-z0-9]{8}` and matched every capture the baseline was
#: built from - none of which happened to contain one. #109 did, and the script reported
#: DIVERGENT on a clean run: a false red, which is the direction that erodes a gate.
_TOKEN = re.compile(r"issued [A-Za-z0-9_-]{8}\.\.\.")


def normalise(raw: str) -> str:
    """The job log in, the compared text out."""
    lines: list[str] = []
    inside = False
    for line in raw.splitlines():
        # Per line, not once at the top. `gh run view --log` emits a BOM at the start of
        # every STEP - twelve in one job - and one of them is the `##[group]Run
        # ./scripts/console-smoke.sh` line that opens the compared region. A BOM there
        # pushes that line off `_TIMESTAMP`'s `^` anchor, so it keeps a per-run
        # timestamp and the digest becomes unique to the run. B49.
        stripped = _TIMESTAMP.sub("", line.lstrip("\ufeff"))
        if _STEP_START in stripped:
            inside = True
        if not inside:
            continue
        if stripped.strip().startswith(_RUNNER_TAIL):
            break
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

    # Byte 0 of every capture is a UTF-8 BOM. On the documented `gh api` path it sits on
    # a line this script discards, so it never reached the digest; stripped anyway,
    # because a normaliser that depends on which line the junk landed on is not one.
    raw = path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff")
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
