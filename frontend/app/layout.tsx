import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

/**
 * Primary font per UI_UX_DESIGN_SPECIFICATION §6.
 * Inter is used for body text; Poppins for headings is applied via CSS.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

/**
 * Application-wide metadata for SEO.
 * Updated per milestone as new pages are added.
 */
export const metadata: Metadata = {
  title: {
    default: "IntelliFlow AI",
    template: "%s | IntelliFlow AI",
  },
  description:
    "Enterprise SaaS platform combining AI, Workflow Automation, Document Intelligence, and Predictive Analytics.",
  keywords: ["AI", "workflow automation", "document intelligence", "analytics", "SaaS"],
  authors: [{ name: "IntelliFlow AI Team" }],
  robots: { index: false, follow: false }, // Set to true once publicly launched
};

/**
 * Root layout — wraps every page in the application.
 * Fonts and global styles are applied here.
 */
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} h-full`} suppressHydrationWarning>
      <body className="min-h-full bg-background font-sans antialiased">{children}</body>
    </html>
  );
}
