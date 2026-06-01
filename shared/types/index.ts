/**
 * Kontrol_Alt — Shared TypeScript types.
 * Consumed by the frontend and any other TypeScript services.
 */

/** Supported scraping platforms. */
export type Platform = "rumble" | "substack";

/** Gate 0 compliance check status. */
export type Gate0Status = "clean" | "dirty" | "pending" | "unchecked";

/** Scrape log status. */
export type ScrapeStatus = "success" | "blocked" | "retry" | "failed";

/** Comment engagement tier. */
export type CommentTier = "active" | "sweet_spot" | "whale";

/** Lookalike match type. */
export type MatchType = "guest_appearance" | "niche_overlap";

/** A channel discovered on an alternative media platform. */
export interface Channel {
  id: string;
  platform: Platform;
  channel_url: string;
  name: string;
  description: string;
  subscriber_count: number | null;
  avg_views: number | null;
  avg_comments: number | null;
  comment_tier: CommentTier | null;
  posts_per_week: number | null;
  last_active_date: string | null;
  contact_info: string[];
  category_tags?: string[];
  niche_tags: string[];
  video_titles: string[];
  is_active: boolean;
  gate0_status: Gate0Status;
  gate0_checked_at: string | null;
  secondary_urls: string[];
  created_at: string;
  updated_at: string;
}

/** A point-in-time snapshot of channel metrics. */
export interface ChannelSnapshot {
  id: string;
  channel_id: string;
  scraped_at: string;
  subscriber_count: number | null;
  avg_views: number | null;
  avg_comments: number | null;
  created_at: string;
}

/** Computed growth velocity scores for a channel. */
export interface VelocityScore {
  id: string;
  channel_id: string;
  computed_at: string;
  view_velocity_30d: number | null;
  view_velocity_90d: number | null;
  comment_velocity_30d: number | null;
  comment_velocity_90d: number | null;
  created_at: string;
}

/** Result of a Gate 0 compliance check via Serper search. */
export interface Gate0Result {
  id: string;
  channel_id: string;
  checked_at: string;
  search_query: string;
  result_status: "clean" | "dirty";
  flagged_brand: string | null;
  source_url: string | null;
  created_at: string;
}

/** Log entry for a scrape attempt. */
export interface ScrapeLog {
  id: string;
  channel_id: string;
  attempted_at: string;
  status: ScrapeStatus;
  error_message: string | null;
  created_at: string;
}

/** A seed creator used as input for lookalike searches. */
export interface SeedCreator {
  id: string;
  user_id: string;
  name: string;
  created_at: string;
}

/** A lookalike match found for a seed creator. */
export interface LookalikeMatch {
  id: string;
  seed_id: string;
  matched_channel_id: string;
  match_type: MatchType;
  match_detail: string | null;
  found_at: string;
  created_at: string;
  channel?: Channel | null;
  seed?: SeedCreator | null;
}

export interface Gate0CheckResponse {
  channel_id: string;
  message: string;
  task_id: string;
  status: Gate0Status;
  triggered_at: string;
}

export interface LookalikeSearchResponse {
  message: string;
  task_id: string;
  seed_count: number;
}

export interface ScrapeTaskResponse {
  message: string;
  task_id: string;
  task_ids: string[];
  triggered_at: string;
}
