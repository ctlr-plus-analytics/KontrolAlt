/**
 * Input — styled text input with label and error support.
 */
import { cn } from "@/lib/utils";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({
  label,
  error,
  id,
  className,
  ...props
}: InputProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={id}
          className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]"
        >
          {label}
        </label>
      )}
      <input
        id={id}
        className={cn(
          "rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] placeholder:text-[#6B6B6B]/50 focus:outline-none focus:ring-2 focus:ring-[#C9A84C] transition-shadow duration-150",
          error && "border-[#B22222] focus:ring-[#B22222]",
          className
        )}
        {...props}
      />
      {error && (
        <p className="text-xs text-[#B22222]">{error}</p>
      )}
    </div>
  );
}
