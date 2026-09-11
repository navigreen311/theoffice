"""The merge gate's normaliser, tested on the cases that have actually bitten it.

`scripts/smoke_normalise.py` decides whether a PR's Smoke output is the documented
failure or something new. It was verified once, by hand, against five clean captures, a
real ninth failure and an empty file — and it passed all seven while carrying a defect,
because **none of those seven captures contained a console token with an underscore.**

#109's did. The script reported DIVERGENT on a clean run, and the fix (#112) merged on a
green check that could not have caught its own subject: that run's token had no
underscore either.

So these are not tests of the happy path. **Every case here is one that got through.**

Fixtures are built in the test rather than committed as 100 KB job logs: what is under
test is the normaliser, and a synthetic step exercises every substitution with nothing
incidental in it.
"""

from __future__ import annotations

import importlib.util
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "smoke_normalise",
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "smoke_normalise.py",
)
assert _SPEC and _SPEC.loader
smoke_normalise = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(smoke_normalise)

normalise = smoke_normalise.normalise

TS = "2026-09-11T04:12:33.1234567Z "


def _log(*body: str) -> str:
    """A job log around a console-smoke step, with the setup and teardown that surround it."""
    lines = [
        f"{TS}Current runner version: '2.337.0'",
        f"{TS}##[group]Run actions/checkout@v4",
        f"{TS}##[group]Run ./scripts/console-smoke.sh",
        *[f"{TS}{ln}" for ln in body],
        f"{TS}##[error]Process completed with exit code 1.",
        f"{TS}Post job cleanup.",
    ]
    return "\n".join(lines) + "\n"


def test_the_step_is_extracted_and_the_surrounding_job_is_not():
    out = normalise(_log("  a check passed"))
    assert "console-smoke.sh" in out
    assert "Current runner version" not in out, "setup leaked in"
    assert "Post job cleanup" not in out, "teardown leaked in"
    assert "Process completed with exit code" in out, "the step's end is part of the step"


def test_the_timestamp_column_goes():
    assert TS.strip() not in normalise(_log("  a check passed"))


def test_a_token_with_an_underscore_is_masked():
    """**The case that produced a false DIVERGENT on #109, and the reason this file exists.**

    Console tokens are URL-safe base64. The first mask was `[A-Za-z0-9]{8}` and every
    capture the baseline was built from happened to carry a token without `_` or `-`, so
    seven hand-verifications and one green CI run all passed over it.
    """
    out = normalise(_log("  issued EH4_PjnX..."))
    assert "issued <token>..." in out
    assert "EH4_PjnX" not in out


def test_a_token_with_a_hyphen_is_masked():
    """`-` is the other URL-safe character, and no capture has carried one yet.

    Written before it bites rather than after, which is the whole difference between this
    test and the one above it.
    """
    out = normalise(_log("  issued QZ2-kR8m..."))
    assert "issued <token>..." in out
    assert "QZ2-kR8m" not in out


def test_a_plain_alphanumeric_token_still_masks():
    out = normalise(_log("  issued G0eBHJHt..."))
    assert "issued <token>..." in out


def test_run_ids_are_masked_and_the_sentence_around_them_is_not():
    out = normalise(_log("  run dbc9b4cd stopped at gate 2 (blocked)"))
    assert "run <id> stopped at gate 2 (blocked)" in out
    assert "dbc9b4cd" not in out


def test_chromium_stderr_is_dropped_because_its_order_is_not_stable():
    """The reason a line-count comparison was never enough.

    These lines arrive in a different order run to run, so two identical runs differ by
    permutation. Counting red checks cannot see that; neither can counting lines.
    """
    out = normalise(_log(
        "  a check passed",
        "    DevTools listening on ws://127.0.0.1:9333/devtools/browser/263aa0af-2739",
        "    [4029:4029:0910/041337.471513:ERROR:dbus/object_proxy.cc:572] Failed",
        "    [4029:4118:0910/041337.471631:ERROR:dbus/bus.cc:405] Failed to connect",
    ))
    assert "DevTools" not in out
    assert "dbus" not in out
    assert "a check passed" in out


def test_a_fail_line_is_never_touched():
    """The whole point. Everything else is masked so that these compare byte for byte."""
    fail = "  FAIL unevaluable rules with no gate named: ['V11', 'V32']"
    assert fail in normalise(_log(fail))


def test_two_runs_differing_only_in_run_specific_values_normalise_identically():
    a = _log("  issued EH4_PjnX...", "  run dbc9b4cd stopped at gate 2 (blocked)")
    b = _log("  issued QZ2-kR8m...", "  run 448e0add stopped at gate 2 (blocked)")
    assert normalise(a) == normalise(b)


def test_a_real_difference_survives_normalisation():
    """A ninth failure must not be masked away by the thing that masks run ids.

    #98 carried one and the same-red-count check passed it; only the text diff caught it.
    """
    clean = _log("  8 check(s) failed")
    ninth = _log("  FAIL 3 identifier(s) render as primary text:", "  9 check(s) failed")
    assert normalise(clean) != normalise(ninth)
