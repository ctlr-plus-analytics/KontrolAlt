/**
 * Table — styled table primitives with design system styles.
 */
import { cn } from "@/lib/utils";
import type { WheelEvent } from "react";

/* ─── Table Root ─── */
interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  children: React.ReactNode;
  containerClassName?: string;
}

export function Table({
  children,
  className,
  containerClassName,
  ...props
}: TableProps) {
  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    const container = event.currentTarget;
    const { deltaY } = event;
    if (deltaY === 0) return;

    const maxScrollTop = container.scrollHeight - container.clientHeight;
    const atTop = container.scrollTop <= 0;
    const atBottom = container.scrollTop >= maxScrollTop - 1;

    // Keep scrolling inside the table while there is room; otherwise let page scroll.
    if ((deltaY < 0 && !atTop) || (deltaY > 0 && !atBottom)) {
      event.preventDefault();
      container.scrollTop += deltaY;
    }
  };

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-lg border border-[#E8E4DC] bg-white shadow-sm",
        containerClassName
      )}
      onWheel={handleWheel}
    >
      <table className={cn("w-full text-left text-sm", className)} {...props}>
        {children}
      </table>
    </div>
  );
}

/* ─── Table Head (thead) ─── */
export function TableHead({ children }: { children: React.ReactNode }) {
  return <thead className="bg-[#1A1A2E] text-white">{children}</thead>;
}

/* ─── Table Body ─── */
export function TableBody({ children }: { children: React.ReactNode }) {
  return (
    <tbody className="divide-y divide-[#E8E4DC]">{children}</tbody>
  );
}

/* ─── Table Row ─── */
interface TableRowProps extends React.HTMLAttributes<HTMLTableRowElement> {
  children: React.ReactNode;
  index?: number;
}

export function TableRow({ children, index, className, ...props }: TableRowProps) {
  const isEven = index !== undefined ? index % 2 === 0 : false;
  return (
    <tr
      className={cn(
        "transition-colors hover:bg-[#C9A84C]/5",
        isEven ? "bg-white" : "bg-[#FAF8F4]",
        className
      )}
      {...props}
    >
      {children}
    </tr>
  );
}

/* ─── Table Header Cell (th) ─── */
interface TableHeaderCellProps
  extends React.ThHTMLAttributes<HTMLTableCellElement> {
  children: React.ReactNode;
  sortable?: boolean;
  sorted?: "asc" | "desc" | null;
  onSort?: () => void;
}

export function TableHeaderCell({
  children,
  sortable = false,
  sorted = null,
  onSort,
  className,
  ...props
}: TableHeaderCellProps) {
  return (
    <th
      className={cn(
        "sticky top-0 z-20 bg-[#1A1A2E] px-4 py-3 text-xs font-semibold uppercase tracking-wide whitespace-nowrap",
        sortable && "cursor-pointer select-none hover:text-[#C9A84C] transition-colors",
        className
      )}
      onClick={sortable ? onSort : undefined}
      {...props}
    >
      <span className="inline-flex items-center gap-1">
        {children}
        {sortable && sorted === "asc" && <span className="text-[#C9A84C]">↑</span>}
        {sortable && sorted === "desc" && <span className="text-[#C9A84C]">↓</span>}
        {sortable && !sorted && <span className="opacity-30">↕</span>}
      </span>
    </th>
  );
}

/* ─── Table Cell (td) ─── */
export function TableCell({
  children,
  className,
  ...props
}: React.TdHTMLAttributes<HTMLTableCellElement> & {
  children?: React.ReactNode;
}) {
  return (
    <td className={cn("px-4 py-3 align-middle", className)} {...props}>
      {children}
    </td>
  );
}
