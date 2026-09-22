import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { Hourglass } from "@/components/icons";
import { AsOf } from "@/components/local-time";
import { api, NotAuthenticated, type EscalationInbox } from "@/lib/api";

import { Answered, Received, Waiting } from "./inbox";

export const dynamic = "force-dynamic";

/**
 * Escalations routed to you.
 *
 * **RULED 21 SEPTEMBER 2026 (decisions entry 150).** *"The routed human can reach it: a
 * console page on the /proposals pattern, showing the item, who raised it, what it asks,
 * and the two acts."*
 *
 * There was no page and no route. `record_receipt` and `record_answer` existed and had
 * no caller outside the tests, so the only party able to record a delivery was the
 * process that raised it — which is the one party a delivery cannot be to. An
 * escalation path that nobody can be shown to have travelled cannot be attested
 * verified, and that is what this page unblocks.
 *
 * **Scoped to you, by the API and not by a filter here.** `/api/escalations` reads
 * `routed_to_human = me.human_id`; an escalation addressed to somebody else is not
 * yours to see, to receive or to answer. A page that listed everybody's would invite
 * exactly the close-somebody-else's-item the rule refuses.
 *
 * Two acts and not one, for the reason the two timestamps are separate: the gap between
 * raised and received is what a drill measures, and a single button would erase it.
 */
export default async function EscalationsPage() {
  let inbox: EscalationInbox;
  try {
    inbox = await api.get<EscalationInbox>("/api/escalations");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const nothing =
    inbox.waiting.length === 0 &&
    inbox.received.length === 0 &&
    inbox.answered.length === 0;

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[{ label: "Dashboard", href: "/" }, { label: "Escalations" }]}
      />
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-page font-medium text-ink">Routed to you</h1>
        <AsOf iso={inbox.as_of} />
      </div>

      {nothing ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-8 text-center">
          <p className="text-section font-medium text-ink">Nothing routed to you</p>
          {/*
            Derived, like the approvals queue's empty state: a reader of an empty page
            should be told which empty it is. "No escalations" and "no escalation has
            ever been raised on this platform" are different facts.
          */}
          <p className="mx-auto mt-2 max-w-2xl text-desc text-ink-secondary">
            {inbox.empty_reason}
          </p>
        </section>
      ) : null}

      {inbox.waiting.length > 0 ? (
        <section>
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-section font-medium text-ink">
              {inbox.waiting.length} waiting for you
            </h2>
            <span className="flex items-center gap-1.5 text-meta text-ink-muted">
              <Hourglass className="h-3.5 w-3.5" />
              Oldest first. Nothing expires — an escalation nobody picks up stays here
              and stays a finding.
            </span>
          </div>
          <div className="mt-3 space-y-3">
            {inbox.waiting.map((item) => (
              <Waiting key={item.escalation_id} item={item} />
            ))}
          </div>
        </section>
      ) : null}

      {inbox.received.length > 0 ? (
        <section>
          <h2 className="text-section font-medium text-ink">
            {inbox.received.length} you have, unanswered
          </h2>
          <div className="mt-3 space-y-3">
            {inbox.received.map((item) => (
              <Received key={item.escalation_id} item={item} />
            ))}
          </div>
        </section>
      ) : null}

      <Answered items={inbox.answered} />

      <p className="text-meta text-ink-muted">
        You are the human this venture and department names. Account age decides
        nothing, and nobody else can record receipt or an answer on your behalf — not
        the agent that raised it, and not a process acting as you.
      </p>
    </div>
  );
}
