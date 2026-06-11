"use client";

import { useEffect, useRef, useState } from "react";
import type { AdminTaskStatusResponse, Platform } from "@/types";

export interface IntakeScrapeJob {
  channelUrl: string;
  platform: Platform;
  taskId: string;
  status: AdminTaskStatusResponse | null;
  pollingError: string | null;
}

type ScrapeDisplayKind =
  | "queued"
  | "running"
  | "cf_retry"
  | "retrying"
  | "done"
  | "slot_busy"
  | "cf_failed"
  | "partial_data"
  | "url_unsupported"
  | "failed"
  | "cancelled";

interface ScrapeDisplayInfo {
  kind: ScrapeDisplayKind;
  label: string;
  popupTitle: string;
  popupBody: string;
  step: 1 | 2 | 3;
  stepColor: "blue" | "amber" | "green" | "red" | "gray";
  isTerminal: boolean;
  isSuccess: boolean;
}

const PARTIAL_DATA_CODES = new Set([
  "parse_missing_subscriber_count",
  "parse_missing_avg_views",
  "parse_missing_avg_comments",
  "parse_missing_posts_per_week",
  "parse_missing_last_active_date",
]);

function interpretJob(job: IntakeScrapeJob): ScrapeDisplayInfo {
  const { state, result } = job.status ?? { state: null, result: null };

  if (!state || state === "PENDING") {
    return {
      kind: "queued",
      label: "Waiting to start…",
      popupTitle: "Waiting in queue",
      popupBody:
        "Your channel has been saved and is waiting for the scraper to start. This usually takes just a few seconds.",
      step: 1,
      stepColor: "blue",
      isTerminal: false,
      isSuccess: false,
    };
  }

  if (state === "STARTED") {
    return {
      kind: "running",
      label: "Collecting channel data…",
      popupTitle: "Collecting data",
      popupBody:
        "The scraper is visiting this channel page and reading its metrics — subscriber count, average views, post activity, and more.",
      step: 2,
      stepColor: "blue",
      isTerminal: false,
      isSuccess: false,
    };
  }

  if (state === "RETRY") {
    const errorStr = typeof result === "string" ? result : "";
    const isCf =
      errorStr.startsWith("cloudflare_error=") ||
      errorStr.includes("block_type=");
    if (isCf) {
      return {
        kind: "cf_retry",
        label: "↻  Hit a security check — retrying automatically",
        popupTitle: "Security check detected",
        popupBody:
          "This channel’s host is showing a security challenge. The scraper is automatically retrying with a different approach. No action needed — this resolves on its own most of the time.",
        step: 2,
        stepColor: "amber",
        isTerminal: false,
        isSuccess: false,
      };
    }
    return {
      kind: "retrying",
      label: "↻  Temporary hiccup — retrying automatically",
      popupTitle: "Temporary issue",
      popupBody:
        "The scraper hit a brief connection problem and is retrying automatically. No action needed.",
      step: 2,
      stepColor: "amber",
      isTerminal: false,
      isSuccess: false,
    };
  }

  if (state === "REVOKED") {
    return {
      kind: "cancelled",
      label: "Cancelled",
      popupTitle: "Scrape cancelled",
      popupBody:
        "This scrape task was cancelled, likely due to a queue reset. You can trigger a fresh scrape from the Manual Task Triggers section above.",
      step: 2,
      stepColor: "gray",
      isTerminal: true,
      isSuccess: false,
    };
  }

  if (state === "FAILURE") {
    const errorStr = typeof result === "string" ? result : String(result ?? "");
    const isCf =
      errorStr.startsWith("cloudflare_error=") ||
      errorStr.includes("block_type=");
    if (isCf) {
      return {
        kind: "cf_failed",
        label: "✗  Blocked by security check",
        popupTitle: "Blocked by security check",
        popupBody:
          "After several attempts, the scraper couldn’t get through this channel’s security. The channel has been saved — the daily scheduled scrape will try again automatically. If the problem persists, the channel’s host may be actively blocking scrapers.",
        step: 3,
        stepColor: "red",
        isTerminal: true,
        isSuccess: false,
      };
    }
    return {
      kind: "failed",
      label: "✗  Scrape failed",
      popupTitle: "Scrape failed",
      popupBody:
        "Something went wrong while collecting data. The channel is saved in the database and the daily scrape will retry automatically. If it keeps failing, the URL may be invalid or the channel may no longer exist.",
      step: 3,
      stepColor: "red",
      isTerminal: true,
      isSuccess: false,
    };
  }

  if (state === "SUCCESS") {
    if (typeof result === "object" && result !== null) {
      const r = result as Record<string, unknown>;

      if (r.status === "skipped") {
        return {
          kind: "slot_busy",
          label: "Queue was busy — will run in next available slot",
          popupTitle: "Will run shortly",
          popupBody:
            "All scraper slots were busy when this task was picked up. It’s been placed back in the queue and will run within the next few minutes automatically.",
          step: 1,
          stepColor: "gray",
          isTerminal: true,
          isSuccess: false,
        };
      }

      if (r.status === "success") {
        return {
          kind: "done",
          label: "✓  Data collected",
          popupTitle: "Data collected",
          popupBody:
            "Scrape completed. This channel’s metrics are now in the database.",
          step: 3,
          stepColor: "green",
          isTerminal: true,
          isSuccess: true,
        };
      }

      if (r.status === "failed") {
        const errorStr = String(r.error ?? "");
        if (
          errorStr.startsWith("cloudflare_error=") ||
          errorStr.includes("block_type=")
        ) {
          return {
            kind: "cf_failed",
            label: "✗  Blocked by security check",
            popupTitle: "Blocked by security check",
            popupBody:
              "After several attempts, the scraper couldn’t get through this channel’s security. The channel has been saved — the daily scheduled scrape will try again automatically.",
            step: 3,
            stepColor: "red",
            isTerminal: true,
            isSuccess: false,
          };
        }
        if (errorStr.startsWith("reason=")) {
          const reasonMatch = errorStr.match(/reason=([^;]+)/);
          const reasonCode = reasonMatch?.[1]?.trim() ?? "";
          if (reasonCode === "unsupported_rumble_url_shape") {
            return {
              kind: "url_unsupported",
              label: "✗  URL format not recognised",
              popupTitle: "URL not recognised",
              popupBody:
                "This URL isn’t in a format the scraper understands. The channel has been saved to the database, but it won’t be scraped until a valid URL is provided. Check that the URL follows the expected format (e.g. rumble.com/c/channelname).",
              step: 3,
              stepColor: "red",
              isTerminal: true,
              isSuccess: false,
            };
          }
          if (PARTIAL_DATA_CODES.has(reasonCode)) {
            return {
              kind: "partial_data",
              label: "✓  Saved — some metrics unavailable",
              popupTitle: "Saved with partial data",
              popupBody:
                "Some metrics (like subscriber count or post frequency) weren’t visible on this channel’s page. What was available has been saved. The daily scrape will try to fill in the gaps automatically.",
              step: 3,
              stepColor: "amber",
              isTerminal: true,
              isSuccess: false,
            };
          }
        }
        return {
          kind: "failed",
          label: "✗  Scrape failed",
          popupTitle: "Scrape failed",
          popupBody:
            "Something went wrong while collecting data. The channel is saved in the database and the daily scrape will retry automatically. If it keeps failing, the URL may be invalid or the channel may no longer exist.",
          step: 3,
          stepColor: "red",
          isTerminal: true,
          isSuccess: false,
        };
      }
    }
  }

  return {
    kind: "queued",
    label: "Waiting to start…",
    popupTitle: "Waiting in queue",
    popupBody:
      "Your channel has been saved and is waiting for the scraper to start.",
    step: 1,
    stepColor: "blue",
    isTerminal: false,
    isSuccess: false,
  };
}

const STEP_DOT_CLASSES: Record<
  ScrapeDisplayInfo["stepColor"],
  { active: string; pulse: string }
> = {
  blue: {
    active: "bg-[#1A1A2E] border-[#1A1A2E]",
    pulse: "bg-[#1A1A2E]/20",
  },
  amber: {
    active: "bg-[#C9A84C] border-[#C9A84C]",
    pulse: "bg-[#C9A84C]/20",
  },
  green: { active: "bg-[#4F8A5B] border-[#4F8A5B]", pulse: "" },
  red: { active: "bg-[#B22222] border-[#B22222]", pulse: "" },
  gray: { active: "bg-[#A0A0A0] border-[#A0A0A0]", pulse: "" },
};

function InfoPopup({ title, body }: { title: string; body: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-[#C9A84C] text-[9px] font-bold text-[#C9A84C] hover:bg-[#FFF8DF] focus:outline-none"
        aria-label="More information"
      >
        i
      </button>
      {open && (
        <div className="absolute left-6 top-0 z-50 w-64 rounded-lg border border-[#E8E4DC] bg-white p-3 shadow-lg">
          <p className="mb-1 text-xs font-semibold text-[#1A1A2E]">{title}</p>
          <p className="text-[11px] leading-relaxed text-[#6B6B6B]">{body}</p>
        </div>
      )}
    </div>
  );
}

function StepDot({
  stepNum,
  currentStep,
  color,
  isTerminal,
  label,
}: {
  stepNum: 1 | 2 | 3;
  currentStep: 1 | 2 | 3;
  color: ScrapeDisplayInfo["stepColor"];
  isTerminal: boolean;
  label: string;
}) {
  const isActive = stepNum === currentStep;
  const isComplete = stepNum < currentStep || (stepNum === currentStep && isTerminal);
  const isFuture = stepNum > currentStep;
  const dotClasses = STEP_DOT_CLASSES[color];
  const animate = isActive && !isTerminal;

  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative flex h-5 w-5 items-center justify-center">
        {animate && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-50 ${dotClasses.pulse}`}
          />
        )}
        <span
          className={`relative inline-flex h-3.5 w-3.5 rounded-full border-2 ${
            isComplete || isActive
              ? dotClasses.active
              : isFuture
              ? "border-[#D8D2C8] bg-white"
              : "border-[#D8D2C8] bg-white"
          }`}
        />
      </div>
      <span
        className={`text-center text-[10px] leading-tight ${
          isActive ? "font-semibold text-[#1A1A2E]" : "text-[#9B9B9B]"
        }`}
      >
        {label}
      </span>
    </div>
  );
}

function StepConnector({ filled }: { filled: boolean }) {
  return (
    <div
      className={`mb-4 h-0.5 flex-1 ${filled ? "bg-[#1A1A2E]/30" : "bg-[#E8E4DC]"}`}
    />
  );
}

function JobRow({ job }: { job: IntakeScrapeJob }) {
  const info = interpretJob(job);
  const isStep2Complete = info.step > 2 || (info.step === 2 && info.isTerminal);

  return (
    <div className="rounded-lg border border-[#E8E4DC] bg-[#FBFAF7] px-3 py-2.5">
      <p className="mb-2.5 truncate text-xs font-medium text-[#1A1A2E]" title={job.channelUrl}>
        {job.channelUrl}
      </p>

      <div className="mb-2 flex items-start gap-0">
        <StepDot
          stepNum={1}
          currentStep={info.step}
          color={info.stepColor}
          isTerminal={info.isTerminal}
          label="In Queue"
        />
        <StepConnector filled={info.step > 1} />
        <StepDot
          stepNum={2}
          currentStep={info.step}
          color={info.stepColor}
          isTerminal={info.isTerminal}
          label={`Collecting${"\n"}Data`}
        />
        <StepConnector filled={isStep2Complete} />
        <StepDot
          stepNum={3}
          currentStep={info.step}
          color={info.stepColor}
          isTerminal={info.isTerminal}
          label="Complete"
        />
      </div>

      <div className="flex items-center gap-1.5">
        <p
          className={`flex-1 text-[11px] ${
            info.stepColor === "green"
              ? "text-[#4F8A5B]"
              : info.stepColor === "red"
              ? "text-[#B22222]"
              : info.stepColor === "amber"
              ? "text-[#7A5B00]"
              : "text-[#6B6B6B]"
          }`}
        >
          {info.label}
        </p>
        <InfoPopup title={info.popupTitle} body={info.popupBody} />
      </div>

      {job.pollingError && (
        <p className="mt-1 text-[10px] text-[#B22222]">
          Could not refresh status — will retry
        </p>
      )}
    </div>
  );
}

interface SummaryBarProps {
  jobs: IntakeScrapeJob[];
}

function SummaryBar({ jobs }: SummaryBarProps) {
  const counts = jobs.reduce(
    (acc, job) => {
      const info = interpretJob(job);
      if (info.isSuccess) acc.done++;
      else if (info.isTerminal) acc.failed++;
      else if (info.kind === "running") acc.collecting++;
      else if (info.kind === "cf_retry" || info.kind === "retrying") acc.retrying++;
      else acc.queued++;
      return acc;
    },
    { done: 0, collecting: 0, retrying: 0, queued: 0, failed: 0 }
  );

  const parts: string[] = [];
  if (counts.done > 0) parts.push(`${counts.done} done`);
  if (counts.collecting > 0) parts.push(`${counts.collecting} collecting`);
  if (counts.retrying > 0) parts.push(`${counts.retrying} retrying`);
  if (counts.queued > 0) parts.push(`${counts.queued} queued`);
  if (counts.failed > 0) parts.push(`${counts.failed} failed`);

  return (
    <p className="mb-2 text-[11px] text-[#6B6B6B]">{parts.join(" · ")}</p>
  );
}

interface IntakeScrapeProgressProps {
  jobs: IntakeScrapeJob[];
  onDismiss: () => void;
}

const AUTO_DISMISS_SUCCESS_MS = 10_000;
const AUTO_DISMISS_SLOT_BUSY_MS = 20_000;

export function IntakeScrapeProgress({
  jobs,
  onDismiss,
}: IntakeScrapeProgressProps) {
  const allTerminal = jobs.length > 0 && jobs.every((j) => interpretJob(j).isTerminal);
  const allSuccess =
    allTerminal && jobs.every((j) => interpretJob(j).isSuccess);
  const allSlotBusy =
    allTerminal && jobs.every((j) => interpretJob(j).kind === "slot_busy");
  const shouldAutoDismiss = allSuccess || allSlotBusy;
  const autoDismissMs = allSuccess
    ? AUTO_DISMISS_SUCCESS_MS
    : AUTO_DISMISS_SLOT_BUSY_MS;

  const [countdown, setCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (!shouldAutoDismiss) {
      setCountdown(null);
      return;
    }
    setCountdown(autoDismissMs);
    const tick = window.setInterval(() => {
      setCountdown((prev) => {
        if (prev === null) return null;
        const next = prev - 200;
        if (next <= 0) {
          window.clearInterval(tick);
          onDismiss();
          return 0;
        }
        return next;
      });
    }, 200);
    return () => window.clearInterval(tick);
  }, [shouldAutoDismiss, autoDismissMs, onDismiss]);

  const isSingle = jobs.length === 1;

  return (
    <div className="mt-3 rounded-lg border border-[#E8E4DC] bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-[#1A1A2E]">
          Scrape Status{jobs.length > 1 ? ` · ${jobs.length} channels` : ""}
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="text-[11px] text-[#9B9B9B] hover:text-[#1A1A2E]"
          aria-label="Dismiss scrape status"
        >
          dismiss
        </button>
      </div>

      {!isSingle && <SummaryBar jobs={jobs} />}

      <div
        className={`space-y-2 ${!isSingle ? "max-h-52 overflow-y-auto pr-0.5" : ""}`}
      >
        {jobs.map((job) => (
          <JobRow key={job.taskId} job={job} />
        ))}
      </div>

      {shouldAutoDismiss && countdown !== null && countdown > 0 && (
        <div className="mt-2 h-0.5 w-full overflow-hidden rounded-full bg-[#E8E4DC]">
          <div
            className="h-full rounded-full bg-[#4F8A5B] transition-[width] duration-200"
            style={{ width: `${(countdown / autoDismissMs) * 100}%` }}
          />
        </div>
      )}
    </div>
  );
}
