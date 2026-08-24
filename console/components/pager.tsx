import Link from "next/link";

import { Badge } from "@/components/ui";
import { hasNextPage, pageSummary } from "@/lib/severity";

/**
 * What a list did not show, and how to see the rest.
 *
 * The audit explorer capped at 100 rows and said nothing about the rest. "I searched
 * the audit log and found nothing" is the entire value of that screen, and it was
 * indistinguishable from "I looked at the most recent hundred" — one of those is
 * evidence and the other is a coincidence.
 *
 * This project's rule is *report the denominator*, and this is it for lists. The count
 * renders whether or not there is a next page, because "all 43" is the reassuring
 * sentence and it has to be earned rather than assumed from an absence of controls.
 */
export function Pager({
  page,
  basePath,
  params,
}: {
  page: { total: number; limit: number; offset: number; items: unknown[] };
  basePath: string;
  /** Current filters, so paging does not silently drop them. */
  params?: Record<string, string | undefined>;
}) {
  const summary = pageSummary(page);

  const href = (offset: number) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value) query.set(key, value);
    }
    query.set("limit", String(page.limit));
    if (offset > 0) query.set("offset", String(offset));
    return `${basePath}?${query}`;
  };

  const previous = Math.max(0, page.offset - page.limit);
  const next = page.offset + page.limit;

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
      {/* One interpolation, not `showing {summary.text}`. React renders the second
          form as separate text nodes with a comment between them, so the sentence a
          reader sees never exists as a string in the HTML - which broke the smoke
          check that greps for it, exactly as it broke the gate-ladder check before. */}
      <Badge severity={summary.truncated ? "warn" : "neutral"}>
        {`showing ${summary.text}`}
      </Badge>

      {summary.truncated ? (
        <span className="text-ink-secondary">
          This is not the whole result. Narrow the filters or page through.
        </span>
      ) : null}

      <span className="ml-auto flex gap-3">
        {page.offset > 0 ? (
          <Link href={href(previous)} className="underline underline-offset-2">
            ← previous
          </Link>
        ) : null}
        {hasNextPage(page) ? (
          <Link href={href(next)} className="underline underline-offset-2">
            next →
          </Link>
        ) : null}
      </span>
    </div>
  );
}
