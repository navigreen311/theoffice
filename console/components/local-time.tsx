"use client";

import { useEffect, useState } from "react";

/**
 * A timestamp in the reader's own timezone, without a hydration mismatch.
 *
 * `new Date(iso).toLocaleString()` inside a Server Component is rendered twice against
 * two different runtimes: once by Node, in the server's locale and timezone, and again
 * by the browser, in the reader's. The two strings differ on essentially every machine —
 * `24/08/2026, 13:02:11` against `8/24/2026, 1:02:11 PM`, or a different hour entirely —
 * and React reconciles that as a hydration error rather than a formatting difference.
 *
 * Showing the *reader's* local time is the right behaviour, so the answer is not to pin
 * a timezone. It is to render something stable on the server and localise after mount,
 * which is the one point where the browser's locale is actually knowable.
 *
 * The server-rendered fallback is a real, readable UTC timestamp rather than a blank or
 * a skeleton: with JavaScript disabled, or before hydration, the page still says when.
 */
export function LocalTime({
  iso,
  mode = "datetime",
}: {
  iso: string;
  /** `time` for a row in a list of same-day events; `datetime` for an as-of stamp. */
  mode?: "datetime" | "time";
}) {
  const date = new Date(iso);

  // Deterministic on both sides: an explicit locale, an explicit zone, no ambiguity.
  const stable =
    mode === "time"
      ? `${date.toISOString().slice(11, 19)} UTC`
      : `${date.toISOString().slice(0, 16).replace("T", " ")} UTC`;

  const [text, setText] = useState(stable);

  useEffect(() => {
    setText(
      mode === "time" ? date.toLocaleTimeString() : date.toLocaleString(),
    );
    // `iso` is the input; `date` is derived from it and `mode` never changes per site.
  }, [iso, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  return <time dateTime={iso} title={date.toISOString()}>{text}</time>;
}

/**
 * "As of" — the same problem, and the one where the page is claiming to be evidence.
 *
 * A screenshot of a compliance page with no time on it cannot be dated, so this must not
 * degrade to nothing. It degrades to UTC.
 */
export function AsOf({ iso }: { iso: string }) {
  return (
    <>
      As of <LocalTime iso={iso} />
    </>
  );
}

/**
 * "3m ago", without a hydration mismatch.
 *
 * `relativeAge` is `Date.now()` minus a timestamp, and it was being called during server
 * rendering on fifteen screens. The server renders "3s ago"; the browser hydrates a
 * moment later and renders "5s ago"; React compares the two and reports a hydration
 * error, because it cannot know the difference is the clock rather than a bug. Under
 * `next start` that discards the server HTML and re-renders the whole tree on the
 * client, which is what a blank flash on load looks like.
 *
 * Client components do not escape it either — they are server-rendered too — so the fix
 * has to live here rather than in the pages that call it.
 *
 * First paint is the absolute time, which is stable on both sides and is also the more
 * useful value in the case the relative one reads worst: five gates that all completed
 * inside a second rendered as five rows of "0s ago", which reads as a broken clock.
 * After mount it becomes relative, and re-renders on a timer so it does not go stale
 * while somebody is reading the page.
 */
export function Ago({ iso }: { iso: string | null | undefined }) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    // A minute is fine: nothing here is precise to the second, and the absolute time is
    // one hover away.
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  if (!iso) return <>never</>;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return <>unknown</>;

  if (now === null) {
    // Server render and first paint. Deterministic, and never wrong.
    return (
      <time dateTime={iso} title={new Date(iso).toISOString()}>
        {new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC
      </time>
    );
  }

  const seconds = Math.max(0, Math.floor((now - then) / 1000));
  const text =
    seconds < 90
      ? `${seconds}s ago`
      : seconds < 5400
        ? `${Math.floor(seconds / 60)}m ago`
        : seconds < 172800
          ? `${Math.floor(seconds / 3600)}h ago`
          : `${Math.floor(seconds / 86400)}d ago`;

  return (
    <time dateTime={iso} title={new Date(iso).toLocaleString()}>
      {text}
    </time>
  );
}

/**
 * The client's clock, after mount. `null` during server render and first paint.
 *
 * One place in the console reads the clock, and this is it. Anything that needs "how
 * long until" or "is this overdue" derives it from this value rather than calling
 * `Date.now()` in its own render, which produces one answer on the server and another on
 * hydration — the mismatch that blanked pages once already.
 *
 * The smoke script enforces that by failing on `Date.now()` anywhere in `app/` or
 * `components/` except this file. That is a blunt rule and deliberately so: a rule that
 * tried to tell a safe call from an unsafe one by reading the surrounding code would be
 * wrong occasionally, and the failure it guards against is invisible to every other
 * check we run.
 */
export function useNow(intervalMs = 60_000): number | null {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);

  return now;
}
