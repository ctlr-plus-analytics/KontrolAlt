/**
 * Channel detail page — shows full metrics for a single channel.
 * Server component that fetches data and passes to client ChannelDetail.
 */
import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { ChannelDetail } from "@/components/channels/ChannelDetail";
import type { Channel, VelocityScore, Gate0Result, ScrapeLog } from "@/types";

export const metadata: Metadata = {
  title: "Channel Detail — Kontrol_Alt",
  description:
    "Detailed view of a single channel's metrics and compliance status.",
};

interface ChannelDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function ChannelDetailPage({
  params,
}: ChannelDetailPageProps) {
  const { id } = await params;
  const supabase = await createClient();

  /* Fetch channel */
  const { data: channel } = await supabase
    .from("channels")
    .select("*")
    .eq("id", id)
    .single();

  if (!channel) {
    return (
      <div className="h-full overflow-y-auto p-6 scrollbar-thin">
        <div className="flex flex-col items-center justify-center py-20">
          <p className="text-lg font-medium text-[#1A1A2E]">
            Channel not found
          </p>
          <p className="mt-1 text-sm text-[#6B6B6B]">
            The channel you are looking for does not exist.
          </p>
        </div>
      </div>
    );
  }

  /* Construct velocity from cached flat columns */
  const velocity: VelocityScore | null = channel.velocity_computed_at
    ? {
        id: channel.id,
        channel_id: channel.id,
        computed_at: channel.velocity_computed_at,
        view_velocity_30d: channel.view_velocity_30d,
        view_velocity_90d: channel.view_velocity_90d,
        comment_velocity_30d: channel.comment_velocity_30d,
        comment_velocity_90d: channel.comment_velocity_90d,
      }
    : null;

  /* Construct gate0 from cached flat columns */
  const gate0: Gate0Result | null = channel.gate0_result_id
    ? {
        id: channel.gate0_result_id,
        channel_id: channel.id,
        checked_at: channel.gate0_checked_at,
        search_query: channel.gate0_search_query,
        result_status: channel.gate0_result_status as "clean" | "needs_review" | "dirty",
        flagged_brand: channel.gate0_flagged_brand,
        source_url: channel.gate0_source_url,
        confidence: null,
      }
    : null;

  /* Fetch scrape logs */
  const { data: scrapeLogs } = await supabase
    .from("scrape_logs")
    .select("*")
    .eq("channel_id", id)
    .order("attempted_at", { ascending: false })
    .limit(10);

  return (
    <div className="h-full overflow-y-auto p-6 scrollbar-thin">
      <ChannelDetail
        channel={channel as unknown as Channel}
        velocity={velocity}
        gate0={gate0}
        scrapeLogs={(scrapeLogs as unknown as ScrapeLog[]) ?? []}
      />
    </div>
  );
}
