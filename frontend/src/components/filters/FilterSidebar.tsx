"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Search, X, ArrowUp, ArrowDown, Check, ChevronDown } from "lucide-react";
import type { CategoryTagOption, ChannelFilters, Gate0Status, Gate0StatusOption } from "@/types";
import { NumericRangeFilter } from "@/components/filters/NumericRangeFilter";
import { cn } from "@/lib/utils";

interface FilterSidebarProps {
  filters: ChannelFilters;
  setFilters: (filters: ChannelFilters) => void;
  categoryTagOptions: CategoryTagOption[];
  categoryTagsLoading?: boolean;
  onCategoryMenuOpen?: () => void;
  gate0StatusOptions?: Gate0StatusOption[];
  gate0StatusesLoading?: boolean;
}

const GATE0_STATUS_CONFIG: Record<
  Gate0Status,
  { label: string; dot: string; activeText: string }
> = {
  clean:        { label: "Clean",        dot: "bg-emerald-500",      activeText: "text-emerald-400" },
  needs_review: { label: "Needs Review", dot: "bg-amber-400",        activeText: "text-amber-300"   },
  dirty:        { label: "Competitor",   dot: "bg-red-500",          activeText: "text-red-400"     },
  pending:      { label: "Pending",      dot: "bg-amber-600/40",     activeText: "text-amber-600/70"},
  unchecked:    { label: "Unchecked",    dot: "bg-[#F7F4EE]/20",     activeText: "text-[#F7F4EE]/50"},
};

const GATE0_STATUS_ORDER: Gate0Status[] = [
  "clean", "needs_review", "dirty", "pending", "unchecked",
];

export const DEFAULT_FILTERS: ChannelFilters = {
  platform: "all",
  comment_tier: "all",
  gate0_statuses: [],
  category_tags: [],
  search_query: null,
  min_subscriber_count: null,
  max_subscriber_count: null,
  min_avg_views: null,
  max_avg_views: null,
  min_avg_comments: null,
  max_avg_comments: null,
  last_active_from: null,
  last_active_to: null,
  inactive_filter: false,
  incomplete_only: false,
  sort_by: "avg_comments",
  sort_order: "desc",
};

const PLATFORMS = [
  { value: "all", label: "All" },
  { value: "rumble", label: "Rumble" },
  { value: "substack", label: "Substack" },
] as const;

const COMMENT_TIERS = [
  { value: "all", label: "All Tiers" },
  { value: "active", label: "Active (10+)" },
  { value: "sweet_spot", label: "Sweet Spot (20-100)" },
  { value: "whale", label: "Whale (100+)" },
] as const;

const SORT_OPTIONS = [
  { value: "avg_comments", label: "Avg Comments" },
  { value: "subscriber_count", label: "Subscribers" },
  { value: "avg_views", label: "Avg Views" },
  { value: "view_velocity_30d", label: "View Velocity 30d" },
  { value: "view_velocity_90d", label: "View Velocity 90d" },
  { value: "last_active_date", label: "Last Active" },
] as const;

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 px-4 py-2">
      <span className="text-[10px] font-semibold uppercase tracking-widest text-[#C9A84C]/60">
        {children}
      </span>
      <div className="h-px flex-1 bg-[#C9A84C]/15" />
    </div>
  );
}

function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-medium uppercase tracking-wide text-[#F7F4EE]/40">
      {children}
    </span>
  );
}

export function FilterSidebar({
  filters,
  setFilters,
  categoryTagOptions,
  categoryTagsLoading = false,
  onCategoryMenuOpen,
  gate0StatusOptions = [],
  gate0StatusesLoading = false,
}: FilterSidebarProps) {
  const [isCategoryMenuOpen, setIsCategoryMenuOpen] = useState<boolean>(false);
  const categoryMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!categoryMenuRef.current?.contains(target)) {
        setIsCategoryMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocumentClick);
    return () => {
      document.removeEventListener("mousedown", onDocumentClick);
    };
  }, []);

  const update = useCallback(
    (partial: Partial<ChannelFilters>): void => {
      setFilters({ ...filters, ...partial });
    },
    [filters, setFilters]
  );

  const activeCount = useMemo(() => {
    let count = 0;
    if (filters.search_query) count++;
    if (filters.platform !== "all") count++;
    if (filters.comment_tier !== "all") count++;
    if (filters.category_tags.length > 0) count++;
    if (filters.min_subscriber_count != null || filters.max_subscriber_count != null) count++;
    if (filters.min_avg_views != null || filters.max_avg_views != null) count++;
    if (filters.min_avg_comments != null || filters.max_avg_comments != null) count++;
    if (filters.last_active_from || filters.last_active_to) count++;
    if (filters.inactive_filter) count++;
    if (filters.incomplete_only) count++;
    if (filters.gate0_statuses.length > 0) count++;
    return count;
  }, [filters]);

  const darkInput =
    "w-full rounded-lg border border-[#F7F4EE]/10 bg-[#F7F4EE]/6 px-3 py-2 text-sm text-[#F7F4EE] placeholder:text-[#F7F4EE]/30 focus:outline-none focus:ring-2 focus:ring-[#C9A84C]/60 transition-shadow";

  const darkSelect =
    "w-full appearance-none rounded-lg border border-[#F7F4EE]/10 bg-[#F7F4EE]/6 px-3 py-2 pr-8 text-sm text-[#F7F4EE] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]/60 transition-shadow cursor-pointer";

  return (
    <aside className="flex w-72 shrink-0 flex-col bg-[#1A1A2E] border-r border-[#F7F4EE]/8 overflow-y-auto scrollbar-thin">
      <div className="flex h-14 shrink-0 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-[#F7F4EE]/70">Filters</span>
          {activeCount > 0 && (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-[#C9A84C] px-1 text-[10px] font-bold text-[#1A1A2E]">
              {activeCount}
            </span>
          )}
        </div>
        {activeCount > 0 && (
          <button
            type="button"
            onClick={() => setFilters(DEFAULT_FILTERS)}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[#F7F4EE]/40 transition-colors hover:bg-[#F7F4EE]/6 hover:text-[#F7F4EE]/70 cursor-pointer"
          >
            <X size={11} />
            Clear
          </button>
        )}
      </div>

      <div className="px-4 pb-4">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#F7F4EE]/30 pointer-events-none" />
          <input
            type="text"
            value={filters.search_query ?? ""}
            onChange={(e) => update({ search_query: e.target.value.trim().length ? e.target.value : null })}
            placeholder="Name, URL, description..."
            className={cn(darkInput, "pl-8")}
          />
        </div>
      </div>

      <SectionLabel>Platform</SectionLabel>
      <div className="flex flex-wrap gap-1.5 px-4 pb-4">
        {PLATFORMS.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() => update({ platform: p.value as ChannelFilters["platform"] })}
            className={cn(
              "rounded-full border px-3 py-1 text-xs font-medium transition-all duration-150 cursor-pointer",
              filters.platform === p.value
                ? "border-[#C9A84C] bg-[#C9A84C]/15 text-[#C9A84C]"
                : "border-[#F7F4EE]/15 text-[#F7F4EE]/50 hover:border-[#F7F4EE]/30 hover:text-[#F7F4EE]/80"
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      <SectionLabel>Comment Tier</SectionLabel>
      <div className="flex flex-col gap-0.5 px-4 pb-4">
        {COMMENT_TIERS.map((t) => {
          const active = filters.comment_tier === t.value;
          return (
            <button
              key={t.value}
              type="button"
              onClick={() => update({ comment_tier: t.value as ChannelFilters["comment_tier"] })}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-all duration-150 cursor-pointer text-left",
                active
                  ? "bg-[#C9A84C]/12 text-[#C9A84C]"
                  : "text-[#F7F4EE]/50 hover:bg-[#F7F4EE]/5 hover:text-[#F7F4EE]/80"
              )}
            >
              <span
                className={cn(
                  "h-3.5 w-3.5 shrink-0 rounded-full border-2 transition-all",
                  active ? "border-[#C9A84C] bg-[#C9A84C]" : "border-[#F7F4EE]/25"
                )}
              />
              {t.label}
            </button>
          );
        })}
      </div>

      <SectionLabel>Competitor Check</SectionLabel>
      <div className="flex flex-col gap-0.5 px-4 pb-4">
        {gate0StatusesLoading && gate0StatusOptions.length === 0 && (
          <p className="px-1 py-2 text-[11px] text-[#F7F4EE]/30">Loading…</p>
        )}
        {GATE0_STATUS_ORDER.map((status) => {
          const cfg = GATE0_STATUS_CONFIG[status];
          const isActive = filters.gate0_statuses.includes(status);
          const option = gate0StatusOptions.find((o) => o.status === status);
          const count = option?.count ?? null;
          return (
            <button
              key={status}
              type="button"
              onClick={() =>
                update({
                  gate0_statuses: isActive
                    ? filters.gate0_statuses.filter((s) => s !== status)
                    : [...filters.gate0_statuses, status],
                })
              }
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-all duration-150 cursor-pointer text-left",
                isActive
                  ? cn("bg-[#F7F4EE]/8", cfg.activeText)
                  : "text-[#F7F4EE]/50 hover:bg-[#F7F4EE]/5 hover:text-[#F7F4EE]/80"
              )}
            >
              <span
                className={cn(
                  "h-2.5 w-2.5 shrink-0 rounded-full transition-all",
                  isActive ? cfg.dot : "bg-[#F7F4EE]/20"
                )}
              />
              <span className="flex-1 leading-none">{cfg.label}</span>
              {count !== null && (
                <span className="shrink-0 rounded-full border border-[#F7F4EE]/12 bg-[#F7F4EE]/5 px-1.5 py-0.5 text-[10px] text-[#F7F4EE]/40">
                  {count.toLocaleString()}
                </span>
              )}
              <span
                className={cn(
                  "ml-auto h-3.5 w-3.5 shrink-0 rounded border-2 transition-all flex items-center justify-center",
                  isActive ? "border-current bg-current/20" : "border-[#F7F4EE]/25"
                )}
              >
                {isActive && (
                  <svg width="8" height="8" viewBox="0 0 10 10" fill="currentColor">
                    <path d="M1.5 5l2.5 2.5 5-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </span>
            </button>
          );
        })}
        {filters.gate0_statuses.length > 0 && (
          <button
            type="button"
            onClick={() => update({ gate0_statuses: [] })}
            className="mt-1 flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] text-[#F7F4EE]/30 transition-colors hover:text-[#F7F4EE]/60 cursor-pointer"
          >
            <X size={10} />
            Clear selection
          </button>
        )}
      </div>

      <SectionLabel>Sort</SectionLabel>
      <div className="flex flex-col gap-3 px-4 pb-4">
        <div className="flex flex-col gap-1">
          <FilterLabel>Sort By</FilterLabel>
          <div className="relative">
            <select
              value={filters.sort_by}
              onChange={(e) => update({ sort_by: e.target.value as ChannelFilters["sort_by"] })}
              className={darkSelect}
            >
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value} className="bg-[#1A1A2E]">
                  {opt.label}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[#F7F4EE]/30">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="m6 9 6 6 6-6" />
              </svg>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <FilterLabel>Order</FilterLabel>
          <div className="flex gap-1.5">
            <button
              type="button"
              onClick={() => update({ sort_order: "desc" })}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-lg border py-2 text-xs font-medium transition-all duration-150 cursor-pointer",
                filters.sort_order === "desc"
                  ? "border-[#C9A84C] bg-[#C9A84C]/15 text-[#C9A84C]"
                  : "border-[#F7F4EE]/15 text-[#F7F4EE]/50 hover:border-[#F7F4EE]/30 hover:text-[#F7F4EE]/80"
              )}
            >
              <ArrowDown size={12} />
              High {"->"} Low
            </button>
            <button
              type="button"
              onClick={() => update({ sort_order: "asc" })}
              className={cn(
                "flex flex-1 items-center justify-center gap-1.5 rounded-lg border py-2 text-xs font-medium transition-all duration-150 cursor-pointer",
                filters.sort_order === "asc"
                  ? "border-[#C9A84C] bg-[#C9A84C]/15 text-[#C9A84C]"
                  : "border-[#F7F4EE]/15 text-[#F7F4EE]/50 hover:border-[#F7F4EE]/30 hover:text-[#F7F4EE]/80"
              )}
            >
              <ArrowUp size={12} />
              Low {"->"} High
            </button>
          </div>
        </div>
      </div>

      <SectionLabel>Advanced</SectionLabel>
      <div className="flex flex-col gap-4 px-4 pb-6">
        <div className="flex flex-col gap-1">
            <FilterLabel>Topic Category</FilterLabel>
            <p className="text-[11px] text-[#F7F4EE]/35">
              Broad, approximate tags. Channels may span multiple categories.
            </p>
            <div className="relative" ref={categoryMenuRef}>
              <button
                type="button"
                onClick={() => {
                  setIsCategoryMenuOpen((prev) => !prev);
                  onCategoryMenuOpen?.();
                }}
                className="flex w-full items-center justify-between rounded-lg border border-[#F7F4EE]/10 bg-[#F7F4EE]/6 px-3 py-2 text-sm text-[#F7F4EE] transition-shadow hover:border-[#F7F4EE]/20 focus:outline-none focus:ring-2 focus:ring-[#C9A84C]/60"
              >
                <span className="truncate">
                  {filters.category_tags.length === 0
                    ? "Any / All Categories"
                    : filters.category_tags.length === 1
                      ? filters.category_tags[0]
                      : `${filters.category_tags.length} categories selected`}
                </span>
                <div className="flex shrink-0 items-center gap-1.5">
                  {categoryTagsLoading && (
                    <span className="h-3 w-3 animate-spin rounded-full border border-[#F7F4EE]/20 border-t-[#C9A84C]/60" />
                  )}
                  <ChevronDown
                    size={14}
                    className={cn("text-[#F7F4EE]/45 transition-transform", isCategoryMenuOpen ? "rotate-180" : "")}
                  />
                </div>
              </button>

              {isCategoryMenuOpen && (
                <div className="absolute z-20 mt-1 w-full rounded-xl border border-[#F7F4EE]/15 bg-[#131323] p-1 shadow-2xl">
                  <button
                    type="button"
                    onClick={() => update({ category_tags: [] })}
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                      filters.category_tags.length === 0
                        ? "bg-[#C9A84C]/14 text-[#C9A84C]"
                        : "text-[#F7F4EE]/75 hover:bg-[#F7F4EE]/6"
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <span className="flex h-4 w-4 items-center justify-center rounded border border-current/35">
                        {filters.category_tags.length === 0 && <Check size={12} />}
                      </span>
                      Any / All Categories
                    </span>
                  </button>

                  <div className="my-1 h-px bg-[#F7F4EE]/10" />

                  <div className="max-h-64 overflow-y-auto scrollbar-thin">
                    {categoryTagsLoading && categoryTagOptions.length === 0 && (
                      <div className="px-2.5 py-3 text-sm text-[#F7F4EE]/45">
                        Loading categories...
                      </div>
                    )}
                    {!categoryTagsLoading && categoryTagOptions.length === 0 && (
                      <div className="px-2.5 py-3 text-sm text-[#F7F4EE]/45">
                        No categories available
                      </div>
                    )}
                    {categoryTagOptions.map((option) => {
                      const isActive = filters.category_tags.includes(option.tag);
                      const isEmpty = option.count === 0 && !isActive;
                      return (
                        <button
                          key={option.tag}
                          type="button"
                          disabled={isEmpty}
                          onClick={() =>
                            update({
                              category_tags: isActive
                                ? filters.category_tags.filter((tag) => tag !== option.tag)
                                : [...filters.category_tags, option.tag],
                            })
                          }
                          className={cn(
                            "flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                            isActive
                              ? "bg-[#C9A84C]/14 text-[#C9A84C]"
                              : isEmpty
                                ? "cursor-not-allowed text-[#F7F4EE]/25"
                                : "text-[#F7F4EE]/75 hover:bg-[#F7F4EE]/6"
                          )}
                        >
                          <span className="flex min-w-0 items-center gap-2">
                            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded border border-current/35">
                              {isActive && <Check size={12} />}
                            </span>
                            <span className="truncate">{option.tag}</span>
                          </span>
                          <span className={cn(
                            "ml-3 shrink-0 rounded-full border px-2 py-0.5 text-[11px]",
                            isEmpty
                              ? "border-[#F7F4EE]/8 bg-transparent text-[#F7F4EE]/25"
                              : "border-[#F7F4EE]/15 bg-[#F7F4EE]/5 text-[#F7F4EE]/60"
                          )}>
                            {option.count.toLocaleString()}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>

        <NumericRangeFilter
          label="Subscribers"
          minLimit={0}
          maxLimit={10_000_000}
          step={1000}
          minValue={filters.min_subscriber_count ?? null}
          maxValue={filters.max_subscriber_count ?? null}
          onChange={({ min, max }) => update({ min_subscriber_count: min, max_subscriber_count: max })}
        />

        <NumericRangeFilter
          label="Avg Views"
          minLimit={0}
          maxLimit={5_000_000}
          step={500}
          minValue={filters.min_avg_views ?? null}
          maxValue={filters.max_avg_views ?? null}
          onChange={({ min, max }) => update({ min_avg_views: min, max_avg_views: max })}
        />

        <NumericRangeFilter
          label="Avg Comments"
          minLimit={0}
          maxLimit={100_000}
          step={10}
          minValue={filters.min_avg_comments ?? null}
          maxValue={filters.max_avg_comments ?? null}
          onChange={({ min, max }) => update({ min_avg_comments: min, max_avg_comments: max })}
        />

        <div className="flex flex-col gap-2">
          <FilterLabel>Last Active</FilterLabel>
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] text-[#F7F4EE]/30">From</span>
              <input
                type="date"
                value={filters.last_active_from ?? ""}
                onChange={(e) => update({ last_active_from: e.target.value || null })}
                className={darkInput}
              />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] text-[#F7F4EE]/30">To</span>
              <input
                type="date"
                value={filters.last_active_to ?? ""}
                onChange={(e) => update({ last_active_to: e.target.value || null })}
                className={darkInput}
              />
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <FilterLabel>Filters</FilterLabel>
          <button
            type="button"
            onClick={() => update({ inactive_filter: !filters.inactive_filter })}
            className={cn(
              "flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm font-medium transition-all duration-150 cursor-pointer",
              filters.inactive_filter
                ? "border-[#B22222]/60 bg-[#B22222]/15 text-[#ff6b6b]"
                : "border-[#F7F4EE]/15 text-[#F7F4EE]/50 hover:border-[#F7F4EE]/30 hover:text-[#F7F4EE]/80"
            )}
          >
            Exclude 90d+ Inactive
            <span
              className={cn(
                "h-4 w-7 rounded-full transition-all duration-200 relative shrink-0",
                filters.inactive_filter ? "bg-[#B22222]/60" : "bg-[#F7F4EE]/15"
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all duration-200",
                  filters.inactive_filter ? "left-3.5" : "left-0.5"
                )}
              />
            </span>
          </button>

          <button
            type="button"
            onClick={() => update({ incomplete_only: !filters.incomplete_only })}
            className={cn(
              "flex w-full items-center justify-between rounded-lg border px-3 py-2 text-sm font-medium transition-all duration-150 cursor-pointer",
              filters.incomplete_only
                ? "border-[#C9A84C]/60 bg-[#C9A84C]/12 text-[#C9A84C]"
                : "border-[#F7F4EE]/15 text-[#F7F4EE]/50 hover:border-[#F7F4EE]/30 hover:text-[#F7F4EE]/80"
            )}
          >
            <span className="flex items-center gap-1.5">
              Incomplete Only
              <span
                title="Shows channels where dashboard data collection is incomplete — these channels failed eligibility checks and may be missing subscriber count, average views, or average comments."
                className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-current text-[10px] font-bold opacity-60"
              >
                ?
              </span>
            </span>
            <span
              className={cn(
                "h-4 w-7 rounded-full transition-all duration-200 relative shrink-0",
                filters.incomplete_only ? "bg-[#C9A84C]/60" : "bg-[#F7F4EE]/15"
              )}
            >
              <span
                className={cn(
                  "absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all duration-200",
                  filters.incomplete_only ? "left-3.5" : "left-0.5"
                )}
              />
            </span>
          </button>
        </div>
      </div>
    </aside>
  );
}
