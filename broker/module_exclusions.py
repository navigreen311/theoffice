"""Modules that must never be granted, and the evidence for each.

Declared here rather than only in the database, for the same reason
`forge_map.ESTATE` is declared beside its code: a table can say what was recorded,
and cannot say what was found. These are findings about a Forge's source, and they
need to be reviewable in a diff, with the file and symbol that justify them, by
somebody deciding whether an exclusion still holds.

`scripts/apply_module_exclusions.py` writes these into `forge_module_exclusion`,
where the BEFORE INSERT trigger on `agent_forge_grant` enforces them.

THREE SHAPES, ONE FAILURE
=========================

    Every module below returns a plausible success for work that does not happen.
    An agent granted one gets a 200, and The Office writes a ledger row saying a
    call was made - which is true, and which reads afterwards as evidence that the
    work was done. It was not.

    inert       persists or records something no runner ever consumes
    stubbed     calls a stub client that fabricates a third-party response
    refuses     answers 501 by design

NOTE ON NAMES
=============

    CapitalForge is not onboarded, so these `module_id` values do not exist in any
    registry yet. Recording the exclusion first fixes the vocabulary: whoever writes
    `forge_module_registry` rows for CapitalForge must use these names for these
    endpoints, or the exclusion silently misses and the endpoint becomes grantable
    under a different name. That is the one way this can be defeated by accident.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModuleExclusion:
    forge_id: str
    module_id: str
    reason: str
    evidence: str


#: CapitalForge. Endpoint paths are as at capitalforge@c73318c.
CAPITALFORGE: tuple[ModuleExclusion, ...] = (
    # ---------------------------------------------------------------- inert
    ModuleExclusion(
        "capitalforge",
        "platform_workflow_create",
        "inert: POST /api/platform/workflows persists a WorkflowRule that no scheduler, "
        "runner or cron consumes. Worse, it writes conditions as {expression: string} "
        "while the engine reads them as RuleCondition[] and calls .every() - one such "
        "row makes workflow_evaluate throw for every rule in that tenant.",
        "capitalforge: api/routes/platform.routes.ts:684 (write shape) vs "
        "services/workflow-engine.service.ts:212,279 (read shape). The platform's own "
        "GET /workflows returns execution: {runs: false}. "
        "Filed as navigreen311/Capitalforge#81.",
    ),
    ModuleExclusion(
        "capitalforge",
        "platform_workflow_update",
        "inert: PATCH /api/platform/workflows/:id sets isActive on a rule nothing "
        "runs. It does not rewrite conditions or actions, so it cannot introduce the "
        "shape that breaks evaluation - but it can re-activate a row carrying it.",
        "capitalforge: api/routes/platform.routes.ts:740 -> setWorkflowActive. "
        "Filed as navigreen311/Capitalforge#81.",
    ),
    ModuleExclusion(
        "capitalforge",
        "platform_workflow_toggle",
        "inert: PATCH /api/platform/workflows/:id/toggle flips isActive on a rule "
        "nothing runs, and can re-activate a row that breaks evaluation.",
        "capitalforge: api/routes/platform.routes.ts:752. "
        "Filed as navigreen311/Capitalforge#81.",
    ),
    # --------------------------------------------------------------- stubbed
    ModuleExclusion(
        "capitalforge",
        "voice_call_initiate",
        "stubbed: records a CallRecord and dials nobody. VoiceForgeService uses a "
        "TwilioStubClient declared inside itself, which logs and returns fabricated "
        "SIDs. The production Twilio client exists and is imported only by the SMS "
        "path. A call 'placed' here reaches no telephone.",
        "capitalforge: services/voiceforge.service.ts:157 (TwilioStubClient), :216 "
        "(the service instantiates it), :257 (createCall). Contrast "
        "services/sms-dispatch.service.ts, which imports the real client.",
    ),
    ModuleExclusion(
        "capitalforge",
        "voice_call_end",
        "stubbed: terminates a call that was never placed. Same stub client.",
        "capitalforge: services/voiceforge.service.ts:172 (updateCall).",
    ),
    ModuleExclusion(
        "capitalforge",
        "outreach_apr_expiry",
        "stubbed: fans a campaign across a cohort through the same stub client. Reads "
        "as the highest-blast-radius module in the Forge and contacts no one.",
        "capitalforge: api/routes/voiceforge.routes.ts:271 -> services/voiceforge.service.ts:157.",
    ),
    ModuleExclusion(
        "capitalforge",
        "outreach_restack",
        "stubbed: as outreach_apr_expiry.",
        "capitalforge: api/routes/voiceforge.routes.ts (POST /voiceforge/outreach/restack).",
    ),
    # --------------------------------------------------------------- refuses
    ModuleExclusion(
        "capitalforge",
        "disclosure_file",
        "refuses 501: nothing files a disclosure - no submission path and no table.",
        "capitalforge: api/routes/compliance.routes.ts (POST /compliance/disclosures/:id/file); "
        "docs/specification.md section 2.",
    ),
    ModuleExclusion(
        "capitalforge",
        "decline_reminder_send",
        "refuses 501: nothing schedules or delivers reapply reminders.",
        "capitalforge: api/routes/decline-actions.routes.ts (POST /declines/:id/reminder).",
    ),
    ModuleExclusion(
        "capitalforge",
        "offboarding_stage_advance",
        "refuses 501: stage moves when the export or task completes, not directly.",
        "capitalforge: api/routes/platform-offboarding.routes.ts (PATCH /:id/advance).",
    ),
    ModuleExclusion(
        "capitalforge",
        "billing_overdue_reminders_send",
        "refuses 501: nothing queues or sends overdue reminders.",
        "capitalforge: api/routes/platform.routes.ts (POST /billing/send-overdue-reminders).",
    ),
    ModuleExclusion(
        "capitalforge",
        "integration_connect",
        "refuses 501: previously answered 200 reporting connected, from a held value.",
        "capitalforge: api/routes/platform.routes.ts (POST /integrations/:id/connect).",
    ),
    ModuleExclusion(
        "capitalforge",
        "integration_test",
        "refuses 501: as integration_connect.",
        "capitalforge: api/routes/platform.routes.ts (POST /integrations/:id/test).",
    ),
    ModuleExclusion(
        "capitalforge",
        "crm_mrr_trend",
        "refuses 501.",
        "capitalforge: GET /platform/crm/mrr-trend; docs/specification.md section 2.",
    ),
    ModuleExclusion(
        "capitalforge",
        "rewards_points_balances",
        "refuses 501: nothing records points or cash back.",
        "capitalforge: api/routes/rewards.routes.ts (GET /rewards/:clientId/points-balances).",
    ),
    ModuleExclusion(
        "capitalforge",
        "statement_anomaly_dismiss",
        "refuses 501: anomalies are derived at read time and carry no identifier, so a "
        "dismissal cannot be recorded against one.",
        "capitalforge: api/routes/statements.routes.ts (POST /anomalies/:id/dismiss).",
    ),
    ModuleExclusion(
        "capitalforge",
        "statement_anomaly_step",
        "refuses 501: as statement_anomaly_dismiss.",
        "capitalforge: api/routes/statements.routes.ts (POST /anomalies/:id/steps/:step).",
    ),
)

#: Every declared exclusion, across every Forge.
ALL: tuple[ModuleExclusion, ...] = CAPITALFORGE
