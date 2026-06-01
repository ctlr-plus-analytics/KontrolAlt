/**
 * ChannelIntakePanel - frontend intake flows for adding channels.
 */
"use client";

import { useMemo, useState } from "react";
import type {
  IntakeSummaryResponse,
  Platform,
  ResolverConfirmSelection,
  ResolverSeedResult,
} from "@/types";
import {
  ApiError,
  confirmResolvedChannels,
  intakeBulkChannels,
  intakeManualChannel,
  resolveSeedChannels,
} from "@/lib/api/backend";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

interface ChannelIntakePanelProps {
  onIntakeComplete: () => void;
}

function IntakeSummary({
  summary,
}: {
  summary: IntakeSummaryResponse | null;
}) {
  if (!summary) {
    return null;
  }
  return (
    <div className="rounded-lg bg-[#F7F4EE] px-3 py-2 text-xs text-[#1A1A2E]">
      {summary.message}: {summary.inserted} inserted, {summary.duplicates} duplicates,{" "}
      {summary.invalid} invalid.
    </div>
  );
}

export function ChannelIntakePanel({ onIntakeComplete }: ChannelIntakePanelProps) {
  const { session } = useAuth();
  const token = session?.access_token ?? undefined;

  const [manualPlatform, setManualPlatform] = useState<Platform>("rumble");
  const [manualUrl, setManualUrl] = useState<string>("");
  const [manualNotes, setManualNotes] = useState<string>("");
  const [manualTags, setManualTags] = useState<string>("");
  const [manualTriggerNow, setManualTriggerNow] = useState<boolean>(true);
  const [manualLoading, setManualLoading] = useState<boolean>(false);
  const [manualSummary, setManualSummary] = useState<IntakeSummaryResponse | null>(null);
  const [manualError, setManualError] = useState<string | null>(null);

  const [bulkUrls, setBulkUrls] = useState<string>("");
  const [bulkTriggerNow, setBulkTriggerNow] = useState<boolean>(false);
  const [bulkLoading, setBulkLoading] = useState<boolean>(false);
  const [bulkSummary, setBulkSummary] = useState<IntakeSummaryResponse | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const [seedNames, setSeedNames] = useState<string>("");
  const [resolverResults, setResolverResults] = useState<ResolverSeedResult[]>([]);
  const [resolverLoading, setResolverLoading] = useState<boolean>(false);
  const [resolverConfirmLoading, setResolverConfirmLoading] = useState<boolean>(false);
  const [resolverSummary, setResolverSummary] = useState<IntakeSummaryResponse | null>(null);
  const [resolverError, setResolverError] = useState<string | null>(null);
  const [resolverSelected, setResolverSelected] = useState<Record<string, boolean>>({});

  const selectedResolverCandidates = useMemo(() => {
    const selections: ResolverConfirmSelection[] = [];
    for (const seedResult of resolverResults) {
      for (const candidate of seedResult.candidates) {
        const key = `${seedResult.seed_name}|${candidate.channel_url}`;
        if (!resolverSelected[key]) {
          continue;
        }
        selections.push({
          seed_name: seedResult.seed_name,
          platform: candidate.platform,
          channel_url: candidate.channel_url,
          tags: [],
          notes: null,
        });
      }
    }
    return selections;
  }, [resolverResults, resolverSelected]);

  const handleManualSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!manualUrl.trim()) {
      return;
    }
    setManualError(null);
    setManualLoading(true);
    try {
      const summary = await intakeManualChannel(
        {
          platform: manualPlatform,
          channel_url: manualUrl,
          notes: manualNotes.trim() || null,
          tags: manualTags
            .split(",")
            .map((item) => item.trim())
            .filter((item) => item.length > 0),
          trigger_scrape_now: manualTriggerNow,
        },
        token
      );
      setManualSummary(summary);
      setManualUrl("");
      onIntakeComplete();
    } catch (error: unknown) {
      setManualError(error instanceof ApiError ? error.message : "Manual intake failed");
    } finally {
      setManualLoading(false);
    }
  };

  const handleBulkSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!bulkUrls.trim()) {
      return;
    }
    setBulkError(null);
    setBulkLoading(true);
    try {
      const summary = await intakeBulkChannels(
        {
          urls_text: bulkUrls,
          trigger_scrape_now: bulkTriggerNow,
        },
        token
      );
      setBulkSummary(summary);
      onIntakeComplete();
    } catch (error: unknown) {
      setBulkError(error instanceof ApiError ? error.message : "Bulk intake failed");
    } finally {
      setBulkLoading(false);
    }
  };

  const handleResolverSearch = async () => {
    const parsedSeeds = seedNames
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    if (parsedSeeds.length === 0) {
      return;
    }
    setResolverError(null);
    setResolverLoading(true);
    try {
      const response = await resolveSeedChannels(
        {
          seed_names: parsedSeeds,
          limit_per_seed: 5,
        },
        token
      );
      setResolverResults(response.results);
      setResolverSelected({});
    } catch (error: unknown) {
      setResolverError(error instanceof ApiError ? error.message : "Resolver search failed");
    } finally {
      setResolverLoading(false);
    }
  };

  const handleResolverConfirm = async () => {
    if (selectedResolverCandidates.length === 0) {
      return;
    }
    setResolverError(null);
    setResolverConfirmLoading(true);
    try {
      const summary = await confirmResolvedChannels(
        {
          selections: selectedResolverCandidates,
          trigger_scrape_now: true,
        },
        token
      );
      setResolverSummary(summary);
      onIntakeComplete();
    } catch (error: unknown) {
      setResolverError(error instanceof ApiError ? error.message : "Resolver confirm failed");
    } finally {
      setResolverConfirmLoading(false);
    }
  };

  return (
    <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
      <form
        onSubmit={handleManualSubmit}
        className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm"
      >
        <h2 className="mb-3 text-sm font-semibold tracking-tight text-[#1A1A2E]">
          Manual Add Channel
        </h2>
        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            Platform
          </label>
          <select
            className="w-full rounded-lg border border-[#E8E4DC] px-3 py-2 text-sm text-[#0D0D0D]"
            value={manualPlatform}
            onChange={(event) => setManualPlatform(event.target.value as Platform)}
          >
            <option value="rumble">Rumble</option>
            <option value="substack">Substack</option>
          </select>
        </div>
        <Input
          id="manual-channel-url"
          label="Channel URL"
          placeholder="https://substack.com/@example"
          value={manualUrl}
          onChange={(event) => setManualUrl(event.target.value)}
          className="mb-3"
        />
        <Input
          id="manual-tags"
          label="Category Tags (Optional)"
          placeholder="financial / macro, prepper / survival"
          value={manualTags}
          onChange={(event) => setManualTags(event.target.value)}
          className="mb-3"
        />
        <Input
          id="manual-notes"
          label="Notes (Optional)"
          placeholder="Source or context"
          value={manualNotes}
          onChange={(event) => setManualNotes(event.target.value)}
          className="mb-3"
        />
        <label className="mb-3 flex items-center gap-2 text-xs text-[#6B6B6B]">
          <input
            type="checkbox"
            checked={manualTriggerNow}
            onChange={(event) => setManualTriggerNow(event.target.checked)}
          />
          Trigger scrape immediately
        </label>
        <Button type="submit" variant="accent" size="sm" loading={manualLoading}>
          Add Channel
        </Button>
        <div className="mt-3">
          <IntakeSummary summary={manualSummary} />
          {manualError ? <p className="mt-2 text-xs text-red-700">{manualError}</p> : null}
        </div>
      </form>

      <form
        onSubmit={handleBulkSubmit}
        className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm"
      >
        <h2 className="mb-3 text-sm font-semibold tracking-tight text-[#1A1A2E]">
          Bulk Add URLs
        </h2>
        <label
          htmlFor="bulk-urls"
          className="mb-1 block text-xs font-medium uppercase tracking-wide text-[#6B6B6B]"
        >
          URLs (newline or comma separated)
        </label>
        <textarea
          id="bulk-urls"
          className="mb-3 h-40 w-full rounded-lg border border-[#E8E4DC] px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
          placeholder={
            "https://rumble.com/c/one\nhttps://substack.com/@two\nhttps://substack.com/@three"
          }
          value={bulkUrls}
          onChange={(event) => setBulkUrls(event.target.value)}
        />
        <label className="mb-3 flex items-center gap-2 text-xs text-[#6B6B6B]">
          <input
            type="checkbox"
            checked={bulkTriggerNow}
            onChange={(event) => setBulkTriggerNow(event.target.checked)}
          />
          Trigger scrape immediately
        </label>
        <Button type="submit" variant="accent" size="sm" loading={bulkLoading}>
          Process Bulk Intake
        </Button>
        <div className="mt-3">
          <IntakeSummary summary={bulkSummary} />
          {bulkError ? <p className="mt-2 text-xs text-red-700">{bulkError}</p> : null}
        </div>
      </form>

      <div className="rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold tracking-tight text-[#1A1A2E]">
          Seed Name Resolver
        </h2>
        <Input
          id="resolver-seeds"
          label="Creator Names (Comma Separated, max 3)"
          placeholder="Creator One, Creator Two"
          value={seedNames}
          onChange={(event) => setSeedNames(event.target.value)}
          className="mb-3"
        />
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={resolverLoading}
          onClick={handleResolverSearch}
          className="mb-3"
        >
          Resolve Names
        </Button>

        <div className="max-h-52 space-y-2 overflow-y-auto pr-1">
          {resolverResults.map((seedResult) => (
            <div key={seedResult.seed_name} className="rounded-md border border-[#E8E4DC] p-2">
              <p className="mb-1 text-xs font-semibold text-[#1A1A2E]">{seedResult.seed_name}</p>
              {seedResult.candidates.map((candidate) => {
                const key = `${seedResult.seed_name}|${candidate.channel_url}`;
                return (
                  <label key={key} className="mb-1 flex items-start gap-2 text-xs text-[#2E2E2E]">
                    <input
                      type="checkbox"
                      checked={resolverSelected[key] ?? false}
                      onChange={(event) =>
                        setResolverSelected((prev) => ({ ...prev, [key]: event.target.checked }))
                      }
                    />
                    <span>
                      [{candidate.platform}] {candidate.channel_url} ({candidate.confidence})
                    </span>
                  </label>
                );
              })}
            </div>
          ))}
        </div>

        <Button
          type="button"
          variant="accent"
          size="sm"
          loading={resolverConfirmLoading}
          disabled={selectedResolverCandidates.length === 0}
          onClick={handleResolverConfirm}
          className="mt-3"
        >
          Confirm And Add Selected
        </Button>
        <div className="mt-3">
          <IntakeSummary summary={resolverSummary} />
          {resolverError ? <p className="mt-2 text-xs text-red-700">{resolverError}</p> : null}
        </div>
      </div>
    </div>
  );
}
