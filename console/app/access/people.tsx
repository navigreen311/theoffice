"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useFormState, useFormStatus } from "react-dom";

import { Ago, LocalTime } from "@/components/local-time";
import { Badge, Button, inputClass } from "@/components/ui";
import type { HumanRow } from "@/lib/api";

import {
  reissueTokenAction,
  setStatusAction,
  suspendFixturesAction,
} from "./actions";

/**
 * The roster.
 *
 * It was 179 rows, each carrying an expanded Reason field and two buttons — 179 inline
 * forms on one page, which is why nobody ever used them and why 94 test accounts kept
 * `ivan`. Actions collapse into a menu now and the reason appears when an action is
 * chosen, so the page is a list of people again rather than a wall of controls.
 *
 * **Suspend and Reissue were both destructive-red.** Only one of them is destructive.
 * Reissuing invalidates the old token, which is disruptive and reversible by issuing
 * another; suspending takes somebody's access away. Styling them identically taught the
 * reader that the colour means nothing.
 */

const PAGE_SIZE = 25;

export type Row = HumanRow & {
  origin: string | null;
  last_seen_at: string | null;
  mfa_enrolled_at: string | null;
};

function Submit({ label, busy, variant }: { label: string; busy: string; variant?: "danger" }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant={variant} disabled={pending}>
      {pending ? busy : label}
    </Button>
  );
}

/** Suspending every fixture at once. The only bulk action, and it is reversible. */
export function SuspendFixtures({ count }: { count: number }) {
  const [state, action] = useFormState(suspendFixturesAction, null);
  const [confirming, setConfirming] = useState(false);

  if (state?.ok) return <Badge severity="ok">{state.ok}</Badge>;

  return (
    <form action={action} className="inline-flex flex-wrap items-center gap-3">
      {confirming ? (
        <>
          <Submit label={`Suspend ${count} test accounts`} busy="Suspending…" variant="danger" />
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="text-meta text-ink-muted underline underline-offset-2"
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="rounded-lg border border-bad-line px-3 py-1.5 text-desc font-medium text-bad transition hover:bg-bad-bg"
        >
          Suspend all test accounts
        </button>
      )}
      {state?.error ? <Badge severity="bad">{state.error}</Badge> : null}
    </form>
  );
}

function RowActions({ person }: { person: Row }) {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<"status" | "reissue" | null>(null);
  const [statusState, statusFormAction] = useFormState(setStatusAction, null);
  const [reissueState, reissueFormAction] = useFormState(reissueTokenAction, null);

  if (chosen === "status") {
    const next = person.status === "active" ? "suspended" : "active";
    return (
      <form action={statusFormAction} className="mt-2 space-y-2">
        <input type="hidden" name="human_id" value={person.human_id} />
        <input type="hidden" name="intent" value={next} />
        <label className="block text-meta text-ink-muted">
          Reason
          <span className="block text-meta text-ink-muted">Recorded against your name.</span>
          <input name="reason" required className={inputClass} />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Submit
            label={next === "suspended" ? "Suspend" : "Reactivate"}
            busy="Working…"
            variant={next === "suspended" ? "danger" : undefined}
          />
          <button
            type="button"
            onClick={() => setChosen(null)}
            className="text-meta text-ink-muted underline underline-offset-2"
          >
            Cancel
          </button>
        </div>
        {statusState?.error ? <Badge severity="bad">{statusState.error}</Badge> : null}
        {statusState?.ok ? <Badge severity="ok">{statusState.ok}</Badge> : null}
      </form>
    );
  }

  if (chosen === "reissue") {
    return (
      <form action={reissueFormAction} className="mt-2 space-y-2">
        <input type="hidden" name="human_id" value={person.human_id} />
        <p className="max-w-2xl text-meta text-ink-secondary">
          This invalidates their current token immediately. Their token is shown once,
          here, and is not recoverable.
        </p>
        <label className="block text-meta text-ink-muted">
          Reason
          <span className="block text-meta text-ink-muted">Recorded against your name.</span>
          <input name="reason" required className={inputClass} />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          {/* Secondary, not destructive. Reissuing is disruptive and reversible by
              issuing another; suspending takes access away. */}
          <Submit label="Reissue token" busy="Reissuing…" />
          <button
            type="button"
            onClick={() => setChosen(null)}
            className="text-meta text-ink-muted underline underline-offset-2"
          >
            Cancel
          </button>
        </div>
        {reissueState?.error ? <Badge severity="bad">{reissueState.error}</Badge> : null}
        {reissueState?.token ? (
          <div className="rounded-lg border border-warn-line bg-warn-bg px-3 py-2">
            <p className="text-meta text-warn">{reissueState.ok}</p>
            <code className="text-ident text-ink">{reissueState.token}</code>
          </div>
        ) : null}
      </form>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-label={`Actions for ${person.display_name}`}
        className="rounded-lg border border-line px-2 py-1 text-meta text-ink-secondary transition hover:bg-surface-muted"
      >
        Actions
      </button>
      {open ? (
        <div className="absolute right-0 z-10 mt-1 w-48 rounded-lg border border-line bg-surface py-1 shadow-sm">
          <button
            type="button"
            onClick={() => {
              setChosen("status");
              setOpen(false);
            }}
            className="block w-full px-3 py-1.5 text-left text-desc text-ink transition hover:bg-surface-muted"
          >
            {person.status === "active" ? "Suspend…" : "Reactivate…"}
          </button>
          <button
            type="button"
            onClick={() => {
              setChosen("reissue");
              setOpen(false);
            }}
            className="block w-full px-3 py-1.5 text-left text-desc text-ink transition hover:bg-surface-muted"
          >
            Reissue token…
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function People({
  people,
  hiddenFixtures,
  ventures,
}: {
  people: Row[];
  hiddenFixtures: number;
  ventures: string[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const page = Number(params.get("page") ?? "1");
  const search = (params.get("search") ?? "").toLowerCase();

  function set(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    router.push(`${pathname}?${next.toString()}`);
  }

  const filtered = people.filter((person) => {
    if (search) {
      const haystack = `${person.display_name} ${person.email} ${person.human_id}`.toLowerCase();
      if (!haystack.includes(search)) return false;
    }
    const role = params.get("role");
    if (role && !person.roles.some((r) => r.role === role)) return false;
    const status = params.get("status");
    if (status && person.status !== status) return false;
    const venture = params.get("venture");
    if (venture && !person.roles.some((r) => r.venture_id === venture)) return false;
    return true;
  });

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const shown = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const select =
    "mt-1 block rounded-lg border border-line bg-surface px-2 py-1.5 text-desc text-ink";

  return (
    <section className="rounded-xl border border-line bg-surface px-5 py-4">
      <h2 className="text-section font-medium text-ink">People</h2>
      <p className="mt-0.5 text-desc text-ink-secondary">
        Status is read live: a suspension takes effect on their next request.
      </p>

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-meta text-ink-muted">
          Search
          <input
            className={select}
            defaultValue={params.get("search") ?? ""}
            placeholder="name, email or id"
            onChange={(event) => set("search", event.target.value)}
          />
        </label>
        <label className="text-meta text-ink-muted">
          Origin
          <select
            className={select}
            value={params.get("origin") ?? ""}
            onChange={(event) => set("origin", event.target.value)}
          >
            <option value="">Real accounts</option>
            <option value="test_fixture">Test fixtures</option>
            <option value="all">Everyone</option>
          </select>
        </label>
        <label className="text-meta text-ink-muted">
          Role
          <select
            className={select}
            value={params.get("role") ?? ""}
            onChange={(event) => set("role", event.target.value)}
          >
            <option value="">Any</option>
            {["ivan", "compliance_officer", "venture_operator"].map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <label className="text-meta text-ink-muted">
          Status
          <select
            className={select}
            value={params.get("status") ?? ""}
            onChange={(event) => set("status", event.target.value)}
          >
            <option value="">Any</option>
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
          </select>
        </label>
        <label className="text-meta text-ink-muted">
          Venture
          <select
            className={select}
            value={params.get("venture") ?? ""}
            onChange={(event) => set("venture", event.target.value)}
          >
            <option value="">Any</option>
            {ventures.map((venture) => (
              <option key={venture} value={venture}>
                {venture}
              </option>
            ))}
          </select>
        </label>
        <span className="ml-auto pb-1.5 text-meta text-ink-muted">
          {filtered.length} shown
          {pages > 1 ? ` · page ${page} of ${pages}` : ""}
        </span>
      </div>

      {/* The hidden count, stated. A default filter nobody can see is a page lying by
          omission, which is the same defect as counting the fixtures as colleagues. */}
      {hiddenFixtures > 0 ? (
        <p className="mt-2 text-meta text-ink-muted">
          {hiddenFixtures} test account{hiddenFixtures === 1 ? "" : "s"} hidden by the
          current filter ·{" "}
          <button
            type="button"
            onClick={() => set("origin", "all")}
            className="underline underline-offset-2"
          >
            show them
          </button>
        </p>
      ) : null}

      <ul className="mt-3">
        {shown.map((person) => (
          <li key={person.human_id} className="border-t border-line py-2.5 first:border-t-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="text-rowtitle font-medium text-ink">
                {person.display_name}
              </span>
              <code className="text-ident text-ink-muted">
                {person.human_id.slice(0, 8)}
              </code>
              <span className="text-meta text-ink-muted">{person.email}</span>
              {person.origin === "test_fixture" ? (
                <span className="rounded-lg border border-warn-line bg-warn-bg px-2 py-0.5 text-meta text-warn">
                  test fixture
                </span>
              ) : null}
              <Badge severity={person.status === "active" ? "ok" : "neutral"}>
                {person.status}
              </Badge>
              <div className="ml-auto">
                <RowActions person={person} />
              </div>
            </div>

            <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              {person.roles.map((role) => (
                <code
                  key={`${role.role}:${role.venture_id ?? "*"}`}
                  className="text-ident text-ink-secondary"
                >
                  {role.role}
                  {role.venture_id ? ` · ${role.venture_id}` : " · all ventures"}
                </code>
              ))}
              <span className="text-meta text-ink-muted">
                {person.last_seen_at ? (
                  <>
                    last active <Ago iso={person.last_seen_at} />
                  </>
                ) : (
                  "never signed in"
                )}
              </span>
              <span
                className={`text-meta ${person.mfa_enrolled_at ? "text-ink-muted" : "text-warn"}`}
              >
                {person.mfa_enrolled_at ? (
                  <>
                    MFA enrolled <LocalTime iso={person.mfa_enrolled_at} />
                  </>
                ) : (
                  `MFA not enrolled — ${person.auth_method} is a claim, not evidence`
                )}
              </span>
            </div>
          </li>
        ))}
        {shown.length === 0 ? (
          <li className="py-2 text-desc text-ink-secondary">
            No account matches this filter.
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

      <p className="mt-3 text-meta text-ink-muted">
        Revocation is the kill switch, checked on every call and never cached. Lifting one
        is a decision worth a sentence —{" "}
        <Link href="/revocations" className="underline underline-offset-2">
          active revocations live on the Revocation page
        </Link>
        , where the re-enable ritual is.
      </p>
    </section>
  );
}
