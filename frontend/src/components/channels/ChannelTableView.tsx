"use client";

import { useState, useCallback, useEffect, useRef, useLayoutEffect, useMemo } from "react";
import { ChevronLeft, ChevronRight, Plus, RefreshCw, X } from "lucide-react";
import type { CategoryTagOption, Channel, ChannelFilters, VelocityScore } from "@/types";
import { ChannelTable } from "@/components/channels/ChannelTable";
import { ChannelIntakePanel } from "@/components/channels/ChannelIntakePanel";
import { FilterSidebar, DEFAULT_FILTERS } from "@/components/filters/FilterSidebar";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useChannels } from "@/hooks/useChannels";
import { useAuth } from "@/hooks/useAuth";
import { getCategoryTags } from "@/lib/api/backend";

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
  // Keep initial render SSR-stable; restore session state after mount.
  const [filters, setFilters] = useState<ChannelFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState<number>(1);
  const [intakeOpen, setIntakeOpen] = useState<boolean>(false);
  const [categoryTagOptions, setCategoryTagOptions] = useState<CategoryTagOption[]>([]);
  const [categoryTagsLoading, setCategoryTagsLoading] = useState<boolean>(false);
  const { session } = useAuth();
  const categoryTagsScopeFilters = useMemo(
    () => ({
      platform: filters.platform,
      comment_tier: filters.comment_tier,
      gate0_statuses: filters.gate0_statuses,
      search_query: filters.search_query,
      min_subscriber_count: filters.min_subscriber_count,
      max_subscriber_count: filters.max_subscriber_count,
      min_avg_views: filters.min_avg_views,
      max_avg_views: filters.max_avg_views,
      min_avg_comments: filters.min_avg_comments,
      max_avg_comments: filters.max_avg_comments,
      last_active_from: filters.last_active_from,
      last_active_to: filters.last_active_to,
      inactive_filter: filters.inactive_filter,
      incomplete_only: filters.incomplete_only,
    }),
    [
      filters.platform,
      filters.comment_tier,
      filters.gate0_statuses,
      filters.search_query,
      filters.min_subscriber_count,
      filters.max_subscriber_count,
      filters.min_avg_views,
      filters.max_avg_views,
      filters.min_avg_comments,
      filters.max_avg_comments,
      filters.last_active_from,
      filters.last_active_to,
      filters.inactive_filter,
      filters.incomplete_only,
    ]
  );
  const categoryTagsScopeKey = useMemo(
    () => JSON.stringify(categoryTagsScopeFilters),
    [categoryTagsScopeFilters]
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  const hasRestoredScroll = useRef(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      const saved = readStorage();
      if (saved.filters) {
        const normalizedFilters: ChannelFilters = {
          ...saved.filters,
          category_tags: saved.filters.category_tags ?? saved.filters.niche_tags ?? [],
        };
        setFilters(normalizedFilters);
      }
      if (saved.page) {
        setPage(saved.page);
      }
    }, 0);
    return () => clearTimeout(timer);
  }, []);

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
    const node = scrollRef.current;
    return () => {
      if (node) {
        writeStorage({ scrollTop: node.scrollTop });
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

  // Re-fetch category tag counts whenever filters change so counts reflect
  // the current filtered dataset (category_tags itself is excluded server-side).
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (!cancelled) {
        setCategoryTagsLoading(true);
      }
      const tagsResult = await getCategoryTags(session?.access_token, categoryTagsScopeFilters).catch(() => null);
      if (!cancelled) {
        setCategoryTagOptions(tagsResult ?? []);
        setCategoryTagsLoading(false);
      }
    }, 300);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [session?.access_token, categoryTagsScopeKey, categoryTagsScopeFilters]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Filter Sidebar ── */}
      <FilterSidebar
        filters={filters}
        setFilters={handleSetFilters}
        categoryTagOptions={categoryTagOptions}
        categoryTagsLoading={categoryTagsLoading}
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
