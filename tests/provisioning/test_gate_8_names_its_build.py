"""Gate 8 records which build submitted, and refuses to submit on one that is stale.

WHY THIS GATE AND NOT THE OTHERS
================================

    Gate 8's output is generated from FILES BESIDE THE CODE - the Pack, the
    instructions, and `scenarios/*.yaml`. Every other gate reads the database, where a
    stale process and a current one see the same rows and disagree about nothing. Gate
    8 is the one that can submit a superseded curriculum and be truthful about every
    number it reports, because it is reporting truthfully about the wrong tree.

WHAT HAPPENED TWICE, IN TWO DAYS
================================

        17 Sep 17:00  run c4edc85a   "41 scenario(s) ... across 4 module(s)"
        18 Sep 15:52  run b8ca7dec   "41 scenario(s) ... across 4 module(s)"

    The same sentence, the second one recorded hours after 44 approved scenarios were
    merged. The API was serving from a worktree detached at an older commit. Neither
    gate result carried one field that could have said so.

    **What eventually found it was arithmetic**: `scenario_count` read 7 on every
    module, and the approved keys carry 8, 8, 5, 10 and 13. A coincidence a reader
    happened to notice is not a control, and the second incident proves the first one
    taught nothing, because there was nothing recorded to learn from.

THE LOAD-BEARING TEST IN THIS FILE
==================================

    `test_a_current_build_still_submits`. Every other test asserts something is
    refused, and a gate that refused every build would satisfy all of them while
    stopping the ladder on every machine in the world.
"""

from __future__ import annotations

import pytest

from broker import build, provisioning
from tests.conftest import requires_db
from tests.provisioning.test_simforge_handover import (  # noqa: F401 - fixtures
    SimForgeAccepts,
    at_gate_8,
)

pytestmark = [requires_db, pytest.mark.db]

CURRENT = "a" * 40
MOVED_ON = "b" * 40


def _gate_8(outcomes):
    for outcome in outcomes:
        if outcome.gate == "8":
            return outcome
    raise AssertionError("Gate 8 did not run")


def _identity(commit: str, checkout: str, *, stamped: bool = False) -> build.BuildIdentity:
    return build.BuildIdentity(
        commit=commit, checkout=checkout, root="/checkout", stamped=stamped
    )


# ------------------------------------------------------------- the identity itself

def test_a_worktrees_dot_git_is_a_file_and_must_still_be_asked():
    """**The configuration the incident actually ran on.**

    A git worktree's `.git` is a FILE pointing at the main checkout's admin directory,
    not a directory. `_git_head` tests it with `exists()` for that reason: `is_dir()`
    would report every worktree as unidentifiable, and a worktree is exactly what was
    serving in both incidents. This asserts against the real tree the suite runs in.
    """
    resolved = build.identity()
    assert resolved.identified, (
        f"this checkout ({resolved.root}) cannot name its own commit; a worktree's "
        "`.git` is a file and the probe must not require a directory"
    )
    assert resolved.commit == resolved.checkout or resolved.stamped


def test_a_stamped_image_is_not_compared_against_a_tree_it_does_not_have():
    """An image carries no `.git`. "Not comparable" is honest; "stale" would be false."""
    image = _identity("deadbeef" * 5, "", stamped=True)
    assert image.identified
    assert not image.comparable
    assert image.current, "an image has no tree to have moved past it"
    assert build.refusal(image) is None


def test_an_unstamped_image_cannot_say_what_it_is():
    """No stamp and no git tree. This is the state an unstamped image build produces."""
    nameless = _identity(build.UNKNOWN, "")
    assert not nameless.identified
    assert "cannot be identified" in (build.refusal(nameless) or "")


def test_the_refusal_names_both_commits_and_the_directory():
    """The reason IS the deliverable.

    Both incidents cost forensics because the record said what was sent and never what
    sent it. A block reading "stale build" would send the next reader to `git log`;
    this one ends the investigation where it starts.
    """
    stale = build.refusal(_identity(CURRENT, MOVED_ON)) or ""
    assert CURRENT[:12] in stale
    assert MOVED_ON[:12] in stale
    assert "/checkout" in stale


# -------------------------------------------------------------- the gate's behaviour

async def test_a_stale_build_submits_nothing_at_all(at_gate_8, operator):  # noqa: F811
    """**Refused before the client is built**, so no module and no department unit goes.

    A gate that refuses after sending four modules has not refused: SimForge would hold
    a curriculum from a tree nobody approved, a `curriculum_submission` row would be
    owed a verdict, and the sweep would ingest a result earned on superseded scenarios.
    """
    conn, run_id = at_gate_8
    forge = SimForgeAccepts()
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=forge,
        build_identity=_identity(CURRENT, MOVED_ON),
    )

    gate_8 = _gate_8(outcomes)
    assert gate_8.verdict == provisioning.BLOCKED
    assert gate_8.reason.startswith("Refusing to submit:")
    assert gate_8.evidence["submitted"] is False
    assert not forge.calls, (
        f"{len(forge.calls)} curriculum(s) reached SimForge from a stale build"
    )
    assert not forge.run_starts, "a run was opened by a build that may not submit"

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT count(*) FROM curriculum_submission WHERE venture_id = %s",
            ("greenstone",),
        )
        assert (await cur.fetchone())[0] == 0, (
            "a correlation row was written for a submission that never happened; the "
            "sweep would owe a verdict on it for ever"
        )


async def test_a_build_nobody_can_identify_may_not_submit(at_gate_8, operator):  # noqa: F811
    """`dev-all.sh`'s rule, not a new one.

    Entry 123 changed that script from reporting `ok "live (build unverified)"` to
    calling it bad: *"a build nobody could identify is not a build that was checked."*
    A gate that submitted on `unknown` while the shell script refused to call the same
    process healthy would be two controls disagreeing about one fact.
    """
    conn, run_id = at_gate_8
    forge = SimForgeAccepts()
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=forge,
        build_identity=_identity(build.UNKNOWN, ""),
    )

    gate_8 = _gate_8(outcomes)
    assert gate_8.verdict == provisioning.BLOCKED
    assert not forge.calls


async def test_a_current_build_still_submits(at_gate_8, operator):  # noqa: F811
    """**The test that keeps this a check rather than an off switch.**

    Every other test here asserts something is refused. A gate that refused every build
    would satisfy all of them and stop the ladder on every machine in the world.
    """
    conn, run_id = at_gate_8
    forge = SimForgeAccepts()
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=forge,
        build_identity=_identity(CURRENT, CURRENT),
    )

    gate_8 = _gate_8(outcomes)
    assert gate_8.verdict == provisioning.PASSED
    assert gate_8.evidence["submitted"] is True
    assert forge.calls, "a current build submitted nothing"


# ------------------------------------------------------------------ what is recorded

async def test_the_evidence_names_the_build_and_where_the_scenarios_came_from(
    at_gate_8, operator,  # noqa: F811
):
    """**The two fields that would have closed both incidents on sight.**

    `checkout_root` and `scenario_root` share one anchor - the directory the code was
    imported from - because code and content travel together: a process cannot read one
    checkout's code and another's answer keys. Recording both, rather than deriving one
    from the other, is what lets a reader check the claim instead of trusting it.
    """
    conn, run_id = at_gate_8
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=SimForgeAccepts(),
        build_identity=_identity(CURRENT, CURRENT),
    )

    recorded = _gate_8(outcomes).evidence["submitting_build"]
    assert recorded["commit"] == CURRENT
    assert recorded["checkout_head"] == CURRENT
    assert recorded["checkout_root"] == "/checkout"
    assert recorded["current"] is True
    assert recorded["stamped"] is False
    assert recorded["scenario_root"].endswith("scenarios"), (
        f"the scenario root is not recorded: {recorded['scenario_root']!r}. It is half "
        "of the 17 September finding - the build named one tree and the answer keys "
        "came from it, and nothing said which"
    )


async def test_the_build_is_recorded_on_the_refusal_too(at_gate_8, operator):  # noqa: F811
    """A refusal is the outcome most in need of it.

    The evidence on a block is what a reader opens first, and a block that withheld the
    identity would be the original defect with a louder verdict.
    """
    conn, run_id = at_gate_8
    outcomes = await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=SimForgeAccepts(),
        build_identity=_identity(CURRENT, MOVED_ON),
    )

    recorded = _gate_8(outcomes).evidence["submitting_build"]
    assert recorded["commit"] == CURRENT
    assert recorded["checkout_head"] == MOVED_ON
    assert recorded["current"] is False


async def test_the_recorded_build_survives_into_the_stored_gate_result(
    at_gate_8, operator,  # noqa: F811
):
    """Recorded in the row, not only returned to the caller.

    Both incidents were investigated days later, from `provisioning_gate_result`. An
    identity that existed only in the return value would be an identity nobody reading
    the ledger could ever see, which is the whole failure restated.
    """
    conn, run_id = at_gate_8
    await provisioning.advance(
        conn, run_id=run_id, actor=operator.human_id, simforge=SimForgeAccepts(),
        build_identity=_identity(CURRENT, CURRENT),
    )

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT evidence FROM provisioning_gate_result "
            " WHERE run_id = %s AND gate = '8' ORDER BY recorded_at DESC LIMIT 1",
            (run_id,),
        )
        stored = (await cur.fetchone())[0]

    assert stored["submitting_build"]["commit"] == CURRENT
    assert stored["submitting_build"]["checkout_root"] == "/checkout"
