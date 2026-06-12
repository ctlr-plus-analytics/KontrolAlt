/**
 * Channel detail page — shows full metrics for a single channel.
 * Server component that fetches data and passes to client ChannelDetail.
 */
import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { ChannelDetail } from "@/components/channels/ChannelDetail";
import type { Channel } from "@/types";
import { getChannel, type ChannelDetail as ChannelDetailResponse } from "@/lib/api/backend";

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

  const {
    data: { session },
  } = await supabase.auth.getSession();

  let channelDetail: ChannelDetailResponse | null = null;
  try {
    channelDetail = await getChannel(id, session?.access_token);
  } catch {
    channelDetail = null;
  }

  if (!channelDetail) {
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

  const { velocity, gate0, scrape_logs: scrapeLogs, ...channel } = channelDetail;

  return (
    <div className="h-full overflow-y-auto p-6 scrollbar-thin">
      <ChannelDetail
        channel={channel as Channel}
        velocity={velocity ?? null}
        gate0={gate0 ?? null}
        scrapeLogs={scrapeLogs ?? []}
      />
    </div>
  );
}
