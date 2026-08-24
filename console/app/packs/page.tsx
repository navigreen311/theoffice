import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type PackSummary,
  type VentureRow,
} from "@/lib/api";
import { relativeAge } from "@/lib/severity";

export const dynamic = "force-dynamic";

/**
 * Pack Editor index — Part 17 screen 12.
 *
 * Two lists rather than one, because "ventures with a Pack" and "ventures without one"
 * are different problems. A venture that appears in the directory with no Pack cannot
 * be provisioned at all: Gate 1 refuses, and nothing downstream of it has an input.
 * Showing only the Packs that exist would hide exactly the ventures that need one.
 */
export default async function PacksPage() {
  let packs: PackSummary[];
  let ventures: VentureRow[];
  try {
    [packs, ventures] = await Promise.all([
      api.get<PackSummary[]>("/api/packs"),
      api.get<VentureRow[]>("/api/ventures"),
    ]);
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const withPack = new Set(packs.map((p) => p.venture_id));
  const withoutPack = ventures.filter((v) => !withPack.has(v.venture_id));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Business Packs</h2>
        <p className="mt-1 text-xs text-ink-muted">
          The Pack is the document every artifact derives from — positions,
          appointments, workflow, task ledger, curriculum, grants. Publishing supersedes
          the live version; the next provisioning run provisions the new one.
        </p>
      </div>

      <Card title="Live Packs" subtitle="One per venture. The hash is computed by the database.">
        <Table
          head={["Venture", "Version", "Content hash", "Authored", ""]}
          empty="No venture has a Pack. Gate 1 refuses a run without one."
        >
          {packs.map((p) => (
            <Row key={p.venture_id}>
              <Cell>{p.venture_id}</Cell>
              <Cell mono>{p.pack_version}</Cell>
              <Cell mono>{p.content_hash.slice(0, 16)}…</Cell>
              <Cell>{relativeAge(p.authored_at)}</Cell>
              <Cell>
                <Link
                  href={`/packs/${encodeURIComponent(p.venture_id)}`}
                  className="text-sm underline underline-offset-2"
                >
                  Edit →
                </Link>
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>

      <Card
        title="Ventures with no Pack"
        subtitle="An engagement exists here — grants, manifest rows or a budget — but there is no document to provision from."
      >
        <Table head={["Venture", "Agents", "Live grants", ""]} empty="Every venture has a Pack.">
          {withoutPack.map((v) => (
            <Row key={v.venture_id}>
              <Cell>{v.venture_id}</Cell>
              <Cell>{v.agents}</Cell>
              <Cell>{v.live_grants}</Cell>
              <Cell>
                <Badge severity="warn">Gate 1 blocks</Badge>
              </Cell>
            </Row>
          ))}
        </Table>
      </Card>
    </div>
  );
}
