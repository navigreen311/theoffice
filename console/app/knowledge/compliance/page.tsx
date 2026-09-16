import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { api, NotAuthenticated } from "@/lib/api";

import { ComplianceEntryForm } from "../forms";
import { KnowledgeTabs } from "../tabs";

export const dynamic = "force-dynamic";

/**
 * The compliance library.
 *
 * This is one of the two knowledge bases that block Gate 6, and the reason is in the
 * copy: a flag with no entry reaches the agent as a label rather than a constraint. The
 * Pack can declare `tsr_disclosure_required` all it likes; without an entry saying what
 * the agent must do differently, nothing changes about how it behaves.
 */

type Entry = {
  venture_id: string;
  entry_ref: string;
  framework: string;
  jurisdiction: string;
  runtime_flag: string;
  applicability_rule: string;
  agent_behavior_implication: string;
  escalation_trigger: string;
  citation: string;
  status: string;
  counsel_reviewed_at: string | null;
};

/**
 * What an entry's own standing is, said in the list rather than left to be assumed.
 *
 * Until migration 0039 the table had no `status` column at all, so an entry tagged
 * `draft_pending_claim_library_approval` in its file - written by hand, its central
 * claim recorded by its own author as a contradiction between two artifacts, counsel
 * review deferred - rendered here exactly like one taken from a statute. An entry no
 * lawyer has reviewed must never read as settled.
 */
function standing(entry: Entry): { label: string; tone: string } | null {
  if (entry.status !== "approved") {
    return { label: "DRAFT", tone: "border-warn text-warn" };
  }
  if (!entry.counsel_reviewed_at) {
    return { label: "NO COUNSEL REVIEW", tone: "border-line text-ink-muted" };
  }
  return null;
}

export default async function CompliancePage({
  searchParams,
}: {
  searchParams: { framework?: string; jurisdiction?: string };
}) {
  let entries: Entry[];
  try {
    entries = await api.get<Entry[]>("/api/knowledge/compliance");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const frameworks = [...new Set(entries.map((entry) => entry.framework))].sort();
  const jurisdictions = [...new Set(entries.map((entry) => entry.jurisdiction))].sort();

  const visible = entries.filter(
    (entry) =>
      (!searchParams.framework || entry.framework === searchParams.framework) &&
      (!searchParams.jurisdiction || entry.jurisdiction === searchParams.jurisdiction),
  );

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Knowledge", href: "/knowledge" },
          { label: "Compliance" },
        ]}
      />

      <div>
        <h1 className="text-page font-medium text-ink">Compliance Library</h1>
        <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
          A flag with no entry reaches the agent as a label, not a constraint.
        </p>
      </div>

      <KnowledgeTabs />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <form className="flex flex-wrap items-end gap-3">
          <label className="text-meta text-ink-muted">
            Framework
            <select
              name="framework"
              defaultValue={searchParams.framework ?? ""}
              className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            >
              <option value="">All {frameworks.length}</option>
              {frameworks.map((framework) => (
                <option key={framework} value={framework}>
                  {framework}
                </option>
              ))}
            </select>
          </label>
          <label className="text-meta text-ink-muted">
            Jurisdiction
            <select
              name="jurisdiction"
              defaultValue={searchParams.jurisdiction ?? ""}
              className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            >
              <option value="">All {jurisdictions.length}</option>
              {jurisdictions.map((jurisdiction) => (
                <option key={jurisdiction} value={jurisdiction}>
                  {jurisdiction}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
          >
            Filter
          </button>
          <span className="pb-1.5 text-meta text-ink-muted">
            {visible.length} of {entries.length} entries
          </span>
        </form>

        <ul className="mt-4">
          {visible.map((entry) => (
            <li
              key={`${entry.venture_id}/${entry.entry_ref}`}
              className="border-t border-line py-2.5"
            >
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <code className="text-ident text-ink">{entry.entry_ref}</code>
                <span className="font-mono text-meta text-ink-muted">
                  {entry.venture_id}
                </span>
                {standing(entry) && (
                  <span
                    className={`rounded-lg border px-2 py-0.5 font-mono text-meta ${
                      standing(entry)!.tone
                    }`}
                  >
                    {standing(entry)!.label}
                  </span>
                )}
                <span className="rounded-lg border border-line bg-surface-muted px-2 py-0.5 font-mono text-meta text-ink-secondary">
                  {entry.framework}
                </span>
                <span className="text-meta text-ink-muted">{entry.jurisdiction}</span>
                <span className="ml-auto font-mono text-meta text-ink-muted">
                  {entry.runtime_flag}
                </span>
              </div>
              <p className="mt-1 text-desc text-ink-secondary">
                {entry.agent_behavior_implication}
              </p>
              <p className="mt-0.5 text-meta text-ink-muted">
                Escalates when: {entry.escalation_trigger}
              </p>
            </li>
          ))}
          {visible.length === 0 ? (
            <li className="py-2 text-desc text-ink-secondary">
              No entry matches this filter.
            </li>
          ) : null}
        </ul>
      </section>

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Write an entry</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Six required fields. The two that matter most are what the agent must do
          differently and what sends it to a human — an entry without them is a citation.
        </p>
        <div className="mt-3">
          <ComplianceEntryForm
            knownFlags={[...new Set(entries.map((entry) => entry.runtime_flag))]}
          />
        </div>
      </section>
    </div>
  );
}
