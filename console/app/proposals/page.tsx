import { redirect } from "next/navigation";

import { Badge, Card } from "@/components/ui";
import { api, NotAuthenticated, type Proposal } from "@/lib/api";
import { RUBBER_STAMP_SECONDS, relativeAge } from "@/lib/severity";

import { DecideForm } from "./form";

export const dynamic = "force-dynamic";

/**
 * The approval queue.
 *
 * **This is the screen where a UI can defeat a control without bypassing it.**
 *
 * Part 14 requires rubber-stamp detection because approving is the easy path. A queue
 * with a one-click Approve next to a collapsed payload is a rubber-stamp machine: every
 * approval is authorised, audited and counted, and the outcome is exactly what the
 * control exists to prevent.
 *
 * So the payload is expanded by default rather than behind a disclosure, the five-second
 * threshold is named on screen next to the button, and the compliance flags that apply
 * are shown before the decision rather than after it.
 *
 * None of that is enforcement - the API decides, and it computes the review time in the
 * database so a client cannot lie about it. It is the difference between a screen that
 * cooperates with a control and one that quietly erodes it.
 */
export default async function ProposalsPage({
  searchParams,
}: {
  searchParams: { venture?: string };
}) {
  const query = new URLSearchParams({ status: "pending" });
  if (searchParams.venture) query.set("venture_id", searchParams.venture);

  let proposals: Proposal[];
  try {
    proposals = await api.get<Proposal[]>(`/api/proposals?${query}`);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <div className="space-y-4">
      <Card
        title={`Approval queue — ${proposals.length} pending`}
        subtitle="An agent below auto_execute asked to act. It has not acted."
      >
        <p className="text-xs text-ink-secondary">
          Approvals decided in under {RUBBER_STAMP_SECONDS} seconds raise a governance
          flag. That threshold exists because a trust tier that is really a click-through
          is worse than no tier at all — it looks like oversight. Read the payload.
        </p>
      </Card>

      {proposals.length === 0 ? (
        <Card title="Nothing pending">
          <p className="text-sm text-ink-secondary">
            No proposals awaiting a decision. If you expected some, check that the
            agents&apos; grants are below <code>auto_execute</code> — an agent at
            auto_execute acts without asking.
          </p>
        </Card>
      ) : null}

      {proposals.map((p) => (
        <Card
          key={p.proposal_id}
          title={`${p.forge_id} / ${p.module_id}`}
          subtitle={`${p.venture_id} · task ${p.task_id} · raised ${relativeAge(p.created_at)}`}
        >
          <div className="mb-3 flex flex-wrap gap-2">
            <Badge severity="warn">{p.trust_tier}</Badge>
            <Badge severity="neutral">agent {p.office_agent_id.slice(0, 8)}…</Badge>
          </div>

          {/* Expanded, not behind a disclosure. A payload nobody opened is a payload
              nobody read, and the whole decision rests on it. */}
          <div className="mb-3">
            <div className="mb-1 text-xs font-medium text-ink-secondary">
              Payload — this is what the agent will send if you approve
            </div>
            <pre className="max-h-72 overflow-auto rounded border border-line bg-surface-page p-3 text-xs">
              {JSON.stringify(p.payload, null, 2)}
            </pre>
          </div>

          <DecideForm proposalId={p.proposal_id} />
        </Card>
      ))}
    </div>
  );
}
