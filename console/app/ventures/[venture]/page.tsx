import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type Capacity,
  type ForgeMap,
  type Gates,
  type VentureRow,
} from "@/lib/api";
import { capacityTriple } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Venture Dashboard, including the Shift & Capacity view and the Readiness Gate view.
 *
 * Composed rather than split across three screens because the three questions an
 * operator asks about a venture — can it staff, what is blocking it, what is it using —
 * are answered by each other. Splitting them makes you hold the answer to one while
 * navigating to the next.
 */
export default async function VenturePage({
  params,
}: {
  params: { venture: string };
}) {
  const venture = decodeURIComponent(params.venture);

  let capacity: Capacity;
  let gates: Gates;
  let map: ForgeMap;
  try {
    // Ventures are engagements, not a table - a venture "exists" when it appears in the
    // directory. Without this check every string renders a dashboard full of zeroes,
    // and zeroes for a mistyped venture look exactly like zeroes for a real one that
    // has not started. That is the UI misrepresenting state, which is the failure this
    // console is most able to commit.
    const known = await api.get<VentureRow[]>("/api/ventures");
    if (!known.some((v) => v.venture_id === venture)) notFound();

    [capacity, gates, map] = await Promise.all([
      api.get<Capacity>(`/api/ventures/${encodeURIComponent(venture)}/capacity`),
      api.get<Gates>(`/api/ventures/${encodeURIComponent(venture)}/gates`),
      api.get<ForgeMap>(`/api/ventures/${encodeURIComponent(venture)}/forge-map`),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const blocking =
    gates.gate_15_pending_dispositions > 0 || gates.unassignable_grants > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">{venture}</h2>
        <Link
          href={`/forge-map?venture=${encodeURIComponent(venture)}`}
          className="text-sm text-ink-secondary underline underline-offset-2"
        >
          Forge map →
        </Link>
      </div>

      <Card title="Capacity" subtitle={capacity.note}>
        <div className="grid gap-3 sm:grid-cols-3">
          {/* All three, always. capacityTriple throws rather than rendering a partial
              set, because one number hides the state. */}
          {capacityTriple(capacity).map((n) => (
            <div key={n.label} className="rounded border border-line p-3">
              <div className="text-2xl font-semibold">{n.value}</div>
              <div className="mt-1 text-xs text-ink-secondary">{n.label}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card
        title="Readiness gates"
        subtitle="What stands between this venture and production."
      >
        <Table head={["Check", "State", "Detail"]}>
          <Row>
            <Cell>Gate 15 — manifest reconciliation</Cell>
            <Cell>
              <Badge
                severity={gates.gate_15_pending_dispositions > 0 ? "bad" : "ok"}
              >
                {gates.gate_15_pending_dispositions > 0 ? "blocked" : "clear"}
              </Badge>
            </Cell>
            <Cell>
              {gates.gate_15_pending_dispositions} undispositioned UNDECLARED finding(s)
            </Cell>
          </Row>
          <Row>
            <Cell>Assignability</Cell>
            <Cell>
              <Badge severity={gates.unassignable_grants > 0 ? "warn" : "ok"}>
                {gates.unassignable_grants > 0 ? "incomplete" : "clear"}
              </Badge>
            </Cell>
            <Cell>
              {gates.unassignable_grants} live grant(s) missing a certification unit
            </Cell>
          </Row>
          <Row>
            <Cell>Gate 10 — sign-offs</Cell>
            <Cell>
              <Badge severity={gates.signoffs.length > 0 ? "ok" : "neutral"}>
                {gates.signoffs.length > 0 ? "signed" : "unsigned"}
              </Badge>
            </Cell>
            <Cell>
              {gates.signoffs.length === 0
                ? "no gate signed"
                : gates.signoffs
                    .map((s) => `${s.gate}: ${s.signatures}`)
                    .join(", ")}
            </Cell>
          </Row>
        </Table>
        {blocking ? (
          <p className="mt-3 rounded border border-bad/40 bg-bad/10 px-3 py-2 text-xs text-bad">
            This venture cannot pass its gates in the current state.
          </p>
        ) : null}
      </Card>

      <Card title="Forge usage (30d)">
        <Table
          head={["Forge", "Module", "Required", "Calls"]}
          empty="No manifest rows. Generator 5.6 produces these from a Pack."
        >
          {map.declared.map((row) => (
            <Row key={`${row.forge_id}/${row.module_id}`}>
              <Cell mono>{row.forge_id}</Cell>
              <Cell mono>{row.module_id}</Cell>
              <Cell>{row.is_required ? "yes" : "no"}</Cell>
              <Cell>{row.calls_30d}</Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
