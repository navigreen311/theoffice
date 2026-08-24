import { redirect } from "next/navigation";

import { Badge, Card, Cell, Field, Row, Table, inputClass } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type ForgeMap,
  type VentureRow,
} from "@/lib/api";

export const dynamic = "force-dynamic";

/**
 * Forge Map — Part 15 / Part 17.
 *
 * Three states reconciled: Declared (a manifest row exists), Required (`is_required`),
 * In-Use (calls in the ledger). The diff between them is the screen; the list of
 * declared modules on its own is a bill of materials nobody is checking.
 *
 * Pending Gate 15 dispositions are shown first and loudly, because an undeclared call
 * that nobody dispositions is the finding this whole reconciliation exists to surface -
 * and Part 15 says it blocks rather than being absorbed by time passing.
 */
export default async function ForgeMapPage({
  searchParams,
}: {
  searchParams: { venture?: string };
}) {
  let ventures: VentureRow[];
  try {
    ventures = await api.get<VentureRow[]>("/api/ventures");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const selected = searchParams.venture ?? ventures[0]?.venture_id ?? null;
  const map = selected
    ? await api.get<ForgeMap>(`/api/ventures/${encodeURIComponent(selected)}/forge-map`)
    : null;

  return (
    <div className="space-y-4">
      <Card title="Venture">
        <form method="get" className="max-w-sm">
          <Field label="Forge map for">
            <select name="venture" className={inputClass} defaultValue={selected ?? ""}>
              {ventures.map((v) => (
                <option key={v.venture_id} value={v.venture_id}>
                  {v.venture_id} — {v.agents} agent(s), {v.live_grants} grant(s)
                </option>
              ))}
            </select>
          </Field>
        </form>
      </Card>

      {map === null ? (
        <Card title="No ventures">
          <p className="text-sm text-ink-secondary">
            No venture has a manifest, a grant or a budget yet.
          </p>
        </Card>
      ) : (
        <>
          {map.pending_dispositions.length > 0 ? (
            <Card
              title={`Gate 15 — ${map.pending_dispositions.length} undispositioned finding(s)`}
              subtitle="An undeclared call must not be absorbed by time passing. The monthly sweep fails while any of these are pending."
            >
              <Table head={["Forge", "Module", "Calls", "State"]}>
                {map.pending_dispositions.map((d) => (
                  <Row key={`${d.forge_id}/${d.module_id}`}>
                    <Cell mono>{d.forge_id}</Cell>
                    <Cell mono>{d.module_id}</Cell>
                    <Cell>{d.call_count}</Cell>
                    <Cell>
                      <Badge severity="bad">pending</Badge>
                    </Cell>
                  </Row>
                ))}
              </Table>
              <p className="mt-3 text-xs text-ink-muted">
                Resolving one requires a compliance officer and a written reason.
                `accepted_risk` is a real option — a vocabulary that forces a lie
                produces a register nobody trusts.
              </p>
            </Card>
          ) : null}

          <Card
            title="Bill of materials"
            subtitle="Declared × Required × In-Use. The diff is the information."
          >
            <Table
              head={["Forge", "Module", "Required", "Criticality", "Calls (30d)", "State"]}
              empty="Nothing declared for this venture. Generator 5.6 produces these rows from a Pack."
            >
              {map.declared.map((row) => {
                const unused = row.calls_30d === 0;
                return (
                  <Row key={`${row.forge_id}/${row.module_id}`}>
                    <Cell mono>{row.forge_id}</Cell>
                    <Cell mono>{row.module_id}</Cell>
                    <Cell>{row.is_required ? "yes" : "no"}</Cell>
                    <Cell>
                      <Badge severity={row.criticality === "hard" ? "warn" : "neutral"}>
                        {row.criticality}
                      </Badge>
                    </Cell>
                    <Cell>{row.calls_30d}</Cell>
                    <Cell>
                      {row.module_gap ? (
                        <Badge severity="bad">module gap</Badge>
                      ) : unused && row.is_required ? (
                        <Badge severity="warn">required, never used</Badge>
                      ) : unused ? (
                        <Badge severity="neutral">declared, unused</Badge>
                      ) : (
                        <Badge severity="ok">in use</Badge>
                      )}
                    </Cell>
                  </Row>
                );
              })}
            </Table>
          </Card>
        </>
      )}
    </div>
  );
}
