/**
 * ChannelDetail — full detail view for a single channel.
 */
"use client";

import { useMemo, useState } from "react";
import {
  ExternalLink,
  Link as LinkIcon,
  Tag,
  History,
  RefreshCw,
  Trash2,
  FileText,
  Video,
  Brain,
  Sparkles,
} from "lucide-react";
import type {
  Channel,
  RecentVideo,
  VelocityScore,
  ScrapeLog,
  ChannelLookalikeMatch,
  LookalikeMatch,
} from "@/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { InfoPopover } from "@/components/ui/InfoPopover";
import { VelocityBadge } from "@/components/channels/VelocityBadge";
import { formatEngagementRate, formatNumber, timeAgo, cn } from "@/lib/utils";
import {
  deleteChannelCompletely,
  deleteChannelHistory,
  getChannelLookalikes,
  updateChannelDoNotContact,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import { useRealtimeRefresh } from "@/hooks/useRealtimeRefresh";
import { useChannelDetailTour } from "@/hooks/useTourAutoStart";
import { useRouter } from "next/navigation";
import { LookalikeMatchCard } from "@/components/lookalike/LookalikeMatchCard";

interface ChannelDetailProps {
  channel: Channel;
  velocity: VelocityScore | null;
  scrapeLogs: ScrapeLog[];
}

type DoNotContactChoice = NonNullable<Channel["do_not_contact"]>;
type RecentVideoRow = RecentVideo & { id?: string };

export function ChannelDetail({
  channel,
  velocity: initialVelocity,
  scrapeLogs,
}: ChannelDetailProps) {
  useChannelDetailTour();

  const router = useRouter();
  const { session } = useAuth();
  const [lookalikes, setLookalikes] = useState<ChannelLookalikeMatch[]>([]);
  const [lookalikesLoaded, setLookalikesLoaded] = useState(false);
  const [lookalikesLoading, setLookalikesLoading] = useState(false);
  const [lookalikesError, setLookalikesError] = useState<string | null>(null);
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
  const categoryTags = channel.category_tags ?? channel.niche_tags;
  const realtimeTables = useMemo(
    () => [
      { table: "channels", filter: `id=eq.${channel.id}` },
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
  const similarChannelCount = lookalikes.length;
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

  return (
    <div className="space-y-6">
      {/* ─── Header Section ─── */}
      <div id="tour-channel-header" className="rounded-xl border border-[#E8E4DC] bg-white p-6 shadow-sm">
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
              <StatPill label="Subscribers" value={formatNumber(channel.subscriber_count)} info="Total subscriber or follower count at the time of last scrape." />
              <StatPill label="Avg Views" value={formatNumber(channel.avg_views)} info="Rolling average views per video or post. Reflects actual content reach, independent of subscriber count." />
              <StatPill
                label="Engagement Rate"
                value={formatEngagementRate(channel.subscriber_count, channel.avg_comments)}
                info="Average comments divided by subscriber count, as a percentage. A high ratio signals a highly engaged, niche audience relative to size."
              />
              <StatPill label="Avg Comments" value={formatNumber(channel.avg_comments)} info="Rolling average comments per post. The primary engagement signal used for tier classification." />
              <StatPill
                label="Posts/Week"
                value={
                  channel.posts_per_week === null
                    ? "N/A"
                    : String(channel.posts_per_week)
                }
                info="Average number of posts or videos published per week, calculated from recent history."
              />
              <StatPill label="Last Active" value={timeAgo(channel.last_active_date)} info="Date of the channel's most recent post or video upload." />
            </div>
          </div>

          <div className="flex flex-col items-end gap-3">
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

      {/* ─── Channel Intelligence Report ─── */}
      <div id="tour-ai-report">
        {channel.ai_channel_report ? (
          <ChannelIntelligenceSection report={channel.ai_channel_report} />
        ) : (
          <div>
            <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
              <Brain size={18} className="text-[#C9A84C]" />
              Channel Intelligence Report
            </h2>
            <div className="rounded-xl border border-[#E8E4DC] bg-[#FAF8F4] p-5 shadow-sm">
              <p className="text-sm text-[#6B6B6B]">AI report not yet generated for this channel.</p>
            </div>
          </div>
        )}
      </div>

      {/* ─── Velocity Section ─── */}
      <div id="tour-velocity-section">
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <RefreshCw size={18} className="text-[#C9A84C]" />
          Growth Velocity
          <InfoPopover content="Percentage change in views or comments compared to the prior equivalent period. Positive = growing, negative = declining. Requires at least two scrape snapshots to compute." />
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
      <div id="tour-channel-about">
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

      <div id="tour-recent-videos">
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

      <div id="tour-channel-links">
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

      <div id="tour-similar-channels">
        <section className="overflow-hidden rounded-3xl border border-[#C9A84C]/25 bg-white shadow-[0_18px_50px_rgba(26,26,46,0.08)]">
          <div className="bg-gradient-to-br from-[#1A1A2E] via-[#20213B] to-[#0F1020] px-6 py-6 text-white md:px-8 md:py-8">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-3xl">
                <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-white/80">
                  <Sparkles size={12} />
                  Similar channel finder
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-2xl font-semibold tracking-tight md:text-3xl">
                    Similar Channels
                  </h2>
                  <InfoPopover
                    dark
                    content="Channels that share a similar niche, subscriber range, or engagement profile. Powered by the lookalike algorithm using topic tags, engagement metrics, and contact overlap."
                  />
                </div>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-white/75 md:text-base">
                  Load a focused shortlist of related creators to expand outreach, compare audience fit, and spot adjacent channels with matching engagement patterns.
                </p>
              </div>

              <div className="flex flex-col gap-3 lg:items-end">
                <Button
                  variant="accent"
                  size="lg"
                  loading={lookalikesLoading}
                  disabled={!session?.access_token}
                  className="min-w-[12rem] shadow-[0_12px_24px_rgba(201,168,76,0.24)]"
                  onClick={() => void handleLoadLookalikes()}
                >
                  <Sparkles size={16} />
                  Load Similar Channels
                </Button>
                <div className="flex flex-wrap items-center gap-2 text-xs text-white/70">
                  <span className="rounded-full border border-white/10 bg-white/10 px-2.5 py-1">
                    Matches update on demand
                  </span>
                  {lookalikesLoaded && (
                    <span className="rounded-full border border-white/10 bg-white/10 px-2.5 py-1">
                      {similarChannelCount} result{similarChannelCount === 1 ? "" : "s"} loaded
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-4 bg-[#FAF8F4] px-6 py-6 md:px-8 md:py-8">
            {lookalikesError && (
              <div className="rounded-2xl border border-[#B22222]/20 bg-[#B22222]/8 px-4 py-3 text-sm text-[#B22222]">
                {lookalikesError}
              </div>
            )}

            {lookalikesLoaded && lookalikes.length === 0 && !lookalikesError && (
              <div className="rounded-2xl border border-dashed border-[#C9A84C]/35 bg-white px-5 py-8 text-center shadow-sm">
                <p className="text-base font-medium text-[#1A1A2E]">
                  No similar channels found yet
                </p>
                <p className="mt-1 text-sm text-[#6B6B6B]">
                  Try loading again after more channels are scraped or classified.
                </p>
              </div>
            )}

            {!lookalikesLoaded && !lookalikesError && !lookalikesLoading && (
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-2xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#6B6B6B]">
                    Audience overlap
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#1A1A2E]">
                    Finds channels with similar engagement and size ranges.
                  </p>
                </div>
                <div className="rounded-2xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#6B6B6B]">
                    Topic adjacency
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#1A1A2E]">
                    Surfaces related niche tags and category matches.
                  </p>
                </div>
                <div className="rounded-2xl border border-[#E8E4DC] bg-white p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#6B6B6B]">
                    Outreach expansion
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#1A1A2E]">
                    Use it to widen a prospect list without leaving the page.
                  </p>
                </div>
              </div>
            )}

            {lookalikesLoading && (
              <div className="rounded-2xl border border-[#E8E4DC] bg-white p-8 text-center shadow-sm">
                <div className="mx-auto mb-4 h-12 w-12 animate-pulse rounded-full bg-[#C9A84C]/15" />
                <p className="text-base font-medium text-[#1A1A2E]">
                  Loading similar channels
                </p>
                <p className="mt-1 text-sm text-[#6B6B6B]">
                  Pulling related creators, audience overlap, and category matches.
                </p>
              </div>
            )}

            {lookalikes.length > 0 && (
              <div className="grid gap-4 lg:grid-cols-2">
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
        </section>
      </div>
      {/* ─── Scrape History ─── */}
      <div id="tour-scrape-history">
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <History size={18} className="text-[#C9A84C]" />
          Scrape History
          <InfoPopover content="Log of each time this channel was scraped. 'blocked' = Cloudflare or platform protection triggered; 'retry' = task was re-queued for another attempt." />
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
                      {formatScrapeTimestamp(log.attempted_at)}
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

      <div id="tour-data-cleanup">
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-[#1A1A2E]">
          <Trash2 size={18} className="text-[#B22222]" />
          Data Cleanup
          <InfoPopover content="'Delete History' removes snapshot records but keeps the channel active. 'Delete Completely' permanently removes the channel and all associated data from the database." />
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
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#6B6B6B]">
                  Do Not Contact
                </p>
                <InfoPopover content="Tracks the partnership status of this channel. 'Current Partner' and 'Hired and Canceled' exclude the channel from outreach workflows." />
              </div>
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
        <InfoPopover content="AI-generated summary of the channel's content, audience, and positioning, based on scraped video titles, description, and about text." />
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

/* ─── Helper: Stat Pill ─── */
function StatPill({ label, value, info }: { label: string; value: string; info?: string }) {
  return (
    <div className="rounded-lg border border-[#E8E4DC] bg-[#FAF8F4] px-3 py-1.5">
      <div className="flex items-center gap-1">
        <span className="text-[10px] font-medium uppercase tracking-wide text-[#6B6B6B]">
          {label}
        </span>
        {info && <InfoPopover content={info} />}
      </div>
      <p className="font-mono text-sm font-medium text-[#0D0D0D]">{value}</p>
    </div>
  );
}

function formatScrapeTimestamp(dateString: string | null): string {
  if (!dateString) return "N/A";
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return dateString;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
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
