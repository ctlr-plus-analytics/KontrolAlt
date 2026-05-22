/**
 * Table — styled table primitives with design system styles.
 */
import { cn } from "@/lib/utils";

/* ─── Table Root ─── */
interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  children: React.ReactNode;
}

export function Table({ children, className, ...props }: TableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[#E8E4DC] bg-white shadow-sm">
      <table className={cn("w-full text-left text-sm", className)} {...props}>
        {children}
      </table>
    </div>
  );
}

/* ─── Table Head (thead) ─── */
export function TableHead({ children }: { children: React.ReactNode }) {
  return <thead className="sticky top-0 z-10 bg-[#1A1A2E] text-white">{children}</thead>;
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
        "px-4 py-3 text-xs font-semibold uppercase tracking-wide whitespace-nowrap",
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
