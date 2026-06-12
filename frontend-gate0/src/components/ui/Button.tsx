/**
 * Button — reusable button primitive with loading state.
 */
import { cn } from "@/lib/utils";
import { Spinner } from "@/components/ui/Spinner";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "accent" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
}

const BASE_CLASSES =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-[#C9A84C]/50 focus:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none cursor-pointer";

const VARIANT_CLASSES: Record<NonNullable<ButtonProps["variant"]>, string> = {
  primary: "bg-[#1A1A2E] text-white hover:bg-[#2A2A3E]",
  accent: "bg-[#C9A84C] text-white hover:bg-[#B8953E]",
  ghost: "bg-transparent text-[#1A1A2E] hover:bg-[#1A1A2E]/5",
  danger: "bg-[#B22222] text-white hover:bg-[#B22222]/90",
};

const SIZE_CLASSES: Record<NonNullable<ButtonProps["size"]>, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        BASE_CLASSES,
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        loading && "pointer-events-none",
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  );
}
