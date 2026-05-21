/**
 * useVelocity — hook for fetching velocity data for a channel.
 */
"use client";

import { useState, useEffect } from "react";
import type { VelocityScore } from "@/types";
import { getVelocity } from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";

interface UseVelocityReturn {
  velocity: VelocityScore | null;
  loading: boolean;
  error: string | null;
}

export function useVelocity(channelId: string): UseVelocityReturn {
  const { session } = useAuth();
  const [velocity, setVelocity] = useState<VelocityScore | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!channelId) return;

    const fetchVelocity = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getVelocity(channelId, session?.access_token);
        setVelocity(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to fetch velocity"
        );
      } finally {
        setLoading(false);
      }
    };

    void fetchVelocity();
  }, [channelId, session?.access_token]);

  return { velocity, loading, error };
}
