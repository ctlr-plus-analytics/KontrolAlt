"use client";

import { useState, useCallback, useEffect, useRef, useLayoutEffect } from "react";
import { ChevronLeft, ChevronRight, Plus, RefreshCw, X } from "lucide-react";
import type { Channel, ChannelFilters, Gate0StatusOption, NicheTagOption, VelocityScore } from "@/types";
import { ChannelTable } from "@/components/channels/ChannelTable";
import { ChannelIntakePanel } from "@/components/channels/ChannelIntakePanel";
import { FilterSidebar, DEFAULT_FILTERS } from "@/components/filters/FilterSidebar";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useChannels } from "@/hooks/useChannels";
import { useAuth } from "@/hooks/useAuth";
import { getGate0Statuses, getNicheTags } from "@/lib/api/backend";

interface ChannelTableViewProps {
  initialChannels: (Channel & { velocity?: VelocityScore | null })[];
  initialTotal: number;
}

const PAGE_SIZE = 25;
const STORAGE_KEY = "channel-table-state";

function readStorage(): { filters?: ChannelFilters; page?: number; scrollTop?: number } {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as { filters?: ChannelFilters; page?: number; scrollTop?: number }) : {};
  } catch {
    return {};
  }
}

function writeStorage(patch: { filters?: ChannelFilters; page?: number; scrollTop?: number }) {
  try {
    const current = readStorage();
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...current, ...patch }));
  } catch {
    // sessionStorage unavailable — silently ignore
  }
}

export function ChannelTableView({
  initialChannels,
  initialTotal,
}: ChannelTableViewProps) {
  const [filters, setFilters] = useState<ChannelFilters>(() => {
    const saved = readStorage();
    return saved.filters ?? DEFAULT_FILTERS;
  });
  const [page, setPage] = useState<number>(() => {
    const saved = readStorage();
    return saved.page ?? 1;
  });
  const [intakeOpen, setIntakeOpen] = useState<boolean>(false);
  const [nicheTagOptions, setNicheTagOptions] = useState<NicheTagOption[]>([]);
  const [gate0StatusOptions, setGate0StatusOptions] = useState<Gate0StatusOption[]>([]);
  const { session } = useAuth();

  const scrollRef = useRef<HTMLDivElement>(null);
  const hasRestoredScroll = useRef(false);

  const { channels, total, loading, refreshing, refetch } = useChannels(
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

  // Persist filters + page to sessionStorage whenever they change.
  useEffect(() => {
    writeStorage({ filters, page });
  }, [filters, page]);

  // Save scroll position when navigating away (component unmounts).
  useEffect(() => {
    return () => {
      if (scrollRef.current) {
        writeStorage({ scrollTop: scrollRef.current.scrollTop });
      }
    };
  }, []);

  // Restore scroll position after the first successful data load.
  useLayoutEffect(() => {
    if (!loading && !hasRestoredScroll.current && scrollRef.current) {
      hasRestoredScroll.current = true;
      const saved = readStorage();
      if (saved.scrollTop) {
        scrollRef.current.scrollTop = saved.scrollTop;
      }
    }
  }, [loading]);

  const handleSetFilters = useCallback((newFilters: ChannelFilters) => {
    setFilters(newFilters);
    setPage(1);
    // Intentional filter change — reset saved scroll so we start from top.
    writeStorage({ scrollTop: 0 });
  }, []);

  const handleSort = useCallback((column: ChannelFilters["sort_by"]) => {
    setFilters((prev) => ({
      ...prev,
      sort_by: column,
      sort_order:
        prev.sort_by === column && prev.sort_order === "desc" ? "asc" : "desc",
    }));
    setPage(1);
    writeStorage({ scrollTop: 0 });
  }, []);

  const handleIntakeComplete = useCallback(() => {
    setPage(1);
    void refetch();
    setIntakeOpen(false);
  }, [refetch]);

  useEffect(() => {
    let cancelled = false;
    const loadFilterOptions = async () => {
      const [tagsResult, statusesResult] = await Promise.allSettled([
        getNicheTags(session?.access_token),
        getGate0Statuses(session?.access_token),
      ]);

      if (cancelled) {
        return;
      }

      if (tagsResult.status === "fulfilled") {
        setNicheTagOptions(tagsResult.value);
      } else {
        setNicheTagOptions([]);
      }

      if (statusesResult.status === "fulfilled") {
        setGate0StatusOptions(statusesResult.value);
      } else {
        setGate0StatusOptions([
          { status: "unchecked", count: 0 },
          { status: "pending", count: 0 },
          { status: "clean", count: 0 },
          { status: "dirty", count: 0 },
        ]);
      }
    };
    void loadFilterOptions();
    return () => { cancelled = true; };
  }, [session?.access_token]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Filter Sidebar ── */}
      <FilterSidebar
        filters={filters}
        setFilters={handleSetFilters}
        nicheTagOptions={nicheTagOptions}
        gate0StatusOptions={gate0StatusOptions}
      />

      {/* ── Main Content ── */}
      <div ref={scrollRef} className="flex flex-1 flex-col overflow-y-auto scrollbar-thin">
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-[#E8E4DC] bg-white px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-[#1A1A2E]">
              Channel Discovery
            </h1>
            <p className="mt-0.5 text-sm text-[#6B6B6B]">
              {displayTotal.toLocaleString()} channel{displayTotal !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              loading={refreshing}
              onClick={() => void refetch()}
            >
              <RefreshCw size={14} />
              Refresh
            </Button>
            <Button variant="accent" size="sm" onClick={() => setIntakeOpen(true)}>
              <Plus size={14} />
              Add / Resolve Channels
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 p-6">
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
                onClick={() => setPage((p) => Math.max(1, p - 1))}
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
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Next
                <ChevronRight size={16} />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ── Intake Modal ── */}
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
