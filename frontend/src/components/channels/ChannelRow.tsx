/**
 * ChannelRow — renders a single row in the channel table.
 */
import Link from "next/link";
import { Eye } from "lucide-react";
import type { Channel, VelocityScore } from "@/types";
import { TableRow, TableCell } from "@/components/ui/Table";
import { VelocityBadge } from "@/components/channels/VelocityBadge";
import { Gate0Badge } from "@/components/channels/Gate0Badge";
import { DemoBadge55 } from "@/components/channels/DemoBadge55";
import { CommentTierBadge } from "@/components/channels/CommentTierBadge";
import { formatNumber, timeAgo, cn } from "@/lib/utils";

interface ChannelRowProps {
  channel: Channel & { velocity?: VelocityScore | null };
  index: number;
}

export function ChannelRow({ channel, index }: ChannelRowProps) {
  return (
    <TableRow index={index}>
      {/* Channel Name */}
      <TableCell>
        <div className="flex min-w-0 items-center gap-2">
          <a
            href={channel.channel_url}
            target="_blank"
            rel="noopener noreferrer"
            title={channel.name}
            className="block max-w-[10rem] min-w-0 truncate font-medium text-[#1A1A2E] transition-colors hover:text-[#C9A84C] lg:max-w-[14rem]"
          >
            {channel.name}
          </a>
          <span
            className={cn(
              "inline-flex h-5 w-5 items-center justify-center rounded text-[10px] font-bold",
              channel.platform === "rumble"
                ? "bg-[#E8712B]/10 text-[#E8712B]"
                : "bg-[#7B3FA0]/10 text-[#7B3FA0]"
            )}
          >
            {channel.platform === "rumble" ? "R" : "B"}
          </span>
          {channel.is_55_plus && <DemoBadge55 />}
        </div>
      </TableCell>

      {/* Platform */}
      <TableCell className="max-w-0 truncate capitalize">{channel.platform}</TableCell>

      {/* Subscribers */}
      <TableCell className="font-mono text-[#0D0D0D]">
        {formatNumber(channel.subscriber_count)}
      </TableCell>

      {/* Avg Views */}
      <TableCell className="font-mono text-[#0D0D0D]">
        {formatNumber(channel.avg_views)}
      </TableCell>

      {/* Avg Comments */}
      <TableCell className="font-mono text-[#0D0D0D]">
        {formatNumber(channel.avg_comments)}
      </TableCell>

      {/* Comment Tier */}
      <TableCell>
        <CommentTierBadge tier={channel.comment_tier} />
      </TableCell>

      {/* View Velocity 30d */}
      <TableCell>
        <VelocityBadge value={channel.velocity?.view_velocity_30d ?? null} />
      </TableCell>

      {/* View Velocity 90d */}
      <TableCell>
        <VelocityBadge value={channel.velocity?.view_velocity_90d ?? null} />
      </TableCell>

      {/* Gate 0 */}
      <TableCell>
        <Gate0Badge status={channel.gate0_status} />
      </TableCell>

      {/* 55+ Signal */}
      <TableCell>
        {channel.is_55_plus ? (
          <DemoBadge55 />
        ) : (
          <span className="text-xs text-[#6B6B6B]">—</span>
        )}
      </TableCell>

      {/* Last Active */}
      <TableCell className="max-w-0 truncate text-xs text-[#6B6B6B]">
        {timeAgo(channel.last_active_date)}
      </TableCell>

      {/* Actions */}
      <TableCell>
        <Link
          href={`/channel/${channel.id}`}
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#6B6B6B] transition-colors hover:bg-[#1A1A2E]/5 hover:text-[#1A1A2E]"
        >
          <Eye size={16} />
        </Link>
      </TableCell>
    </TableRow>
  );
}
