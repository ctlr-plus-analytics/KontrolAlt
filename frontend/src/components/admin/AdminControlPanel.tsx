"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAdminAudit,
  getAdminMe,
  getAdminSettings,
  getAdminTaskStatus,
  patchAdminSettings,
  triggerAdminDiscoveryNow,
  triggerAdminGate0Now,
  triggerAdminWeeklyVelocityNow,
  triggerAdminScrapeNow,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import type {
  AdminAuditRecord,
  AdminTaskStatusResponse,
  Gate0Competitor,
  SystemSettings,
} from "@/types";
import { Button } from "@/components/ui/Button";

const AUDIT_PAGE_SIZE = 20;
const TASK_POLL_INTERVAL_MS = 2500;
const TERMINAL_TASK_STATES = new Set(["SUCCESS", "FAILURE", "REVOKED"]);
const ERROR_TASK_STATES = new Set(["FAILURE", "REVOKED"]);
const WEEKDAY_OPTIONS: Array<SystemSettings["weekly_velocity_utc_day"]> = [
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
  "sat",
  "sun",
];
const DEFAULT_GATE0_COMPETITORS: Gate0Competitor[] = [
  { brand: "Noble Gold", domains: ["noblegold.com"] },
  { brand: "Birch Gold", domains: ["birchgold.com"] },
  { brand: "Patriot Gold", domains: ["patriotgold.com"] },
  { brand: "Kirk Elliot", domains: ["kirkelliot.com"] },
];

type ManualTaskKind = "scrape" | "discovery" | "weekly-velocity" | "gate0";

interface ManualTaskRun {
  id: string;
  kind: ManualTaskKind;
  label: string;
  taskIds: string[];
  triggeredAt: string;
  message: string;
  statuses: Record<string, AdminTaskStatusResponse>;
  pollingError: string | null;
}

interface OperationalForm {
  scrape_dispatch_batch_size: number;
  scrape_dispatch_pause_seconds: number;
  scrape_run_max_channels: number;
  scrape_daily_byte_budget_mb: number;
  scrape_retry_base_delay_seconds: number;
  scrape_retry_jitter_min: number;
  scrape_retry_jitter_max: number;
  scrape_circuit_breaker_fail_threshold: number;
  scrape_circuit_breaker_window_seconds: number;
  scrape_circuit_breaker_cooldown_seconds: number;
  gate0_daily_queue_limit: number;
  gate0_clean_recheck_days: number;
  scraper_human_delay_min_seconds: number;
  scraper_human_delay_max_seconds: number;
  scraper_content_wait_min_bytes: number;
  scraper_content_wait_timeout_seconds: number;
  scraper_content_wait_poll_seconds: number;
  discovery_serper_query_limit: number;
  discovery_results_per_query: number;
  discovery_max_pages_per_query: number;
  discovery_insert_limit: number;
  discovery_query_stagnation_limit: number;
  discovery_global_stop_no_new: number;
  discovery_max_feedback_terms: number;
  discovery_new_scrape_limit: number;
  discovery_channel_page_size: number;
  discovery_verify_timeout_seconds: number;
}

const DEFAULT_OPERATIONAL_FORM: OperationalForm = {
  scrape_dispatch_batch_size: 8,
  scrape_dispatch_pause_seconds: 2,
  scrape_run_max_channels: 0,
  scrape_daily_byte_budget_mb: 0,
  scrape_retry_base_delay_seconds: 60,
  scrape_retry_jitter_min: 0.8,
  scrape_retry_jitter_max: 1.2,
  scrape_circuit_breaker_fail_threshold: 5,
  scrape_circuit_breaker_window_seconds: 1800,
  scrape_circuit_breaker_cooldown_seconds: 1800,
  gate0_daily_queue_limit: 200,
  gate0_clean_recheck_days: 7,
  scraper_human_delay_min_seconds: 2,
  scraper_human_delay_max_seconds: 8,
  scraper_content_wait_min_bytes: 5000,
  scraper_content_wait_timeout_seconds: 20,
  scraper_content_wait_poll_seconds: 1.5,
  discovery_serper_query_limit: 480,
  discovery_results_per_query: 20,
  discovery_max_pages_per_query: 8,
  discovery_insert_limit: 20000,
  discovery_query_stagnation_limit: 4,
  discovery_global_stop_no_new: 120,
  discovery_max_feedback_terms: 36,
  discovery_new_scrape_limit: 500,
  discovery_channel_page_size: 1000,
  discovery_verify_timeout_seconds: 15,
};

const OPERATIONAL_KEYS = Object.keys(
  DEFAULT_OPERATIONAL_FORM
) as Array<keyof OperationalForm>;

function getTaskLabel(kind: ManualTaskKind): string {
  if (kind === "scrape") {
    return "Full Scrape";
  }
  if (kind === "discovery") {
    return "Discovery";
  }
  if (kind === "weekly-velocity") {
    return "Weekly Velocity";
  }
  return "Gate 0 Batch";
}

function isTaskSettled(status?: AdminTaskStatusResponse): boolean {
  return status ? TERMINAL_TASK_STATES.has(status.state) : false;
}

function getRunState(run: ManualTaskRun): string {
  if (run.taskIds.length === 0) {
    return "Not queued";
  }
  const statuses = run.taskIds.map((taskId) => run.statuses[taskId]);
  if (statuses.some((status) => status && ERROR_TASK_STATES.has(status.state))) {
    return "Error";
  }
  if (statuses.every((status) => status?.state === "SUCCESS")) {
    return "Success";
  }
  if (statuses.some((status) => status?.state === "STARTED")) {
    return "Running";
  }
  if (statuses.some((status) => status?.state === "RETRY")) {
    return "Retrying";
  }
  if (statuses.some((status) => status?.state === "PENDING")) {
    return "Queued";
  }
  return statuses.some(Boolean) ? "Running" : "Queued";
}

function getRunStateClass(run: ManualTaskRun): string {
  const state = getRunState(run);
  if (state === "Success") {
    return "border-[#4F8A5B] bg-[#EEF7F0] text-[#2F6B3B]";
  }
  if (state === "Error") {
    return "border-[#B22222] bg-[#FDECEC] text-[#B22222]";
  }
  if (state === "Not queued") {
    return "border-[#D8D2C8] bg-[#F7F4EE] text-[#6B6B6B]";
  }
  return "border-[#C9A84C] bg-[#FFF8DF] text-[#7A5B00]";
}

function formatTaskResult(result: unknown): string | null {
  if (result === null || result === undefined) {
    return null;
  }
  if (typeof result === "string") {
    return result;
  }
  if (
    typeof result === "number" ||
    typeof result === "boolean" ||
    typeof result === "bigint"
  ) {
    return String(result);
  }
  try {
    return JSON.stringify(result);
  } catch {
    return "Result could not be displayed.";
  }
}

function normalizeCompetitors(competitors: Gate0Competitor[]): Gate0Competitor[] {
  return competitors
    .map((competitor) => ({
      brand: competitor.brand.trim().replace(/\s+/g, " "),
      domains: competitor.domains
        .map((domain) =>
          domain
            .trim()
            .toLowerCase()
            .replace(/^https?:\/\//, "")
            .split("/")[0]
        )
        .filter((domain, index, domains) => domain.length > 0 && domains.indexOf(domain) === index),
    }))
    .filter((competitor) => competitor.brand.length > 0);
}

export function AdminControlPanel() {
  const { session } = useAuth();
  const token = session?.access_token;

  const [allowed, setAllowed] = useState<boolean>(false);
  const [settings, setSettings] = useState<SystemSettings | null>(null);
  const [audit, setAudit] = useState<AdminAuditRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [message, setMessage] = useState<string>("");
  const [gate0IdsInput, setGate0IdsInput] = useState<string>("");
  const [taskRuns, setTaskRuns] = useState<ManualTaskRun[]>([]);

  const [timeInput, setTimeInput] = useState<string>("02:00");
  const [gate0Enabled, setGate0Enabled] = useState<boolean>(true);
  const [discoveryEnabled, setDiscoveryEnabled] = useState<boolean>(true);
  const [lookalikeEnabled, setLookalikeEnabled] = useState<boolean>(true);
  const [scrapeOnlyNewOrMissing, setScrapeOnlyNewOrMissing] = useState<boolean>(true);
  const [scrapeRescrapeMinHours, setScrapeRescrapeMinHours] = useState<number>(72);
  const [weeklyVelocityEnabled, setWeeklyVelocityEnabled] = useState<boolean>(true);
  const [weeklyVelocityDay, setWeeklyVelocityDay] = useState<
    SystemSettings["weekly_velocity_utc_day"]
  >("sun");
  const [weeklyVelocityTime, setWeeklyVelocityTime] = useState<string>("03:00");
  const [velocityMinAvgComments, setVelocityMinAvgComments] = useState<number>(20);
  const [velocityMinAvgViews, setVelocityMinAvgViews] = useState<number>(0);
  const [velocityMinSubscribers, setVelocityMinSubscribers] = useState<number>(0);
  const [velocityStaleHours, setVelocityStaleHours] = useState<number>(144);
  const [operational, setOperational] = useState<OperationalForm>(
    DEFAULT_OPERATIONAL_FORM
  );
  const [platformPriority, setPlatformPriority] = useState<
    ("rumble" | "bitchute" | "substack")[]
  >([
    "rumble",
    "bitchute",
    "substack",
  ]);
  const [gate0Competitors, setGate0Competitors] = useState<Gate0Competitor[]>(
    DEFAULT_GATE0_COMPETITORS
  );
  const [showAdvancedSettings, setShowAdvancedSettings] = useState<boolean>(false);

  useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;
    const run = async () => {
      try {
        const [meData, settingsData, auditData] = await Promise.all([
          getAdminMe(token),
          getAdminSettings(token),
          getAdminAudit(1, AUDIT_PAGE_SIZE, token),
        ]);
        if (cancelled) {
          return;
        }
        setAllowed(meData.roles.includes("admin"));
        setSettings(settingsData);
        setTimeInput(settingsData.daily_scrape_utc_time);
        setGate0Enabled(settingsData.gate0_enabled);
        setGate0Competitors(settingsData.gate0_competitors);
        setDiscoveryEnabled(settingsData.discovery_enabled);
        setLookalikeEnabled(settingsData.lookalike_enabled);
        setPlatformPriority(settingsData.scrape_platform_priority);
        setScrapeOnlyNewOrMissing(settingsData.scrape_only_new_or_missing_metrics);
        setScrapeRescrapeMinHours(settingsData.scrape_rescrape_min_hours);
        setWeeklyVelocityEnabled(settingsData.weekly_velocity_enabled);
        setWeeklyVelocityDay(settingsData.weekly_velocity_utc_day);
        setWeeklyVelocityTime(settingsData.weekly_velocity_utc_time);
        setVelocityMinAvgComments(settingsData.velocity_weekly_min_avg_comments);
        setVelocityMinAvgViews(settingsData.velocity_weekly_min_avg_views);
        setVelocityMinSubscribers(settingsData.velocity_weekly_min_subscribers);
        setVelocityStaleHours(settingsData.velocity_weekly_stale_hours);
        setOperational({
          scrape_dispatch_batch_size: settingsData.scrape_dispatch_batch_size,
          scrape_dispatch_pause_seconds: settingsData.scrape_dispatch_pause_seconds,
          scrape_run_max_channels: settingsData.scrape_run_max_channels,
          scrape_daily_byte_budget_mb: settingsData.scrape_daily_byte_budget_mb,
          scrape_retry_base_delay_seconds:
            settingsData.scrape_retry_base_delay_seconds,
          scrape_retry_jitter_min: settingsData.scrape_retry_jitter_min,
          scrape_retry_jitter_max: settingsData.scrape_retry_jitter_max,
          scrape_circuit_breaker_fail_threshold:
            settingsData.scrape_circuit_breaker_fail_threshold,
          scrape_circuit_breaker_window_seconds:
            settingsData.scrape_circuit_breaker_window_seconds,
          scrape_circuit_breaker_cooldown_seconds:
            settingsData.scrape_circuit_breaker_cooldown_seconds,
          gate0_daily_queue_limit: settingsData.gate0_daily_queue_limit,
          gate0_clean_recheck_days: settingsData.gate0_clean_recheck_days,
          scraper_human_delay_min_seconds:
            settingsData.scraper_human_delay_min_seconds,
          scraper_human_delay_max_seconds:
            settingsData.scraper_human_delay_max_seconds,
          scraper_content_wait_min_bytes:
            settingsData.scraper_content_wait_min_bytes,
          scraper_content_wait_timeout_seconds:
            settingsData.scraper_content_wait_timeout_seconds,
          scraper_content_wait_poll_seconds:
            settingsData.scraper_content_wait_poll_seconds,
          discovery_serper_query_limit: settingsData.discovery_serper_query_limit,
          discovery_results_per_query: settingsData.discovery_results_per_query,
          discovery_max_pages_per_query: settingsData.discovery_max_pages_per_query,
          discovery_insert_limit: settingsData.discovery_insert_limit,
          discovery_query_stagnation_limit:
            settingsData.discovery_query_stagnation_limit,
          discovery_global_stop_no_new: settingsData.discovery_global_stop_no_new,
          discovery_max_feedback_terms: settingsData.discovery_max_feedback_terms,
          discovery_new_scrape_limit: settingsData.discovery_new_scrape_limit,
          discovery_channel_page_size: settingsData.discovery_channel_page_size,
          discovery_verify_timeout_seconds:
            settingsData.discovery_verify_timeout_seconds,
        });
        setAudit(auditData.data);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setAllowed(false);
        setMessage(error instanceof Error ? error.message : "Admin access denied.");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!token) {
      return;
    }
    const pendingTaskIds = taskRuns.flatMap((run) =>
      run.taskIds.filter((taskId) => !isTaskSettled(run.statuses[taskId]))
    );
    if (pendingTaskIds.length === 0) {
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        const updates = await Promise.all(
          pendingTaskIds.map(async (taskId) => {
            try {
              const status = await getAdminTaskStatus(taskId, token);
              return { taskId, status, error: null };
            } catch (error) {
              const message =
                error instanceof Error ? error.message : "Failed to refresh task status.";
              return { taskId, status: null, error: message };
            }
          })
        );
        if (cancelled) {
          return;
        }
        setTaskRuns((currentRuns) =>
          currentRuns.map((run) => {
            const matchingUpdates = updates.filter((update) =>
              run.taskIds.includes(update.taskId)
            );
            if (matchingUpdates.length === 0) {
              return run;
            }
            const nextStatuses = { ...run.statuses };
            let pollingError = run.pollingError;
            matchingUpdates.forEach((update) => {
              if (update.status) {
                nextStatuses[update.taskId] = update.status;
                pollingError = null;
              } else if (update.error) {
                pollingError = update.error;
              }
            });
            return { ...run, statuses: nextStatuses, pollingError };
          })
        );
      })();
    }, TASK_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [taskRuns, token]);

  const movePriority = useCallback((index: number, direction: -1 | 1) => {
    setPlatformPriority((prev) => {
      const nextIndex = index + direction;
      if (nextIndex < 0 || nextIndex >= prev.length) {
        return prev;
      }
      const next = [...prev];
      const current = next[index];
      next[index] = next[nextIndex];
      next[nextIndex] = current;
      return next;
    });
  }, []);

  const dirty = useMemo(() => {
    if (!settings) {
      return false;
    }
    return (
      settings.daily_scrape_utc_time !== timeInput ||
      settings.gate0_enabled !== gate0Enabled ||
      settings.discovery_enabled !== discoveryEnabled ||
      settings.lookalike_enabled !== lookalikeEnabled ||
      settings.scrape_only_new_or_missing_metrics !== scrapeOnlyNewOrMissing ||
      settings.scrape_rescrape_min_hours !== scrapeRescrapeMinHours ||
      settings.weekly_velocity_enabled !== weeklyVelocityEnabled ||
      settings.weekly_velocity_utc_day !== weeklyVelocityDay ||
      settings.weekly_velocity_utc_time !== weeklyVelocityTime ||
      settings.velocity_weekly_min_avg_comments !== velocityMinAvgComments ||
      settings.velocity_weekly_min_avg_views !== velocityMinAvgViews ||
      settings.velocity_weekly_min_subscribers !== velocityMinSubscribers ||
      settings.velocity_weekly_stale_hours !== velocityStaleHours ||
      OPERATIONAL_KEYS.some((key) => settings[key] !== operational[key]) ||
      JSON.stringify(settings.gate0_competitors) !==
        JSON.stringify(normalizeCompetitors(gate0Competitors)) ||
      settings.scrape_platform_priority.join(",") !== platformPriority.join(",")
    );
  }, [
    discoveryEnabled,
    gate0Enabled,
    gate0Competitors,
    lookalikeEnabled,
    operational,
    platformPriority,
    scrapeOnlyNewOrMissing,
    scrapeRescrapeMinHours,
    settings,
    timeInput,
    velocityMinAvgComments,
    velocityMinAvgViews,
    velocityMinSubscribers,
    velocityStaleHours,
    weeklyVelocityDay,
    weeklyVelocityEnabled,
    weeklyVelocityTime,
  ]);

  const handleSave = useCallback(async () => {
    if (!token || !settings) {
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const updated = await patchAdminSettings(
        {
          daily_scrape_utc_time: timeInput,
          gate0_enabled: gate0Enabled,
          gate0_competitors: normalizeCompetitors(gate0Competitors),
          discovery_enabled: discoveryEnabled,
          lookalike_enabled: lookalikeEnabled,
          scrape_platform_priority: platformPriority,
          scrape_only_new_or_missing_metrics: scrapeOnlyNewOrMissing,
          scrape_rescrape_min_hours: scrapeRescrapeMinHours,
          weekly_velocity_enabled: weeklyVelocityEnabled,
          weekly_velocity_utc_day: weeklyVelocityDay,
          weekly_velocity_utc_time: weeklyVelocityTime,
          velocity_weekly_min_avg_comments: velocityMinAvgComments,
          velocity_weekly_min_avg_views: velocityMinAvgViews,
          velocity_weekly_min_subscribers: velocityMinSubscribers,
          velocity_weekly_stale_hours: velocityStaleHours,
          ...operational,
          expected_version: settings.version,
        },
        token
      );
      setSettings(updated);
      setGate0Competitors(updated.gate0_competitors);
      setMessage("Settings saved.");
      const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
      setAudit(auditData.data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  }, [
    discoveryEnabled,
    gate0Enabled,
    gate0Competitors,
    lookalikeEnabled,
    operational,
    platformPriority,
    scrapeOnlyNewOrMissing,
    scrapeRescrapeMinHours,
    settings,
    timeInput,
    token,
    velocityMinAvgComments,
    velocityMinAvgViews,
    velocityMinSubscribers,
    velocityStaleHours,
    weeklyVelocityDay,
    weeklyVelocityEnabled,
    weeklyVelocityTime,
  ]);

  const runTask = useCallback(
    async (kind: "scrape" | "discovery" | "weekly-velocity" | "gate0") => {
      if (!token) {
        return;
      }
      setMessage("");
      try {
        if (kind === "scrape") {
          const result = await triggerAdminScrapeNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
          setTaskRuns((prev) => [
            {
              id: `${kind}-${result.triggered_at}`,
              kind,
              label: getTaskLabel(kind),
              taskIds: result.task_ids,
              triggeredAt: result.triggered_at,
              message: result.message,
              statuses: {},
              pollingError: null,
            },
            ...prev.slice(0, 4),
          ]);
        } else if (kind === "discovery") {
          const result = await triggerAdminDiscoveryNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
          setTaskRuns((prev) => [
            {
              id: `${kind}-${result.triggered_at}`,
              kind,
              label: getTaskLabel(kind),
              taskIds: result.task_ids,
              triggeredAt: result.triggered_at,
              message: result.message,
              statuses: {},
              pollingError: null,
            },
            ...prev.slice(0, 4),
          ]);
        } else if (kind === "weekly-velocity") {
          const result = await triggerAdminWeeklyVelocityNow(
            { reason: "admin-ui" },
            token
          );
          setMessage(result.message);
          setTaskRuns((prev) => [
            {
              id: `${kind}-${result.triggered_at}`,
              kind,
              label: getTaskLabel(kind),
              taskIds: result.task_ids,
              triggeredAt: result.triggered_at,
              message: result.message,
              statuses: {},
              pollingError: null,
            },
            ...prev.slice(0, 4),
          ]);
        } else {
          const channelIds = gate0IdsInput
            .split(/[,\n]+/)
            .map((value) => value.trim())
            .filter((value) => value.length > 0);
          const result = await triggerAdminGate0Now(
            { channel_ids: channelIds, reason: "admin-ui-batch" },
            token
          );
          setMessage(`Gate 0 queued: ${result.queued}`);
          setTaskRuns((prev) => [
            {
              id: `${kind}-${result.triggered_at}`,
              kind,
              label: getTaskLabel(kind),
              taskIds: result.task_ids,
              triggeredAt: result.triggered_at,
              message: `Gate 0 queued: ${result.queued}`,
              statuses: {},
              pollingError: null,
            },
            ...prev.slice(0, 4),
          ]);
        }
        const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
        setAudit(auditData.data);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Task trigger failed.");
      }
    },
    [gate0IdsInput, token]
  );

  const updateOperational = useCallback(
    (key: keyof OperationalForm, value: number) => {
      setOperational((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  const updateGate0Competitor = useCallback(
    (index: number, field: keyof Gate0Competitor, value: string) => {
      setGate0Competitors((prev) =>
        prev.map((competitor, currentIndex) => {
          if (currentIndex !== index) {
            return competitor;
          }
          if (field === "domains") {
            return {
              ...competitor,
              domains: value.split(",").map((domain) => domain.trim()),
            };
          }
          return { ...competitor, brand: value };
        })
      );
    },
    []
  );

  const addGate0Competitor = useCallback(() => {
    setGate0Competitors((prev) => [...prev, { brand: "", domains: [] }]);
  }, []);

  const removeGate0Competitor = useCallback((index: number) => {
    setGate0Competitors((prev) =>
      prev.filter((_, currentIndex) => currentIndex !== index)
    );
  }, []);

  if (loading) {
    return <p className="text-sm text-[#6B6B6B]">Loading admin controls...</p>;
  }

  if (!allowed) {
    return <p className="text-sm text-[#B22222]">{message || "Admin access denied."}</p>;
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h1 className="mb-3 text-xl font-semibold text-[#1A1A2E]">Admin Control Plane</h1>
        <p className="text-sm text-[#6B6B6B]">
          Update runtime controls without restarting workers. Changes apply to new task dispatches.
        </p>
      </section>

      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-[#1A1A2E]">System Settings</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
              Daily Scrape UTC
            </span>
            <input
              type="time"
              value={timeInput}
              onChange={(event) => setTimeInput(event.target.value)}
              className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
            />
          </label>
          <div className="flex flex-col gap-2">
            <label className="inline-flex items-center gap-2 text-sm text-[#1A1A2E]">
              <input
                type="checkbox"
                checked={gate0Enabled}
                onChange={(event) => setGate0Enabled(event.target.checked)}
              />
              Gate 0 Enabled
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-[#1A1A2E]">
              <input
                type="checkbox"
                checked={discoveryEnabled}
                onChange={(event) => setDiscoveryEnabled(event.target.checked)}
              />
              Discovery Enabled
            </label>
            <label className="inline-flex items-center gap-2 text-sm text-[#1A1A2E]">
              <input
                type="checkbox"
                checked={lookalikeEnabled}
                onChange={(event) => setLookalikeEnabled(event.target.checked)}
              />
              Lookalike Enabled
            </label>
          </div>
        </div>

        <div className="mt-4">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            Platform Priority
          </p>
          <div className="space-y-2">
            {platformPriority.map((platform, index) => (
              <div
                key={platform}
                className="flex items-center justify-between rounded-lg border border-[#E8E4DC] px-3 py-2"
              >
                <span className="text-sm capitalize text-[#1A1A2E]">{platform}</span>
                <div className="flex gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => movePriority(index, -1)}
                    disabled={index === 0}
                  >
                    Up
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => movePriority(index, 1)}
                    disabled={index === platformPriority.length - 1}
                  >
                    Down
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-6 grid gap-4 border-t border-[#E8E4DC] pt-4 md:grid-cols-2">
          <div>
            <h3 className="mb-3 text-sm font-semibold text-[#1A1A2E]">Daily Scrape Scope</h3>
            <label className="mb-3 inline-flex items-center gap-2 text-sm text-[#1A1A2E]">
              <input
                type="checkbox"
                checked={scrapeOnlyNewOrMissing}
                onChange={(event) => setScrapeOnlyNewOrMissing(event.target.checked)}
              />
              Only new, queued, never-scraped, or incomplete-metric channels
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                Rescrape Minimum Hours
              </span>
              <input
                type="number"
                min={0}
                value={scrapeRescrapeMinHours}
                onChange={(event) => setScrapeRescrapeMinHours(Number(event.target.value))}
                className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
              />
            </label>
          </div>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-[#1A1A2E]">Weekly Velocity</h3>
            <label className="mb-3 inline-flex items-center gap-2 text-sm text-[#1A1A2E]">
              <input
                type="checkbox"
                checked={weeklyVelocityEnabled}
                onChange={(event) => setWeeklyVelocityEnabled(event.target.checked)}
              />
              Enabled for clean higher-metric leads
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                  Day
                </span>
                <select
                  value={weeklyVelocityDay}
                  onChange={(event) =>
                    setWeeklyVelocityDay(
                      event.target.value as SystemSettings["weekly_velocity_utc_day"]
                    )
                  }
                  className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                >
                  {WEEKDAY_OPTIONS.map((day) => (
                    <option key={day} value={day}>
                      {day.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                  Time UTC
                </span>
                <input
                  type="time"
                  value={weeklyVelocityTime}
                  onChange={(event) => setWeeklyVelocityTime(event.target.value)}
                  className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                />
              </label>
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
              Min Avg Comments
            </span>
            <input
              type="number"
              min={0}
              value={velocityMinAvgComments}
              onChange={(event) => setVelocityMinAvgComments(Number(event.target.value))}
              className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
              Min Avg Views
            </span>
            <input
              type="number"
              min={0}
              value={velocityMinAvgViews}
              onChange={(event) => setVelocityMinAvgViews(Number(event.target.value))}
              className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
              Min Subscribers
            </span>
            <input
              type="number"
              min={0}
              value={velocityMinSubscribers}
              onChange={(event) => setVelocityMinSubscribers(Number(event.target.value))}
              className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
              Stale After Hours
            </span>
            <input
              type="number"
              min={0}
              value={velocityStaleHours}
              onChange={(event) => setVelocityStaleHours(Number(event.target.value))}
              className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
            />
          </label>
        </div>

        <div className="mt-6 border-t border-[#E8E4DC] pt-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowAdvancedSettings((current) => !current)}
          >
            {showAdvancedSettings ? "Hide Advanced Settings" : "Show Advanced Settings"}
          </Button>
        </div>

        {showAdvancedSettings && (
          <>
            <div className="mt-6 border-t border-[#E8E4DC] pt-4">
              <h3 className="mb-3 text-sm font-semibold text-[#1A1A2E]">
                Scrape Pacing And Quotas
              </h3>
              <div className="grid gap-4 md:grid-cols-4">
                {[
                  ["scrape_dispatch_batch_size", "Dispatch Batch", 1],
                  ["scrape_dispatch_pause_seconds", "Dispatch Pause Seconds", 0],
                  ["scrape_run_max_channels", "Max Channels Per Run", 0],
                  ["scrape_daily_byte_budget_mb", "Daily Budget MB", 0],
                  ["scrape_retry_base_delay_seconds", "Retry Base Seconds", 1],
                  ["scrape_retry_jitter_min", "Retry Jitter Min", 0],
                  ["scrape_retry_jitter_max", "Retry Jitter Max", 0],
                  ["scrape_circuit_breaker_fail_threshold", "CB Fail Threshold", 1],
                  ["scrape_circuit_breaker_window_seconds", "CB Window Seconds", 1],
                  ["scrape_circuit_breaker_cooldown_seconds", "CB Cooldown Seconds", 1],
                ].map(([key, label, min]) => (
                  <label key={key} className="flex flex-col gap-1.5">
                    <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                      {label}
                    </span>
                    <input
                      type="number"
                      min={min}
                      step={String(key).includes("jitter") || String(key).includes("pause") ? 0.1 : 1}
                      value={operational[key as keyof OperationalForm]}
                      onChange={(event) =>
                        updateOperational(
                          key as keyof OperationalForm,
                          Number(event.target.value)
                        )
                      }
                      className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-6 border-t border-[#E8E4DC] pt-4">
              <h3 className="mb-3 text-sm font-semibold text-[#1A1A2E]">
                Gate 0 And Browser Timing
              </h3>
              <div className="grid gap-4 md:grid-cols-4">
                {[
                  ["gate0_daily_queue_limit", "Gate 0 Daily Queue", 0],
                  ["gate0_clean_recheck_days", "Clean Recheck Days", 0],
                  ["scraper_human_delay_min_seconds", "Human Delay Min", 0],
                  ["scraper_human_delay_max_seconds", "Human Delay Max", 0],
                  ["scraper_content_wait_min_bytes", "Content Min Bytes", 0],
                  ["scraper_content_wait_timeout_seconds", "Content Timeout", 0],
                  ["scraper_content_wait_poll_seconds", "Content Poll Seconds", 0.1],
                ].map(([key, label, min]) => (
                  <label key={key} className="flex flex-col gap-1.5">
                    <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                      {label}
                    </span>
                    <input
                      type="number"
                      min={min}
                      step={String(key).includes("seconds") ? 0.1 : 1}
                      value={operational[key as keyof OperationalForm]}
                      onChange={(event) =>
                        updateOperational(
                          key as keyof OperationalForm,
                          Number(event.target.value)
                        )
                      }
                      className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-6 border-t border-[#E8E4DC] pt-4">
              <h3 className="mb-3 text-sm font-semibold text-[#1A1A2E]">
                Discovery Limits
              </h3>
              <div className="grid gap-4 md:grid-cols-4">
                {[
                  ["discovery_serper_query_limit", "Serper Query Limit", 0],
                  ["discovery_results_per_query", "Results Per Query", 1],
                  ["discovery_max_pages_per_query", "Max Pages Per Query", 1],
                  ["discovery_insert_limit", "Insert Limit", 0],
                  ["discovery_query_stagnation_limit", "Query Stagnation", 1],
                  ["discovery_global_stop_no_new", "Global No-New Stop", 1],
                  ["discovery_max_feedback_terms", "Max Feedback Terms", 0],
                  ["discovery_new_scrape_limit", "New Scrape Queue", 0],
                  ["discovery_channel_page_size", "Channel Page Size", 1],
                  ["discovery_verify_timeout_seconds", "Verify Timeout Seconds", 0],
                ].map(([key, label, min]) => (
                  <label key={key} className="flex flex-col gap-1.5">
                    <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                      {label}
                    </span>
                    <input
                      type="number"
                      min={min}
                      step={String(key).includes("confidence") ? 0.01 : 1}
                      value={operational[key as keyof OperationalForm]}
                      onChange={(event) =>
                        updateOperational(
                          key as keyof OperationalForm,
                          Number(event.target.value)
                        )
                      }
                      className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    />
                  </label>
                ))}
              </div>
            </div>
          </>
        )}

        <div className="mt-6 border-t border-[#E8E4DC] pt-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-[#1A1A2E]">
              Gate 0 Competitors
            </h3>
            <Button variant="ghost" size="sm" onClick={addGate0Competitor}>
              Add Competitor
            </Button>
          </div>
          <div className="space-y-3">
            {gate0Competitors.map((competitor, index) => (
              <div
                key={`${index}-${competitor.brand}`}
                className="grid gap-3 rounded-lg border border-[#E8E4DC] bg-[#FBFAF7] p-3 md:grid-cols-[1fr_2fr_auto]"
              >
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                    Brand
                  </span>
                  <input
                    type="text"
                    value={competitor.brand}
                    onChange={(event) =>
                      updateGate0Competitor(index, "brand", event.target.value)
                    }
                    className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
                    Domains
                  </span>
                  <input
                    type="text"
                    value={competitor.domains.join(", ")}
                    onChange={(event) =>
                      updateGate0Competitor(index, "domains", event.target.value)
                    }
                    placeholder="example.com, partner.example.com"
                    className="rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                  />
                </label>
                <div className="flex items-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeGate0Competitor(index)}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            ))}
            {gate0Competitors.length === 0 && (
              <p className="text-sm text-[#6B6B6B]">
                No competitors configured. Gate 0 will mark channels clean unless new competitors are added.
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <Button variant="accent" size="sm" onClick={handleSave} disabled={!dirty || saving}>
            Save Settings
          </Button>
          <span className="text-xs text-[#6B6B6B]">
            Version: {settings?.version ?? "-"} | Updated by: {settings?.updated_by_email ?? "n/a"}
          </span>
        </div>
      </section>

      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Manual Task Triggers</h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" size="sm" onClick={() => void runTask("scrape")}>
            Trigger Full Scrape
          </Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("discovery")}>
            Trigger Discovery
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void runTask("weekly-velocity")}
          >
            Trigger Weekly Velocity
          </Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("gate0")}>
            Trigger Gate 0 Batch
          </Button>
        </div>
        <textarea
          value={gate0IdsInput}
          onChange={(event) => setGate0IdsInput(event.target.value)}
          rows={3}
          placeholder="Paste channel UUIDs (comma or newline separated)"
          className="mt-3 w-full rounded-lg border border-[#E8E4DC] bg-white px-3 py-2 text-xs text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
        />
        {taskRuns.length > 0 && (
          <div className="mt-4 space-y-3">
            {taskRuns.map((run) => (
              <div
                key={run.id}
                className="rounded-lg border border-[#E8E4DC] bg-[#FBFAF7] p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-[#1A1A2E]">
                        {run.label}
                      </h3>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-xs font-medium ${getRunStateClass(run)}`}
                      >
                        {getRunState(run)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[#6B6B6B]">
                      {run.message} | {new Date(run.triggeredAt).toLocaleString()}
                    </p>
                  </div>
                  <p className="text-xs text-[#6B6B6B]">
                    {run.taskIds.length} task{run.taskIds.length === 1 ? "" : "s"}
                  </p>
                </div>

                {run.pollingError && (
                  <p className="mt-2 text-xs text-[#B22222]">{run.pollingError}</p>
                )}

                {run.taskIds.length === 0 ? (
                  <p className="mt-3 text-xs text-[#6B6B6B]">
                    No Celery tasks were queued.
                  </p>
                ) : (
                  <div className="mt-3 space-y-2">
                    {run.taskIds.map((taskId) => {
                      const status = run.statuses[taskId];
                      const result = formatTaskResult(status?.result);
                      return (
                        <div
                          key={taskId}
                          className="rounded-md border border-[#E8E4DC] bg-white px-3 py-2"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <code className="break-all text-xs text-[#1A1A2E]">
                              {taskId}
                            </code>
                            <span className="rounded-full bg-[#F7F4EE] px-2 py-0.5 text-xs font-medium text-[#6B6B6B]">
                              {status?.state ?? "Queued"}
                            </span>
                          </div>
                          {status?.date_done && (
                            <p className="mt-1 text-xs text-[#6B6B6B]">
                              Settled: {new Date(status.date_done).toLocaleString()}
                            </p>
                          )}
                          {result && (
                            <p className="mt-1 break-words text-xs text-[#6B6B6B]">
                              {result}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Recent Admin Audit</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[#6B6B6B]">
              <tr>
                <th className="px-2 py-2">Time (UTC)</th>
                <th className="px-2 py-2">Actor</th>
                <th className="px-2 py-2">Action</th>
                <th className="px-2 py-2">Target</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((row) => (
                <tr key={row.id} className="border-t border-[#E8E4DC]">
                  <td className="px-2 py-2 text-[#6B6B6B]">{row.created_at}</td>
                  <td className="px-2 py-2 text-[#1A1A2E]">{row.actor_email ?? "n/a"}</td>
                  <td className="px-2 py-2 text-[#1A1A2E]">{row.action}</td>
                  <td className="px-2 py-2 text-[#1A1A2E]">{row.target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {message && (
        <p className="text-sm text-[#1A1A2E]">{message}</p>
      )}
    </div>
  );
}
