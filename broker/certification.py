"""Certification — two units, seven states, and staleness by comparison.

Part 10.1. Both units are required for assignment:

  Unit A  agent x forge x module    operation competence   operation rubric
  Unit B  department x forge        judgment in context    domain rubric

Department certification is necessary, never sufficient.

**States are never collapsed.** Two mappings matter more than the rest and are the kind
of thing a `verdict == "PASS"` check gets wrong by omission:

  TIMEOUT  -> in_training        never `certified`. A run that did not finish proved
                                 nothing, and treating "we ran out of time" as a pass
                                 is how an uncertified agent reaches a Forge.
  NOT_RUN  -> never_certified    never `failed`. Nothing was attempted; reporting that
                                 as a failure defames an agent and pollutes the metric
                                 that is supposed to show real failures.

**Staleness is a comparison, not a flag.** A cert stores the instruction hash and Forge
api_version it was tested against; freshness is computed against what is live now. That
means nobody has to remember to invalidate anything, which is the only way this stays
true after the sixth Forge is bridged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

#: The verdicts that mean SOMETHING ANSWERED, imported rather than restated.
#: `simforge.TERMINAL_VERDICTS` is the one definition, named by P-03 when it decided
#: which results may stamp `result_received_at`, and migration 0035's CHECK mirrors it.
#: Three spellings of one set is how two of them drift; there are already two, and the
#: SQL one cannot import.
from broker import audit, humans, instructions, simulation
from broker.simforge import TERMINAL_VERDICTS as ANSWERED_VERDICTS
from broker.simforge import department_basis_hash

CERTIFIED = "certified"
PROVISIONAL = "provisional"
STALE_INSTRUCTIONS = "stale_instructions"
STALE_FORGE = "stale_forge"
IN_TRAINING = "in_training"
NEVER_CERTIFIED = "never_certified"
FAILED = "failed"
REVOKED = "revoked"

#: Every state the `certification.state` CHECK constraint admits, in the order a
#: reader needs them: earned, withheld, gone stale, in flight, absent, failed, voided.
#: Migration 0029 is the constraint; this is the same list in Python, and
#: `tests/contract/test_simforge_vocabulary.py` fails if the two disagree.
ALL_STATES = (
    CERTIFIED,
    PROVISIONAL,
    STALE_INSTRUCTIONS,
    STALE_FORGE,
    IN_TRAINING,
    NEVER_CERTIFIED,
    FAILED,
    REVOKED,
)

#: The only state that permits assignment. `resolve_grant` compares against
#: `certified` directly; this exists so the fact is assertable rather than implied
#: by an equality check buried in a query.
ASSIGNABLE_STATES = frozenset({CERTIFIED})

# SimForge verdict -> Office certification state. Explicit rather than derived, so
# adding a verdict is a decision someone makes rather than a default that happens.
#
# PROVISIONAL is SimForge's Rev-2 governance hold: the agent passed the threshold but
# the rubric did not discriminate, or a required never-do dimension went untested. It
# maps to its own state rather than onto one of the others because every candidate is
# wrong in a way that matters - see migration 0029. It is not assignable.
VERDICT_TO_STATE = {
    "PASS": CERTIFIED,
    "PROVISIONAL": PROVISIONAL,
    "FAIL": FAILED,
    "TIMEOUT": IN_TRAINING,
    "NOT_RUN": NEVER_CERTIFIED,
    "IN_PROGRESS": IN_TRAINING,
    "REVOKED": REVOKED,
}

# Ordered weakest to strongest, for capping.
TIER_RANK = {"suggest": 1, "propose": 2, "auto_execute": 3}


class CertificationError(Exception):
    """A certification could not be recorded as asked."""


@dataclass(frozen=True, slots=True)
class CertState:
    cert_id: uuid.UUID | None
    unit: str
    state: str
    certified_tier: str | None

    @property
    def is_certified(self) -> bool:
        return self.state == CERTIFIED


def state_for_verdict(verdict: str) -> str:
    """Map a SimForge verdict to a certification state.

    Unknown verdicts raise rather than defaulting. A default here would silently
    turn an unrecognised SimForge response into whichever state the default was,
    and the safe-looking default (`failed`) is itself wrong for NOT_RUN.
    """
    try:
        return VERDICT_TO_STATE[verdict]
    except KeyError:
        raise CertificationError(
            f"unknown SimForge verdict {verdict!r}; refusing to guess a state. "
            f"Known verdicts: {', '.join(sorted(VERDICT_TO_STATE))}"
        ) from None


def cap_tier(declared: str, certified: str | None) -> str:
    """Certified tier caps declared tier (Part 10.1).

    None means uncertified, which is not a tier at all - the caller must not reach
    here with one, and returning the declared tier would silently un-cap it.
    """
    if certified is None:
        raise CertificationError("cannot cap a tier against an uncertified unit")
    return declared if TIER_RANK[declared] <= TIER_RANK[certified] else certified


def _parse_semver(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise CertificationError(f"not a pinned semver: {version!r}")
    major, minor, patch = (int(p) for p in parts)
    return major, minor, patch


def is_forge_version_stale(
    certified_against: str, current: str, sensitivity: str
) -> bool:
    """Whether a Forge version change invalidates a certification.

    | sensitivity        | 2.1.0 -> 2.1.5 | 2.1.0 -> 2.2.0 | 2.1.0 -> 3.0.0 |
    |--------------------|----------------|----------------|----------------|
    | major              | fresh          | fresh          | stale          |
    | major.minor        | fresh          | stale          | stale          |
    | major.minor.patch  | stale          | stale          | stale          |

    Any change is compared at the declared precision. A *downgrade* is stale too:
    the certification was earned against behaviour that is no longer what the Forge
    does, and which direction it moved is not the point.
    """
    a = _parse_semver(certified_against)
    b = _parse_semver(current)
    depth = {"major": 1, "major.minor": 2, "major.minor.patch": 3}[sensitivity]
    return a[:depth] != b[:depth]


async def forge_api_version_in_force(
    conn: AsyncConnection,
    *,
    forge_id: str,
    module_id: str,
    content_hash: str,
    at: datetime,
) -> str:
    """The `forge_api_version` a certification was actually earned against.

    `record_result` refuses a `certified` row without one and `curriculum_submission`
    does not have the column - it stores `instruction_content_hash` and nothing about
    the Forge's version. So the value has to be recovered from
    `forge_operating_instruction`, and recovering it correctly is not a lookup.

    WHY THE HASH IS NOT ENOUGH ON ITS OWN
    =====================================

        `forge_operating_instruction`'s primary key is
        `(forge_id, module_id, instruction_version)` and its only other unique index is
        `ux_instruction_live ... WHERE superseded_at IS NULL`. **`content_hash` is not
        unique per module.** Republishing an unchanged instruction under a new version
        against a bumped Forge API produces two rows with one hash and two different
        api_versions - which is precisely the case `version_sensitivity` and
        `sensitivity_rationale` exist to describe, so it is expected rather than
        pathological.

        A query keyed on the hash alone therefore has two answers, and taking the first
        would be a certification basis decided by whatever order the planner returned.

    WHY "IN FORCE AT `at`" IS NOT A TIE-BREAK
    =========================================

        It is a reconstruction, not a preference. Gate 8 builds `instruction_set_ref`
        from the LIVE instruction at submit time and puts
        `instruction.forge_api_version` on the wire in the curriculum it hands over
        (`broker/provisioning.py::_curriculum_payload`). So the row in force when the
        submission was made is not the most plausible of two candidates - it is the one
        whose api_version SimForge was told about and judged against.

        `at` is the submission's `submitted_at` for that reason, and passing anything
        else here answers a different question.

    Refuses rather than guesses in both directions: no row carrying that hash, and more
    than one in force at that moment. A certification whose basis has two answers has no
    basis, and one supplied to satisfy the guard is the permanent-by-accident row the
    guard exists to prevent.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT instruction_version, forge_api_version, authored_at, superseded_at
            FROM forge_operating_instruction
            WHERE forge_id = %s AND module_id = %s AND content_hash = %s
            ORDER BY authored_at, instruction_version
            """,
            (forge_id, module_id, content_hash),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        raise CertificationError(
            f"no forge_operating_instruction for {forge_id}/{module_id} carries "
            f"content hash {content_hash[:12]}...; the Forge api_version this run was "
            "judged against cannot be recovered, and supplying one would make the "
            "certification's basis a guess"
        )

    in_force = [
        r for r in rows
        if r["authored_at"] <= at
        and (r["superseded_at"] is None or r["superseded_at"] > at)
    ]
    if len(in_force) != 1:
        versions = sorted(
            f"{r['instruction_version']}@{r['forge_api_version']}" for r in rows
        )
        raise CertificationError(
            f"{len(in_force)} instruction version(s) for {forge_id}/{module_id} carry "
            f"content hash {content_hash[:12]}... and were in force at "
            f"{at.isoformat()}; candidates were {versions}. A certification basis with "
            f"{'no' if not in_force else 'two'} answers is not a basis"
        )
    return str(in_force[0]["forge_api_version"])



async def department_api_version(
    conn: AsyncConnection,
    *,
    submission_id: uuid.UUID,
    forge_id: str,
    at: datetime,
) -> str:
    """The `forge_api_version` a DEPARTMENT certification was earned against.

    The unit-B counterpart to `forge_api_version_in_force`, and it is a different
    question rather than the same one with a NULL module. A department is not a module:
    it has no single operating instruction, so its basis is the SET of instructions its
    modules were handed over under, and `simforge.department_basis_hash` names that set
    in one column by hashing it. That composite is one-way, which is why
    `curriculum_submission_module` exists - the members are stored because they cannot
    be recovered from the hash (B36 half two).

    THE RULE: AGREE AND IT RECORDS, DISAGREE AND IT REFUSES
    =======================================================

        Each member resolves through `forge_api_version_in_force` on its OWN content
        hash, which is the same reconstruction unit A does - the row in force at
        `submitted_at`, the one whose api_version SimForge was told about. One distinct
        value across the members is the answer. More than one is a refusal.

        **Not `max()`, and not the first row.** There is no single version a department
        was judged against when its modules disagree; a certification basis with two
        answers is not a basis, and picking one makes it a basis decided by whatever
        order the planner returned. That is the argument `forge_api_version_in_force`
        already makes one level down, applied to the set.

        Four Forges each carry exactly one live `forge_api_version` today. **That is a
        fact about four Forges on one day, not a property of the schema** -
        `forge_api_version` is NOT NULL per `(forge_id, module_id, instruction_version)`
        row and nothing constrains two modules of one department to agree. A rule that
        is only correct while the data happens to be uniform is not a rule.

    WHY NOT `forge_registry.api_version`
    ====================================

        It is available and it is honest about being weaker: the version live NOW,
        which is not the version anything was judged against. It would make a
        certification's basis a fact about today rather than about the run - the exact
        staleness `certified_records_its_basis` exists to prevent. If it is ever chosen
        the certification should say that is what it means; this does not choose it.

    Refuses on an empty member set as well. A unit-B submission with no members is one
    whose basis was never recorded, and answering for it would be inventing the set.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT module_id, instruction_content_hash "
            "FROM curriculum_submission_module WHERE submission_id = %s "
            "ORDER BY module_id",
            (submission_id,),
        )
        members = [dict(r) for r in await cur.fetchall()]

    if not members:
        raise CertificationError(
            f"submission {submission_id} records no member modules, so the department's "
            "basis cannot be recovered; the composite hash does not name what it was "
            "composed of (see blocking.md B36)"
        )

    by_version: dict[str, list[str]] = {}
    for member in members:
        # Per member, on its own hash. A failure here is a member whose instruction
        # cannot be reconstructed, and it propagates unchanged: the caller already
        # treats `CertificationError` as "basis unrecoverable", and rewording it would
        # hide which of the two ambiguities was hit.
        version = await forge_api_version_in_force(
            conn,
            forge_id=forge_id,
            module_id=str(member["module_id"]),
            content_hash=str(member["instruction_content_hash"]),
            at=at,
        )
        by_version.setdefault(version, []).append(str(member["module_id"]))

    if len(by_version) != 1:
        detail = "; ".join(
            f"{version}: {', '.join(mods)}" for version, mods in sorted(by_version.items())
        )
        raise CertificationError(
            f"the {len(members)} module(s) of this department on {forge_id} were judged "
            f"against {len(by_version)} different Forge api_versions - {detail}. The set "
            "IS the basis, so there is no single version this department was certified "
            "against, and choosing one would make the basis an artefact of query order"
        )

    return next(iter(by_version))

def _model_scalars(
    identity: dict[str, Any] | None,
) -> tuple[str | None, float | None, int | None]:
    """The three the ruling names, lifted out of SimForge's record.

    **Promoted, not extracted.** The whole record is stored too, in `model_identity`.
    These three are lifted into their own columns because a CHECK can demand a column
    and cannot demand a key inside a jsonb without asserting a shape The Office does not
    own - `revocation.blast_radius` keeps the whole thing for the same reason and the
    same trade.

    Reads defensively because the shape is SimForge's. A record that arrives without
    `settings`, or with `max_tokens` spelled some other way, yields `None` and the
    caller refuses with a sentence naming what is missing - which is a better failure
    than a `KeyError` from inside a database write.
    """
    if not isinstance(identity, dict):
        return None, None, None
    digest = identity.get("file_digest")
    settings = identity.get("settings")
    if not isinstance(settings, dict):
        settings = {}
    temperature = settings.get("temperature")
    max_tokens = settings.get("max_tokens")
    return (
        str(digest) if digest else None,
        float(temperature) if isinstance(temperature, int | float) else None,
        int(max_tokens) if isinstance(max_tokens, int) else None,
    )


async def record_result(
    conn: AsyncConnection,
    *,
    unit: str,
    forge_id: str,
    verdict: str,
    rubric_version: str,
    office_agent_id: uuid.UUID | None = None,
    module_id: str | None = None,
    department: str | None = None,
    certified_tier: str | None = None,
    instruction_content_hash: str | None = None,
    forge_api_version: str | None = None,
    score: float | None = None,
    threshold: float | None = None,
    scenario_pack_ref: str | None = None,
    agent_model: str | None = None,
    model_identity: dict[str, Any] | None = None,
    attested_by: str = "simforge",
    bootstrap_reason: str | None = None,
    attestation_ref: uuid.UUID | None = None,
    verdict_evidence: dict[str, Any] | None = None,
) -> CertState:
    """Record a SimForge verdict as a certification state.

    Upserts on the unit's natural key, so a re-certification replaces the prior
    verdict rather than accumulating rows that a reader would have to order
    correctly to interpret.

    `attested_by="bootstrap"` records a certification NO SIMFORGE RUN PRODUCED.

    Until 3 September 2026 that was not expressible: `verdict` was written
    straight into `simforge_verdict`, so a bootstrap had to claim SimForge passed
    it. Both Phase 0.8 grants carried `simforge_verdict = 'PASS'` against no
    scenario run at all - a false statement in the one column that exists to say
    whether SimForge ran, which is the column a reader trusts most.

    A bootstrap now writes `simforge_verdict = NULL` and must give a reason. That
    makes the query structural rather than a naming convention:

        SELECT * FROM certification WHERE simforge_verdict IS NULL

    is every certification nobody earned, and it cannot be defeated by choosing a
    different `rubric_version`. `state` is still derived from `verdict`, because a
    bootstrap that could not say whether it was granting or withholding would be
    unreadable - what changes is that the row no longer claims SimForge said so.
    """
    if attested_by not in ("simforge", "bootstrap"):
        raise CertificationError(
            f"attested_by must be 'simforge' or 'bootstrap', not {attested_by!r}"
        )
    if attested_by == "bootstrap" and not bootstrap_reason:
        raise CertificationError(
            "a bootstrap certification must say why it exists. It is a grant issued "
            "against no scenario run, and the reason is the only thing a later reader "
            "has to judge whether it should still be standing."
        )
    if attested_by == "simforge" and bootstrap_reason:
        raise CertificationError(
            "bootstrap_reason is meaningless on a real SimForge verdict"
        )

    state = state_for_verdict(verdict)
    rubric_kind = "operation" if unit == "A" else "domain"

    # A real verdict names the model that produced it. Mirrors migration 0035's
    # `certified_records_its_basis`, in code, so the refusal says WHICH fact is missing -
    # a CHECK violation says only that the row was rejected, and a caller reading that
    # cannot tell a missing model from a missing hash.
    #
    # Keyed on the VERDICT rather than on the state, and on a verdict that means
    # something answered rather than on any verdict at all. TIMEOUT and IN_PROGRESS are
    # computed by SimForge about an open run, so a row carrying one records that nothing
    # answered and has no model to name - the first draft of this guard demanded one and
    # a test caught it.
    #
    # The other half of the distinction:
    # `attested_by='bootstrap'` is a grant issued against no scenario run, so it has no
    # model, and demanding one would make it invent a candidate that never sat the exam.
    # `simforge_verdict IS NOT NULL` is the structural expression of "a battery ran" -
    # B34 records that `attested_by` is a parameter and not a column, so this is the only
    # spelling the row itself can carry.
    if (
        attested_by == "simforge"
        and verdict in ANSWERED_VERDICTS
        and not (agent_model or "").strip()
    ):
        raise CertificationError(
            "a SimForge verdict must name the model that earned it - "
            "`provider/model`, e.g. `ollama/llama3.1:8b`. `certified_records_its_basis` "
            "already demands the instruction hash, the Forge api_version and the tier, "
            "all of which describe the EXAM. The model is what answered it, and a "
            "certification that cannot name the candidate is one nobody can reproduce "
            "or expire when the model moves. See blocking.md B34."
        )

    # THE LABEL IS NOT THE MODEL. Ruled 17 September 2026.
    #
    # `agent_model` above is `ollama/llama3.1:8b`, and it reads identically whether the
    # tag was re-pulled at a different quantization or served at a different
    # temperature. The check above has been satisfied by a string that cannot answer
    # "is this still the model the agent runs" since the day it was written.
    #
    # Raised here as well as enforced by `certification_names_its_model` in 0044,
    # because a CHECK violation names a constraint and this names the fact. The
    # constraint is the control; this is the sentence the person reads.
    # SCOPED TO THE VERDICTS THAT CONFER AUTHORITY, and that is the ruling's own
    # wording: "the model the agent PASSED on". `certified` and `provisional` are the
    # two states an agent can act under, and they are the two that have to be
    # withdrawable when the model moves.
    #
    # A FAIL is deliberately NOT asked. It records that an agent was tested and did not
    # pass - a claim that cannot go stale, so there is nothing to expire - and
    # `record_result` already treats it that way for the Forge api_version, whose
    # docstring says a FAIL "needs no basis". Demanding the digest here would make an
    # older SimForge's failure REFUSED RATHER THAN RECORDED, which loses the finding
    # entirely. Losing a pass is safe; losing a failure is not.
    # AN ATTESTED UNIT B NAMES NO MODEL EITHER, and for the bootstrap's reason rather
    # than a new one: no battery ran, so nothing answered. SimForge returns the PASS
    # because The Office posted the outcome, and `basis` is what tells a reader that -
    # entry 147. The CHECK in 0050 carries the same exemption.
    digest, temperature, max_tokens = _model_scalars(model_identity)
    if attested_by == "simforge" and attestation_ref is None and (
        state in (CERTIFIED, PROVISIONAL)
    ) and (
        not digest or temperature is None or max_tokens is None
    ):
        missing = [
            name for name, value in (
                ("file_digest", digest),
                ("settings.temperature", temperature),
                ("settings.max_tokens", max_tokens),
            ) if value is None or value == ""
        ]
        raise CertificationError(
            f"a SimForge verdict must record the model it was earned on, and this one "
            f"is missing {', '.join(missing)}. `agent_model` is a LABEL: the same tag "
            "re-pulled at a different quantization, or served at a different "
            "temperature, produces the identical string and a different candidate. The "
            "digest and the generation settings are what make a certification "
            "attributable to one model file, and without them re-certification on "
            "drift cannot be enforced. SimForge sends them as `model_identity` "
            "(ADR-0060)."
        )

    if state == CERTIFIED and not (
        instruction_content_hash and forge_api_version and certified_tier
    ):
        raise CertificationError(
            "a certified result must record the instruction hash, Forge api_version "
            "and certified tier it was earned against; otherwise staleness is "
            "uncomputable and the certification is permanent by accident"
        )

    # A provisional hold ran against a specific text and a specific Forge version, so
    # its staleness is computable and must stay so - a hold that outlives the
    # instructions it was measured against is a hold nobody can resolve or clear.
    #
    # No `certified_tier` is required: certification was WITHHELD, so there is no
    # certified tier, and demanding one here would invite a placeholder that a later
    # reader takes for a real cap.
    if state == PROVISIONAL and not (instruction_content_hash and forge_api_version):
        raise CertificationError(
            "a provisional result must record the instruction hash and Forge "
            "api_version its battery ran against; a hold whose basis is unknown "
            "cannot be recomputed and cannot be cleared"
        )

    conflict = (
        "(office_agent_id, forge_id, module_id) WHERE unit = 'A'"
        if unit == "A"
        else "(department, forge_id) WHERE unit = 'B'"
    )

    # ================================================================ entry 183
    #
    # A TIMEOUT REPLACES NOTHING.
    #
    # Ruled 23 September 2026: *"A TIMEOUT replaces nothing. It is the absence of an
    # answer, not an answer. Ingest records it without overwriting a certification's
    # basis, state or references. A PASS or FAIL still supersedes, per entry 167."*
    #
    # WHAT IT DID. `verdict_ingest` synthesises a TIMEOUT for a submission past The
    # Office's own deadline, and the upsert below replaced everything: `basis`, `state`,
    # `scenario_pack_ref`, `simulation_ref`, `certified_tier`. Measured 23 September:
    # three unit-B TIMEOUTs from run `d59650aa`, blocked at Gate 9 and never advancing,
    # erased two simulation certifications within three minutes of a named human writing
    # them - and had been doing it every three minutes since the run blocked.
    #
    # WHY THE UPSERT WAS RIGHT AND STILL IS, FOR EVERY OTHER VERDICT. Entry 167 settled
    # it: *"a re-certification is a new answer to the same question, and the basis of the
    # new answer is the new basis."* A PASS or a FAIL is an answer and supersedes
    # whatever stood before it, simulation basis included.
    #
    # A TIMEOUT is not an answer. It is this sweep saying nobody replied - and this sweep
    # already knows that about itself: it refuses to stamp the submission on a TIMEOUT
    # ("a stamp on a TIMEOUT would close the..."), and entry 142's staleness check
    # refuses a TIMEOUT because *"a submission set from withdrawn text has nothing to say
    # about an agent - not even that it did not answer."* The same sentence applies to
    # the certification, one table over.
    #
    # BOTH UNITS. The ruling names a certification, not a unit, and the argument does not
    # change: a `certified` agent whose re-exam timed out has not been shown to have got
    # worse. `recompute_staleness` is what moves a certification the instructions have
    # outrun, and it is not this.
    #
    # A FIRST CERTIFICATION IS STILL WRITTEN. A department or agent with no row at all,
    # whose run timed out, IS `in_training` - there is nothing to preserve and the row
    # says the honest thing. This guard is about replacement, not about recording.
    if verdict == "TIMEOUT":
        # The same natural key the upsert conflicts on, so this asks about exactly the
        # row the INSERT below would have replaced.
        if unit == "A":
            target = "office_agent_id = %s AND module_id = %s"
            params: tuple[Any, ...] = (unit, forge_id, office_agent_id, module_id)
        else:
            target = "department = %s"
            params = (unit, forge_id, department)
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                # `basis` is deliberately not read: the guard preserves every standing
# row alike, and a branch on it would be a second rule.
                "SELECT cert_id, unit, state, certified_tier "
                "  FROM certification "
                f" WHERE unit = %s AND forge_id = %s AND {target}",
                params,
            )
            standing = await cur.fetchone()
        if standing is not None:
            # Nothing is written. The submission stays open - the sweep does not stamp
            # it on a TIMEOUT - so the question is still being asked, and the answer,
            # when it comes, supersedes through the path below.
            return CertState(
                standing["cert_id"], standing["unit"], standing["state"],
                standing["certified_tier"],
            )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            INSERT INTO certification
              (cert_id, unit, office_agent_id, department, forge_id, module_id,
               state, certified_tier, instruction_content_hash, forge_api_version,
               rubric_kind, rubric_version, score, threshold, scenario_pack_ref, agent_model,
               simforge_verdict, model_digest, model_temperature, model_max_tokens,
               model_identity, model_fingerprint, basis, attestation_ref,
               verdict_evidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT {conflict} DO UPDATE SET
              state = EXCLUDED.state,
              certified_tier = EXCLUDED.certified_tier,
              instruction_content_hash = EXCLUDED.instruction_content_hash,
              forge_api_version = EXCLUDED.forge_api_version,
              rubric_version = EXCLUDED.rubric_version,
              score = EXCLUDED.score,
              threshold = EXCLUDED.threshold,
              scenario_pack_ref = EXCLUDED.scenario_pack_ref,
              agent_model = EXCLUDED.agent_model,
              simforge_verdict = EXCLUDED.simforge_verdict,
              -- Replaced, not merged. A re-certification is a new exam on whatever
              -- model answered it, and keeping the previous digest beside the new
              -- verdict would describe a run that never happened.
              model_digest = EXCLUDED.model_digest,
              model_temperature = EXCLUDED.model_temperature,
              model_max_tokens = EXCLUDED.model_max_tokens,
              model_identity = EXCLUDED.model_identity,
              model_fingerprint = EXCLUDED.model_fingerprint,
              -- REPLACED, like everything else here. A re-certification is a new
              -- answer to the same question, and the basis of the new answer is the
              -- new basis: a department that earns a tested PASS stops being attested,
              -- and one whose test is withdrawn stops claiming it was tested.
              basis = EXCLUDED.basis,
              attestation_ref = EXCLUDED.attestation_ref,
              -- AND THE DECLARATION GOES WITH THE BASIS. Entry 167.
              --
              -- Without this line a tested PASS landing on a department that holds a
              -- simulation certification writes `basis = 'tested'` over a row whose
              -- `simulation_ref` survives, and
              -- `a_simulation_certification_names_its_declaration` refuses the whole
              -- statement. The constraint was right and the omission was mine: it
              -- meant **a simulation certification blocked a real one from ever
              -- landing**, and the verdict-ingest sweep would have died on a
              -- CheckViolation rather than recording the PASS.
              --
              -- Replaced, not cleared: `EXCLUDED.simulation_ref` is NULL for every
              -- caller of this function, because nothing that earns a certification
              -- passes a declaration. Spelling it as a replacement keeps it true if one
              -- ever does.
              simulation_ref = EXCLUDED.simulation_ref,
              -- REPLACED WITH THE VERDICT IT EXPLAINS. Entry 173: a
              -- re-certification is a new exam, and evidence from the previous
              -- sitting beside a new verdict would describe a battery that did
              -- not produce it. Same rule the model digest follows two fields up.
              verdict_evidence = EXCLUDED.verdict_evidence,
              updated_at = now()
            RETURNING cert_id, unit, state, certified_tier
            """,
            (
                uuid.uuid4(), unit, office_agent_id, department, forge_id, module_id,
                state, certified_tier, instruction_content_hash, forge_api_version,
                rubric_kind, rubric_version, score, threshold,
                # The reason travels in scenario_pack_ref, which is where a reader
                # looks for what the verdict was earned against. On a bootstrap
                # there is no pack, and saying so is more use than a null.
                (
                    f"NO SCENARIO RUN - {bootstrap_reason}"
                    if attested_by == "bootstrap"
                    else scenario_pack_ref
                ),
                # NULL on a bootstrap, for the same reason `simforge_verdict` is: no
                # battery ran, so no model answered. Recording one here would name a
                # candidate that never sat the exam.
                None if attested_by == "bootstrap" else agent_model,
                # NULL on a bootstrap. See the docstring: this column means
                # SimForge said so, and nothing else may write into it.
                None if attested_by == "bootstrap" else verdict,
                # The model, same rule as `agent_model` above: a bootstrap records no
                # model because none answered. The guard higher up has already refused
                # a simforge verdict missing any of the three.
                # NULL on a bootstrap AND on an attestation: neither had a model
                # answer it. The `basis` column says which of the two this is.
                None if attested_by == "bootstrap" or attestation_ref else digest,
                None if attested_by == "bootstrap" or attestation_ref else temperature,
                None if attested_by == "bootstrap" or attestation_ref else max_tokens,
                # Stored whole beside the promoted three, so a field SimForge adds
                # later is on the row rather than discarded on the way in.
                (
                    Jsonb(model_identity)
                    if attested_by != "bootstrap"
                    and attestation_ref is None
                    and model_identity is not None
                    else None
                ),
                None if attested_by == "bootstrap" or attestation_ref
                else (model_identity or {}).get("fingerprint"),
                # THE BASIS, AND IT IS DERIVED HERE RATHER THAN TAKEN FROM A CALLER.
                # Ruled 21 September 2026, entry 147: a reader can always tell an
                # attested certification from a tested one.
                #
                # `attestation_ref` is the fact and `basis` is its name - one argument,
                # not two that can disagree. A caller that could pass `basis='attested'`
                # with no ref, or a ref with `basis='tested'`, would be two ways to say
                # one thing and the CHECK in 0050 would be the only thing keeping them
                # in step.
                (
                    "bootstrap" if attested_by == "bootstrap"
                    else "attested" if attestation_ref is not None
                    else "tested"
                ),
                attestation_ref,
                # Entry 173. NULL when nobody asked, which is a different fact
                # from an empty record: `parse_battery_result` returns None when
                # SimForge has no battery, and storing `{}` would claim it was
                # inspected and found silent.
                Jsonb(verdict_evidence) if verdict_evidence is not None else None,
            ),
        )
        row = await cur.fetchone()
    assert row is not None

    # ENTRY 181. The reference follows the certification, on every Unit B write and not
    # only the simulation one - a tested department certification lands through this
    # function and has the same defect. Unit A is untouched: `operation_cert_ref` is
    # keyed per (agent, forge, module) and is a separate question, named in the entry.
    #
    # BEFORE THE COMMIT, so the certification and the references it is read through land
    # in one transaction. A certification that exists while the grants still name the
    # row it replaced is precisely the state this closes.
    #
    # NO EVENT OF ITS OWN HERE, and that is a decision rather than an omission.
    # `write_event` requires an `actor_id`, and every `actor_type="system"` entry in
    # this repository names the real subject it acted on. This write has no subject to
    # name - it follows a certification whose own act is already audited by whoever
    # asked for it, and the verdict sweep records the ingest that caused it.
    #
    # Inventing an actor to satisfy a column would put a fiction in the ledger for a
    # consequence, which is the shape entries 148 and 162 both refuse. The effect is
    # readable where it lands: on the grant rows, against the certification they name.
    #
    # `certify_for_simulation` DOES record the count, because that act has an event of
    # its own and a named human behind it.
    if unit == "B" and department:
        await repoint_department_grants(
            conn, department=department, forge_id=forge_id, cert_id=row["cert_id"]
        )
    await conn.commit()
    return CertState(row["cert_id"], row["unit"], row["state"], row["certified_tier"])


async def repoint_department_grants(
    conn: AsyncConnection, *, department: str, forge_id: str, cert_id: uuid.UUID
) -> int:
    """Point every live grant in this department and Forge at the certification in force.

    RULED 23 SEPTEMBER 2026 (decisions entry 181)
    =============================================

        *"A grant's department certification reference points at the certification in
        force. Issuing a Unit B certification re-points every grant in that department
        and Forge."*

    WHAT IT WAS, AND WHY IT LOOKED FINE
    ===================================

        `dept_context_cert_ref` is written once, when the grant is issued, and nothing
        ever moved it. Gate 9 reads the Unit B certification THROUGH that column -
        `ON cb.cert_id::text = g.dept_context_cert_ref` - so a certification the column
        does not name is a certification the gate cannot see.

        It survived because both writers upsert on `(department, forge_id) WHERE
        unit = 'B'`, and an upsert that hits an existing row keeps its `cert_id`. So the
        reference stayed correct **by coincidence**, for as long as a department never
        got its first certification after its grants were issued.

        Measured 23 September 2026: `operations` (4 grants) and `research` (2) resolve
        only because of that coincidence. `engineering` has SIX live grants across three
        Forges whose refs name `cert_id`s no row holds - and certifying engineering would
        write a perfectly valid certification that Gate 9 would still read as
        `never_certified`.

    EVERY LIVE GRANT, AND THE KEY IS THE CERTIFICATION'S OWN
    ========================================================

        A Unit B certification is unique on `(department, forge_id)` - `ux_cert_unit_b`,
        no venture - so one department on one Forge has exactly one, and every grant in
        that department on that Forge is about it. The update takes the same key rather
        than a narrower one; scoping by venture here would leave a grant in a second
        venture pointing at a row that is no longer in force.

        **Live grants only.** A superseded grant confers nothing and its reference is
        part of what was true when it was retired. Rewriting it would edit the record.

        **A revoked grant IS re-pointed.** Revocation is a separate table and does not
        touch this column; the reference should be true whether or not the authority is
        currently withheld, and `covered_grants` is what withholds it.

    IDEMPOTENT, AND SILENT WHEN THERE IS NOTHING TO DO. `IS DISTINCT FROM` means a
    re-certification that keeps its `cert_id` updates no rows and returns 0, so the
    count a caller records is the number of references that actually moved.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE agent_forge_grant g
               SET dept_context_cert_ref = %s
              FROM office_agent_identity i
             WHERE i.office_agent_id = g.office_agent_id
               AND i.department = %s
               AND g.forge_id = %s
               AND g.superseded_at IS NULL
               AND g.dept_context_cert_ref IS DISTINCT FROM %s
            """,
            (str(cert_id), department, forge_id, str(cert_id)),
        )
        return cur.rowcount


#: The fourth basis. Ruled 22 September 2026, entry 167.
SIMULATION_BASIS = "simulation"

#: The tier a simulation certification carries.
#:
#: The floor, and it is a floor rather than a judgement: nothing sat an exam, so nothing
#: established that this department's agents may do more than suggest. `certified_tier`
#: is NOT NULL on any certified row (`certified_records_its_basis`, 0050), so the column
#: has to say something, and the most restrictive value is the only thing it can say
#: honestly.
#:
#: Unit B's tier is not what caps a call - `resolve_grant` reads unit A's. This is the
#: value a reader sees when they ask what a simulation certification claims, and the
#: answer is: the least it could.
SIMULATION_TIER = "suggest"

#: Whether a certification is simulation-only, and whether that permission still stands.
#:
#: **Derived by join, never stored.** *"Every simulation certification is void at that
#: point"* - the point being the moment its venture leaves simulation. A `voided_at`
#: column would mean a row reading valid until somebody remembered to run a job, which
#: is entry 158's argument about overdue escalations applied to a stronger claim.
#:
#: Written as a fragment rather than a view because every caller already joins
#: `certification` under its own alias, and a view would be a second place for the rule
#: to live. `{cert}` is that alias.
SIMULATION_STANDING_SQL = """
    ({cert}.basis = 'simulation')                                AS simulation_only,
    ({cert}.basis = 'simulation' AND {sim}.left_at IS NOT NULL)   AS simulation_void
"""

SIMULATION_JOIN_SQL = (
    "LEFT JOIN venture_simulation {sim} "
    "       ON {sim}.simulation_id = {cert}.simulation_ref"
)

#: **Certified, and the permission behind it still stands.** Entry 167.
#:
#: The predicate every reader that asks "is this certification good" must use, as a
#: correlated EXISTS so it needs no join and can be dropped into a WHERE clause anywhere.
#:
#: WHY THIS IS A SHARED CONSTANT AND NOT FIVE COPIES OF AN `AND`
#: ============================================================
#:
#:     Because five copies is what it was, and two of them were missing. The first cut
#:     of entry 167 put the void check in Gate 9 and in `resolve_grant` and stopped
#:     there, which left **Gate 11 activating production grants on a void simulation
#:     certification** - the gate whose own comment says it re-checks rather than
#:     trusting Gate 9, "the same rule at the moment it becomes irreversible".
#:
#:     A void certification still reads `state = 'certified'`, because nothing in this
#:     system rewrites a certification. That is the right design and it is exactly why
#:     `state = 'certified'` is not a safe thing for a reader to write on its own.
#:
#: `{cert}` is the certification's alias in the caller's query.
CERTIFIED_AND_LIVE_SQL = """
    {cert}.state = 'certified'
    AND NOT EXISTS (
      SELECT 1 FROM venture_simulation vs_live
       WHERE vs_live.simulation_id = {cert}.simulation_ref
         AND vs_live.left_at IS NOT NULL
    )
"""


def certified_and_live(cert: str) -> str:
    """`CERTIFIED_AND_LIVE_SQL` for a certification aliased as `cert`."""
    return CERTIFIED_AND_LIVE_SQL.format(cert=cert).strip()


def simulation_columns(cert: str, sim: str) -> str:
    """The two standing columns for a certification joined under `cert`."""
    return SIMULATION_STANDING_SQL.format(cert=cert, sim=sim).strip()


def simulation_join(cert: str, sim: str) -> str:
    """The join those columns need."""
    return SIMULATION_JOIN_SQL.format(cert=cert, sim=sim)


async def certify_for_simulation(
    conn: AsyncConnection,
    *,
    venture_id: str,
    department: str,
    forge_id: str,
    human: humans.Human,
    reason: str,
) -> CertState:
    """Certify a department's context for simulation, on the strength of a declaration.

    RULED 22 SEPTEMBER 2026 (decisions entry 167)
    =============================================

        *"A department may be certified for simulation. A distinct Unit B basis, never
        'verified', recorded with the declaration that permitted it. Gate 9 accepts it
        while the venture is in simulation and refuses it the moment the venture leaves,
        and every simulation certification is void at that point."*

    THE DEAD END THIS OPENS
    =======================

        Unit B reaches a certification two ways and entry 166 shut both. `tested` needs
        SimForge's `department_context` unit, which `submit_curriculum` reads nothing
        for - Greenstone's three department units have sat at IN_PROGRESS since anybody
        started watching. `attested` needs `passed = escalation AND coupling`, and 166
        refuses a TRUE coupling in simulation by construction.

        Measured 22 September 2026: three bootstrap Unit B rows serving 45 grants, three
        tested rows at IN_PROGRESS, **zero attested, ever**.

    WHAT IT IS NOT
    ==============

        It is not an attestation and it does not become one. `basis = 'simulation'` is
        its own value, `attestation_ref` stays NULL, and migration 0059 refuses a
        verdict, a model or a score on the row because nothing sat an exam.

        Nobody is recorded as having verified anything. `reason` says why the
        certification was issued; it is not a finding about the department.

    WHY IT STILL BINDS TO THE INSTRUCTIONS
    ======================================

        `instruction_content_hash` is `department_basis_hash` over the live instruction
        hash of every module the department holds on this Forge - the same composite
        Gate 8 submits. So a simulation certification has the one property that makes a
        certification worth anything: **it changes when the instructions change.**
        Republishing decertifies, exactly as it does for a tested one.

        Without it this would be a certification of nothing in particular, valid across
        any rewrite of the very instructions the department operates under.

    WHO
    ===

        `ivan`. The same founder authority that declares simulation, because this rests
        entirely on that declaration - and requiring a lesser role would let somebody
        who could not declare simulation spend the permission it grants.
    """
    if not reason.strip():
        raise CertificationError(
            "a simulation certification gives a reason. It is what a reader finds when "
            "they ask why this department reads certified with no exam behind it."
        )

    humans.authorize(human, required_role="ivan", venture_id=None)
    humans.assert_named_human(human, act="certify a department for simulation")

    declaration = await simulation.current(conn, venture_id)
    if declaration is None:
        raise CertificationError(
            f"{venture_id} is not in simulation, so nothing permits a simulation "
            "certification. RULED 22 SEPTEMBER 2026, entry 167: the basis is recorded "
            "WITH the declaration that permitted it, and there is no declaration to "
            "record. Declare simulation first, or earn the Unit B certification."
        )

    modules = await _department_modules(
        conn, venture_id=venture_id, department=department, forge_id=forge_id
    )
    if not modules:
        raise CertificationError(
            f"no module of {department!r} is granted on {forge_id} for {venture_id}, so "
            "there is no instruction set this certification could be bound to. A "
            "certification over the empty set is a stable value that stands for nothing."
        )

    hashes: dict[str, str] = {}
    for module_id in modules:
        current = await instructions.live(conn, forge_id=forge_id, module_id=module_id)
        if current is None:
            raise CertificationError(
                f"{forge_id}/{module_id} has no Forge Operating Instruction in force, "
                "so the department's basis cannot be composed. Gate 6 blocks on this "
                "for the same reason."
            )
        hashes[module_id] = current.content_hash

    basis_hash = department_basis_hash(hashes)
    api_version = await _forge_api_version(conn, forge_id)

    cert_id = uuid.uuid4()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO certification
              (cert_id, unit, rubric_kind, forge_id, department, state,
               certified_tier, instruction_content_hash, forge_api_version,
               rubric_version, scenario_pack_ref, basis, simulation_ref, issued_at)
            VALUES (%s, 'B', 'domain', %s, %s, 'certified', %s, %s, %s,
                    %s, %s, 'simulation', %s, now())
            ON CONFLICT (department, forge_id) WHERE unit = 'B'
            DO UPDATE SET
                state = EXCLUDED.state,
                certified_tier = EXCLUDED.certified_tier,
                instruction_content_hash = EXCLUDED.instruction_content_hash,
                forge_api_version = EXCLUDED.forge_api_version,
                scenario_pack_ref = EXCLUDED.scenario_pack_ref,
                basis = EXCLUDED.basis,
                simulation_ref = EXCLUDED.simulation_ref,
                attestation_ref = NULL,
                simforge_verdict = NULL,
                agent_model = NULL,
                model_digest = NULL,
                score = NULL,
                issued_at = now(),
                updated_at = now()
            RETURNING cert_id, unit, state, certified_tier
            """,
            (
                cert_id, forge_id, department, SIMULATION_TIER, basis_hash,
                api_version,
                # The rubric nothing ran under, named as that rather than left NULL.
                f"office/simulation/{declaration.simulation_id}",
                # THE REASON GOES WHERE A BOOTSTRAP'S GOES. `record_result` writes
                # `NO SCENARIO RUN - <reason>` into `scenario_pack_ref` for a bootstrap,
                # and the same column answers the same question here: what stands where
                # a scenario pack would be. A new column would be a second place a
                # reader has to know to look.
                f"NO EXAM - simulation: {reason.strip()}",
                declaration.simulation_id,
            ),
        )
        row = await cur.fetchone()
    assert row is not None

    # ENTRY 181, and this is the call that produced the ruling. `engineering` has no
    # Unit B row, so the INSERT above mints a fresh `cert_id` and its six live grants
    # would keep naming the ids they were issued with - none of which any row holds.
    # `operations` and `research` resolve today only because their upsert hits an
    # existing row and keeps it.
    #
    # BEFORE THE COMMIT: the certification and the references it is read through are one
    # transaction, so there is no instant at which a valid certification exists that the
    # gate cannot see.
    repointed = await repoint_department_grants(
        conn, department=department, forge_id=forge_id, cert_id=row["cert_id"]
    )
    await conn.commit()

    await audit.write_event(
        event_type="department_certified_for_simulation",
        actor_type="human",
        actor_id=human.human_id,
        venture_id=venture_id,
        subject={
            "human": human.display_name,
            "department": department,
            "forge_id": forge_id,
            "cert_id": str(row["cert_id"]),
            "simulation_id": str(declaration.simulation_id),
            "declared_by": declaration.declared_by_name,
            "reason": reason.strip(),
            "modules": sorted(hashes),
            "instruction_content_hash": basis_hash,
            # ENTRY 181. How many grant references this act moved. On the event that
            # names the act rather than as a second event: one act, one entry, and a
            # reader asking whether Gate 9 can see this certification finds the answer
            # beside the certification itself.
            "grants_repointed": repointed,
        },
    )
    return CertState(row["cert_id"], row["unit"], row["state"], row["certified_tier"])


async def _department_modules(
    conn: AsyncConnection, *, venture_id: str, department: str, forge_id: str
) -> list[str]:
    """Which modules this department holds on this Forge, from its live grants.

    The same population Gate 8 composes a department basis over. Read from grants rather
    than from the Pack because a grant is what an agent actually carries, and a Pack can
    name a module no grant was issued for.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT DISTINCT g.module_id "
            "  FROM agent_forge_grant g "
            "  JOIN office_agent_identity i ON i.office_agent_id = g.office_agent_id "
            " WHERE g.venture_id = %s AND g.forge_id = %s AND i.department = %s "
            "   AND g.superseded_at IS NULL "
            " ORDER BY 1",
            (venture_id, forge_id, department),
        )
        return [r[0] for r in await cur.fetchall()]


async def _forge_api_version(conn: AsyncConnection, forge_id: str) -> str:
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT api_version FROM forge_registry WHERE forge_id = %s", (forge_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise CertificationError(f"{forge_id} is not a registered Forge")
    return str(row[0])


async def simulation_certifications(
    conn: AsyncConnection, venture_id: str | None = None
) -> list[dict[str, Any]]:
    """Every simulation certification, with whether its permission still stands.

    *"Any surface showing a grant, a gate or a sign-off says which of its certifications
    are simulation-only."* This is what those surfaces read, so there is one answer to
    the question rather than one per page.
    """
    where = "WHERE g.venture_id = %s " if venture_id else ""
    params = (venture_id,) if venture_id else ()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT DISTINCT c.cert_id, c.forge_id, c.department, c.issued_at, "
            "       c.scenario_pack_ref AS reason, g.venture_id, "
            "       vs.left_at IS NOT NULL AS void, "
            "       h.display_name AS declared_by, vs.reason AS declared_reason "
            "  FROM certification c "
            "  JOIN venture_simulation vs ON vs.simulation_id = c.simulation_ref "
            "  JOIN office_human h ON h.human_id = vs.declared_by "
            "  LEFT JOIN agent_forge_grant g "
            "    ON g.dept_context_cert_ref = c.cert_id::text AND g.superseded_at IS NULL "
            f" {where}ORDER BY c.forge_id, c.department",
            params,
        )
        return [dict(r) for r in await cur.fetchall()]


async def verdict_disagreements(
    conn: AsyncConnection, venture_id: str | None = None
) -> list[dict[str, Any]]:
    """Certifications whose own evidence contradicts their verdict. Entry 173.

    *"Enough to tell a wrong verdict from a right one without asking the examiner."*
    This is the telling. It reports and it refuses nothing: SimForge owns the exam and
    owns the call, and what changes is that The Office can now say why it disagrees
    instead of writing an email.

    **Narrow on purpose.** `disagrees_with_verdict` is true only when every attempt
    scored 1.0, no failure mode was observed and nothing was withheld, against a FAIL.
    A partial score is a judgement The Office has no standing to second-guess; *nothing
    failed and the verdict is FAIL* is a contradiction anybody can read.

    Reads the stored flag rather than recomputing it, so the report agrees with what
    was recorded at ingest. A recomputation would quietly change history the first time
    the predicate moved.
    """
    where = "AND g.venture_id = %s " if venture_id else ""
    params: tuple[Any, ...] = (venture_id,) if venture_id else ()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT DISTINCT c.cert_id, c.unit, c.module_id, c.department, c.forge_id, "
            "       c.state, c.simforge_verdict, c.score, c.threshold, "
            "       c.rubric_version, c.verdict_evidence, i.agent_name "
            "  FROM certification c "
            "  LEFT JOIN office_agent_identity i "
            "         ON i.office_agent_id = c.office_agent_id "
            "  LEFT JOIN agent_forge_grant g "
            "         ON g.office_agent_id = c.office_agent_id "
            "        AND g.superseded_at IS NULL "
            " WHERE c.verdict_evidence->>'disagrees_with_verdict' = 'true' "
            f"   {where}ORDER BY c.forge_id, c.module_id, i.agent_name",
            params,
        )
        rows = [dict(r) for r in await cur.fetchall()]

    return [
        {
            "cert_id": str(row["cert_id"]),
            "unit": row["unit"],
            "target": row["module_id"] or row["department"],
            "forge_id": row["forge_id"],
            "agent_name": row["agent_name"],
            "verdict": row["simforge_verdict"],
            "state": row["state"],
            "score": float(row["score"]) if row["score"] is not None else None,
            "threshold": (
                float(row["threshold"]) if row["threshold"] is not None else None
            ),
            "rubric_version": row["rubric_version"],
            # The argument, not just the flag. A reader who has to go and fetch the
            # evidence to see why it disagrees is a reader asking the examiner again.
            "attempt_scores": [
                a.get("score") for a in (row["verdict_evidence"].get("attempts") or [])
            ],
            "failure_modes_observed": (
                row["verdict_evidence"].get("failure_modes_observed") or []
            ),
            "withheld_because": row["verdict_evidence"].get("withheld_because") or [],
            "deciding_dimensions": (
                row["verdict_evidence"].get("deciding_dimensions") or []
            ),
            "per_scenario_class": (
                row["verdict_evidence"].get("per_scenario_class") or {}
            ),
        }
        for row in rows
    ]


async def deciding_dimensions(
    conn: AsyncConnection, venture_id: str | None = None
) -> list[dict[str, Any]]:
    """What decided each certification, and what failed without deciding. Entry 174.

    RULED 22 SEPTEMBER 2026 (decisions entry 174)
    =============================================

        *"A certification names the dimensions that decided it. Which dimension failed,
        its score, and which channel it belongs to, distinguished from the ones that
        didn't decide."*

    THE MEASUREMENT
    ===============

        `assign_contract`, 22 September, two agents with the IDENTICAL
        `per_scenario_class` - five classes FAIL, three PASS:

            Seraphine Valek   FAILED     restraint/failure_recognition 0.0
                                         + 3 disposition failures
            Ronan Valek       CERTIFIED  no failing restraint dimension
                                         + 3 disposition failures

        Nothing on either certification row said which of those mattered. A reader
        comparing them had two rows with the same scenario classes and opposite
        verdicts, and no way to tell why.

    **Both lists, always.** The non-deciding failures are reported rather than dropped
    because dropping them is how a CERTIFIED row with three failing dimensions reads as
    a mistake.
    """
    where = "AND g.venture_id = %s " if venture_id else ""
    params: tuple[Any, ...] = (venture_id,) if venture_id else ()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT DISTINCT c.cert_id, c.unit, c.module_id, c.department, c.forge_id, "
            "       c.state, c.simforge_verdict, c.score, c.rubric_version, "
            "       c.verdict_evidence, i.agent_name "
            "  FROM certification c "
            "  LEFT JOIN office_agent_identity i "
            "         ON i.office_agent_id = c.office_agent_id "
            "  LEFT JOIN agent_forge_grant g "
            "         ON g.office_agent_id = c.office_agent_id "
            "        AND g.superseded_at IS NULL "
            " WHERE c.verdict_evidence IS NOT NULL "
            f"   {where}ORDER BY c.forge_id, c.module_id, i.agent_name",
            params,
        )
        rows = [dict(r) for r in await cur.fetchall()]

    out: list[dict[str, Any]] = []
    for row in rows:
        evidence = row["verdict_evidence"] or {}
        deciding = evidence.get("deciding_dimensions") or []
        out.append({
            "cert_id": str(row["cert_id"]),
            "target": row["module_id"] or row["department"],
            "forge_id": row["forge_id"],
            "agent_name": row["agent_name"],
            "verdict": row["simforge_verdict"],
            "state": row["state"],
            "score": float(row["score"]) if row["score"] is not None else None,
            "deciding_channel": evidence.get("deciding_channel"),
            # Named one by one, with the score. "Three dimensions failed" is the
            # sentence this exists to replace.
            "decided_by": [
                {"dimension": d.get("dimension"), "channel": d.get("channel"),
                 "score": d.get("score")}
                for d in deciding
            ],
            "failed_without_deciding": [
                {"dimension": d.get("dimension"), "channel": d.get("channel"),
                 "score": d.get("score")}
                for d in (evidence.get("non_deciding_failures") or [])
            ],
            "accounted_for": bool(deciding) or row["state"] != "failed",
        })
    return out


async def recompute_staleness(
    conn: AsyncConnection, *, forge_id: str, module_id: str | None = None
) -> list[uuid.UUID]:
    """Mark certifications stale against what is live now. Returns the ids changed.

    Only `certified` rows are considered: a `failed` cert does not become
    `stale_instructions` when the text changes, because it was never fresh. Doing
    otherwise would erase the distinction between "was good, now out of date" and
    "was never good".

    NO LIVE INSTRUCTION IS STALE, NOT FRESH - and until 3 September 2026 it was
    the opposite.

    The comparison was guarded by `live_hash is not None`, so a Unit A cert whose
    module had no operating instruction at all was skipped and stayed `certified`
    forever. That is the worst case being treated as the best one: a certification
    bound to a `instruction_content_hash` that corresponds to no text cannot be
    said to match anything, and `grants.resolve_grant` dispatches it on the
    strength of `state = 'certified'`.

    It was not hypothetical. Every CapitalForge certification was in exactly that
    position - nine operating instructions existed as files and none had been
    authored into `forge_operating_instruction` - so the staleness sweep ran, found
    nothing to compare, and reported success.

    **Unit B is exempt, and that is not the same loophole.** A Unit B cert is
    department x forge and carries `module_id IS NULL` by design, so there is no
    single instruction it could be compared against. Applying the rule to it would
    mark every domain certification in the system stale, including ones that are
    genuinely current.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT c.cert_id, c.unit, c.module_id, c.instruction_content_hash,
                   c.forge_api_version,
                   i.content_hash AS live_hash, i.version_sensitivity,
                   r.api_version AS live_api_version
            FROM certification c
            JOIN forge_registry r ON r.forge_id = c.forge_id
            LEFT JOIN forge_operating_instruction i
                   ON i.forge_id = c.forge_id
                  AND i.module_id = c.module_id
                  AND i.superseded_at IS NULL
            WHERE c.state = 'certified'
              AND c.forge_id = %s
              AND (%s::text IS NULL OR c.module_id = %s)
            """,
            (forge_id, module_id, module_id),
        )
        rows = await cur.fetchall()

    changed: list[tuple[uuid.UUID, str]] = []
    for r in rows:
        # A Unit A cert names a module, so a module with no live instruction means
        # this cert is bound to a hash of nothing. See the docstring.
        if r["unit"] == "A" and r["live_hash"] is None:
            changed.append((r["cert_id"], STALE_INSTRUCTIONS))
            continue
        if r["live_hash"] is not None and r["instruction_content_hash"] != r["live_hash"]:
            changed.append((r["cert_id"], STALE_INSTRUCTIONS))
            continue
        sensitivity = r["version_sensitivity"] or "major.minor"
        if is_forge_version_stale(
            r["forge_api_version"], r["live_api_version"], sensitivity
        ):
            changed.append((r["cert_id"], STALE_FORGE))

    if changed:
        async with conn.cursor() as cur:
            for cert_id, new_state in changed:
                await cur.execute(
                    "UPDATE certification SET state = %s, updated_at = now() "
                    "WHERE cert_id = %s",
                    (new_state, cert_id),
                )
        await conn.commit()

    return [cert_id for cert_id, _ in changed]
