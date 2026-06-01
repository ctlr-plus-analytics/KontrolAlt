/**
 * ChannelRow - renders a single row in the channel table.
 */
import Link from "next/link";
import type { Channel, VelocityScore } from "@/types";
import { TableRow, TableCell } from "@/components/ui/Table";
import { Gate0Badge } from "@/components/channels/Gate0Badge";
import { formatEngagementRate, formatNumber, timeAgo } from "@/lib/utils";

interface ChannelRowProps {
  channel: Channel & { velocity?: VelocityScore | null };
  index: number;
}

export function ChannelRow({ channel, index }: ChannelRowProps) {
  const primaryCategory = channel.category_tags?.[0] ?? channel.niche_tags?.[0] ?? "Uncategorized";

  return (
    <TableRow index={index}>
      <TableCell>
        <Link
          href={`/channel/${channel.id}`}
          title={channel.name}
          className="block max-w-[12rem] min-w-0 truncate font-medium text-[#1A1A2E] transition-colors hover:text-[#C9A84C] xl:max-w-[18rem]"
        >
          {channel.name}
        </Link>
      </TableCell>

      <TableCell className="max-w-0 truncate capitalize text-[#2E2E2E]">
        {channel.platform}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatNumber(channel.subscriber_count)}
      </TableCell>

      <TableCell className="max-w-0 truncate text-[#2E2E2E]" title={primaryCategory}>
        {primaryCategory}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatNumber(channel.avg_views)}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatNumber(channel.avg_comments)}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatEngagementRate(channel.subscriber_count, channel.avg_views)}
      </TableCell>

      <TableCell>
        <Gate0Badge status={channel.gate0_status} flaggedBrand={channel.gate0_flagged_brand} />
      </TableCell>

      <TableCell className="max-w-0 truncate text-xs text-[#6B6B6B]">
        {timeAgo(channel.updated_at)}
      </TableCell>
    </TableRow>
  );
}
