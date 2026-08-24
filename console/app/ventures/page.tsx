import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { ExternalLink, PlugOff } from "@/components/icons";
import {
  api,
  NotAuthenticated,
  type PortfolioGap,
  type VentureCard,
  type VentureDirectory,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import { NewVenture, VentureMenu } from "./forms";

export const dynamic = "force-dynamic";

/**
 * Venture directory — Part 17.
 *
 * The old page showed five columns and none of them answered the question a reader
 * opens it to ask: **where is this venture, and can it go live.** Pipeline state is a
 * venture's most important attribute and it appeared nowhere — and a table row has
 * nowhere to put the blocked reason, which is the most important content here.
 *
 * So: cards. Each one names its status with the gate number in it, says in a sentence
 * what is blocking it, shows the six phases of the sixteen-gate pipeline, and carries a
 * stat strip where every number has a denominator.
 *
 * The panel at the bottom is the same principle as the Compliance banner: four of the
 * five portfolio ventures have no Pack, and absence must not be able to look like
 * health. They are listed as missing rather than simply not rendered.
 */

const STATUS_TONE: Record<string, string> = {
  draft: "border-neutral2-line bg-neutral2-bg text-neutral2",
  validating: "border-warn-line bg-warn-bg text-warn",
  "in certification": "border-warn-line bg-warn-bg text-warn",
  "awaiting sign-off": "border-warn-line bg-warn-bg text-warn",
  live: "border-ok-line bg-ok-bg text-ok",
  "winding down": "border-neutral2-line bg-neutral2-bg text-neutral2",
  archived: "border-line bg-surface-muted text-ink-muted",
};

/** `blocked at gate N` is dynamic, so it is matched by prefix rather than listed. */
function toneFor(status: string): string {
  if (status.startsWith("blocked")) {
    return "border-bad-line bg-bad-bg text-bad";
  }
  return STATUS_TONE[status] ?? "border-warn-line bg-warn-bg text-warn";
}

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

/** Six segments, one per phase of the sixteen-gate pipeline. */
function GateBar({ venture }: { venture: VentureCard }) {
  const blocked = venture.status.startsWith("blocked");
  const live = venture.status === "live";

  return (
    <div>
      <div className="flex gap-1">
        {venture.phases.map((phase) => {
          const fill =
            phase.state === "done"
              ? "bg-ok"
              : phase.state === "current"
                ? blocked
                  ? "bg-bad"
                  : "bg-warn"
                : "bg-surface-muted";
          return (
            <div
              key={phase.name}
              className={`h-1.5 flex-1 rounded-full ${fill}`}
              title={`${phase.name}: ${phase.state}`}
            />
          );
        })}
      </div>
      <p className="mt-1.5 text-meta text-ink-muted">
        {live
          ? "Live · all sixteen gates passed"
          : venture.gate
            ? `Gate ${venture.gate} of ${venture.gate_total - 1} · ${venture.phases
                .map((p) => p.name)
                .join(" → ")}`
            : `Not started · ${venture.phases.map((p) => p.name).join(" → ")}`}
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div>
      <div className="text-meta text-ink-muted">{label}</div>
      <div className={`text-desc ${muted ? "text-ink-muted" : "text-ink"}`}>{value}</div>
    </div>
  );
}

function VentureCardView({ venture }: { venture: VentureCard }) {
  const blocked = venture.status.startsWith("blocked");
  const cap = venture.monthly_usd_cap;
  const softCapAt = cap && venture.soft_cap_pct ? (cap * venture.soft_cap_pct) / 100 : null;
  const spendPct = cap ? Math.min(100, (venture.spend_this_month / cap) * 100) : 0;

  return (
    <article className="rounded-xl border-[0.5px] border-line bg-surface px-5 py-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-section font-medium text-ink">{venture.display_name}</h3>
            <code className="text-ident text-ink-muted">{venture.slug}</code>
            <span
              className={`inline-flex items-center rounded-md border px-2 py-0.5 text-meta ${toneFor(venture.status)}`}
            >
              {venture.status}
            </span>
          </div>
          <p className="mt-1 text-desc text-ink-secondary">
            {venture.category}
            {" · "}
            {venture.carries_phi ? "carries PHI" : "no PHI"}
            {venture.operating_forge ? ` · ${venture.operating_forge}` : " · no Forge yet"}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <Link
            href={`/ventures/${encodeURIComponent(venture.slug)}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1 text-desc text-ink-secondary hover:border-line-strong hover:text-ink"
          >
            <ExternalLink size={14} />
            Open
          </Link>
          <VentureMenu slug={venture.slug} archived={venture.status === "archived"} />
        </div>
      </header>

      {/* Only when blocked. The sentence names the specific blocker and what it
          prevents, and it comes from the rule that failed rather than a lookup table -
          one of the example blockers this page was specified with had already stopped
          being true. */}
      {blocked && venture.blocked_because ? (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-bad-line bg-bad-bg px-3 py-2">
          <PlugOff size={16} className="mt-0.5 shrink-0 text-bad" />
          <p className="text-desc text-bad">{venture.blocked_because}</p>
        </div>
      ) : null}

      <div className="mt-4">
        <GateBar venture={venture} />
      </div>

      <div className="mt-4 grid gap-3 border-t border-line pt-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat
          label="Positions filled"
          value={`${venture.positions_filled} of ${venture.positions_defined} defined`}
          muted={venture.positions_defined === 0}
        />
        <Stat label="Live grants" value={String(venture.live_grants)} />
        <Stat
          label="Spend / cap"
          // "Unmetered" means no budget row exists, not a zero cap.
          value={cap === null ? "unmetered" : `$${venture.spend_this_month.toLocaleString()} of $${cap.toLocaleString()}`}
          muted={cap === null}
        />
        <Stat
          label="Frameworks"
          value={
            venture.frameworks.length === 0
              ? "none declared"
              : `${venture.frameworks_wired} of ${venture.frameworks.length} wired`
          }
          muted={venture.frameworks.length === 0}
        />
        <Stat
          label="Last activity"
          value={venture.last_activity ? relativeAge(venture.last_activity) : "none yet"}
          muted={!venture.last_activity}
        />
      </div>

      {/* The hard cap, with its current setting rather than an unlabelled button. */}
      <div className="mt-3 flex flex-wrap items-center gap-3 text-meta">
        <span className="text-ink-muted">Hard cap</span>
        {cap === null ? (
          <span className="text-warn">unmetered</span>
        ) : (
          <span className="text-ink-secondary">
            {venture.hard_cap_action ?? "pause"} at ${cap.toLocaleString()}
            {venture.soft_cap_pct
              ? ` · soft cap ${venture.soft_cap_pct}% ($${softCapAt?.toLocaleString()})`
              : ""}
          </span>
        )}
        {venture.hard_cap_reversed_at ? (
          <span className="text-warn">reversed {relativeAge(venture.hard_cap_reversed_at)}</span>
        ) : null}
      </div>

      {/* The burn-down bar renders only when there is real spend. A bar pinned at zero
          would be read as "nothing spent" when it means "nothing measured". */}
      {cap !== null && venture.spend_this_month > 0 ? (
        <div className="mt-2">
          <div className="relative h-1.5 rounded-full bg-surface-muted">
            <div
              className={`h-1.5 rounded-full ${spendPct >= (venture.soft_cap_pct ?? 80) ? "bg-warn" : "bg-ok"}`}
              style={{ width: `${spendPct}%` }}
            />
            {venture.soft_cap_pct ? (
              <div
                className="absolute top-0 h-1.5 w-px bg-warn"
                style={{ left: `${venture.soft_cap_pct}%` }}
                title={`soft cap ${venture.soft_cap_pct}%`}
              />
            ) : null}
          </div>
          <p className="mt-1 text-meta text-ink-muted">
            At the soft cap every agent in this venture downgrades to propose.
          </p>
        </div>
      ) : cap !== null ? (
        <p className="mt-2 text-meta text-ink-muted">
          No spend recorded. Cost attribution is not wired — Forges report no usage, so
          this is zero because nothing is measured rather than because nothing was spent.
        </p>
      ) : null}
    </article>
  );
}

function MissingPanel({ missing, total }: { missing: PortfolioGap[]; total: number }) {
  if (missing.length === 0) return null;
  return (
    <section className="rounded-xl bg-surface-muted px-5 py-4">
      <h2 className="text-section font-medium text-ink">
        {missing.length} of {total} portfolio ventures have no Pack yet
      </h2>
      <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
        {missing.map((m) => m.display_name).join(", ")}{" "}
        {missing.length === 1 ? "is" : "are"} named in the portfolio but not authored
        here. They do not appear above because nothing exists to show — not because they
        are healthy.
      </p>

      <ul className="mt-3 space-y-3">
        {missing.map((venture) => (
          <li
            key={venture.slug}
            className="flex flex-wrap items-start justify-between gap-3 border-t border-line pt-3"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-rowtitle font-medium text-ink">
                  {venture.display_name}
                </span>
                <code className="text-ident text-ink-muted">{venture.slug}</code>
              </div>
              <p className="mt-0.5 text-desc text-ink-secondary">
                {venture.category} · {venture.operating_status} ·{" "}
                {venture.frameworks.join(", ")}
              </p>
              <p className="mt-0.5 text-meta text-ink-muted">{venture.note}</p>
            </div>
            <div className="shrink-0">
              <NewVenture
                prefill={{
                  display_name: venture.display_name,
                  category: venture.category,
                  slug: venture.slug,
                }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default async function VenturesPage() {
  let directory: VentureDirectory;
  try {
    directory = await api.get<VentureDirectory>("/api/ventures/directory");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { scorecard } = directory;
  const asOf = new Date(directory.as_of);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Ventures" }]} />
          <h1 className="mt-1 text-[18px] font-medium text-ink">Ventures</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            The Village carries several ventures at once. One venture per agent per
            shift.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <p className="text-meta text-ink-muted">
            As of {asOf.toISOString().replace("T", " ").slice(0, 19)} UTC
          </p>
          <NewVenture />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Live"
          value={`${scorecard.live.value} of ${scorecard.live.denominator}`}
          note="a venture is live when an agent could actually act for it"
        />
        <Metric
          label="Agents appointed"
          value={`${scorecard.agents_appointed.value} of ${scorecard.agents_appointed.denominator}`}
          note={scorecard.agents_appointed.note}
        />
        <Metric
          label="Spend this month"
          value={`$${scorecard.spend_this_month.value.toLocaleString()} of $${scorecard.spend_this_month.denominator.toLocaleString()}`}
          note={scorecard.spend_this_month.note}
        />
        <Metric
          label="Blocked"
          value={`${scorecard.blocked.value} of ${scorecard.blocked.denominator}`}
          alarming={scorecard.blocked.value > 0}
        />
      </div>

      {directory.ventures.length === 0 ? (
        <section className="rounded-xl border-[0.5px] border-line bg-surface px-5 py-8 text-center">
          <h2 className="text-section font-medium text-ink">No ventures yet</h2>
          <p className="mx-auto mt-2 max-w-xl text-desc text-ink-secondary">
            A venture is an engagement the Village operates — a named business with its
            own Business Pack, its own compliance surface, and its own agents. One
            venture per agent per shift, so a venture is also the boundary an agent&rsquo;s
            work is isolated inside.
          </p>
          <div className="mt-4 inline-block">
            <NewVenture />
          </div>
        </section>
      ) : (
        <div className="space-y-3">
          {directory.ventures.map((venture) => (
            <VentureCardView key={venture.slug} venture={venture} />
          ))}
        </div>
      )}

      <MissingPanel missing={directory.missing} total={directory.portfolio_size} />

      <p className="text-meta text-ink-muted">
        &quot;Unmetered&quot; means no budget row exists, not a zero cap. Validator rule
        V18 makes budget caps a required Pack field, so an unmetered venture cannot reach
        production.
      </p>
    </div>
  );
}
