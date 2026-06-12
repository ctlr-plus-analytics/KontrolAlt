/**
 * NumericRangeFilter - dual-thumb range + min/max numeric inputs.
 */
"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface NumericRangeFilterProps {
  label: string;
  labelExtra?: React.ReactNode;
  minLimit: number;
  maxLimit: number;
  step?: number;
  minValue: number | null;
  maxValue: number | null;
  onChange: (next: { min: number | null; max: number | null }) => void;
  className?: string;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function NumericRangeFilter({
  label,
  labelExtra,
  minLimit,
  maxLimit,
  step = 1,
  minValue,
  maxValue,
  onChange,
  className,
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
    const stripped = raw.replace(/,/g, "");
    if (!stripped.trim()) {
      onChange({ min: null, max: maxValue });
      return;
    }
    const numeric = Number(stripped);
    if (!Number.isFinite(numeric)) {
      return;
    }
    const clamped = clamp(numeric, minLimit, maxValue ?? maxLimit);
    onChange({ min: clamped, max: maxValue });
  };

  const onMaxInputChange = (raw: string): void => {
    const stripped = raw.replace(/,/g, "");
    if (!stripped.trim()) {
      onChange({ min: minValue, max: null });
      return;
    }
    const numeric = Number(stripped);
    if (!Number.isFinite(numeric)) {
      return;
    }
    const clamped = clamp(numeric, minValue ?? minLimit, maxLimit);
    onChange({ min: minValue, max: clamped });
  };

  return (
    <div
      className={cn(
        "flex min-w-[220px] flex-col gap-1.5 rounded-lg border border-[#E8E4DC] bg-[#FCFBF8] p-2.5",
        className
      )}
    >
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">{label}</span>
        {labelExtra}
      </div>

      <div className="flex items-center justify-between text-[10px] font-medium text-[#6B6B6B]">
        <span>{minLimit.toLocaleString()}</span>
        <span>{maxLimit.toLocaleString()}</span>
      </div>

      <div className="relative h-6">
        <div className="absolute left-0 right-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-[#E2DDD2]" />
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
            "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[#1A1A2E] [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-[0_1px_3px_rgba(26,26,46,0.24)]",
            "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-[#1A1A2E] [&::-moz-range-thumb]:bg-white [&::-moz-range-thumb]:shadow-[0_1px_3px_rgba(26,26,46,0.24)]"
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
            "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[#1A1A2E] [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-[0_1px_3px_rgba(26,26,46,0.24)]",
            "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-[#1A1A2E] [&::-moz-range-thumb]:bg-white [&::-moz-range-thumb]:shadow-[0_1px_3px_rgba(26,26,46,0.24)]"
          )}
          aria-label={`${label} maximum`}
        />
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <label className="flex flex-col gap-0.5">
          <span className="text-[11px] font-medium uppercase tracking-wide text-[#7A766F]">
            Min
          </span>
          <input
            type="text"
            inputMode="numeric"
            value={minValue ?? ""}
            placeholder="Any"
            onChange={(event) => onMinInputChange(event.target.value)}
            className="rounded-md border border-[#DDD7CC] bg-white px-2.5 py-1.5 text-sm text-[#0D0D0D] placeholder:text-[#9A948A] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
          />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-[11px] font-medium uppercase tracking-wide text-[#7A766F]">
            Max
          </span>
          <input
            type="text"
            inputMode="numeric"
            value={maxValue ?? ""}
            placeholder="Any"
            onChange={(event) => onMaxInputChange(event.target.value)}
            className="rounded-md border border-[#DDD7CC] bg-white px-2.5 py-1.5 text-sm text-[#0D0D0D] placeholder:text-[#9A948A] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
          />
        </label>
      </div>
    </div>
  );
}
