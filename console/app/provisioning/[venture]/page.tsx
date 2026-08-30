import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import {
  AlertTriangle,
  Check,
  Hourglass,
  Loader,
  Lock,
  Minus,
  X,
} from "@/components/icons";
import { Ago, AsOf, LocalTime } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type Advisory,
  type LadderRow,
  type Me,
  type PackDetail,
  type RunDetail,
  type RunSummary,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import { Hash } from "../../packs/forms";
import {
  AbortForm,
  AdvanceForm,
  ReviewForm,
  SignOffForm,
  StartRunForm,
} from "../forms";
import { RawEvidence, RunHistoryTable } from "./panels";

export const dynamic = "force-dynamic";

/**
 * The gate ladder — Part 17 screen 13, detail.
 *
 * The structure here was already right: sixteen rows including the gates still ahead, a
 * review form beside the numbers it is about, advance and abandon as separate acts. What
 * was wrong was what the page knew and did not say.
 *
 * It knew, at gate 4, that V13 already fails at gate 4.5 — and filed that under
 * "Generator warnings (2)" beside a genuine advisory, then asked a human to write a
 * review and advance into a halt one gate later. A page that holds the reason the next
 * gate will stop the run and asks for the current gate's approval anyway is spending
 * somebody's attention to manufacture another abandoned run.
 *
 * It also printed raw JSON at the reviewer: three capacity numbers as an object literal,
 * a warnings array with escaped quotes. That is a debug view, and this is the screen
 * where a named human takes responsibility for what they read.
 */

function GateIcon({ row }: { row: LadderRow }) {
  const className = "h-3.5 w-3.5 shrink-0";
  if (row.is_ceiling && row.state !== "passed") {
    return <Lock className={`${className} text-warn`} />;
  }
  switch (row.state) {
    case "passed":
      return <Check className={`${className} text-ok`} />;
    case "blocked":
      return <X className={`${className} text-bad`} />;
    case "awaiting":
      return <Hourglass className={`${className} text-warn`} />;
    case "running":
      return <Loader className={`${className} text-ink`} />;
    default:
      return <Minus className={`${className} text-ink-muted`} />;
  }
}

function elapsed(seconds: number | null): string | null {
  if (seconds === null) return null;
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 90) return `${seconds.toFixed(1)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

/**
 * The failure the next gate will produce, said before the human is asked to act.
 *
 * Deliberately does not disable Advance. An operator may legitimately want to confirm
 * the halt, and a page that decides for them has stopped informing and started
 * enforcing — which is the gates' job, not the page's.
 */
function DownstreamBanner({
  advisories,
  venture,
}: {
  advisories: Advisory[];
  venture: string;
}) {
  const blocking = advisories.filter((a) => a.severity === "fail");
  if (blocking.length === 0) return null;

  // Deep-link to the block the failure lives in, so "fix the Pack" lands on the fields
  // to change rather than at the top of a 342-line document.
  const target = blocking.flatMap((advisory) => advisory.blocks ?? [])[0] ?? null;

  const gates = [...new Set(blocking.map((a) => a.blocks_at).filter(Boolean))];
  const where = gates.length === 1 ? `gate ${gates[0]}` : `gates ${gates.join(", ")}`;
  const rules = blocking.map((a) => a.rule_id).filter(Boolean);

  return (
    <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-bad" />
        <div className="min-w-0">
          <h2 className="text-section font-medium text-bad">
            Advancing will stop at {where}
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            {rules.length === 1 ? "Rule " : "Rules "}
            <span className="font-mono">{rules.join(", ")}</span>{" "}
            {rules.length === 1 ? "already fails" : "already fail"} against this Pack.
            Recording a review and advancing will clear this gate and immediately halt
            one gate later. Fix the Pack first, or advance knowing it stops.
          </p>
          <Link
            href={`/packs/${encodeURIComponent(venture)}${target ? `#${target}` : ""}`}
            className="mt-2 inline-block text-desc text-ink underline underline-offset-2"
          >
            Fix in Pack editor
            {target ? (
              <span className="text-ink-muted"> — {target}</span>
            ) : null}
          </Link>
        </div>
      </div>
    </section>
  );
}

/** A blocking advisory, rendered as the paragraphs it is written as. */
function AdvisoryBlock({
  advisory,
  tone,
}: {
  advisory: Advisory;
  tone: "fail" | "warn";
}) {
  const border = tone === "fail" ? "border-bad-line bg-bad-bg" : "border-warn-line bg-warn-bg";
  const label = tone === "fail" ? "text-bad" : "text-warn";
  return (
    <div className={`rounded-xl border px-3 py-2.5 ${border}`}>
      <p className={`text-meta font-medium ${label}`}>
        {advisory.rule_id ? <span className="font-mono">{advisory.rule_id}</span> : null}
        {advisory.rule_id ? " · " : ""}
        {tone === "fail"
          ? `fails at gate ${advisory.blocks_at ?? "a later gate"}`
          : "advisory"}
      </p>
      {/* Written as paragraphs by the validator. Rendering it as one run-on line puts
          the arithmetic and the conclusion in the same breath. */}
      {advisory.message.split("\n\n").map((paragraph) => (
        <p key={paragraph.slice(0, 40)} className="mt-1.5 text-desc text-ink-secondary">
          {paragraph}
        </p>
      ))}
    </div>
  );
}

/**
 * What Gate 4 asks a human to look at, expanded.
 *
 * The approval queue taught this: a one-click decision beside a collapsed payload is a
 * rubber-stamp machine — every action authorised, audited, and producing exactly the
 * outcome the control exists to prevent. Gate 4 is the same shape, so the numbers the
 * reviewer is accountable for are on screen before the form, not behind a disclosure —
 * and rendered, not printed as JSON.
 */
function ReviewBrief({
  evidence,
  advisories,
}: {
  evidence: Record<string, unknown>;
  advisories: Advisory[];
}) {
  const capacity = evidence.capacity as Record<string, number> | undefined;
  const unfilled = (evidence.unfilled_positions ?? []) as {
    position: string;
    unfilled: number;
  }[];
  const artifactsHash = evidence.artifacts_hash as string | undefined;

  const failures = advisories.filter((a) => a.severity === "fail");
  const warnings = advisories.filter((a) => a.severity === "warn");

  return (
    <div className="space-y-4">
      {capacity ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {[
            ["certified_and_free", "Certified and free"],
            ["certified_but_allocated", "Certified, allocated elsewhere"],
            ["produced_not_yet_certified", "Produced, not yet certified"],
          ].map(([key, label]) => (
            <div key={key} className="rounded-xl bg-surface-muted px-4 py-3">
              <div className="text-[24px] font-medium leading-tight text-ink">
                {capacity[key] ?? "—"}
              </div>
              <div className="mt-1 text-desc text-ink-secondary">{label}</div>
            </div>
          ))}
        </div>
      ) : null}

      <div>
        <h4 className="text-meta text-ink-muted">
          Unfilled positions ({unfilled.length})
        </h4>
        {unfilled.length === 0 ? (
          <p className="mt-1 text-desc text-ink-secondary">
            Every position is filled by a certified agent.
          </p>
        ) : (
          <ul className="mt-1 space-y-1">
            {unfilled.map((position) => (
              <li key={position.position} className="text-desc text-warn">
                {position.position} — {position.unfilled} unfilled
              </li>
            ))}
          </ul>
        )}
      </div>

      {/*
        Two containers, two counts. A rule that FAILs one gate later is not a warning,
        and a single list labelled "Generator warnings (2)" over one failure and one
        advisory understates the first and inflates the second.
      */}
      {failures.length ? (
        <div>
          <h4 className="text-meta text-bad">
            Blocking failures ({failures.length})
          </h4>
          <div className="mt-1.5 space-y-2">
            {failures.map((advisory) => (
              <AdvisoryBlock key={advisory.message} advisory={advisory} tone="fail" />
            ))}
          </div>
        </div>
      ) : null}

      <div>
        <h4 className="text-meta text-ink-muted">Warnings ({warnings.length})</h4>
        {warnings.length === 0 ? (
          <p className="mt-1 text-desc text-ink-secondary">None.</p>
        ) : (
          <div className="mt-1.5 space-y-2">
            {warnings.map((advisory) => (
              <AdvisoryBlock key={advisory.message} advisory={advisory} tone="warn" />
            ))}
          </div>
        )}
      </div>

      {artifactsHash ? (
        <div>
          <Hash value={artifactsHash} label="artifacts" />
          <p className="mt-0.5 text-meta text-ink-muted">
            Sign-off at gate 10 binds to this hash. If artifacts change, signatures void.
          </p>
        </div>
      ) : null}

      <RawEvidence evidence={evidence} />
    </div>
  );
}

function GateLadder({ ladder }: { ladder: LadderRow[] }) {
  return (
    <ol className="space-y-2">
      {ladder.map((row) => {
        const ceiling = row.is_ceiling && row.state !== "passed";
        const fill =
          row.state === "blocked"
            ? "border-bad-line bg-bad-bg"
            : ceiling || row.state === "awaiting"
              ? "border-warn-line bg-warn-bg"
              : row.is_current
                ? "border-border-strong"
                : "border-line";
        return (
          <li key={row.gate} className={`rounded-xl border px-4 py-3 ${fill}`}>
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="self-center">
                <GateIcon row={row} />
              </span>
              <span className="w-7 text-right font-mono text-meta text-ink-muted">
                {row.gate}
              </span>
              <span className="text-rowtitle font-medium text-ink">{row.name}</span>
              {ceiling ? (
                <span className="text-meta text-warn">blocked — ceiling</span>
              ) : null}
              <span className="ml-auto flex items-center gap-3 text-meta text-ink-muted">
                {elapsed(row.seconds) ? <span>{elapsed(row.seconds)}</span> : null}
                {/*
                  An absolute time, because five gates that all completed inside a second
                  rendered as five rows of "0s ago", which reads as a broken clock.
                */}
                {row.recorded_at ? (
                  <LocalTime iso={row.recorded_at} mode="time" />
                ) : null}
              </span>
            </div>
            <p className="mt-1 pl-[3.1rem] text-desc text-ink-secondary">
              {/* A pending gate showing only a name says nothing about what is ahead. */}
              {row.reason ?? row.description}
            </p>
            {ceiling ? (
              <p className="mt-1 pl-[3.1rem] text-meta text-warn">
                SimForge&rsquo;s held-out adversarial partition does not exist yet, so no
                run started from this console can pass gate 9.5. Blocked, not skipped.
              </p>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

export default async function ProvisioningVenturePage({
  params,
}: {
  params: { venture: string };
}) {
  const venture = decodeURIComponent(params.venture);

  let runList: { runs: RunSummary[]; excluded_fixtures: number };
  let pack: PackDetail;
  let me: Me;
  try {
    [runList, pack, me] = await Promise.all([
      api.get<{ runs: RunSummary[]; excluded_fixtures: number }>(
        `/api/provisioning/runs?venture_id=${encodeURIComponent(venture)}`,
      ),
      api.get<PackDetail>(`/api/packs/${encodeURIComponent(venture)}`),
      api.get<Me>("/api/me"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // The listing filters smoke-test runs out by default and says how many.
  const runs = runList.runs;

  // No Pack and no run is not a venture this screen can act on. Rendering an empty
  // ladder for a mistyped slug would offer a "Start a run" button for a venture that
  // does not exist, and Gate 1 would refuse it with a message about a missing Pack.
  if (!pack.live && pack.versions.length === 0 && runs.length === 0) notFound();

  const current = runs.find((run) =>
    ["running", "blocked", "awaiting_human"].includes(run.status),
  );
  const latest = current ?? runs[0];

  let detail: RunDetail | null = null;
  if (latest) {
    detail = await api.get<RunDetail>(`/api/provisioning/runs/${latest.run_id}`);
  }

  const currentGate = detail?.ladder.find((row) => row.is_current);
  const isOpen =
    detail !== null && ["running", "blocked", "awaiting_human"].includes(detail.status);
  const atGate4 = isOpen && detail?.current_gate === "4";
  const atGate10 = isOpen && detail?.current_gate === "10";

  const advisories = (currentGate?.evidence.advisories ?? []) as Advisory[];
  // From the server, never the render clock. `new Date()` evaluated during SSR and
  // again during hydration produces two different values by construction, and the two
  // renders then disagree about what time it is.
  const asOf = detail?.as_of ?? null;
  const displayName =
    pack.live?.yaml_source?.match(/venture_name:\s*(.+)/)?.[1]?.trim() ?? venture;

  // "awaiting you" only when this reader can actually act. Everyone with the role can
  // review — the gate names no individual — so the honest alternative is that it is
  // waiting on somebody with the role, not on a named person the page cannot identify.
  const canReview =
    me.roles.includes("venture_operator") || me.roles.includes("ivan");
  const waitingLine =
    detail?.status === "awaiting_human"
      ? canReview
        ? "awaiting you"
        : "awaiting a venture operator"
      : detail?.display_status;

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Provisioning", href: "/provisioning" },
          { label: displayName },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">
            {displayName} — provisioning
          </h1>
          <p className="mt-1 text-desc text-ink-secondary">
            {pack.live
              ? `Live Pack ${pack.live.pack_version} · ${pack.live.content_hash.slice(0, 16)}…`
              : "No live Pack — Gate 1 refuses a run without one."}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-meta text-ink-muted">
            {asOf ? <AsOf iso={asOf} /> : null}
          </span>
          <Link
            href={`/packs/${encodeURIComponent(venture)}`}
            className="text-desc text-ink underline underline-offset-2"
          >
            Pack editor
          </Link>
        </div>
      </div>

      {/* Before the form that asks for a decision, not after it. */}
      {atGate4 ? (
        <DownstreamBanner advisories={advisories} venture={venture} />
      ) : null}

      {detail === null ? (
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">No run yet</h2>
          <p className="mt-0.5 text-desc text-ink-secondary">
            A run provisions the Pack that is live when it starts.
          </p>
          <div className="mt-3">
            <StartRunForm venture={venture} />
          </div>
        </section>
      ) : (
        <>
          <section className="rounded-xl border border-line bg-surface px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="text-section font-medium text-ink">
                Run <span className="font-mono">{detail.run_id.slice(0, 8)}</span> — Pack{" "}
                <span className="font-mono">{detail.pack_version}</span>
              </h2>
              <span
                className={`rounded-lg border px-2 py-0.5 text-meta ${
                  detail.status === "rejected"
                    ? "border-bad-line bg-bad-bg text-bad"
                    : detail.status === "aborted"
                      ? // Abandonment is neutral. It says nothing about the artifacts,
                        // and colouring it like a judgement would say something it does
                        // not mean.
                        "border-line bg-surface-muted text-ink-secondary"
                      : detail.status === "complete"
                        ? "border-ok-line bg-ok-bg text-ok"
                        : "border-warn-line bg-warn-bg text-warn"
                }`}
                title={detail.disposition?.reason ?? undefined}
              >
                {waitingLine}
              </span>
            </div>
            <p className="mt-1 text-desc text-ink-secondary">
              At gate <span className="font-mono">{detail.current_gate}</span> —{" "}
              {detail.current_gate_name}.
              {detail.disposition ? (
                <>
                  {" "}
                  {detail.status === "rejected" ? "Rejected" : "Abandoned"} by{" "}
                  {detail.disposition.actor ?? "an operator"}{" "}
                  <Ago iso={detail.disposition.at} />
                  {detail.disposition.reason ? `: ${detail.disposition.reason}` : "."}
                </>
              ) : null}
            </p>
            {detail.artifacts_hash ? (
              <div className="mt-2">
                <Hash value={detail.artifacts_hash} label="artifacts" />
              </div>
            ) : (
              <p className="mt-2 text-meta text-ink-muted">
                Artifacts have not been generated yet — Gate 3 does that.
              </p>
            )}
          </section>

          {atGate4 && currentGate ? (
            <section className="rounded-xl border border-line bg-surface px-5 py-4">
              <h2 className="text-section font-medium text-ink">Gate 4 — human review</h2>
              <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
                This gate waits. It does not pass on its own, and nothing advances until a
                named human records what they read.
              </p>
              <div className="mt-4 space-y-4">
                <ReviewBrief
                  evidence={currentGate.evidence}
                  advisories={advisories}
                />
                <ReviewForm
                  runId={detail.run_id}
                  venture={venture}
                  artifactsHash={detail.artifacts_hash}
                />
              </div>
            </section>
          ) : null}

          {atGate10 ? (
            <section className="rounded-xl border border-line bg-surface px-5 py-4">
              <h2 className="text-section font-medium text-ink">
                Gate 10 — named-human sign-off
              </h2>
              <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
                Bound to the artifact hash. Separation of duties applies: whoever recorded
                the Gate 4 review cannot sign this.
              </p>
              <div className="mt-3">
                <SignOffForm
                  runId={detail.run_id}
                  venture={venture}
                  artifactsHash={detail.artifacts_hash}
                />
              </div>
            </section>
          ) : null}

          {isOpen ? (
            <div className="grid gap-4 md:grid-cols-2">
              <section className="rounded-xl border border-line bg-surface px-5 py-4">
                <h2 className="text-section font-medium text-ink">Advance</h2>
                <AdvanceForm
                  runId={detail.run_id}
                  venture={venture}
                  currentGate={detail.current_gate}
                />
              </section>
              <section className="rounded-xl border border-line bg-surface px-5 py-4">
                <h2 className="text-section font-medium text-ink">Abandon</h2>
                <AbortForm runId={detail.run_id} venture={venture} />
              </section>
            </div>
          ) : (
            <section className="rounded-xl border border-line bg-surface px-5 py-4">
              <h2 className="text-section font-medium text-ink">
                This run is {detail.display_status}
              </h2>
              <p className="mt-0.5 text-desc text-ink-secondary">
                A finished run cannot be advanced. Start a new one.
              </p>
              <div className="mt-3">
                <StartRunForm venture={venture} />
              </div>
            </section>
          )}

          <section className="rounded-xl border border-line bg-surface px-5 py-4">
            <h2 className="text-section font-medium text-ink">Gate ladder</h2>
            <p className="mt-0.5 text-desc text-ink-secondary">
              All sixteen, including the ones still ahead.
            </p>
            <div className="mt-3">
              <GateLadder ladder={detail.ladder} />
            </div>
          </section>
        </>
      )}

      <RunHistoryTable runs={runs} />
    </div>
  );
}
