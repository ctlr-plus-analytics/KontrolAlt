/**
 * FilterBar - filtering controls for the channel table.
 */
"use client";

import { SlidersHorizontal, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import type { ChannelFilters } from "@/types";
import { Dropdown } from "@/components/ui/Dropdown";
import { Button } from "@/components/ui/Button";
import { NumericRangeFilter } from "@/components/filters/NumericRangeFilter";
import { cn, formatNumber } from "@/lib/utils";

interface FilterBarProps {
  filters: ChannelFilters;
  setFilters: (filters: ChannelFilters) => void;
  nicheTagOptions: string[];
}

interface ActiveFilter {
  key: string;
  label: string;
  onClear: () => void;
  advanced: boolean;
}

const DEFAULT_FILTERS: ChannelFilters = {
  platform: "all",
  comment_tier: "all",
  gate0_status: "all",
  is_55_plus: null,
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
  include_incomplete: false,
  sort_by: "view_velocity_30d",
  sort_order: "desc",
};

const PLATFORM_OPTIONS = [
  { value: "all", label: "All Platforms" },
  { value: "rumble", label: "Rumble" },
  { value: "bitchute", label: "BitChute" },
];

const TIER_OPTIONS = [
  { value: "all", label: "All Tiers" },
  { value: "active", label: "Active (10+)" },
  { value: "sweet_spot", label: "Sweet Spot (20-100)" },
  { value: "whale", label: "Whale (100+)" },
];

const GATE0_OPTIONS = [
  { value: "all", label: "All" },
  { value: "unchecked", label: "Not Checked" },
  { value: "pending", label: "Checking" },
  { value: "clean", label: "Clean Lead" },
  { value: "dirty", label: "Brand Risk" },
];

const SORT_OPTIONS = [
  { value: "subscriber_count", label: "Subscribers" },
  { value: "avg_views", label: "Avg Views" },
  { value: "avg_comments", label: "Avg Comments" },
  { value: "view_velocity_30d", label: "View Velocity 30d" },
  { value: "view_velocity_90d", label: "View Velocity 90d" },
  { value: "last_active_date", label: "Last Active" },
];

function getOptionLabel(
  options: Array<{ value: string; label: string }>,
  value: string
): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

function formatRangeLabel(
  label: string,
  minValue: number | null | undefined,
  maxValue: number | null | undefined
): string {
  const min = minValue === null || minValue === undefined ? "Any" : formatNumber(minValue);
  const max = maxValue === null || maxValue === undefined ? "Any" : formatNumber(maxValue);
  return `${label}: ${min}-${max}`;
}

export function FilterBar({
  filters,
  setFilters,
  nicheTagOptions,
}: FilterBarProps) {
  const [advancedOpen, setAdvancedOpen] = useState<boolean>(false);

  const update = useCallback(
    (partial: Partial<ChannelFilters>): void => {
      setFilters({ ...filters, ...partial });
    },
    [filters, setFilters]
  );

  const activeFilters = useMemo<ActiveFilter[]>(() => {
    const active: ActiveFilter[] = [];

    if (filters.search_query) {
      active.push({
        key: "search_query",
        label: `Search: ${filters.search_query}`,
        onClear: () => update({ search_query: null }),
        advanced: false,
      });
    }
    if (filters.platform !== "all") {
      active.push({
        key: "platform",
        label: `Platform: ${getOptionLabel(PLATFORM_OPTIONS, filters.platform)}`,
        onClear: () => update({ platform: "all" }),
        advanced: false,
      });
    }
    if (filters.comment_tier !== "all") {
      active.push({
        key: "comment_tier",
        label: `Tier: ${getOptionLabel(TIER_OPTIONS, filters.comment_tier)}`,
        onClear: () => update({ comment_tier: "all" }),
        advanced: false,
      });
    }
    if (filters.gate0_status !== "all") {
      active.push({
        key: "gate0_status",
        label: `Gate 0: ${getOptionLabel(GATE0_OPTIONS, filters.gate0_status)}`,
        onClear: () => update({ gate0_status: "all" }),
        advanced: false,
      });
    }
    if (filters.is_55_plus) {
      active.push({
        key: "is_55_plus",
        label: "55+ Signal",
        onClear: () => update({ is_55_plus: null }),
        advanced: false,
      });
    }
    if (filters.niche_tag) {
      active.push({
        key: "niche_tag",
        label: `Tag: ${filters.niche_tag}`,
        onClear: () => update({ niche_tag: null }),
        advanced: true,
      });
    }
    if (
      filters.min_subscriber_count != null ||
      filters.max_subscriber_count != null
    ) {
      active.push({
        key: "subscriber_range",
        label: formatRangeLabel(
          "Subscribers",
          filters.min_subscriber_count,
          filters.max_subscriber_count
        ),
        onClear: () =>
          update({ min_subscriber_count: null, max_subscriber_count: null }),
        advanced: true,
      });
    }
    if (filters.min_avg_views != null || filters.max_avg_views != null) {
      active.push({
        key: "views_range",
        label: formatRangeLabel(
          "Views",
          filters.min_avg_views,
          filters.max_avg_views
        ),
        onClear: () => update({ min_avg_views: null, max_avg_views: null }),
        advanced: true,
      });
    }
    if (
      filters.min_avg_comments != null ||
      filters.max_avg_comments != null
    ) {
      active.push({
        key: "comments_range",
        label: formatRangeLabel(
          "Comments",
          filters.min_avg_comments,
          filters.max_avg_comments
        ),
        onClear: () =>
          update({ min_avg_comments: null, max_avg_comments: null }),
        advanced: true,
      });
    }
    if (filters.last_active_from || filters.last_active_to) {
      active.push({
        key: "active_range",
        label: `Active: ${filters.last_active_from ?? "Any"}-${filters.last_active_to ?? "Any"}`,
        onClear: () => update({ last_active_from: null, last_active_to: null }),
        advanced: true,
      });
    }
    if (filters.inactive_filter) {
      active.push({
        key: "inactive_filter",
        label: "Inactive 90d+",
        onClear: () => update({ inactive_filter: false }),
        advanced: true,
      });
    }
    if (filters.include_incomplete) {
      active.push({
        key: "include_incomplete",
        label: "Include Incomplete",
        onClear: () => update({ include_incomplete: false }),
        advanced: true,
      });
    }

    return active;
  }, [filters, update]);

  const advancedFilterCount = activeFilters.filter(
    (filter) => filter.advanced
  ).length;

  return (
    <div className="mb-6 rounded-lg border border-[#E8E4DC] bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex min-w-[260px] flex-1 flex-col gap-1.5">
          <label className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            Search
          </label>
          <input
            type="text"
            value={filters.search_query ?? ""}
            onChange={(event) =>
              update({
                search_query: event.target.value.trim().length
                  ? event.target.value
                  : null,
              })
            }
            placeholder="Name, URL, description"
            className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] placeholder:text-[#6B6B6B]/50 focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
          />
        </div>

        <Dropdown
          label="Platform"
          options={PLATFORM_OPTIONS}
          value={filters.platform}
          onChange={(value) =>
            update({ platform: value as ChannelFilters["platform"] })
          }
        />

        <Dropdown
          label="Comment Tier"
          options={TIER_OPTIONS}
          value={filters.comment_tier}
          onChange={(value) =>
            update({ comment_tier: value as ChannelFilters["comment_tier"] })
          }
        />

        <Dropdown
          label="Gate 0 Status"
          options={GATE0_OPTIONS}
          value={filters.gate0_status}
          onChange={(value) =>
            update({ gate0_status: value as ChannelFilters["gate0_status"] })
          }
        />

        <Dropdown
          label="Sort By"
          options={SORT_OPTIONS}
          value={filters.sort_by}
          onChange={(value) =>
            update({ sort_by: value as ChannelFilters["sort_by"] })
          }
        />

        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            55+ Audience
          </span>
          <button
            type="button"
            onClick={() =>
              update({ is_55_plus: filters.is_55_plus ? null : true })
            }
            className={cn(
              "rounded-lg border px-3 py-2 text-sm font-medium transition-all duration-150 cursor-pointer",
              filters.is_55_plus
                ? "border-[#E6A817] bg-[#E6A817]/10 text-[#E6A817]"
                : "border-[#E8E4DC] bg-white text-[#6B6B6B] hover:border-[#C9A84C]"
            )}
          >
            55+
          </button>
        </div>

        <button
          type="button"
          onClick={() => setAdvancedOpen((open) => !open)}
          className={cn(
            "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all duration-150 cursor-pointer",
            advancedOpen || advancedFilterCount > 0
              ? "border-[#C9A84C] bg-[#C9A84C]/10 text-[#1A1A2E]"
              : "border-[#E8E4DC] bg-white text-[#1A1A2E] hover:border-[#C9A84C]"
          )}
          aria-expanded={advancedOpen}
        >
          <SlidersHorizontal size={14} />
          More filters
          {advancedFilterCount > 0 && (
            <span className="rounded-full bg-[#1A1A2E] px-1.5 py-0.5 text-[10px] font-bold text-white">
              {advancedFilterCount}
            </span>
          )}
        </button>

        {activeFilters.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setFilters(DEFAULT_FILTERS)}
          >
            <X size={14} />
            Clear All
          </Button>
        )}
      </div>

      {activeFilters.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {activeFilters.map((filter) => (
            <button
              key={filter.key}
              type="button"
              onClick={filter.onClear}
              className="inline-flex items-center gap-1 rounded-full border border-[#E8E4DC] bg-[#FAF8F4] px-2.5 py-1 text-xs font-medium text-[#1A1A2E] transition-colors hover:border-[#C9A84C]"
              title={`Remove ${filter.label}`}
            >
              {filter.label}
              <X size={12} className="text-[#6B6B6B]" />
            </button>
          ))}
        </div>
      )}

      {advancedOpen && (
        <div className="mt-4 border-t border-[#E8E4DC] pt-4">
          <div className="flex flex-wrap items-end gap-4">
            <Dropdown
              label="Niche Tag"
              options={[
                { value: "all", label: "All Tags" },
                ...nicheTagOptions.map((tag) => ({ value: tag, label: tag })),
              ]}
              value={filters.niche_tag ?? "all"}
              onChange={(value) =>
                update({
                  niche_tag: value === "all" ? null : value,
                })
              }
            />

            <NumericRangeFilter
              label="Subscribers"
              minLimit={0}
              maxLimit={10_000_000}
              step={1000}
              minValue={filters.min_subscriber_count ?? null}
              maxValue={filters.max_subscriber_count ?? null}
              onChange={({ min, max }) =>
                update({
                  min_subscriber_count: min,
                  max_subscriber_count: max,
                })
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
                update({
                  min_avg_views: min,
                  max_avg_views: max,
                })
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
                update({
                  min_avg_comments: min,
                  max_avg_comments: max,
                })
              }
            />

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                Active From
              </label>
              <input
                type="date"
                value={filters.last_active_from ?? ""}
                onChange={(event) =>
                  update({
                    last_active_from: event.target.value || null,
                  })
                }
                className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                Active To
              </label>
              <input
                type="date"
                value={filters.last_active_to ?? ""}
                onChange={(event) =>
                  update({
                    last_active_to: event.target.value || null,
                  })
                }
                className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                Order
              </span>
              <button
                type="button"
                onClick={() =>
                  update({
                    sort_order: filters.sort_order === "asc" ? "desc" : "asc",
                  })
                }
                className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm font-medium text-[#1A1A2E] transition-all duration-150 hover:border-[#C9A84C] cursor-pointer"
              >
                {filters.sort_order === "asc" ? "ASC" : "DESC"}
              </button>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                Inactive
              </span>
              <button
                type="button"
                onClick={() =>
                  update({ inactive_filter: !filters.inactive_filter })
                }
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm font-medium transition-all duration-150 cursor-pointer",
                  filters.inactive_filter
                    ? "border-[#B22222] bg-[#B22222]/10 text-[#B22222]"
                    : "border-[#E8E4DC] bg-white text-[#6B6B6B] hover:border-[#C9A84C]"
                )}
              >
                Only 90d+
              </button>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                Incomplete
              </span>
              <button
                type="button"
                onClick={() =>
                  update({ include_incomplete: !filters.include_incomplete })
                }
                className={cn(
                  "rounded-lg border px-3 py-2 text-sm font-medium transition-all duration-150 cursor-pointer",
                  filters.include_incomplete
                    ? "border-[#1A1A2E] bg-[#1A1A2E]/10 text-[#1A1A2E]"
                    : "border-[#E8E4DC] bg-white text-[#6B6B6B] hover:border-[#C9A84C]"
                )}
              >
                Include
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { DEFAULT_FILTERS };
