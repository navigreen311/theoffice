"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { AlertTriangle } from "@/components/icons";
import { Ago, useNow } from "@/components/local-time";
import type { DecidedApproval, PendingApproval } from "@/lib/api";
import { RUBBER_STAMP_SECONDS } from "@/lib/severity";

import { decideAction, type DecisionState } from "./actions";

/**
 * A pending approval.
 *
 * There is deliberately no select-all. Bulk approval is the rubber-stamp mechanism this
 * page's own copy warns about, industrialised: one click authorising fifty payloads
 * nobody read, each one audited and counted. If volume makes it feel necessary, the fix
 * is V13's — raise a trust-tier ceiling, add reviewer coverage, or cut scope.
 *
 * Denying in bulk would be acceptable, because denying is the safe direction. It is not
 * built here because nothing in this system has ever produced a queue to clear; the
 * asymmetry is recorded so that whoever adds it knows which half is safe.
 */

/**
 * What the agent is asking to do, in a sentence.
 *
 * Generated from the module and the payload rather than restating the module name: "the
 * agent wants to run place_call" tells a reviewer what they already read in the header.
 * What they need is the effect.
 */
function intent(item: PendingApproval): string {
  const payload = item.payload ?? {};
  const target =
    (payload.to as string) ??
    (payload.recipient as string) ??
    (payload.address as string) ??
    (payload.query as string) ??
    null;

  const mutating = item.is_mutating
    ? "This changes something outside The Office."
    : "This reads; it changes nothing outside The Office.";

  return (
    `${item.agent_name ?? "An agent"} wants to run ` +
    `${item.module_name ?? item.module_id} on ${item.forge_id}` +
    (target ? `, targeting ${target}` : "") +
    `, for ${item.venture_id}. ${mutating}`
  );
}

/** What each decision causes. Reviewers approve differently when it is stated. */
function consequences(item: PendingApproval): { approve: string; deny: string } {
  const flags = item.compliance_flags_implied ?? [];
  const recording = flags.some((flag) => flag.includes("recording"));
  const outward = item.is_mutating;

  return {
    approve: outward
      ? `Approving places a real ${item.module_id.replace(/_/g, " ")}` +
        (recording ? " and starts a recording" : "") +
        ". It happens once, immediately."
      : "Approving lets the agent read. Nothing outside The Office changes.",
    deny:
      "Denying stops this task; the agent does not retry without a new proposal.",
  };
}

function Field({ name, value }: { name: string; value: unknown }) {
  const [expanded, setExpanded] = useState(false);
  const text =
    typeof value === "string" ? value : JSON.stringify(value, null, 2) ?? "null";
  const long = text.length > 160;
  const shown = long && !expanded ? `${text.slice(0, 160)}…` : text;

  return (
    <div className="grid grid-cols-[minmax(6rem,max-content)_1fr] gap-x-3">
      <dt className="text-ink-muted">{name}</dt>
      <dd className="whitespace-pre-wrap break-words text-ink">
        {shown}
        {long ? (
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="ml-2 font-sans text-ink-muted underline underline-offset-2 hover:text-ink"
          >
            {expanded ? "less" : "more"}
          </button>
        ) : null}
      </dd>
    </div>
  );
}

function Deny({ proposalId }: { proposalId: string }) {
  const [open, setOpen] = useState(false);
  const [state, action] = useFormState<DecisionState | null, FormData>(
    decideAction,
    null,
  );
  const { pending } = useFormStatus();

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
      >
        Deny…
      </button>
    );
  }

  return (
    <form action={action} className="w-full max-w-md space-y-2">
      <input type="hidden" name="proposal_id" value={proposalId} />
      <input type="hidden" name="approve" value="false" />
      <label className="block text-meta text-ink-secondary">
        Why
        <input
          name="reason"
          required
          placeholder="Recorded against your name, with how long you took."
          className="mt-1 w-full rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg border border-bad-line px-3 py-1.5 text-desc font-medium text-bad transition hover:bg-bad-bg disabled:opacity-50"
        >
          {pending ? "Denying…" : "Deny"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-meta text-ink-muted underline underline-offset-2"
        >
          Cancel
        </button>
      </div>
      {state?.error ? <p className="text-meta text-bad">{state.error}</p> : null}
    </form>
  );
}

function ApproveButton({ proposalId }: { proposalId: string }) {
  const [state, action] = useFormState<DecisionState | null, FormData>(
    decideAction,
    null,
  );
  const { pending } = useFormStatus();
  const [seconds, setSeconds] = useState(0);

  // A visible timer, not a disabled button. Blocking the control for five seconds
  // trains people to wait five seconds; showing the number they are about to be
  // measured against gives them a reason to read. The API measures it either way, from
  // `created_at` in the database, so this cannot be gamed by the client.
  useEffect(() => {
    const timer = setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const tooFast = seconds < RUBBER_STAMP_SECONDS;

  return (
    <form action={action} className="flex flex-wrap items-center gap-3">
      <input type="hidden" name="proposal_id" value={proposalId} />
      <input type="hidden" name="approve" value="true" />
      <button
        type="submit"
        disabled={pending}
        className="rounded-lg bg-surface-inverse px-3 py-1.5 text-desc font-medium text-ink-inverse transition hover:opacity-90 disabled:opacity-50"
      >
        {pending ? "Approving…" : "Approve"}
      </button>
      <span className={`text-meta ${tooFast ? "text-warn" : "text-ink-muted"}`}>
        {tooFast
          ? `${seconds}s on screen — approving now flags as a rubber stamp`
          : `${seconds}s on screen`}
      </span>
      {state?.error ? <p className="text-meta text-bad">{state.error}</p> : null}
      {state?.ok ? <p className="text-meta text-ok">{state.ok}</p> : null}
    </form>
  );
}

export function Approval({ item }: { item: PendingApproval }) {
  // How close this is to expiring depends on the clock, which the server and the
  // browser do not share. `useNow` is the one place in the console that reads it, and
  // returns null until after mount, so the first paint matches the server exactly.
  const now = useNow();
  const window = Date.parse(item.expires_at) - Date.parse(item.created_at);
  const urgent =
    now !== null && Date.parse(item.expires_at) - now < 0.25 * window;

  const effects = consequences(item);
  const flags = item.compliance_flags_implied ?? [];
  const fields = Object.entries(item.payload ?? {});

  return (
    <article className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[15px] font-medium text-ink">
          {item.agent_name ?? "Unnamed agent"}
        </span>
        <span
          className={`rounded-lg border px-2 py-0.5 text-meta ${
            urgent
              ? "border-bad-line bg-bad-bg text-bad"
              : "border-warn-line bg-warn-bg text-warn"
          }`}
        >
          waiting <Ago iso={item.created_at} />
        </span>

        {/* Individual pills, never a comma-joined string: a reviewer scans for the one
            that matters, and a joined string hides it in the middle. */}
        {flags.map((flag) => (
          <span
            key={flag}
            className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 font-mono text-meta text-warn"
          >
            {flag}
          </span>
        ))}

        <span className="ml-auto text-meta text-ink-muted">
          expires <Ago iso={item.expires_at} />
        </span>
      </div>

      <p className="mt-1 text-meta text-ink-muted">
        {item.venture_id} ·{" "}
        <span className="font-mono">
          {item.forge_id}/{item.module_id}
        </span>{" "}
        · tier <span className="font-mono">{item.trust_tier}</span>
      </p>

      <p className="mt-2 text-desc text-ink">{intent(item)}</p>

      <div className="mt-3">
        <p className="text-meta text-ink-muted">
          Payload · <span className="font-mono">{item.payload_hash.slice(0, 12)}…</span>
        </p>
        <dl className="mt-1 rounded-lg bg-surface-muted p-3 font-mono text-[11px] leading-[1.7]">
          {fields.length ? (
            fields.map(([name, value]) => (
              <Field key={name} name={name} value={value} />
            ))
          ) : (
            <span className="text-ink-muted">The payload is empty.</span>
          )}
        </dl>
      </div>

      <div className="mt-3 rounded-lg border border-warn-line bg-warn-bg px-3 py-2">
        <p className="text-desc text-ink-secondary">{effects.approve}</p>
        <p className="mt-1 text-desc text-ink-secondary">{effects.deny}</p>
      </div>

      <div className="mt-3 flex flex-wrap items-start gap-3">
        <ApproveButton proposalId={item.proposal_id} />
        <Deny proposalId={item.proposal_id} />
        <Link
          href={`/agents/${encodeURIComponent(item.office_agent_id)}`}
          className="self-center text-desc text-ink underline underline-offset-2"
        >
          Open agent
        </Link>
      </div>
    </article>
  );
}

/**
 * What was decided, by whom, and how long they took.
 *
 * The payload lives on the proposal row, which is never rewritten, so this is the
 * document as it stood when the decision was made — which is what "show me who approved
 * this and what they saw" asks for.
 */
export function DecisionHistory({ history }: { history: DecidedApproval[] }) {
  const [reviewer, setReviewer] = useState("");
  const [decision, setDecision] = useState("");
  const [fastOnly, setFastOnly] = useState(false);
  const [shown, setShown] = useState<string | null>(null);

  const reviewers = [...new Set(history.map((row) => row.reviewer).filter(Boolean))];

  const visible = history.filter((row) => {
    if (reviewer && row.reviewer !== reviewer) return false;
    if (decision && row.status !== decision) return false;
    if (fastOnly && !(Number(row.review_seconds) < 5 && row.status === "approved")) {
      return false;
    }
    return true;
  });

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-section font-medium text-ink">Decision history</h2>
        <span className="text-meta text-ink-muted">
          {visible.length} of {history.length}
        </span>
      </div>

      {history.length === 0 ? (
        <p className="mt-2 text-desc text-ink-secondary">
          No proposal has ever been decided. Nothing has been approved, denied or
          expired.
        </p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-meta text-ink-muted">
              Reviewer
              <select
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
              >
                <option value="">Anyone</option>
                {reviewers.map((name) => (
                  <option key={name} value={name ?? ""}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-meta text-ink-muted">
              Decision
              <select
                value={decision}
                onChange={(event) => setDecision(event.target.value)}
                className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
              >
                <option value="">Any</option>
                <option value="approved">Approved</option>
                <option value="rejected">Denied</option>
                <option value="expired">Expired</option>
                <option value="executed">Executed</option>
              </select>
            </label>
            <label className="flex items-center gap-1.5 pb-1.5 text-meta text-ink-muted">
              <input
                type="checkbox"
                checked={fastOnly}
                onChange={(event) => setFastOnly(event.target.checked)}
              />
              Flagged fast only
            </label>
          </div>

          <ul className="mt-3">
            {visible.map((row) => {
              const seconds = Number(row.review_seconds);
              const fast = row.status === "approved" && seconds < 5;
              return (
                <li key={row.proposal_id} className="border-t border-line py-2">
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-desc text-ink">
                      {row.agent_name ?? "Unnamed agent"}
                    </span>
                    <span className="font-mono text-meta text-ink-muted">
                      {row.forge_id}/{row.module_id}
                    </span>
                    <span className="text-meta text-ink-muted">{row.venture_id}</span>
                    <span
                      className={`rounded-lg border px-2 py-0.5 text-meta ${
                        row.status === "approved"
                          ? "border-ok-line bg-ok-bg text-ok"
                          : row.status === "expired"
                            ? "border-warn-line bg-warn-bg text-warn"
                            : "border-line bg-surface-muted text-ink-secondary"
                      }`}
                    >
                      {row.status === "rejected" ? "denied" : row.status}
                    </span>
                    {row.reviewer ? (
                      <span className="text-meta text-ink-muted">by {row.reviewer}</span>
                    ) : (
                      <span className="text-meta text-ink-muted">
                        no reviewer — expired
                      </span>
                    )}
                    {row.review_seconds !== null ? (
                      <span
                        className={`text-meta ${fast ? "text-warn" : "text-ink-muted"}`}
                      >
                        {fast ? (
                          <AlertTriangle className="mr-1 inline h-3 w-3" />
                        ) : null}
                        {seconds.toFixed(0)}s to decide
                      </span>
                    ) : null}
                    <span className="ml-auto text-meta text-ink-muted">
                      {row.decided_at ? <Ago iso={row.decided_at} /> : null}
                    </span>
                  </div>
                  {row.decision_reason ? (
                    <p className="mt-0.5 text-meta text-ink-secondary">
                      {row.decision_reason}
                    </p>
                  ) : null}
                  <button
                    type="button"
                    onClick={() =>
                      setShown(shown === row.proposal_id ? null : row.proposal_id)
                    }
                    className="mt-0.5 text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
                  >
                    {shown === row.proposal_id
                      ? "Hide the payload"
                      : "The payload as it stood"}
                  </button>
                  {shown === row.proposal_id ? (
                    <pre className="mt-1 overflow-x-auto rounded-lg bg-surface-muted p-3 font-mono text-[11px] leading-[1.7] text-ink-secondary">
                      {JSON.stringify(row.payload, null, 2)}
                    </pre>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
