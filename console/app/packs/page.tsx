import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle, GitCompare } from "@/components/icons";
import {
  api,
  NotAuthenticated,
  type PackCard,
  type PackDirectory,
  type PackTemplateCategory,
  type RuleHit,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

import { templateCategories } from "./actions";
import { Hash, NewPack, PublishDraft } from "./forms";

export const dynamic = "force-dynamic";

/**
 * Business Packs — Part 17 screen 12, rebuilt.
 *
 * The old page listed which ventures had a Pack and gave the first sixteen characters
 * of a hash. It could not answer the question a reader opens it to ask: **can this Pack
 * provision, and if not, why.** A Pack failing any FAIL rule cannot provision, cannot
 * generate and cannot appoint — so validation state is the most important thing here,
 * and it was the one thing the page did not show.
 *
 * Four validation states, not two. `not validated` exists because a rule that could not
 * run has not passed, and rendering "nothing was found wrong" the same way as "every
 * rule passed" is the failure mode this page exists to prevent. A Pack is only `valid`
 * when every rule that can run has run and passed.
 *
 * Three version states, because they are genuinely different documents: the draft
 * somebody is writing, the live one that would be provisioned next, and the one the
 * running system was actually built from. When the last two differ, that is drift, and
 * nothing in the old page could express it.
 */

const STATE_LABEL: Record<PackCard["validation"]["state"], string> = {
  failing: "cannot provision",
  not_validated: "not validated",
  warnings: "provisions with warnings",
  valid: "can provision",
};

const STATE_TONE: Record<PackCard["validation"]["state"], string> = {
  failing: "border-bad-line bg-bad-bg text-bad",
  // Deliberately not neutral. "Not validated" is an unknown, and an unknown about
  // whether a Pack can provision is a warning, not a resting state.
  not_validated: "border-warn-line bg-warn-bg text-warn",
  warnings: "border-warn-line bg-warn-bg text-warn",
  valid: "border-ok-line bg-ok-bg text-ok",
};

function Rules({
  hits,
  tone,
  heading,
}: {
  hits: RuleHit[];
  tone: string;
  heading: string;
}) {
  if (hits.length === 0) return null;
  return (
    <div>
      <p className="text-meta text-ink-muted">{heading}</p>
      <ul className="mt-1 space-y-1">
        {hits.map((hit) => (
          <li key={hit.rule_id} className="text-desc text-ink-secondary">
            {/*
              The validator's own message, which says what is wrong with *this* Pack
              ("no operating instructions authored for 3 modules"), not the rule's
              description ("every position's modules have instructions"). The second is a
              specification; only the first tells anybody what to go and do.
            */}
            <span className={`font-mono text-meta ${tone}`}>{hit.rule_id}</span>{" "}
            {hit.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** How much of the schema this Pack fills in. A different question from validation. */
function SchemaBar({ schema }: { schema: PackCard["schema"] }) {
  const pct = Math.round((schema.present / schema.total) * 100);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-meta text-ink-muted">Schema blocks</span>
        <span className="text-meta text-ink-secondary">
          {schema.present} of {schema.total}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-muted">
        <div
          className={`h-full rounded-full ${
            schema.required_missing.length ? "bg-bad" : "bg-ok"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {schema.missing.length ? (
        <p className="mt-1 text-meta text-ink-muted">
          {schema.required_missing.length ? (
            <span className="text-bad">
              required: {schema.required_missing.join(", ")}.{" "}
            </span>
          ) : null}
          {schema.missing
            .filter((block) => !schema.required_missing.includes(block))
            .join(", ") || null}
          {schema.required_missing.length ? null : " — all optional"}
        </p>
      ) : null}
    </div>
  );
}

/** Draft, live, provisioned. Drift is live ≠ provisioned. */
function Versions({ pack }: { pack: PackCard }) {
  const { draft, live, provisioned } = pack.versions;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="text-meta text-ink-muted">Versions</span>
        {draft ? (
          <span className="text-desc text-ink-secondary">
            <span className="rounded bg-surface-muted px-1.5 py-0.5 text-meta">draft</span>{" "}
            <span className="font-mono">{draft.version}</span> · {relativeAge(draft.authored_at)}
            {draft.author ? ` by ${draft.author}` : ""}
          </span>
        ) : null}
        {live ? (
          <span className="text-desc text-ink-secondary">
            <span className="rounded bg-ok-bg px-1.5 py-0.5 text-meta text-ok">live</span>{" "}
            <span className="font-mono">{live.version}</span> · {relativeAge(live.authored_at)}
            {live.author ? ` by ${live.author}` : ""}
          </span>
        ) : (
          <span className="text-desc text-ink-muted">no live version</span>
        )}
        <span className="text-desc text-ink-secondary">
          <span className="rounded bg-surface-muted px-1.5 py-0.5 text-meta">provisioned</span>{" "}
          {provisioned ? (
            <span className="font-mono">{provisioned}</span>
          ) : (
            <span className="text-ink-muted">never</span>
          )}
        </span>
      </div>

      {live ? <Hash value={live.content_hash} label="live hash" /> : null}
      {draft ? <Hash value={draft.content_hash} label="draft hash" /> : null}

      {pack.drift ? (
        <p className="flex items-start gap-1.5 text-desc text-warn">
          <GitCompare className="mt-px h-3.5 w-3.5 shrink-0" />
          Drift: the running system was provisioned from {provisioned}, and{" "}
          {live?.version} is what is published. The next run provisions {live?.version};
          until then the two describe different systems.
        </p>
      ) : null}

      {pack.signatures_voided_by_publish ? (
        <p className="flex items-start gap-1.5 text-desc text-bad">
          <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
          {pack.signatures} Gate 10 signature{pack.signatures === 1 ? "" : "s"} no longer
          cover what is published. A signature binds to the artifacts one version
          generates — nothing revoked these, they stopped matching.
        </p>
      ) : null}
    </div>
  );
}

/** What this Pack has actually produced. Zero is a real answer; unknown is not. */
function Artifacts({ pack }: { pack: PackCard }) {
  return (
    <div>
      <p className="text-meta text-ink-muted">Generated from this Pack</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {pack.artifacts.map((artifact) => (
          <span
            key={artifact.name}
            title={artifact.note ?? undefined}
            className={`rounded-lg border px-2 py-0.5 text-meta ${
              artifact.count === null
                ? "border-line text-ink-muted"
                : artifact.count === 0
                  ? "border-warn-line bg-warn-bg text-warn"
                  : "border-line bg-surface-muted text-ink-secondary"
            }`}
          >
            {artifact.name}
            {artifact.count === null ? (
              // Not an absence. Workflow and the task ledger are generated on demand and
              // stored nowhere, and rendering them as "0" would read as a generator that
              // failed rather than a decision somebody made.
              <span className="ml-1 text-ink-muted">on demand</span>
            ) : (
              <span className="ml-1 font-mono">{artifact.count}</span>
            )}
          </span>
        ))}
      </div>
      {pack.nothing_generated ? (
        <p className="mt-1.5 text-meta text-ink-muted">
          Nothing has been generated from this Pack yet
          {pack.never_provisioned ? " — it has never been provisioned." : "."}
        </p>
      ) : null}
    </div>
  );
}

function Card({ pack, rulesTotal }: { pack: PackCard; rulesTotal: number }) {
  const { validation } = pack;
  const problems = validation.failures.length;

  return (
    <article className="rounded-2xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-rowtitle font-medium text-ink">{pack.display_name}</h3>
            <code className="text-ident text-ink-muted">{pack.venture_id}</code>
          </div>
          <span
            className={`mt-2 inline-block rounded-lg border px-2 py-0.5 text-meta ${
              STATE_TONE[validation.state]
            }`}
          >
            {STATE_LABEL[validation.state]}
            {problems
              ? ` · ${problems} of ${validation.rules_checked} rules failing`
              : validation.state === "not_validated"
                ? ` · ${validation.not_run.length} of ${validation.rules_checked} rules could not run`
                : ` · ${validation.rules_checked} of ${rulesTotal} rules checked`}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {pack.versions.draft ? <PublishDraft ventureId={pack.venture_id} /> : null}
          <Link
            href={`/packs/${encodeURIComponent(pack.venture_id)}`}
            className="text-desc text-ink underline underline-offset-2"
          >
            Open editor
          </Link>
        </div>
      </div>

      <div className="mt-4 space-y-3 border-t border-line pt-4">
        <Rules heading="Failing" hits={validation.failures} tone="text-bad" />
        <Rules
          heading="Could not run — these have validated nothing"
          hits={validation.not_run}
          tone="text-warn"
        />
        <Rules heading="Warnings" hits={validation.warnings} tone="text-warn" />
        {validation.deferred.length ? (
          <p className="text-meta text-ink-muted">
            {validation.deferred.map((rule) => rule.rule_id).join(", ")} evaluated at a
            later gate, not here.
          </p>
        ) : null}
      </div>

      <div className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
        <Versions pack={pack} />
        <div className="space-y-4">
          <SchemaBar schema={pack.schema} />
          <Artifacts pack={pack} />
        </div>
      </div>
    </article>
  );
}

/**
 * Ventures with an engagement and no document to provision from.
 *
 * Fixed, not conditional. The old page rendered this list only when it was non-empty,
 * which meant the most consequential state — no Pack anywhere — showed as an empty
 * table under a heading, indistinguishable from everything being fine.
 */
function NoPackPanel({
  packless,
  unregistered,
  portfolioSize,
}: {
  packless: string[];
  unregistered: PackDirectory["unregistered_portfolio"];
  portfolioSize: number;
}) {
  const total = packless.length + unregistered.length;

  return (
    <section className="rounded-xl bg-surface-muted px-5 py-4">
      <h2 className="text-section font-medium text-ink">
        {total} of {portfolioSize} portfolio ventures have no Pack
      </h2>
      <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
        An engagement exists here — grants, manifest rows or a budget — but there is no
        document to provision from.
      </p>

      {packless.length ? (
        <ul className="mt-3 space-y-1 border-t border-line pt-3">
          {packless.map((venture) => (
            <li key={venture} className="text-desc text-ink-secondary">
              <code className="text-ident text-ink">{venture}</code> — registered, no
              Pack. Gate 1 refuses a run without one.
            </li>
          ))}
        </ul>
      ) : null}

      {unregistered.length ? (
        <ul className="mt-3 space-y-1 border-t border-line pt-3">
          {unregistered.map((venture) => (
            <li key={venture.slug} className="text-desc text-ink-secondary">
              <span className="text-ink">{venture.display_name}</span>{" "}
              <code className="text-ident text-ink-muted">{venture.slug}</code> — named
              in the portfolio, not authored here. It is absent, not healthy.
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export default async function PacksPage() {
  let directory: PackDirectory;
  let categories: PackTemplateCategory[];
  try {
    [directory, categories] = await Promise.all([
      api.get<PackDirectory>("/api/packs/directory"),
      templateCategories(),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const provisionable = directory.packs.filter(
    (pack) => pack.validation.state === "valid" || pack.validation.state === "warnings",
  ).length;
  const drifting = directory.packs.filter((pack) => pack.drift).length;

  return (
    <div className="space-y-6">
      <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Packs" }]} />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">Business Packs</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            The Pack is the document every artifact derives from — positions,
            appointments, workflow, task ledger, curriculum, grants. Publishing
            supersedes the live version; the next provisioning run provisions the new
            one.
          </p>
        </div>
        <NewPack
          categories={categories}
          existing={directory.packs
            .filter((pack) => pack.versions.live)
            .map((pack) => ({
              venture_id: pack.venture_id,
              display_name: pack.display_name,
            }))}
        />
      </div>

      {directory.packs.length ? (
        <p className="text-desc text-ink-secondary">
          {provisionable} of {directory.packs.length} authored Pack
          {directory.packs.length === 1 ? "" : "s"} can provision, against{" "}
          {directory.rules_total} validator rules and {directory.schema_blocks} schema
          blocks.
          {drifting
            ? ` ${drifting} has drifted from what is running.`
            : " None has drifted from what is running."}
        </p>
      ) : null}

      {directory.packs.length ? (
        <div className="space-y-4">
          {directory.packs.map((pack) => (
            <Card key={pack.venture_id} pack={pack} rulesTotal={directory.rules_total} />
          ))}
        </div>
      ) : (
        <section className="rounded-2xl border border-line bg-surface px-5 py-8 text-center">
          <p className="text-section font-medium text-ink">No venture has a Pack</p>
          <p className="mx-auto mt-1 max-w-xl text-desc text-ink-secondary">
            Gate 1 refuses a provisioning run without one, so nothing in the portfolio
            can reach production from here. Start from a template — it fills in the
            schema and the compliance surface for a category, and leaves every
            venture-specific decision to you.
          </p>
        </section>
      )}

      <NoPackPanel
        packless={directory.packless}
        unregistered={directory.unregistered_portfolio}
        portfolioSize={directory.portfolio_size}
      />

      <p className="text-meta text-ink-muted">
        As of {new Date(directory.as_of).toLocaleString()}. Validation runs against the
        live database each time this page loads — a Pack that passed yesterday can fail
        today because a Forge went unreachable or an instruction was withdrawn.
      </p>
    </div>
  );
}
