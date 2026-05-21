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
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-lg font-medium text-[#1A1A2E]">
          Channel not found
        </p>
        <p className="mt-1 text-sm text-[#6B6B6B]">
          The channel you are looking for does not exist.
        </p>
      </div>
    );
  }

  /* Fetch velocity */
  const { data: velocity } = await supabase
    .from("velocity_scores")
    .select("*")
    .eq("channel_id", id)
    .order("computed_at", { ascending: false })
    .limit(1)
    .single();

  /* Fetch gate0 result */
  const { data: gate0 } = await supabase
    .from("gate0_results")
    .select("*")
    .eq("channel_id", id)
    .order("checked_at", { ascending: false })
    .limit(1)
    .single();

  /* Fetch scrape logs */
  const { data: scrapeLogs } = await supabase
    .from("scrape_logs")
    .select("*")
    .eq("channel_id", id)
    .order("attempted_at", { ascending: false })
    .limit(10);

  return (
    <ChannelDetail
      channel={channel as unknown as Channel}
      velocity={(velocity as unknown as VelocityScore) ?? null}
      gate0={(gate0 as unknown as Gate0Result) ?? null}
      scrapeLogs={(scrapeLogs as unknown as ScrapeLog[]) ?? []}
    />
  );
}
