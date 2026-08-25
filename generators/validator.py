"""The Pack Validator — Gate 2 of the provisioning pipeline.

27 rules. Any FAIL blocks provisioning; WARN is reported and does not.

Three things about the design are load-bearing:

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
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
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
        for r in self.results:
            if r.verdict is not Verdict.PASS:
                lines.append(f"  {r.rule_id} {r.verdict.value}: {r.message}")
        return "\n".join(lines)


# Rules that cannot be answered from the document alone.
NEEDS_WORLD = {"V2", "V6", "V11", "V28"}

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
        "optimistic one.",
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
    from generators.pack import VILLAGE_DEPARTMENTS

    bad = []
    for p in pack.positions_required:
        if not p.forge_modules_operated:
            bad.append(f"{p.position_title}: no modules")
        if p.source_department not in VILLAGE_DEPARTMENTS:
            bad.append(f"{p.position_title}: {p.source_department!r} is not a Village department")
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
    # Every position below auto_execute produces approvals. One per headcount per
    # agent-day is the deliberately conservative estimate: under-estimating here
    # produces a green check on a reviewer who is already saturated.
    approvals = sum(
        p.headcount for p in pack.positions_required if p.trust_tier_ceiling != "auto_execute"
    ) * max(1.0, pack.capacity_demand.agent_days_per_week / 7.0)

    minutes_needed = sum(
        h.median_review_minutes for h in pack.human_capacity
    ) / max(len(pack.human_capacity), 1) * approvals

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
    missing = sorted(declared - exercised)
    return (not missing,
            f"runtime flag(s) never exercised by a scenario: {_join(missing)}" if missing
            else f"all {len(declared)} compliance flag(s) exercised")


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
) -> tuple[bool, str]:
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
    """
    from broker.curriculum_quality import assess

    modules = {m for p in pack.positions_required for m in p.forge_modules_operated}
    if not modules:
        return True, "no modules operated"

    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT module_id, content FROM forge_operating_instruction "
            "WHERE superseded_at IS NULL"
        )
        live = {r[0]: r[1] for r in await cur.fetchall()}

    missing = sorted(modules - set(live))
    if missing:
        return False, f"no Forge Operating Instructions authored for: {_join(missing)}"

    hollow = sorted(
        module for module in modules
        if assess(live[module])["teaches_nothing"]
    )
    if hollow:
        return False, (
            f"instructions exist but teach nothing for: {_join(hollow)}. A content_hash "
            "computed over placeholder text is a valid hash of nothing, and every "
            "certification bound to it inherits that emptiness."
        )

    thin = sorted(
        module for module in modules if assess(live[module])["state"] == "thin"
    )
    detail = f" ({_join(thin)} thin)" if thin else ""
    return True, f"instructions authored for all {len(modules)} module(s){detail}"


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
    return (
        not missing,
        f"[COMPLIANCE LIBRARY GAP] {len(missing)} of {len(refs)} ref(s) resolve to "
        f"nothing: {_join(missing)}. Write the entry, or set library_gap so the Pack "
        "stops claiming coverage it does not have."
        if missing
        else f"{len(found)} of {len(refs)} library ref(s) resolve",
    )


_WORLD_RULES = {
    "V2": (Severity.FAIL, "Bridge operational for every hard Forge binding (Gate 0)",
           _v2_bridge_operational),
    "V6": (Severity.FAIL, "Every Workflow module ref resolves in forge_module_registry",
           _v6_modules_resolve),
    "V11": (Severity.FAIL, "Every position's modules have Forge Operating Instructions",
            _v11_instructions_authored),
    "V28": (Severity.FAIL, "Every library_entry_ref resolves in the Compliance Library",
            _v28_library_refs_resolve),
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
    pack: BusinessPack, task_ledger: Any, appointment: Any
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
    review_minutes_by_role: dict[str, float] = {}
    for human in pack.human_capacity:
        coverage_by_role[human.role] = (
            coverage_by_role.get(human.role, 0.0)
            + human.coverage_hours * 60 * UTILISATION_FACTOR
        )
        review_minutes_by_role.setdefault(human.role, human.median_review_minutes)

    # Written as sentences rather than as a formula. The reviewer this message is for is
    # the person whose day it describes, and "192 x 6 = 1152 against 144" asks them to
    # do the arithmetic before they can tell whether it matters. The numbers all survive;
    # what changes is that they arrive inside a sentence that says what they mean.
    overloaded = []
    for role, approvals in sorted(task_ledger.projected_daily_approvals.items()):
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
