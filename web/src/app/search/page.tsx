"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { Search as SearchIcon, ExternalLink, FileText, Loader2 } from "lucide-react";
import { api, SearchResult, Library } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Navbar } from "@/components/layout/navbar";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [selectedLibrary, setSelectedLibrary] = useState<string>("");

  useEffect(() => {
    // Load libraries for filter dropdown
    api.listLibraries().then(setLibraries).catch(console.error);
  }, []);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearched(true);

    try {
      const response = await api.search({
        query: query.trim(),
        library_id: selectedLibrary || undefined,
        limit: 10,
      });
      setResults(response.results || []);
    } catch (err) {
      console.error("Search failed:", err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Navbar />

      <main className="max-w-4xl mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
            Search Documentation
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            AI-powered semantic search across all indexed documentation
          </p>
        </div>

        {/* Search Form */}
        <form onSubmit={handleSearch} className="mb-8">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <Input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="How do I use hooks in React?"
                className="h-12 text-lg"
              />
            </div>
            {libraries.length > 0 && (
              <select
                value={selectedLibrary}
                onChange={(e) => setSelectedLibrary(e.target.value)}
                className="h-12 px-4 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
              >
                <option value="">All Libraries</option>
                {libraries.map((lib) => (
                  <option key={lib.id} value={lib.id}>
                    {lib.name}
                  </option>
                ))}
              </select>
            )}
            <Button type="submit" size="lg" disabled={loading || !query.trim()}>
              {loading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <SearchIcon className="h-5 w-5" />
              )}
              <span className="ml-2">Search</span>
            </Button>
          </div>
        </form>

        {/* Results */}
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="h-10 w-10 animate-spin text-primary-600 mb-4" />
            <p className="text-gray-500 dark:text-gray-400">Searching...</p>
          </div>
        ) : searched && results.length === 0 ? (
          <div className="text-center py-20">
            <FileText className="h-12 w-12 mx-auto text-gray-400 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              No results found
            </h3>
            <p className="text-gray-500 dark:text-gray-400">
              Try a different search query or add more documentation sources
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {results.map((result, index) => {
              // Extract library name from metadata or URL
              const libraryName = result.metadata?.library_name as string
                || result.metadata?.source as string
                || (result.url ? new URL(result.url).hostname.replace('www.', '').split('.')[0] : 'docs');
              const sourceUrl = result.url || result.source_url;

              return (
                <Card key={result.chunk_id || index} className="hover:shadow-md transition-shadow">
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-400">
                            {libraryName}
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            Score: {(result.score * 100).toFixed(1)}%
                          </span>
                          {result.title && (
                            <span className="text-xs text-gray-600 dark:text-gray-300 font-medium truncate max-w-[200px]">
                              {result.title}
                            </span>
                          )}
                        </div>
                        <p className="text-gray-700 dark:text-gray-300 text-sm leading-relaxed line-clamp-4">
                          {result.content}
                        </p>
                      </div>
                      {sourceUrl && (
                        <a
                          href={sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex-shrink-0 p-2 text-gray-400 hover:text-cyan-600 transition-colors"
                          title="View source"
                        >
                          <ExternalLink className="h-5 w-5" />
                        </a>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
