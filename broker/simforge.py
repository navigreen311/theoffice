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
from typing import TYPE_CHECKING, Any

import httpx
from psycopg.rows import dict_row

from broker.audit import write_event
from broker.config import get_settings
from broker.credentials import Credential, build_resolver

if TYPE_CHECKING:  # a broker module must not import the client at runtime
    from client.office_client import AgentContext, OfficeClient

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


class SimForgeClient:
    """The only two calls The Office makes to SimForge.

    **They travel different paths, and that asymmetry is the design.**

    `get_gate_result` is brokered. An agent reads a verdict about its own
    certification, so it goes through `OfficeClient.call` exactly like any other
    Forge module: a grant resolved fresh, a trust tier, a shift, an idempotency
    key, an audit entry before the call and a ledger row after. Nothing here
    modifies that path - this class supplies the module name and narrows the
    answer.

    `submit_curriculum` is not brokered. It is signed with The Office's own
    tenant credential and audited as `curriculum_handed_over`, naming the human
    who provisioned.

    WHY GATE 8 DOES NOT GET AN AGENT
    ================================

        The brokered path takes an `AgentContext` and writes a ledger row naming
        that agent. Gate 8 runs during provisioning: the actor is a human, and
        the agents that will hold grants for this venture do not exist yet.
        There is no agent behind a curriculum hand-over because no agent
        performs it.

        Minting one to satisfy the signature is `origin='human'` again. That
        column exists because an audit entry signed by a fixture is worthless -
        an actor named in a record as though it acted. An agent invented to fill
        an `agent_ctx` is the same object: a name in a ledger row for a call it
        did not make, indistinguishable afterwards from one it did.

        So the hand-over is recorded as what it is - an Office act, with the
        human on it - and the ledger keeps meaning "an agent did this".
    """

    def __init__(
        self,
        office: OfficeClient,
        *,
        forge_id: str = "simforge",
        http: httpx.AsyncClient | None = None,
        resolver: Any | None = None,
    ) -> None:
        self._office = office
        self._forge_id = forge_id
        settings = get_settings()
        self._http = http or httpx.AsyncClient()
        self._owns_http = http is None
        self._resolver = resolver or build_resolver(settings.credential_backend)
        self._timeout = settings.forge_timeout_seconds

    # ------------------------------------------------------------- brokered

    async def get_gate_result(
        self, run_ref: str, *, agent_ctx: AgentContext
    ) -> GateResult:
        """Read one verdict, as the agent it is about.

        The response is validated before any caller sees it. `parse_gate_result`
        runs `validate_response`, which refuses a field the manifest does not
        name and refuses prose anywhere in the body - so a SimForge that started
        returning scenario content raises here rather than reaching a caller who
        might store it.
        """
        result = await self._office.call(
            self._forge_id, "gate_result", {"run_ref": run_ref}, agent_ctx=agent_ctx
        )
        if result.status_code == 404:
            raise SimForgeError(f"SimForge has no record of run_ref {run_ref!r}")
        if result.status_code >= 400:
            # The body is not echoed. A Forge error body has not been through
            # validate_response, and an exception message is the one place a leak
            # would travel without being checked.
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned {result.status_code}"
            )
        if not isinstance(result.body, dict):
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned "
                f"{type(result.body).__name__}, not an object"
            )
        return parse_gate_result(result.body)

    # --------------------------------------------------------- not brokered

    async def submit_curriculum(
        self,
        conn: Any,
        *,
        scenario_pack_ref: str,
        payload: dict[str, Any],
        actor: uuid.UUID,
        venture_id: str,
    ) -> str:
        """Hand a curriculum over. Returns SimForge's `run_ref`.

        Audited before the call and not after, for the reason `broker/audit.py`
        gives: a hand-over that reaches SimForge and then crashes this process
        must still have left a trace, or the run exists on one side only and
        nothing here knows to wait for it.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        await write_event(
            event_type="curriculum_handed_over",
            actor_type="human",
            actor_id=actor,
            venture_id=venture_id,
            subject={
                "forge_id": self._forge_id,
                "scenario_pack_ref": scenario_pack_ref,
                # Counts, never bodies. Same rule as `record_submission`: a record
                # of what was sent must not become a copy of it.
                "scenario_count": payload.get("scenario_count"),
                "coverage_denominator": payload.get("coverage_denominator"),
            },
        )

        url = f"{base_url.rstrip('/')}/submit_curriculum"
        try:
            response = await self._http.post(
                url,
                json={"scenario_pack_ref": scenario_pack_ref, **payload},
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL,
            # and this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            raise SimForgeError(
                f"submit_curriculum returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("submit_curriculum returned a non-JSON body") from exc

        validate_response("submit_curriculum", body)
        if not body.get("accepted"):
            raise SimForgeError(
                f"SimForge refused the curriculum: {body.get('rejected_reason')!r}"
            )
        run_ref = body.get("run_ref")
        if not isinstance(run_ref, str) or not run_ref:
            # An accepted hand-over with no ref is unusable: nothing correlates a
            # verdict to it, and `overdue_submissions` cannot see it time out.
            raise SimForgeError(
                "SimForge accepted the curriculum without returning a run_ref"
            )
        return run_ref

    # ----------------------------------------------------------- internals

    async def _tenant_credential(self, conn: Any) -> Credential:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT credential_ref FROM forge_tenant_credential WHERE forge_id = %s",
                (self._forge_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise SimForgeError(
                f"no tenant credential is registered for {self._forge_id!r}; "
                "this Forge has not been onboarded"
            )
        return await self._resolver.resolve(row[0])

    async def _registry(self, conn: Any) -> tuple[str, str]:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT base_url, api_version FROM forge_registry WHERE forge_id = %s",
                (self._forge_id,),
            )
            row = await cur.fetchone()
        if row is None:
            raise SimForgeError(f"{self._forge_id!r} is not in forge_registry")
        return str(row[0]), str(row[1])

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


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
