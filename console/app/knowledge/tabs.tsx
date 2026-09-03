"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Five knowledge bases, five routes.
 *
 * They shared one ~4,000px page: five tables and five authoring forms stacked, with 121
 * rows rendered unpaginated and no search anywhere. Each of these stores answers a
 * different question and blocks a different thing, and putting them on one page meant
 * none of them had room for its own filters.
 *
 * Instructions is a link out rather than a tab: it already has its own page with the
 * eight-section view and an authoring form, and a second one would be a second answer to
 * the same question.
 */

const TABS = [
  { href: "/knowledge", label: "Overview" },
  { href: "/instructions", label: "Instructions", external: true },
  { href: "/knowledge/compliance", label: "Compliance" },
  { href: "/knowledge/playbooks", label: "Playbooks" },
  { href: "/knowledge/personas", label: "Personas" },
  { href: "/knowledge/history", label: "History" },
];

export function KnowledgeTabs() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-1 border-b border-line pb-2">
      {TABS.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={`rounded-lg px-2.5 py-1 text-desc transition ${
              active
                ? "bg-surface-inverse text-ink-inverse"
                : "text-ink-secondary hover:bg-surface-muted"
            }`}
          >
            {tab.label}
            {tab.external ? <span className="ml-1 text-ink-muted">↗</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}
