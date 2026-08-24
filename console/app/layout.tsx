import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "The Office — Console",
  description: "Operations console for the Village↔Forge identity and execution layer.",
};

/**
 * Fourteen links, four groups.
 *
 * Flat, they wrapped onto two lines with no grouping and no order anybody could infer —
 * which meant every visit was a scan. The groups are the four things somebody comes
 * here to do, and the labels are the answer to "where would I look for this".
 *
 * Same links. Nothing was added, removed or renamed.
 */
const NAV: { group: string; links: { href: string; label: string }[] }[] = [
  {
    group: "Operate",
    links: [
      { href: "/ventures", label: "Ventures" },
      { href: "/packs", label: "Packs" },
      { href: "/provisioning", label: "Provisioning" },
      { href: "/agents", label: "Agents" },
      { href: "/proposals", label: "Approvals" },
    ],
  },
  {
    group: "Teach",
    links: [
      { href: "/instructions", label: "Instructions" },
      { href: "/knowledge", label: "Knowledge" },
    ],
  },
  {
    group: "Govern",
    links: [
      { href: "/", label: "Compliance" },
      { href: "/incidents", label: "Incidents" },
      { href: "/revocations", label: "Revocation" },
      { href: "/access", label: "Access" },
    ],
  },
  {
    group: "Inspect",
    links: [
      { href: "/forge-map", label: "Forge Map" },
      { href: "/audit", label: "Audit" },
    ],
  },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-6xl px-6 py-6">
          <header className="mb-6 border-b border-line pb-4">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <h1 className="text-section font-medium text-ink">The Office</h1>
                <p className="text-meta text-ink-muted">
                  Every action here is audited with you as the actor. Humans sign, not
                  agents.
                </p>
              </div>
              <Link
                href="/login"
                className="text-meta text-ink-muted underline underline-offset-2 hover:text-ink"
              >
                Session
              </Link>
            </div>

            <nav className="mt-4 flex flex-wrap gap-x-8 gap-y-3">
              {NAV.map((section) => (
                <div key={section.group}>
                  <div className="text-ident uppercase tracking-wide text-ink-muted">
                    {section.group}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3">
                    {section.links.map((item) => (
                      <Link
                        key={item.href}
                        href={item.href}
                        className="text-desc text-ink-secondary hover:text-ink"
                      >
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
