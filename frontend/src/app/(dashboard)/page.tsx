/**
 * Dashboard home — main channel discovery table.
 * Server component that fetches initial data and passes to client view.
 */
import type { Metadata } from "next";
import { createClient } from "@/lib/supabase/server";
import { getChannels } from "@/lib/api/backend";
import { ChannelTableView } from "@/components/channels/ChannelTableView";

export const metadata: Metadata = {
  title: "Dashboard — Kontrol_Alt",
  description: "Browse and discover alternative media channels.",
};

export default async function DashboardPage() {
  let initialChannels: Array<Record<string, unknown>> = [];
  let initialTotal = 0;

  try {
    const supabase = await createClient();
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    const result = await getChannels(
      { sort_by: "avg_comments", sort_order: "desc" },
      1,
      25,
      token
    );

    initialChannels = result.data as never[];
    initialTotal = result.total;
  } catch {
    // Backend may not be running — render with empty data
  }

  return (
    <div className="h-full">
      <ChannelTableView
        initialChannels={initialChannels as never[]}
        initialTotal={initialTotal}
      />
    </div>
  );
}
