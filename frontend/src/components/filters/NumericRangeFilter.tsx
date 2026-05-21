/**
 * NumericRangeFilter - dual-thumb range + min/max numeric inputs.
 */
"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface NumericRangeFilterProps {
  label: string;
  minLimit: number;
  maxLimit: number;
  step?: number;
  minValue: number | null;
  maxValue: number | null;
  onChange: (next: { min: number | null; max: number | null }) => void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function NumericRangeFilter({
  label,
  minLimit,
  maxLimit,
  step = 1,
  minValue,
  maxValue,
  onChange,
}: NumericRangeFilterProps) {
  const resolvedMin = useMemo(
    () => (minValue ?? minLimit),
    [minLimit, minValue]
  );
  const resolvedMax = useMemo(
    () => (maxValue ?? maxLimit),
    [maxLimit, maxValue]
  );

  const minPercent = ((resolvedMin - minLimit) / (maxLimit - minLimit)) * 100;
  const maxPercent = ((resolvedMax - minLimit) / (maxLimit - minLimit)) * 100;

  const onMinInputChange = (raw: string): void => {
    if (!raw.trim()) {
      onChange({ min: null, max: maxValue });
      return;
    }
    const numeric = Number(raw);
    if (!Number.isFinite(numeric)) {
      return;
    }
    const clamped = clamp(numeric, minLimit, maxValue ?? maxLimit);
    onChange({ min: clamped, max: maxValue });
  };

  const onMaxInputChange = (raw: string): void => {
    if (!raw.trim()) {
      onChange({ min: minValue, max: null });
      return;
    }
    const numeric = Number(raw);
    if (!Number.isFinite(numeric)) {
      return;
    }
    const clamped = clamp(numeric, minValue ?? minLimit, maxLimit);
    onChange({ min: minValue, max: clamped });
  };

  return (
    <div className="flex min-w-[240px] flex-col gap-2">
      <label className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
        {label}
      </label>

      <div className="relative h-10">
        <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-[#E8E4DC]" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-[#C9A84C]"
          style={{
            left: `${minPercent}%`,
            right: `${100 - maxPercent}%`,
          }}
        />
        <input
          type="range"
          min={minLimit}
          max={maxLimit}
          step={step}
          value={resolvedMin}
          onChange={(event) => {
            const next = clamp(
              Number(event.target.value),
              minLimit,
              maxValue ?? maxLimit
            );
            onChange({ min: next, max: maxValue });
          }}
          className={cn(
            "pointer-events-none absolute left-0 top-1/2 h-1 w-full -translate-y-1/2 appearance-none bg-transparent",
            "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[#1A1A2E] [&::-webkit-slider-thumb]:bg-white",
            "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-[#1A1A2E] [&::-moz-range-thumb]:bg-white"
          )}
          aria-label={`${label} minimum`}
        />
        <input
          type="range"
          min={minLimit}
          max={maxLimit}
          step={step}
          value={resolvedMax}
          onChange={(event) => {
            const next = clamp(
              Number(event.target.value),
              minValue ?? minLimit,
              maxLimit
            );
            onChange({ min: minValue, max: next });
          }}
          className={cn(
            "pointer-events-none absolute left-0 top-1/2 h-1 w-full -translate-y-1/2 appearance-none bg-transparent",
            "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[#1A1A2E] [&::-webkit-slider-thumb]:bg-white",
            "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-[#1A1A2E] [&::-moz-range-thumb]:bg-white"
          )}
          aria-label={`${label} maximum`}
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <input
          type="number"
          min={minLimit}
          max={maxLimit}
          step={step}
          value={minValue ?? ""}
          placeholder="Min"
          onChange={(event) => onMinInputChange(event.target.value)}
          className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
        />
        <input
          type="number"
          min={minLimit}
          max={maxLimit}
          step={step}
          value={maxValue ?? ""}
          placeholder="Max"
          onChange={(event) => onMaxInputChange(event.target.value)}
          className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
        />
      </div>
    </div>
  );
}
