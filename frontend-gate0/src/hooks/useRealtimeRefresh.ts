/**
 * useRealtimeRefresh - subscribe to Supabase table changes and trigger refresh.
 */
"use client";

import { useEffect, useRef } from "react";
import { createClient } from "@/lib/supabase/client";

interface UseRealtimeRefreshOptions {
  channelKey: string;
  tables: Array<{
    table: string;
    filter?: string;
  }>;
  enabled?: boolean;
  debounceMs?: number;
  onRefresh: () => void;
}

export function useRealtimeRefresh({
  channelKey,
  tables,
  enabled = true,
  debounceMs = 500,
  onRefresh,
}: UseRealtimeRefreshOptions): void {
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tableSignature = tables
    .map((entry) => `${entry.table}:${entry.filter ?? ""}`)
    .join("|");

  useEffect(() => {
    if (!enabled || tables.length === 0) {
      return;
    }

    const supabase = createClient();
    const channel = supabase.channel(channelKey);

    for (const entry of tables) {
      channel.on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: entry.table,
          filter: entry.filter,
        },
        () => {
          if (refreshTimer.current) {
            clearTimeout(refreshTimer.current);
          }
          refreshTimer.current = setTimeout(() => {
            onRefresh();
          }, debounceMs);
        }
      );
    }

    channel.subscribe();

    return () => {
      if (refreshTimer.current) {
        clearTimeout(refreshTimer.current);
      }
      void supabase.removeChannel(channel);
    };
  }, [channelKey, debounceMs, enabled, onRefresh, tableSignature, tables]);
}
