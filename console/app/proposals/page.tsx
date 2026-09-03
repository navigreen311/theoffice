import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle, Hourglass } from "@/components/icons";
import { AsOf, Ago } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type ApprovalQueue,
  type PendingApproval,
  type Reviewer,
} from "@/lib/api";

import { Approval, DecisionHistory } from "./queue";

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
 * threshold is named on screen and measured against, the compliance flags that apply are
 * shown before the decision, and the consequence of both decisions is stated. There is
 * no bulk approve, and there is no auto-approve on expiry.
 *
 * None of that is enforcement — the API decides, and it computes the review time in the
 * database so a client cannot lie about it. It is the difference between a screen that
 * cooperates with a control and one that quietly erodes it.
 */

function Metric({
  label,
  value,
  note,
  alarming,
}: {
  label: string;
  value: string;
  note?: string;
  alarming?: boolean;
}) {
  return (
    <div className="rounded-xl bg-surface-muted px-4 py-3">
      <div className="text-desc text-ink-secondary">{label}</div>
      <div
        className={`mt-1 text-[24px] font-medium leading-tight ${
          alarming ? "text-bad" : "text-ink"
        }`}
      >
        {value}
      </div>
      {note ? <p className="mt-1 text-meta text-ink-muted">{note}</p> : null}
    </div>
  );
}

/**
 * Reviewer capacity, from the Pack.
 *
 * This is the page where V13 either holds or fails in practice: the rule projects
 * approvals against coverage, and here is where the projection meets the day.
 */
function Capacity({
  reviewers,
  capacity,
  pending,
}: {
  reviewers: Reviewer[];
  capacity: ApprovalQueue["capacity"];
  pending: number;
}) {
  if (reviewers.length === 0) {
    return (
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Reviewer capacity</h2>
        <p className="mt-0.5 text-desc text-ink-secondary">
          No live Pack declares any reviewer. `human_capacity` is where reviewers are
          named, and until a Pack is live there is nobody this system knows to be on
          duty.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-section font-medium text-ink">Reviewer capacity</h2>
        <span className="text-meta text-ink-muted">
          {capacity.remaining_today} approvals left today across {reviewers.length}{" "}
          reviewer{reviewers.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* The V13 question asked against today rather than against the estimate. */}
      {capacity.over_capacity ? (
        <p className="mt-3 flex items-start gap-1.5 rounded-lg border border-bad-line bg-bad-bg px-3 py-2 text-desc text-bad">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
          {pending} pending against {capacity.remaining_today} remaining approvals in
          today&rsquo;s coverage. The overflow will not be reviewed before the window
          closes.
        </p>
      ) : null}

      <ul className="mt-3">
        {reviewers.map((reviewer) => (
          <li
            key={`${reviewer.venture_id}-${reviewer.name}`}
            className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-t border-line py-2"
          >
            <span className="text-rowtitle font-medium text-ink">{reviewer.name}</span>
            <span className="text-meta text-ink-muted">{reviewer.role}</span>
            <span className="text-meta text-ink-muted">
              {reviewer.coverage_hours}h · {reviewer.timezone}
            </span>
            <span className="text-meta text-ink-muted">
              backup {reviewer.backup_human ?? "none named"}
            </span>
            <span className="text-desc text-ink-secondary">
              {reviewer.decisions_today} of {reviewer.max_daily_approvals} today
            </span>
            <span className="ml-auto text-meta text-ink-muted">
              {reviewer.median_seconds_today !== null
                ? `median ${reviewer.median_seconds_today.toFixed(0)}s`
                : "no data"}
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-meta text-ink-muted">
        Coverage and daily limits are declared in each venture&rsquo;s Pack, which is what
        validator rule V13 checks against. A reviewer is matched to their decisions by
        name; where the two do not match this shows no decisions rather than guessing.
      </p>
    </section>
  );
}

export default async function ProposalsPage() {
  let queue: ApprovalQueue;
  try {
    queue = await api.get<ApprovalQueue>("/api/proposals/queue");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { metrics, capacity } = queue;
  const pending: PendingApproval[] = queue.pending;

  return (
    <div className="space-y-6">
      <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Approvals" }]} />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">Approvals</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            An agent that may not act on its own{" "}
            <code className="text-ident text-ink-muted">auto_execute</code> asked to act.
            It has not acted.
          </p>
        </div>
        <span className="text-meta text-ink-muted">
          <AsOf iso={queue.as_of} />
        </span>
      </div>

      {/*
        The clearest statement of the rubber-stamp problem in the console, and it stays
        on screen when the queue is empty — an empty queue is exactly when somebody
        forgets why the threshold exists.
      */}
      <section className="rounded-xl border border-warn-line bg-warn-bg px-5 py-4">
        <p className="max-w-3xl text-desc text-ink-secondary">
          Approvals decided in under 5 seconds raise a governance flag. That threshold
          exists because a trust tier that is really a click-through is worse than no tier
          at all — it looks like oversight. Read the payload.
        </p>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Pending"
          value={String(pending.length)}
          note={
            pending.length
              ? "Oldest first"
              : "Nothing waiting on a human"
          }
        />
        <Metric
          label="Decisions today"
          value={String(metrics.decisions_today)}
          note={
            metrics.approval_rate !== null
              ? `${Math.round(metrics.approval_rate * 100)}% approved`
              : "none yet"
          }
        />
        <Metric
          label="Median decision time"
          value={
            metrics.median_seconds !== null
              ? `${metrics.median_seconds.toFixed(0)}s`
              : "no data"
          }
          note={`Flagged under ${metrics.threshold_seconds}s`}
        />
        <Metric
          label={`Under ${metrics.threshold_seconds}s`}
          value={String(metrics.under_threshold)}
          alarming={metrics.under_threshold > 0}
          note="Approvals, not denials"
        />
      </div>

      {/* Flagged and recorded. Nothing is blocked or undone. */}
      {metrics.under_threshold > 0 ? (
        <section className="rounded-xl border border-warn-line bg-warn-bg px-5 py-4">
          <h2 className="flex items-center gap-1.5 text-section font-medium text-warn">
            <AlertTriangle className="h-4 w-4" />
            {metrics.under_threshold} approval
            {metrics.under_threshold === 1 ? "" : "s"} decided in under{" "}
            {metrics.threshold_seconds} seconds today
          </h2>
          <ul className="mt-2 space-y-0.5">
            {metrics.by_reviewer
              .filter((row) => row.fast_approvals > 0)
              .map((row) => (
                <li key={row.reviewer ?? "unknown"} className="text-desc text-ink-secondary">
                  {row.reviewer ?? "an unnamed reviewer"} — {row.fast_approvals} of{" "}
                  {row.decisions} decisions
                </li>
              ))}
          </ul>
          <p className="mt-2 text-meta text-ink-muted">
            Recorded, not blocked. Each one raised a governance incident when it was
            made.
          </p>
        </section>
      ) : null}

      <Capacity
        reviewers={queue.reviewers}
        capacity={capacity}
        pending={pending.length}
      />

      {pending.length === 0 ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-8 text-center">
          <p className="text-section font-medium text-ink">Nothing to approve</p>
          {/*
            Derived from what is actually true. The old copy named one cause — trust
            tiers set to act on their own — which is real in general and was wrong here: no
            agent held a grant to any Forge at all.
          */}
          <p className="mx-auto mt-2 max-w-2xl text-desc text-ink-secondary">
            {queue.empty_reason}
          </p>
        </section>
      ) : (
        <section>
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-section font-medium text-ink">
              {pending.length} waiting
            </h2>
            <span className="flex items-center gap-1.5 text-meta text-ink-muted">
              <Hourglass className="h-3.5 w-3.5" />
              Oldest first. A proposal nobody decides expires — the task fails, and it is
              never approved.
            </span>
          </div>
          <div className="mt-3 space-y-3">
            {pending.map((item) => (
              <Approval key={item.proposal_id} item={item} />
            ))}
          </div>
        </section>
      )}

      <DecisionHistory history={queue.history} />

      <p className="text-meta text-ink-muted">
        Expiry never approves. There is no bulk approve, no auto-approve on timeout, and
        no trusted-agent bypass — each would convert this page from a control into a
        formality. If the queue is consistently beyond capacity, the fix is V13&rsquo;s:
        raise a trust-tier ceiling, add reviewer coverage, or cut scope.
      </p>
    </div>
  );
}
