import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "The Office — Console",
  description: "Operations console for the Village↔Forge identity and execution layer.",
};

const NAV = [
  { href: "/", label: "Compliance" },
  { href: "/ventures", label: "Ventures" },
  { href: "/packs", label: "Packs" },
  { href: "/provisioning", label: "Provisioning" },
  { href: "/agents", label: "Agents" },
  { href: "/proposals", label: "Approvals" },
  { href: "/instructions", label: "Instructions" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/revocations", label: "Revocation" },
  { href: "/forge-map", label: "Forge Map" },
  { href: "/audit", label: "Audit" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto max-w-6xl px-6 py-6">
          <header className="mb-6 flex items-baseline justify-between border-b border-neutral-200 pb-4">
            <div>
              <h1 className="text-lg font-semibold">The Office</h1>
              <p className="text-xs text-neutral-500">
                Every action here is audited with you as the actor. Humans sign, not
                agents.
              </p>
            </div>
            <nav className="flex gap-4 text-sm">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-neutral-600 hover:text-neutral-900"
                >
                  {item.label}
                </Link>
              ))}
              <Link href="/login" className="text-neutral-400 hover:text-neutral-900">
                Session
              </Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
