"""The Pack Validator — Gate 2 of the provisioning pipeline.

33 rules. Any FAIL blocks provisioning; WARN is reported and does not.

Four things about the design are load-bearing:

**It returns a report, not a boolean.** A validator that answers False tells an author
to go looking. One that says `V13 FAIL: 340 projected approvals x 5 min = 1700 minutes
against 216 available` tells them what to change.

**Rules that need the world say so.** V2, V6 and V11 cannot be checked from the
document — a Pack that *declares* a Forge is bridged proves nothing, and that is
precisely the state Gate 0 exists to catch. Without a database connection those rules
report `NOT_RUN`. Part 10.1 says `NOT_RUN` must never be reported as a failure; the
converse matters just as much here, and it must never be reported as a pass either.

**Every FAIL rule has a must-fail fixture.** A rule nobody has watched fire is a rule
that might not. `tests/validator/` asserts both directions for all of them, and a
meta-test fails if any rule lacks either.

**A conformance rule states its own scope.** V32 resolves a Pack against what a Forge
actually dispatches, and a report that carried that verdict without its limits would be
the same overclaim the rule exists to catch. `render()` prints the scope whenever V32
reached an answer: it proves a handler is bound to the name, not that the handler works
or that it does what the name says. It automates the half of the question that was
already being done by hand and does not touch the other half.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from generators.pack import BusinessPack

# Part 14: a human reviewing for 100% of their coverage hours does nothing else, and a
# trust tier backed by a saturated reviewer is a rubber stamp waiting to happen.
UTILISATION_FACTOR = 0.6

# Roles whose failure has no second chance, so they cannot have a single point of
# human failure either.
CRITICAL_HUMAN_ROLES = ("compliance_officer", "trust_safety_escalation")

SENSITIVE_DATA_HINTS = ("phi", "pii", "financial", "credential", "recording", "biometric")


class Severity(StrEnum):
    FAIL = "FAIL"
    WARN = "WARN"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class RuleResult:
    rule_id: str
    severity: Severity
    verdict: Verdict
    message: str

    @property
    def blocks(self) -> bool:
        return self.verdict is Verdict.FAIL


@dataclass
class ValidationReport:
    results: list[RuleResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """WARN never blocks. NOT_RUN never counts as a pass.

        A Pack whose bridge check could not run has not been validated, and saying
        it passed would defeat the one rule that exists to stop provisioning against
        a Forge nobody can reach.
        """
        return not any(r.blocks for r in self.results) and not self.not_run

    @property
    def failures(self) -> list[RuleResult]:
        return [r for r in self.results if r.verdict is Verdict.FAIL]

    @property
    def warnings(self) -> list[RuleResult]:
        return [r for r in self.results if r.verdict is Verdict.WARN]

    @property
    def not_run(self) -> list[RuleResult]:
        return [r for r in self.results if r.verdict is Verdict.NOT_RUN]

    def get(self, rule_id: str) -> RuleResult:
        for r in self.results:
            if r.rule_id == rule_id:
                return r
        raise KeyError(f"rule {rule_id} did not run")

    def render(self) -> str:
        """Human-readable, and deterministic — same Pack, same text, same order."""
        lines = [
            f"Pack validation: {len(self.failures)} FAIL, {len(self.warnings)} WARN, "
            f"{len(self.not_run)} NOT_RUN, of {len(self.results)} rules"
        ]
        lines.extend(self._scope_header())
        for r in self.results:
            if r.verdict is not Verdict.PASS:
                lines.append(f"  {r.rule_id} {r.verdict.value}: {r.message}")
        return "\n".join(lines)

    def _scope_header(self) -> list[str]:
        """What V32's verdict means, printed where its verdict is read.

        Only when V32 reached the Forge. A NOT_RUN needs no scope line — nothing was
        checked, which its own message already says — and printing one anyway would
        put a sentence about what was proved above a report that proved nothing.
        """
        conformance = [
            r for r in self.results
            if r.rule_id == "V32" and r.verdict is not Verdict.NOT_RUN
        ]
        if not conformance:
            return []
        return [
            "  Module conformance (V32) proves a handler is bound to the name. Not "
            "that it works, and not that it does what the name says.",
            "  It automates the half of the question that was done by hand and does "
            "not touch the other half; the rest is forge_module_exclusion.",
        ]


# Rules that cannot be answered from the document alone.
# Kept in step with `_WORLD_RULES` by `test_needs_world_matches_the_world_rules`, which
# exists because these two lists drifted the first time a world rule was added: V29 and
# V30 were registered below and absent here, so the fixture meta-test demanded document
# fixtures for rules that cannot be evaluated without the Village. A literal is needed
# here rather than `set(_WORLD_RULES)` only because the registry is defined further down.
NEEDS_WORLD = {"V2", "V6", "V11", "V28", "V29", "V30", "V31", "V32", "V33", "V34"}

# V24 is evaluated at Gate 4.5 against appointment output, which does not exist at
# Gate 2. Recorded as metadata rather than a comment so the meta-test can see it.
GATE_45_RULES = {"V24"}

_RULES: list[tuple[str, Severity, str, Callable[[BusinessPack], tuple[bool, str]]]] = []


def rule(
    rule_id: str, severity: Severity, description: str
) -> Callable[[Callable[[BusinessPack], tuple[bool, str]]], Callable[..., Any]]:
    def wrap(fn: Callable[[BusinessPack], tuple[bool, str]]) -> Callable[..., Any]:
        _RULES.append((rule_id, severity, description, fn))
        return fn

    return wrap


def _join(items: Iterable[Any], limit: int = 5) -> str:
    items = list(items)
    head = ", ".join(str(i) for i in items[:limit])
    return head if len(items) <= limit else f"{head} (+{len(items) - limit} more)"


# --------------------------------------------------------------------- document rules

# Rules Gate 4.5 evaluates against real generator output. Two different situations share
# this list and the difference matters to a reader:
#
#   V24  cannot be evaluated at Gate 2 at all - it tests appointment output, which does
#        not exist until Gate 3 has run. It reports NOT_RUN, and NOT_RUN is not a pass.
#   V13  can be evaluated at Gate 2, from headcount and a conservative per-agent-day
#        factor, and is evaluated again at Gate 4.5 against the real Task Ledger. The
#        two can disagree by an order of magnitude and **the Gate 2 estimate is the
#        optimistic one** - Greenstone passes here and fails there.
#
#        The two gates also differ on the *supply* side, which for a long time nothing
#        said: Gate 2 pools every human regardless of role, Gate 4.5 splits per role and
#        weights by coverage share. That is a deliberate simplification rather than a
#        second unstated divergence - `v13`'s docstring states it and says why, and
#        blocking.md B25 is the item. Read them together; a difference between two gates
#        that only one of them documents reads as an accident in the other.
#
# So a Pack with no failures at Gate 2 has not been shown to be provisionable. It has
# been shown to have no failures *that Gate 2 can see*, which is a weaker statement and
# the one the editor is entitled to make.
GATE_45_RECHECKS = ("V13", "V24")

# Why each rule cannot be, or has not finally been, settled at Gate 2. Keyed by rule so
# the console can say which gate will answer it rather than leaving a bare NOT_RUN.
LATER_GATE_REASONS = {
    "V24": (
        "4.5",
        "Tests appointment output, which does not exist until the generators run at "
        "Gate 3.",
    ),
    "V13": (
        "4.5",
        "Estimated here from headcount and a conservative per-agent-day factor, and "
        "re-checked at Gate 4.5 against the real Task Ledger. The estimate here is the "
        "optimistic one. It also pools every reviewer together rather than checking each "
        "role against its own workload, which it cannot do until the workflow exists - so "
        "a role that is over capacity on its own can still pass here.",
    ),
}


@rule("V1", Severity.FAIL, "All required fields present")
def v1(pack: BusinessPack) -> tuple[bool, str]:
    # Pydantic enforced presence at load. What it cannot enforce is that a required
    # list is non-empty in the places emptiness is meaningless.
    empty = [
        name
        for name, value in (
            ("engagement_model.conversion_events", pack.engagement_model.conversion_events),
            ("engagement_model.disqualification_criteria",
             pack.engagement_model.disqualification_criteria),
            ("market.target_personas", pack.market.target_personas),
            ("market.target_geographies", pack.market.target_geographies),
        )
        if not value
    ]
    return (not empty, f"empty required list(s): {_join(empty)}" if empty else "all present")


@rule("V3", Severity.FAIL, "Every compliance framework has a resolving runtime_flag")
def v3(pack: BusinessPack) -> tuple[bool, str]:
    missing = [c.framework for c in pack.market.compliance_surface if not c.runtime_flag.strip()]
    return (not missing, f"no runtime_flag: {_join(missing)}" if missing
            else f"{len(pack.market.compliance_surface)} framework(s) resolve")


@rule("V4", Severity.FAIL, "Every framework has library_entry_ref or an explicit gap flag")
def v4(pack: BusinessPack) -> tuple[bool, str]:
    missing = [
        c.framework
        for c in pack.market.compliance_surface
        if not c.library_entry_ref and not c.library_gap
    ]
    return (not missing,
            f"[COMPLIANCE LIBRARY GAP] unflagged for: {_join(missing)}" if missing
            else "all frameworks resolve or are explicitly flagged")


@rule("V5", Severity.FAIL, "Every KPI has measurement_source, frequency and owner")
def v5(pack: BusinessPack) -> tuple[bool, str]:
    bad = [
        f"{horizon}/{k.kpi_name}"
        for horizon, kpis in pack.kpi_targets.items()
        for k in kpis
        if not (k.measurement_source.strip() and k.measurement_frequency.strip()
                and k.owner.strip())
    ]
    return (not bad, f"unmeasurable KPI(s): {_join(bad)}" if bad
            else "every KPI names a source, a frequency and an owner")


@rule("V7", Severity.FAIL, "api_version pinned; not 'latest'")
def v7(pack: BusinessPack) -> tuple[bool, str]:
    unpinned = [b.forge for b in pack.forge_dependencies.forge_bindings
                if b.api_version.strip().lower() in ("latest", "*", "")]
    return (not unpinned, f"unpinned api_version: {_join(unpinned)}" if unpinned
            else "all bindings pinned")


@rule("V8", Severity.FAIL, "No criticality:hard with module_gap:true")
def v8(pack: BusinessPack) -> tuple[bool, str]:
    bad = [b.forge for b in pack.forge_dependencies.forge_bindings
           if b.criticality == "hard" and b.module_gap]
    return (not bad, f"hard dependency on a module gap: {_join(bad)}" if bad
            else "no hard dependency on a gap")


@rule("V9", Severity.FAIL, "External software transmitting PHI has a signed BAA/DPA")
def v9(pack: BusinessPack) -> tuple[bool, str]:
    bad = [
        s.name
        for s in pack.forge_dependencies.external_software
        if any("phi" in d.lower() for d in s.data_types_transmitted)
        and s.dpa_or_baa_status != "signed"
    ]
    return (not bad, f"PHI transmitted without a signed BAA/DPA: {_join(bad)}" if bad
            else "no unsigned PHI transmission")


@rule("V10", Severity.FAIL, "Every position names >=1 Forge module and a source department")
def v10(pack: BusinessPack) -> tuple[bool, str]:
    """Presence only. Whether the department *exists* is V29, which has to ask.

    This rule used to check the name against a tuple of twelve departments kept in
    `generators/pack.py`. The Village was rebuilt and nine of them stopped existing;
    nothing failed, because the copy could not know. A Pack naming
    `Research & Market Intelligence` validated cleanly for two days after that department
    ceased to exist.
    """
    bad = []
    for p in pack.positions_required:
        if not p.forge_modules_operated:
            bad.append(f"{p.position_title}: no modules")
        if not (p.source_department or "").strip():
            bad.append(f"{p.position_title}: no source department")
    return (not bad, _join(bad) if bad else f"{len(pack.positions_required)} position(s) resolve")


@rule("V12", Severity.FAIL, "Every instruction set has version_sensitivity and content_hash")
def v12(pack: BusinessPack) -> tuple[bool, str]:
    bad = [
        f"{i.forge_id}/{i.module_id}"
        for i in pack.forge_operating_instructions
        if not i.content_hash
        or (i.version_sensitivity == "major.minor.patch" and not i.sensitivity_rationale)
    ]
    return (not bad, f"instruction set(s) incomplete: {_join(bad)}" if bad
            else "all instruction sets are hash-bound")


@rule("V13", Severity.FAIL, "Projected daily approvals <= capacity x 0.6")
def v13(pack: BusinessPack) -> tuple[bool, str]:
    """Gate 2's cheap capacity estimate. **It pools supply across roles, deliberately.**

    Both sides of the comparison below are pooled over every human in the Pack, with no
    role split at all: one unweighted mean review time, one total of all coverage. Gate
    4.5 re-checks this same rule and does the opposite - it splits by role, sums coverage
    within the role, and weights review minutes by each person's coverage share of it.

    **The two gates do not compute the same quantity, and this is the note that says so.**
    `validate_gate_4_5`'s docstring explains at length why the two see different *demand*
    figures - Gate 2 estimates approvals from headcount, the Task Ledger computes them
    from the real workflow, and the Gate 2 estimate is the optimistic one. It says nothing
    about *supply*. That left a documented difference sitting next to an undocumented one,
    which is worse than two undocumented ones because the first vouches for the second.
    See blocking.md B25. **Pooling is the stated choice; the reason is below.**

    WHY POOLING RATHER THAN GATE 4.5's SPLIT

    Gate 2 has no per-role demand figure to split against. `approvals` below is a single
    number off headcount and agent-days, and nothing in the Pack attributes any part of it
    to a reviewer role - the thing that does the attributing is the workflow and the
    compliance flags on each step, which are generator output that does not exist until
    Gate 3. Split supply per role here and you get role buckets with nothing to set
    against them. **The split is not skipped because it is expensive. It is skipped
    because at this gate there is no other half of it.**

    WHICH WAY THE SIMPLIFICATION ERRS - BOTH DIRECTIONS, NOT ONE

    *Pooling across roles errs optimistic, and only optimistic.* A slack role's spare
    coverage absorbs a saturated one, so pooling can hide a bottleneck and can never
    invent one. That agrees with the direction `LATER_GATE_REASONS` already declares, and
    it is why Greenstone passes here and fails at 4.5.

    *The unweighted mean errs either way, and is bounded.* It can land on either side of
    Gate 4.5's coverage-weighted figure: for Greenstone the pooled mean is 5.0 against a
    coverage-weighted 4.8, so here it is the **more** demanding of the two; for Burkham,
    whose two officers declare equal coverage, the two agree exactly at 3.5. It always
    lies between the smallest and largest declared `median_review_minutes`, so unlike the
    role split it cannot run away from the truth in either direction.

    Writing only the first of those would be the same failure B25 is about, one level
    down. Both are here so neither vouches for the other.

    **A PASS here is therefore not a capacity finding.** It is "no shortfall a pooled
    estimate can see", which is the weaker claim, and `GATE_45_RECHECKS` carries that to
    the editor so the screen does not imply otherwise.
    """
    # Every position below auto_execute produces approvals. One per headcount per
    # agent-day is the deliberately conservative estimate: under-estimating here
    # produces a green check on a reviewer who is already saturated.
    #
    # No role appears in this expression, and none can: see the docstring.
    approvals = sum(
        p.headcount for p in pack.positions_required if p.trust_tier_ceiling != "auto_execute"
    ) * max(1.0, pack.capacity_demand.agent_days_per_week / 7.0)

    # Pooled and unweighted, by the choice stated above - not by oversight, and not the
    # coverage-weighted per-role figure Gate 4.5 computes.
    minutes_needed = sum(
        h.median_review_minutes for h in pack.human_capacity
    ) / max(len(pack.human_capacity), 1) * approvals

    # Every human's coverage, in one number, for the same reason.
    minutes_available = sum(
        h.coverage_hours * 60 * UTILISATION_FACTOR for h in pack.human_capacity
    )
    ok = minutes_needed <= minutes_available
    return (ok, f"{approvals:.0f} projected approvals need {minutes_needed:.0f} review-minutes "
                f"against {minutes_available:.0f} available "
                f"({UTILISATION_FACTOR} x coverage). Trust tiers become decorative above this."
            if not ok else
            f"{minutes_needed:.0f} of {minutes_available:.0f} review-minutes used")


@rule("V14", Severity.FAIL, "Compliance and T&S roles have backup_human")
def v14(pack: BusinessPack) -> tuple[bool, str]:
    bad = [
        h.human_name for h in pack.human_capacity
        if any(r in h.role.lower().replace(" ", "_") for r in CRITICAL_HUMAN_ROLES)
        and not h.backup_human
    ]
    return (not bad, f"critical role(s) with no backup: {_join(bad)}" if bad
            else "critical roles are backed up")


@rule("V15", Severity.FAIL, "gate_signoff_policy declared; justification if single-human")
def v15(pack: BusinessPack) -> tuple[bool, str]:
    sod = pack.separation_of_duties
    if sod.gate_signoff_policy == "single_human_permitted" and not (
        sod.single_human_justification or ""
    ).strip():
        return False, ("single_human_permitted requires a written justification; it is "
                       "surfaced verbatim in regulator exports")
    return True, f"signoff policy: {sod.gate_signoff_policy}"


@rule("V16", Severity.FAIL, "agent_initiated triggers have rate and depth limits")
def v16(pack: BusinessPack) -> tuple[bool, str]:
    bad = [
        t.trigger_id for t in pack.triggers
        if t.type == "agent_initiated"
        and (t.max_invocations_per_hour is None or t.max_chain_depth < 1)
    ]
    return (not bad, f"unbounded agent_initiated trigger(s): {_join(bad)}" if bad
            else "agent-initiated triggers are bounded")


@rule("V17", Severity.FAIL, "data_retention covers every sensitive data type")
def v17(pack: BusinessPack) -> tuple[bool, str]:
    covered = {d.data_type.lower() for d in pack.data_retention}
    mentioned = {
        d.lower()
        for s in pack.forge_dependencies.external_software
        for d in s.data_types_transmitted
    }
    sensitive = {
        d for d in mentioned if any(hint in d for hint in SENSITIVE_DATA_HINTS)
    }
    missing = sorted(d for d in sensitive if d not in covered)
    return (not missing, f"sensitive data with no retention policy: {_join(missing)}" if missing
            else f"{len(covered)} retention polic(ies) declared")


@rule("V18", Severity.FAIL, "Budget caps present")
def v18(pack: BusinessPack) -> tuple[bool, str]:
    b = pack.budget
    bad = [
        name for name, value in (
            ("monthly_usd_cap", b.monthly_usd_cap),
            ("per_agent_usd_daily_cap", b.per_agent_usd_daily_cap),
            ("per_task_usd_ceiling", b.per_task_usd_ceiling),
        ) if value <= 0
    ]
    return (not bad, f"non-positive budget cap(s): {_join(bad)}" if bad
            else f"caps: {b.monthly_usd_cap}/mo, {b.per_agent_usd_daily_cap}/agent-day")


@rule("V19", Severity.FAIL, "availability complete including RTO/RPO")
def v19(pack: BusinessPack) -> tuple[bool, str]:
    a = pack.availability
    if a.rto_minutes <= 0 or a.rpo_minutes <= 0:
        return False, f"RTO={a.rto_minutes} RPO={a.rpo_minutes}; both must be positive"
    return True, f"RTO {a.rto_minutes}m / RPO {a.rpo_minutes}m, {a.office_unreachable_behavior}"


@rule("V20", Severity.FAIL, "Every binding has rate_limit_policy and credential_mode")
def v20(pack: BusinessPack) -> tuple[bool, str]:
    bad = [b.forge for b in pack.forge_dependencies.forge_bindings if b.rate_limit_policy is None]
    return (not bad, f"binding(s) without a rate_limit_policy: {_join(bad)}" if bad
            else "every binding is rate-limited")


@rule("V21", Severity.FAIL, "SimForge binding present and criticality:hard")
def v21(pack: BusinessPack) -> tuple[bool, str]:
    sim = [b for b in pack.forge_dependencies.forge_bindings if b.forge.lower() == "simforge"]
    if not sim:
        return False, "no SimForge binding; certification gates assignment, so it is not optional"
    if sim[0].criticality != "hard":
        return False, f"SimForge declared {sim[0].criticality!r}; certification is not soft"
    return True, "SimForge bound as hard"


@rule("V22", Severity.FAIL, "Every compliance flag appears in >=1 scenario")
def v22(pack: BusinessPack) -> tuple[bool, str]:
    # "Compliance flag" means the runtime_flag, not the framework name. The flag is
    # what propagates through positions, bindings and agent_call_ledger; the framework
    # name never appears at runtime, so a scenario can only exercise a flag. Comparing
    # against framework names would make this rule unsatisfiable by construction.
    declared = {c.runtime_flag for c in pack.market.compliance_surface if c.runtime_flag.strip()}
    exercised = {f for s in pack.scenarios for f in s.compliance_flags_exercised}

    # A human-held obligation is accounted for here and checked elsewhere. It is real,
    # and no agent role holds it - so demanding a scenario would mean inventing a duty
    # no position has. `HumanHeld` says so with a reason; whether the obligation was
    # actually discharged is a different question with its own rule and its own verdict,
    # so that a missing discharge can never read as an unexercised flag.
    #
    # This rule stays a pure function of the Pack. It does not read the discharge record
    # and must not: a world rule reports NOT_RUN where there is no database, and turning
    # the one failure that is supposed to be visible into a NOT_RUN would bury it.
    human_held = {
        c.runtime_flag for c in pack.market.compliance_surface
        if c.runtime_flag.strip() and c.human_held is not None
    }
    missing = sorted(declared - exercised - human_held)
    if missing:
        return False, f"runtime flag(s) never exercised by a scenario: {_join(missing)}"
    if human_held:
        return True, (
            f"all {len(declared)} compliance flag(s) accounted for: "
            f"{len(declared) - len(human_held)} exercised by a scenario, "
            f"{len(human_held)} declared human-held ({_join(sorted(human_held))}) - "
            "whether those were discharged is V34's question, not this one"
        )
    return True, f"all {len(declared)} compliance flag(s) exercised"


@rule("V23", Severity.FAIL, ">=3 scenarios per role x domain; >=1 expected_escalation per role")
def v23(pack: BusinessPack) -> tuple[bool, str]:
    by_role_domain: dict[tuple[str, str], int] = {}
    escalations: dict[str, int] = {}
    for s in pack.scenarios:
        by_role_domain[(s.role, s.domain)] = by_role_domain.get((s.role, s.domain), 0) + 1
        escalations.setdefault(s.role, 0)
        if s.expected_escalation:
            escalations[s.role] += 1

    thin = [f"{r}/{d}={n}" for (r, d), n in sorted(by_role_domain.items()) if n < 3]
    no_escalation = sorted(r for r, n in escalations.items() if n == 0)
    roles_without_scenarios = sorted(
        {p.position_title for p in pack.positions_required} - set(escalations)
    )

    problems = []
    if roles_without_scenarios:
        problems.append(f"no scenarios for: {_join(roles_without_scenarios)}")
    if thin:
        problems.append(f"fewer than 3 scenarios: {_join(thin)}")
    if no_escalation:
        problems.append(f"no expected_escalation scenario: {_join(no_escalation)}")

    return (not problems, "; ".join(problems) if problems
            else f"{len(pack.scenarios)} scenarios across {len(by_role_domain)} role-domain pairs")


# ------------------------------------------------------------------------ WARN rules

@rule("V25", Severity.WARN, "Declared Forge with zero required_by references")
def v25(pack: BusinessPack) -> tuple[bool, str]:
    used = {m for p in pack.positions_required for m in p.forge_modules_operated}
    unused = [
        b.forge for b in pack.forge_dependencies.forge_bindings
        if b.forge.lower() != "simforge"
        and not any(m in used for m in b.modules_expected)
    ]
    return (not unused, f"declared but unreferenced: {_join(unused)}" if unused
            else "every declared Forge is referenced")


@rule("V26", Severity.WARN, "fallback_behavior on every soft Forge")
def v26(pack: BusinessPack) -> tuple[bool, str]:
    bad = [b.forge for b in pack.forge_dependencies.forge_bindings
           if b.criticality == "soft" and b.fallback_behavior is None]
    return (not bad, f"soft Forge(s) with no fallback_behavior: {_join(bad)}" if bad
            else "soft dependencies declare a fallback")


@rule("V27", Severity.WARN, "Any [MODULE GAP] in Pack")
def v27(pack: BusinessPack) -> tuple[bool, str]:
    gaps = [b.forge for b in pack.forge_dependencies.forge_bindings if b.module_gap]
    return (not gaps, f"[MODULE GAP] declared for: {_join(gaps)} - surfaced at Gate 4" if gaps
            else "no module gaps")


# ------------------------------------------------------------------- world-aware rules

async def _v2_bridge_operational(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool, str]:
    """Gate 0. A Pack that declares a Forge is bridged proves nothing.

    Operational means: registered, health not RED, and a tenant credential exists.
    All three, because a Forge with no credential is a Forge the broker cannot
    authenticate to however healthy it looks.
    """
    hard = [b.forge for b in pack.forge_dependencies.forge_bindings if b.criticality == "hard"]
    if not hard:
        return True, "no hard bindings"

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.forge_id, r.health_status, c.credential_ref
            FROM forge_registry r
            LEFT JOIN forge_tenant_credential c ON c.forge_id = r.forge_id
            WHERE lower(r.forge_id) = ANY(%s)
            """,
            ([f.lower() for f in hard],),
        )
        rows = {r["forge_id"].lower(): r for r in await cur.fetchall()}

    unreached = []
    for forge in hard:
        row = rows.get(forge.lower())
        if row is None:
            unreached.append(f"{forge}: not in forge_registry")
        elif row["health_status"] == "RED":
            unreached.append(f"{forge}: health RED")
        elif row["credential_ref"] is None:
            unreached.append(f"{forge}: no tenant credential")

    return (not unreached,
            f"bridge not operational: {_join(unreached)}. Gate 0 blocks provisioning "
            "against a Forge the bridge does not reach." if unreached
            else f"bridge operational for {_join(hard)}")


async def _v6_modules_resolve(conn: AsyncConnection, pack: BusinessPack) -> tuple[bool, str]:
    wanted = {
        (b.forge.lower(), m)
        for b in pack.forge_dependencies.forge_bindings
        for m in b.modules_expected
    }
    if not wanted:
        return True, "no modules declared"

    async with conn.cursor() as cur:
        await cur.execute("SELECT lower(forge_id), module_id FROM forge_module_registry")
        known = {(r[0], r[1]) for r in await cur.fetchall()}

    missing = sorted(f"{f}/{m}" for f, m in wanted - known)
    return (not missing, f"module(s) not in forge_module_registry: {_join(missing)}" if missing
            else f"all {len(wanted)} module reference(s) resolve")


async def _v11_instructions_authored(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool | None, str]:
    """Every module a position operates must have live instructions that teach it.

    Without them SimForge has nothing to test against, so the position can never be
    certified and the appointment can never be filled.

    **A row is not a curriculum.** This rule used to check that an instruction set
    existed, which the live cre-forge set satisfies with `"what_it_does": "Documented."`
    and `"inputs": {"a": "b"}` - eight sections present, none empty, a valid
    `content_hash` over the lot. A hash computed over placeholder text satisfies the
    letter of this rule and defeats its purpose: SimForge trains against that text, an
    agent is certified against that hash, and the certification is a statement about
    nothing.

    So the content is assessed, in the same place the console and the compliance page
    assess it. `thin` passes - it is real content that does not go far enough, and
    blocking a release on a short but honest sentence would teach people to pad. `stub`
    and `missing` do not.

    AN EXCLUDED MODULE NEEDS NO CURRICULUM, AND IS NAMED RATHER THAN SKIPPED SILENTLY
    ================================================================================

        **A curriculum exists to be certified against.** Nothing can be certified for a
        module in `forge_module_exclusion`, because no agent may ever hold a grant over
        it, so requiring an instruction for one asks for a document with no purpose -
        and where the exclusion is `forbidden`, for a manual teaching how to perform a
        prohibited act, whose `content_hash` would then bind a certification to it.

        Ruled 2026-09-07 (docs/blocking.md B12). The alternative was to take the module
        off `forge_modules_operated`, and it is worse: a Pack edit hides that the Pack
        once asked for it, where the exclusion row is the honest record of both the ask
        and the refusal.

        **They are reported, never silently dropped.** A skipped module that vanished
        from the message would make an exclusion indistinguishable from coverage - the
        reader would see every operated module accounted for and could not tell which
        were taught and which were refused. That is entry 16's shape: a rollup losing a
        distinction the layer beneath keeps.
    """
    from broker.curriculum_quality import assess

    modules = {m for p in pack.positions_required for m in p.forge_modules_operated}
    if not modules:
        return True, "no modules operated"

    declared = _declared_forges(pack)
    operating = pack.forge_dependencies.operating_forge.lower()

    def forges_for(module: str) -> set[str]:
        return declared.get(module) or {operating}

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT lower(forge_id), module_id FROM forge_module_exclusion"
        )
        excluded_pairs = {(r[0], r[1]) for r in await cur.fetchall()}
        # Keyed on (forge_id, module_id), not module_id. `forge_operating_instruction`
        # is keyed on both, and flattening it to the module id lets two Forges with a
        # same-named module satisfy each other's requirement - the manual an agent is
        # certified against would be the other Forge's. Same defect as B10, in a rule
        # rather than in a gate.
        await cur.execute(
            "SELECT lower(forge_id), module_id, content FROM forge_operating_instruction "
            "WHERE superseded_at IS NULL"
        )
        live = {(r[0], r[1]): r[2] for r in await cur.fetchall()}

    excluded = sorted(
        module for module in modules
        if any((forge_id, module) in excluded_pairs for forge_id in forges_for(module))
    )
    excluded_note = (
        f" ({len(excluded)} excluded, no instruction required: {_join(excluded)})"
        if excluded else ""
    )
    teachable = modules - set(excluded)
    if not teachable:
        return True, f"no module requires an instruction{excluded_note}"

    missing = sorted(
        module for module in teachable
        if not any((forge_id, module) in live for forge_id in forges_for(module))
    )
    if missing:
        return False, (
            f"no Forge Operating Instructions authored for: {_join(missing)}"
            f"{excluded_note}"
        )

    def content_for(module: str) -> dict[str, Any]:
        for forge_id in sorted(forges_for(module)):
            if (forge_id, module) in live:
                content: dict[str, Any] = live[(forge_id, module)]
                return content
        raise AssertionError(f"{module} passed the missing check with no content")

    hollow = sorted(
        module for module in teachable
        if assess(content_for(module))["teaches_nothing"]
    )
    if hollow:
        return False, (
            f"instructions exist but teach nothing for: {_join(hollow)}. A content_hash "
            "computed over placeholder text is a valid hash of nothing, and every "
            "certification bound to it inherits that emptiness."
            f"{excluded_note}"
        )

    # And the module the instructions teach has to exist.
    #
    # Present, and not hollow, were both questions about the document. Neither asks
    # whether there is anything on the other end of it. `cre-forge/generate_loi` had a
    # complete-looking instruction, assessed `state=complete`, for a module CRE Forge
    # has never dispatched - no service, no route, no letter-of-intent among its
    # contract templates.
    #
    # That reaches further than a Pack. SimForge would train an agent against that text
    # and issue a certification carrying its `content_hash`, and afterwards a
    # certification for a module with no handler reads exactly like one for a real
    # module: the row is there, the hash resolves, the agent is certified. Nothing
    # downstream can tell them apart. V32 refuses a Pack that *declares* a module the
    # Forge does not dispatch; this is the same refusal one table over, on the path
    # that ends in a certification.
    from broker import forge_modules

    per_forge: dict[str, set[str]] = {}
    for module in teachable:
        for forge_id in forges_for(module):
            per_forge.setdefault(forge_id, set()).add(module)

    taught_but_absent: list[str] = []
    unread: list[str] = []
    for forge_id, wanted in sorted(per_forge.items()):
        answer = await forge_modules.read(conn, forge_id, candidates=wanted)
        if isinstance(answer, forge_modules.Unread):
            unread.append(f"{forge_id}: {answer.reason}")
            continue
        taught_but_absent.extend(f"{forge_id}/{m}" for m in answer.missing(wanted))

    if taught_but_absent:
        return False, (
            f"instructions teach a module the Forge does not dispatch: "
            f"{_join(taught_but_absent)}. SimForge trains against that text and binds a "
            "certification to its content_hash, and a certification for a module with "
            "no handler is indistinguishable from a real one afterwards."
        )

    thin = sorted(
        module for module in teachable if assess(content_for(module))["state"] == "thin"
    )
    detail = f" ({_join(thin)} thin)" if thin else ""

    # `len(teachable)`, not `len(modules)`, and the excluded ones named beside it. The
    # count and the note have to move together: "all 7 module(s)" over a set of six
    # taught and one refused is the rollup that loses the distinction.
    if unread:
        return None, (
            f"instructions are authored for all {len(teachable)} module(s){detail}"
            f"{excluded_note}, but whether the modules they teach exist could not be "
            f"checked: {_join(unread)}. NOT_RUN is not a pass - curriculum for a module "
            "that does not exist reaches certification, and nothing here has ruled that "
            "out."
        )

    return True, (
        f"instructions authored for all {len(teachable)} module(s){detail}, each "
        f"teaching a module the Forge dispatches{excluded_note}"
    )


async def _v28_library_refs_resolve(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool, str]:
    """V4 says a `library_entry_ref` is present. V28 says it points at something.

    V4 is self-attestation and always was: a Pack naming
    `compliance/nv-two-party-consent-v1` passes it whether or not that entry exists.
    That is the same shape as a Pack *declaring* a Forge is bridged, which is precisely
    what V2 exists to disbelieve. Until Part 6.3 was built there was nothing to check
    against, so the gap was unavoidable rather than deliberate.

    An explicit `library_gap: true` is honest and does not fail here - the Pack has said
    the entry does not exist, which is the thing V28 would otherwise have to discover.
    A ref that resolves to nothing is the failure, because that Pack claims coverage it
    does not have.
    """
    refs = [
        c.library_entry_ref
        for c in pack.market.compliance_surface
        if c.library_entry_ref and not c.library_gap
    ]
    if not refs:
        return True, "no compliance framework claims a library entry"

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT entry_ref FROM compliance_library_entry WHERE entry_ref = ANY(%s)",
            (refs,),
        )
        found = {r[0] for r in await cur.fetchall()}

    missing = sorted(set(refs) - found)
    if not missing:
        return True, f"{len(found)} of {len(refs)} library ref(s) resolve"

    # UNWRITTEN AND UNLOADED ARE DIFFERENT FACTS, and saying "resolve to nothing" for
    # both is what let nineteen fully-written entries sit behind this rule reading as
    # a documentation gap. They were complete on disk the whole time; nothing had
    # ingested them, and "write the entry" is the wrong instruction for an entry
    # somebody had already written.
    on_disk = _refs_on_disk()
    unloaded = [r for r in missing if r in on_disk]
    unwritten = [r for r in missing if r not in on_disk]

    parts: list[str] = []
    if unloaded:
        parts.append(
            f"{len(unloaded)} WRITTEN BUT NOT LOADED - present in "
            f"packs/compliance-library/ and absent from compliance_library_entry: "
            f"{_join(unloaded)}. Run scripts/load_compliance_library.py; do not "
            "rewrite these."
        )
    if unwritten:
        parts.append(
            f"{len(unwritten)} NOT WRITTEN ANYWHERE - no entry in "
            f"packs/compliance-library/ either: {_join(unwritten)}. Write the entry, "
            "or set library_gap so the Pack stops claiming coverage it does not have."
        )
    return False, (
        f"[COMPLIANCE LIBRARY GAP] {len(missing)} of {len(refs)} ref(s) do not "
        f"resolve. " + " ".join(parts)
    )


def _refs_on_disk() -> set[str]:
    """Every `entry_ref` written in packs/compliance-library/, loaded or not.

    Read from the files rather than from the database on purpose: the whole point of
    this call is to tell an entry nobody wrote from one nobody ingested, and the
    database cannot answer that question about itself.
    """
    library = Path(__file__).resolve().parents[1] / "packs" / "compliance-library"
    if not library.is_dir():
        return set()
    refs: set[str] = set()
    for path in sorted(library.glob("*.yaml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        refs.update(re.findall(r"^\s*-?\s*entry_ref:\s*(\S+)", text, re.M))
    return refs


async def _v29_departments_exist(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool | None, str]:
    """Every position's department is one the Village actually has.

    The failure names all twelve, in the casing the Village UI shows, because the
    operator's next action is to pick one and they should not have to go and find the
    list to do it.
    """
    from broker import departments as depts

    known = await depts.names()
    if known is None:
        # Two different facts, and they send a reader to different places: "start the
        # Village" versus "find out what is holding that port". Reporting the first when
        # the second was true left V29 and V30 NOT_RUN for a week while everyone assumed
        # a missing credential.
        if depts.was_misidentified():
            return (
                None,
                "no position's department has been checked, and NOT because the Village "
                f"refused: {depts.unreachable_reason()} NOT_RUN is not a pass, and this "
                "one is not a credential problem.",
            )
        return (
            None,
            "the department list could not be read from the Village "
            f"({depts.unreachable_reason() or 'no answer'}), so no position's department "
            "has been checked. NOT_RUN is not a pass.",
        )

    labels = await depts.labels() or ()
    bad = [
        f"{p.position_title}: {p.source_department!r}"
        for p in pack.positions_required
        if depts.normalize(p.source_department) not in known
    ]
    if bad:
        return (
            False,
            f"{_join(bad)} - not a Village department. The twelve are: "
            f"{', '.join(labels)}.",
        )
    return (True, f"{len(pack.positions_required)} position(s) name a real department")


async def _v30_department_has_seats(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool | None, str]:
    """The department is big enough for what the Pack asks. Warns here.

    Two different questions, split deliberately. This one asks whether the department is
    large enough at all - a Pack wanting 20 researchers from a department of 14 is wrong
    on its face and should be caught while somebody is still editing it. Gate 4.5 asks
    the harder question, whether those seats are uncommitted, which needs appointment
    output that does not exist at Gate 2.
    """
    from broker import departments as depts

    seats = await depts.seats()
    if seats is None:
        if depts.was_misidentified():
            return (
                None,
                "no position has been checked against the size of its department, and "
                f"NOT because the Village refused: {depts.unreachable_reason()}",
            )
        return (
            None,
            "department headcount could not be read from the Village "
            f"({depts.unreachable_reason() or 'no answer'}), so no position has been "
            "checked against the size of its department.",
        )

    wanted: dict[str, int] = {}
    for position in pack.positions_required:
        key = depts.normalize(position.source_department)
        wanted[key] = wanted.get(key, 0) + int(getattr(position, "headcount", 1) or 1)

    # A department the Village does not have is not a department with room. Splitting
    # these apart is the whole correctness of this rule: the first version filtered
    # `if name in seats` and then reported `len(wanted)`, so a Pack naming three
    # departments that do not exist compared nothing and answered "3 department(s) have
    # seats for what the Pack asks". Every one of the three was absent. The rule passed
    # by skipping its entire subject and then described the subject it had skipped.
    checked = {name: count for name, count in wanted.items() if name in seats}
    unknown = sorted(set(wanted) - set(checked))

    over = [
        f"{name} wants {count} of {seats[name]} seat(s)"
        for name, count in sorted(checked.items())
        if count > seats[name]
    ]
    if over:
        return (False, f"{_join(over)}. The department is not that large.")

    if not checked:
        return (
            None,
            f"no position could be checked against a department size: {_join(unknown)} "
            "- none of these is a Village department, so there is no headcount to "
            "compare against. V29 reports that as the failure it is; this rule has "
            "measured nothing and says so rather than passing.",
        )

    # "Has seats" is not "has people free". This rule compares headcount requested
    # against the department's total size; Gate 4.5 asks whether those seats are
    # uncommitted, which needs appointment output that does not exist here. A V30 pass
    # means the department is large enough in principle, and says nothing about whether
    # anybody in it is available.
    message = f"{len(checked)} department(s) have seats for what the Pack asks"
    if unknown:
        message += (
            f"; {len(unknown)} not checked because they are not Village departments "
            f"({_join(unknown)}) - see V29"
        )
    return (True, message)


# ------------------------------------------------------- V31: unattended writes

#: The only tier that reaches a Forge at all. Step 7 of the client library turns
#: anything below `auto_execute` into a proposal and makes no HTTP call, so a human
#: sees every call at `propose` and `suggest` before it happens. `auto_execute` is
#: therefore not "the fast one" — it is the one with nobody in the path.
UNATTENDED_TIER = "auto_execute"

#: A module that mints a new artefact on every call and cannot be asked twice safely.
#: `key` and `natural` both survive a retry: the Forge either de-duplicates on the
#: idempotency key or the write is naturally the same act repeated.
UNSAFE_IDEMPOTENCY = "at_most_once"


@dataclass(frozen=True, slots=True)
class ModuleShape:
    """What `forge_module_registry` knows about calling a module twice, and whence."""

    is_mutating: bool
    idempotency_support: str
    verification_method: str

    @property
    def unsafe_unattended(self) -> bool:
        return self.is_mutating and self.idempotency_support == UNSAFE_IDEMPOTENCY

    @property
    def is_evidence(self) -> bool:
        """`hand` is a claim. The other two were obtained from the Forge.

        This is the asymmetry the rule turns on. A hand-written row that says a
        module is an at-most-once writer may be wrong, and refusing on it blocks
        a Pack that might have been fine — annoying, and safe. A hand-written row
        that says a module is a harmless read may also be wrong, and passing on
        it hands an unattended agent a writer. `property_lookup` was recorded
        mutating by hand and it is a search: the one module anybody had called
        had the checkable half wrong.

        So a refusal stands on any row, and a pass needs evidence.
        """
        return self.verification_method != "hand"


def _declared_forges(pack: BusinessPack) -> dict[str, set[str]]:
    """module_id -> the forge(s) a binding declares it under.

    A set rather than a single value because nothing stops two bindings from naming
    the same module, and picking one silently would check the tier against the wrong
    Forge's row.
    """
    out: dict[str, set[str]] = {}
    for binding in pack.forge_dependencies.forge_bindings:
        for module in binding.modules_expected:
            out.setdefault(module, set()).add(binding.forge.lower())
    return out


def unattended_writes(
    pack: BusinessPack, shapes: dict[tuple[str, str], ModuleShape]
) -> tuple[list[str], list[str]]:
    """(refusals, unresolved) for every module operated at `auto_execute`.

    Pure, and separate from the query, so the decision can be tested without a
    database. `shapes` is keyed `(forge_id, module_id)` with `forge_id` lowercased.
    """
    declared = _declared_forges(pack)
    refusals: list[str] = []
    unresolved: list[str] = []

    for position in pack.positions_required:
        if position.trust_tier_ceiling != UNATTENDED_TIER:
            continue
        for module in position.forge_modules_operated:
            forges = declared.get(module) or {pack.forge_dependencies.operating_forge.lower()}
            known = [shapes[(f, module)] for f in sorted(forges) if (f, module) in shapes]
            if not known:
                unresolved.append(f"{position.position_title}: {_join(sorted(forges))}/{module}")
                continue
            for forge, shape in (
                (f, shapes[(f, module)]) for f in sorted(forges) if (f, module) in shapes
            ):
                if shape.unsafe_unattended:
                    refusals.append(
                        f"{position.position_title} operates {forge}/{module} at "
                        f"{UNATTENDED_TIER}, and the registry says it is a mutating "
                        f"{UNSAFE_IDEMPOTENCY} module"
                    )
                elif not shape.is_evidence:
                    unresolved.append(
                        f"{position.position_title}: {forge}/{module} "
                        "(hand-written row, never verified against the Forge)"
                    )
    return refusals, unresolved


async def _v31_unattended_writes(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool | None, str]:
    """`auto_execute` on a module that cannot be called twice is refused.

    This is the tier check with teeth, and it is a different question from V6. V6 asks
    whether a module resolves to a registry row. This asks whether the tier the Pack
    grants over it is survivable — a module can resolve perfectly and still be wrong to
    run with nobody watching.

    **WHAT IT DOES NOT REACH: a mutating module whose idempotency is `natural`.**
    `record_consent` is one - calling it twice records consent twice against the
    same business, and this rule permits `auto_execute` over it because a natural
    key means a retry is not a second act. That is the right reading of
    `natural` and it leaves one module unguarded by tier.

    Deliberately not closed. A `min_trust_tier` column on `forge_module_registry`
    plus a check in `resolve_grant` is machinery built for a single case, and the
    Burkham Pack grants nothing at `auto_execute` anyway. Recorded here rather
    than fixed, so the next reader knows the gap is known and sized.

    The shape it refuses is the one `regulator_dossier_export` is written around:
    every call mints a new `exportId`, writes a row and emits an event, so a retry
    after a timeout produces a second export of the same inquiry and the audit trail
    then shows two. Its sibling `compliance_manifest_assemble` mints nothing and
    retries freely — same permission, same reader, opposite handling. An agent is the
    caller least likely to go looking for the first `exportId` before minting a second,
    and an unattended agent is the one with nobody to stop it.

    **A FAIL outranks an unresolved module.** If one module is refused and another has
    no registry row, this reports the refusal: a defect that has been found does not
    stop being found because something else could not be checked. Only when nothing is
    refused and something is unknown does it report NOT_RUN, because then the honest
    answer is that the Pack's tiers have not been checked rather than that they passed.
    """
    forges = {
        b.forge.lower() for b in pack.forge_dependencies.forge_bindings
    } | {pack.forge_dependencies.operating_forge.lower()}

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT lower(forge_id) AS forge_id, module_id, is_mutating,
                   idempotency_support, verification_method
            FROM forge_module_registry WHERE lower(forge_id) = ANY(%s)
            """,
            (sorted(forges),),
        )
        shapes = {
            (r["forge_id"], r["module_id"]): ModuleShape(
                is_mutating=r["is_mutating"],
                idempotency_support=r["idempotency_support"],
                verification_method=r["verification_method"],
            )
            for r in await cur.fetchall()
        }

    refusals, unresolved = unattended_writes(pack, shapes)
    if refusals:
        return False, (
            f"{_join(refusals)}. An unattended retry writes a second record of the same "
            "act, and the audit trail cannot tell the two apart afterwards. Grant it at "
            "propose, or give the module an idempotency key."
        )
    if unresolved:
        return None, (
            f"nothing verified is known about the shape of {_join(unresolved)}, so no "
            f"{UNATTENDED_TIER} grant has been checked against its module's behaviour. "
            "NOT_RUN is not a pass. Run scripts/verify_forge_modules.py, which reads "
            "is_mutating and idempotency_support from the Forge's own adapter; V6 says "
            "which modules have no row at all."
        )

    operated = sum(
        len(p.forge_modules_operated)
        for p in pack.positions_required
        if p.trust_tier_ceiling == UNATTENDED_TIER
    )
    return True, (
        f"{operated} module(s) operated at {UNATTENDED_TIER}, none of them a mutating "
        f"{UNSAFE_IDEMPOTENCY} write, each checked against a shape the Forge stated"
    )


# ------------------------------------------------ V32: conformance against the Forge

async def _v32_modules_conform(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool | None, str]:
    """Every declared module resolves against what the Forge actually dispatches.

    V6 and this rule look alike and are not the same check. V6 resolves a Pack against
    `forge_module_registry`, which is rows a human wrote — both sides are assertions,
    so it compares two claims and can find a typo. This resolves the Pack against the
    Forge's own dispatch map, which is derived: a name is in the answer if and only if
    a handler is bound to it.

    **It proves a handler is bound, and nothing further.** Not that the handler works,
    not that it does what the name says. It automates the half of the conformance
    question that was being done by hand and does not touch the other half — the
    modules that answer 200 for work that never happened are bound like any other, and
    they are caught by reading the source, in `forge_module_exclusion`.

    NOT_RUN is the expected verdict for a Forge whose adapter does not exist yet. That
    is not a defect in the Pack and it is not a pass: nothing has been checked.
    """
    from broker import forge_modules

    wanted: dict[str, set[str]] = {}
    for binding in pack.forge_dependencies.forge_bindings:
        wanted.setdefault(binding.forge.lower(), set()).update(binding.modules_expected)
    wanted = {f: m for f, m in wanted.items() if m}
    if not wanted:
        return True, "no modules declared"

    absent: list[str] = []
    unread: list[str] = []
    methods: list[str] = []
    for forge_id, modules in sorted(wanted.items()):
        answer = await forge_modules.read(conn, forge_id, candidates=modules)
        if isinstance(answer, forge_modules.Unread):
            unread.append(f"{forge_id}: {answer.reason}")
            continue
        methods.append(f"{forge_id} via {answer.method}")
        absent.extend(f"{forge_id}/{m}" for m in answer.missing(modules))

    if absent:
        # A FAIL is the right verdict when any module is absent — something is known to
        # be wrong, and that outranks not having asked. But the two facts are DIFFERENT
        # facts, and this rule used to report only the first: with several bindings, a
        # Forge that could not be asked at all was dropped from the message entirely, so
        # a red V32 read as "asked and does not dispatch" when half of it was "nobody
        # could ask". Both now travel, because a summary line that means two things is
        # how a blocker gets described one layer too shallow — twice, on this rule.
        message = (
            f"{len(absent)} declared module(s) the Forge does not dispatch: "
            f"{_join(absent)}. A grant over one of these is a grant on a capability "
            f"that is not there."
        )
        if unread:
            message += (
                f" SEPARATELY, and not covered by this failure: could not ask "
                f"{_join(unread)} — those bindings are unverified rather than verified, "
                "and fixing the modules named above will not resolve them."
            )
        return False, f"{message} ({forge_modules.SCOPE}.)"
    if unread:
        asked = f" Asked and clean: {_join(methods)}." if methods else ""
        return None, (
            f"could not ask: {_join(unread)}.{asked} Those bindings are unverified "
            "rather than verified, so the Pack's modules are not resolved against what "
            "the Forge dispatches. NOT_RUN is not a pass."
        )

    total = sum(len(m) for m in wanted.values())
    return True, (
        f"all {total} declared module(s) are dispatched by the Forge "
        f"({_join(methods)}) — {forge_modules.SCOPE}"
    )


# ----------------------------------- V33: one instruction, one content_hash

async def _v33_instructions_are_distinct(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool, str]:
    """No two live instructions on a Forge may share a `content_hash`.

    A certification is bound to `instruction_content_hash`, and that column exists to
    answer one question: certified on what, exactly. If two modules on a Forge carry the
    same hash, it cannot answer it — a certification for a property search and one for a
    deal underwrite are the same value.

    All five live `cre-forge` instructions were byte-identical, written at the same
    second by the same author, with **one** hash between them and no module's own name
    appearing anywhere in its own text. Every one said "Performs one operation against
    the Forge and returns its result", which is true of any module.
    `underwrite_deal`'s said it "does not write to any other system", and it upserts a
    `DealAnalysis` row.

    **This is the class `curriculum_quality.assess` cannot see.** That assessor was
    built to catch emptiness — `"what_it_does": "Documented."` — and rated all five
    `complete`, correctly by its own lights: it is real prose, and it does not go
    nowhere. It is simply not about any particular module, and no reading of one
    document in isolation can tell. Two documents can.

    Cheap, and it fires the day the instructions are written rather than the day
    somebody reads five of them side by side.
    """
    forges = sorted(
        {b.forge.lower() for b in pack.forge_dependencies.forge_bindings}
        | {pack.forge_dependencies.operating_forge.lower()}
    )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT lower(forge_id) AS forge_id, content_hash,
                   array_agg(module_id ORDER BY module_id) AS modules
            FROM forge_operating_instruction
            WHERE superseded_at IS NULL AND lower(forge_id) = ANY(%s)
            GROUP BY 1, 2 HAVING count(*) > 1
            """,
            (forges,),
        )
        collisions = await cur.fetchall()

    if not collisions:
        return True, "every live instruction on a bound Forge has its own content_hash"

    detail = _join(
        f"{r['forge_id']}: {_join(r['modules'])} share {r['content_hash'][:12] or '(empty)'}"
        for r in collisions
    )
    return False, (
        f"{detail}. A certification is bound to instruction_content_hash, so one hash "
        "across several modules cannot say which module an agent was certified on. "
        "Identical text for two modules also teaches nothing about either."
    )


# ----------------------------- V34: a human-held obligation needs a current discharge

async def _v34_human_held_discharged(
    conn: AsyncConnection, pack: BusinessPack
) -> tuple[bool | None, str]:
    """Every obligation declared `HumanHeld` has a discharge that is current and covers.

    **This rule is the other half of `HumanHeld` and neither ships without the other.**
    V22 counts a human-held flag as accounted for; if nothing then asked whether the
    obligation was discharged, any flag nobody wanted to write a scenario for could be
    marked human-held and V22 would go quiet. That was measured, not supposed: with the
    type landed and this rule unwritten, Burkham reached 32 PASS / 0 FAIL and Gate 2
    cleared for a venture whose referral obligation nobody had verified.

    **It carries its own verdict on purpose.** A missing discharge must never arrive as
    "a flag no scenario exercises" — that is V22's sentence and it names the wrong
    problem. Whoever reads this failure should be sent to a person, not to an author.

    **On NOT_RUN.** This rule reports NOT_RUN only when it could not ask — no database.
    An absent row is an ANSWER, and it is a FAIL. Three NOT_RUNs have been misread this
    week as "not checked yet"; a fourth that actually meant "no discharge required"
    would be the worst of them, because it would read as permission.
    """
    # Pairs rather than entries, so the declaration's type is carried instead of
    # re-asserted at each use. mypy refused the comprehension-narrowed version, and it
    # was right to: the filter and the access were two separate claims.
    held = [
        (c, c.human_held) for c in pack.market.compliance_surface
        if c.runtime_flag.strip() and c.human_held is not None
    ]
    if not held:
        # Distinguishable from a real pass. Nothing was checked because there was
        # nothing to check, and saying so is the difference between this and the
        # vacuous PASS a rule gives when its table happens to be empty.
        return True, "no obligation is declared human-held in this Pack - nothing to discharge"

    # pending_activation is the one state that passes without a discharge, because no
    # verification is due yet. It is declared on the Pack rather than derived: a clock
    # cannot know whether a partner exists. What keeps it from being an escape hatch is
    # that it carries a condition a reviewer can check - and the reviewer, not this
    # rule, is who checks it.
    pending = [(c, hh.pending_activation) for c, hh in held
               if hh is not None and hh.pending_activation is not None]
    live = [c for c, hh in held if hh is not None and hh.pending_activation is None]

    geographies = {g.strip() for g in pack.market.target_geographies if g.strip()}
    problems: list[str] = []
    async with conn.cursor(row_factory=dict_row) as cur:
        for entry in live:
            await cur.execute(
                """
                SELECT jurisdiction_scope, expires_at, discharged_by, verified_at
                  FROM obligation_discharge
                 WHERE venture_id = %s AND runtime_flag = %s AND superseded_at IS NULL
                 ORDER BY verified_at DESC
                 LIMIT 1
                """,
                (pack.venture_id, entry.runtime_flag),
            )
            row = await cur.fetchone()
            if row is None:
                problems.append(
                    f"{entry.runtime_flag}: no discharge record exists. The obligation is "
                    f"declared human-held ({entry.framework}) and nobody has verified it"
                )
                continue
            if row["expires_at"] <= datetime.now(UTC):
                problems.append(
                    f"{entry.runtime_flag}: discharge expired {row['expires_at']:%Y-%m-%d}; "
                    "verified is not the same claim as verified in the past"
                )
                continue
            scope = set(row["jurisdiction_scope"])
            if entry.jurisdiction not in ("ALL", "FEDERAL"):
                uncovered = sorted({j.strip() for j in entry.jurisdiction} - scope)
                if uncovered:
                    problems.append(
                        f"{entry.runtime_flag}: discharge covers {sorted(scope)} and the "
                        f"obligation reaches {uncovered} - not covered where it applies"
                    )
                    continue
            elif geographies - scope:
                problems.append(
                    f"{entry.runtime_flag}: jurisdiction is {entry.jurisdiction} and the "
                    f"discharge covers {sorted(scope)}; the venture operates in "
                    f"{sorted(geographies - scope)}, which it does not reach"
                )
                continue

    if problems:
        return False, "; ".join(problems)

    # Say which of the two passing states each obligation is in. A pass that cannot
    # distinguish "verified" from "not yet due" is the shape this rule exists to refuse
    # one level up.
    parts = []
    if live:
        parts.append(
            f"{len(live)} live obligation(s) carry a current discharge covering the "
            "venture's jurisdictions"
        )
    for entry, pa in pending:
        assert pa is not None
        parts.append(
            f"{entry.runtime_flag}: pending_activation - no verification is due until "
            f"{pa.activates_when} (deferred to {pa.deferred_to})"
        )
    return True, "; ".join(parts)


_WORLD_RULES = {
    "V2": (Severity.FAIL, "Bridge operational for every hard Forge binding (Gate 0)",
           _v2_bridge_operational),
    "V6": (Severity.FAIL, "Every Workflow module ref resolves in forge_module_registry",
           _v6_modules_resolve),
    "V11": (Severity.FAIL, "Every position's modules have Forge Operating Instructions",
            _v11_instructions_authored),
    "V28": (Severity.FAIL, "Every library_entry_ref resolves in the Compliance Library",
            _v28_library_refs_resolve),
    "V29": (Severity.FAIL, "Every position names a department the Village has",
            _v29_departments_exist),
    "V30": (Severity.WARN, "Every department has seats for the positions requested",
            _v30_department_has_seats),
    "V31": (Severity.FAIL, "No auto_execute grant over a mutating at_most_once module",
            _v31_unattended_writes),
    "V32": (Severity.FAIL, "Every declared module is dispatched by the Forge itself",
            _v32_modules_conform),
    "V33": (Severity.FAIL, "No two live instructions on a Forge share a content_hash",
            _v33_instructions_are_distinct),
    "V34": (Severity.FAIL,
            "Every human-held obligation has a current discharge",
            _v34_human_held_discharged),
}


# --------------------------------------------------------------------------- entry point

async def validate(
    pack: BusinessPack, conn: AsyncConnection | None = None
) -> ValidationReport:
    """Run every rule. Deterministic order, so two runs produce identical reports."""
    report = ValidationReport()
    document_rules = {r[0]: r for r in _RULES}

    for rule_id in _rule_order():
        if rule_id in _WORLD_RULES:
            severity, _desc, fn = _WORLD_RULES[rule_id]
            if conn is None:
                report.results.append(RuleResult(
                    rule_id, severity, Verdict.NOT_RUN,
                    "requires a database connection; not run. NOT_RUN is not a pass - "
                    "this Pack has not been validated against the bridge.",
                ))
                continue
            ok, message = await fn(conn, pack)
            if ok is None:
                # The rule ran and could not reach what it needed. Not a pass - the Pack
                # is unvalidated in this respect - and not a failure either, because
                # nothing about the Pack is known to be wrong.
                report.results.append(RuleResult(
                    rule_id, severity, Verdict.NOT_RUN, message,
                ))
                continue
        elif rule_id in GATE_45_RULES:
            report.results.append(RuleResult(
                rule_id, Severity.FAIL, Verdict.NOT_RUN,
                "evaluated at Gate 4.5 against appointment output, which does not "
                "exist at Gate 2.",
            ))
            continue
        else:
            _rid, severity, _desc, fn_doc = document_rules[rule_id]
            ok, message = fn_doc(pack)

        verdict = Verdict.PASS if ok else (
            Verdict.FAIL if severity is Severity.FAIL else Verdict.WARN
        )
        report.results.append(RuleResult(rule_id, severity, verdict, message))

    return report


def _rule_order() -> list[str]:
    """V1..Vn, numerically. Report order must not depend on import order."""
    ids = {r[0] for r in _RULES} | set(_WORLD_RULES) | GATE_45_RULES
    return sorted(ids, key=lambda r: int(r[1:]))


# Which Pack block each rule is about, derived from the rule's own source.
#
# The editor's block sidebar marks the blocks a failing rule lives in, and needs a map
# from rule to block to do it. A hand-written table would be right the day it was
# written: twenty-eight entries maintained beside twenty-eight functions, with nothing
# forcing them to agree, is the same shape as the blocker-string table the ventures page
# replaced for exactly this reason.
#
# A rule function names the fields it reads - `pack.budget`, `pack.positions_required` -
# so the mapping is already stated in the code that does the work. Reading it back is
# not a guess about intent; it is the same fact, from the same place.
#
# The four world rules are appended by `validate` rather than registered by the
# decorator, and are about the bridge and the registry rather than about a block, so
# they are named here with the block whose contents they check against the world.
_WORLD_RULE_BLOCKS = {
    "V2": ("forge_dependencies",),
    "V6": ("forge_dependencies",),
    "V11": ("positions_required", "forge_operating_instructions"),
    "V28": ("forge_dependencies",),
    "V24": ("positions_required",),
    "V31": ("positions_required", "forge_dependencies"),
    "V32": ("forge_dependencies",),
    "V33": ("forge_dependencies", "forge_operating_instructions"),
    "V34": ("market",),
}


@lru_cache(maxsize=1)
def rule_blocks() -> dict[str, tuple[str, ...]]:
    """rule_id -> the Pack blocks it reads. Empty tuple when it reads none."""
    fields = set(BusinessPack.model_fields)
    reads = re.compile(r"pack\.([a-z_]+)")

    out: dict[str, tuple[str, ...]] = {}
    for rule_id, _severity, _description, fn in _RULES:
        try:
            source = inspect.getsource(fn)
        except OSError:  # pragma: no cover - only when running from a zip
            source = ""
        out[rule_id] = tuple(
            sorted({name for name in reads.findall(source) if name in fields})
        )

    for rule_id, blocks in _WORLD_RULE_BLOCKS.items():
        out.setdefault(rule_id, blocks)
    return out


def all_rule_ids() -> list[str]:
    return _rule_order()


def rule_severity(rule_id: str) -> Severity:
    if rule_id in _WORLD_RULES:
        return _WORLD_RULES[rule_id][0]
    if rule_id in GATE_45_RULES:
        return Severity.FAIL
    for rid, severity, _d, _f in _RULES:
        if rid == rule_id:
            return severity
    raise KeyError(rule_id)


# ------------------------------------------------------------------------ Gate 4.5

async def validate_gate_4_5(
    pack: BusinessPack, approval_projection: Any, appointment: Any
) -> ValidationReport:
    """Gate 4.5 — capacity and budget feasibility, against real generator output.

    V13 runs at Gate 2 with only the Pack to estimate from: headcount times a
    conservative per-agent-day factor. The Task Ledger, produced at Gate 3, computes
    the actual projected approvals per human role from the real workflow.

    **The two can disagree by an order of magnitude, and the Gate 2 estimate is the
    optimistic one.** Greenstone passes V13 at Gate 2 and fails it here. That is not a
    bug in either: Gate 2 cannot see a workflow that does not exist yet, which is
    precisely why the blueprint puts a second capacity check after the generators run.

    V24 also resolves here — unfilled positions are appointment output, so Gate 2
    reported it NOT_RUN.
    """
    report = ValidationReport()

    unfilled = [
        f"{a.position_title} ({a.unfilled} of {a.headcount_required})"
        for a in appointment.appointments
        if a.unfilled
    ]
    report.results.append(
        RuleResult(
            "V24", Severity.FAIL,
            Verdict.FAIL if unfilled else Verdict.PASS,
            f"unfilled positions: {_join(unfilled)}" if unfilled
            else "every position is filled by a certified agent",
        )
    )

    coverage_by_role: dict[str, float] = {}
    # Review minutes are weighted by each person's share of their role's coverage.
    #
    # This used to be a setdefault, which meant the FIRST entry of a role set the
    # multiplier for everyone in it. Two compliance officers at six hours each, one at
    # four minutes a review and one at three, gave 480 review-minutes or 360 against 432
    # available depending purely on which line came first in the YAML - FAIL or PASS with
    # nothing on the page saying the order was the reason. Whoever alphabetised that list,
    # or moved a founder to the top out of courtesy, would have changed a gate outcome and
    # had no way to know. See blocking.md B24.
    #
    # Weighted by coverage share is what "how long does a review take here" means when two
    # people share the load, and unlike first-in-the-list it is the same answer in any
    # order. A plain mean would also be defensible; taking the first was the one option
    # nobody chose.
    weighted_minutes_by_role: dict[str, float] = {}
    coverage_weight_by_role: dict[str, float] = {}
    for human in pack.human_capacity:
        coverage_by_role[human.role] = (
            coverage_by_role.get(human.role, 0.0)
            + human.coverage_hours * 60 * UTILISATION_FACTOR
        )
        weighted_minutes_by_role[human.role] = (
            weighted_minutes_by_role.get(human.role, 0.0)
            + human.coverage_hours * human.median_review_minutes
        )
        coverage_weight_by_role[human.role] = (
            coverage_weight_by_role.get(human.role, 0.0) + human.coverage_hours
        )

    review_minutes_by_role: dict[str, float] = {}
    for role, weight in coverage_weight_by_role.items():
        if weight > 0:
            review_minutes_by_role[role] = weighted_minutes_by_role[role] / weight
        else:
            # Nobody in the role declared any coverage hours, so there is no share to
            # weight by. Fall back to the plain mean of their declared review times rather
            # than to a default: the review times are declared, it is the coverage that is
            # missing, and zero coverage is what the rule fails on below anyway.
            times = [
                h.median_review_minutes for h in pack.human_capacity if h.role == role
            ]
            review_minutes_by_role[role] = sum(times) / len(times)

    # Written as sentences rather than as a formula. The reviewer this message is for is
    # the person whose day it describes, and "192 x 6 = 1152 against 144" asks them to
    # do the arithmetic before they can tell whether it matters. The numbers all survive;
    # what changes is that they arrive inside a sentence that says what they mean.
    overloaded = []
    for role, approvals in sorted(approval_projection.projected_daily_approvals.items()):
        each = review_minutes_by_role.get(role, 5.0)
        needed = approvals * each
        available = coverage_by_role.get(role, 0.0)
        if needed > available:
            over = needed / available if available else float("inf")
            multiple = (
                "with no reviewer coverage at all" if available == 0
                else f"{over:.0f} times over" if over >= 2
                else f"{(over - 1) * 100:.0f}% over"
            )
            overloaded.append(
                f"The {role.replace('_', ' ')} would receive {approvals:,.0f} "
                f"approvals a day. At {each:g} minutes each that is "
                f"{needed:,.0f} minutes of review against "
                f"{available:,.0f} minutes available - {multiple}."
            )

    report.results.append(
        RuleResult(
            "V13", Severity.FAIL,
            Verdict.FAIL if overloaded else Verdict.PASS,
            (
                " ".join(overloaded)
                + "\n\nAbove this line trust tiers stop meaning anything: the reviewer "
                "approves without reading, and the dashboard still shows green."
                # Verbatim, and last. It closes off the obvious wrong fix - the
                # utilisation factor is the one number here somebody can change to make
                # the rule pass without changing anything real.
                + "\n\nFix by raising a trust-tier ceiling, adding reviewer coverage, "
                "or cutting scope - not by lowering the utilisation factor."
            )
            if overloaded
            else "projected approvals fit within reviewer capacity",
        )
    )

    return report
