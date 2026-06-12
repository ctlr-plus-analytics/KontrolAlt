"use client";

import { useState, useCallback, useEffect, useRef, useLayoutEffect, useMemo } from "react";
import { ChevronLeft, ChevronRight, Download, RefreshCw } from "lucide-react";
import type { CategoryTagOption, Channel, ChannelFilters, VelocityScore } from "@/types";
import { ChannelTable } from "@/components/channels/ChannelTable";
import { FilterSidebar, DEFAULT_FILTERS } from "@/components/filters/FilterSidebar";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { useChannels } from "@/hooks/useChannels";
import { useAuth } from "@/hooks/useAuth";
import { getCategoryTags, exportChannels } from "@/lib/api/backend";
import { useDashboardTour } from "@/hooks/useTourAutoStart";

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
  useDashboardTour();

  // Keep initial render SSR-stable; restore session state after mount.
  const [filters, setFilters] = useState<ChannelFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState<number>(1);
  const [exporting, setExporting] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);
  const [categoryTagOptions, setCategoryTagOptions] = useState<CategoryTagOption[]>([]);
  const [categoryTagsLoading, setCategoryTagsLoading] = useState<boolean>(false);
  const [categoryTagsLoadedKey, setCategoryTagsLoadedKey] = useState<string | null>(null);
  const { session } = useAuth();
  const token = session?.access_token;
  const categoryTagsScopeFilters = useMemo(
    () => ({
      platform: filters.platform,
      comment_tier: filters.comment_tier,
      affiliation_statuses: filters.affiliation_statuses,
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
      filters.affiliation_statuses,
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
  const hasRestoredSession = useRef(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      const saved = readStorage();
      if (saved.filters) {
        const normalizedFilters: ChannelFilters = {
          ...DEFAULT_FILTERS,
          ...saved.filters,
          category_tags: saved.filters.category_tags ?? saved.filters.niche_tags ?? [],
          affiliation_statuses: [],
        };
        setFilters(normalizedFilters);
      }
      if (saved.page) {
        setPage(saved.page);
      }
      hasRestoredSession.current = true;
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

  // Persist filters + page to sessionStorage whenever they change (skip until session is restored).
  useEffect(() => {
    if (!hasRestoredSession.current) return;
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

  const commitPageInput = useCallback((rawValue: string, inputElement?: HTMLInputElement | null) => {
    const parsed = Number.parseInt(rawValue.trim(), 10);
    if (Number.isNaN(parsed)) {
      if (inputElement) {
        inputElement.value = String(page);
      }
      return;
    }
    const nextPage = Math.min(totalPages, Math.max(1, parsed));
    setPage(nextPage);
    if (inputElement) {
      inputElement.value = String(nextPage);
    }
  }, [page, totalPages]);

  const handleExport = useCallback(async () => {
    if (!token) return;
    setExporting(true);
    try {
      await exportChannels(filters, token, "csv");
    } finally {
      setExporting(false);
    }
  }, [filters, token]);

  const handleExportExcel = useCallback(async () => {
    if (!token) return;
    setExportingExcel(true);
    try {
      await exportChannels(filters, token, "xlsx");
    } finally {
      setExportingExcel(false);
    }
  }, [filters, token]);

  const loadCategoryTags = useCallback(async () => {
    if (!token || categoryTagsLoading || categoryTagsLoadedKey === categoryTagsScopeKey) {
      return;
    }
    setCategoryTagsLoading(true);
    const tagsResult = await getCategoryTags(token, categoryTagsScopeFilters).catch(() => null);
    setCategoryTagOptions(tagsResult ?? []);
    setCategoryTagsLoadedKey(categoryTagsScopeKey);
    setCategoryTagsLoading(false);
  }, [
    categoryTagsLoadedKey,
    categoryTagsLoading,
    categoryTagsScopeFilters,
    categoryTagsScopeKey,
    token,
  ]);

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── Filter Sidebar ── */}
      <FilterSidebar
        filters={filters}
        setFilters={handleSetFilters}
        categoryTagOptions={categoryTagOptions}
        categoryTagsLoading={categoryTagsLoading}
        onCategoryMenuOpen={loadCategoryTags}
      />

      {/* ── Main Content ── */}
      <div ref={scrollRef} className="flex flex-1 flex-col overflow-y-auto scrollbar-thin">
        {/* Header */}
        <div id="tour-table-header" className="flex shrink-0 items-center justify-between gap-4 border-b border-[#E8E4DC] bg-white px-6 py-4">
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
              loading={exporting}
              onClick={() => void handleExport()}
            >
              <Download size={14} />
              Export CSV
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={exportingExcel}
              onClick={() => void handleExportExcel()}
            >
              <Download size={14} />
              Export Excel
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={refreshing}
              onClick={() => void refetch()}
            >
              <RefreshCw size={14} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 p-6">
          <div id="tour-channel-table" className="relative min-h-[400px]">
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
          <div id="tour-pagination" className="mt-4 flex items-center justify-between">
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
              <div className="flex items-center gap-2 rounded-lg border border-[#E8E4DC] bg-white px-3 py-1.5 text-sm font-medium text-[#1A1A2E]">
                <input
                  key={page}
                  type="number"
                  min={1}
                  max={totalPages}
                  step={1}
                  defaultValue={page}
                  onBlur={(event) => commitPageInput(event.currentTarget.value, event.currentTarget)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      commitPageInput(event.currentTarget.value, event.currentTarget);
                    }
                  }}
                  aria-label="Page number"
                  className="w-14 border-0 bg-transparent p-0 text-right text-sm font-medium text-[#1A1A2E] outline-none [appearance:textfield] focus:ring-0 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />
                <span className="text-[#6B6B6B]">/ {totalPages}</span>
              </div>
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
        </div>
      </div>

    </div>
  );
}
