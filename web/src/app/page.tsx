"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Logo } from "@/components/ui/logo";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { Search, Zap, Shield, ArrowRight, Sparkles } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen" style={{ background: "var(--background)" }}>
      {/* Gradient background overlay */}
      <div className="fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-1/2 -right-1/4 w-[800px] h-[800px] rounded-full bg-gradient-to-br from-cyan-500/20 to-violet-500/20 blur-3xl" />
        <div className="absolute -bottom-1/2 -left-1/4 w-[600px] h-[600px] rounded-full bg-gradient-to-tr from-emerald-500/10 to-cyan-500/10 blur-3xl" />
      </div>

      {/* Header */}
      <header className="container mx-auto px-4 py-6">
        <nav className="flex justify-between items-center">
          <Logo size={40} />
          <div className="flex items-center space-x-4">
            <ThemeToggle />
            <Link href="/dashboard/sources">
              <Button variant="ghost">Manage Sources</Button>
            </Link>
            <Link href="/search">
              <Button>Search Docs</Button>
            </Link>
          </div>
        </nav>
      </header>

      {/* Hero */}
      <main className="container mx-auto px-4 pt-20 pb-32">
        <div className="text-center max-w-4xl mx-auto">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-cyan-500/10 to-violet-500/10 border border-cyan-500/20 text-sm text-cyan-600 dark:text-cyan-400 mb-8">
            <Sparkles className="h-4 w-4" />
            <span>Built for the MCP ecosystem</span>
          </div>

          <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold mb-6">
            <span style={{ color: "var(--foreground)" }}>AI-Powered Search for </span>
            <span className="bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">
              Documentation
            </span>
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-300 mb-10 max-w-2xl mx-auto">
            Index your docs, search semantically, and let AI agents find the
            answers. Powered by vector embeddings and hybrid search.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/search">
              <button className="group relative inline-flex items-center justify-center px-8 py-4 text-base font-medium text-white rounded-xl overflow-hidden transition-all duration-300 hover:scale-105">
                <div className="absolute inset-0 bg-gradient-to-r from-cyan-500 to-violet-500 transition-all duration-300 group-hover:from-cyan-400 group-hover:to-violet-400"></div>
                <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-gradient-to-r from-cyan-400 to-violet-400 blur-xl"></div>
                <span className="relative flex items-center gap-2">
                  Start Searching
                  <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </span>
              </button>
            </Link>
            <Link href="/search">
              <button className="group relative inline-flex items-center justify-center px-8 py-4 text-base font-medium rounded-xl border-2 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-white bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm hover:border-cyan-500 dark:hover:border-cyan-400 hover:text-cyan-600 dark:hover:text-cyan-400 transition-all duration-300">
                <Search className="h-5 w-5 mr-2" />
                Try Search
              </button>
            </Link>
          </div>
        </div>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-6 mt-32">
          {/* Feature Card 1 */}
          <div className="group relative">
            <div className="absolute -inset-[1px] rounded-2xl bg-gradient-to-b from-cyan-500/50 via-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm"></div>
            <div className="relative p-8 rounded-2xl border group-hover:border-cyan-500/50 transition-all duration-300 h-full" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
              <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-gradient-to-br from-cyan-500 to-cyan-400 text-white mb-6 shadow-lg shadow-cyan-500/25">
                <Search className="h-7 w-7" />
              </div>
              <h3 className="text-xl font-semibold mb-3" style={{ color: "var(--foreground)" }}>
                Semantic Search
              </h3>
              <p className="leading-relaxed" style={{ color: "var(--foreground-secondary)" }}>
                Find relevant docs with AI-powered semantic search. No more keyword guessing.
              </p>
            </div>
          </div>

          {/* Feature Card 2 */}
          <div className="group relative">
            <div className="absolute -inset-[1px] rounded-2xl bg-gradient-to-b from-emerald-500/50 via-emerald-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm"></div>
            <div className="relative p-8 rounded-2xl border group-hover:border-emerald-500/50 transition-all duration-300 h-full" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
              <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-400 text-white mb-6 shadow-lg shadow-emerald-500/25">
                <Zap className="h-7 w-7" />
              </div>
              <h3 className="text-xl font-semibold mb-3" style={{ color: "var(--foreground)" }}>
                MCP Native
              </h3>
              <p className="leading-relaxed" style={{ color: "var(--foreground-secondary)" }}>
                Built for AI agents. Works with Claude Desktop, Cursor, and any MCP host.
              </p>
            </div>
          </div>

          {/* Feature Card 3 */}
          <div className="group relative">
            <div className="absolute -inset-[1px] rounded-2xl bg-gradient-to-b from-violet-500/50 via-violet-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-sm"></div>
            <div className="relative p-8 rounded-2xl border group-hover:border-violet-500/50 transition-all duration-300 h-full" style={{ background: "var(--card)", borderColor: "var(--border)" }}>
              <div className="inline-flex items-center justify-center h-14 w-14 rounded-2xl bg-gradient-to-br from-violet-500 to-violet-400 text-white mb-6 shadow-lg shadow-violet-500/25">
                <Shield className="h-7 w-7" />
              </div>
              <h3 className="text-xl font-semibold mb-3" style={{ color: "var(--foreground)" }}>
                Self-Hostable
              </h3>
              <p className="leading-relaxed" style={{ color: "var(--foreground-secondary)" }}>
                Run on your own infrastructure. Full data control with Docker deployment.
              </p>
            </div>
          </div>
        </div>

        {/* Code snippet */}
        <div className="mt-32 max-w-3xl mx-auto">
          <div className="bg-gray-900 dark:bg-gray-950 rounded-2xl p-6 overflow-hidden border border-gray-800 shadow-2xl shadow-cyan-500/10">
            <div className="flex items-center space-x-2 mb-4">
              <div className="h-3 w-3 rounded-full bg-red-500"></div>
              <div className="h-3 w-3 rounded-full bg-yellow-500"></div>
              <div className="h-3 w-3 rounded-full bg-green-500"></div>
              <span className="text-gray-400 text-sm ml-4">
                claude_desktop_config.json
              </span>
            </div>
            <pre className="text-sm text-gray-300 overflow-x-auto">
              <code>{`{
  "mcpServers": {
    "docvector": {
      "command": "python",
      "args": ["-m", "docvector.mcp.server"],
      "env": {
        "DOCVECTOR_API_URL": "https://api.docvector.dev"
      }
    }
  }
}`}</code>
            </pre>
          </div>
        </div>

        {/* Stats */}
        <div className="mt-32 grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="text-center">
            <div className="text-4xl font-bold bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">9K+</div>
            <div className="text-gray-600 dark:text-gray-300 mt-1">Vectors Indexed</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">23+</div>
            <div className="text-gray-600 dark:text-gray-300 mt-1">Libraries</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">&lt;100ms</div>
            <div className="text-gray-600 dark:text-gray-300 mt-1">Avg Response</div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold bg-gradient-to-r from-cyan-500 to-violet-500 bg-clip-text text-transparent">100%</div>
            <div className="text-gray-600 dark:text-gray-300 mt-1">Open Source</div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 dark:border-gray-800 py-12">
        <div className="container mx-auto px-4 text-center text-gray-500 dark:text-gray-300">
          <Logo size={32} className="justify-center mb-4" />
          <p>&copy; 2024 DocVector. Open source under MIT license.</p>
        </div>
      </footer>
    </div>
  );
}
