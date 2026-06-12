/**
 * VelocityBadge — displays a velocity percentage with directional arrow.
 */
import { cn } from "@/lib/utils";

interface VelocityBadgeProps {
  value: number | null;
  label?: string;
}

export function VelocityBadge({ value }: VelocityBadgeProps) {
  if (value === null || value === undefined) {
    return <span className="text-sm text-[#6B6B6B]">N/A — building history</span>;
  }

  if (value === 0) {
    return <span className="font-mono text-sm text-[#6B6B6B]">0.0%</span>;
  }

  const isPositive = value > 0;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono text-sm font-medium",
        isPositive ? "text-[#2E7D32]" : "text-[#B22222]"
      )}
    >
      {isPositive ? "▲" : "▼"}
      {" "}
      {Math.abs(value).toFixed(1)}%
    </span>
  );
}
