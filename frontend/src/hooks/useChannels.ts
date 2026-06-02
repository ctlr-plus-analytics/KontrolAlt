/**
 * useChannels — hook for fetching paginated channel data with filters.
 */
"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import type { ChannelFilters } from "@/types";
import { getChannels, type ChannelWithVelocity } from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import { useRealtimeRefresh } from "@/hooks/useRealtimeRefresh";

interface UseChannelsReturn {
  channels: ChannelWithVelocity[];
  total: number;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refetch: () => void;
}

interface FetchChannelsOptions {
  showLoading?: boolean;
  preserveDataOnError?: boolean;
  isManualRefresh?: boolean;
}

export function useChannels(
  filters: Partial<ChannelFilters>,
  page: number,
  pageSize: number = 25,
  initialChannels: ChannelWithVelocity[] = [],
  initialTotal: number = 0
): UseChannelsReturn {
  const { session, loading: authLoading } = useAuth();
  const token = session?.access_token;
  const [channels, setChannels] = useState<ChannelWithVelocity[]>(initialChannels);
  const [total, setTotal] = useState<number>(initialTotal);
  const [loading, setLoading] = useState<boolean>(initialChannels.length === 0);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestRequestId = useRef<number>(0);
  const hasVisibleData = useRef<boolean>(initialChannels.length > 0);
  const skippedInitialServerData = useRef<boolean>(false);
  const realtimeTables = useMemo(
    () => [
      { table: "channels" },
      { table: "gate0_results" },
    ],
    []
  );

  const fetchChannels = useCallback(async (options: FetchChannelsOptions = {}) => {
    if (!token) {
      setLoading(false);
      return;
    }

    const {
      showLoading = true,
      preserveDataOnError = false,
      isManualRefresh = false,
    } = options;
    const requestId = latestRequestId.current + 1;
    latestRequestId.current = requestId;

    if (showLoading && !hasVisibleData.current) {
      setLoading(true);
    }
    if (isManualRefresh) {
      setRefreshing(true);
    }
    setError(null);
    try {
      const result = await getChannels(filters, page, pageSize, token);
      if (requestId !== latestRequestId.current) {
        return;
      }
      setChannels(result.data);
      setTotal(result.total);
      hasVisibleData.current = result.data.length > 0;
    } catch (err) {
      if (requestId !== latestRequestId.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to fetch channels");
      if (!preserveDataOnError) {
        setChannels([]);
        setTotal(0);
        hasVisibleData.current = false;
      }
    } finally {
      if (requestId === latestRequestId.current) {
        setLoading(false);
        if (isManualRefresh) {
          setRefreshing(false);
        }
      }
    }
  }, [filters, page, pageSize, token]);

  const refreshChannelsInBackground = useCallback(() => {
    void fetchChannels({
      showLoading: false,
      preserveDataOnError: true,
    });
  }, [fetchChannels]);

  const refetchChannels = useCallback(() => {
    void fetchChannels({ showLoading: true, isManualRefresh: true });
  }, [fetchChannels]);

  useEffect(() => {
    if (authLoading) {
      return;
    }
    if (!token) {
      const id = setTimeout(() => setLoading(false), 0);
      return () => clearTimeout(id);
    }
    if (
      !skippedInitialServerData.current &&
      initialChannels.length > 0 &&
      page === 1 &&
      isDefaultInitialQuery(filters)
    ) {
      skippedInitialServerData.current = true;
      return;
    }

    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }
    debounceTimer.current = setTimeout(() => {
      void fetchChannels({ showLoading: true });
    }, 300);

    return () => {
      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }
    };
  }, [authLoading, fetchChannels, filters, initialChannels.length, page, token]);

  useRealtimeRefresh({
    channelKey: `channels-live-${page}-${pageSize}`,
    tables: realtimeTables,
    enabled: Boolean(token),
    onRefresh: refreshChannelsInBackground,
  });

  // Supabase Realtime WebSockets silently drop; poll as fallback so the dashboard never goes stale.
  useEffect(() => {
    if (!token) return;
    const id = setInterval(() => {
      refreshChannelsInBackground();
    }, 30_000);
    return () => clearInterval(id);
  }, [token, refreshChannelsInBackground]);

  return {
    channels,
    total,
    loading,
    refreshing,
    error,
    refetch: refetchChannels,
  };
}

function isDefaultInitialQuery(filters: Partial<ChannelFilters>): boolean {
  return (
    (filters.platform === undefined || filters.platform === "all") &&
    (filters.comment_tier === undefined || filters.comment_tier === "all") &&
    (filters.gate0_statuses?.length ?? 0) === 0 &&
    (filters.category_tags?.length ?? 0) === 0 &&
    !filters.search_query &&
    filters.min_subscriber_count == null &&
    filters.max_subscriber_count == null &&
    filters.min_avg_views == null &&
    filters.max_avg_views == null &&
    filters.min_avg_comments == null &&
    filters.max_avg_comments == null &&
    !filters.last_active_from &&
    !filters.last_active_to &&
    !filters.inactive_filter &&
    !filters.incomplete_only &&
    (filters.sort_by === undefined || filters.sort_by === "avg_comments") &&
    (filters.sort_order === undefined || filters.sort_order === "desc")
  );
}
