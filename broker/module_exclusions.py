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

    Once CapitalForge has an adapter, its dispatch map is the naming authority and the
    accident stops being possible: a Pack, these exclusions and the registry rows all
    resolve against `GET {base_url}/_modules`, so a second spelling fails to resolve
    instead of quietly working. Until then these names are the vocabulary, and the
    adapter should be built to use them. See `broker/forge_modules.py`.
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
    # ------------------------------------------------- attributed, not read
    ModuleExclusion(
        "capitalforge",
        "readiness_score",
        "attributed to a subject it never consulted: GET /api/readiness/:businessId "
        "reads the path parameter only to log it and to stamp the response. The score "
        "is computed from QUERY PARAMETERS the caller supplies - allConsentsGranted, "
        "allAcknowledgmentsSigned, kybVerified, compliancePassed, ficoScore - none of "
        "which are checked against the consent, acknowledgment, KYB or compliance "
        "records that exist. An agent granted this receives a readiness assessment for "
        "a named client that is a restatement of what the agent itself asserted, and "
        "the response carries the businessId as though the business had been read. "
        "Declared in the Burkham Wickmont Pack at hard criticality.",
        "capitalforge: api/routes/readiness.routes.ts:41 (param read) vs :51-68 "
        "(client built from req.query) vs :74,:82 (businessId stamped onto the "
        "response). The handler's own comment: 'ASSUMPTION: In a full implementation "
        "this would fetch business data from Prisma.'",
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
        "spend_evidence_export",
        "fabricated: POST /api/spend-governance/export-evidence returned a SPEND "
        "GOVERNANCE EVIDENCE REPORT whose every figure was written into the handler - "
        "142 transactions reviewed, three violations naming Best Buy at $249.99, "
        "Western Union at $500.00 and a crypto merchant at $1,200.00 'pending review', "
        "plus coverage percentages. It took no request parameters at all, so it was the "
        "same document for every tenant and every client. A report titled EVIDENCE is "
        "what goes to an auditor or a regulator, and this one asserted an open "
        "compliance item that does not exist about transactions that never happened. "
        "Refused 2026-09-01; excluded because the module must not become grantable if "
        "the endpoint is rebuilt without the data behind it. Note the rest of that "
        "router is real - only the document summarising it was invented, which is the "
        "pattern in all five found so far: the export is the last thing anybody "
        "rebuilds.",
        "capitalforge: api/routes/spend-governance.routes.ts "
        "(POST /export-evidence). Fixed in 510b6d8. Related but NOT excluded: "
        "assemble_evidence maps to complaints.routes.ts export-dossier, which reads "
        "real rows via RegulatorResponseService.",
    ),
    ModuleExclusion(
        "capitalforge",
        "rewards_export",
        "fabricated: exported a client-facing 'REWARDS PORTFOLIO REPORT' asserting "
        "124,500 Amex points, 89,200 Chase points, $312.47 cash back and a $3,206.72 "
        "total - written into the handler, identical for every client, with no tenant "
        "check on the client id. Its own sibling GET /points-balances was already a 501 "
        "because nothing records a balance. Refused 2026-09-01; excluded because a "
        "document asserting a balance is the worst shape this can take, and the module "
        "must not become grantable if somebody rebuilds the endpoint without the data "
        "behind it.",
        "capitalforge: api/routes/rewards.routes.ts (POST /:clientId/export). Fixed in "
        "ffd6b25; compare api/routes/card-benefits.routes.ts:238 for a real one.",
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
