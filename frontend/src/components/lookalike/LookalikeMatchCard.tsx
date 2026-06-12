/**
 * LookalikeMatchCard — displays a single lookalike match result.
 */
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import type { LookalikeMatch } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { formatNumber, cn } from "@/lib/utils";

interface LookalikeMatchCardProps {
  match: LookalikeMatch;
}

export function LookalikeMatchCard({ match }: LookalikeMatchCardProps) {
  const channel = match.channel;
  const platformBadgeClass = {
    rumble: "bg-[#E8712B]/10 text-[#E8712B]",
    substack: "bg-[#FF6719]/10 text-[#C04A0E]",
  } as const;
  const platformAbbrev = { rumble: "R", substack: "S" } as const;

  return (
    <div className="rounded-2xl border border-[#D8D0BF] bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2.5">
            {channel ? (
              <Link
                href={`/channel/${channel.id}`}
                className="truncate text-lg font-semibold tracking-tight text-[#1A1A2E] transition-colors hover:text-[#C9A84C]"
              >
                {channel.name}
              </Link>
            ) : (
              <span className="text-lg font-semibold tracking-tight text-[#1A1A2E]">
                Unknown Channel
              </span>
            )}

            {channel && (
              <span
                className={cn(
                  "inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.18em]",
                  platformBadgeClass[channel.platform]
                )}
              >
                {platformAbbrev[channel.platform]}
              </span>
            )}
          </div>

          {/* Match Type Badge */}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge
              variant={
                match.match_type === "guest_appearance" ? "info" : "gold"
              }
              className="px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]"
            >
              {match.match_type === "guest_appearance"
                ? "Guest Appearance"
                : "Category Overlap"}
            </Badge>
          </div>

          {/* Match Detail */}
          <p className="mt-3 text-sm leading-6 italic text-[#6B6B6B]">
            {match.match_detail}
          </p>

          {/* Stats */}
          {channel && (
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="inline-flex items-center rounded-full bg-[#FAF8F4] px-3 py-1.5 text-xs text-[#6B6B6B]">
                <span className="font-semibold text-[#0D0D0D]">
                  {formatNumber(channel.subscriber_count)}
                </span>
                <span className="ml-1">subscribers</span>
              </span>
              <span className="inline-flex items-center rounded-full bg-[#FAF8F4] px-3 py-1.5 text-xs text-[#6B6B6B]">
                <span className="font-semibold text-[#0D0D0D]">
                  {formatNumber(channel.avg_comments)}
                </span>
                <span className="ml-1">avg comments</span>
              </span>
            </div>
          )}
        </div>

        {channel && (
          <a
            href={channel.channel_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] p-3 text-[#6B6B6B] transition-colors hover:border-[#C9A84C]/25 hover:bg-[#C9A84C]/10 hover:text-[#1A1A2E]"
          >
            <ExternalLink size={18} />
          </a>
        )}
      </div>
    </div>
  );
}
