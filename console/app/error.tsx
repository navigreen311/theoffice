"use client";

import { useEffect, useState } from "react";

/**
 * What the console shows when a page throws in the browser.
 *
 * Without this, Next renders "Application error: a client-side exception has occurred
 * (see the browser console for more information)" — a dead end that names nothing, offers
 * nothing, and was reported by hand three times during this project. Twice it was a stale
 * build: the tab was open, the app was rebuilt, and the chunk the running page asked for
 * no longer existed. The page was one refresh away from working and said so to nobody.
 *
 * So a chunk-loading failure reloads once, automatically. That is the correct response —
 * the browser is holding half of a build that has been replaced, and the only thing that
 * can fix it is fetching the new one. Everything else gets a message that says what
 * happened and offers the two things worth trying.
 *
 * The reload is guarded by a `sessionStorage` flag, because an error that survives a
 * refresh would otherwise reload for ever, and a page stuck in a reload loop is worse
 * than one showing an error: you cannot read the error.
 */

const STALE_BUILD =
  /ChunkLoadError|Loading chunk \S+ failed|Failed to fetch dynamically imported module|error loading dynamically imported module/i;

const RELOADED = "office:reloaded-after-stale-chunk";

export default function ConsoleError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // `name` matters as much as `message`: a ChunkLoadError carries its identity there and
  // may have nothing useful in the message at all.
  const stale = STALE_BUILD.test(`${error.name} ${error.message}`);
  const [reloading, setReloading] = useState(false);

  useEffect(() => {
    if (!stale) return;

    let alreadyTried = false;
    try {
      alreadyTried = window.sessionStorage.getItem(RELOADED) === "1";
      window.sessionStorage.setItem(RELOADED, "1");
    } catch {
      // Private mode, or storage denied. Better to skip the automatic reload than to
      // risk a loop we cannot detect.
      alreadyTried = true;
    }

    if (!alreadyTried) {
      setReloading(true);
      window.location.reload();
    }
  }, [stale]);

  // A successful load clears the flag, so the next stale build is handled automatically
  // rather than being refused because of one that happened weeks ago.
  useEffect(() => {
    if (stale) return;
    try {
      window.sessionStorage.removeItem(RELOADED);
    } catch {
      // Nothing to clear if storage is unavailable.
    }
  }, [stale]);

  return (
    <div className="mx-auto max-w-2xl py-16">
      <div className="rounded-xl border border-bad-line bg-bad-bg px-6 py-5">
        <h1 className="text-page font-medium text-bad">
          {stale ? "This page is from an older version" : "This page did not load"}
        </h1>

        <p className="mt-2 text-desc text-ink-secondary">
          {stale
            ? reloading
              ? "The console was updated while this tab was open. Reloading…"
              : "The console was updated while this tab was open, and part of the old " +
                "version is still in this tab. Reloading fetches the new one."
            : "Something in this page threw while rendering in the browser. Nothing was " +
              "written: every action in this console is a deliberate submission, and " +
              "this failure happened before any of them."}
        </p>

        {error.digest ? (
          <p className="mt-2 text-meta text-ink-muted">
            Reference <code className="text-ident">{error.digest}</code> — this identifies
            the failure in the server log.
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
          >
            Reload the page
          </button>
          <button
            type="button"
            onClick={() => reset()}
            className="rounded-lg border border-line px-3 py-1.5 text-desc font-medium text-ink transition hover:bg-surface-muted"
          >
            Try again without reloading
          </button>
        </div>
      </div>
    </div>
  );
}
