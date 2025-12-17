"use client";

import { useEffect, useState } from "react";
import { api, Source, Library } from "@/lib/api";
import { Navbar } from "@/components/layout/navbar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Database,
  Plus,
  Trash2,
  ExternalLink,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
} from "lucide-react";

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newSource, setNewSource] = useState({
    name: "",
    url: "",
    library_id: "",
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [sourcesData, librariesData] = await Promise.all([
        api.listSources(),
        api.listLibraries(),
      ]);
      setSources(sourcesData);
      setLibraries(librariesData);
    } catch (err) {
      console.error("Failed to load data:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddSource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSource.name.trim() || !newSource.url.trim()) return;

    setCreating(true);
    try {
      await api.createSource({
        name: newSource.name.trim(),
        url: newSource.url.trim(),
        library_id: newSource.library_id || undefined,
      });
      setNewSource({ name: "", url: "", library_id: "" });
      setShowAddForm(false);
      await loadData();
    } catch (err) {
      console.error("Failed to add source:", err);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteSource = async (sourceId: string) => {
    if (!confirm("Are you sure you want to delete this source? All indexed documents will be removed.")) {
      return;
    }

    try {
      await api.deleteSource(sourceId);
      await loadData();
    } catch (err) {
      console.error("Failed to delete source:", err);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
      case "indexed":
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case "failed":
      case "error":
        return <XCircle className="h-5 w-5 text-red-500" />;
      case "processing":
      case "crawling":
        return <Loader2 className="h-5 w-5 text-primary-500 animate-spin" />;
      default:
        return <Clock className="h-5 w-5 text-gray-400" />;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <Navbar />

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
              Documentation Sources
            </h1>
            <p className="text-gray-600 dark:text-gray-400 mt-1">
              Add and manage documentation sources to index
            </p>
          </div>
          <Button onClick={() => setShowAddForm(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Add Source
          </Button>
        </div>

        {/* Add Source Form */}
        {showAddForm && (
          <Card className="mb-6">
            <CardHeader>
              <CardTitle>Add Documentation Source</CardTitle>
              <CardDescription>
                Enter a URL to crawl and index documentation
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleAddSource} className="space-y-4">
                <Input
                  label="Source Name"
                  value={newSource.name}
                  onChange={(e) => setNewSource({ ...newSource, name: e.target.value })}
                  placeholder="e.g., React Documentation"
                  required
                />
                <Input
                  label="Documentation URL"
                  type="url"
                  value={newSource.url}
                  onChange={(e) => setNewSource({ ...newSource, url: e.target.value })}
                  placeholder="https://react.dev/docs"
                  required
                />
                {libraries.length > 0 && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Library (optional)
                    </label>
                    <select
                      value={newSource.library_id}
                      onChange={(e) => setNewSource({ ...newSource, library_id: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    >
                      <option value="">No library</option>
                      {libraries.map((lib) => (
                        <option key={lib.id} value={lib.id}>
                          {lib.name}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="flex gap-3">
                  <Button type="submit" loading={creating}>
                    Add & Start Indexing
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setShowAddForm(false)}
                  >
                    Cancel
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Sources List */}
        <Card>
          <CardHeader>
            <CardTitle>Your Sources</CardTitle>
            <CardDescription>
              {sources.length === 0
                ? "No documentation sources added yet"
                : `${sources.length} source${sources.length === 1 ? "" : "s"} configured`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div
                    key={i}
                    className="h-20 bg-gray-100 dark:bg-gray-800 rounded-lg animate-pulse"
                  ></div>
                ))}
              </div>
            ) : sources.length === 0 ? (
              <div className="text-center py-12">
                <Database className="h-12 w-12 mx-auto text-gray-400 mb-4" />
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                  No sources yet
                </h3>
                <p className="text-gray-500 dark:text-gray-400 mb-6">
                  Add your first documentation source to start indexing
                </p>
                <Button onClick={() => setShowAddForm(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Add your first source
                </Button>
              </div>
            ) : (
              <div className="divide-y divide-gray-200 dark:divide-gray-800">
                {sources.map((source) => {
                  // Extract URL from config
                  const sourceUrl = source.config?.url || "";
                  const docsCount = source.documents_count || 0;

                  return (
                    <div key={source.id} className="py-4">
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-4">
                          <div className="h-10 w-10 rounded-lg bg-gray-100 dark:bg-gray-800 flex items-center justify-center flex-shrink-0">
                            <Database className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="font-medium text-gray-900 dark:text-white">
                                {source.name}
                              </p>
                              {getStatusIcon(source.status)}
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300">
                                {source.type}
                              </span>
                            </div>
                            {sourceUrl && (
                              <a
                                href={sourceUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sm text-primary-600 hover:text-primary-700 flex items-center gap-1"
                              >
                                {sourceUrl}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                            <div className="mt-1 flex items-center gap-4 text-sm text-gray-500 dark:text-gray-400">
                              <span>{docsCount} documents</span>
                              {source.last_synced_at && (
                                <span>
                                  Last synced:{" "}
                                  {new Date(source.last_synced_at).toLocaleDateString()}
                                </span>
                              )}
                              {source.sync_frequency && (
                                <span className="capitalize">{source.sync_frequency}</span>
                              )}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteSource(source.id)}
                            className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Libraries Section */}
        {libraries.length > 0 && (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Libraries</CardTitle>
              <CardDescription>
                Libraries help organize your documentation by project
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2">
                {libraries.map((lib) => (
                  <div
                    key={lib.id}
                    className="p-4 border border-gray-200 dark:border-gray-800 rounded-lg"
                  >
                    <h4 className="font-medium text-gray-900 dark:text-white">
                      {lib.name}
                    </h4>
                    {lib.description && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                        {lib.description}
                      </p>
                    )}
                    <div className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                      {lib.sources_count || 0} sources · {lib.documents_count || 0} docs
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
