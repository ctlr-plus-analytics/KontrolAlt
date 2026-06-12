/**
 * Badge — small status pill label.
 */
import { cn } from "@/lib/utils";

interface BadgeProps {
  variant?: "success" | "danger" | "warning" | "info" | "muted" | "gold" | "navy" | "purple";
  children: React.ReactNode;
  className?: string;
}

const VARIANT_CLASSES: Record<NonNullable<BadgeProps["variant"]>, string> = {
  success: "bg-[#2E7D32]/10 text-[#2E7D32]",
  danger: "bg-[#B22222]/10 text-[#B22222]",
  warning: "bg-[#E6A817]/10 text-[#E6A817]",
  info: "bg-[#1A1A2E]/10 text-[#1A1A2E]",
  muted: "bg-[#E8E4DC] text-[#6B6B6B]",
  gold: "bg-[#C9A84C]/10 text-[#C9A84C]",
  navy: "bg-[#1A1A2E] text-[#F7F4EE]",
  purple: "bg-[#7B3FA0]/10 text-[#7B3FA0]",
};

export function Badge({
  variant = "muted",
  children,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        VARIANT_CLASSES[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
