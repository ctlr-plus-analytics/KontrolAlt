/**
 * ChannelDetail — full detail view for a single channel.
 */
"use client";

import { useMemo, useState } from "react";
import {
  ExternalLink,
  Shield,
  Link as LinkIcon,
  Tag,
  History,
  RefreshCw,
} from "lucide-react";
import type { Channel, VelocityScore, Gate0Result, ScrapeLog } from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Gate0Badge } from "@/components/channels/Gate0Badge";
import { DemoBadge55 } from "@/components/channels/DemoBadge55";
import { VelocityBadge } from "@/components/channels/VelocityBadge";
import { formatNumber, timeAgo, cn } from "@/lib/utils";
import { triggerGate0Check } from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import { useRealtimeRefresh } from "@/hooks/useRealtimeRefresh";
import { useRouter } from "next/navigation";

interface ChannelDetailProps {
  channel: Channel;
  velocity: VelocityScore | null;
  gate0: Gate0Result | null;
  scrapeLogs: ScrapeLog[];
}

export function ChannelDetail({
  channel,
  velocity: initialVelocity,
  gate0: initialGate0,
  scrapeLogs,
}: ChannelDetailProps) {
  const router = useRouter();
  const { session } = useAuth();
  const [gate0Loading, setGate0Loading] = useState(false);
  const [gate0Error, setGate0Error] = useState<string | null>(null);

  const velocity = initialVelocity;
  const gate0Result = initialGate0;
  const gate0Status = channel.gate0_status;
  const realtimeTables = useMemo(
    () => [
      { table: "channels", filter: `id=eq.${channel.id}` },
      { table: "velocity_scores", filter: `channel_id=eq.${channel.id}` },
      { table: "gate0_results", filter: `channel_id=eq.${channel.id}` },
      { table: "scrape_logs", filter: `channel_id=eq.${channel.id}` },
    ],
    [channel.id]
  );

  useRealtimeRefresh({
    channelKey: `channel-detail-${channel.id}`,
    tables: realtimeTables,
    enabled: Boolean(session?.access_token),
    onRefresh: () => router.refresh(),
  });

  const handleGate0Check = async () => {
    setGate0Loading(true);
    setGate0Error(null);
    try {
      await triggerGate0Check(
        channel.id,
        session?.access_token ?? undefined
      );
    } catch (err) {
      setGate0Error(
        err instanceof Error ? err.message : "Failed to queue Gate 0 check"
      );
    } finally {
      setGate0Loading(false);
    }
  };

  const velocityMetrics = [
    {
      label: "View Velocity — 30 Day",
      value: velocity?.view_velocity_30d ?? null,
    },
    {
      label: "View Velocity — 90 Day",
      value: velocity?.view_velocity_90d ?? null,
    },
    {
      label: "Comment Velocity — 30 Day",
      value: velocity?.comment_velocity_30d ?? null,
    },
    {
      label: "Comment Velocity — 90 Day",
      value: velocity?.comment_velocity_90d ?? null,
    },
  ];

  const statusBadgeConfig: Record<string, "success" | "warning" | "danger" | "muted"> = {
    success: "success",
    blocked: "warning",
    retry: "warning",
    failed: "danger",
  };

  return (
    <div className="space-y-6">
      {/* ─── Header Section ─── */}
      <div className="rounded-xl border border-[#E8E4DC] bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-[#1A1A2E]">
                {channel.name}
              </h1>
              <span
                className={cn(
                  "inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-bold",
                  channel.platform === "rumble"
                    ? "bg-[#E8712B]/10 text-[#E8712B]"
                    : "bg-[#7B3FA0]/10 text-[#7B3FA0]"
                )}
              >
                {channel.platform === "rumble" ? "Rumble" : "BitChute"}
              </span>
              {channel.is_55_plus && <DemoBadge55 />}
            </div>

            {/* Stat Pills */}
            <div className="mt-4 flex flex-wrap gap-3">
              <StatPill label="Subscribers" value={formatNumber(channel.subscriber_count)} />
              <StatPill label="Avg Views" value={formatNumber(channel.avg_views)} />
              <StatPill label="Avg Comments" value={formatNumber(channel.avg_comments)} />
              <StatPill
                label="Posts/Week"
                value={
                  channel.posts_per_week === null
                    ? "N/A"
                    : String(channel.posts_per_week)
                }
              />
              <StatPill label="Last Active" value={timeAgo(channel.last_active_date)} />
            </div>
          </div>

          <div className="flex flex-col items-end gap-3">
            <Gate0Badge status={gate0Status} />
            <div className="flex gap-2">
              <a
                href={channel.channel_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button variant="primary" size="sm">
                  <ExternalLink size={14} />
                  Visit Channel
                </Button>
              </a>
              <Button
                variant="accent"
                size="sm"
                loading={gate0Loading}
                onClick={handleGate0Check}
              >
                <Shield size={14} />
                Run Gate 0 Check
              </Button>
            </div>
            {gate0Error && (
              <p className="max-w-xs text-right text-xs text-[#B22222]">
                {gate0Error}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ─── Velocity Section ─── */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <RefreshCw size={18} className="text-[#C9A84C]" />
          Growth Velocity
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {velocityMetrics.map((metric) => (
            <div
              key={metric.label}
              className="rounded-xl border border-[#E8E4DC] bg-white p-5 shadow-sm"
            >
              <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                {metric.label}
              </p>
              {metric.value !== null ? (
                <div className="mt-2">
                  <VelocityBadge value={metric.value} />
                  <p className="mt-1 text-xs text-[#6B6B6B]">vs prior period</p>
                </div>
              ) : (
                <p className="mt-2 text-sm text-[#6B6B6B]">
                  Insufficient Data — collecting history
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ─── Contact & Links ─── */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <LinkIcon size={18} className="text-[#C9A84C]" />
          Contact &amp; Links
        </h2>
        <div className="rounded-xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
          {channel.contact_info.length === 0 &&
          channel.secondary_urls.length === 0 ? (
            <p className="text-sm text-[#6B6B6B]">
              No contact information found
            </p>
          ) : (
            <div className="space-y-2">
              {channel.contact_info.map((info, idx) => (
                <a
                  key={`contact-${idx}`}
                  href={info.startsWith("http") ? info : `mailto:${info}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-[#1A1A2E] hover:text-[#C9A84C] transition-colors"
                >
                  <ExternalLink size={12} className="text-[#6B6B6B]" />
                  {info}
                </a>
              ))}
              {channel.secondary_urls.map((url, idx) => (
                <a
                  key={`url-${idx}`}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-sm text-[#1A1A2E] hover:text-[#C9A84C] transition-colors"
                >
                  <ExternalLink size={12} className="text-[#6B6B6B]" />
                  {url}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ─── Niche Tags ─── */}
      {channel.niche_tags.length > 0 && (
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
            <Tag size={18} className="text-[#C9A84C]" />
            Niche Tags
          </h2>
          <div className="flex flex-wrap gap-2">
            {channel.niche_tags.map((tag) => (
              <Badge key={tag} variant="navy">
                {tag}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* ─── Scrape History ─── */}
      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <History size={18} className="text-[#C9A84C]" />
          Scrape History
        </h2>
        <div className="overflow-x-auto rounded-xl border border-[#E8E4DC] bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#1A1A2E] text-white">
              <tr>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Timestamp
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Status
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Error
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E8E4DC]">
              {scrapeLogs.length === 0 ? (
                <tr>
                  <td
                    colSpan={3}
                    className="px-4 py-8 text-center text-[#6B6B6B]"
                  >
                    No scrape history available
                  </td>
                </tr>
              ) : (
                scrapeLogs.slice(0, 10).map((log, idx) => (
                  <tr
                    key={log.id}
                    className={idx % 2 === 0 ? "bg-white" : "bg-[#FAF8F4]"}
                  >
                    <td className="px-4 py-3 text-xs text-[#6B6B6B]">
                      {timeAgo(log.attempted_at)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        variant={statusBadgeConfig[log.status] ?? "muted"}
                      >
                        {log.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-[#6B6B6B]">
                      {log.error_message ?? "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Gate 0 History ─── */}
      {gate0Result && (
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
            <Shield size={18} className="text-[#C9A84C]" />
            Gate 0 Result
          </h2>
          <div className="rounded-xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                  Checked At
                </p>
                <p className="mt-1 text-sm text-[#0D0D0D]">
                  {timeAgo(gate0Result.checked_at)}
                </p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                  Status
                </p>
                <div className="mt-1">
                  <Badge
                    variant={
                      gate0Result.result_status === "clean"
                        ? "success"
                        : "danger"
                    }
                  >
                    {gate0Result.result_status}
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                  Search Query
                </p>
                <p className="mt-1 font-mono text-sm text-[#0D0D0D]">
                  {gate0Result.search_query}
                </p>
              </div>
              {gate0Result.flagged_brand && (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                    Flagged Brand
                  </p>
                  <p className="mt-1 text-sm font-medium text-[#B22222]">
                    {gate0Result.flagged_brand}
                  </p>
                </div>
              )}
              {gate0Result.source_url && (
                <div className="sm:col-span-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                    Source URL
                  </p>
                  <a
                    href={gate0Result.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 flex items-center gap-1 text-sm text-[#1A1A2E] hover:text-[#C9A84C] transition-colors"
                  >
                    <ExternalLink size={12} />
                    {gate0Result.source_url}
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Helper: Stat Pill ─── */
function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[#E8E4DC] bg-[#FAF8F4] px-3 py-1.5">
      <span className="text-[10px] font-medium uppercase tracking-wide text-[#6B6B6B]">
        {label}
      </span>
      <p className="font-mono text-sm font-medium text-[#0D0D0D]">{value}</p>
    </div>
  );
}
