/**
 * LookalikeResults — displays lookalike match results.
 * Re-exported for backwards compatibility; primary rendering is inline in the page.
 */
"use client";

import { GitBranch } from "lucide-react";
import type { LookalikeMatch } from "@/types";
import { LookalikeMatchCard } from "@/components/lookalike/LookalikeMatchCard";
import { Spinner } from "@/components/ui/Spinner";
import { Badge } from "@/components/ui/Badge";

interface LookalikeResultsProps {
  results: LookalikeMatch[] | null;
  loading: boolean;
  error: string | null;
}

export function LookalikeResults({
  results,
  loading,
  error,
}: LookalikeResultsProps) {
  return (
    <div className="rounded-xl border border-[#E8E4DC] bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <h2 className="text-lg font-semibold tracking-tight text-[#1A1A2E]">
          Similar Channels
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

      {results === null && !loading && (
        <div className="flex flex-col items-center justify-center py-16">
          <GitBranch size={48} className="mb-4 text-[#E8E4DC]" />
          <p className="text-sm text-[#6B6B6B]">
            Enter seed creators to find similar channels
          </p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-16">
          <Spinner size="lg" />
        </div>
      )}

      {results && !loading && results.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16">
          <p className="text-sm text-[#6B6B6B]">
            No similar channels found for the given creators
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
  );
}
