import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle, Check, Minus, X } from "@/components/icons";
import { AsOf, Ago } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type Certification,
  type ForgeAccess,
} from "@/lib/api";

import { Revoke } from "./revoke";

export const dynamic = "force-dynamic";

/**
 * One agent.
 *
 * The list page claimed a certified tier for this agent and the detail page had no
 * certifications section at all — so the one screen that could say *which Forge* and
 * *which module* an agent was certified for did not say it. A bare "certified:
 * auto_execute" is the same failure as a green check with no denominator.
 */

type AgentDetail = {
  as_of: string;
  identity: {
    office_agent_id: string;
    agent_name: string;
    department: string;
    village_agent_ref: string | null;
    status: string;
  };
  grants: {
    grant_id: string;
    forge_id: string;
    module_id: string;
    venture_id: string;
    trust_tier: string;
    is_assignable: boolean;
    revoked_at: string | null;
    unit_a_state: string | null;
    certified_tier: string | null;
  }[];
  forge_access: ForgeAccess[];
  certifications: { unit_a: Certification[]; unit_b: Certification[] };
  recent_calls: {
    call_id: string;
    forge_id: string;
    module_id: string;
    venture_id: string;
    status_code: number;
    latency_ms: number;
    trust_tier_at_call: string;
    ts_start: string;
    trace_id: string;
  }[];
  cost: { calls: number; spend_total: string; spend_today: string };
  recent_shifts: {
    shift_id: string;
    venture_id: string;
    shift_start: string;
    shift_end: string;
    flush_verified: boolean;
  }[];
};

const CERT_TONE: Record<string, string> = {
  certified: "border-ok-line bg-ok-bg text-ok",
  stale_instructions: "border-warn-line bg-warn-bg text-warn",
  stale_forge: "border-warn-line bg-warn-bg text-warn",
  in_training: "border-line bg-surface-muted text-ink-secondary",
  never_certified: "border-line bg-surface-muted text-ink-muted",
  failed: "border-bad-line bg-bad-bg text-bad",
  revoked: "border-bad-line bg-bad-bg text-bad",
};

function Section({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">{title}</h2>
      {subtitle ? (
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">{subtitle}</p>
      ) : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** A certification, always scoped. Never a bare tier. */
function CertRow({ cert }: { cert: Certification }) {
  return (
    <li className="border-t border-line py-2">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-desc text-ink">
          {cert.forge_id}
          {cert.module_id ? ` / ${cert.module_id}` : ""}
          {cert.department ? ` · ${cert.department}` : ""}
        </span>
        <span
          className={`rounded-lg border px-2 py-0.5 text-meta ${
            CERT_TONE[cert.state] ?? "border-line bg-surface-muted text-ink-muted"
          }`}
        >
          {cert.state.replace(/_/g, " ")}
        </span>
        {cert.certified_tier ? (
          <span className="font-mono text-meta text-ink-secondary">
            {cert.certified_tier}
          </span>
        ) : null}
        <span className="ml-auto text-meta text-ink-muted">
          {cert.updated_at ? <Ago iso={cert.updated_at} /> : null}
        </span>
      </div>
      <p className="mt-0.5 text-meta text-ink-muted">
        {/* What it was earned under. A certification against a since-changed instruction
            or Forge version is stale, and the versions are how anybody can tell. */}
        {cert.instruction_content_hash ? (
          <>
            instructions{" "}
            <span className="font-mono">
              {cert.instruction_content_hash.slice(0, 12)}…
            </span>
          </>
        ) : (
          "no instruction hash recorded"
        )}
        {cert.forge_api_version ? ` · Forge ${cert.forge_api_version}` : ""}
        {cert.score !== null && cert.threshold !== null
          ? ` · scored ${cert.score} against ${cert.threshold}`
          : ""}
        {cert.simforge_verdict ? ` · ${cert.simforge_verdict}` : ""}
      </p>
    </li>
  );
}

export default async function AgentDetailPage({
  params,
}: {
  params: { agentId: string };
}) {
  let detail: AgentDetail;
  try {
    detail = await api.get<AgentDetail>(
      `/api/agents/${encodeURIComponent(params.agentId)}`,
    );
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { identity, grants, certifications } = detail;
  const live = grants.filter((grant) => grant.revoked_at === null);
  const brokered = detail.forge_access.filter(
    (forge) => forge.credential_mode === "brokered",
  );

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Agents", href: "/agents" },
          { label: identity.agent_name },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">{identity.agent_name}</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            {identity.department} · identity {identity.status}
            {identity.village_agent_ref ? (
              <code className="ml-2 text-ident text-ink-muted">
                {identity.village_agent_ref}
              </code>
            ) : null}
          </p>
        </div>
        <span className="text-meta text-ink-muted">
          <AsOf iso={detail.as_of} />
        </span>
      </div>

      {live.length === 0 ? (
        <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
          <p className="text-desc font-medium text-bad">
            No grants. This agent cannot reach any Forge.
          </p>
          {certifications.unit_a.some((cert) => cert.state === "certified") ? (
            <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
              It holds certifications. Certification makes an agent eligible; a grant is
              what lets it reach a Forge.
            </p>
          ) : null}
        </section>
      ) : null}

      <Section
        title="Certifications"
        subtitle="A grant with either certification unit missing is not assignable — certification is the grant condition, not advisory metadata. Department certification is necessary but never sufficient."
      >
        <div className="space-y-4">
          <div>
            <h3 className="text-meta text-ink-muted">
              Unit A — operation certification ({certifications.unit_a.length})
            </h3>
            <p className="mt-0.5 text-meta text-ink-muted">
              Agent × Forge × module. What this agent is certified to operate.
            </p>
            {certifications.unit_a.length ? (
              <ul className="mt-1">
                {certifications.unit_a.map((cert) => (
                  <CertRow key={`${cert.forge_id}-${cert.module_id}`} cert={cert} />
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-desc text-ink-secondary">
                No operation certification. This agent is not certified to operate any
                module on any Forge.
              </p>
            )}
          </div>

          <div>
            <h3 className="text-meta text-ink-muted">
              Unit B — department context certification ({certifications.unit_b.length})
            </h3>
            <p className="mt-0.5 text-meta text-ink-muted">
              Department × Forge × context. Necessary for assignment, never sufficient on
              its own.
            </p>
            {certifications.unit_b.length ? (
              <ul className="mt-1">
                {certifications.unit_b.map((cert) => (
                  <CertRow key={`${cert.forge_id}-${cert.department}`} cert={cert} />
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-desc text-ink-secondary">
                No department context certification for {identity.department}. Every
                grant this agent holds is unassignable until one exists.
              </p>
            )}
          </div>
        </div>
      </Section>

      <Section
        title="Forge access for this agent"
        subtitle="A Forge being healthy and this agent being able to reach it are different statements."
      >
        <ul>
          {detail.forge_access.map((forge) => (
            <li
              key={forge.forge_id}
              className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-line py-2"
            >
              <span className="font-mono text-desc text-ink">{forge.forge_id}</span>

              {/* Two facts, two columns. The old page put "cannot reach any Forge"
                  directly above three Forges marked GREEN, in one column. */}
              <span className="text-meta text-ink-muted">
                Forge health{" "}
                <span
                  className={
                    forge.health_status === "GREEN" ? "text-ok" : "text-warn"
                  }
                >
                  {forge.health_status}
                </span>
              </span>

              <span className="text-meta">
                <span className="text-ink-muted">This agent&rsquo;s access </span>
                {forge.reachable ? (
                  <span className="inline-flex items-center gap-1 text-ok">
                    <Check className="h-3 w-3" />
                    {forge.grants_here} grant{forge.grants_here === 1 ? "" : "s"}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-ink-muted">
                    <Minus className="h-3 w-3" />
                    no grant
                  </span>
                )}
              </span>

              <span className="ml-auto text-meta text-ink-muted">
                {forge.credential_mode}
              </span>
            </li>
          ))}
        </ul>
        {brokered.length ? (
          <p className="mt-3 border-t border-line pt-3 text-desc text-ink-secondary">
            Brokered means the Forge logs attribute every call to the tenant — the Office
            ledger is the only record naming this agent.
          </p>
        ) : null}
      </Section>

      <Section
        title="Grants"
        subtitle="A grant with either certification unit missing is not assignable — certification is the grant condition, not advisory metadata."
      >
        {grants.length === 0 ? (
          <p className="text-desc text-ink-secondary">
            No grants. This agent cannot reach any Forge.
          </p>
        ) : (
          <ul>
            {grants.map((grant) => (
              <li
                key={grant.grant_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2"
              >
                <span className="font-mono text-desc text-ink">
                  {grant.forge_id} / {grant.module_id}
                </span>
                <span className="text-meta text-ink-muted">{grant.venture_id}</span>
                <span className="font-mono text-meta text-ink-secondary">
                  {grant.trust_tier}
                </span>
                {grant.revoked_at ? (
                  <span className="rounded-lg border border-line bg-surface-muted px-2 py-0.5 text-meta text-ink-muted">
                    revoked <Ago iso={grant.revoked_at} />
                  </span>
                ) : grant.is_assignable ? (
                  <span className="rounded-lg border border-ok-line bg-ok-bg px-2 py-0.5 text-meta text-ok">
                    assignable
                  </span>
                ) : (
                  <span
                    className="inline-flex items-center gap-1 rounded-lg border border-bad-line bg-bad-bg px-2 py-0.5 text-meta text-bad"
                    title="Certification is the grant condition, not advisory metadata."
                  >
                    <X className="h-3 w-3" />
                    not assignable
                    {grant.unit_a_state ? ` · unit A ${grant.unit_a_state}` : " · no unit A certification"}
                  </span>
                )}
                <span className="ml-auto">
                  {grant.revoked_at === null ? (
                    <Revoke
                      officeAgentId={identity.office_agent_id}
                      grantId={grant.grant_id}
                      scope="grant"
                      label="Revoke"
                    />
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Activity"
        subtitle="Under the brokered model the Office ledger is the only record naming this agent."
      >
        {detail.recent_calls.length === 0 ? (
          <p className="text-desc text-ink-secondary">
            This agent has never called a Forge.
          </p>
        ) : (
          <ul>
            {detail.recent_calls.map((call) => (
              <li
                key={call.call_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2"
              >
                <span className="font-mono text-desc text-ink">
                  {call.forge_id} / {call.module_id}
                </span>
                <span className="text-meta text-ink-muted">{call.venture_id}</span>
                <span
                  className={`text-meta ${call.status_code >= 400 ? "text-bad" : "text-ink-muted"}`}
                >
                  {call.status_code} · {call.latency_ms}ms
                </span>
                <code className="text-ident text-ink-muted">
                  {call.trace_id.slice(0, 8)}
                </code>
                <span className="ml-auto text-meta text-ink-muted">
                  <Ago iso={call.ts_start} />
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 border-t border-line pt-3 text-meta text-ink-muted">
          {detail.cost.calls} call{detail.cost.calls === 1 ? "" : "s"} on record · $
          {Number(detail.cost.spend_total).toFixed(2)} total · $
          {Number(detail.cost.spend_today).toFixed(2)} today
        </p>
      </Section>

      <Section
        title="Shifts"
        subtitle="One venture per agent per shift. A failed PHI flush blocks the next assignment."
      >
        {detail.recent_shifts.length === 0 ? (
          <p className="text-desc text-ink-secondary">Never assigned to a shift.</p>
        ) : (
          <ul>
            {detail.recent_shifts.map((shift) => (
              <li
                key={shift.shift_id}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2"
              >
                <span className="text-desc text-ink">{shift.venture_id}</span>
                <span className="text-meta text-ink-muted">
                  <Ago iso={shift.shift_start} />
                </span>
                {shift.flush_verified ? (
                  <span className="text-meta text-ok">PHI flush verified</span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-meta text-bad">
                    <AlertTriangle className="h-3 w-3" />
                    flush not verified — blocks the next assignment
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Revocation"
        subtitle="The kill switch under the brokered model: the Forge attributes calls to the tenant, so pulling the grant is the only way to stop this agent reaching that Forge. Every scope writes an audit entry."
      >
        <div className="flex flex-wrap items-start gap-3">
          <Revoke
            officeAgentId={identity.office_agent_id}
            scope="agent"
            label={`Revoke all ${live.length} live grant${live.length === 1 ? "" : "s"}`}
          />
        </div>
        <p className="mt-3 text-meta text-ink-muted">
          Revoking is not the same as suspending the identity: a revoked grant can be
          reissued, and a suspended identity cannot hold one at all.
        </p>
      </Section>
    </div>
  );
}
