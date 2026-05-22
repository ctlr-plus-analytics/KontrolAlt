/**
 * ChannelRow - renders a single row in the channel table.
 */
import Link from "next/link";
import { Eye } from "lucide-react";
import type { Channel, VelocityScore } from "@/types";
import { TableRow, TableCell } from "@/components/ui/Table";
import { VelocityBadge } from "@/components/channels/VelocityBadge";
import { Gate0Badge } from "@/components/channels/Gate0Badge";
import { DemoBadge55 } from "@/components/channels/DemoBadge55";
import { CommentTierBadge } from "@/components/channels/CommentTierBadge";
import { formatNumber, timeAgo } from "@/lib/utils";

interface ChannelRowProps {
  channel: Channel & { velocity?: VelocityScore | null };
  index: number;
}

export function ChannelRow({ channel, index }: ChannelRowProps) {
  return (
    <TableRow index={index}>
      <TableCell>
        <a
          href={channel.channel_url}
          target="_blank"
          rel="noopener noreferrer"
          title={channel.name}
          className="block max-w-[12rem] min-w-0 truncate font-medium text-[#1A1A2E] transition-colors hover:text-[#C9A84C] xl:max-w-[18rem]"
        >
          {channel.name}
        </a>
      </TableCell>

      <TableCell className="max-w-0 truncate capitalize text-[#2E2E2E]">
        {channel.platform}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatNumber(channel.avg_comments)}
      </TableCell>

      <TableCell>
        <CommentTierBadge tier={channel.comment_tier} />
      </TableCell>

      <TableCell className="text-right">
        <VelocityBadge value={channel.velocity?.view_velocity_30d ?? null} />
      </TableCell>

      <TableCell className="text-right">
        <VelocityBadge value={channel.velocity?.view_velocity_90d ?? null} />
      </TableCell>

      <TableCell>
        <Gate0Badge status={channel.gate0_status} />
      </TableCell>

      <TableCell className="text-center">
        {channel.is_55_plus ? (
          <DemoBadge55 />
        ) : (
          <span className="text-xs text-[#6B6B6B]">-</span>
        )}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatNumber(channel.subscriber_count)}
      </TableCell>

      <TableCell className="text-right font-mono text-[#0D0D0D]">
        {formatNumber(channel.avg_views)}
      </TableCell>

      <TableCell className="max-w-0 truncate text-xs text-[#6B6B6B]">
        {timeAgo(channel.last_active_date)}
      </TableCell>

      <TableCell className="text-center">
        <Link
          href={`/channel/${channel.id}`}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#6B6B6B] transition-colors hover:bg-[#1A1A2E]/5 hover:text-[#1A1A2E]"
          aria-label={`View ${channel.name}`}
        >
          <Eye size={16} />
        </Link>
      </TableCell>
    </TableRow>
  );
}
