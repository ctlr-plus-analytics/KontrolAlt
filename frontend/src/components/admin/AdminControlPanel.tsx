"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getAdminAudit,
  getAdminCompetitors,
  getAdminKeywordTaxonomy,
  getAdminMe,
  getAdminTaskStatus,
  triggerAdminDiscoveryNow,
  triggerAdminGate0Now,
  triggerAdminWeeklyVelocityNow,
  triggerAdminScrapeNow,
  updateAdminCompetitors,
  updateAdminKeywordTaxonomy,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import type { AdminAuditRecord, AdminTaskStatusResponse, CompetitorDef, KeywordTaxonomyDef } from "@/types";
import { Button } from "@/components/ui/Button";

const AUDIT_PAGE_SIZE = 20;
const TASK_POLL_INTERVAL_MS = 2500;
const TERMINAL_TASK_STATES = new Set(["SUCCESS", "FAILURE", "REVOKED"]);
const ERROR_TASK_STATES = new Set(["FAILURE", "REVOKED"]);

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

function getTaskLabel(kind: ManualTaskKind): string {
  if (kind === "scrape") return "Full Scrape";
  if (kind === "discovery") return "Discovery";
  if (kind === "weekly-velocity") return "Weekly Velocity";
  return "Gate 0 Batch";
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
        } else {
          const ids = gate0IdsInput
            .split(/[\n,]/)
            .map((value) => value.trim())
            .filter(Boolean);
          const result = await triggerAdminGate0Now({ channel_ids: ids, reason: "admin-ui" }, token);
          setMessage(`Queued Gate 0 tasks: ${result.queued}`);
          setTaskRuns((prev) => [{
            id: `${kind}-${result.triggered_at}`,
            kind,
            label: getTaskLabel(kind),
            taskIds: result.task_ids,
            triggeredAt: result.triggered_at,
            message: `Queued Gate 0 tasks: ${result.queued}`,
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
      setTaxonomySuccess("Niche taxonomy saved.");
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
      setTaxonomyError("Niche and at least one keyword are required.");
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
      setTaxonomyError("Niche and at least one keyword are required.");
      return;
    }
    setIsAddingTaxonomy(false);
    void handleSaveTaxonomy([...keywordTaxonomy, { niche, keywords }]);
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
          <Button variant="primary" size="sm" onClick={() => void runTask("weekly-velocity")}>Trigger Weekly Velocity</Button>
          <Button variant="primary" size="sm" onClick={() => void runTask("gate0")}>Trigger Gate 0 Batch</Button>
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
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Gate 0 Competitors</h2>
        <p className="mb-3 text-xs text-[#6B6B6B]">Channels promoting these brands are flagged dirty. Changes take effect on the next Gate 0 run.</p>

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
        <h2 className="mb-3 text-lg font-semibold text-[#1A1A2E]">Niche Keywords</h2>
        <p className="mb-3 text-xs text-[#6B6B6B]">Niche tags and keywords are sourced from database settings. Changes take effect on subsequent discovery/scrape runs.</p>

        {taxonomyError && (
          <p className="mb-3 text-xs text-[#B22222]">{taxonomyError}</p>
        )}
        {taxonomySuccess && (
          <p className="mb-3 text-xs text-[#4F8A5B]">{taxonomySuccess}</p>
        )}

        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-[#6B6B6B]">
            <tr>
              <th className="px-2 py-2">Niche</th>
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
                        placeholder="Niche key"
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
                    placeholder="Niche key"
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
            <Button variant="primary" size="sm" onClick={handleStartTaxonomyAdd}>+ Add Niche</Button>
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
