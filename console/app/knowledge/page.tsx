import { redirect } from "next/navigation";

import { Ago } from "@/components/local-time";
import { Badge, Card, Cell, Row, Table } from "@/components/ui";
import {
  api,
  NotAuthenticated,
  type ComplianceEntry,
  type HistoryRow,
  type KnowledgeCoverage,
  type PersonaRow,
  type PlaybookResponse,
  type StoreCoverage,
  type VentureRow,
} from "@/lib/api";
import { coverageLabel, coverageSeverity, relativeAge } from "@/lib/severity";

import {
  ComplianceEntryForm,
  NoteForm,
  PersonaForm,
  PlaybookForm,
  ShareForm,
} from "./forms";

export const dynamic = "force-dynamic";

/**
 * Knowledge Base Manager — Part 17, screen 14. The last of the fourteen.
 *
 * This screen was refused three times, in three commit messages, with the same
 * sentence: a screen over nothing is worse than an absent screen, because it implies
 * the thing exists. Part 6 names five knowledge bases and one was built. The four
 * stores had to exist first; this is what you get once they do.
 *
 * **Coverage, not browsing.** For each of the five: what exists, out of how many, and
 * what is missing by name. A screen that listed forty entries and no denominator would
 * be a filing cabinet with search — the question an operator has is which store is thin
 * and where, and one of those five gaps stops a venture provisioning while three do not.
 */

const STORES = [
  [
    "forge_operating_instructions",
    "Forge Operating Instructions",
    "6.1 — per Forge, per module. content_hash binds certification, so republishing decertifies.",
  ],
  [
    "compliance_library",
    "Compliance Library",
    "6.3 — six structured fields. A flag with no entry reaches the agent as a label, not a constraint.",
  ],
  [
    "business_playbooks",
    "Business Playbooks",
    "6.2 — venture SOPs. Cross-venture sharing is opt-in only.",
  ],
  [
    "persona_library",
    "Persona Library",
    "6.4 — SimForge only, never production.",
  ],
  [
    "historical_records",
    "Historical Records",
    "6.5 — append-only institutional memory.",
  ],
] as const;

function CoverageCard({ store, title, note }: {
  store: StoreCoverage;
  title: string;
  note: string;
}) {
  const severity = coverageSeverity(store);
  const uncovered = store.uncovered ?? [];

  return (
    <div className="rounded-lg border border-line bg-surface p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        <Badge severity={severity}>{coverageLabel(store)}</Badge>
      </div>
      <p className="mt-1 text-xs text-ink-muted">{note}</p>
      <p className="mt-2 text-xs text-ink-secondary">{store.note}</p>

      <p className="mt-2 text-xs">
        {store.blocking ? (
          <Badge severity="neutral">blocks provisioning at Gate 6</Badge>
        ) : (
          <Badge severity="neutral">advisory at Gate 6</Badge>
        )}
      </p>

      {/* What is missing, by name. A count of gaps tells you there is work; the names
          tell you what the work is. */}
      {uncovered.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-1">
          {uncovered.map((item) => (
            <li key={item}>
              <Badge severity={store.blocking ? "bad" : "warn"}>{item}</Badge>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: { venture?: string };
}) {
  let coverage: KnowledgeCoverage;
  let entries: ComplianceEntry[];
  let personas: PersonaRow[];
  let history: HistoryRow[];
  let ventures: VentureRow[];
  let playbooks: PlaybookResponse;

  const selected = searchParams.venture ?? null;

  try {
    [coverage, entries, personas, history, ventures] = await Promise.all([
      api.get<KnowledgeCoverage>("/api/knowledge/coverage"),
      api.get<ComplianceEntry[]>("/api/knowledge/compliance"),
      api.get<PersonaRow[]>("/api/knowledge/personas"),
      api.get<HistoryRow[]>("/api/knowledge/history?limit=25"),
      api.get<VentureRow[]>("/api/ventures"),
    ]);
    // Playbooks are only readable scoped to a venture — there is no unscoped read, by
    // design, because one forgotten filter is a tenancy breach that reads as a feature.
    playbooks = await api.get<PlaybookResponse>(
      selected
        ? `/api/knowledge/playbooks?venture_id=${encodeURIComponent(selected)}`
        : "/api/knowledge/playbooks",
    );
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const ventureIds = ventures.map((v) => v.venture_id);
  const unexplainedFlags = coverage.compliance_library.uncovered ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold">Knowledge Bases</h2>
        <p className="mt-1 text-xs text-ink-muted">
          Part 6 names five. Two of them block provisioning at Gate 6 and three are
          advisory — a venture can operate without its SOPs written down, and cannot
          operate under a compliance flag nobody has defined.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {STORES.map(([key, title, note]) => (
          <CoverageCard key={key} store={coverage[key]} title={title} note={note} />
        ))}
      </div>

      <Card
        title="Compliance Library"
        subtitle="Part 6.3. Six fields, all required. This is what a Pack's library_entry_ref resolves against — V28 fails a Pack naming a ref that points at nothing."
      >
        <Table
          head={["Ref", "Framework", "Jurisdiction", "Runtime flag", "Agent must", "Escalate when"]}
          empty="No entries. Every Pack naming a library ref fails V28, and every compliance flag in use blocks Gate 6."
        >
          {entries.map((e) => (
            <Row key={e.entry_ref}>
              <Cell mono>{e.entry_ref}</Cell>
              <Cell>{e.framework}</Cell>
              <Cell>{e.jurisdiction.join(", ")}</Cell>
              <Cell mono>{e.runtime_flag ?? "—"}</Cell>
              <Cell>{e.agent_behavior_implication}</Cell>
              <Cell>{e.escalation_trigger}</Cell>
            </Row>
          ))}
        </Table>
        <div className="mt-4 border-t border-line pt-4">
          <ComplianceEntryForm knownFlags={unexplainedFlags} />
        </div>
      </Card>

      <Card
        title="Business Playbooks"
        subtitle={
          selected
            ? `Everything ${selected} may see: its own, plus what has been shared to it.`
            : "Pick a venture to read playbooks. There is no unscoped read — one forgotten filter is a tenancy breach that reads as a feature."
        }
      >
        <div className="mb-4 flex flex-wrap gap-2 text-sm">
          {ventureIds.map((v) => (
            <a
              key={v}
              href={`/knowledge?venture=${encodeURIComponent(v)}`}
              className={`rounded border px-2 py-1 text-xs ${
                v === selected
                  ? "border-ink bg-surface-inverse text-ink-inverse"
                  : "border-line-strong text-ink-secondary"
              }`}
            >
              {v}
            </a>
          ))}
        </div>

        <Table
          head={["Title", "Stage", "Version", "Owner", "Hash"]}
          empty={
            selected
              ? `${selected} has no playbooks of its own and none shared to it.`
              : "No venture selected."
          }
        >
          {playbooks.playbooks.map((p) => (
            <Row key={p.playbook_id}>
              <Cell>{p.title}</Cell>
              <Cell>{p.lifecycle_stage ?? "—"}</Cell>
              <Cell mono>{p.playbook_version}</Cell>
              <Cell>
                {p.shared_from ? (
                  <Badge severity="warn">shared from {p.shared_from}</Badge>
                ) : (
                  "own"
                )}
              </Cell>
              <Cell mono>{p.content_hash.slice(0, 12)}…</Cell>
            </Row>
          ))}
        </Table>

        <h3 className="mt-6 text-xs font-medium text-ink-secondary">
          Cross-venture shares ({playbooks.shares.length})
        </h3>
        <Table
          head={["Playbook", "From", "To", "Reason", "State"]}
          empty="Nothing is shared across ventures."
        >
          {playbooks.shares.map((s) => (
            <Row key={`${s.playbook_id}-${s.to_venture_id}`}>
              <Cell>{s.title}</Cell>
              <Cell>{s.from_venture}</Cell>
              <Cell>{s.to_venture_id}</Cell>
              <Cell>{s.reason}</Cell>
              <Cell>
                {s.revoked_at ? (
                  <Badge>withdrawn <Ago iso={s.revoked_at} /></Badge>
                ) : (
                  <Badge severity="ok">active</Badge>
                )}
              </Cell>
            </Row>
          ))}
        </Table>

        <div className="mt-4 grid gap-6 border-t border-line pt-4 lg:grid-cols-2">
          <PlaybookForm ventures={ventureIds} />
          <ShareForm playbooks={playbooks.playbooks} ventures={ventureIds} />
        </div>
      </Card>

      <Card
        title="Persona Library"
        subtitle="Part 6.4 — SimForge only, never production. Names and hashes only: the runtime role this console uses holds no read privilege on a persona body."
      >
        <Table
          head={["Venture", "Persona", "Stands in for", "Version", "Body hash"]}
          empty="No personas authored."
        >
          {personas.map((p) => (
            <Row key={p.persona_id}>
              <Cell>{p.venture_id}</Cell>
              <Cell>{p.persona_name}</Cell>
              <Cell>{p.target_persona}</Cell>
              <Cell mono>{p.persona_version}</Cell>
              <Cell mono>{p.body_hash.slice(0, 12)}…</Cell>
            </Row>
          ))}
        </Table>
        <div className="mt-4 border-t border-line pt-4">
          <PersonaForm ventures={ventureIds} />
        </div>
      </Card>

      <Card
        title="Historical Records"
        subtitle="Part 6.5 — append-only. Provisioning writes here on completion and on abandonment; humans add notes."
      >
        <Table
          head={["When", "Venture", "Type", "Summary", "By"]}
          empty="No institutional history recorded yet."
        >
          {history.map((r) => (
            <Row key={r.record_id}>
              <Cell><Ago iso={r.occurred_at} /></Cell>
              <Cell>{r.venture_id ?? "portfolio"}</Cell>
              <Cell mono>{r.record_type}</Cell>
              <Cell>{r.summary}</Cell>
              <Cell>{r.actor_type}</Cell>
            </Row>
          ))}
        </Table>
        <div className="mt-4 border-t border-line pt-4">
          <NoteForm ventures={ventureIds} />
        </div>
      </Card>
    </div>
  );
}
