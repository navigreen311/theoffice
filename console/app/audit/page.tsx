import { redirect } from "next/navigation";

import { Badge, Card, Cell, Field, Row, Table, inputClass } from "@/components/ui";
import { Pager } from "@/components/pager";
import {
  api,
  NotAuthenticated,
  type AuditEntry,
  type ChainStatus,
  type Paged,
} from "@/lib/api";
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
  searchParams: {
    event_type?: string;
    venture_id?: string;
    trace_id?: string;
    limit?: string;
    offset?: string;
  };
}) {
  const limit = searchParams.limit ?? "100";
  const offset = searchParams.offset ?? "0";
  const query = new URLSearchParams({ limit, offset });
  for (const key of ["event_type", "venture_id", "trace_id"] as const) {
    const value = searchParams[key];
    if (value) query.set(key, value);
  }

  let page: Paged<AuditEntry>;
  let chain: ChainStatus;
  try {
    [page, chain] = await Promise.all([
      api.get<Paged<AuditEntry>>(`/api/audit?${query}`),
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
          <span className="text-ink-secondary">
            {chain.checked_count.toLocaleString()} entries
          </span>
          <span className="text-xs text-ink-muted">
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
          empty="No entries match these filters. The count below is the denominator — an empty result over 40,000 entries is a finding; over zero it is an empty database."
        >
          {page.items.map((entry) => (
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

        {/* The denominator. Without it, "no entries match" and "no entries match in the
            most recent hundred" render identically — and only one of them is a finding. */}
        <Pager
          page={page}
          basePath="/audit"
          params={{
            event_type: searchParams.event_type,
            venture_id: searchParams.venture_id,
            trace_id: searchParams.trace_id,
          }}
        />
      </Card>
    </div>
  );
}
