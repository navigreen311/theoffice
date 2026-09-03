import { redirect } from "next/navigation";

import { Breadcrumb } from "@/components/breadcrumb";
import { Ago } from "@/components/local-time";
import { api, NotAuthenticated } from "@/lib/api";

import { PlaybookForm, ShareForm } from "../forms";
import { KnowledgeTabs } from "../tabs";

export const dynamic = "force-dynamic";

/**
 * Business playbooks.
 *
 * Publishing and cross-venture sharing were two forms stacked in one card, with Share
 * and Withdraw adjacent at equal weight. Withdrawing a share is destructive-adjacent —
 * it takes access away from a venture that has been relying on it — and it should not
 * sit beside the control that grants it as though the two were symmetrical.
 *
 * The venture chip is the tenancy boundary. There is no unscoped read here, and the page
 * says so rather than rendering an empty table under an unclicked control.
 */

type Playbook = {
  playbook_id: string;
  venture_id: string;
  title: string;
  lifecycle_stage: string | null;
  playbook_version: string;
  authored_at: string;
};

export default async function PlaybooksPage({
  searchParams,
}: {
  searchParams: { venture_id?: string };
}) {
  const venture = searchParams.venture_id ?? "";

  let ventures: { venture_id: string }[];
  let playbooks: Playbook[] = [];
  try {
    ventures = await api.get<{ venture_id: string }[]>("/api/ventures");
    if (venture) {
      playbooks = await api.get<Playbook[]>(
        `/api/knowledge/playbooks?venture_id=${encodeURIComponent(venture)}`,
      );
    }
  } catch (error) {
    if (error instanceof NotAuthenticated) redirect("/login");
    throw error;
  }

  const names = ventures.map((row) => row.venture_id);

  return (
    <div className="space-y-6">
      <Breadcrumb
        trail={[
          { label: "Dashboard", href: "/" },
          { label: "Knowledge", href: "/knowledge" },
          { label: "Playbooks" },
        ]}
      />

      <div>
        <h1 className="text-page font-medium text-ink">Business Playbooks</h1>
        <p className="mt-1 max-w-3xl text-desc text-ink-secondary">
          Pick a venture to read playbooks. There is no unscoped read — one forgotten
          filter is a tenancy breach that reads as a feature.
        </p>
      </div>

      <KnowledgeTabs />

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* A real control rather than a chip that does not look interactive. */}
          <label className="text-meta text-ink-muted">
            Venture
            <form>
              <select
                name="venture_id"
                defaultValue={venture}
                className="mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink"
              >
                <option value="">Choose a venture</option>
                {names.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                className="mt-2 rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
              >
                Read playbooks
              </button>
            </form>
          </label>
        </div>

        <div className="mt-4 border-t border-line pt-3">
          {!venture ? (
            <p className="text-desc text-ink-secondary">
              No venture selected. Nothing is read until you choose one — this store has
              no unscoped view.
            </p>
          ) : playbooks.length === 0 ? (
            <p className="text-desc text-ink-secondary">
              {venture} has no playbook. Its positions and lifecycle stages are defined in
              the Pack; none of them has a written SOP.
            </p>
          ) : (
            <ul>
              {playbooks.map((playbook) => (
                <li
                  key={playbook.playbook_id}
                  className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-line py-2 first:border-t-0"
                >
                  <span className="text-rowtitle font-medium text-ink">
                    {playbook.title}
                  </span>
                  {playbook.lifecycle_stage ? (
                    <span className="text-meta text-ink-muted">
                      {playbook.lifecycle_stage}
                    </span>
                  ) : null}
                  <span className="ml-auto text-meta text-ink-muted">
                    v{playbook.playbook_version} · <Ago iso={playbook.authored_at} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Write a playbook</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Scoped to one venture. A playbook is an SOP for a lifecycle stage, not a note.
        </p>
        <div className="mt-3">
          <PlaybookForm ventures={names} />
        </div>
      </section>

      {/*
        Its own card. Sharing crosses a tenancy boundary and withdrawing takes access
        away from somebody relying on it - neither belongs beside the publish form as an
        equal-weight button.
      */}
      <section className="rounded-xl border border-line bg-surface px-5 py-4">
        <h2 className="text-section font-medium text-ink">Cross-venture sharing</h2>
        <p className="mt-0.5 max-w-3xl text-desc text-ink-secondary">
          Cross-venture sharing is opt-in only; absence is a refusal.
        </p>
        {!venture ? (
          <p className="mt-2 text-meta text-ink-muted">
            Choose a venture above to see what it has to share.
          </p>
        ) : null}
        <div className="mt-3">
          <ShareForm playbooks={playbooks} ventures={names} />
        </div>
      </section>
    </div>
  );
}
