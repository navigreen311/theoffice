import Link from "next/link";

/**
 * Where you are, and a route back.
 *
 * There was no way home from any page: the wordmark was not a link, no nav item pointed
 * at the dashboard, and nothing said where you were. On a venture detail page the only
 * way back to the directory was the browser's back button.
 */
export function Breadcrumb({
  trail,
}: {
  /** Ancestors, nearest last. The final entry is the current page and is not a link. */
  trail: { label: string; href?: string }[];
}) {
  return (
    <nav aria-label="Breadcrumb" className="text-meta text-ink-muted">
      {trail.map((crumb, index) => (
        <span key={`${crumb.label}-${index}`}>
          {index > 0 ? <span className="px-1.5">/</span> : null}
          {crumb.href ? (
            <Link href={crumb.href} className="hover:text-ink">
              {crumb.label}
            </Link>
          ) : (
            <span className="text-ink-secondary">{crumb.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
