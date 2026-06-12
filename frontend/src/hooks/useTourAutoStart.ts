"use client";

import { useEffect } from "react";
import { useTour } from "@/components/tour/TourContext";

// Delay before calling startTour so React has time to paint.
// Dashboard is already rendered when the user clicks "Start Tour" — 400ms is enough.
// Channel detail and admin wait on API responses, so they need a longer head-start
// before TourManager begins polling for DOM targets.
const SETTLE_DELAY_FAST = 400;
const SETTLE_DELAY_SLOW = 1200;

export function useDashboardTour() {
  const {
    isHydrated,
    hasSeenWelcome,
    hasDoneTour,
    isRunning,
    activeTourId,
    startTour,
  } = useTour();

  useEffect(() => {
    if (
      !isHydrated ||
      !hasSeenWelcome ||
      hasDoneTour("dashboard") ||
      isRunning ||
      activeTourId !== null
    ) {
      return;
    }
    const t = setTimeout(() => startTour("dashboard"), SETTLE_DELAY_FAST);
    return () => clearTimeout(t);
    // Re-run only when hydration completes or welcome is marked seen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHydrated, hasSeenWelcome]);
}

export function useChannelDetailTour() {
  const {
    isHydrated,
    hasSeenWelcome,
    hasDoneTour,
    isRunning,
    activeTourId,
    startTour,
  } = useTour();

  useEffect(() => {
    if (
      !isHydrated ||
      !hasSeenWelcome ||
      hasDoneTour("channel-detail") ||
      isRunning ||
      activeTourId !== null
    ) {
      return;
    }
    const t = setTimeout(() => startTour("channel-detail"), SETTLE_DELAY_SLOW);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHydrated, hasSeenWelcome]);
}

export function useAdminTour({ enabled = true }: { enabled?: boolean } = {}) {
  const {
    isHydrated,
    isAdmin,
    hasSeenWelcome,
    hasDoneTour,
    isRunning,
    activeTourId,
    startTour,
  } = useTour();

  useEffect(() => {
    if (
      !isHydrated ||
      !isAdmin ||
      !enabled ||
      !hasSeenWelcome ||
      hasDoneTour("admin") ||
      isRunning ||
      activeTourId !== null
    ) {
      return;
    }
    const t = setTimeout(() => startTour("admin"), SETTLE_DELAY_SLOW);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHydrated, isAdmin, enabled, hasSeenWelcome]);
}
