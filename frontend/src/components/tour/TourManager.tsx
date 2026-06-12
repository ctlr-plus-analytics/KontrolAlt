"use client";

import { useEffect, useMemo } from "react";
import { usePathname } from "next/navigation";
import {
  Joyride,
  type EventData,
  EVENTS,
  STATUS,
} from "react-joyride";
import { useTour } from "./TourContext";
import { TourTooltip } from "./TourTooltip";
import {
  DASHBOARD_STEPS,
  CHANNEL_DETAIL_STEPS,
  ADMIN_STEPS,
} from "./TourSteps";

export function TourManager() {
  const {
    activeTourId,
    isRunning,
    setRunning,
    stopTour,
    markTourComplete,
    markTourSkipped,
  } = useTour();
  const pathname = usePathname();

  const steps = useMemo(() => {
    if (activeTourId === "dashboard") return DASHBOARD_STEPS;
    if (activeTourId === "channel-detail") return CHANNEL_DETAIL_STEPS;
    if (activeTourId === "admin") return ADMIN_STEPS;
    return [];
  }, [activeTourId]);

  // Route guard — stop tour if user navigates away from the relevant page
  useEffect(() => {
    if (!activeTourId || !isRunning) return;
    if (activeTourId === "dashboard" && pathname !== "/") stopTour();
    if (activeTourId === "channel-detail" && !pathname.startsWith("/channel/")) stopTour();
    if (activeTourId === "admin" && pathname !== "/admin") stopTour();
  }, [pathname, activeTourId, isRunning, stopTour]);

  // Target readiness — poll until ALL step targets exist in the DOM, then start.
  // Checks all targets (not just the first) so data-heavy pages finish rendering
  // before the tour begins. 20 attempts × 300ms = up to 6 seconds of patience.
  useEffect(() => {
    if (!activeTourId || isRunning || steps.length === 0) return;

    let attempts = 0;
    let timeoutId: ReturnType<typeof setTimeout>;

    const check = () => {
      const missing = steps
        .map((s) => s.target as string)
        .find((sel) => !document.querySelector(sel));

      if (!missing) {
        setRunning(true);
        return;
      }
      attempts++;
      if (attempts < 20) {
        timeoutId = setTimeout(check, 300);
      } else {
        console.warn(`[Tour] Target "${missing}" not found after ${attempts} attempts — tour cancelled.`);
        stopTour();
      }
    };

    const rafId = requestAnimationFrame(check);
    return () => {
      cancelAnimationFrame(rafId);
      clearTimeout(timeoutId);
    };
  }, [activeTourId, isRunning, steps, setRunning, stopTour]);

  function handleEvent({ type, status }: EventData) {
    if (type !== EVENTS.TOUR_END) return;
    if (status === STATUS.FINISHED && activeTourId) {
      markTourComplete(activeTourId);
    } else if (status === STATUS.SKIPPED && activeTourId) {
      markTourSkipped(activeTourId);
    }
    stopTour();
  }

  // activeTourId is always null during SSR (effects don't run server-side),
  // so this also serves as the SSR guard — Joyride never renders on the server.
  if (!activeTourId) return null;

  return (
    <Joyride
      key={activeTourId}
      steps={steps}
      run={isRunning}
      continuous
      tooltipComponent={TourTooltip}
      // Keep tooltip clear of the 56px fixed TopBar on every side.
      // shiftOptions slides the tooltip back into view; flipOptions triggers
      // a placement flip before it would collide with the header.
      floatingOptions={{
        shiftOptions: { padding: { top: 80, right: 16, bottom: 16, left: 16 } },
        flipOptions: { padding: { top: 80, right: 16, bottom: 16, left: 16 } },
      }}
      options={{
        skipBeacon: true,
        overlayClickAction: false,
        blockTargetInteraction: false,
        zIndex: 10000,
        overlayColor: "rgba(0, 0, 0, 0.55)",
        arrowColor: "#1A1A2E",
        buttons: ["back", "primary", "skip"],
      }}
      onEvent={handleEvent}
    />
  );
}
