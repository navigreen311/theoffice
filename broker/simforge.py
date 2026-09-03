"""The SimForge contract, and the boundary The Office must never cross.

Part 10.1, resolved (J8): **SimForge owns the held-out partition outright.** Held-out
scenario content lives in SimForge storage. The Office holds none of it and exposes no
endpoint, field, log, query, backup or export that returns it.

The Office's obligation here is **negative**. There is no read path to build — only one
never to build. That is unusually hard to enforce, because you cannot demonstrate the
absence of a capability by exercising it.

So the enforcement is a manifest plus a test, not a promise:

  * every field SimForge may return to The Office is enumerated below, with a declared
    purpose;
  * `tests/golden/test_no_read_path.py` walks real responses and fails on any field the
    manifest does not name, on any field that could carry scenario content, and on any
    parameter combination that produces scenario bodies.

Master prompt Part 10.1: *"Because Green Companies operates both sides of this boundary,
self-attestation is the weakest possible enforcement for the one control whose entire
purpose is preventing one side from seeing the other's content."* Both sides being the
same company is exactly why a machine has to check this continuously.

**Adding a field here without adding it to the manifest fails the build.** That is the
mechanism, and it is deliberate that it is annoying.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from psycopg.rows import dict_row

MANIFEST_PATH = Path(__file__).with_name("simforge_response_manifest.json")

# Substrings that, appearing in a field name, indicate scenario content. Deliberately
# broad: a false positive costs one rename, a false negative costs the boundary.
FORBIDDEN_NAME_FRAGMENTS = (
    "scenario_body",
    "scenario_text",
    "scenario_content",
    "scenarios",
    "held_out",
    "heldout",
    "prompt",
    "expected_answer",
    "expected_output",
    "rubric_detail",
    "answer_key",
    "transcript",
    "case_text",
)

# Parameters a careless caller or a determined one would reach for. The check sweeps
# every combination and asserts none of them widens the response.
SMUGGLING_PARAMS: tuple[dict[str, Any], ...] = (
    {},
    {"include_scenarios": "true"},
    {"include_scenarios": "1"},
    {"expand": "scenarios"},
    {"expand": "*"},
    {"fields": "*"},
    {"verbose": "true"},
    {"debug": "true"},
    {"include": "held_out"},
    {"format": "full"},
    {"depth": "999"},
)


class SimForgeError(Exception):
    """SimForge could not be reached, or answered in a shape the contract forbids."""


@dataclass(frozen=True, slots=True)
class GateResult:
    """What The Office is allowed to learn from a certification run.

    A verdict, a score against a threshold, and provenance. Not *why* — the reasoning
    is scenario-adjacent, and a rich enough explanation of a failure reconstructs the
    scenario that produced it.
    """

    run_ref: str
    unit: str
    verdict: str
    rubric_kind: str
    rubric_version: str
    score: float | None
    threshold: float | None
    certified_tier: str | None
    scenario_count: int
    coverage_denominator: int


class SimForgeClient(Protocol):
    async def submit_curriculum(
        self, *, scenario_pack_ref: str, payload: dict[str, Any]
    ) -> str: ...

    async def get_gate_result(self, run_ref: str) -> dict[str, Any]: ...


def load_manifest() -> dict[str, dict[str, Any]]:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        data: dict[str, dict[str, Any]] = json.load(fh)
    return data


def manifested_fields(endpoint: str) -> set[str]:
    manifest = load_manifest()
    # Leading-underscore keys are documentation (_README, _deliberately_absent), not
    # endpoints. Treating one as callable would legalise the forbidden-field list.
    if endpoint.startswith("_") or endpoint not in manifest:
        raise SimForgeError(
            f"endpoint {endpoint!r} is not in the SimForge response manifest. "
            "Every endpoint must be enumerated before it may be called."
        )
    return set(manifest[endpoint]["fields"])


def assert_no_scenario_content(endpoint: str, body: Any, *, path: str = "") -> None:
    """Recursively assert a response carries no scenario content.

    Two independent checks, because either alone is defeatable:
      * field NAMES are matched against FORBIDDEN_NAME_FRAGMENTS — catches an
        honestly-named leak;
      * field VALUES are checked for prose shape — catches a leak hidden behind an
        innocuous name like `notes` or `meta`.

    Prose shape is a heuristic, and that is acknowledged: a long free-text string is
    not proof of a scenario. It is a tripwire, and a tripwire that occasionally fires
    on a legitimate field is doing its job — the response to it is to narrow the field,
    not to widen the check.
    """
    if isinstance(body, dict):
        for key, value in body.items():
            here = f"{path}.{key}" if path else key
            lowered = key.lower()
            for fragment in FORBIDDEN_NAME_FRAGMENTS:
                if fragment in lowered:
                    raise SimForgeError(
                        f"{endpoint}: field {here!r} matches forbidden fragment "
                        f"{fragment!r}. The Office has no read path to scenario "
                        "content; this field must not exist."
                    )
            assert_no_scenario_content(endpoint, value, path=here)
    elif isinstance(body, list):
        for i, item in enumerate(body):
            assert_no_scenario_content(endpoint, item, path=f"{path}[{i}]")
    elif isinstance(body, str) and _looks_like_prose(body):
        raise SimForgeError(
            f"{endpoint}: field {path!r} carries {len(body)} characters of prose. "
            "Scenario content must never reach The Office; if this field is "
            "legitimate, narrow it rather than widening the check."
        )


def _looks_like_prose(value: str) -> bool:
    """A long, multi-sentence, multi-word string is scenario-shaped.

    Thresholds are deliberately generous: refs, hashes and version strings are long
    but have no sentence structure, and short human labels have structure but no
    length. A scenario has both.
    """
    if len(value) < 200:
        return False
    words = value.split()
    return len(words) >= 30 and value.count(" ") > 20


def validate_response(endpoint: str, body: dict[str, Any]) -> None:
    """The build-failing check: shape, then content.

    Field-set equality in the *unexpected* direction only. A response omitting an
    optional field is fine; a response carrying a field nobody enumerated is the
    case this exists to catch.
    """
    allowed = manifested_fields(endpoint)
    actual = set(body)
    undeclared = actual - allowed
    if undeclared:
        raise SimForgeError(
            f"{endpoint}: response carries field(s) not in the SimForge response "
            f"manifest: {sorted(undeclared)}. Add them to "
            f"{MANIFEST_PATH.name} with a declared purpose, or remove them. "
            "This check exists so a new field cannot arrive unreviewed."
        )
    assert_no_scenario_content(endpoint, body)


def parse_gate_result(body: dict[str, Any]) -> GateResult:
    """Validate then narrow. The dataclass is the only thing callers see."""
    validate_response("get_gate_result", body)
    return GateResult(
        run_ref=body["run_ref"],
        unit=body["unit"],
        verdict=body["verdict"],
        rubric_kind=body["rubric_kind"],
        rubric_version=body["rubric_version"],
        score=body.get("score"),
        threshold=body.get("threshold"),
        certified_tier=body.get("certified_tier"),
        scenario_count=body["scenario_count"],
        coverage_denominator=body["coverage_denominator"],
    )


# ------------------------------------------------------- the timeout that never came

#: How long a submitted curriculum may sit without a result before it is treated as
#: TIMEOUT. Deliberately generous: an operation battery is slow, and resolving a
#: still-running run to `in_training` is harmless (it already is in training) while
#: resolving one too eagerly churns certifications.
DEFAULT_RUN_DEADLINE_HOURS = 24


async def overdue_submissions(
    conn: Any,
    *,
    deadline_hours: int = DEFAULT_RUN_DEADLINE_HOURS,
) -> list[dict[str, Any]]:
    """Submissions that were handed over and never answered.

    THE GAP THIS CLOSES
    ===================

        `certification.VERDICT_TO_STATE` maps TIMEOUT to `in_training`, and Part 10.1
        requires that a timeout never resolve to PASS. That mapping is correct and it
        was also unreachable: **SimForge does not emit a TIMEOUT verdict.** Its outbound
        shape carries states, not verdicts, and none of them means "this run did not
        finish".

        So the real failure mode was never a TIMEOUT resolving to PASS. It was a hung
        run resolving to *nothing at all* — no callback, no verdict, no row, and a
        certification left in whatever state it held before. That is a different failure
        with the same consequence, and it is worse in one respect: a verdict that never
        arrives raises no error anywhere.

    WHY THE OFFICE HAS TO DETECT THIS AND NOT SIMFORGE
    ==================================================

        SimForge should report a run it knows exceeded its window, and that is being
        asked of it separately. But the case that matters most is the one where
        SimForge's worker died — and a process that has died cannot report that it has.
        A deadline held by the party that is *waiting* is the only version of this check
        that survives the failure it exists to catch.

        This is the same reasoning as the shift flush: a control that depends on the
        failing component to announce its own failure is not a control.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT submission_id, venture_id, forge_id, module_id, department,
                   scenario_pack_ref, simforge_run_ref, submitted_at,
                   instruction_content_hash,
                   EXTRACT(EPOCH FROM (now() - submitted_at)) / 3600.0 AS hours_waiting
            FROM curriculum_submission
            WHERE result_received_at IS NULL
              AND submitted_at < now() - make_interval(hours => %s)
            ORDER BY submitted_at
            """,
            (deadline_hours,),
        )
        return [dict(r) for r in await cur.fetchall()]


def timeout_gate_result(submission: dict[str, Any], *, rubric_version: str) -> GateResult:
    """The verdict a silent run resolves to.

    Constructed here rather than by the caller so there is exactly one place that can
    decide what an unanswered run means, and it cannot be PASS: `verdict` is fixed at
    TIMEOUT, and `score` and `certified_tier` are None because nothing was measured.

    A `score` of 0.0 would have been the tempting default and is wrong — it says the
    agent scored zero, which is a claim about the agent rather than about the run.
    """
    return GateResult(
        run_ref=submission.get("simforge_run_ref") or f"unanswered:{submission['submission_id']}",
        unit="A" if submission.get("module_id") else "B",
        verdict="TIMEOUT",
        rubric_kind="operation" if submission.get("module_id") else "domain",
        rubric_version=rubric_version,
        score=None,
        threshold=None,
        certified_tier=None,
        scenario_count=0,
        coverage_denominator=0,
    )


async def record_submission(
    conn: Any,
    *,
    venture_id: str,
    forge_id: str,
    scenario_pack_ref: str,
    scenario_count: int,
    coverage_denominator: int,
    instruction_content_hash: str,
    submitted_by: uuid.UUID,
    module_id: str | None = None,
    department: str | None = None,
) -> uuid.UUID:
    """Record that curriculum was handed over.

    Stores refs and counts. Never scenario bodies - the submission record is on the
    Office side of the boundary, and a table holding what was sent is a table
    holding scenario content.
    """
    submission_id = uuid.uuid4()
    async with conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO curriculum_submission
              (submission_id, venture_id, forge_id, module_id, department,
               scenario_pack_ref, scenario_count, coverage_denominator,
               instruction_content_hash, submitted_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                submission_id, venture_id, forge_id, module_id, department,
                scenario_pack_ref, scenario_count, coverage_denominator,
                instruction_content_hash, submitted_by,
            ),
        )
    await conn.commit()
    return submission_id
