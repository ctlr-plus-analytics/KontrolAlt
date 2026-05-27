"use client";

import { useCallback, useMemo } from "react";
import { Search, X, ArrowUp, ArrowDown } from "lucide-react";
import type { ChannelFilters } from "@/types";
import { NumericRangeFilter } from "@/components/filters/NumericRangeFilter";
import { cn } from "@/lib/utils";

interface FilterSidebarProps {
  filters: ChannelFilters;
  setFilters: (filters: ChannelFilters) => void;
  nicheTagOptions: string[];
}

export const DEFAULT_FILTERS: ChannelFilters = {
  platform: "all",
  comment_tier: "all",
  gate0_status: "all",
  niche_tag: null,
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
  { value: "bitchute", label: "BitChute" },
  { value: "substack", label: "Substack" },
] as const;

const COMMENT_TIERS = [
  { value: "all", label: "All Tiers" },
  { value: "active", label: "Active (10+)" },
  { value: "sweet_spot", label: "Sweet Spot (20–100)" },
  { value: "whale", label: "Whale (100+)" },
] as const;

const GATE0_OPTIONS = [
  { value: "all", label: "All Statuses" },
  { value: "unchecked", label: "Not Checked" },
  { value: "pending", label: "Checking" },
  { value: "clean", label: "Clean Lead" },
  { value: "dirty", label: "Gold Dirty" },
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
  nicheTagOptions,
}: FilterSidebarProps) {
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
    if (filters.gate0_status !== "all") count++;
    if (filters.niche_tag) count++;
    if (filters.min_subscriber_count != null || filters.max_subscriber_count != null) count++;
    if (filters.min_avg_views != null || filters.max_avg_views != null) count++;
    if (filters.min_avg_comments != null || filters.max_avg_comments != null) count++;
    if (filters.last_active_from || filters.last_active_to) count++;
    if (filters.inactive_filter) count++;
    if (filters.incomplete_only) count++;
    return count;
  }, [filters]);

  const darkInput =
    "w-full rounded-lg border border-[#F7F4EE]/10 bg-[#F7F4EE]/6 px-3 py-2 text-sm text-[#F7F4EE] placeholder:text-[#F7F4EE]/30 focus:outline-none focus:ring-2 focus:ring-[#C9A84C]/60 transition-shadow";

  const darkSelect =
    "w-full appearance-none rounded-lg border border-[#F7F4EE]/10 bg-[#F7F4EE]/6 px-3 py-2 pr-8 text-sm text-[#F7F4EE] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]/60 transition-shadow cursor-pointer";

  return (
    <aside className="flex w-72 shrink-0 flex-col bg-[#1A1A2E] border-r border-[#F7F4EE]/8 overflow-y-auto scrollbar-thin">

      {/* ── Header ── */}
      <div className="flex h-14 shrink-0 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-[#F7F4EE]/70">
            Filters
          </span>
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

      {/* ── Search ── */}
      <div className="px-4 pb-4">
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[#F7F4EE]/30 pointer-events-none"
          />
          <input
            type="text"
            value={filters.search_query ?? ""}
            onChange={(e) =>
              update({
                search_query: e.target.value.trim().length
                  ? e.target.value
                  : null,
              })
            }
            placeholder="Name, URL, description…"
            className={cn(darkInput, "pl-8")}
          />
        </div>
      </div>

      {/* ── Platform ── */}
      <SectionLabel>Platform</SectionLabel>
      <div className="flex flex-wrap gap-1.5 px-4 pb-4">
        {PLATFORMS.map((p) => (
          <button
            key={p.value}
            type="button"
            onClick={() =>
              update({ platform: p.value as ChannelFilters["platform"] })
            }
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

      {/* ── Comment Tier ── */}
      <SectionLabel>Comment Tier</SectionLabel>
      <div className="flex flex-col gap-0.5 px-4 pb-4">
        {COMMENT_TIERS.map((t) => {
          const active = filters.comment_tier === t.value;
          return (
            <button
              key={t.value}
              type="button"
              onClick={() =>
                update({
                  comment_tier: t.value as ChannelFilters["comment_tier"],
                })
              }
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
                  active
                    ? "border-[#C9A84C] bg-[#C9A84C]"
                    : "border-[#F7F4EE]/25"
                )}
              />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* ── Gate 0 Status ── */}
      <SectionLabel>Gate 0 Status</SectionLabel>
      <div className="flex flex-col gap-0.5 px-4 pb-4">
        {GATE0_OPTIONS.map((g) => {
          const active = filters.gate0_status === g.value;
          return (
            <button
              key={g.value}
              type="button"
              onClick={() =>
                update({
                  gate0_status: g.value as ChannelFilters["gate0_status"],
                })
              }
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
                  active
                    ? "border-[#C9A84C] bg-[#C9A84C]"
                    : "border-[#F7F4EE]/25"
                )}
              />
              {g.label}
            </button>
          );
        })}
      </div>

      {/* ── Sort ── */}
      <SectionLabel>Sort</SectionLabel>
      <div className="flex flex-col gap-3 px-4 pb-4">
        <div className="flex flex-col gap-1">
          <FilterLabel>Sort By</FilterLabel>
          <div className="relative">
            <select
              value={filters.sort_by}
              onChange={(e) =>
                update({ sort_by: e.target.value as ChannelFilters["sort_by"] })
              }
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
              High → Low
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
              Low → High
            </button>
          </div>
        </div>
      </div>

      {/* ── Advanced ── */}
      <SectionLabel>Advanced</SectionLabel>
      <div className="flex flex-col gap-4 px-4 pb-6">

        {/* Niche Tag */}
        {nicheTagOptions.length > 0 && (
          <div className="flex flex-col gap-1">
            <FilterLabel>Niche Tag</FilterLabel>
            <div className="relative">
              <select
                value={filters.niche_tag ?? "all"}
                onChange={(e) =>
                  update({ niche_tag: e.target.value === "all" ? null : e.target.value })
                }
                className={darkSelect}
              >
                <option value="all" className="bg-[#1A1A2E]">All Tags</option>
                {nicheTagOptions.map((tag) => (
                  <option key={tag} value={tag} className="bg-[#1A1A2E]">
                    {tag}
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
        )}

        {/* Numeric ranges */}
        <NumericRangeFilter
          label="Subscribers"
          minLimit={0}
          maxLimit={10_000_000}
          step={1000}
          minValue={filters.min_subscriber_count ?? null}
          maxValue={filters.max_subscriber_count ?? null}
          onChange={({ min, max }) =>
            update({ min_subscriber_count: min, max_subscriber_count: max })
          }
        />

        <NumericRangeFilter
          label="Avg Views"
          minLimit={0}
          maxLimit={5_000_000}
          step={500}
          minValue={filters.min_avg_views ?? null}
          maxValue={filters.max_avg_views ?? null}
          onChange={({ min, max }) =>
            update({ min_avg_views: min, max_avg_views: max })
          }
        />

        <NumericRangeFilter
          label="Avg Comments"
          minLimit={0}
          maxLimit={100_000}
          step={10}
          minValue={filters.min_avg_comments ?? null}
          maxValue={filters.max_avg_comments ?? null}
          onChange={({ min, max }) =>
            update({ min_avg_comments: min, max_avg_comments: max })
          }
        />

        {/* Date range */}
        <div className="flex flex-col gap-2">
          <FilterLabel>Last Active</FilterLabel>
          <div className="flex flex-col gap-1.5">
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] text-[#F7F4EE]/30">From</span>
              <input
                type="date"
                value={filters.last_active_from ?? ""}
                onChange={(e) =>
                  update({ last_active_from: e.target.value || null })
                }
                className={darkInput}
              />
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-[10px] text-[#F7F4EE]/30">To</span>
              <input
                type="date"
                value={filters.last_active_to ?? ""}
                onChange={(e) =>
                  update({ last_active_to: e.target.value || null })
                }
                className={darkInput}
              />
            </div>
          </div>
        </div>

        {/* Toggles */}
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
            Incomplete Only
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
