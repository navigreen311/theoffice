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
