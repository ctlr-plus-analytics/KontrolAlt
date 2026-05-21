"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getAdminAudit,
  getAdminMe,
  getAdminSettings,
  patchAdminSettings,
  triggerAdminDiscoveryNow,
  triggerAdminGate0Now,
  triggerAdminScrapeNow,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import type { AdminAuditRecord, SystemSettings } from "@/types";
import { Button } from "@/components/ui/Button";

const AUDIT_PAGE_SIZE = 20;

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

  const [timeInput, setTimeInput] = useState<string>("02:00");
  const [gate0Enabled, setGate0Enabled] = useState<boolean>(true);
  const [discoveryEnabled, setDiscoveryEnabled] = useState<boolean>(true);
  const [lookalikeEnabled, setLookalikeEnabled] = useState<boolean>(true);
  const [platformPriority, setPlatformPriority] = useState<("rumble" | "bitchute")[]>([
    "rumble",
    "bitchute",
  ]);

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
        setDiscoveryEnabled(settingsData.discovery_enabled);
        setLookalikeEnabled(settingsData.lookalike_enabled);
        setPlatformPriority(settingsData.scrape_platform_priority);
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
      settings.scrape_platform_priority.join(",") !== platformPriority.join(",")
    );
  }, [
    discoveryEnabled,
    gate0Enabled,
    lookalikeEnabled,
    platformPriority,
    settings,
    timeInput,
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
          discovery_enabled: discoveryEnabled,
          lookalike_enabled: lookalikeEnabled,
          scrape_platform_priority: platformPriority,
          expected_version: settings.version,
        },
        token
      );
      setSettings(updated);
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
    lookalikeEnabled,
    platformPriority,
    settings,
    timeInput,
    token,
  ]);

  const runTask = useCallback(
    async (kind: "scrape" | "discovery" | "gate0") => {
      if (!token) {
        return;
      }
      setMessage("");
      try {
        if (kind === "scrape") {
          const result = await triggerAdminScrapeNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
        } else if (kind === "discovery") {
          const result = await triggerAdminDiscoveryNow({ reason: "admin-ui" }, token);
          setMessage(result.message);
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
        }
        const auditData = await getAdminAudit(1, AUDIT_PAGE_SIZE, token);
        setAudit(auditData.data);
      } catch (error) {
        setMessage(error instanceof Error ? error.message : "Task trigger failed.");
      }
    },
    [gate0IdsInput, token]
  );

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
