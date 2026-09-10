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

import hashlib
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
from broker.errors import CredentialUnavailable

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


class CurriculumRejectedError(SimForgeError):
    """SimForge validated the curriculum and refused it, naming what is missing.

    Its own type because it is **an answer, not a fault**. Unreachable means nothing was
    learned; rejected means SimForge read the submission and said which Batch-3 rules it
    fails. Collapsing the two loses the only useful half - a rejection names the work.
    """

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        count = len(violations)
        super().__init__(
            f"SimForge refused the curriculum: {count} violation(s). "
            + "; ".join(violations[:4])
            + (" ..." if count > 4 else "")
        )


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
    #: `provider/model` that answered the battery, e.g. `ollama/llama3.1:8b`.
    #:
    #: Optional on the wire and NOT optional in the record: a verdict that arrives
    #: without one cannot be stored as a certification, because
    #: `certified_records_its_basis` refuses it. The field is `str | None` here so an
    #: older SimForge that does not send it produces a REFUSAL at the guard rather than
    #: a parse error at the boundary - the two need different responses, and the first
    #: names the missing fact while the second only says the shape was wrong.
    agent_model: str | None = None


def submission_unit(module_id: str | None) -> tuple[str, str]:
    """`(unit, rubric_kind)` for one curriculum submission. **The only place that decides.**

    A submission naming a module is a unit A - one agent, one Forge, one module, judged
    against the operation rubric. One naming no module is a unit B - a department in a
    Forge, judged against the domain rubric.

    Extracted from `timeout_gate_result`, which has answered this exact question since
    it was written and is now this function's second caller rather than a second rule.
    `run_start` needs the same answer at the *start* of a run that the timeout sweep
    needs at the end of one, and two spellings of one rule is how the sweep and the
    hand-over would eventually disagree about what a run is - silently, because both
    would look right beside their own call site.
    """
    return ("A", "operation") if module_id else ("B", "domain")


def mint_run_ref(
    *,
    venture_id: str,
    forge_id: str,
    module_id: str | None,
    content_hash: str,
    department: str | None = None,
) -> str:
    """The run reference The Office mints, and SimForge opens a run under.

    **The Office mints this, not SimForge.** `OperationRunStartRequest.run_ref` is an
    input field, and its own docstring says why the unit travels with it: "The Office
    reads one verdict per `run_ref`, and a run whose unit is only known once it finishes
    cannot be asked about while it is hanging." A ref the receiving side invents cannot
    be declared before the run exists, which is the whole point of the call.

    DETERMINISTIC, DELIBERATELY
    ===========================

        Derived from the submission's natural key - venture, forge, module, and the
        instruction content hash. That is the same key SimForge upserts the bound
        instruction set on, so the two systems agree on what "the same submission"
        means without either asserting it.

        The consequence is the reason: `open_run` is idempotent on `run_ref` and
        returns the existing row with its clock UNTOUCHED, so a re-run of Gate 8
        against an unchanged instruction lands on the run that is already open rather
        than starting a second window. Extending the window of a hanging run is the one
        thing that hides a timeout, and a fresh uuid per attempt would do it from the
        caller's side while SimForge's own guard read as satisfied.

        A changed `content_hash` is a different instruction set and mints a different
        ref. That is not a retry - it is a new submission, and it should be a new run.

    A UNIT-B REF NAMES THE DEPARTMENT IN THE SLOT A MODULE WOULD HOLD
    =================================================================

        A unit-B run has no module, so without `department` the third segment would be
        `-` on every department in a venture and two departments operating the same
        module set on one Forge would mint the SAME ref. `open_run` is idempotent on
        the ref, so the second `run_start` would land silently on the first
        department's run, both correlation rows would carry one ref, and P-03's sweep
        would write two certifications - for two different departments - out of one
        verdict.

        That is why this stayed one function rather than becoming a second minter: a
        unit-B ref differs from a unit-A ref in exactly one segment, and two functions
        agreeing on the other four is the same "two spellings of one rule" defect
        `submission_unit` was extracted to prevent.

        `department` is ignored when `module_id` is given. A run is one unit or the
        other and `submission_unit` is what decides; a ref carrying both would be a ref
        that cannot say which.

    Carries no scenario content: two ids, a module or department name and a hash
    prefix. The hash is truncated because the full 64 characters buy nothing a reader
    wants and make the ref unreadable in a log line, where its only job is to be
    recognised.
    """
    target = module_id or (f"dept:{department}" if department else "-")
    return ":".join(("office", venture_id, forge_id, target, content_hash[:12]))


def department_basis_hash(module_hashes: dict[str, str]) -> str:
    """The basis a unit-B run executes against. **A composite, and it says so.**

    `OperationRunStartRequest.instruction_content_hash` is required and
    `curriculum_submission.instruction_content_hash` is NOT NULL, so a unit-B run has
    to name what it was judged against. A department is not a module and has no single
    operating instruction, so there is nothing to look up - the basis is the set of
    instructions the department's modules were actually handed over under, and the only
    honest way to name a set in one column is to hash it.

    WHY THIS IS NOT A `forge_operating_instruction.content_hash`, AND MUST NOT BE READ AS ONE
    =========================================================================================

        A reader who takes this value into
        `certification.forge_api_version_in_force` gets a refusal - "no
        forge_operating_instruction carries content hash ..." - which is correct and is
        the point. It is domain-separated by the `office/unit-b/v1` prefix so it cannot
        collide with a real instruction hash by accident, and
        `certification.recompute_staleness` already exempts unit B from the live-hash
        comparison for this exact reason, in writing: a unit-B cert "carries
        `module_id IS NULL` by design, so there is no single instruction it could be
        compared against."

        The property that makes it useful is the one a single hash has: it changes when
        any of the department's instructions changes, and it does not change when they
        do not. So a re-run of Gate 8 against unchanged instructions mints the same ref
        and lands on the run that is already open, exactly as the unit-A path does.

    An empty mapping raises rather than hashing nothing. A department with no handed
    over module on a Forge has no context to clear, and a hash of the empty set would
    be a stable value that looks like a basis and stands for nothing.
    """
    if not module_hashes:
        raise ValueError(
            "a department basis needs at least one module instruction; a hash of no "
            "instructions is a value that looks like a basis and names nothing"
        )
    material = "\n".join(
        f"{module_id}:{content_hash}"
        for module_id, content_hash in sorted(module_hashes.items())
    )
    return hashlib.sha256(f"office/unit-b/v1\n{material}".encode()).hexdigest()


class SimForgeClient:
    """The only three calls The Office makes to SimForge.

    **They travel two different paths, and that asymmetry is the design.**

    `get_gate_result` is brokered. An agent reads a verdict about its own
    certification, so it goes through `OfficeClient.call` exactly like any other
    Forge module: a grant resolved fresh, a trust tier, a shift, an idempotency
    key, an audit entry before the call and a ledger row after. Nothing here
    modifies that path - this class supplies the module name and narrows the
    answer.

    `submit_curriculum` and `run_start` are not brokered. Both are signed with
    The Office's own tenant credential; the hand-over is audited as
    `curriculum_handed_over`, naming the human who provisioned, and the
    `run_start` that follows it is bookkeeping on that same act rather than a
    second one.

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
    ) -> dict[str, Any]:
        """Hand a curriculum over. Returns the acceptance body, validated.

        **This used to return `run_ref` and raise when it did not get one, and that
        expectation was never true.** The ref was never SimForge's to return: its
        `OperationRunStartRequest` takes `run_ref` as an *input* field, so the caller
        mints it and `run_start` opens the run under it. Nothing on
        `POST /api/operation/curriculum` produces a ref, and P-01 measured ten of ten
        Burkham modules ACCEPTED while this method raised on every one of them.

        So the acceptance body is returned whole instead. What it carries is enumerated
        in the manifest; the one worth naming here is **`module_levels`**, the
        per-module certification level - `certified`,
        `certified_with_declared_absence`, `demonstrated` - which is exactly what the
        certification run needs and what this method was throwing away.

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
                # The body is a `ForgeOperationCurriculum` and is sent verbatim.
                # SimForge's shape wins here: it has a validator behind it, and a
                # summary of a curriculum is not a curriculum - nothing can be
                # certified against a count. `scenario_pack_ref` is the Office's own
                # correlation id and stays on this side, in the audit entry.
                json=payload,
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

        if response.status_code == 422:
            # The one error body worth reading. It is checked the same way a success
            # body is - refusing to look would throw away the violations, and reading
            # it unchecked is the hole the manifest exists to close.
            raise _rejection(response)
        if response.status_code >= 400:
            # Not echoed. An error body that is not a 422 has no declared shape, and
            # an exception message is the one place a leak would travel unvalidated.
            raise SimForgeError(
                f"submit_curriculum returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("submit_curriculum returned a non-JSON body") from exc

        if not isinstance(body, dict):
            raise SimForgeError(
                f"submit_curriculum returned {type(body).__name__}, not an object"
            )
        # Unchanged, and deliberately so: a field the manifest does not name still
        # fails here. The manifest became accurate about what arrives; the check did
        # not become lenient about what may.
        validate_response("submit_curriculum", body)
        if not body.get("accepted"):
            raise SimForgeError(
                f"SimForge refused the curriculum: {body.get('rejected_reason')!r}"
            )
        # No `run_ref` check. There is nothing here to check for - see the docstring.
        # The ref is minted on this side and travels on `run_start`.
        return body

    async def run_start(
        self,
        conn: Any,
        *,
        run_ref: str,
        unit: str,
        forge_id: str,
        instruction_content_hash: str,
        rubric_kind: str = "operation",
        module_id: str | None = None,
        agent_id: str | None = None,
        department_id: str | None = None,
        scenario_count: int = 0,
        coverage_denominator: int = 0,
        window_minutes: int | None = None,
    ) -> dict[str, Any]:
        """Open the `OperationRun` a verdict is later read by. **The caller mints the ref.**

        `broker/forge_modules.py` has declared this module and its reason since the
        adapter was bound - "opens the OperationRun a verdict is later read by,
        bookkeeping between the two systems, on the same footing as the hand-over that
        precedes it" - and nothing has ever called it. Without it SimForge holds no
        record of a run between the curriculum and the gate result, so a battery that
        hangs produces no row, no verdict and no error, and TIMEOUT is unreachable from
        either side.

        WHY THIS TRAVELS THE HAND-OVER'S PATH AND NOT THE BROKERED ONE
        ==============================================================

            Same reason, unchanged: Gate 8 runs during provisioning, the actor is a
            human, and the agents that will hold grants for this venture do not exist
            yet. `forge_modules.NOT_AGENT_FACING` records exactly that for this name.
            So it is signed with the Office's own tenant credential and posted to
            `{base_url}/run_start` - SimForge's Office adapter, the same surface
            `submit_curriculum` already uses, dispatched from the same `MODULES` map
            behind the same tenant-credential check.

            **It is NOT `POST /api/operation/run/start`.** That route exists and is
            behind `require_role("compliance_analyst")` - a *user* role verified from a
            Clerk JWT. The Office holds no user identity in SimForge and has no business
            acquiring one for a machine hand-over. Reaching for that route and then
            reporting an authorization problem would have been a finding about a
            question nobody had to ask.

        WHY THE REF IS DETERMINISTIC AND NOT A FRESH UUID
        =================================================

            SimForge's `open_run` is idempotent on `run_ref` and answers
            `already_open: true` with **the clock untouched**, so that a retried
            hand-over cannot extend the window of a run that is already hanging
            (its ADR-0044). A caller minting a fresh uuid on every attempt defeats
            that control from the outside: two runs, two windows, and the second one
            young. `mint_run_ref` derives the ref from the submission's natural key
            instead - see its docstring.

        Not audited separately. The `curriculum_handed_over` entry written moments
        before names the same act, and the ref itself lands on
        `curriculum_submission.simforge_run_ref`, which is the durable record
        `overdue_submissions` actually reads. A second event for one hand-over would
        make the log say a thing happened twice.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        payload: dict[str, Any] = {
            "run_ref": run_ref,
            "unit": unit,
            "forge_id": forge_id,
            "instruction_content_hash": instruction_content_hash,
            "rubric_kind": rubric_kind,
            "module_id": module_id,
            "agent_id": agent_id,
            "department_id": department_id,
            "scenario_count": scenario_count,
            "coverage_denominator": coverage_denominator,
            "window_minutes": window_minutes,
        }

        url = f"{base_url.rstrip('/')}/run_start"
        try:
            response = await self._http.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL, and
            # this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            # Not echoed, for the reason submit_curriculum does not echo one: an error
            # body has not been through validate_response, and an exception message is
            # the one place a leak would travel unchecked.
            raise SimForgeError(
                f"run_start for {run_ref!r} returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("run_start returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise SimForgeError(
                f"run_start returned {type(body).__name__}, not an object"
            )
        validate_response("run_start", body)
        return body

    async def office_gate_result(self, conn: Any, *, run_ref: str) -> GateResult:
        """Read one verdict as an Office act, for the sweep that polls for it.

        **This is not a second copy of `get_gate_result` and it must not become one.**
        They answer two different questions and the difference is who is asking.

        WHY THE SWEEP CANNOT USE THE BROKERED READ
        ==========================================

            `get_gate_result` goes through `OfficeClient.call`, which resolves a grant
            for `(agent, simforge, gate_result)`, enforces a shift, checks a budget and
            writes a ledger row naming that agent. That is exactly right for the call it
            models - an agent reading the verdict about its own certification - and it
            is unreachable from a background sweep, which has no agent, no shift and no
            task.

            The obvious workaround is refused two hundred lines above, in this class's
            own docstring, and it is refused for this exact shape: "Minting one to
            satisfy the signature is `origin='human'` again ... a name in a ledger row
            for a call it did not make, indistinguishable afterwards from one it did."
            A sweep that invented an agent to read a verdict would put a fabricated
            actor on the record that GRANTS that agent production authority. The whole
            point of polling rather than receiving is that nobody gets to announce their
            own certification; forging the reader would give it back.

            **So the sweep does not pretend to be an agent. It is The Office, and it
            signs as The Office** - the same footing as `submit_curriculum` and
            `run_start`, which are Office acts for the same reason: no agent performs
            them.

        WHY THIS WORKS ON THE RECEIVING SIDE
        ====================================

            Read out of SimForge rather than assumed. Its Office adapter dispatches
            `gate_result` from the same `MODULES` map as `submit_curriculum` and
            `run_start`, `call_module` gates all three on `_require_tenant_credential`,
            and `x_office_agent_id` is an optional header there. There is one surface
            and one credential check; the brokered/unbrokered distinction is entirely
            The Office's own governance and does not exist on the wire.

        WHAT IS NOT WEAKENED
        ====================

            The leak protection is `parse_gate_result`, not the brokered path: it runs
            `validate_response`, which refuses a field the manifest does not name and
            refuses prose anywhere in the body. This read goes through the identical
            function, so a SimForge that started returning scenario content raises here
            exactly as it would there.

            A 404 stays a named refusal rather than an empty verdict, for the reason
            SimForge gives for returning one: a `NOT_RUN` body would have to invent a
            `unit` and a `rubric_version` for a run it never received. The sweep turns
            that refusal into a TIMEOUT only when its own deadline has passed, which is
            a statement about the deadline and not about the run.
        """
        credential = await self._tenant_credential(conn)
        base_url, api_version = await self._registry(conn)

        url = f"{base_url.rstrip('/')}/gate_result"
        try:
            response = await self._http.post(
                url,
                json={"run_ref": run_ref},
                headers={
                    "Authorization": f"Bearer {credential.reveal()}",
                    "X-Office-Forge-Api-Version": api_version,
                    "Content-Type": "application/json",
                },
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            # type(exc).__name__, never str(exc): the message can carry the URL, and
            # this request carried a credential.
            raise SimForgeError(
                f"could not reach SimForge: {type(exc).__name__}"
            ) from exc

        if response.status_code == 404:
            raise SimForgeError(f"SimForge has no record of run_ref {run_ref!r}")
        if response.status_code >= 400:
            # Not echoed. Same rule as the two calls above: an error body has not been
            # through validate_response, and an exception message is the one place a
            # leak would travel unchecked.
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise SimForgeError("gate_result returned a non-JSON body") from exc
        if not isinstance(body, dict):
            raise SimForgeError(
                f"gate_result for {run_ref!r} returned "
                f"{type(body).__name__}, not an object"
            )
        return parse_gate_result(body)

    # ----------------------------------------------------------- internals

    async def _tenant_credential(self, conn: Any) -> Credential:
        """The tenant credential, or a `SimForgeError` naming why there is none.

        **The resolver raises `CredentialUnavailable`, not `SimForgeError`**, and that
        difference escaped this class until CI ran without `SIMFORGE_TOKEN`: Gate 8
        catches `SimForgeError` and records a failed hand-over, so an unresolvable
        credential went straight past it and 503'd the whole provisioning API. A Forge
        that cannot be reached must never stop a provisioning run - that is the entire
        reason the hand-over is non-fatal - and "cannot be reached" includes "we hold no
        credential for it".

        So it is translated here rather than caught at the call site. The ref travels in
        the message and the value never does, which is `CredentialUnavailable`'s own
        rule.
        """
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
        try:
            return await self._resolver.resolve(row[0])
        except CredentialUnavailable as exc:
            raise SimForgeError(
                f"the tenant credential for {self._forge_id!r} did not resolve: {exc}"
            ) from exc

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
        agent_model=body.get("agent_model"),
    )


def _rejection(response: Any) -> SimForgeError:
    """Turn a 422 into a `CurriculumRejectedError` carrying its violations.

    The violations are generated by SimForge's `validate_curriculum_submission` from
    fixed format strings over module ids, scenario indices, class names and never-do
    entries - all of them things The Office authored and sent. None of it is held-out
    content. **That is an argument, not a guarantee**, so the strings go through
    `assert_no_scenario_content` before they are read, and a violation list that trips
    it becomes a plain refusal rather than a message.
    """
    try:
        detail = response.json().get("detail", {})
    except ValueError:
        return SimForgeError("submit_curriculum returned 422 with a non-JSON body")
    violations = detail.get("violations") if isinstance(detail, dict) else None
    if not isinstance(violations, list) or not violations:
        return SimForgeError("submit_curriculum returned 422 naming no violations")
    try:
        assert_no_scenario_content("submit_curriculum", violations)
    except SimForgeError:
        return SimForgeError(
            "submit_curriculum returned 422 whose violations did not pass the "
            "no-scenario-content check; they are not reproduced here"
        )
    return CurriculumRejectedError([str(v) for v in violations])

# ------------------------------------------------------- the timeout that never came

#: How long a submitted curriculum may sit without a result before it is treated as
#: TIMEOUT. Deliberately generous: an operation battery is slow, and resolving a
#: still-running run to `in_training` is harmless (it already is in training) while
#: resolving one too eagerly churns certifications.
DEFAULT_RUN_DEADLINE_HOURS = 24

#: The `rubric_version` a TIMEOUT carries. `certification.rubric_version` is NOT NULL,
#: and a run that never answered was judged against no rubric at all.
#:
#: **Not a version number.** Any plausible semver here - "0.0.0", the last rubric the
#: Forge used - would be a claim that a rubric was applied, sitting in the column a
#: reader consults to find out which one. This says what happened instead, and it sorts
#: nowhere near a real version, so a query that groups by rubric cannot silently fold
#: these rows in with runs that were actually scored.
TIMEOUT_RUBRIC_VERSION = "none: the run did not answer"


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
    # One rule, one place. This function used to spell the A/B and operation/domain
    # derivation inline; `run_start` needs the identical answer, and two copies of it
    # would be two things to keep in step.
    unit, rubric_kind = submission_unit(submission.get("module_id"))
    return GateResult(
        run_ref=submission.get("simforge_run_ref") or f"unanswered:{submission['submission_id']}",
        unit=unit,
        verdict="TIMEOUT",
        rubric_kind=rubric_kind,
        rubric_version=rubric_version,
        score=None,
        threshold=None,
        certified_tier=None,
        # No model, and deliberately not the one that WOULD have answered. A timeout is
        # the absence of an answer; naming a model here would record a candidate that
        # never sat the exam. `simforge_verdict` is TIMEOUT and the state is
        # `in_training`, so the CHECK does not demand one - which is the rule agreeing
        # with the fact rather than being worked around.
        agent_model=None,
        scenario_count=0,
        coverage_denominator=0,
    )


#: The verdicts SimForge has STORED on the run, and will not revise.
#:
#: Read off the receiving side rather than off the verdict vocabulary.
#: `run_registry.gate_result_for` returns `run.verdict` when the run carries one, and
#: otherwise DERIVES the answer from the window - TIMEOUT past it, IN_PROGRESS inside
#: it - "even before the sweep has stamped it: the answer must not depend on how
#: recently a background job ran."
#:
#: So TIMEOUT and IN_PROGRESS are computed answers about a run that is still open, and
#: NOT_RUN is an answer about a run SimForge does not hold. None of the three is final,
#: and a late result replaces all of them: SimForge records a verdict arriving after a
#: TIMEOUT and leaves `timedOutAt` in place, "because a result that ARRIVED is better
#: evidence than a deadline that passed."
#:
#: This is the set `result_received_at` is stamped on, and nothing else. **A stamp on a
#: TIMEOUT would close the submission against the verdict SimForge is still holding
#: open** - The Office would have thrown away better evidence and left a certification
#: at `in_training` forever on a battery that finished five minutes late.
TERMINAL_VERDICTS = frozenset({"PASS", "PROVISIONAL", "FAIL", "REVOKED"})


async def mark_result_received(conn: Any, submission_id: uuid.UUID) -> None:
    """Close one submission: a real verdict was recorded against it.

    `result_received_at` means "a verdict SimForge stands behind was written into a
    certification", NOT "we stopped asking". `overdue_submissions` is the only reader
    and it treats a NULL as "still owed an answer", which is the correct reading of a
    run that timed out and might yet finish.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE curriculum_submission SET result_received_at = now() "
            "WHERE submission_id = %s AND result_received_at IS NULL",
            (submission_id,),
        )
    await conn.commit()


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
