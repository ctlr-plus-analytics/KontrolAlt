"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getAdminAudit,
  getAdminCompetitors,
  getAdminKeywordTaxonomy,
  getAdminMe,
  getAdminTaskStatus,
  getAdminWorkerLogs,
  getAdminWorkers,
  triggerAdminClassifyChannels,
  triggerAdminDiscoveryNow,
  triggerAdminGate0Now,
  triggerAdminNeverScrapedBootstrapNow,
  triggerAdminWeeklyVelocityNow,
  triggerAdminScrapeNow,
  updateAdminCompetitors,
  updateAdminKeywordTaxonomy,
  purgeAdminQueue,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import type { AdminAuditRecord, AdminTaskStatusResponse, CompetitorDef, KeywordTaxonomyDef, PurgeQueueResponse, WorkerInfo, WorkerLogsResponse } from "@/types";
import { Button } from "@/components/ui/Button";

const AUDIT_PAGE_SIZE = 20;
const TASK_POLL_INTERVAL_MS = 2500;
const TERMINAL_TASK_STATES = new Set(["SUCCESS", "FAILURE", "REVOKED"]);
const ERROR_TASK_STATES = new Set(["FAILURE", "REVOKED"]);

type ManualTaskKind = "scrape" | "discovery" | "never-scraped-bootstrap" | "weekly-velocity" | "gate0" | "classify-channels" | "classify-channels-all";

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

function getTaskLabel(kind: ManualTaskKind): string {
  if (kind === "scrape") return "Full Scrape";
  if (kind === "discovery") return "Discovery";
  if (kind === "never-scraped-bootstrap") return "Never-Scraped Bootstrap";
  if (kind === "weekly-velocity") return "Weekly Velocity";
  if (kind === "classify-channels") return "AI Classify (Unclassified)";
  if (kind === "classify-channels-all") return "AI Classify (All Channels)";
  return "Previous Gold Affiliation Batch";
}

function isTaskSettled(status?: AdminTaskStatusResponse): boolean {
  return status ? TERMINAL_TASK_STATES.has(status.state) : false;
}

function getRunState(run: ManualTaskRun): string {
  if (run.taskIds.length === 0) return "Not queued";
  const statuses = run.taskIds.map((taskId) => run.statuses[taskId]);
  if (statuses.some((status) => status && ERROR_TASK_STATES.has(status.state))) return "Error";
  if (statuses.every((status) => status?.state === "SUCCESS")) return "Success";
  if (statuses.some((status) => status?.state === "STARTED")) return "Running";
  if (statuses.some((status) => status?.state === "RETRY")) return "Retrying";
  if (statuses.some((status) => status?.state === "PENDING")) return "Queued";
  return statuses.some(Boolean) ? "Running" : "Queued";
}

function getRunStateClass(run: ManualTaskRun): string {
  const state = getRunState(run);
  if (state === "Success") return "border-[#4F8A5B] bg-[#EEF7F0] text-[#2F6B3B]";
  if (state === "Error") return "border-[#B22222] bg-[#FDECEC] text-[#B22222]";
  if (state === "Not queued") return "border-[#D8D2C8] bg-[#F7F4EE] text-[#6B6B6B]";
  return "border-[#C9A84C] bg-[#FFF8DF] text-[#7A5B00]";
}

function formatTaskResult(result: unknown): string | null {
  if (result === null || result === undefined) return null;
  if (typeof result === "object" && !Array.isArray(result)) {
    const value = result as Record<string, unknown>;
    if (typeof value.queued === "number") {
      const parts = [`Queued ${value.queued}`];
      const byPlatform = value.queued_by_platform;
      if (byPlatform && typeof byPlatform === "object" && !Array.isArray(byPlatform)) {
        const platformText = Object.entries(byPlatform as Record<string, unknown>)
          .map(([platform, count]) => `${platform}: ${String(count)}`)
          .join(", ");
        if (platformText) parts.push(`(${platformText})`);
      }
      const queuedTasks = Array.isArray(value.queued_tasks) ? value.queued_tasks : [];
      if (queuedTasks.length > 0) {
        const preview = queuedTasks
          .slice(0, 8)
          .map((item) => {
            if (!item || typeof item !== "object") return null;
            const queued = item as Record<string, unknown>;
            const platform = String(queued.platform ?? "unknown");
            const taskId = String(queued.task_id ?? "no task id");
            const url = String(queued.channel_url ?? "");
            return `${platform} ${taskId}${url ? ` ${url}` : ""}`;
          })
          .filter(Boolean)
          .join("; ");
        if (preview) {
          parts.push(`Tasks: ${preview}${queuedTasks.length > 8 ? `; +${queuedTasks.length - 8} more` : ""}`);
        }
      }
      return parts.join(" ");
    }
  }
  if (typeof result === "string") return result;
  if (typeof result === "number" || typeof result === "boolean" || typeof result === "bigint") {
    return String(result);
  }
  try {
    return JSON.stringify(result);
  } catch {
    return "Result could not be displayed.";
  }
}

export function AdminControlPanel() {
  const { session } = useAuth();
  const token = session?.access_token;

  const [allowed, setAllowed] = useState<boolean>(false);
  const [audit, setAudit] = useState<AdminAuditRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [message, setMessage] = useState<string>("");
  const [gate0IdsInput, setGate0IdsInput] = useState<string>("");
  const [taskRuns, setTaskRuns] = useState<ManualTaskRun[]>([]);

  const [competitors, setCompetitors] = useState<CompetitorDef[]>([]);
  const [competitorsSaving, setCompetitorsSaving] = useState(false);
  const [competitorsError, setCompetitorsError] = useState<string | null>(null);
  const [competitorsSuccess, setCompetitorsSuccess] = useState<string | null>(null);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editBrand, setEditBrand] = useState("");
  const [editDomains, setEditDomains] = useState("");
  const [isAddingNew, setIsAddingNew] = useState(false);
  const [newBrand, setNewBrand] = useState("");
  const [newDomains, setNewDomains] = useState("");
  const [keywordTaxonomy, setKeywordTaxonomy] = useState<KeywordTaxonomyDef[]>([]);
  const [taxonomySaving, setTaxonomySaving] = useState(false);
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null);
  const [taxonomySuccess, setTaxonomySuccess] = useState<string | null>(null);
  const [editingTaxonomyIdx, setEditingTaxonomyIdx] = useState<number | null>(null);
  const [editNiche, setEditNiche] = useState("");
  const [editKeywords, setEditKeywords] = useState("");
  const [isAddingTaxonomy, setIsAddingTaxonomy] = useState(false);
  const [newNiche, setNewNiche] = useState("");
  const [newKeywords, setNewKeywords] = useState("");

  const [purgeConfirming, setPurgeConfirming] = useState(false);
  const [purgeLoading, setPurgeLoading] = useState(false);
  const [purgeResult, setPurgeResult] = useState<PurgeQueueResponse | null>(null);
  const [purgeError, setPurgeError] = useState<string | null>(null);

  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [workersCheckedAt, setWorkersCheckedAt] = useState<string | null>(null);
  const [workersLoading, setWorkersLoading] = useState(false);
  const [workersError, setWorkersError] = useState<string | null>(null);
  const [openLogs, setOpenLogs] = useState<Record<string, WorkerLogsResponse | null>>({});
  const [logsLoading, setLogsLoading] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const run = async () => {
      try {
        const [meData, auditData, competitorsData, taxonomyData] = await Promise.all([
          getAdminMe(token),
          getAdminAudit(1, AUDIT_PAGE_SIZE, token),
          getAdminCompetitors(token),
          getAdminKeywordTaxonomy(token),
        ]);
        if (cancelled) return;
        setAllowed(meData.roles.includes("admin"));
        setAudit(auditData.data);
        setCompetitors(competitorsData.competitors);
        setKeywordTaxonomy(taxonomyData.taxonomy);
      } catch (error) {
        if (cancelled) return;
        setAllowed(false);
        setMessage(error instanceof Error ? error.message : "Admin access denied.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    const pendingTaskIds = taskRuns.flatMap((run) =>
      run.taskIds.filter((taskId) => !isTaskSettled(run.statuses[taskId]))
    );
    if (pendingTaskIds.length === 0) return;

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        const updates = await Promise.all(
          pendingTaskIds.map(async (taskId) => {
            try {
              const status = await getAdminTaskStatus(taskId, token);
              return { taskId, status, error: null };
            } catch (error) {
              const err = error instanceof Error ? error.message : "Failed to refresh task status.";
              return { taskId, status: null, error: err };
            }
          })
        );
        if (cancelled) return;
        setTaskRuns((currentRuns) =>
          currentRuns.map((run) => {
            const matchingUpdates = updates.filter((update) => run.taskIds.includes(update.taskId));
            if (matchingUpdates.length === 0) return run;
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

  const fetchWorkers = useCallback(async () => {
    if (!token) return;
    setWorkersLoading(true);
    setWorkersError(null);
    try {
      const data = await getAdminWorkers(token);
      setWorkers(data.workers);
      setWorkersCheckedAt(data.checked_at);
    } catch (error) {
      setWorkersError(error instanceof Error ? error.message : "Failed to fetch worker status.");
    } finally {
      setWorkersLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token || !allowed) return;
    void fetchWorkers();
    const interval = window.setInterval(() => { void fetchWorkers(); }, 10_000);
    return () => window.clearInterval(interval);
  }, [token, allowed, fetchWorkers]);

  const toggleLogs = useCallback(async (service: string) => {
    if (!token) return;
    if (openLogs[service] !== undefined) {
      setOpenLogs((prev) => { const next = { ...prev }; delete next[service]; return next; });
      return;
    }
    setLogsLoading((prev) => ({ ...prev, [service]: true }));
    try {
      const data = await getAdminWorkerLogs(service, 150, token);
      setOpenLogs((prev) => ({ ...prev, [service]: data }));
    } catch (error) {
      setOpenLogs((prev) => ({
        ...prev,
        [service]: { service, lines: [error instanceof Error ? error.message : "Failed to fetch logs."], tail: 150 },
      }));
    } finally {
      setLogsLoading((prev) => ({ ...prev, [service]: false }));
    }
  }, [token, openLogs]);

  const runTask = useCallback(
    async (kind: ManualTaskKind) => {
      if (!token) return;
      setMessage("");
      try {
        if (kind === "scrape") {
          const result = await triggerAdminScrapeNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: result.message,
            statuses: {},
            pollingError: null,
          }, ...prev.slice(0, 4)]);
        } else if (kind === "discovery") {
          const result = await triggerAdminDiscoveryNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: result.message,
            statuses: {},
            pollingError: null,
          }, ...prev.slice(0, 4)]);
        } else if (kind === "weekly-velocity") {
          const result = await triggerAdminWeeklyVelocityNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: result.message,
            statuses: {},
            pollingError: null,
          }, ...prev.slice(0, 4)]);
        } else if (kind === "never-scraped-bootstrap") {
          const result = await triggerAdminNeverScrapedBootstrapNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: result.message,
            statuses: {},
            pollingError: null,
          }, ...prev.slice(0, 4)]);
        } else if (kind === "classify-channels" || kind === "classify-channels-all") {
          const result = await triggerAdminClassifyChannels(
            { reclassify: kind === "classify-channels-all", reason: "admin-ui" },
            token,
          );
          setMessage(result.message);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: result.message,
            statuses: {},
            pollingError: null,
          }, ...prev.slice(0, 4)]);
        } else {
          const ids = gate0IdsInput
            .split(/[\n,]/)
            .map((value) => value.trim())
            .filter(Boolean);
          const result = await triggerAdminGate0Now({ channel_ids: ids, reason: "admin-ui" }, token);
          setMessage(`Queued previous gold affiliation tasks: ${result.queued}`);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: `Queued previous gold affiliation tasks: ${result.queued}`,
            statuses: {},
            pollingError: null,
          }, ...prev.slice(0, 4)]);
        }
        const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
        setAudit(auditData.data);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Task trigger failed.");
      }
    },
    [gate0IdsInput, token]
  );

  const parseDomains = (raw: string): string[] =>
    raw.split(",").map((d) => d.trim()).filter(Boolean);
  const parseKeywords = (raw: string): string[] =>
    raw.split(",").map((keyword) => keyword.trim()).filter(Boolean);

  const handleSaveCompetitors = async (updated: CompetitorDef[]) => {
    if (!token) return;
    setCompetitorsSaving(true);
    setCompetitorsError(null);
    setCompetitorsSuccess(null);
    try {
      const result = await updateAdminCompetitors(updated, token);
      setCompetitors(result.competitors);
      setCompetitorsSuccess("Competitors saved.");
      const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
      setAudit(auditData.data);
    } catch (error) {
      setCompetitorsError(error instanceof Error ? error.message : "Save failed.");
    } finally {
      setCompetitorsSaving(false);
    }
  };

  const handleDeleteCompetitor = (idx: number) => {
    setCompetitorsSuccess(null);
    void handleSaveCompetitors(competitors.filter((_, i) => i !== idx));
  };

  const handleStartEdit = (idx: number) => {
    setEditingIdx(idx);
    setEditBrand(competitors[idx].brand);
    setEditDomains(competitors[idx].domains.join(", "));
    setCompetitorsError(null);
    setCompetitorsSuccess(null);
  };

  const handleCancelEdit = () => setEditingIdx(null);

  const handleSaveEdit = () => {
    if (editingIdx === null) return;
    const brand = editBrand.trim();
    const domains = parseDomains(editDomains);
    if (!brand || domains.length === 0) {
      setCompetitorsError("Brand and at least one domain are required.");
      return;
    }
    setEditingIdx(null);
    void handleSaveCompetitors(
      competitors.map((c, i) => (i === editingIdx ? { brand, domains } : c))
    );
  };

  const handleStartAdd = () => {
    setIsAddingNew(true);
    setNewBrand("");
    setNewDomains("");
    setCompetitorsError(null);
    setCompetitorsSuccess(null);
  };

  const handleCancelAdd = () => setIsAddingNew(false);

  const handleSaveNew = () => {
    const brand = newBrand.trim();
    const domains = parseDomains(newDomains);
    if (!brand || domains.length === 0) {
      setCompetitorsError("Brand and at least one domain are required.");
      return;
    }
    setIsAddingNew(false);
    void handleSaveCompetitors([...competitors, { brand, domains }]);
  };

  const handleSaveTaxonomy = async (updated: KeywordTaxonomyDef[]) => {
    if (!token) return;
    setTaxonomySaving(true);
    setTaxonomyError(null);
    setTaxonomySuccess(null);
    try {
      const result = await updateAdminKeywordTaxonomy(updated, token);
      setKeywordTaxonomy(result.taxonomy);
      setTaxonomySuccess("Category taxonomy saved.");
      const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
      setAudit(auditData.data);
    } catch (error) {
      setTaxonomyError(error instanceof Error ? error.message : "Save failed.");
    } finally {
      setTaxonomySaving(false);
    }
  };

  const handleDeleteTaxonomy = (idx: number) => {
    setTaxonomySuccess(null);
    void handleSaveTaxonomy(keywordTaxonomy.filter((_, i) => i !== idx));
  };

  const handleStartTaxonomyEdit = (idx: number) => {
    setEditingTaxonomyIdx(idx);
    setEditNiche(keywordTaxonomy[idx].niche);
    setEditKeywords(keywordTaxonomy[idx].keywords.join(", "));
    setTaxonomyError(null);
    setTaxonomySuccess(null);
  };

  const handleCancelTaxonomyEdit = () => setEditingTaxonomyIdx(null);

  const handleSaveTaxonomyEdit = () => {
    if (editingTaxonomyIdx === null) return;
    const niche = editNiche.trim();
    const keywords = parseKeywords(editKeywords);
    if (!niche || keywords.length === 0) {
      setTaxonomyError("Category and at least one keyword are required.");
      return;
    }
    setEditingTaxonomyIdx(null);
    void handleSaveTaxonomy(
      keywordTaxonomy.map((entry, i) => (i === editingTaxonomyIdx ? { niche, keywords } : entry))
    );
  };

  const handleStartTaxonomyAdd = () => {
    setIsAddingTaxonomy(true);
    setNewNiche("");
    setNewKeywords("");
    setTaxonomyError(null);
    setTaxonomySuccess(null);
  };

  const handleCancelTaxonomyAdd = () => setIsAddingTaxonomy(false);

  const handleSaveNewTaxonomy = () => {
    const niche = newNiche.trim();
    const keywords = parseKeywords(newKeywords);
    if (!niche || keywords.length === 0) {
      setTaxonomyError("Category and at least one keyword are required.");
      return;
    }
    setIsAddingTaxonomy(false);
    void handleSaveTaxonomy([...keywordTaxonomy, { niche, keywords }]);
  };

  const handlePurge = async () => {
    if (!token) return;
    setPurgeLoading(true);
    setPurgeError(null);
    setPurgeResult(null);
    setPurgeConfirming(false);
    try {
      const result = await purgeAdminQueue({ reason: "admin-ui manual purge" }, token);
      setPurgeResult(result);
      const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
      setAudit(auditData.data);
    } catch (error) {
      setPurgeError(error instanceof Error ? error.message : "Purge failed.");
    } finally {
      setPurgeLoading(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-[#6B6B6B]">Loading admin controls...</p>;
  }

  if (!allowed) {
    return (
      <div className="rounded-xl border border-[#E8E4DC] bg-white p-6">
        <h1 className="text-xl font-semibold text-[#1A1A2E]">Admin Access Required</h1>
        <p className="mt-2 text-sm text-[#6B6B6B]">You do not have permission to view this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Manual Task Triggers</h2>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" size="sm" onClick={() => void runTask("scrape")}>Trigger Full Scrape</Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("discovery")}>Trigger Discovery</Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("never-scraped-bootstrap")}>Bootstrap Never-Scraped Rumble/Substack</Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("weekly-velocity")}>Trigger Weekly Velocity</Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("gate0")}>Trigger Previous Gold Affiliation Batch</Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("classify-channels")}>AI Classify Channels</Button>
          <Button variant="ghost" size="sm" onClick={() => void runTask("classify-channels-all")}>AI Reclassify All</Button>
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
              <div key={run.id} className="rounded-lg border border-[#E8E4DC] bg-[#FBFAF7] p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-[#1A1A2E]">{run.label}</h3>
                      <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${getRunStateClass(run)}`}>{getRunState(run)}</span>
                    </div>
                    <p className="mt-1 text-xs text-[#6B6B6B]">{run.message} | {new Date(run.triggeredAt).toLocaleString()}</p>
                  </div>
                  <p className="text-xs text-[#6B6B6B]">{run.taskIds.length} task{run.taskIds.length === 1 ? "" : "s"}</p>
                </div>
                {run.pollingError && <p className="mt-2 text-xs text-[#B22222]">{run.pollingError}</p>}
                {run.taskIds.length === 0 ? (
                  <p className="mt-3 text-xs text-[#6B6B6B]">No Celery tasks were queued.</p>
                ) : (
                  <div className="mt-3 space-y-2">
                    {run.taskIds.map((taskId) => {
                      const status = run.statuses[taskId];
                      const result = formatTaskResult(status?.result);
                      return (
                        <div key={taskId} className="rounded-md border border-[#E8E4DC] bg-white px-3 py-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <code className="break-all text-xs text-[#1A1A2E]">{taskId}</code>
                            <span className="rounded-full bg-[#F7F4EE] px-2 py-0.5 text-xs font-medium text-[#6B6B6B]">{status?.state ?? "Queued"}</span>
                          </div>
                          {status?.date_done && <p className="mt-1 text-xs text-[#6B6B6B]">Settled: {new Date(status.date_done).toLocaleString()}</p>}
                          {result && <p className="mt-1 break-words text-xs text-[#6B6B6B]">{result}</p>}
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
        <div className="mb-3 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-[#1A1A2E]">Worker Health</h2>
            {workersCheckedAt && (
              <p className="text-xs text-[#6B6B6B]">Last checked {new Date(workersCheckedAt).toLocaleTimeString()} · auto-refreshes every 10s</p>
            )}
          </div>
          <button
            onClick={() => void fetchWorkers()}
            disabled={workersLoading}
            className="rounded-lg border border-[#E8E4DC] bg-[#F7F4EE] px-3 py-1.5 text-xs font-medium text-[#1A1A2E] hover:bg-[#EDE8DE] disabled:opacity-50"
          >
            {workersLoading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        {workersError && <p className="mb-3 text-xs text-[#B22222]">{workersError}</p>}

        {workers.length === 0 && !workersLoading && !workersError && (
          <p className="text-xs text-[#6B6B6B]">No worker data yet.</p>
        )}

        <div className="space-y-2">
          {workers.map((w) => {
            const logsOpen = openLogs[w.service] !== undefined;
            const logsFetching = logsLoading[w.service] ?? false;
            const logsData = openLogs[w.service];
            return (
              <div key={w.service} className="rounded-lg border border-[#E8E4DC] bg-[#FBFAF7]">
                <div className="flex flex-wrap items-center gap-3 px-3 py-2.5">
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${w.online ? "bg-[#4F8A5B]" : "bg-[#B22222]"}`}
                  />
                  <span className="min-w-[140px] font-mono text-sm font-medium text-[#1A1A2E]">{w.service}</span>

                  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${w.online ? "border-[#4F8A5B] bg-[#EEF7F0] text-[#2F6B3B]" : "border-[#B22222] bg-[#FDECEC] text-[#B22222]"}`}>
                    {w.online ? "Online" : "Offline"}
                  </span>

                  <span className="rounded-full border border-[#D8D2C8] bg-[#F7F4EE] px-2 py-0.5 text-xs text-[#6B6B6B]">
                    {w.container_status}
                  </span>

                  {w.celery_name && (
                    <span className="text-xs text-[#6B6B6B]">
                      active <span className="font-semibold text-[#1A1A2E]">{w.active_tasks}</span>
                      {" · "}reserved <span className="font-semibold text-[#1A1A2E]">{w.reserved_tasks}</span>
                      {w.concurrency !== null && <> · concurrency <span className="font-semibold text-[#1A1A2E]">{w.concurrency}</span></>}
                      {w.processed_total > 0 && <> · <span className="font-semibold text-[#1A1A2E]">{w.processed_total}</span> done</>}
                    </span>
                  )}

                  <button
                    onClick={() => void toggleLogs(w.service)}
                    disabled={logsFetching}
                    className="ml-auto rounded border border-[#E8E4DC] bg-white px-2 py-0.5 text-xs text-[#6B6B6B] hover:bg-[#F7F4EE] disabled:opacity-50"
                  >
                    {logsFetching ? "Loading…" : logsOpen ? "Hide Logs" : "View Logs"}
                  </button>
                </div>

                {logsOpen && (
                  <div className="border-t border-[#E8E4DC] px-3 pb-3 pt-2">
                    <div className="max-h-64 overflow-y-auto rounded bg-[#1A1A2E] p-2">
                      {logsData && logsData.lines.length > 0 ? (
                        <pre className="whitespace-pre-wrap break-all font-mono text-[10px] leading-relaxed text-[#D8D2C8]">
                          {logsData.lines.join("\n")}
                        </pre>
                      ) : (
                        <p className="font-mono text-[10px] text-[#6B6B6B]">No log lines returned.</p>
                      )}
                    </div>
                    <button
                      onClick={async () => {
                        setOpenLogs((prev) => { const next = { ...prev }; delete next[w.service]; return next; });
                        await toggleLogs(w.service);
                      }}
                      className="mt-2 text-xs text-[#6B6B6B] hover:text-[#1A1A2E]"
                    >
                      Refresh logs
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border border-[#B22222] bg-[#FFF8F8] p-4 shadow-sm">
        <h2 className="mb-1 text-lg font-semibold text-[#B22222]">Danger Zone — Purge All Tasks</h2>
        <p className="mb-4 text-xs text-[#6B6B6B]">
          Sends SIGKILL to all active and reserved tasks in the worker containers, purges the
          broker queue, deletes all Redis scraper state (platform slots, scrape locks, proxy
          health scores, byte budget), and restarts the worker process pools to flush any
          prefetch or zombie state. Use this to get a clean slate before a fresh scrape run.
        </p>

        {!purgeConfirming && !purgeLoading && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => { setPurgeConfirming(true); setPurgeResult(null); setPurgeError(null); }}
          >
            Purge All Tasks &amp; Redis State
          </Button>
        )}

        {purgeConfirming && (
          <div className="rounded-lg border border-[#B22222] bg-white p-3">
            <p className="mb-3 text-sm font-medium text-[#B22222]">
              This will SIGKILL all running tasks in the worker containers, purge the broker queue, wipe all Redis scraper state, and restart worker pools. Are you sure?
            </p>
            <div className="flex gap-2">
              <Button variant="danger" size="sm" onClick={() => void handlePurge()}>
                Yes, purge everything
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setPurgeConfirming(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {purgeLoading && (
          <p className="text-sm text-[#6B6B6B]">Purging...</p>
        )}

        {purgeError && (
          <p className="mt-3 text-xs text-[#B22222]">{purgeError}</p>
        )}

        {purgeResult && (
          <div className="mt-3 rounded-lg border border-[#4F8A5B] bg-[#EEF7F0] p-3">
            <p className="mb-2 text-sm font-medium text-[#2F6B3B]">{purgeResult.message}</p>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
              {(
                [
                  ["Killed (SIGKILL)", purgeResult.stats.revoked],
                  ["Purged from broker queue", purgeResult.stats.broker_purged],
                  ["Direct Redis keys deleted", purgeResult.stats.direct_keys_deleted],
                  ["Scraper state keys deleted", purgeResult.stats.scraper_keys_deleted],
                  ["Result backend keys deleted", purgeResult.stats.result_keys_deleted],
                  ["Worker pools restarted", purgeResult.stats.pool_restarted ? "Yes" : "No"],
                ] as [string, unknown][]
              ).map(([label, value]) => (
                <div key={label}>
                  <dt className="text-[#6B6B6B]">{label}</dt>
                  <dd className="font-semibold text-[#1A1A2E]">{String(value ?? "—")}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-2 text-xs text-[#6B6B6B]">
              Purged at {new Date(purgeResult.purged_at).toLocaleString()}
            </p>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Previous Gold Affiliation Competitors</h2>
        <p className="mb-3 text-xs text-[#6B6B6B]">Channels promoting these brands are flagged with a prior gold affiliation. Changes take effect on the next affiliation run.</p>

        {competitorsError && (
          <p className="mb-3 text-xs text-[#B22222]">{competitorsError}</p>
        )}
        {competitorsSuccess && (
          <p className="mb-3 text-xs text-[#4F8A5B]">{competitorsSuccess}</p>
        )}

        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-[#6B6B6B]">
            <tr>
              <th className="px-2 py-2">Brand</th>
              <th className="px-2 py-2">Domains</th>
              <th className="px-2 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {competitors.map((c, idx) => (
              <tr key={idx} className="border-t border-[#E8E4DC]">
                {editingIdx === idx ? (
                  <>
                    <td className="px-2 py-2">
                      <input
                        value={editBrand}
                        onChange={(e) => setEditBrand(e.target.value)}
                        className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                        placeholder="Brand name"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <input
                        value={editDomains}
                        onChange={(e) => setEditDomains(e.target.value)}
                        className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                        placeholder="domain.com, domain2.com"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex gap-2">
                        <Button variant="accent" size="sm" onClick={handleSaveEdit} loading={competitorsSaving}>Save</Button>
                        <Button variant="ghost" size="sm" onClick={handleCancelEdit}>Cancel</Button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="px-2 py-2 font-medium text-[#1A1A2E]">{c.brand}</td>
                    <td className="px-2 py-2 text-[#6B6B6B]">{c.domains.join(", ")}</td>
                    <td className="px-2 py-2">
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => handleStartEdit(idx)}>Edit</Button>
                        <Button variant="danger" size="sm" onClick={() => handleDeleteCompetitor(idx)} loading={competitorsSaving}>Delete</Button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}

            {isAddingNew && (
              <tr className="border-t border-[#E8E4DC]">
                <td className="px-2 py-2">
                  <input
                    value={newBrand}
                    onChange={(e) => setNewBrand(e.target.value)}
                    className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    placeholder="Brand name"
                    autoFocus
                  />
                </td>
                <td className="px-2 py-2">
                  <input
                    value={newDomains}
                    onChange={(e) => setNewDomains(e.target.value)}
                    className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    placeholder="domain.com, domain2.com"
                  />
                </td>
                <td className="px-2 py-2">
                  <div className="flex gap-2">
                    <Button variant="accent" size="sm" onClick={handleSaveNew} loading={competitorsSaving}>Add</Button>
                    <Button variant="ghost" size="sm" onClick={handleCancelAdd}>Cancel</Button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {!isAddingNew && (
          <div className="mt-3">
            <Button variant="primary" size="sm" onClick={handleStartAdd}>+ Add Competitor</Button>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Category Keywords</h2>
        <p className="mb-3 text-xs text-[#6B6B6B]">Broad category tags and keywords are sourced from database settings. Changes take effect on subsequent discovery/scrape runs.</p>

        {taxonomyError && (
          <p className="mb-3 text-xs text-[#B22222]">{taxonomyError}</p>
        )}
        {taxonomySuccess && (
          <p className="mb-3 text-xs text-[#4F8A5B]">{taxonomySuccess}</p>
        )}

        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-[#6B6B6B]">
            <tr>
              <th className="px-2 py-2">Category</th>
              <th className="px-2 py-2">Keywords</th>
              <th className="px-2 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {keywordTaxonomy.map((entry, idx) => (
              <tr key={idx} className="border-t border-[#E8E4DC]">
                {editingTaxonomyIdx === idx ? (
                  <>
                    <td className="px-2 py-2">
                      <input
                        value={editNiche}
                        onChange={(e) => setEditNiche(e.target.value)}
                        className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                        placeholder="Category name"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <input
                        value={editKeywords}
                        onChange={(e) => setEditKeywords(e.target.value)}
                        className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                        placeholder="keyword 1, keyword 2"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex gap-2">
                        <Button variant="accent" size="sm" onClick={handleSaveTaxonomyEdit} loading={taxonomySaving}>Save</Button>
                        <Button variant="ghost" size="sm" onClick={handleCancelTaxonomyEdit}>Cancel</Button>
                      </div>
                    </td>
                  </>
                ) : (
                  <>
                    <td className="px-2 py-2 font-medium text-[#1A1A2E]">{entry.niche}</td>
                    <td className="px-2 py-2 text-[#6B6B6B]">{entry.keywords.join(", ")}</td>
                    <td className="px-2 py-2">
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm" onClick={() => handleStartTaxonomyEdit(idx)}>Edit</Button>
                        <Button variant="danger" size="sm" onClick={() => handleDeleteTaxonomy(idx)} loading={taxonomySaving}>Delete</Button>
                      </div>
                    </td>
                  </>
                )}
              </tr>
            ))}

            {isAddingTaxonomy && (
              <tr className="border-t border-[#E8E4DC]">
                <td className="px-2 py-2">
                  <input
                    value={newNiche}
                    onChange={(e) => setNewNiche(e.target.value)}
                    className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    placeholder="Category name"
                    autoFocus
                  />
                </td>
                <td className="px-2 py-2">
                  <input
                    value={newKeywords}
                    onChange={(e) => setNewKeywords(e.target.value)}
                    className="w-full rounded border border-[#E8E4DC] px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
                    placeholder="keyword 1, keyword 2"
                  />
                </td>
                <td className="px-2 py-2">
                  <div className="flex gap-2">
                    <Button variant="accent" size="sm" onClick={handleSaveNewTaxonomy} loading={taxonomySaving}>Add</Button>
                    <Button variant="ghost" size="sm" onClick={handleCancelTaxonomyAdd}>Cancel</Button>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {!isAddingTaxonomy && (
          <div className="mt-3">
            <Button variant="primary" size="sm" onClick={handleStartTaxonomyAdd}>+ Add Category</Button>
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

      {message && <p className="text-sm text-[#1A1A2E]">{message}</p>}
    </div>
  );
}
