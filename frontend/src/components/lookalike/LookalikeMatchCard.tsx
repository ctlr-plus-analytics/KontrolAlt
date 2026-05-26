/**
 * LookalikeMatchCard — displays a single lookalike match result.
 */
import Link from "next/link";
import { ExternalLink } from "lucide-react";
import type { LookalikeMatch } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Gate0Badge } from "@/components/channels/Gate0Badge";
import { DemoBadge55 } from "@/components/channels/DemoBadge55";
import { formatNumber, cn } from "@/lib/utils";

interface LookalikeMatchCardProps {
  match: LookalikeMatch;
}

export function LookalikeMatchCard({ match }: LookalikeMatchCardProps) {
  const channel = match.channel;
  const platformBadgeClass = {
    rumble: "bg-[#E8712B]/10 text-[#E8712B]",
    bitchute: "bg-[#7B3FA0]/10 text-[#7B3FA0]",
    substack: "bg-[#FF6719]/10 text-[#C04A0E]",
  } as const;
  const platformAbbrev = { rumble: "R", bitchute: "B", substack: "S" } as const;

  return (
    <div className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {channel ? (
              <Link
                href={`/channel/${channel.id}`}
                className="font-medium text-[#1A1A2E] hover:text-[#C9A84C] transition-colors truncate"
              >
                {channel.name}
              </Link>
            ) : (
              <span className="font-medium text-[#1A1A2E]">
                Unknown Channel
              </span>
            )}

            {channel && (
              <span
                className={cn(
                  "inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[10px] font-bold",
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
            >
              {match.match_type === "guest_appearance"
                ? "Guest Appearance"
                : "Niche Overlap"}
            </Badge>
            {channel?.gate0_status && (
              <Gate0Badge status={channel.gate0_status} />
            )}
            {channel?.is_55_plus && <DemoBadge55 />}
          </div>

          {/* Match Detail */}
          <p className="mt-2 text-xs italic text-[#6B6B6B]">
            {match.match_detail}
          </p>

          {/* Stats */}
          {channel && (
            <div className="mt-3 flex gap-4 text-xs text-[#6B6B6B]">
              <span>
                <span className="font-medium text-[#0D0D0D]">
                  {formatNumber(channel.subscriber_count)}
                </span>{" "}
                subscribers
              </span>
              <span>
                <span className="font-medium text-[#0D0D0D]">
                  {formatNumber(channel.avg_comments)}
                </span>{" "}
                avg comments
              </span>
            </div>
          )}
        </div>

        {channel && (
          <a
            href={channel.channel_url}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 rounded-lg p-2 text-[#6B6B6B] transition-colors hover:bg-[#1A1A2E]/5 hover:text-[#1A1A2E]"
          >
            <ExternalLink size={16} />
          </a>
        )}
      </div>
    </div>
  );
}
