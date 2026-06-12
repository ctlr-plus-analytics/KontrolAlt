/**
 * useChannelSearch - debounced backend-powered channel search for dropdown UX.
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import { getChannels, type ChannelWithVelocity } from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";

interface UseChannelSearchReturn {
  results: ChannelWithVelocity[];
  loading: boolean;
}

export function useChannelSearch(query: string): UseChannelSearchReturn {
  const { session } = useAuth();
  const token = session?.access_token;
  const [results, setResults] = useState<ChannelWithVelocity[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const normalizedQuery = useMemo(() => query.trim(), [query]);

  useEffect(() => {
    if (!normalizedQuery) {
      return;
    }

    let cancelled = false;
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const response = await getChannels(
          {
            search_query: normalizedQuery,
            sort_by: "avg_comments",
            sort_order: "desc",
          },
          1,
          8,
          token
        );
        if (!cancelled) {
          setResults(response.data);
        }
      } catch {
        if (!cancelled) {
          setResults([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [normalizedQuery, token]);

  return {
    results: normalizedQuery ? results : [],
    loading: normalizedQuery ? loading : false,
  };
}
