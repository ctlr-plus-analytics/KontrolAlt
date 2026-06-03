/**
 * Typed API client for FastAPI backend calls.
 * All functions accept an optional auth token for Bearer header.
 */

import type {
  Channel,
  VelocityScore,
  Gate0Result,
  ScrapeLog,
  LookalikeMatch,
  ChannelFilters,
  PaginatedResponse,
  ApiErrorResponse,
  Gate0CheckResponse,
  LookalikeSearchResponse,
  ChannelLookalikeResponse,
  ManualChannelIntakeRequest,
  BulkChannelIntakeRequest,
  IntakeSummaryResponse,
  ResolverSeedRequest,
  ResolverResponse,
  ResolverConfirmRequest,
  UpdateChannelDoNotContactRequest,
  ScrapeTaskResponse,
  AdminMeResponse,
  AdminTaskTriggerRequest,
  AdminTaskTriggerResponse,
  ClassifyChannelsTriggerRequest,
  Gate0BatchTriggerRequest,
  Gate0BatchTriggerResponse,
  AdminTaskStatusResponse,
  PaginatedAdminAuditResponse,
  CompetitorDef,
  CompetitorListResponse,
  Gate0StatusOption,
  KeywordTaxonomyDef,
  KeywordTaxonomyListResponse,
  CategoryTagOption,
  PurgeQueueRequest,
  PurgeQueueResponse,
  WorkerStatusResponse,
  WorkerLogsResponse,
} from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Structured API error. */
export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Internal fetch wrapper. */
async function apiFetch<T>(
  path: string,
  options: {
    method?: string;
    body?: unknown;
    token?: string;
  } = {}
): Promise<T> {
  const { method = "GET", body, token } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({
      error: response.statusText,
      detail: response.statusText,
    }));
    const apiError = error as Partial<ApiErrorResponse> & {
      message?: string;
    };
    throw new ApiError(
      apiError.detail ??
        apiError.error ??
        apiError.message ??
        `Backend error: ${response.status}`,
      response.status
    );
  }

  return response.json() as Promise<T>;
}

/** Channel with optional joined velocity data. */
export type ChannelWithVelocity = Channel & { velocity?: VelocityScore | null };

/** Channel detail with full joined data. */
export type ChannelDetail = Channel & {
  velocity?: VelocityScore | null;
  gate0?: Gate0Result | null;
  scrape_logs?: ScrapeLog[];
};

export interface ChannelDeleteResponse {
  message: string;
  channel_id: string;
}

/** Fetch paginated channels with filters. */
export async function getChannels(
  filters: Partial<ChannelFilters>,
  page: number,
  pageSize: number,
  token?: string
): Promise<PaginatedResponse<ChannelWithVelocity>> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));

  if (filters.platform && filters.platform !== "all") {
    params.set("platform", filters.platform);
  }
  if (filters.comment_tier && filters.comment_tier !== "all") {
    params.set("comment_tier", filters.comment_tier);
  }
  if (filters.gate0_statuses && filters.gate0_statuses.length > 0) {
    filters.gate0_statuses.forEach((status) => params.append("gate0_statuses", status));
  }
  const categoryTags = filters.category_tags ?? filters.niche_tags;
  if (categoryTags && categoryTags.length > 0) {
    categoryTags.forEach((tag) => params.append("category_tags", tag));
  }
  if (filters.search_query && filters.search_query.trim().length > 0) {
    params.set("search_query", filters.search_query.trim());
  }
  if (filters.min_subscriber_count !== undefined && filters.min_subscriber_count !== null) {
    params.set("min_subscriber_count", String(filters.min_subscriber_count));
  }
  if (filters.max_subscriber_count !== undefined && filters.max_subscriber_count !== null) {
    params.set("max_subscriber_count", String(filters.max_subscriber_count));
  }
  if (filters.min_avg_views !== undefined && filters.min_avg_views !== null) {
    params.set("min_avg_views", String(filters.min_avg_views));
  }
  if (filters.max_avg_views !== undefined && filters.max_avg_views !== null) {
    params.set("max_avg_views", String(filters.max_avg_views));
  }
  if (filters.min_avg_comments !== undefined && filters.min_avg_comments !== null) {
    params.set("min_avg_comments", String(filters.min_avg_comments));
  }
  if (filters.max_avg_comments !== undefined && filters.max_avg_comments !== null) {
    params.set("max_avg_comments", String(filters.max_avg_comments));
  }
  if (filters.last_active_from) {
    params.set("last_active_from", filters.last_active_from);
  }
  if (filters.last_active_to) {
    params.set("last_active_to", filters.last_active_to);
  }
  if (filters.inactive_filter) {
    params.set("inactive_filter", "true");
  }
  if (filters.incomplete_only) {
    params.set("incomplete_only", "true");
  }
  if (filters.sort_by) {
    params.set("sort_by", filters.sort_by);
  }
  if (filters.sort_order) {
    params.set("sort_order", filters.sort_order);
  }

  return apiFetch<PaginatedResponse<ChannelWithVelocity>>(
    `/api/v1/channels?${params.toString()}`,
    { token }
  );
}

/** Fetch distinct category tags and counts for dropdown filters, scoped to active filters (excluding category_tags). */
export async function getCategoryTags(
  token?: string,
  filters?: Omit<ChannelFilters, "category_tags" | "niche_tags" | "sort_by" | "sort_order">
): Promise<CategoryTagOption[]> {
  const params = new URLSearchParams();
  if (filters) {
    if (filters.platform && filters.platform !== "all") params.set("platform", filters.platform);
    if (filters.comment_tier && filters.comment_tier !== "all") params.set("comment_tier", filters.comment_tier);
    if (filters.gate0_statuses && filters.gate0_statuses.length > 0) {
      filters.gate0_statuses.forEach((s) => params.append("gate0_statuses", s));
    }
    if (filters.search_query && filters.search_query.trim().length > 0) {
      params.set("search_query", filters.search_query.trim());
    }
    if (filters.min_subscriber_count != null) params.set("min_subscriber_count", String(filters.min_subscriber_count));
    if (filters.max_subscriber_count != null) params.set("max_subscriber_count", String(filters.max_subscriber_count));
    if (filters.min_avg_views != null) params.set("min_avg_views", String(filters.min_avg_views));
    if (filters.max_avg_views != null) params.set("max_avg_views", String(filters.max_avg_views));
    if (filters.min_avg_comments != null) params.set("min_avg_comments", String(filters.min_avg_comments));
    if (filters.max_avg_comments != null) params.set("max_avg_comments", String(filters.max_avg_comments));
    if (filters.inactive_filter) params.set("inactive_filter", "true");
    if (filters.incomplete_only) params.set("incomplete_only", "true");
    if (filters.last_active_from) params.set("last_active_from", filters.last_active_from);
    if (filters.last_active_to) params.set("last_active_to", filters.last_active_to);
  }
  const qs = params.toString();
  const response = await apiFetch<{ tags: string[]; tag_counts?: CategoryTagOption[] }>(
    `/api/v1/channels/category-tags${qs ? `?${qs}` : ""}`,
    { token }
  );
  if (response.tag_counts && response.tag_counts.length > 0) {
    return response.tag_counts;
  }
  return response.tags.map((tag) => ({ tag, count: 0 }));
}

/** @deprecated Use getCategoryTags */
export const getNicheTags = getCategoryTags;

/** Fetch Gate 0 statuses and counts for dropdown filters. */
export async function getGate0Statuses(token?: string): Promise<Gate0StatusOption[]> {
  const response = await apiFetch<{ status_counts?: Gate0StatusOption[] }>(
    "/api/v1/channels/gate0-statuses",
    { token }
  );
  return response.status_counts ?? [];
}

/** Fetch a single channel with all related data. */
export async function getChannel(
  id: string,
  token?: string
): Promise<ChannelDetail> {
  return apiFetch<ChannelDetail>(`/api/v1/channels/${id}`, { token });
}

/** Delete channel snapshots/history while keeping the channel record. */
export async function deleteChannelHistory(
  channelId: string,
  token?: string
): Promise<ChannelDeleteResponse> {
  return apiFetch<ChannelDeleteResponse>(`/api/v1/channels/${channelId}/history`, {
    method: "DELETE",
    token,
  });
}

/** Delete channel and related rows permanently. */
export async function deleteChannelCompletely(
  channelId: string,
  token?: string
): Promise<ChannelDeleteResponse> {
  return apiFetch<ChannelDeleteResponse>(`/api/v1/channels/${channelId}`, {
    method: "DELETE",
    token,
  });
}

/** Update a channel's do-not-contact status. */
export async function updateChannelDoNotContact(
  channelId: string,
  payload: UpdateChannelDoNotContactRequest,
  token?: string
): Promise<ChannelDetail> {
  return apiFetch<ChannelDetail>(`/api/v1/channels/${channelId}/do-not-contact`, {
    method: "PATCH",
    body: payload,
    token,
  });
}

/** Fetch velocity data for a channel. */
export async function getVelocity(
  channelId: string,
  token?: string
): Promise<VelocityScore> {
  return apiFetch<VelocityScore>(`/api/v1/velocity/${channelId}`, { token });
}

/** Trigger a Gate 0 compliance check for a channel. */
export async function triggerGate0Check(
  channelId: string,
  token?: string
): Promise<Gate0CheckResponse> {
  return apiFetch<Gate0CheckResponse>(`/api/v1/gate0/check/${channelId}`, {
    method: "POST",
    token,
  });
}

/** Search for lookalike channels by seed creator names. */
export async function searchLookalikes(
  seedNames: string[],
  token?: string
): Promise<LookalikeSearchResponse> {
  return apiFetch<LookalikeSearchResponse>("/api/v1/lookalike/search", {
    method: "POST",
    body: { seed_names: seedNames },
    token,
  });
}

/** Get previous lookalike search results. */
export async function getLookalikeResults(
  token?: string
): Promise<LookalikeMatch[]> {
  return apiFetch<LookalikeMatch[]>("/api/v1/lookalike/results", { token });
}

/** Compute lookalikes for a single channel seed (detail page). */
export async function getChannelLookalikes(
  channelId: string,
  token?: string
): Promise<ChannelLookalikeResponse> {
  return apiFetch<ChannelLookalikeResponse>(`/api/v1/lookalike/channel/${channelId}`, {
    token,
  });
}

/** Trigger a manual scrape run (admin only). */
export async function triggerScrape(
  token?: string
): Promise<ScrapeTaskResponse> {
  return apiFetch<ScrapeTaskResponse>("/api/v1/scraper/trigger", {
    method: "POST",
    token,
  });
}

/** Add a single channel manually from the intake form. */
export async function intakeManualChannel(
  payload: ManualChannelIntakeRequest,
  token?: string
): Promise<IntakeSummaryResponse> {
  return apiFetch<IntakeSummaryResponse>("/api/v1/channels/intake/manual", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Add many channels from newline/comma separated URLs. */
export async function intakeBulkChannels(
  payload: BulkChannelIntakeRequest,
  token?: string
): Promise<IntakeSummaryResponse> {
  return apiFetch<IntakeSummaryResponse>("/api/v1/channels/intake/bulk", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Resolve creator names to channel candidates for user confirmation. */
export async function resolveSeedChannels(
  payload: ResolverSeedRequest,
  token?: string
): Promise<ResolverResponse> {
  return apiFetch<ResolverResponse>("/api/v1/channels/intake/resolve", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Insert user-confirmed resolver selections. */
export async function confirmResolvedChannels(
  payload: ResolverConfirmRequest,
  token?: string
): Promise<IntakeSummaryResponse> {
  return apiFetch<IntakeSummaryResponse>("/api/v1/channels/intake/resolve/confirm", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Health check. */
export async function getHealth(): Promise<{
  status: string;
  timestamp: string;
  supabase: boolean;
  redis: boolean;
  environment: string;
}> {
  return apiFetch("/health");
}

/** Get current admin identity/capabilities. */
export async function getAdminMe(token?: string): Promise<AdminMeResponse> {
  return apiFetch<AdminMeResponse>("/api/v1/admin/me", { token });
}

/** Trigger full scrape workflow as admin. */
export async function triggerAdminScrapeNow(
  payload: AdminTaskTriggerRequest,
  token?: string
): Promise<AdminTaskTriggerResponse> {
  return apiFetch<AdminTaskTriggerResponse>("/api/v1/admin/tasks/scrape-now", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Trigger discovery-only workflow as admin. */
export async function triggerAdminDiscoveryNow(
  payload: AdminTaskTriggerRequest,
  token?: string
): Promise<AdminTaskTriggerResponse> {
  return apiFetch<AdminTaskTriggerResponse>("/api/v1/admin/tasks/discovery-now", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Trigger weekly clean-lead velocity workflow as admin. */
export async function triggerAdminWeeklyVelocityNow(
  payload: AdminTaskTriggerRequest,
  token?: string
): Promise<AdminTaskTriggerResponse> {
  return apiFetch<AdminTaskTriggerResponse>("/api/v1/admin/tasks/weekly-velocity-now", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Trigger never-scraped Rumble/Substack bootstrap as admin. */
export async function triggerAdminNeverScrapedBootstrapNow(
  payload: AdminTaskTriggerRequest,
  token?: string
): Promise<AdminTaskTriggerResponse> {
  return apiFetch<AdminTaskTriggerResponse>("/api/v1/admin/tasks/never-scraped-bootstrap-now", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Trigger Gate 0 checks for explicit channels as admin. */
export async function triggerAdminGate0Now(
  payload: Gate0BatchTriggerRequest,
  token?: string
): Promise<Gate0BatchTriggerResponse> {
  return apiFetch<Gate0BatchTriggerResponse>("/api/v1/admin/tasks/gate0-now", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Fetch Celery task status by id. */
export async function getAdminTaskStatus(
  taskId: string,
  token?: string
): Promise<AdminTaskStatusResponse> {
  return apiFetch<AdminTaskStatusResponse>(`/api/v1/admin/tasks/${taskId}`, {
    token,
  });
}

/** Fetch admin audit feed. */
export async function getAdminAudit(
  page: number,
  pageSize: number,
  token?: string
): Promise<PaginatedAdminAuditResponse> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return apiFetch<PaginatedAdminAuditResponse>(
    `/api/v1/admin/audit?${params.toString()}`,
    { token }
  );
}

/** Fetch the current Gate 0 competitor list. */
export async function getAdminCompetitors(
  token?: string
): Promise<CompetitorListResponse> {
  return apiFetch<CompetitorListResponse>("/api/v1/admin/competitors", { token });
}

/** Replace the Gate 0 competitor list. */
export async function updateAdminCompetitors(
  competitors: CompetitorDef[],
  token?: string
): Promise<CompetitorListResponse> {
  return apiFetch<CompetitorListResponse>("/api/v1/admin/competitors", {
    method: "PUT",
    body: { competitors },
    token,
  });
}

/** Fetch the current editable niche/keyword taxonomy. */
export async function getAdminKeywordTaxonomy(
  token?: string
): Promise<KeywordTaxonomyListResponse> {
  return apiFetch<KeywordTaxonomyListResponse>("/api/v1/admin/keyword-taxonomy", { token });
}

/** Replace the editable niche/keyword taxonomy. */
export async function updateAdminKeywordTaxonomy(
  taxonomy: KeywordTaxonomyDef[],
  token?: string
): Promise<KeywordTaxonomyListResponse> {
  return apiFetch<KeywordTaxonomyListResponse>("/api/v1/admin/keyword-taxonomy", {
    method: "PUT",
    body: { taxonomy },
    token,
  });
}

/** Trigger AI channel classification for unclassified or all scraped channels. */
export async function triggerAdminClassifyChannels(
  payload: ClassifyChannelsTriggerRequest,
  token?: string
): Promise<AdminTaskTriggerResponse> {
  return apiFetch<AdminTaskTriggerResponse>("/api/v1/admin/tasks/classify-channels-now", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Purge all queued/reserved/active tasks and reset Redis scraper state. */
export async function purgeAdminQueue(
  payload: PurgeQueueRequest,
  token?: string
): Promise<PurgeQueueResponse> {
  return apiFetch<PurgeQueueResponse>("/api/v1/admin/tasks/purge-all", {
    method: "POST",
    body: payload,
    token,
  });
}

/** Fetch online/offline status and task counts for all worker containers. */
export async function getAdminWorkers(token?: string): Promise<WorkerStatusResponse> {
  return apiFetch<WorkerStatusResponse>("/api/v1/admin/workers", { token });
}

/** Fetch the last N log lines from a worker container. */
export async function getAdminWorkerLogs(
  service: string,
  tail = 100,
  token?: string
): Promise<WorkerLogsResponse> {
  return apiFetch<WorkerLogsResponse>(
    `/api/v1/admin/workers/${encodeURIComponent(service)}/logs?tail=${tail}`,
    { token }
  );
}
