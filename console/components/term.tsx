import type { ReactNode } from "react";

import { DOMAIN, label as labelFor, type Vocabulary } from "@/lib/vocabulary";

/**
 * A stored value, shown as a person reads it with the identifier kept beside it.
 *
 * The pattern, applied everywhere: human label as primary text, code identifier as 11px
 * monospace secondary. Never the identifier alone, and never the label alone either —
 * engineers need the identifier, it is what appears in every log and export, and a screen
 * that hides it makes the log harder to use rather than easier.
 *
 *     Waiting for you        ← 13px, primary
 *     awaiting_human         ← 11px mono, muted
 */
export function Term({
  value,
  from,
  className,
}: {
  value: string | null | undefined;
  /** The dictionary to prefer, when the same string means different things. */
  from?: Vocabulary;
  className?: string;
}) {
  if (!value) return <span className="text-desc text-ink-muted">—</span>;

  const text = labelFor(value, from);
  const sameThing = text.toLowerCase() === value.toLowerCase();

  return (
    <span className={`inline-flex flex-wrap items-baseline gap-x-1.5 ${className ?? ""}`}>
      <span className="text-desc text-ink">{text}</span>
      {/* Suppressed only when the label and the identifier are the same word, where
          showing both is noise rather than precision. */}
      {sameThing ? null : (
        <code className="font-mono text-ident text-ink-muted">{value}</code>
      )}
    </span>
  );
}

/**
 * A domain term with its definition attached.
 *
 * Pack, Forge, Gate, Grant and the rest are proper nouns for real things and are not
 * replaced. What a reader has never seen is what one *is*, so the definition rides along
 * on first use rather than living on a glossary page nobody opens mid-task.
 */
export function Define({
  term,
  children,
}: {
  term: keyof typeof DOMAIN | string;
  children?: ReactNode;
}) {
  const definition = DOMAIN[term as string];
  if (!definition) return <>{children ?? term}</>;

  return (
    <span
      title={definition}
      className="underline decoration-dotted decoration-from-font underline-offset-2"
    >
      {children ?? term}
    </span>
  );
}

/**
 * The one-line definitions for the terms a page uses, rendered once near the top.
 *
 * `title` alone is not enough: it is invisible on a touch screen and to anybody who does
 * not think to hover. This states them outright, and the page still marks each term where
 * it appears.
 */
export function Glossary({ terms }: { terms: string[] }) {
  const known = terms.filter((term) => DOMAIN[term]);
  if (known.length === 0) return null;

  return (
    <details className="rounded-xl border border-line bg-surface px-5 py-3">
      <summary className="cursor-pointer text-desc text-ink-secondary">
        What these words mean on this page
      </summary>
      <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
        {known.map((term) => (
          <div key={term} className="flex flex-wrap items-baseline gap-x-2">
            <dt className="text-desc font-medium text-ink">{term}</dt>
            <dd className="text-meta text-ink-secondary">{DOMAIN[term]}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/**
 * Prose that quotes a code identifier, with the quoted run set as one.
 *
 * `Term` covers a stored value that has a label. This covers the other shape: a sentence
 * *about* the system, which has to name a table, a column or a function to say anything
 * useful. The audit glossary in `broker/audit_events.py` already marks those runs with
 * backticks and the console rendered the string raw — so the backticks themselves reached
 * the screen, and the identifiers between them were set in the same size and colour as
 * the sentence around them.
 *
 * That is the failure `Term`'s doctrine exists to prevent, arriving through the one door
 * it did not cover. **The mark-up said which words were identifiers and nothing read it.**
 * The console smoke check caught it as three identifiers rendering as primary text on
 * /audit; the fix is to honour the marks, not to widen the check's allow-list, which
 * would have made the sentence pass while still reading wrong.
 *
 *     A hand-set agent_forge_grant.revoked_at was removed.   ← before: 12px, prose colour
 *     A hand-set `agent_forge_grant.revoked_at` was removed. ← after:  11px mono, muted
 *
 * Splits on PAIRED backticks only. A lone backtick is left as written rather than
 * swallowing the rest of the sentence into a code span — a rendering bug should not be
 * able to hide the text it was given.
 */
export function Prose({ text }: { text: string }) {
  const parts = text.split(/`([^`]+)`/g);

  return (
    <>
      {parts.map((part, index) =>
        // Odd indices are the capture groups, which is to say the quoted runs.
        index % 2 === 1 ? (
          <code key={index} className="font-mono text-ident text-ink-muted">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}
