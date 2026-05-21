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
  const realtimeTables = useMemo(
    () => [
      { table: "channels" },
      { table: "velocity_scores" },
      { table: "gate0_results" },
    ],
    []
  );

  const fetchChannels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getChannels(filters, page, pageSize, token);
      setChannels(result.data);
      setTotal(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch channels");
      setChannels([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters, page, pageSize, token]);

  useEffect(() => {
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }
    debounceTimer.current = setTimeout(() => {
      void fetchChannels();
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
    onRefresh: fetchChannels,
  });

  return { channels, total, loading, error, refetch: fetchChannels };
}
