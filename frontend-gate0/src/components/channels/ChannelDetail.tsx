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
  RecentVideo,
  VelocityScore,
  Gate0Result,
  Gate0EvidenceSignal,
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
  triggerGate0Check,
  updateChannelDoNotContact,
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

type DoNotContactChoice = NonNullable<Channel["do_not_contact"]>;
type RecentVideoRow = RecentVideo & { id?: string };

export function ChannelDetail({
  channel,
  velocity: initialVelocity,
  gate0: initialGate0,
  scrapeLogs,
}: ChannelDetailProps) {
  const router = useRouter();
  const { session, user } = useAuth();
  const [lookalikes, setLookalikes] = useState<ChannelLookalikeMatch[]>([]);
  const [lookalikesLoaded, setLookalikesLoaded] = useState(false);
  const [lookalikesLoading, setLookalikesLoading] = useState(false);
  const [lookalikesError, setLookalikesError] = useState<string | null>(null);
  const [gate0Triggering, setGate0Triggering] = useState(false);
  const [gate0Message, setGate0Message] = useState<string | null>(null);
  const [gate0Error, setGate0Error] = useState<string | null>(null);
  const [deletingHistory, setDeletingHistory] = useState(false);
  const [deletingCompletely, setDeletingCompletely] = useState(false);
  const [doNotContactUpdating, setDoNotContactUpdating] = useState<
    DoNotContactChoice | "reset" | null
  >(null);
  const [doNotContactError, setDoNotContactError] = useState<string | null>(null);
  const [doNotContactMessage, setDoNotContactMessage] = useState<string | null>(
    null
  );
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleteMessage, setDeleteMessage] = useState<string | null>(null);

  const velocity = initialVelocity;
  const gate0Result = initialGate0;
  const gate0Status = channel.gate0_status;
  const isAdminUser = Boolean(
    user &&
      (user.app_metadata?.role === "admin" ||
        user.app_metadata?.is_admin === true ||
        user.app_metadata?.is_admin === "true" ||
        user.user_metadata?.role === "admin" ||
        user.user_metadata?.is_admin === true ||
        user.user_metadata?.is_admin === "true")
  );
  const gate0NeedsManualOverride = gate0Status === "needs_review" || gate0Status === "dirty";
  const gate0StatusLabel = gate0Status.replace(/_/g, " ");
  const gate0ActionToneClass = gate0Status === "dirty"
    ? "border-[#B22222]/20 bg-[#FFF5F5]"
    : gate0NeedsManualOverride
      ? "border-[#E6A817]/20 bg-[#FFFDF3]"
      : "border-[#E8E4DC] bg-[#FAF8F4]";
  const gate0ActionBadgeVariant = gate0Status === "dirty" ? "danger" : gate0NeedsManualOverride ? "warning" : "muted";
  const gate0ActionDescription = gate0NeedsManualOverride
    ? `Manual override rerun: this channel is currently marked ${gate0StatusLabel}, but this action queues a fresh Gate 0 check anyway.`
    : "Run a fresh Gate 0 check for this channel.";
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
  const doNotContactLabel = channel.do_not_contact ?? "Not Set";
  const doNotContactBadgeVariant =
    channel.do_not_contact === "Hired and Canceled"
      ? "danger"
      : channel.do_not_contact === "Current Partner"
        ? "gold"
        : "muted";
  const recentVideos = channel.recent_videos ?? [];
  const recentVideoRows: RecentVideoRow[] =
    recentVideos.length > 0
      ? (recentVideos.slice(0, 3) as RecentVideoRow[])
      : channel.video_titles.slice(0, 3).map((title) => ({
          title,
          views: null,
          comments: null,
          published_at: null,
          url: null,
        }));

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

  const handleDoNotContactUpdate = async (value: Channel["do_not_contact"]) => {
    if (!session?.access_token) {
      setDoNotContactError("You must be signed in to update do-not-contact.");
      return;
    }
    if (doNotContactUpdating !== null) {
      return;
    }

    setDoNotContactError(null);
    setDoNotContactMessage(null);
    setDoNotContactUpdating(value ?? "reset");
    try {
      await updateChannelDoNotContact(
        channel.id,
        { do_not_contact: value },
        session.access_token
      );
      setDoNotContactMessage(
        value ? `Do not contact set to ${value}.` : "Do not contact reset."
      );
      router.refresh();
    } catch (err) {
      setDoNotContactError(
        err instanceof Error
          ? err.message
          : "Failed to update do-not-contact status."
      );
    } finally {
      setDoNotContactUpdating(null);
    }
  };

  const handleRunGate0Now = async () => {
    if (!isAdminUser) {
      setGate0Error("Admin access is required to run Gate0.");
      return;
    }
    if (!session?.access_token || gate0Triggering) {
      return;
    }

    setGate0Error(null);
    setGate0Message(null);
    setGate0Triggering(true);
    try {
      const response = await triggerGate0Check(channel.id, session.access_token);
      setGate0Message(`${response.message} Task ID: ${response.task_id}.`);
      router.refresh();
    } catch (err) {
      setGate0Error(
        err instanceof Error ? err.message : "Failed to run Gate0."
      );
    } finally {
      setGate0Triggering(false);
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
            {isAdminUser && (
              <div className={cn("w-full max-w-sm rounded-xl border p-4 shadow-sm", gate0ActionToneClass)}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-widest text-[#6B6B6B]">
                      Gate0 Admin Action
                    </p>
                    <p className="mt-1 text-sm font-semibold text-[#1A1A2E]">
                      Run Gate0 now
                    </p>
                    <p className="mt-1 text-xs leading-5 text-[#6B6B6B]">
                      {gate0ActionDescription}
                    </p>
                  </div>
                  <Badge variant={gate0ActionBadgeVariant}>Admin only</Badge>
                </div>
                <Button
                  variant={gate0NeedsManualOverride ? "danger" : "accent"}
                  size="sm"
                  loading={gate0Triggering}
                  disabled={!session?.access_token || gate0Triggering}
                  className="mt-3 w-full"
                  onClick={() => void handleRunGate0Now()}
                >
                  <RefreshCw size={14} />
                  Run Gate0 now
                </Button>
                {gate0Error && (
                  <p className="mt-2 text-xs text-[#B22222]" role="alert">
                    {gate0Error}
                  </p>
                )}
                {gate0Message && (
                  <p className="mt-2 text-xs text-[#1A1A2E]" role="status" aria-live="polite">
                    {gate0Message}
                  </p>
                )}
                <p className="mt-2 text-[11px] text-[#6B6B6B]">
                  Current Gate0 status: {gate0StatusLabel}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

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
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Views
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Comments
                </th>
                <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide">
                  Uploaded Date
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E8E4DC]">
              {recentVideoRows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-[#6B6B6B]">
                    No video data available
                  </td>
                </tr>
              ) : (
                recentVideoRows.map((video, idx) => (
                  <tr
                    key={video.id ?? `${video.title}-${idx}`}
                    className={idx % 2 === 0 ? "bg-white" : "bg-[#FAF8F4]"}
                  >
                    <td className="max-w-[520px] px-4 py-3 text-sm text-[#1A1A2E]">
                      {video.url ? (
                        <a
                          href={video.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-start gap-1 font-medium text-[#1A1A2E] transition-colors hover:text-[#C9A84C]"
                        >
                          <span className="line-clamp-2">{video.title}</span>
                          <ExternalLink size={12} className="mt-0.5 shrink-0" />
                        </a>
                      ) : (
                        <p className="line-clamp-2 font-medium">{video.title}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-[#1A1A2E]">
                      {formatNumber(video.views)}
                    </td>
                    <td className="px-4 py-3 text-[#1A1A2E]">
                      {formatNumber(video.comments)}
                    </td>
                    <td className="px-4 py-3 text-[#6B6B6B]">
                      {formatPublishedDate(video.published_at)}
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
          <div className="rounded-xl border border-[#E8E4DC] bg-white p-5 shadow-sm space-y-5">
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
              {gate0Result.confidence !== null && (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                    Confidence
                  </p>
                  <ConfidenceBar confidence={gate0Result.confidence} />
                </div>
              )}
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
                    Evidence Found In
                  </p>
                  {gate0Result.source_url.startsWith("http") ? (
                    <a
                      href={gate0Result.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-1 flex items-center gap-1 break-all text-sm text-[#1A1A2E] hover:text-[#C9A84C] transition-colors"
                    >
                      <ExternalLink size={12} className="shrink-0" />
                      {gate0Result.source_url}
                    </a>
                  ) : (
                    <p className="mt-1 text-sm text-[#1A1A2E]">
                      {gate0Result.source_url}
                    </p>
                  )}
                </div>
              )}
            </div>

            {gate0Result.evidence_signals && gate0Result.evidence_signals.length > 0 && (
              <EvidenceSignalsTable signals={gate0Result.evidence_signals} />
            )}
          </div>
        </div>
      )}

      <div>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <Trash2 size={18} className="text-[#B22222]" />
          Data Cleanup
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
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

          <div className="rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] p-5 shadow-sm self-start">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#6B6B6B]">
                Do Not Contact
              </p>
              <Badge variant={doNotContactBadgeVariant}>
                {doNotContactLabel}
              </Badge>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button
                variant="danger"
                size="sm"
                loading={doNotContactUpdating === "Hired and Canceled"}
                disabled={!session?.access_token || doNotContactUpdating !== null}
                onClick={() => void handleDoNotContactUpdate("Hired and Canceled")}
              >
                Hired and Canceled
              </Button>
              <Button
                variant="accent"
                size="sm"
                loading={doNotContactUpdating === "Current Partner"}
                disabled={!session?.access_token || doNotContactUpdating !== null}
                onClick={() => void handleDoNotContactUpdate("Current Partner")}
              >
                Current Partner
              </Button>
              <Button
                variant="ghost"
                size="sm"
                loading={doNotContactUpdating === "reset"}
                disabled={!session?.access_token || doNotContactUpdating !== null}
                className="border border-[#E8E4DC] bg-white hover:bg-[#FAF8F4]"
                onClick={() => void handleDoNotContactUpdate(null)}
              >
                Reset
              </Button>
            </div>
            {doNotContactError && (
              <p className="mt-3 text-xs text-[#B22222]">{doNotContactError}</p>
            )}
            {doNotContactMessage && (
              <p className="mt-3 text-xs text-[#6B6B6B]">{doNotContactMessage}</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Channel Intelligence Report ─── */
function ChannelIntelligenceSection({ report }: { report: string }) {
  return (
    <div>
      <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
        <Brain size={18} className="text-[#C9A84C]" />
        Channel Intelligence Report
      </h2>
      <div className="overflow-hidden rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] shadow-sm">
        <div className="flex items-center gap-2 border-b border-[#E8E4DC] px-5 py-3">
          <span className="inline-flex items-center rounded bg-[#1A1A2E] px-1.5 py-0.5 text-[9px] font-bold text-white">
            AI
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-[#6B6B6B]">
            Report
          </span>
        </div>
        <div className="px-5 py-5">
          <p className="whitespace-pre-wrap text-sm leading-7 text-[#1A1A2E]">
            {report}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ─── Helper: Confidence Bar ─── */
function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.95
      ? "bg-[#B22222]"
      : confidence >= 0.80
        ? "bg-[#C9A84C]"
        : "bg-[#2E7D32]";
  return (
    <div className="mt-1 flex items-center gap-2">
      <div className="h-2 w-28 overflow-hidden rounded-full bg-[#E8E4DC]">
        <div
          className={cn("h-full rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="font-mono text-sm font-medium text-[#0D0D0D]">{pct}%</span>
    </div>
  );
}

/* ─── Helper: Signal Type Label ─── */
function formatSignalType(type: string): string {
  const map: Record<string, string> = {
    domain_in_contact: "Domain in Contact Info",
    brand_in_contact: "Brand in Contact Info",
    redirect_to_domain: "Redirect → Competitor Domain",
    affiliate_url: "Affiliate URL",
    domain_in_description: "Domain in Description",
    brand_in_description: "Brand in Description",
    domain_in_name: "Domain in Channel Name",
    brand_in_name: "Brand in Channel Name",
    title_promo: "Promo Video Title",
    title_neutral: "Video Title Mention",
    serper_hit: "Web Search Hit",
  };
  return map[type] ?? type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/* ─── Helper: Evidence Signals Table ─── */
function EvidenceSignalsTable({ signals }: { signals: Gate0EvidenceSignal[] }) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
        Evidence Signals ({signals.length})
      </p>
      <div className="overflow-x-auto rounded-lg border border-[#E8E4DC]">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#1A1A2E] text-white">
            <tr>
              <th className="px-3 py-2 font-semibold uppercase tracking-wide">Signal</th>
              <th className="px-3 py-2 font-semibold uppercase tracking-wide">Matched Value</th>
              <th className="px-3 py-2 font-semibold uppercase tracking-wide">Weight</th>
              <th className="px-3 py-2 font-semibold uppercase tracking-wide">Source / Context</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E8E4DC]">
            {signals.map((sig, idx) => (
              <tr key={idx} className={idx % 2 === 0 ? "bg-white" : "bg-[#FAF8F4]"}>
                <td className="px-3 py-2 text-[#1A1A2E]">{formatSignalType(sig.type)}</td>
                <td className="px-3 py-2 font-mono text-[#1A1A2E]">{sig.value}</td>
                <td className="px-3 py-2">
                  <span
                    className={cn(
                      "inline-block rounded px-1.5 py-0.5 font-mono font-semibold",
                      sig.weight >= 0.95
                        ? "bg-[#B22222]/10 text-[#B22222]"
                        : sig.weight >= 0.80
                          ? "bg-[#C9A84C]/15 text-[#8B6914]"
                          : "bg-[#E8E4DC] text-[#6B6B6B]"
                    )}
                  >
                    {Math.round(sig.weight * 100)}%
                  </span>
                </td>
                <td className="max-w-[280px] px-3 py-2 text-[#6B6B6B]">
                  {sig.source_url && sig.source_url.startsWith("http") ? (
                    <a
                      href={sig.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 break-all text-[#1A1A2E] hover:text-[#C9A84C] transition-colors"
                    >
                      <ExternalLink size={10} className="shrink-0" />
                      <span className="line-clamp-1">{sig.source_url}</span>
                    </a>
                  ) : sig.source_url ? (
                    <span>{sig.source_url}</span>
                  ) : null}
                  {sig.context && (
                    <p className="mt-0.5 line-clamp-2 italic text-[#6B6B6B]">
                      &ldquo;{sig.context}&rdquo;
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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

function formatPublishedDate(dateString: string | null): string {
  if (!dateString) {
    return "N/A";
  }

  const datePart = dateString.slice(0, 10);
  const date = new Date(`${datePart}T00:00:00Z`);

  if (Number.isNaN(date.getTime())) {
    return datePart;
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}
