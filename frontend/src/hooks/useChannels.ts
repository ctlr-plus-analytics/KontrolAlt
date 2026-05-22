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
  error: string | null;
  refetch: () => void;
}

interface FetchChannelsOptions {
  showLoading?: boolean;
  preserveDataOnError?: boolean;
}

export function useChannels(
  filters: Partial<ChannelFilters>,
  page: number,
  pageSize: number = 25,
  initialChannels: ChannelWithVelocity[] = [],
  initialTotal: number = 0
): UseChannelsReturn {
  const { session } = useAuth();
  const token = session?.access_token;
  const [channels, setChannels] = useState<ChannelWithVelocity[]>(initialChannels);
  const [total, setTotal] = useState<number>(initialTotal);
  const [loading, setLoading] = useState<boolean>(initialChannels.length === 0);
  const [error, setError] = useState<string | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latestRequestId = useRef<number>(0);
  const hasVisibleData = useRef<boolean>(initialChannels.length > 0);
  const realtimeTables = useMemo(
    () => [
      { table: "channels" },
      { table: "gate0_results" },
    ],
    []
  );

  const fetchChannels = useCallback(async (options: FetchChannelsOptions = {}) => {
    const {
      showLoading = true,
      preserveDataOnError = false,
    } = options;
    const requestId = latestRequestId.current + 1;
    latestRequestId.current = requestId;

    if (showLoading && !hasVisibleData.current) {
      setLoading(true);
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
    void fetchChannels({ showLoading: true });
  }, [fetchChannels]);

  useEffect(() => {
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
  }, [fetchChannels]);

  useRealtimeRefresh({
    channelKey: `channels-live-${page}-${pageSize}`,
    tables: realtimeTables,
    enabled: Boolean(token),
    onRefresh: refreshChannelsInBackground,
  });

  return {
    channels,
    total,
    loading,
    error,
    refetch: refetchChannels,
  };
}
