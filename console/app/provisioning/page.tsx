import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import {
  Check,
  Hourglass,
  Loader,
  Lock,
  Minus,
  X,
} from "@/components/icons";
import { Ago, AsOf } from "@/components/local-time";
import {
  api,
  NotAuthenticated,
  type LadderRow,
  type PackDirectory,
  type ProvisioningCard,
  type ProvisioningDirectory,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import { Reject, Rerun, Resume, RunHistory, StartRun } from "./controls";

export const dynamic = "force-dynamic";

/**
 * Provisioning — Part 17 screen 13, rebuilt.
 *
 * The page's own subtitle promised that a run "stops at the first gate that blocks and
 * says which". It named the gate number and stopped there: sixteen gates were
 * represented by a fraction, `5 of 16`, and a fraction is a number without a map. It
 * could not say what happened at the gate that stopped the run, what cleared before it,
 * or what is still ahead — and it carried no action at all, so the provisioning page was
 * the one place you could not provision from.
 *
 * So: a ladder. Every gate, in order, whether or not it ran, with the gate that stopped
 * the run filled in danger and the ceiling gate always visible in warning. Those are two
 * unrelated walls — the one this run hit, and the one every run in this deployment will
 * hit — and the old page gave no way to tell them apart.
 *
 * What is deliberately absent is any control that passes a gate. The ceiling notice says
 * there is no override; a page offering one would make that copy a lie.
 */

const ORDINALS = [
  "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
  "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
  "sixteenth",
];

/** Colour encodes state only; the icon carries the meaning for anyone who cannot see it. */
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
 * The whole path, never truncated.
 *
 * A ladder that listed only what has happened could not show what is still ahead of a
 * stopped run, which is most of the reason to draw one.
 */
function Ladder({ ladder }: { ladder: LadderRow[] }) {
  return (
    <ol className="mt-1">
      {ladder.map((row) => {
        const stopped = row.state === "blocked";
        const ceiling = row.is_ceiling && row.state !== "passed";
        const fill = stopped
          ? "bg-bad-bg"
          : ceiling
            ? "bg-warn-bg"
            : row.state === "awaiting"
              ? "bg-warn-bg"
              : "";
        return (
          <li
            key={row.gate}
            title={row.title}
            className={`flex items-baseline gap-2 rounded-md px-2 py-1 ${fill}`}
          >
            <span className="self-center">
              <GateIcon row={row} />
            </span>
            <span className="w-7 shrink-0 text-right font-mono text-meta text-ink-muted">
              {row.gate}
            </span>
            <span
              className={`text-desc ${
                stopped
                  ? "text-bad"
                  : ceiling
                    ? "text-warn"
                    : row.state === "pending"
                      ? "text-ink-muted"
                      : "text-ink"
              }`}
            >
              {row.name}
              {ceiling ? (
                <span className="text-warn"> — ceiling, not buildable yet</span>
              ) : null}
            </span>
            <span className="ml-auto shrink-0 text-meta text-ink-muted">
              {elapsed(row.seconds)}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Why the run stopped — the gate, what happened, who acted, and what it means next.
 *
 * The old page said `aborted, gate 4`. Gate 4 is human review, so that could have been a
 * rejection, a timeout or an error, and nothing on the page could tell you which.
 *
 * The reason is always this run's own recorded outcome. Rendering the gate's generic
 * description here would produce a sentence that is true of every run and about none.
 */
function StopReason({ venture }: { venture: ProvisioningCard }) {
  const run = venture.run;
  if (!run?.stop) return null;

  const ceiling = run.display_status === "at ceiling";
  const tone = ceiling
    ? "border-warn-line bg-warn-bg"
    : "border-bad-line bg-bad-bg";
  const text = ceiling ? "text-warn" : "text-bad";

  const downstream = venture.ladder.filter((row) => row.downstream_of_stop).length;

  // The gate is already named at the start of the line, so the status drops its
  // " at gate N" tail here rather than reading "Gate 4 — human review · rejected at
  // gate 4". The full form is what the card heading uses, where there is no context.
  const disposition = run.display_status.replace(/ at gate .*$/, "");

  return (
    <div className={`mt-3 rounded-xl border px-3 py-2.5 ${tone}`}>
      <p className={`text-desc font-medium ${text}`}>
        Gate {run.stop.gate} — {run.stop.name.toLowerCase()} · {disposition}
        {/*
          The actor who acted *at the gate*, which for a run somebody ended is not the
          person who started it. Falling back to the starter would credit a cancellation
          to whoever kicked the run off days earlier.
        */}
        {run.stop.actor ? ` by ${run.stop.actor}` : ""}
        {run.stop.at ? ` · $<Ago iso={run.stop.at} />` : ""}
      </p>
      <p className="mt-1 text-desc text-ink-secondary">
        {run.stop.reason}
        {downstream ? (
          <>
            {" "}
            {downstream} gate{downstream === 1 ? "" : "s"} downstream never ran.
          </>
        ) : null}
      </p>
    </div>
  );
}

/** The numbering is not a bug, and the page has to say so before a reader decides it is. */
function Numbering({ venture, total }: { venture: ProvisioningCard; total: number }) {
  const fractional = venture.ladder
    .filter((row) => row.gate.includes("."))
    .map((row) => row.gate);
  const cleared = venture.run?.gates_passed ?? 0;
  const stopIndex = venture.ladder.findIndex((row) => row.is_current);

  return (
    <p className="mt-2 text-meta text-ink-muted">
      Gates {fractional.slice(0, -1).join(", ")} and {fractional.at(-1)} were inserted
      after the original twelve, so gate numbers and the cleared count differ.
      {venture.run && stopIndex >= 0 ? (
        <>
          {" "}
          {cleared} gate{cleared === 1 ? "" : "s"} cleared, stopped at the{" "}
          {ORDINALS[stopIndex] ?? `${stopIndex + 1}th`}.
        </>
      ) : (
        <> {total} gates in all.</>
      )}
    </p>
  );
}

function Meta({ venture }: { venture: ProvisioningCard }) {
  const run = venture.run;
  if (!run) return null;

  // `Date.now()` for an open run is read once on the server and again on hydration, so
  // the two renders disagree by however long the round trip took. A run that is still
  // going has no settled duration anyway - saying so is more honest than a number that
  // was true for one instant on a machine the reader is not using.
  const started = new Date(run.started_at).getTime();
  const duration = run.completed_at
    ? elapsed(Math.max(0, new Date(run.completed_at).getTime() - started) / 1000)
    : null;

  return (
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-2.5 text-meta text-ink-muted">
      <span>
        Run <code className="text-ident text-ink-secondary">{run.run_id.slice(0, 8)}</code>
      </span>
      <span>started <Ago iso={run.started_at} /></span>
      {duration ? (
        <span>{duration} elapsed</span>
      ) : (
        <span>still running</span>
      )}
      <span>
        {run.gates_passed} of {venture.ladder.length} gates cleared
      </span>
      {/* A run against a superseded Pack is not evidence about the current one. */}
      <span>
        Pack <span className="font-mono text-ink-secondary">{run.pack_version}</span>
        {venture.live_pack_version && venture.live_pack_version !== run.pack_version
          ? ` · ${venture.live_pack_version} is now live`
          : ""}
      </span>
    </div>
  );
}

function VentureCard({
  venture,
  total,
}: {
  venture: ProvisioningCard;
  total: number;
}) {
  return (
    <article className="rounded-xl border border-line bg-surface px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-rowtitle font-medium text-ink">
              {venture.display_name}
            </h3>
            <code className="text-ident text-ink-muted">{venture.venture_id}</code>
          </div>
          <p className="mt-0.5 text-desc text-ink-secondary">
            {venture.run
              ? venture.run.display_status
              : "No run has been started for this venture."}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Rerun ventureId={venture.venture_id} />
          <Link
            href={`/provisioning/${encodeURIComponent(venture.venture_id)}`}
            className="text-desc text-ink underline underline-offset-2"
          >
            Open run
          </Link>
        </div>
      </div>

      <StopReason venture={venture} />

      <div className="mt-3">
        <Ladder ladder={venture.ladder} />
        <Numbering venture={venture} total={total} />
      </div>

      <Meta venture={venture} />

      <div className="mt-3 flex flex-wrap items-start gap-3">
        <Resume venture={venture} />
        <Reject venture={venture} />
        <RunHistory ventureId={venture.venture_id} total={venture.runs_total} />
      </div>
    </article>
  );
}

export default async function ProvisioningPage() {
  let directory: ProvisioningDirectory;
  let packs: PackDirectory;
  try {
    [directory, packs] = await Promise.all([
      api.get<ProvisioningDirectory>("/api/provisioning/directory"),
      api.get<PackDirectory>("/api/packs/directory"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  // A venture whose Pack fails validation is offered and disabled with the count, never
  // hidden: Gate 2 would refuse the run, and the picker should say so before it is
  // started rather than after.
  const candidates = packs.packs.map((pack) => {
    const failing = pack.validation.failures.length;
    const unrun = pack.validation.not_run.length;
    return {
      venture_id: pack.venture_id,
      display_name: pack.display_name,
      blocked_reason: failing
        ? `${failing} validator rule${failing === 1 ? "" : "s"} failing`
        : unrun
          ? `${unrun} validator rule${unrun === 1 ? "" : "s"} could not run`
          : null,
    };
  });

  return (
    <div className="space-y-6">
      <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Provisioning" }]} />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">Provisioning</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            Sixteen gates from a Business Pack to a live venture. A run stops at the
            first gate that blocks and says which.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <span className="text-meta text-ink-muted">
            <AsOf iso={directory.as_of} />
          </span>
          <StartRun candidates={candidates} />
        </div>
      </div>

      {/*
        A live constraint, not a paragraph of explanation. It was styled identically to
        body copy, which is how the strongest sentence in the console came to read like
        a footnote.
      */}
      <section className="rounded-xl border border-warn-line bg-warn-bg px-5 py-4">
        <div className="flex items-start gap-2">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div>
            <h2 className="text-section font-medium text-warn">
              Ceiling in this deployment: gate 9.5
            </h2>
            <p className="mt-0.5 text-desc text-ink-secondary">
              Stated here rather than discovered at the gate.
            </p>
            <p className="mt-2 max-w-3xl text-desc text-ink-secondary">
              SimForge&rsquo;s held-out adversarial partition does not exist yet, so no
              run started from this console can pass gate 9.5 and no venture can reach
              gate 12. That is <strong className="font-medium">blocked</strong>, not
              skipped: a run that skipped certification would produce a venture reading
              as fully provisioned that has been certified for nothing. There is no
              override, deliberately.
            </p>
          </div>
        </div>
      </section>

      {directory.ventures.length ? (
        <div className="space-y-4">
          {directory.ventures.map((venture) => (
            <VentureCard
              key={venture.venture_id}
              venture={venture}
              total={directory.gates_total}
            />
          ))}
        </div>
      ) : (
        /*
          The pipeline, rather than a blank card. What a run *will* do is more use than
          nothing, and it is the same ladder every run is measured against.
        */
        <section className="rounded-xl border border-line bg-surface px-5 py-4">
          <h2 className="text-section font-medium text-ink">
            What a run does, gate by gate
          </h2>
          <Ladder ladder={directory.empty_ladder} />
          <p className="mt-3 border-t border-line pt-3 text-desc text-ink-secondary">
            No provisioning run has been started. The ladder above is what a run will do.
          </p>
          <p className="mt-2 text-meta text-ink-muted">
            A run needs a venture with a Pack.{" "}
            <Link href="/ventures" className="text-ink underline underline-offset-2">
              New venture
            </Link>{" "}
            registers one; the Pack is authored on{" "}
            <Link href="/packs" className="text-ink underline underline-offset-2">
              Packs
            </Link>
            .
          </p>
        </section>
      )}
    </div>
  );
}
