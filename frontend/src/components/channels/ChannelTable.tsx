/**
 * ChannelTable — displays all discovered channels in a sortable table.
 */
import { Ghost } from "lucide-react";
import type { Channel, ChannelFilters, VelocityScore } from "@/types";
import {
  Table,
  TableHead,
  TableBody,
  TableHeaderCell,
} from "@/components/ui/Table";
import { ChannelRow } from "@/components/channels/ChannelRow";

interface ChannelTableProps {
  channels: (Channel & { velocity?: VelocityScore | null })[];
  sortBy: ChannelFilters["sort_by"];
  sortOrder: ChannelFilters["sort_order"];
  onSort: (column: ChannelFilters["sort_by"]) => void;
}

type SortableColumn = {
  key: ChannelFilters["sort_by"] | null;
  label: string;
  align?: "left" | "right" | "center";
};

const COLUMNS: SortableColumn[] = [
  { key: null, label: "Channel" },
  { key: null, label: "Platform" },
  { key: "subscriber_count", label: "Subscribers", align: "right" },
  { key: null, label: "Niche (Category)" },
  { key: "avg_views", label: "Avg Views", align: "right" },
  { key: "avg_likes", label: "Likes", align: "right" },
  { key: "avg_comments", label: "Avg Comments", align: "right" },
  { key: "engagement_rate", label: "Engagement Rate %", align: "right" },
  { key: "last_active_date", label: "Last Active" },
];

export function ChannelTable({
  channels,
  sortBy,
  sortOrder,
  onSort,
}: ChannelTableProps) {
  if (channels.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-[#E8E4DC] bg-white py-20 shadow-sm">
        <Ghost size={48} className="mb-4 text-[#E8E4DC]" />
        <p className="text-sm font-medium text-[#6B6B6B]">
          No channels found matching your filters
        </p>
        <p className="mt-1 text-xs text-[#6B6B6B]/60">
          Try adjusting your filter criteria
        </p>
      </div>
    );
  }

  return (
    <Table
      className="table-auto"
      containerClassName="max-h-[clamp(360px,calc(100vh-24rem),620px)] overflow-y-auto"
    >
      <TableHead>
        <tr>
          {COLUMNS.map((col) => (
            <TableHeaderCell
              key={col.label}
              sortable={col.key !== null}
              sorted={col.key === sortBy ? sortOrder : null}
              onSort={col.key ? () => onSort(col.key!) : undefined}
              className={
                col.align === "right"
                  ? "text-right"
                  : col.align === "center"
                    ? "text-center"
                    : undefined
              }
            >
              {col.label}
            </TableHeaderCell>
          ))}
        </tr>
      </TableHead>
      <TableBody>
        {channels.map((channel, idx) => (
          <ChannelRow key={channel.id} channel={channel} index={idx} />
        ))}
      </TableBody>
    </Table>
  );
}
