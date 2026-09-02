import type { Metadata } from "next";
import { Inter, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";

/**
 * Body font — Inter for high readability in dense document interfaces.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600"],
});

/**
 * Display font — Plus Jakarta Sans for editorial headings.
 * Loaded with specific weights to avoid bundle bloat.
 */
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-jakarta",
  display: "swap",
  weight: ["600", "700", "800"],
});

export const metadata: Metadata = {
  title: {
    default: "IntelliFlow AI",
    template: "%s | IntelliFlow AI",
  },
  description:
    "Enterprise document intelligence platform — manage knowledge, automate workflows, and gain predictive insights.",
  keywords: ["document management", "workflow automation", "document intelligence", "analytics", "enterprise SaaS"],
  authors: [{ name: "IntelliFlow AI" }],
  robots: { index: false, follow: false },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jakarta.variable} h-full`}
      suppressHydrationWarning
    >
      <body className="min-h-full antialiased">{children}</body>
    </html>
  );
}
