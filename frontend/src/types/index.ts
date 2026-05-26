/**
 * Kontrol_Alt — Shared TypeScript interfaces.
 * All domain types used across the frontend application.
 */

/** Supported scraping platforms. */
export type Platform = "rumble" | "bitchute" | "substack";

/** Comment engagement tier. */
export type CommentTier = "active" | "sweet_spot" | "whale";

/** Gate 0 compliance check status. */
export type Gate0Status = "clean" | "dirty" | "pending" | "unchecked";

/** Scrape log status. */
export type ScrapeStatus = "success" | "blocked" | "retry" | "failed";

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
  niche_tags: string[];
  video_titles: string[];
  is_active: boolean;
  gate0_status: Gate0Status;
  gate0_checked_at: string | null;
  secondary_urls: string[];
  has_been_scraped: boolean;
  discovery_status: "new" | "queued" | "scraped" | "failed" | "dead" | "blocked";
  last_scrape_error: string | null;
  dashboard_metrics_complete: boolean;
  dashboard_url_valid: boolean;
  dashboard_eligible: boolean;

  // Consolidated velocity fields
  view_velocity_30d: number | null;
  view_velocity_90d: number | null;
  comment_velocity_30d: number | null;
  comment_velocity_90d: number | null;
  velocity_computed_at: string | null;

  // Consolidated Gate 0 cache fields
  gate0_result_id: string | null;
  gate0_search_query: string | null;
  gate0_result_status: string | null;
  gate0_flagged_brand: string | null;
  gate0_source_url: string | null;

  created_at: string;
  updated_at: string;
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
}

/** Log entry for a scrape attempt. */
export interface ScrapeLog {
  id: string;
  channel_id: string;
  attempted_at: string;
  status: ScrapeStatus;
  error_message: string | null;
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
  channel?: Channel | null;
  seed?: SeedCreator | null;
}

/** Structured API error response. */
export interface ApiErrorResponse {
  error: string;
  detail: string;
  timestamp: string;
}

/** Response returned when a Gate 0 check is queued. */
export interface Gate0CheckResponse {
  channel_id: string;
  message: string;
  task_id: string;
  status: Gate0Status;
  triggered_at: string;
}

/** Response returned when a lookalike search is queued. */
export interface LookalikeSearchResponse {
  message: string;
  task_id: string;
  seed_count: number;
}

/** Response returned when a scrape job is triggered. */
export interface ScrapeTaskResponse {
  message: string;
  task_id: string;
  task_ids: string[];
  triggered_at: string;
}

export type IntakeStatus = "inserted" | "duplicate" | "invalid";

export interface IntakeRecordResult {
  input_value: string;
  status: IntakeStatus;
  channel_url: string | null;
  platform: Platform | null;
  reason: string | null;
  channel_id: string | null;
  scrape_task_id: string | null;
}

export interface IntakeSummaryResponse {
  message: string;
  inserted: number;
  duplicates: number;
  invalid: number;
  records: IntakeRecordResult[];
}

export interface ManualChannelIntakeRequest {
  platform: Platform;
  channel_url: string;
  notes?: string | null;
  tags: string[];
  trigger_scrape_now: boolean;
}

export interface BulkChannelIntakeRequest {
  urls_text: string;
  trigger_scrape_now: boolean;
}

export interface ResolverSeedRequest {
  seed_names: string[];
  limit_per_seed: number;
}

export interface ResolvedChannelCandidate {
  platform: Platform;
  channel_url: string;
  channel_name: string;
  confidence: number;
  source: string;
}

export interface ResolverSeedResult {
  seed_name: string;
  candidates: ResolvedChannelCandidate[];
}

export interface ResolverResponse {
  results: ResolverSeedResult[];
  unresolved: string[];
}

export interface ResolverConfirmSelection {
  seed_name: string;
  platform: Platform;
  channel_url: string;
  tags: string[];
  notes?: string | null;
}

export interface ResolverConfirmRequest {
  selections: ResolverConfirmSelection[];
  trigger_scrape_now: boolean;
}

/** Filter state for channel discovery table. */
export interface ChannelFilters {
  platform: "all" | Platform;
  comment_tier: "all" | CommentTier;
  gate0_status: "all" | Gate0Status;
  niche_tag: string | null;
  search_query?: string | null;
  min_subscriber_count?: number | null;
  max_subscriber_count?: number | null;
  min_avg_views?: number | null;
  max_avg_views?: number | null;
  min_avg_comments?: number | null;
  max_avg_comments?: number | null;
  last_active_from?: string | null;
  last_active_to?: string | null;
  inactive_filter: boolean;
  include_incomplete?: boolean;
  sort_by:
    | "subscriber_count"
    | "avg_views"
    | "avg_comments"
    | "view_velocity_30d"
    | "view_velocity_90d"
    | "last_active_date";
  sort_order: "asc" | "desc";
}

/** Paginated API response wrapper. */
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminMeResponse {
  user_id: string;
  email: string | null;
  roles: string[];
  capabilities: string[];
}

export interface AdminTaskTriggerRequest {
  reason?: string | null;
}

export interface AdminTaskTriggerResponse {
  message: string;
  task_id: string;
  task_ids: string[];
  triggered_at: string;
}

export interface Gate0BatchTriggerRequest {
  channel_ids: string[];
  reason?: string | null;
}

export interface Gate0BatchTriggerResponse {
  queued: number;
  task_ids: string[];
  triggered_at: string;
}

export interface AdminTaskStatusResponse {
  task_id: string;
  state: string;
  result: unknown;
  date_done: string | null;
}

export interface AdminAuditRecord {
  id: string;
  actor_user_id: string;
  actor_email: string | null;
  action: string;
  target: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface PaginatedAdminAuditResponse {
  data: AdminAuditRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface CompetitorDef {
  brand: string;
  domains: string[];
}

export interface CompetitorListResponse {
  competitors: CompetitorDef[];
}
