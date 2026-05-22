/**
 * ChannelTableView — client component managing filter state,
 * pagination, and data fetching for the channel discovery table.
 */
"use client";

import { useState, useCallback, useEffect } from "react";
import { ChevronLeft, ChevronRight, Plus, X } from "lucide-react";
import type { Channel, ChannelFilters, VelocityScore } from "@/types";
import { ChannelTable } from "@/components/channels/ChannelTable";
import { ChannelIntakePanel } from "@/components/channels/ChannelIntakePanel";
import { FilterBar, DEFAULT_FILTERS } from "@/components/filters/FilterBar";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useChannels } from "@/hooks/useChannels";
import { useAuth } from "@/hooks/useAuth";
import { getNicheTags } from "@/lib/api/backend";

interface ChannelTableViewProps {
  initialChannels: (Channel & { velocity?: VelocityScore | null })[];
  initialTotal: number;
}

const PAGE_SIZE = 25;

export function ChannelTableView({
  initialChannels,
  initialTotal,
}: ChannelTableViewProps) {
  const [filters, setFilters] = useState<ChannelFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState<number>(1);
  const [intakeOpen, setIntakeOpen] = useState<boolean>(false);
  const [nicheTagOptions, setNicheTagOptions] = useState<string[]>([]);
  const { session } = useAuth();

  const { channels, total, loading, refetch } = useChannels(
    filters,
    page,
    PAGE_SIZE,
    initialChannels,
    initialTotal
  );

  const displayChannels = channels;
  const displayTotal = total;
  const totalPages = Math.max(1, Math.ceil(displayTotal / PAGE_SIZE));
  const showBlockingLoader = loading && displayChannels.length === 0;

  const handleSetFilters = useCallback(
    (newFilters: ChannelFilters) => {
      setFilters(newFilters);
      setPage(1);
    },
    []
  );

  const handleSort = useCallback(
    (column: ChannelFilters["sort_by"]) => {
      setFilters((prev) => ({
        ...prev,
        sort_by: column,
        sort_order:
          prev.sort_by === column && prev.sort_order === "desc"
            ? "asc"
            : "desc",
      }));
      setPage(1);
    },
    []
  );

  const handleIntakeComplete = useCallback(() => {
    setPage(1);
    void refetch();
    setIntakeOpen(false);
  }, [refetch]);

  useEffect(() => {
    let cancelled = false;
    const loadNicheTags = async () => {
      try {
        const tags = await getNicheTags(session?.access_token);
        if (!cancelled) {
          setNicheTagOptions(tags);
        }
      } catch {
        if (!cancelled) {
          setNicheTagOptions([]);
        }
      }
    };
    void loadNicheTags();
    return () => {
      cancelled = true;
    };
  }, [session?.access_token]);

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-[#1A1A2E]">
          Channel Discovery
        </h1>
        <Button variant="accent" size="sm" onClick={() => setIntakeOpen(true)}>
          <Plus size={14} />
          Add / Resolve Channels
        </Button>
      </div>

      <FilterBar
        filters={filters}
        setFilters={handleSetFilters}
        nicheTagOptions={nicheTagOptions}
      />

      <div className="relative min-h-[400px]">
        {showBlockingLoader && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-white/60 backdrop-blur-sm">
            <Spinner size="lg" />
          </div>
        )}
        <ChannelTable
          channels={displayChannels}
          sortBy={filters.sort_by}
          sortOrder={filters.sort_order}
          onSort={handleSort}
        />
      </div>

      {/* Pagination */}
      <div className="mt-4 flex items-center justify-between">
        <p className="text-sm text-[#6B6B6B]">
          Showing {displayChannels.length} of {displayTotal} channels
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => {
              setPage((p) => Math.max(1, p - 1));
            }}
          >
            <ChevronLeft size={16} />
            Previous
          </Button>
          <span className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-1.5 text-sm font-medium text-[#1A1A2E]">
            {page} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => {
              setPage((p) => Math.min(totalPages, p + 1));
            }}
          >
            Next
            <ChevronRight size={16} />
          </Button>
        </div>
      </div>

      {intakeOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#1A1A2E]/55 p-4">
          <div className="max-h-[90vh] w-full max-w-7xl overflow-y-auto rounded-2xl border border-[#E8E4DC] bg-[#F7F4EE] p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold tracking-tight text-[#1A1A2E]">
                Channel Intake
              </h2>
              <button
                type="button"
                onClick={() => setIntakeOpen(false)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#6B6B6B] transition-colors hover:bg-[#1A1A2E]/5 hover:text-[#1A1A2E]"
                aria-label="Close intake modal"
              >
                <X size={16} />
              </button>
            </div>
            <ChannelIntakePanel onIntakeComplete={handleIntakeComplete} />
          </div>
        </div>
      )}
    </div>
  );
}
