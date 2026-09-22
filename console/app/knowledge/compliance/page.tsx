import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { api, NotAuthenticated } from "@/lib/api";

import {
  ApproveEntryForm,
  ComplianceEntryForm,
  CounselReviewForm,
} from "../forms";
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
  counsel_reviewer_name: string | null;
  counsel_reviewer_firm: string | null;
  counsel_claims_confirmed: string[] | null;
  approved_by: string | null;
  relied_on: boolean;
  deferred_under_simulation: boolean;
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

/**
 * The standing mark is unchanged under simulation, and this is the second mark.
 *
 * Entry 166: in simulation an unreviewed entry is recorded as deliberately DEFERRED —
 * not verified. It is still a draft and still nothing relies on it, so DRAFT stays on
 * screen beside this. Replacing one with the other would make a declaration of
 * simulation read as an entry somebody approved, which is the confusion entry 165 was
 * written to end arriving through a different door.
 */
function deferral(entry: Entry): { label: string; tone: string } | null {
  return entry.deferred_under_simulation
    ? { label: "DEFERRED — SIMULATION", tone: "border-line text-ink-secondary" }
    : null;
}

/**
 * What the standing COSTS, which the mark alone does not say.
 *
 * Ruled 22 September 2026, entry 165: an entry is relied on only when approved and
 * counsel-reviewed, and anything treating a draft as authoritative refuses. So a DRAFT
 * mark is no longer a caveat on an entry that still works - the entry does not work,
 * and a reader who has only the mark has to already know that to act on it.
 */
function consequence(entry: Entry): string | null {
  if (entry.relied_on) return null;
  const missing =
    entry.status !== "approved" && !entry.counsel_reviewed_at
      ? "It is neither approved nor counsel-reviewed"
      : entry.status !== "approved"
        ? "Nobody has approved it"
        : "No counsel review is recorded";
  if (entry.deferred_under_simulation) {
    return `${missing}, and nothing relies on it. ${entry.venture_id} is in simulation, so this is recorded as a deliberate deferral rather than failing Gate 2 or Gate 6 — deferred, never verified. Leaving simulation makes it fail again immediately.`;
  }
  return `${missing}, so nothing relies on it: Gate 2 refuses a Pack citing this ref, and Gate 6 does not count its flag as explained.`;
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

  // What each form can offer. Computed from the same list the page renders, so a form
  // cannot offer an entry the page does not show or miss one it does.
  const choice = (entry: Entry) => ({
    venture_id: entry.venture_id,
    entry_ref: entry.entry_ref,
  });
  const unapproved = entries.filter((e) => e.status !== "approved").map(choice);
  const unreviewed = entries.filter((e) => !e.counsel_reviewed_at).map(choice);

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
          A flag with no entry reaches the agent as a label, not a constraint. Since
          entry 165 an entry is relied on only once it is approved by somebody other
          than its author and a counsel review is recorded; until both, nothing reads
          it. In a venture declared in simulation the same entry is recorded as a
          deliberate deferral rather than failing its gates — deferred, never verified,
          and never enough for an attestation.
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
                {[standing(entry), deferral(entry)]
                  .filter((mark): mark is { label: string; tone: string } => !!mark)
                  .map((mark) => (
                    <span
                      key={mark.label}
                      className={`rounded-lg border px-2 py-0.5 font-mono text-meta ${mark.tone}`}
                    >
                      {mark.label}
                    </span>
                  ))}
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
              {consequence(entry) ? (
                <p className="mt-0.5 text-meta text-warn">{consequence(entry)}</p>
              ) : (
                <p className="mt-0.5 text-meta text-ink-muted">
                  Counsel review: {entry.counsel_reviewer_name} of{" "}
                  {entry.counsel_reviewer_firm}, confirming{" "}
                  {entry.counsel_claims_confirmed?.length ?? 0} claim
                  {entry.counsel_claims_confirmed?.length === 1 ? "" : "s"}.
                </p>
              )}
            </li>
          ))}
          {visible.length === 0 ? (
            <li className="py-2 text-desc text-ink-secondary">
              No entry matches this filter.
            </li>
          ) : null}
        </ul>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">Approve an entry</h2>
          <p className="mt-0.5 text-desc text-ink-secondary">
            A separate act by somebody who did not write it. Approval is this Office
            saying the entry is the one to use; it is half of what an entry needs before
            anything relies on it.
          </p>
          <div className="mt-3">
            <ApproveEntryForm pending={unapproved} />
          </div>
        </div>

        <div className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">Record a counsel review</h2>
          <p className="mt-0.5 text-desc text-ink-secondary">
            The other half. Counsel has no account here, so this records your statement
            that a named lawyer at a named firm read the entry and confirmed specific
            claims.
          </p>
          <div className="mt-3">
            <CounselReviewForm pending={unreviewed} />
          </div>
        </div>
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
