import Link from "next/link";
import { redirect } from "next/navigation";

import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import { api, NotAuthenticated, type VentureRow } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Venture Directory — Part 17. Ventures are engagements on the Village, not Villages. */
export default async function VenturesPage() {
  let ventures: VentureRow[];
  try {
    ventures = await api.get<VentureRow[]>("/api/ventures");
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  return (
    <Card
      title="Venture directory"
      subtitle="The Village carries several ventures at once. One venture per agent per shift."
    >
      <Table
        head={["Venture", "Agents", "Live grants", "Monthly cap", "Hard cap"]}
        empty="No venture has a manifest, a grant or a budget yet."
      >
        {ventures.map((v) => (
          <Row key={v.venture_id}>
            <Cell>
              <Link
                href={`/ventures/${encodeURIComponent(v.venture_id)}`}
                className="font-medium text-ink underline underline-offset-2"
              >
                {v.venture_id}
              </Link>
            </Cell>
            <Cell>{v.agents}</Cell>
            <Cell>{v.live_grants}</Cell>
            <Cell>{v.monthly_usd_cap ? `$${v.monthly_usd_cap}` : "unmetered"}</Cell>
            <Cell>
              {v.hard_cap_reversed_at ? (
                <Badge severity="warn">reversed</Badge>
              ) : (
                <Badge severity="neutral">—</Badge>
              )}
            </Cell>
          </Row>
        ))}
      </Table>
      <p className="mt-3 text-xs text-ink-muted">
        &quot;Unmetered&quot; means no budget row exists, not a zero cap. Validator rule
        V18 makes budget caps a required Pack field, so an unmetered venture cannot reach
        production.
      </p>
    </Card>
  );
}
