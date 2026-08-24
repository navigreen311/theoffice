"""Starting documents for a new Business Pack.

A template is **not** a working Pack. It is the schema with its shape visible and its
venture-specific values left empty, so an operator authors against the real structure
instead of a blank textarea and a copy of the spec.

Two rules govern what goes in one.

**Nothing venture-specific is guessed.** Every field whose value depends on the venture
carries `REPLACE_ME`, and every number that depends on the venture is zero. A template
that shipped a plausible budget would produce a Pack that passes V18 with a figure
nobody chose - which is worse than one that fails it, because the failure is the thing
that makes somebody set it. The template is meant to fail the validator loudly, and the
Packs page renders that failure as the reason the Pack cannot provision.

**Every choice defaults to its safe end.** `sandbox` rather than production, `suggest`
rather than auto_execute, `halt` rather than degrade, `fail_closed` rather than queue,
`distinct_humans` rather than one signer. An unfinished Pack that reached a run anyway
must not be able to be more permissive than the operator intended, and the way to
guarantee that is to make the unedited value the strictest one rather than the
convenient one.

What a template *does* carry is the compliance surface for its category, because that
does not depend on the venture - a healthcare staffing venture is under HIPAA whoever
runs it. It is carried with `library_gap: true`, so the frameworks are declared and
simultaneously marked as not yet backed by a library entry.
"""

from __future__ import annotations

from typing import Any

import yaml

from broker.ventures import PORTFOLIO

PLACEHOLDER = "REPLACE_ME"

# When a framework applies is a legal question about the venture, not a fact about the
# framework - so the template names the framework and leaves the condition blank.
_FRAMEWORK_FLAGS = {
    "HIPAA": "phi_in_scope",
    "HCQC": "clinical_credentialing_in_scope",
    "TILA": "consumer_credit_in_scope",
    "FCRA": "consumer_report_in_scope",
    "ECOA": "credit_decisioning_in_scope",
    "UDAAP": "consumer_facing_in_scope",
    "CROA": "credit_repair_in_scope",
    "FTC_TSR": "outbound_telemarketing_in_scope",
    "TWO_PARTY_CONSENT_RECORDING": "call_recording_in_scope",
    "VOICE_CLONING_CONSENT": "synthetic_voice_in_scope",
    "NRS_648_NV": "private_investigation_in_scope",
}


def categories() -> list[dict[str, Any]]:
    """The template catalogue, derived from the portfolio rather than listed again.

    A category exists because a venture in the portfolio has it. Maintaining a second
    list here would let the two disagree, and the one that disagreed would be this one.
    """
    seen: dict[str, dict[str, Any]] = {}
    for venture in PORTFOLIO:
        category = str(venture["category"])
        if category not in seen:
            seen[category] = {
                "category": category,
                "frameworks": list(venture.get("frameworks") or []),
                "example": venture["slug"],
            }
    return sorted(seen.values(), key=lambda c: str(c["category"]))


def skeleton(
    category: str, *, venture_name: str = PLACEHOLDER, legal_entity: str = PLACEHOLDER
) -> str:
    """A schema-complete, deliberately invalid Pack for `category`.

    It parses - so it can be stored as a draft and validated - and it fails, so the
    Packs page can name exactly which fields still need a decision.
    """
    known = {c["category"]: c for c in categories()}
    frameworks = [str(f) for f in (known.get(category, {}).get("frameworks") or [])]

    body: dict[str, Any] = {
        "schema_version": 3,
        "identity": {
            "venture_name": venture_name,
            "legal_entity": legal_entity,
            "operating_status": "launching",
            "category": category,
            "positioning_one_liner": PLACEHOLDER,
        },
        # Safe end: a new Pack provisions against sandbox tenants until somebody
        # deliberately changes this line.
        "environment": "sandbox",
        "market": {
            "target_personas": [PLACEHOLDER],
            "target_geographies": [PLACEHOLDER],
            "compliance_surface": [
                {
                    "framework": framework,
                    "jurisdiction": [PLACEHOLDER],
                    "applies_when": PLACEHOLDER,
                    "runtime_flag": _FRAMEWORK_FLAGS.get(framework, PLACEHOLDER),
                    # Declared and simultaneously marked as unbacked. Gate 3 reads this.
                    "library_gap": True,
                }
                for framework in frameworks
            ],
        },
        "engagement_model": {
            "service_lines": [
                {
                    "service_line_name": PLACEHOLDER,
                    # Three, because the schema floors this list at three - a
                    # placeholder still has to be a well-formed document.
                    "lifecycle_stages": [
                        f"{PLACEHOLDER}_stage_1",
                        f"{PLACEHOLDER}_stage_2",
                        f"{PLACEHOLDER}_stage_3",
                    ],
                    "pricing_structure": "project",
                    "revenue_model": "project",
                }
            ],
            "conversion_events": [PLACEHOLDER],
            "disqualification_criteria": [PLACEHOLDER],
            "out_of_scope_at_launch": [PLACEHOLDER],
        },
        "positions_required": [
            {
                "position_title": PLACEHOLDER,
                "reports_to": PLACEHOLDER,
                "duties": [PLACEHOLDER],
                "forge_modules_operated": [PLACEHOLDER],
                "source_department": PLACEHOLDER,
                "compliance_flags_in_scope": [
                    _FRAMEWORK_FLAGS.get(f, PLACEHOLDER) for f in frameworks
                ],
                # One, not zero: the schema floors headcount at one, and a position
                # with nobody in it is not a position. This is the schema's decision
                # rather than a guess about the venture.
                "headcount": 1,
                # Safe end: the lowest tier the schema allows. An agent appointed from
                # an unedited template can execute nothing and propose nothing.
                "trust_tier_ceiling": "suggest",
            }
        ],
        "capacity_demand": {
            "agent_days_per_week": 0,
            "peak_concurrent_positions": 0,
            "shift_pattern": PLACEHOLDER,
        },
        "forge_dependencies": {
            "operating_forge": PLACEHOLDER,
            "forge_bindings": [
                {
                    "forge": PLACEHOLDER,
                    "api_version": PLACEHOLDER,
                    "criticality": "hard",
                    "cost_center": PLACEHOLDER,
                    "credential_mode": "brokered",
                    "fallback_behavior": "halt",
                }
            ],
        },
        # Zero, not a plausible number. V18 fails on a non-positive cap, and that
        # failure is the mechanism that makes somebody choose a real one.
        "budget": {
            "monthly_usd_cap": 0,
            "per_agent_usd_daily_cap": 0,
            "per_task_usd_ceiling": 0,
            "cost_alert_recipients": [PLACEHOLDER],
            "hard_cap_action": "pause",
        },
        "human_capacity": [
            {
                "human_name": PLACEHOLDER,
                "role": PLACEHOLDER,
                "coverage_hours": 0,
                "timezone": PLACEHOLDER,
                "max_daily_approvals": 0,
                "auth_method": "sso_mfa",
            }
        ],
        "separation_of_duties": {"gate_signoff_policy": "distinct_humans"},
        "availability": {
            "office_unreachable_behavior": "halt",
            "audit_write_failure_behavior": "fail_closed",
            "rto_minutes": 0,
            "rpo_minutes": 0,
        },
        "lifecycle": {
            "teardown_policy": {
                "forge_tenant_disposition": PLACEHOLDER,
                "audit_log_disposition": PLACEHOLDER,
                "phi_disposition": PLACEHOLDER,
                "teardown_signoff_required": True,
            }
        },
    }

    header = (
        f"# BUSINESS PACK TEMPLATE - {category} - schema_version: 3\n"
        "#\n"
        f"# Every {PLACEHOLDER} and every zero is a decision nobody has made yet. This\n"
        "# document parses, so it can be saved as a draft and validated, and it FAILS\n"
        "# validation on purpose - the failing rules on the Packs page are the list of\n"
        "# what is still missing.\n"
        "#\n"
        "# Defaults are the safe end of every choice: sandbox, suggest, halt,\n"
        "# fail_closed, distinct_humans. An unedited template cannot be more permissive\n"
        "# than you intended.\n"
        "#\n"
        "# A draft cannot provision: packs.live does not return it, so Gate 1 cannot\n"
        "# find it and nothing downstream can generate from it.\n\n"
    )
    return header + yaml.safe_dump(body, sort_keys=False, width=88, allow_unicode=True)


__all__ = ["PLACEHOLDER", "categories", "skeleton"]
