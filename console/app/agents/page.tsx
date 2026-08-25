import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle, Minus } from "@/components/icons";
import { AsOf, Ago } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type RosterAgent,
  type RosterDepartment,
  type RosterDirectory,
} from "@/lib/api";

import { Filters } from "./filters";
import { IssueIdentities, RosterSync } from "./roster-controls";

export const dynamic = "force-dynamic";

/**
 * The agent roster — Part 17.
 *
 * The old page rendered the agents holding an Office identity and stopped, with no
 * count and no indication that anybody else existed, so a reader concluded the Village
 * has seven people. The agents The Office *cannot* appoint are the most consequential
 * rows here: they are the work that has not been done.
 *
 * Every number is computed from the two tables. There is deliberately no hardcoded 106:
 * the blueprint describes a Village of that size and The Office knows what the roster
 * has told it, so an unimported roster says exactly that rather than inventing a
 * denominator — the same rule the Compliance page set.
 */

function tierLabel(agent: RosterAgent): string {
  if (agent.effective_tier) return agent.effective_tier;
  // Not a tier of zero. No Pack appoints this agent, which is a different state and
  // the one the old table rendered as a bare dash beside a populated certified tier.
  return agent.declared_tier === null && agent.certified_tier === null
    ? "no tier"
    : "not declared";
}

function AgentRow({ agent }: { agent: RosterAgent }) {
  const href = agent.office_agent_id ? `/agents/${agent.office_agent_id}` : null;

  const body = (
    <>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-rowtitle font-medium text-ink">{agent.agent_name}</span>
        {agent.village_agent_ref ? (
          <code className="text-ident text-ink-muted">{agent.village_agent_ref}</code>
        ) : null}

        {!agent.has_identity ? (
          <span className="inline-flex items-center gap-1 rounded-lg border border-line bg-surface-muted px-2 py-0.5 text-meta text-ink-secondary">
            <Minus className="h-3 w-3" />
            no identity
          </span>
        ) : null}

        {/*
          The two facts the old table showed in unrelated columns. Certification makes
          an agent eligible; a grant is what lets it reach a Forge.
        */}
        {agent.certified_without_grants ? (
          <span
            title="Certified, but holds no grant. Certification makes an agent eligible; a grant is what lets it reach a Forge."
            className="inline-flex items-center gap-1 rounded-lg border border-bad-line bg-bad-bg px-2 py-0.5 text-meta text-bad"
          >
            <AlertTriangle className="h-3 w-3" />
            no grants
          </span>
        ) : null}

        {agent.tier_inconsistent ? (
          <span
            title="Certified above the tier the Pack declares. The Pack is the ceiling, so something is inconsistent."
            className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn"
          >
            certified above ceiling
          </span>
        ) : null}

        {agent.roster_status === "departed" ? (
          <span className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
            departed the Village
          </span>
        ) : null}

        <span
          className="ml-auto font-mono text-meta text-ink-muted"
          title={`Declared ${agent.declared_tier ?? "not declared"} · certified ${agent.certified_tier ?? "none"} · effective is the lower of the two`}
        >
          {tierLabel(agent)}
        </span>
      </div>
      <p className="mt-0.5 text-meta text-ink-muted">
        {agent.has_identity ? (
          <>
            {agent.live_grants} grant{agent.live_grants === 1 ? "" : "s"} ·{" "}
            {agent.certifications} certification
            {agent.certifications === 1 ? "" : "s"} ·{" "}
            {agent.last_shift ? (
              <>
                last shift <Ago iso={agent.last_shift} />
              </>
            ) : (
              "Never assigned to a shift."
            )}
          </>
        ) : (
          "In the Village roster. No Office identity, so it cannot be appointed, granted or certified."
        )}
        {!agent.in_roster ? (
          <span className="text-warn">
            {" "}
            · no roster row — the Village has not reported this agent
          </span>
        ) : null}
      </p>
    </>
  );

  // The whole row is the target, not just the name.
  return (
    <li className="border-t border-line">
      {href ? (
        <Link href={href} className="block px-1 py-2.5 transition hover:bg-surface-muted">
          {body}
        </Link>
      ) : (
        <div className="px-1 py-2.5">{body}</div>
      )}
    </li>
  );
}

function Department({ group }: { group: RosterDepartment }) {
  if (group.agents.length === 0 && group.in_roster === 0) return null;

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="text-section font-medium text-ink">{group.department}</h3>
        <span className="text-meta text-ink-muted">
          {group.with_identity} of {group.in_roster} with identity
        </span>
      </div>

      <ul className="mt-2">
        {group.agents.map((agent) => (
          <AgentRow key={agent.village_agent_ref ?? agent.office_agent_id} agent={agent} />
        ))}
      </ul>

      {group.without_identity > 0 ? (
        <div className="mt-3 border-t border-line pt-3">
          <p className="text-meta text-ink-muted">
            {group.without_identity} agent
            {group.without_identity === 1 ? "" : "s"} in this department{" "}
            {group.without_identity === 1 ? "has" : "have"} no Office identity.
          </p>
          <IssueIdentities department={group} agents={group.agents} />
        </div>
      ) : null}
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl bg-surface-muted px-4 py-3">
      <div className="text-desc text-ink-secondary">{label}</div>
      <div className="mt-1 text-[24px] font-medium leading-tight text-ink">{value}</div>
      {note ? <p className="mt-1 text-meta text-ink-muted">{note}</p> : null}
    </div>
  );
}

export default async function AgentsPage({
  searchParams,
}: {
  searchParams: Record<string, string | undefined>;
}) {
  const query = new URLSearchParams();
  for (const key of ["search", "department", "identity", "grants"]) {
    if (searchParams[key]) query.set(key, searchParams[key] as string);
  }

  let directory: RosterDirectory;
  try {
    directory = await api.get<RosterDirectory>(
      `/api/agents/roster${query.size ? `?${query.toString()}` : ""}`,
    );
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const withIdentity = directory.with_identity;
  const rosterTotal = directory.roster_total;
  const emptyDepartments = directory.departments.filter(
    (group) => group.with_identity === 0,
  );

  return (
    <div className="space-y-6">
      <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Agents" }]} />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">Agents</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            The Office appoints agents. The Village creates them. Certified tier caps
            declared tier.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className="text-meta text-ink-muted">
            <AsOf iso={directory.as_of} />
          </span>
          <RosterSync departments={directory.all_departments} />
        </div>
      </div>

      {/*
        The roster gap, stated. Deliberately not "7 of 106": the blueprint describes a
        Village of 106 and this database knows what the roster has told it. Reporting a
        denominator nothing here can support would be inventing one — so an unimported
        roster says so, and says what that means.
      */}
      <section className="rounded-xl border border-warn-line bg-warn-bg px-5 py-4">
        <h2 className="text-section font-medium text-warn">
          {directory.roster_imported
            ? `${withIdentity} of ${rosterTotal} Village agents hold an Office identity`
            : "No Village roster has been imported"}
        </h2>
        <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
          {directory.roster_imported ? (
            <>
              The other {directory.without_identity} exist in the Village but cannot be
              appointed, granted, or certified until an identity is issued.
            </>
          ) : (
            <>
              {withIdentity} agent{withIdentity === 1 ? "" : "s"} hold an Office identity.
              How many the Village has is not recorded here — this page will not report a
              denominator it cannot support. Sync the roster to find out, and to see who
              cannot yet be appointed.
            </>
          )}
          {directory.unmatched_identities > 0 ? (
            <>
              {" "}
              {directory.unmatched_identities} identit
              {directory.unmatched_identities === 1 ? "y has" : "ies have"} no roster row:
              The Office has appointed {directory.unmatched_identities === 1 ? "an agent" : "agents"}{" "}
              the Village has not reported.
            </>
          ) : null}
        </p>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Certified and free"
          value={`${directory.capacity.certified_and_free} of ${withIdentity}`}
          note="Certified, holding no grant"
        />
        <Metric
          label="Holding grants"
          value={`${directory.capacity.holding_grants} of ${withIdentity}`}
        />
        <Metric
          label="Not yet certified"
          value={`${directory.capacity.not_yet_certified} of ${withIdentity}`}
        />
        <Metric
          label="No Office identity"
          value={`${directory.capacity.no_identity} of ${rosterTotal || withIdentity}`}
          note="In the Village, not appointable"
        />
      </div>

      <Filters
        departments={directory.all_departments}
        current={{
          search: searchParams.search ?? "",
          department: searchParams.department ?? "",
          identity: searchParams.identity ?? "",
          grants: searchParams.grants ?? "",
        }}
      />

      <div className="space-y-4">
        {directory.departments.map((group) => (
          <Department key={group.department} group={group} />
        ))}
      </div>

      {/*
        Departments with nobody. A page that renders the departments it found cannot say
        which it did not, and "no agent in Infrastructure & Cybersecurity has reached
        The Office" is a staffing fact rather than an absence of data.
      */}
      {emptyDepartments.length ? (
        <section className="rounded-xl bg-surface-muted px-5 py-4">
          <h2 className="text-section font-medium text-ink">
            {emptyDepartments.length} of {directory.departments_total} departments have
            no agent with an Office identity
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Nothing in these departments can be appointed to a position, so a Pack that
            names one of them in <code className="text-ident">source_department</code>{" "}
            has nobody to fill it.
          </p>
          <ul className="mt-3 grid gap-1 sm:grid-cols-2">
            {emptyDepartments.map((group) => (
              <li key={group.department} className="text-desc text-ink-secondary">
                {group.department}
                <span className="text-ink-muted">
                  {group.in_roster
                    ? ` — ${group.in_roster} in the Village roster, none appointed`
                    : " — nobody in the roster either"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
