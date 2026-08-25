"use client";

import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle, CircleCheck } from "@/components/icons";
import { LocalTime } from "@/components/local-time";
import { Badge, Button } from "@/components/ui";

import { verifyChainAction } from "./actions";

/**
 * Chain integrity, above the log, with what was verified said out loud.
 *
 * The ordering is deliberate and unchanged: entries below are meaningless if this is
 * broken, so this is read first.
 *
 * What changed is the claim. The page reported "chain integrity verified over 1,157
 * entries" from a check it ran on page load and recorded nowhere, while the Compliance
 * page read the last *recorded* control result — which covered 73 entries from the
 * previous day. Both screens were describing the same property, both were telling the
 * truth, and they disagreed. A reader had no way to tell which one was evidence.
 *
 * This reports the recorded verification, which is the row Compliance reads, so the two
 * agree by construction. It states the fraction, the timestamp, the method and the head
 * hash, because a verification without those is not evidence of anything — and this
 * page's own first sentence makes it the most important claim on the screen.
 */

export type ChainState = {
  entries: number;
  verified_entries: number;
  unverified_entries: number;
  covers_whole_log: boolean;
  recorded: boolean;
  ok: boolean;
  stale: boolean;
  trustworthy: boolean;
  age_hours: number | null;
  max_age_days: number | null;
  status: string | null;
  verified_at: string | null;
  method: string | null;
  reason: string | null;
  tail_gap: number | null;
  head_hash: string | null;
  head_audit_id: number | null;
  control: string;
};

function VerifyButton() {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending}>
      {pending ? "Verifying…" : "Verify now"}
    </Button>
  );
}

export function ChainIntegrity({ chain }: { chain: ChainState }) {
  const [state, action] = useFormState(verifyChainAction, null);
  const [showHash, setShowHash] = useState(false);

  const good = chain.trustworthy;

  return (
    <section
      className={`rounded-xl border px-5 py-4 ${
        good ? "border-ok-line bg-ok-bg" : "border-bad-line bg-bad-bg"
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2
          className={`flex items-center gap-1.5 text-section font-medium ${
            good ? "text-ok" : "text-bad"
          }`}
        >
          {good ? (
            <CircleCheck className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
          {!chain.recorded
            ? "No verification has ever been recorded"
            : !chain.ok
              ? "The last recorded verification did not pass"
              : chain.stale
                ? `Last verified ${Math.round((chain.age_hours ?? 0) / 24)} days ago — past the ${chain.max_age_days}-day maximum`
                : "Chain integrity verified"}
        </h2>
        <span className="text-meta text-ink-muted">
          Entries below are meaningless if this is broken — read it first.
        </span>
      </div>

      {/* What was verified, when, and how. The three things the old badge omitted. */}
      <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-meta text-ink-muted">Entries verified</dt>
          <dd className="text-desc text-ink">
            {chain.verified_entries} of {chain.entries}
            {chain.unverified_entries > 0 ? (
              <span className="text-ink-muted">
                {" "}
                · {chain.unverified_entries} appended since
              </span>
            ) : null}
          </dd>
        </div>
        <div>
          <dt className="text-meta text-ink-muted">Verified at</dt>
          <dd className="text-desc text-ink">
            {chain.verified_at ? <LocalTime iso={chain.verified_at} /> : "never"}
          </dd>
        </div>
        <div>
          <dt className="text-meta text-ink-muted">Method</dt>
          <dd className="text-desc text-ink">{chain.method ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-meta text-ink-muted">Head hash</dt>
          <dd className="font-mono text-ident text-ink">
            <button
              type="button"
              onClick={() => setShowHash(!showHash)}
              className="underline underline-offset-2"
            >
              {showHash
                ? chain.head_hash
                : `${(chain.head_hash ?? "").slice(0, 16)}…`}
            </button>
          </dd>
        </div>
      </dl>

      {chain.unverified_entries > 0 ? (
        <p className="mt-3 max-w-3xl text-desc text-ink-secondary">
          {chain.unverified_entries === 1
            ? "One entry has been appended since — running a verification writes an audit entry of its own, so a live log is always at least one ahead."
            : `${chain.unverified_entries} entries have been appended since that verification and are not covered by it.`}{" "}
          The recorded result is what the Compliance page reads, so this screen and that
          one describe the same thing.
        </p>
      ) : null}

      {chain.tail_gap ? (
        <p className="mt-2 text-meta text-warn">
          Tail gap of {chain.tail_gap}. Advisory: a rolled-back insert produces one
          innocently, and a check that failed on every rollback is one people learn to
          ignore.
        </p>
      ) : null}

      <form action={action} className="mt-3 flex flex-wrap items-center gap-3">
        <VerifyButton />
        <span className="text-meta text-ink-muted">
          Re-hashes every entry and records the result as an{" "}
          <code className="text-ident">{chain.control}</code> control run, so this page
          and Compliance cannot drift apart.
        </span>
        {state?.error ? <Badge severity="bad">{state.error}</Badge> : null}
        {state?.ok ? <Badge severity="ok">{state.ok}</Badge> : null}
      </form>
    </section>
  );
}
