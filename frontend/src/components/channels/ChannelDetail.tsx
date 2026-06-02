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
  Trash2,
  FileText,
  Video,
  Brain,
} from "lucide-react";
import type {
  Channel,
  ChannelIntelligenceReport,
  RecentVideo,
  VelocityScore,
  Gate0Result,
  ScrapeLog,
  ChannelLookalikeMatch,
  LookalikeMatch,
} from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Gate0Badge } from "@/components/channels/Gate0Badge";
import { VelocityBadge } from "@/components/channels/VelocityBadge";
import { formatEngagementRate, formatNumber, timeAgo, cn } from "@/lib/utils";
import {
  deleteChannelCompletely,
  deleteChannelHistory,
  getChannelLookalikes,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import { useRealtimeRefresh } from "@/hooks/useRealtimeRefresh";
import { useRouter } from "next/navigation";
import { LookalikeMatchCard } from "@/components/lookalike/LookalikeMatchCard";

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
  const [lookalikes, setLookalikes] = useState<ChannelLookalikeMatch[]>([]);
  const [lookalikesLoaded, setLookalikesLoaded] = useState(false);
  const [lookalikesLoading, setLookalikesLoading] = useState(false);
  const [lookalikesError, setLookalikesError] = useState<string | null>(null);
  const [deletingHistory, setDeletingHistory] = useState(false);
  const [deletingCompletely, setDeletingCompletely] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);

  const velocity = initialVelocity;
  const gate0Result = initialGate0;
  const gate0Status = channel.gate0_status;
  const categoryTags = channel.category_tags ?? channel.niche_tags;
  const realtimeTables = useMemo(
    () => [
      { table: "channels", filter: `id=eq.${channel.id}` },
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

  const handleLoadLookalikes = async () => {
    if (!session?.access_token || lookalikesLoading) {
      return;
    }
    setLookalikesLoading(true);
    setLookalikesError(null);
    try {
      const response = await getChannelLookalikes(channel.id, session.access_token);
      setLookalikes(
        response.matches.filter(
          (match) =>
            match.channel.subscriber_count !== null &&
            match.channel.subscriber_count !== undefined &&
            match.channel.avg_comments !== null &&
            match.channel.avg_comments !== undefined
        )
      );
      setLookalikesLoaded(true);
    } catch (err) {
      setLookalikes([]);
      setLookalikesLoaded(true);
      setLookalikesError(err instanceof Error ? err.message : "Failed to load lookalikes.");
    } finally {
      setLookalikesLoading(false);
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
  const platformLabelMap: Record<Channel["platform"], string> = {
    rumble: "Rumble",
    substack: "Substack",
  };
  const platformClassMap: Record<Channel["platform"], string> = {
    rumble: "bg-[#E8712B]/10 text-[#E8712B]",
    substack: "bg-[#FF6719]/10 text-[#C04A0E]",
  };
  const channelAbout = channel.description?.trim() ?? "";
  const recentVideos = (channel.recent_videos ?? []).length
    ? (channel.recent_videos ?? []).map((video, index) => mapRecentVideo(video, index))
    : (channel.video_titles ?? [])
        .map((raw, index) => parseVideoLine(raw, index))
        .filter((video): video is ParsedVideoLine => Boolean(video));
  const recentVideosTop3 = recentVideos.slice(0, 3);

  const handleDeleteHistory = async () => {
    if (!session?.access_token) {
      setDeleteError("You must be signed in to delete channel history.");
      return;
    }
    const confirmed = window.confirm(
      "Delete this channel's snapshot/history data? This keeps the channel but removes historical records."
    );
    if (!confirmed) return;

    setDeleteError(null);
    setDeleteMessage(null);
    setDeletingHistory(true);
    try {
      await deleteChannelHistory(channel.id, session.access_token);
      setDeleteMessage("Channel history deleted.");
      router.refresh();
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : "Failed to delete channel history."
      );
    } finally {
      setDeletingHistory(false);
    }
  };

  const handleDeleteCompletely = async () => {
    if (!session?.access_token) {
      setDeleteError("You must be signed in to delete channels.");
      return;
    }
    const confirmed = window.confirm(
      "Delete this channel completely from the database? This cannot be undone."
    );
    if (!confirmed) return;

    setDeleteError(null);
    setDeleteMessage(null);
    setDeletingCompletely(true);
    try {
      await deleteChannelCompletely(channel.id, session.access_token);
      router.push("/");
      router.refresh();
    } catch (err) {
      setDeleteError(
        err instanceof Error ? err.message : "Failed to delete channel completely."
      );
    } finally {
      setDeletingCompletely(false);
    }
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
                  platformClassMap[channel.platform]
                )}
              >
                {platformLabelMap[channel.platform]}
              </span>
            </div>

            {/* Stat Pills */}
            <div className="mt-4 flex flex-wrap gap-3">
              <StatPill label="Subscribers" value={formatNumber(channel.subscriber_count)} />
              <StatPill label="Avg Views" value={formatNumber(channel.avg_views)} />
              <StatPill
                label="Engagement Rate"
                value={formatEngagementRate(channel.subscriber_count, channel.avg_comments)}
              />
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
            <Gate0Badge status={gate0Status} flaggedBrand={channel.gate0_flagged_brand} />
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
            </div>
          </div>
        </div>
      </div>

      {/* ─── AI Summary ─── */}
      {channel.ai_summary && (
        <div className="rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] px-6 py-4 shadow-sm">
          <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-[#6B6B6B]">
            <span className="inline-flex items-center rounded bg-[#1A1A2E] px-1.5 py-0.5 text-[9px] font-bold text-white">
              AI
            </span>
            Channel Overview
          </p>
          <p className="text-sm leading-6 text-[#1A1A2E]">{channel.ai_summary}</p>
        </div>
      )}

      {/* ─── Channel Intelligence Report ─── */}
      {channel.ai_channel_report && (
        <ChannelIntelligenceSection report={channel.ai_channel_report} />
      )}

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
          <FileText size={18} className="text-[#C9A84C]" />
          Channel About
        </h2>
        <div className="rounded-xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
          {channelAbout.length > 0 ? (
            <p className="whitespace-pre-wrap text-sm leading-6 text-[#1A1A2E]">
              {channelAbout}
            </p>
          ) : (
            <p className="text-sm text-[#6B6B6B]">No about description available</p>
          )}
        </div>
      </div>

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <Video size={18} className="text-[#C9A84C]" />
          Recent Videos
        </h2>
        <div className="overflow-x-auto rounded-xl border border-[#E8E4DC] bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#1A1A2E] text-white">
              <tr>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Title
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E8E4DC]">
              {recentVideosTop3.length === 0 ? (
                <tr>
                  <td colSpan={1} className="px-4 py-8 text-center text-[#6B6B6B]">
                    No video data available
                  </td>
                </tr>
              ) : (
                recentVideosTop3.map((video, idx) => (
                  <tr
                    key={video.id}
                    className={idx % 2 === 0 ? "bg-white" : "bg-[#FAF8F4]"}
                  >
                    <td className="max-w-[520px] px-4 py-3 text-sm text-[#1A1A2E]">
                      <p className="line-clamp-2">{video.title}</p>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <LinkIcon size={18} className="text-[#C9A84C]" />
          Other Channels and Links
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

      {/* ─── Topic Categories ─── */}
      {categoryTags.length > 0 && (
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
            <Tag size={18} className="text-[#C9A84C]" />
            Topic Categories
          </h2>
          <div className="flex flex-wrap gap-2">
            {categoryTags.map((tag) => (
              <Badge key={tag} variant="navy">
                {tag}
              </Badge>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-[#1A1A2E]">
            Similar Channels
          </h2>
          <Button
            variant="ghost"
            size="sm"
            loading={lookalikesLoading}
            disabled={!session?.access_token}
            onClick={() => void handleLoadLookalikes()}
          >
            Load Similar Channels
          </Button>
        </div>
        {lookalikesError && (
          <p className="mb-3 text-sm text-[#B22222]">{lookalikesError}</p>
        )}
        {lookalikesLoaded && lookalikes.length === 0 && !lookalikesError && (
          <p className="rounded-xl border border-[#E8E4DC] bg-white p-5 text-sm text-[#6B6B6B] shadow-sm">
            No similar channels found
          </p>
        )}
        {lookalikes.length > 0 && (
          <div className="space-y-3">
            {lookalikes.map((match) => {
              const adapted: LookalikeMatch = {
                id: `${channel.id}-${match.matched_channel_id}-${match.match_type}`,
                seed_id: channel.id,
                matched_channel_id: match.matched_channel_id,
                match_type: match.match_type,
                match_detail: match.match_detail,
                found_at: channel.updated_at,
                channel: match.channel,
                seed: null,
              };
              return <LookalikeMatchCard key={adapted.id} match={adapted} />;
            })}
          </div>
        )}
      </div>
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

      {/* ─── Previous Gold Affiliation History ─── */}
      {gate0Result && (
        <div>
          <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
            <Shield size={18} className="text-[#C9A84C]" />
            Previous Gold Affiliation
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
                  <Gate0Badge
                    status={gate0Result.result_status}
                    flaggedBrand={gate0Result.flagged_brand}
                  />
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

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <Trash2 size={18} className="text-[#B22222]" />
          Data Cleanup
        </h2>
        <div className="rounded-xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
          <p className="mb-4 text-sm text-[#6B6B6B]">
            Use these actions when a channel has bad data quality and needs to be reset
            or removed.
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="danger"
              size="sm"
              loading={deletingHistory}
              disabled={deletingCompletely}
              onClick={handleDeleteHistory}
            >
              Delete History (Snapshot)
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={deletingCompletely}
              disabled={deletingHistory}
              onClick={handleDeleteCompletely}
            >
              Delete Completely
            </Button>
          </div>
          {deleteError && (
            <p className="mt-3 text-sm text-[#B22222]">{deleteError}</p>
          )}
          {deleteMessage && (
            <p className="mt-3 text-sm text-[#1A1A2E]">{deleteMessage}</p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Channel Intelligence Report ─── */
const QA_ITEMS: { key: keyof ChannelIntelligenceReport; label: string; risk?: boolean }[] = [
  { key: "creator_about",        label: "What is this channel really about?" },
  { key: "audience_relationship",label: "Audience relationship" },
  { key: "age_55_appeal",        label: "55+ audience appeal" },
  { key: "acquisition_relevance",label: "Acquisition relevance" },
  { key: "monetization_pattern", label: "Monetization pattern" },
  { key: "conversion_signals",   label: "Conversion signals" },
  { key: "risk_flags",           label: "Risk flags", risk: true },
];

function ChannelIntelligenceSection({ report }: { report: ChannelIntelligenceReport }) {
  const items = QA_ITEMS.filter(({ key }) => report[key]);
  if (items.length === 0) return null;

  return (
    <div>
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
        <Brain size={18} className="text-[#C9A84C]" />
        Channel Intelligence
      </h2>
      <div className="rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] shadow-sm overflow-hidden">
        <div className="flex items-center gap-2 border-b border-[#E8E4DC] px-5 py-3">
          <span className="inline-flex items-center rounded bg-[#1A1A2E] px-1.5 py-0.5 text-[9px] font-bold text-white">
            AI
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[#6B6B6B]">
            Acquisition Due Diligence
          </span>
        </div>
        <div className="divide-y divide-[#E8E4DC]">
          {items.map(({ key, label, risk }) => (
            <div key={key} className="px-5 py-4">
              <p
                className={cn(
                  "mb-1.5 text-[10px] font-semibold uppercase tracking-widest",
                  risk ? "text-[#B22222]" : "text-[#6B6B6B]"
                )}
              >
                {label}
              </p>
              <p className="text-sm leading-6 text-[#1A1A2E]">{report[key]}</p>
            </div>
          ))}
        </div>
      </div>
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

interface ParsedVideoLine {
  id: string;
  title: string;
  views: number | null;
  comments: number | null;
  publishedLabel: string;
}

function mapRecentVideo(video: RecentVideo, index: number): ParsedVideoLine {
  return {
    id: `${index}-${video.title}`,
    title: video.title,
    views: video.views,
    comments: video.comments,
    publishedLabel: video.published_at ? timeAgo(video.published_at) : "N/A",
  };
}

function parseVideoLine(raw: string, index: number): ParsedVideoLine | null {
  const input = raw?.trim();
  if (!input) return null;

  const normalized = input.replace(/\s+/g, " ").trim();
  const parts = normalized
    .split(/\s+[|•-]\s+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const title = parts[0] ?? normalized;

  let views: number | null = null;
  let comments: number | null = null;
  let publishedLabel = "N/A";

  const viewsMatch = normalized.match(/(\d[\d,]*)\s*views?/i);
  if (viewsMatch) {
    views = Number(viewsMatch[1].replace(/,/g, ""));
    if (Number.isNaN(views)) views = null;
  }

  const commentsMatch = normalized.match(/(\d[\d,]*)\s*comments?/i);
  if (commentsMatch) {
    comments = Number(commentsMatch[1].replace(/,/g, ""));
    if (Number.isNaN(comments)) comments = null;
  }

  const dateMatch = normalized.match(
    /(\d{4}-\d{2}-\d{2}|[A-Za-z]{3,9}\s+\d{1,2},\s+\d{4}|\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago|yesterday|just now)/i
  );
  if (dateMatch) {
    publishedLabel = dateMatch[1];
  }

  return {
    id: `${index}-${title}`,
    title,
    views,
    comments,
    publishedLabel,
  };
}

