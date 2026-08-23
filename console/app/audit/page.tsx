import { redirect } from "next/navigation";

import { Badge, Card, Cell, Field, Row, Table, inputClass } from "@/components/ui";
import { api, NotAuthenticated, type AuditEntry, type ChainStatus } from "@/lib/api";
import { relativeAge } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Audit Log Explorer — Part 17.
 *
 * Read-only, and there is no route that writes here: the append-only ledger is enforced
 * by role grants, and the API has no audit write endpoint at all (pinned by a test).
 *
 * The chain status is shown above the entries rather than on its own page, because a
 * list of audit entries means nothing without knowing whether the chain they sit in
 * still verifies.
 */
export default async function AuditPage({
  searchParams,
}: {
  searchParams: { event_type?: string; venture_id?: string; trace_id?: string };
}) {
  const query = new URLSearchParams({ limit: "100" });
  for (const key of ["event_type", "venture_id", "trace_id"] as const) {
    const value = searchParams[key];
    if (value) query.set(key, value);
  }

  let entries: AuditEntry[];
  let chain: ChainStatus;
  try {
    [entries, chain] = await Promise.all([
      api.get<AuditEntry[]>(`/api/audit?${query}`),
      api.get<ChainStatus>("/api/audit/chain"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <div className="space-y-4">
      <Card title="Chain integrity">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Badge severity={chain.ok ? "ok" : "critical"}>
            {chain.ok ? "verified" : "BROKEN"}
          </Badge>
          <span className="text-neutral-600">
            {chain.checked_count.toLocaleString()} entries
          </span>
          <span className="text-xs text-neutral-500">
            Entries below are meaningless if this is broken — read it first.
          </span>
        </div>
      </Card>

      <Card title="Audit log" subtitle="Append-only and hash-chained. Nothing here is editable.">
        <form method="get" className="mb-4 grid gap-3 sm:grid-cols-3">
          <Field label="Event type">
            <input
              className={inputClass}
              name="event_type"
              defaultValue={searchParams.event_type ?? ""}
              placeholder="forge_call_intent"
            />
          </Field>
          <Field label="Venture">
            <input
              className={inputClass}
              name="venture_id"
              defaultValue={searchParams.venture_id ?? ""}
            />
          </Field>
          <Field label="Trace">
            <input
              className={inputClass}
              name="trace_id"
              defaultValue={searchParams.trace_id ?? ""}
              placeholder="uuid"
            />
          </Field>
        </form>

        <Table
          head={["#", "Event", "Actor", "Venture", "When", "Entry hash"]}
          empty="No entries match. An empty audit log and an unfiltered one look the same — check the filters."
        >
          {entries.map((entry) => (
            <Row key={entry.audit_id}>
              <Cell mono>{entry.audit_id}</Cell>
              <Cell mono>{entry.event_type}</Cell>
              <Cell>
                <Badge severity={entry.actor_type === "human" ? "warn" : "neutral"}>
                  {entry.actor_type}
                </Badge>
              </Cell>
              <Cell>{entry.venture_id ?? "—"}</Cell>
              <Cell>{relativeAge(entry.ts)}</Cell>
              <Cell mono>{entry.entry_hash.slice(0, 12)}…</Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
