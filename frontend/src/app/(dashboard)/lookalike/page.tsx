/**
 * Lookalike search page — find similar creators.
 * Client component with two-panel layout.
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { GitBranch } from "lucide-react";
import type { LookalikeMatch } from "@/types";
import { SeedCreatorInput } from "@/components/lookalike/SeedCreatorInput";
import { LookalikeMatchCard } from "@/components/lookalike/LookalikeMatchCard";
import { Spinner } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";
import { getLookalikeResults, searchLookalikes } from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import { useRealtimeRefresh } from "@/hooks/useRealtimeRefresh";

export default function LookalikePage() {
  const { session } = useAuth();
  const token = session?.access_token ?? undefined;
  const [seeds, setSeeds] = useState<string[]>([""]);
  const [results, setResults] = useState<LookalikeMatch[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshResults = useCallback(async (): Promise<void> => {
    try {
      const data = await getLookalikeResults(token);
      setResults(data);
    } catch {
      // Keep prior results if refresh fails transiently.
    }
  }, [token]);

  const realtimeTables = useMemo(
    () => [{ table: "lookalike_matches" }, { table: "seed_creators" }],
    []
  );

  useEffect(() => {
    if (!token) {
      setResults(null);
      setNotice(null);
      setError(null);
      return;
    }
    void refreshResults();
  }, [refreshResults, token]);

  useRealtimeRefresh({
    channelKey: "lookalike-live-results",
    tables: realtimeTables,
    enabled: Boolean(token),
    onRefresh: () => {
      void refreshResults();
    },
  });

  const handleSearch = async () => {
    const validSeeds = seeds.map((s) => s.trim()).filter((s) => s.length > 0);
    if (validSeeds.length === 0) return;

    setLoading(true);
    setError(null);
    setNotice(null);

    try {
      const queued = await searchLookalikes(
        validSeeds,
        token
      );
      setNotice(`${queued.message}. Results will appear automatically as matches are written.`);
      await refreshResults();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to search for lookalikes"
      );
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-[#1A1A2E]">
        Lookalike Search
      </h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        {/* Left Panel — Seed Input */}
        <div className="rounded-xl border border-[#E8E4DC] bg-white p-6 shadow-sm h-fit">
          <SeedCreatorInput
            seeds={seeds}
            onChange={setSeeds}
            onSearch={handleSearch}
            loading={loading}
          />
        </div>

        {/* Right Panel — Results */}
        <div className="rounded-xl border border-[#E8E4DC] bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <h2 className="text-lg font-semibold tracking-tight text-[#1A1A2E]">
              Lookalike Channels
            </h2>
            {results && results.length > 0 && (
              <Badge variant="gold">{results.length}</Badge>
            )}
          </div>

          {error && (
            <div className="mb-4 rounded-lg bg-[#B22222]/10 px-4 py-3 text-sm text-[#B22222]">
              {error}
            </div>
          )}
          {notice && (
            <div className="mb-4 rounded-lg bg-[#C9A84C]/10 px-4 py-3 text-sm text-[#1A1A2E]">
              {notice}
            </div>
          )}

          {/* Empty State */}
          {results === null && !loading && (
            <div className="flex flex-col items-center justify-center py-16">
              <GitBranch
                size={48}
                className="mb-4 text-[#E8E4DC]"
              />
              <p className="text-sm text-[#6B6B6B]">
                Enter seed creators to find lookalike channels
              </p>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-16">
              <Spinner size="lg" />
            </div>
          )}

          {/* Results List */}
          {results && !loading && results.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16">
              <p className="text-sm text-[#6B6B6B]">
                No lookalike channels found for the given creators
              </p>
            </div>
          )}

          {results && !loading && results.length > 0 && (
            <div className="space-y-3">
              {results.map((match) => (
                <LookalikeMatchCard key={match.id} match={match} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
