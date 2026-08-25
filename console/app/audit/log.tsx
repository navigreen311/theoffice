"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { AlertTriangle } from "@/components/icons";
import { LocalTime } from "@/components/local-time";

/**
 * The log.
 *
 * Three things it did not do. Every entry named `human` and no person, which defeats the
 * only property this log exists to provide — 95 accounts could have written any of those
 * rows. Timestamps were "23m ago", which is unusable in an export, a regulator
 * conversation, or a post-mortem across time zones. And nothing could be expanded, so a
 * hash column truncated to twelve characters was decoration rather than a chain anybody
 * could check.
 *
 * Fixtures are filtered by default and counted. They are never deleted: the store is
 * append-only, and a filter changes the view rather than the record.
 */

export type Entry = {
  audit_id: number;
  event_type: string;
  label: string;
  actor_type: string;
  actor_id: string | null;
  actor_name: string | null;
  venture_id: string | null;
  trace_id: string | null;
  ts: string;
  prev_hash: string;
  entry_hash: string;
  fixture: boolean;
};

export type Detail = Entry & {
  meaning: string;
  subject: Record<string, unknown>;
  previous_audit_id: number | null;
  previous_entry_hash: string | null;
  links_to_previous: boolean | null;
  link_note: string;
  trace_siblings: { audit_id: number; event_type: string; ts: string }[];
};

export function FixtureBanner({
  excluded,
  total,
  onShow,
}: {
  excluded: number;
  total: number;
  onShow: () => void;
}) {
  if (excluded === 0) return null;
  return (
    <section className="rounded-xl border border-warn-line bg-warn-bg px-5 py-4">
      <h2 className="flex items-center gap-1.5 text-section font-medium text-warn">
        <AlertTriangle className="h-4 w-4" />
        {excluded} of {excluded + total} entries are smoke-test loops
      </h2>
      <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
        Written by accounts this project&rsquo;s own test paths created — every smoke run
        writes a persona, a person, a Pack draft, a proposal, an incident and a
        provisioning run that aborts at gate 4. They are hidden by default and{" "}
        <button type="button" onClick={onShow} className="underline underline-offset-2">
          can be shown
        </button>
        . They are never deleted: this store is append-only, so filtering changes the view
        and not the record, and any export says which it did.
      </p>
    </section>
  );
}

function ActorCell({ entry }: { entry: Entry }) {
  // The name, with the id beneath it. The type stays as its own signal because
  // distinguishing a person from an agent from the platform matters - it just must not
  // be the only thing shown, which is what "actor: human" was.
  if (entry.actor_name) {
    return (
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-desc text-ink-secondary">{entry.actor_name}</span>
        <code className="text-ident text-ink-muted">
          {(entry.actor_id ?? "").slice(0, 8)}
        </code>
      </span>
    );
  }
  return (
    <span className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-desc text-ink-muted">
        {entry.actor_id ? "account not in the roster" : "no actor recorded"}
      </span>
      {entry.actor_id ? (
        <code className="text-ident text-ink-muted">{entry.actor_id.slice(0, 8)}</code>
      ) : null}
    </span>
  );
}

function ExpandedRow({ detail }: { detail: Detail }) {
  return (
    <div className="mt-2 rounded-lg border border-line bg-surface-muted px-4 py-3">
      <p className="text-desc text-ink-secondary">{detail.meaning}</p>

      <dl className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        <div>
          <dt className="text-meta text-ink-muted">Previous entry hash</dt>
          <dd className="break-all font-mono text-ident text-ink">
            {detail.previous_entry_hash ?? "—"}
          </dd>
        </div>
        <div>
          <dt className="text-meta text-ink-muted">This entry&rsquo;s prev_hash</dt>
          <dd className="break-all font-mono text-ident text-ink">{detail.prev_hash}</dd>
        </div>
        <div>
          <dt className="text-meta text-ink-muted">This entry&rsquo;s hash</dt>
          <dd className="break-all font-mono text-ident text-ink">{detail.entry_hash}</dd>
        </div>
        <div>
          <dt className="text-meta text-ink-muted">Trace</dt>
          <dd className="break-all font-mono text-ident text-ink">
            {detail.trace_id ?? "—"}
          </dd>
        </div>
      </dl>

      {/* The line that makes the chain legible rather than decorative: a reader can
          compare the two hashes above by eye, and this says what the comparison found. */}
      <p
        className={`mt-3 text-desc ${
          detail.links_to_previous === false ? "text-bad" : "text-ink-secondary"
        }`}
      >
        {detail.link_note}
      </p>

      <div className="mt-3">
        <span className="text-meta text-ink-muted">Subject</span>
        <pre className="mt-1 overflow-x-auto rounded-lg border border-line bg-surface px-3 py-2 font-mono text-ident text-ink">
          {JSON.stringify(detail.subject, null, 2)}
        </pre>
      </div>

      {detail.trace_siblings.length > 1 ? (
        <div className="mt-3">
          <span className="text-meta text-ink-muted">
            {detail.trace_siblings.length} entries share this trace
          </span>
          <ul className="mt-1">
            {detail.trace_siblings.map((sibling) => (
              <li
                key={sibling.audit_id}
                className="flex flex-wrap items-baseline gap-x-3 text-meta text-ink-muted"
              >
                <code className="text-ident">{sibling.audit_id}</code>
                <span>{sibling.event_type}</span>
                <LocalTime iso={sibling.ts} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function AuditLog({
  rows,
  total,
  page,
  pages,
  excludedFixtures,
  eventTypes,
  actors,
  ventures,
  truncated,
  detail,
}: {
  rows: Entry[];
  total: number;
  page: number;
  pages: number;
  excludedFixtures: number;
  eventTypes: { event_type: string; label: string }[];
  actors: { id: string; name: string }[];
  ventures: string[];
  truncated: boolean;
  detail: Detail | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  function set(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    router.push(`${pathname}?${next.toString()}`);
  }

  // Expansion goes through the URL and the detail is fetched server-side, like every
  // other read in this console. The browser never talks to the API directly - there is
  // no proxy and no rewrite, deliberately, so there is no cross-origin request and no
  // CORS configuration to get wrong. It also makes an expanded entry a link somebody can
  // send to a colleague.
  const open = params.get("expand") ? Number(params.get("expand")) : null;

  const select =
    "mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";

  return (
    <>
      <FixtureBanner
        excluded={excludedFixtures}
        total={total}
        onShow={() => set("include_fixtures", "true")}
      />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="text-section font-medium text-ink">Entries</h2>
          <span className="text-meta text-ink-muted">
            Append-only and hash-chained. Nothing here is editable.
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-meta text-ink-muted">
            Event type
            <select
              className={select}
              value={params.get("event_type") ?? ""}
              onChange={(event) => set("event_type", event.target.value)}
            >
              <option value="">Any</option>
              {eventTypes.map((event) => (
                <option key={event.event_type} value={event.event_type}>
                  {event.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-meta text-ink-muted">
            Actor
            <select
              className={select}
              value={params.get("actor_id") ?? ""}
              onChange={(event) => set("actor_id", event.target.value)}
            >
              <option value="">Anyone</option>
              {actors.map((actor) => (
                <option key={actor.id} value={actor.id}>
                  {actor.name}
                </option>
              ))}
            </select>
          </label>

          <label className="text-meta text-ink-muted">
            Venture
            <select
              className={select}
              value={params.get("venture_id") ?? ""}
              onChange={(event) => set("venture_id", event.target.value)}
            >
              <option value="">Any</option>
              {ventures.map((venture) => (
                <option key={venture} value={venture}>
                  {venture}
                </option>
              ))}
            </select>
          </label>

          <label className="text-meta text-ink-muted">
            From
            <input
              type="date"
              className={select}
              value={params.get("since") ?? ""}
              onChange={(event) => set("since", event.target.value)}
            />
          </label>
          <label className="text-meta text-ink-muted">
            To
            <input
              type="date"
              className={select}
              value={params.get("until") ?? ""}
              onChange={(event) => set("until", event.target.value)}
            />
          </label>

          <label className="text-meta text-ink-muted">
            Fixtures
            <select
              className={select}
              value={params.get("include_fixtures") ?? ""}
              onChange={(event) => set("include_fixtures", event.target.value)}
            >
              <option value="">Excluded</option>
              <option value="true">Included</option>
            </select>
          </label>

          <span className="ml-auto pb-1.5 text-meta text-ink-muted">
            {total} matching
            {pages > 1 ? ` · page ${page} of ${pages}` : ""}
          </span>
        </div>

        <ul className="mt-3">
          {rows.map((entry) => (
            <li key={entry.audit_id} className="border-t border-line py-2 first:border-t-0">
              <button
                type="button"
                onClick={() =>
                  set("expand", open === entry.audit_id ? "" : String(entry.audit_id))
                }
                className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 text-left"
              >
                <code className="text-ident text-ink-muted">{entry.audit_id}</code>
                <span className="text-desc text-ink">{entry.label}</span>
                <code className="text-ident text-ink-muted">{entry.event_type}</code>
                <ActorCell entry={entry} />
                <span className="text-meta text-ink-muted">
                  {entry.venture_id ?? "—"}
                </span>
                {entry.fixture ? (
                  <span className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                    fixture
                  </span>
                ) : null}
                {/* Absolute, with the zone. "23m ago" cannot go in an export or into a
                    conversation with a regulator. `LocalTime` renders the absolute value
                    and puts the relative one on hover. */}
                <span className="ml-auto font-mono text-meta text-ink-muted">
                  <LocalTime iso={entry.ts} />
                </span>
              </button>

              {open === entry.audit_id && detail ? (
                <ExpandedRow detail={detail} />
              ) : null}
            </li>
          ))}
          {rows.length === 0 ? (
            <li className="py-2 text-desc text-ink-secondary">
              No entry matches this filter.
              {excludedFixtures > 0
                ? ` ${excludedFixtures} fixture entries are excluded.`
                : ""}
            </li>
          ) : null}
        </ul>

        {pages > 1 ? (
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => set("page", String(page - 1))}
              className="rounded-lg border border-line px-2 py-1 text-meta text-ink transition hover:bg-surface-muted disabled:opacity-40"
            >
              Previous
            </button>
            <span className="text-meta text-ink-muted">
              page {page} of {pages}
            </span>
            <button
              type="button"
              disabled={page >= pages}
              onClick={() => set("page", String(page + 1))}
              className="rounded-lg border border-line px-2 py-1 text-meta text-ink transition hover:bg-surface-muted disabled:opacity-40"
            >
              Next
            </button>
          </div>
        ) : null}

        {truncated ? (
          <p className="mt-3 text-meta text-ink-muted">
            This is not the whole result. Narrow the filters or page through.
          </p>
        ) : null}
      </section>
    </>
  );
}
