/**
 * FilterBar — filtering controls for the channel table.
 */
"use client";

import { X } from "lucide-react";
import type { ChannelFilters } from "@/types";
import { Dropdown } from "@/components/ui/Dropdown";
import { Button } from "@/components/ui/Button";
import { NumericRangeFilter } from "@/components/filters/NumericRangeFilter";
import { cn } from "@/lib/utils";

interface FilterBarProps {
  filters: ChannelFilters;
  setFilters: (filters: ChannelFilters) => void;
  nicheTagOptions: string[];
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
  { value: "sweet_spot", label: "Sweet Spot (20–100)" },
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

export function FilterBar({
  filters,
  setFilters,
  nicheTagOptions,
}: FilterBarProps) {
  const update = (partial: Partial<ChannelFilters>) => {
    setFilters({ ...filters, ...partial });
  };

  const isFiltered =
    filters.platform !== "all" ||
    filters.comment_tier !== "all" ||
    filters.gate0_status !== "all" ||
    filters.is_55_plus !== null ||
    filters.inactive_filter ||
    Boolean(filters.niche_tag) ||
    Boolean(filters.search_query) ||
    filters.min_subscriber_count !== null ||
    filters.max_subscriber_count !== null ||
    filters.min_avg_views !== null ||
    filters.max_avg_views !== null ||
    filters.min_avg_comments !== null ||
    filters.max_avg_comments !== null ||
    Boolean(filters.last_active_from) ||
    Boolean(filters.last_active_to);

  return (
    <div className="mb-6 rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-[220px] flex-col gap-1.5">
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
          onChange={(v) =>
            update({ platform: v as ChannelFilters["platform"] })
          }
        />

        <Dropdown
          label="Comment Tier"
          options={TIER_OPTIONS}
          value={filters.comment_tier}
          onChange={(v) =>
            update({ comment_tier: v as ChannelFilters["comment_tier"] })
          }
        />

        <Dropdown
          label="Gate 0 Status"
          options={GATE0_OPTIONS}
          value={filters.gate0_status}
          onChange={(v) =>
            update({ gate0_status: v as ChannelFilters["gate0_status"] })
          }
        />

        <Dropdown
          label="Sort By"
          options={SORT_OPTIONS}
          value={filters.sort_by}
          onChange={(v) =>
            update({ sort_by: v as ChannelFilters["sort_by"] })
          }
        />

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

        {/* 55+ Toggle */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            55+ Audience
          </span>
          <button
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

        {/* Sort Order Toggle */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            Order
          </span>
          <button
            onClick={() =>
              update({
                sort_order: filters.sort_order === "asc" ? "desc" : "asc",
              })
            }
            className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm font-medium text-[#1A1A2E] transition-all duration-150 hover:border-[#C9A84C] cursor-pointer"
          >
            {filters.sort_order === "asc" ? "↑ ASC" : "↓ DESC"}
          </button>
        </div>

        {/* Inactive Toggle */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            Inactive
          </span>
          <button
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

        {/* Clear Filters */}
        {isFiltered && (
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
    </div>
  );
}

export { DEFAULT_FILTERS };
