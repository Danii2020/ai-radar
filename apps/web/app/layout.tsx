import { Analytics } from "@vercel/analytics/next";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Radar — curated AI news",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          background: "var(--surface-page)",
          color: "var(--ink)",
          fontFamily: "var(--font-sans)",
        }}
      >
        {children}
        {/* Page views only, and only on Vercel: elsewhere the component would request a Vercel script. */}
        {process.env.VERCEL ? <Analytics /> : null}
      </body>
    </html>
  );
}
