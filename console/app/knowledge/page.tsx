import Link from "next/link";
import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { AlertTriangle } from "@/components/icons";
import { AsOf } from "@/components/local-time";
import { api, NotAuthenticated } from "@/lib/api";

import { RecordExclusion } from "./forms";
import { KnowledgeTabs } from "./tabs";

export const dynamic = "force-dynamic";

/**
 * The five knowledge bases, counted by substance.
 *
 * The page reported *Persona Library 60 entries* and *Historical Records 61 entries*.
 * Every persona is `Smoke NNNNNN`, standing in for the same broker; every record is an
 * abandoned run summarised "console smoke test". A library holding sixty copies of one
 * fixture has zero personas, and reporting it as sixty is the same failure as a green
 * check with no denominator.
 *
 * Each card also states its own gap. "0 entries" is a number; "Greenstone has three
 * positions across six lifecycle stages and no written SOP for any of them" is something
 * somebody can act on.
 */

type Overview = {
  as_of: string;
  bases: {
    key: string;
    name: string;
    blocks_gate_6: boolean;
    count: number;
    denominator: number | null;
    label: string;
    gap: string;
  }[];
  fixtures: {
    total_rows: number;
    test_fixtures: number;
    personas: number;
    records: number;
    playbooks: number;
    personas_deletable: boolean;
    records_deletable: boolean;
  };
};

const TAB_FOR: Record<string, string> = {
  instructions: "/instructions",
  compliance: "/knowledge/compliance",
  playbooks: "/knowledge/playbooks",
  personas: "/knowledge/personas",
  history: "/knowledge/history",
};

export default async function KnowledgePage() {
  let overview: Overview;
  try {
    overview = await api.get<Overview>("/api/knowledge/overview");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const { fixtures } = overview;

  return (
    <div className="space-y-6">
      <Breadcrumb trail={[{ label: "Dashboard", href: "/" }, { label: "Knowledge" }]} />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-page font-medium text-ink">Knowledge bases</h1>
          <p className="mt-1 text-desc text-ink-secondary">
            Part 6 names five. Two of them block provisioning at Gate 6 and three are
            advisory at Gate 6 — a venture can operate without its SOPs written down,
            and cannot operate under a compliance flag nobody has defined.
          </p>
        </div>
        <span className="text-meta text-ink-muted">
          <AsOf iso={overview.as_of} />
        </span>
      </div>

      <KnowledgeTabs />

      {/*
        Stated before the counts, because the counts are what it is about. A page that
        says "60 personas" over sixty fixtures is not reporting a library; it is
        reporting its own test suite.
      */}
      {fixtures.test_fixtures > 0 ? (
        <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
          <h2 className="flex items-center gap-1.5 text-section font-medium text-bad">
            <AlertTriangle className="h-4 w-4" />
            {fixtures.test_fixtures} of {fixtures.total_rows} entries are test data
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            {fixtures.personas} personas and {fixtures.records} historical records were
            written by console smoke runs. They are excluded from every count on this page
            and filtered out of every table by default.
          </p>
          <p className="mt-2 max-w-3xl text-meta text-ink-muted">
            Neither store can be purged from here, and neither should be. Personas are
            write-only to this console — it holds no privilege to read a body back, let
            alone delete one. Historical records are append-only to everyone, refusing
            UPDATE and DELETE, and a bad entry is answered with a compensating entry
            rather than an edit. So excluding these rows is a reading decision, and the
            decision is itself recorded.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Link
              href="/knowledge/personas?include_fixtures=true&origin=test_fixture"
              className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
            >
              Review test personas
            </Link>
            <Link
              href="/knowledge/history?include_fixtures=true&origin=test_fixture"
              className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
            >
              Review test records
            </Link>
            <RecordExclusion
              counts={{ personas: fixtures.personas, records: fixtures.records }}
            />
          </div>
        </section>
      ) : null}

      <div className="space-y-3">
        {overview.bases.map((base) => (
          <Link
            key={base.key}
            href={TAB_FOR[base.key] ?? "/knowledge"}
            className="block rounded-xl border border-line bg-surface px-5 py-4 transition hover:bg-surface-muted"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-[15px] font-medium text-ink">{base.name}</h2>
                  <span
                    className={`rounded-lg border px-2 py-0.5 text-meta ${
                      base.blocks_gate_6
                        ? "border-bad-line bg-bad-bg text-bad"
                        : "border-line bg-surface-muted text-ink-secondary"
                    }`}
                  >
                    {base.blocks_gate_6 ? "blocks provisioning at Gate 6" : "advisory at Gate 6"}
                  </span>
                </div>
                {/* The gap, not the count. */}
                <p className="mt-1 max-w-3xl text-desc text-ink-secondary">{base.gap}</p>
              </div>

              <div className="shrink-0 text-right">
                <div className="text-[20px] font-medium leading-tight text-ink">
                  {base.count}
                  {base.denominator !== null ? (
                    <span className="text-desc text-ink-muted"> of {base.denominator}</span>
                  ) : null}
                </div>
                <div className="text-[11px] text-ink-muted">{base.label}</div>
              </div>
            </div>
          </Link>
        ))}
      </div>

      <p className="text-meta text-ink-muted">
        A flag with no entry reaches the agent as a label, not a constraint. A module with
        no instructions can never be certified.
      </p>
    </div>
  );
}
