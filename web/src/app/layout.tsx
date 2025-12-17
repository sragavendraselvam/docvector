import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import { ThemeProvider } from "@/lib/theme-context";

export const metadata: Metadata = {
  title: "DocVector - AI-Powered Documentation Search",
  description: "Search across all your documentation with AI-powered semantic search. Built for the MCP ecosystem.",
  keywords: ["documentation", "search", "AI", "semantic search", "MCP", "Claude", "vector database"],
  authors: [{ name: "DocVector" }],
  icons: {
    icon: "/favicon.svg",
    apple: "/logo.svg",
  },
  openGraph: {
    title: "DocVector - AI-Powered Documentation Search",
    description: "Index your docs, search semantically, and let AI agents find the answers.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen antialiased" style={{ background: "var(--background)", color: "var(--foreground)" }}>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
