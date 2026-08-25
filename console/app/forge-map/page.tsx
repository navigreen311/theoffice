import Link from "next/link";
import { redirect } from "next/navigation";

import { AlertTriangle, CircleCheck } from "@/components/icons";
import { AsOf, LocalTime } from "@/components/local-time";
import { api, NotAuthenticated, type VentureRow } from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Forge Map — Part 15 / Part 17.
 *
 * The subtitle promised "Declared × Required × In-Use. The diff is the information" and
 * the table had one Required column. Worse, all three states came from one place: a
 * `venture_forge_manifest` row was both the declaration and the requirement, so the diff
 * it advertised could not exist.
 *
 * They come from the three places they actually live now — the Pack, the generator
 * output, and the call ledger — which is also why this page has content at all. The
 * generators have never run, so the manifest is empty and the table used to render
 * nothing. The Pack declares nine modules right now, and "everything declared, nothing
 * required yet" is a finding; "nothing declared" was not even true.
 */

type Row = {
  forge_id: string;
  module_id: string;
  declared: boolean;
  required: boolean;
  calls_30d: number;
  criticality: string | null;
  mismatch: string;
  tone: string;
  meaning: string;
};

type Reconciliation = {
  as_of: string;
  rows: Row[];
  declared_count: number;
  required_count: number;
  in_use_count: number;
  blocked_reason: string | null;
  handlers: { mismatch: string; tone: string; meaning: string }[];
  pending_dispositions: { forge_id: string; module_id: string; call_count: number }[];
};

type Forge = {
  forge_id: string;
  display_name: string;
  note: string;
  bridged: boolean;
  health: string | null;
  credential_mode: string | null;
  api_version: string | null;
  last_health_check: string | null;
  instruction_modules: number;
  pinned_versions: string[];
  version_drift: boolean;
};

type Matrix = {
  ventures: string[];
  forges: string[];
  cells: {
    venture_id: string;
    forge_id: string;
    declared: boolean;
    criticality: string | null;
    fallback: string | null;
    calls_30d: number;
    health: string | null;
  }[];
};

const TONE: Record<string, string> = {
  ok: "border-ok-line bg-ok-bg text-ok",
  warn: "border-warn-line bg-warn-bg text-warn",
  bad: "border-bad-line bg-bad-bg text-bad",
};

function Metric({ label, value, of }: { label: string; value: number; of?: number }) {
  return (
    <div className="rounded-xl border border-line bg-surface-muted px-4 py-3">
      <div className="text-desc text-ink-muted">{label}</div>
      <div className="text-[24px] font-medium leading-tight text-ink">
        {value}
        {of !== undefined ? <span className="text-desc text-ink-muted"> of {of}</span> : null}
      </div>
    </div>
  );
}

export default async function ForgeMapPage({
  searchParams,
}: {
  searchParams: { venture?: string };
}) {
  let ventures: VentureRow[];
  let estate: { as_of: string; forges: Forge[] };
  let matrix: Matrix;
  try {
    [ventures, estate, matrix] = await Promise.all([
      api.get<VentureRow[]>("/api/ventures"),
      api.get<{ as_of: string; forges: Forge[] }>("/api/forge-map/estate"),
      api.get<Matrix>("/api/forge-map/matrix"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const selected = searchParams.venture ?? ventures[0]?.venture_id ?? null;
  const map = selected
    ? await api.get<Reconciliation>(
        `/api/ventures/${encodeURIComponent(selected)}/forge-map`,
      )
    : null;

  const bridged = estate.forges.filter((forge) => forge.bridged);

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-page font-medium text-ink">Forge Map</h1>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            Declared × Required × In-Use. The diff is the information.
          </p>
        </div>
        <AsOf iso={estate.as_of} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Forges in the portfolio" value={estate.forges.length} />
        <Metric label="Bridged" value={bridged.length} of={estate.forges.length} />
        <Metric label="Declared modules" value={map?.declared_count ?? 0} />
        <Metric
          label="Required by a generator"
          value={map?.required_count ?? 0}
          of={map?.declared_count ?? 0}
        />
      </div>

      {map?.pending_dispositions?.length ? (
        <section className="rounded-xl border border-bad-line bg-bad-bg px-5 py-4">
          <h2 className="flex items-center gap-1.5 text-section font-medium text-bad">
            <AlertTriangle className="h-4 w-4" />
            Gate 15 — {map.pending_dispositions.length} undispositioned finding(s)
          </h2>
          <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
            An undeclared call must not be absorbed by time passing. The monthly sweep
            fails while any of these are pending.
          </p>
          <ul className="mt-2">
            {map.pending_dispositions.map((row) => (
              <li
                key={`${row.forge_id}/${row.module_id}`}
                className="flex flex-wrap items-baseline gap-x-3 border-t border-line py-1.5 first:border-t-0"
              >
                <code className="text-ident text-ink">
                  {row.forge_id}/{row.module_id}
                </code>
                <span className="text-meta text-ink-muted">{row.call_count} calls</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* The three-way diff. */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-section font-medium text-ink">Bill of materials</h2>
          <form method="get">
            <select
              name="venture"
              defaultValue={selected ?? ""}
              className="rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
            >
              {ventures.map((venture) => (
                <option key={venture.venture_id} value={venture.venture_id}>
                  {venture.venture_id}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="ml-2 rounded-lg border border-line px-3 py-1.5 text-desc text-ink transition hover:bg-surface-muted"
            >
              Show
            </button>
          </form>
        </div>

        {/* The cause, not just the mechanism. "Generator 5.6 produces these rows from a
            Pack" says how they would arrive; it does not say why none has. */}
        {map?.blocked_reason ? (
          <div className="mt-3 rounded-lg border border-warn-line bg-warn-bg px-4 py-3">
            <p className="text-desc text-warn">{map.blocked_reason}</p>
            {/* The preserved copy - "Nothing declared for this venture. Generator 5.6
                produces these rows from a Pack." - lives in the genuinely empty state
                below, and only there. Printed here it sat directly above a table listing
                nine declared modules, which is the page contradicting itself: what is
                missing is the generator output, not the declaration. */}
            <p className="mt-1 text-meta text-ink-secondary">
              Generator 5.6 produces these rows from a Pack. The Pack&rsquo;s
              declarations are below; what no run has produced is the Required column
              beside them.{" "}
              <Link
                href={`/provisioning/${encodeURIComponent(selected ?? "")}`}
                className="underline underline-offset-2"
              >
                See the runs
              </Link>
              .
            </p>
          </div>
        ) : null}

        {map && map.rows.length > 0 ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-line text-left">
                  {["Forge", "Module", "Declared", "Required", "In-Use (30d)", "Mismatch"].map(
                    (head) => (
                      <th
                        key={head}
                        className="py-2 pr-3 text-meta font-medium text-ink-muted"
                      >
                        {head}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody>
                {map.rows.map((row) => (
                  <tr
                    key={`${row.forge_id}/${row.module_id}`}
                    className="border-b border-line last:border-0"
                  >
                    <td className="py-2 pr-3 font-mono text-ident text-ink">
                      {row.forge_id}
                    </td>
                    <td className="py-2 pr-3 font-mono text-ident text-ink">
                      {row.module_id}
                    </td>
                    <td className="py-2 pr-3 text-desc text-ink-secondary">
                      {row.declared ? "yes" : "—"}
                    </td>
                    <td className="py-2 pr-3 text-desc text-ink-secondary">
                      {row.required ? "yes" : "—"}
                    </td>
                    <td className="py-2 pr-3 text-desc text-ink-secondary">
                      {row.calls_30d}
                    </td>
                    <td className="py-2">
                      <span
                        className={`rounded-lg border px-2 py-0.5 font-mono text-ident ${
                          TONE[row.tone] ?? TONE.warn
                        }`}
                      >
                        {row.mismatch}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-3 text-desc text-ink-secondary">
            Nothing declared for this venture. Generator 5.6 produces these rows from a
            Pack.
          </p>
        )}

        {/* What each classification does. A label nobody acts on is decoration. */}
        {map ? (
          <ul className="mt-4 space-y-1 border-t border-line pt-3">
            {map.handlers.map((handler) => (
              <li key={handler.mismatch} className="text-meta text-ink-muted">
                <code className={`text-ident ${handler.tone === "bad" ? "text-bad" : "text-warn"}`}>
                  {handler.mismatch}
                </code>{" "}
                {handler.meaning}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {/* The blast-radius view. Read a column to answer "if VoiceForge goes down, which
          ventures halt?" */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Ventures × Forges</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Read a column to see which engagements halt if a Forge goes down, and which
          need re-certifying when one ships a release. <code className="text-ident">hard</code>{" "}
          means the Pack said so.
        </p>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-line text-left">
                <th className="py-2 pr-3 text-meta font-medium text-ink-muted">Venture</th>
                {matrix.forges.map((forge) => (
                  <th
                    key={forge}
                    className="py-2 pr-3 font-mono text-ident font-medium text-ink-muted"
                  >
                    {forge}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.ventures.map((venture) => (
                <tr key={venture} className="border-b border-line last:border-0">
                  <td className="py-2 pr-3 text-desc text-ink">{venture}</td>
                  {matrix.forges.map((forge) => {
                    const cell = matrix.cells.find(
                      (c) => c.venture_id === venture && c.forge_id === forge,
                    );
                    if (!cell?.declared) {
                      return (
                        <td key={forge} className="py-2 pr-3 text-meta text-ink-muted">
                          —
                        </td>
                      );
                    }
                    return (
                      <td key={forge} className="py-2 pr-3">
                        <span
                          className={`rounded-lg border px-2 py-0.5 text-meta ${
                            cell.criticality === "hard" ? TONE.warn : "border-line bg-surface-muted text-ink-secondary"
                          }`}
                        >
                          {cell.criticality ?? "declared"} · {cell.calls_30d} calls
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
              {matrix.ventures.length === 0 ? (
                <tr>
                  <td className="py-2 text-desc text-ink-secondary" colSpan={matrix.forges.length + 1}>
                    No venture has a live Pack, so nothing declares a Forge yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {/* Every Forge, bridged or not. */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">The Forge estate</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          The map only ever showed the Forges one venture declared, so a Forge with no
          bridge looked the same as one that does not exist. {estate.forges.length - bridged.length}{" "}
          of {estate.forges.length} have neither a bridge nor operating instructions.
        </p>

        <ul className="mt-3">
          {estate.forges.map((forge) => (
            <li key={forge.forge_id} className="border-t border-line py-2.5 first:border-t-0">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <span className="text-rowtitle font-medium text-ink">
                  {forge.display_name}
                </span>
                <code className="text-ident text-ink-muted">{forge.forge_id}</code>

                {forge.bridged ? (
                  <span
                    className={`rounded-lg border px-2 py-0.5 text-meta ${
                      forge.health === "GREEN" ? TONE.ok : TONE.bad
                    }`}
                  >
                    {forge.health}
                  </span>
                ) : (
                  <span className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                    no bridge
                  </span>
                )}

                {forge.bridged ? (
                  <span className="text-meta text-ink-muted">
                    {forge.credential_mode} · v{forge.api_version}
                  </span>
                ) : null}

                {forge.version_drift ? (
                  <span className="rounded-lg border border-bad-line bg-bad-bg px-2 py-0.5 text-meta text-bad">
                    live v{forge.api_version} has moved past the pinned{" "}
                    {forge.pinned_versions.join(", ")} — certifications bound to the
                    instructions for the pinned version no longer hold
                  </span>
                ) : null}

                <span className="ml-auto text-meta text-ink-muted">
                  {forge.instruction_modules > 0 ? (
                    <>
                      {forge.instruction_modules} module
                      {forge.instruction_modules === 1 ? "" : "s"} instructed
                    </>
                  ) : (
                    "no operating instructions"
                  )}
                  {forge.last_health_check ? (
                    <>
                      {" · checked "}
                      <LocalTime iso={forge.last_health_check} />
                    </>
                  ) : null}
                </span>
              </div>
              {forge.note ? (
                <p className="mt-1 max-w-3xl text-meta text-ink-secondary">{forge.note}</p>
              ) : null}
            </li>
          ))}
        </ul>

        <p className="mt-3 flex items-center gap-1.5 text-meta text-ink-muted">
          <CircleCheck className="h-3.5 w-3.5" />
          Health and credential mode are read from the registry, not from this page.
        </p>
      </section>
    </div>
  );
}
