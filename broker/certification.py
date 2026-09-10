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

from psycopg import AsyncConnection
from psycopg.rows import dict_row

#: The verdicts that mean SOMETHING ANSWERED, imported rather than restated.
#: `simforge.TERMINAL_VERDICTS` is the one definition, named by P-03 when it decided
#: which results may stamp `result_received_at`, and migration 0035's CHECK mirrors it.
#: Three spellings of one set is how two of them drift; there are already two, and the
#: SQL one cannot import.
from broker.simforge import TERMINAL_VERDICTS as ANSWERED_VERDICTS

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
    attested_by: str = "simforge",
    bootstrap_reason: str | None = None,
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

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            INSERT INTO certification
              (cert_id, unit, office_agent_id, department, forge_id, module_id,
               state, certified_tier, instruction_content_hash, forge_api_version,
               rubric_kind, rubric_version, score, threshold, scenario_pack_ref, agent_model,
               simforge_verdict)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            ),
        )
        row = await cur.fetchone()
    await conn.commit()
    assert row is not None
    return CertState(row["cert_id"], row["unit"], row["state"], row["certified_tier"])


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
