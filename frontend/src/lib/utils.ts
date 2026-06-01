/**
 * Utility helpers for the Kontrol_Alt frontend.
 */

import { formatDistanceToNowStrict, differenceInDays } from "date-fns";
import type { CommentTier, Platform } from "@/types";

/**
 * Format a number with comma separators.
 * Abbreviates millions (e.g. 1,200,000 → "1.2M").
 */
export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) {
    return "N/A";
  }
  if (n >= 1_000_000) {
    const millions = n / 1_000_000;
    return `${millions.toFixed(1).replace(/\.0$/, "")}M`;
  }
  return n.toLocaleString("en-US");
}

/**
 * Format a velocity percentage value.
 * Returns "+42.3%", "-12.1%", or "N/A" for null.
 */
export function formatVelocity(v: number | null): string {
  if (v === null || v === undefined) {
    return "N/A";
  }
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

/**
 * Format engagement rate as a percent using avg comments / subscribers.
 * Returns "N/A" when either value is missing or subscribers is <= 0.
 */
export function formatEngagementRate(
  subscriberCount: number | null | undefined,
  avgComments: number | null | undefined
): string {
  if (
    subscriberCount === null ||
    subscriberCount === undefined ||
    avgComments === null ||
    avgComments === undefined ||
    subscriberCount <= 0
  ) {
    return "N/A";
  }

  const engagementRate = (avgComments / subscriberCount) * 100;
  const cappedRate = Math.min(engagementRate, 100);
  return `${cappedRate.toFixed(3)}%`;
}

/**
 * Returns a human-readable "time ago" string.
 * e.g. "3 days ago", "2 weeks ago", "just now"
 */
export function timeAgo(dateString: string | null | undefined): string {
  if (!dateString) {
    return "N/A";
  }
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();

  if (diffMs < 60_000) {
    return "just now";
  }

  return `${formatDistanceToNowStrict(date)} ago`;
}

/**
 * Checks if a channel is inactive (no upload within threshold days).
 */
export function isInactive(
  lastActiveDate: string | null | undefined,
  thresholdDays: number = 90
): boolean {
  if (!lastActiveDate) {
    return false;
  }
  return differenceInDays(new Date(), new Date(lastActiveDate)) > thresholdDays;
}

/**
 * Returns Tailwind class string for a platform.
 */
export function getPlatformColor(platform: Platform): string {
  switch (platform) {
    case "rumble":
      return "bg-[#E8712B]/10 text-[#E8712B]";
    case "substack":
      return "bg-[#FF6719]/10 text-[#C04A0E]";
  }
}

/**
 * Returns the display label for a comment tier.
 */
export function getCommentTierLabel(tier: CommentTier): string {
  switch (tier) {
    case "active":
      return "Active";
    case "sweet_spot":
      return "Sweet Spot";
    case "whale":
      return "Whale";
  }
}

/**
 * Truncate a string to maxLength characters with ellipsis.
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) {
    return str;
  }
  return `${str.slice(0, maxLength)}…`;
}

/**
 * className merger utility — joins class strings, filtering out falsy values.
 */
export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}
