import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tech Hype Monitor",
  description: "Local-first Phase 1 collector and event browser",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <nav className="nav">
            <Link href="/" className="brand">
              Tech Hype Monitor
            </Link>
            <Link href="/">Dashboard</Link>
            <Link href="/events">Events</Link>
            <Link href="/source-health">Source Health</Link>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}
