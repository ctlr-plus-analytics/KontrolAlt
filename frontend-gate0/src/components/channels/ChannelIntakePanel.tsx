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

function IntakeSummary({ summary }: { summary: IntakeSummaryResponse | null }) {
  if (!summary) return null;
  const hasRecords = summary.records.length > 0;
  return (
    <div className="rounded-lg border border-[#E8E4DC] bg-[#F7F4EE] px-3 py-2 text-xs text-[#1A1A2E]">
      <p className="font-medium">{summary.message}</p>
      <p className="mt-0.5 text-[#6B6B6B]">
        {summary.inserted} inserted · {summary.duplicates} duplicate{summary.duplicates !== 1 ? "s" : ""} · {summary.invalid} invalid
      </p>
      {hasRecords && (
        <ul className="mt-2 space-y-0.5">
          {summary.records.map((r, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className={
                r.status === "inserted" ? "text-[#4F8A5B]" :
                r.status === "duplicate" ? "text-[#C9A84C]" :
                "text-[#B22222]"
              }>
                {r.status === "inserted" ? "✓" : r.status === "duplicate" ? "~" : "✗"}
              </span>
              <span className="break-all text-[#6B6B6B]">
                {r.channel_url ?? r.input_value}
                {r.reason ? ` — ${r.reason}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 text-[11px] leading-snug text-[#6B6B6B]">{children}</p>;
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
      setBulkUrls("");
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
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* ── Manual Add ── */}
      <form
        onSubmit={handleManualSubmit}
        className="flex flex-col rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm"
      >
        <h2 className="text-sm font-semibold tracking-tight text-[#1A1A2E]">
          Add Single Channel
        </h2>
        <p className="mb-4 mt-1 text-xs text-[#6B6B6B]">
          Add one channel by URL. Duplicates are detected automatically — re-adding an existing channel
          will not create a duplicate, but can re-trigger a scrape.
        </p>

        <div className="mb-3">
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-[#6B6B6B]">
            Platform
          </label>
          <select
            className="w-full rounded-lg border border-[#E8E4DC] px-3 py-2 text-sm text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
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
          placeholder={
            manualPlatform === "rumble"
              ? "https://rumble.com/c/channel-slug"
              : "https://substack.com/@handle"
          }
          value={manualUrl}
          onChange={(event) => setManualUrl(event.target.value)}
          className="mb-1"
        />
        <FieldHint>
          {manualPlatform === "rumble"
            ? "Rumble channel pages use the format rumble.com/c/slug. Profile pages (rumble.com/user/…) are not supported."
            : "Use the @handle format. Subdomain URLs like handle.substack.com are also accepted and will be normalised."}
        </FieldHint>

        <Input
          id="manual-tags"
          label="Category Tags (Optional)"
          placeholder="e.g. financial / macro, prepper / survival"
          value={manualTags}
          onChange={(event) => setManualTags(event.target.value)}
          className="mb-1"
        />
        <FieldHint>Comma-separated tags stored as niche metadata. Used for filtering and discovery matching.</FieldHint>

        <Input
          id="manual-notes"
          label="Notes (Optional)"
          placeholder="e.g. Referred by ops team, found via newsletter"
          value={manualNotes}
          onChange={(event) => setManualNotes(event.target.value)}
          className="mb-3"
        />

        <label className="mb-4 flex items-start gap-2 text-xs text-[#6B6B6B]">
          <input
            type="checkbox"
            className="mt-0.5 shrink-0"
            checked={manualTriggerNow}
            onChange={(event) => setManualTriggerNow(event.target.checked)}
          />
          <span>
            <span className="font-medium text-[#1A1A2E]">Trigger scrape immediately</span>
            {" "}— queues a full channel scrape now and schedules a Gate 0 check ~2 minutes later. Leave unchecked to add the channel quietly and let the daily scrape pick it up.
          </span>
        </label>

        <Button type="submit" variant="accent" size="sm" loading={manualLoading}>
          Add Channel
        </Button>
        <div className="mt-3">
          <IntakeSummary summary={manualSummary} />
          {manualError ? <p className="mt-2 text-xs text-[#B22222]">{manualError}</p> : null}
        </div>
      </form>

      {/* ── Bulk Add ── */}
      <form
        onSubmit={handleBulkSubmit}
        className="flex flex-col rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm"
      >
        <h2 className="text-sm font-semibold tracking-tight text-[#1A1A2E]">
          Bulk Add URLs
        </h2>
        <p className="mb-4 mt-1 text-xs text-[#6B6B6B]">
          Paste a list of channel URLs — one per line or comma-separated. Platform is detected
          automatically from the URL. Existing channels are skipped without error.
        </p>

        <label
          htmlFor="bulk-urls"
          className="mb-1 block text-xs font-medium uppercase tracking-wide text-[#6B6B6B]"
        >
          Channel URLs
        </label>
        <textarea
          id="bulk-urls"
          className="mb-1 h-44 w-full rounded-lg border border-[#E8E4DC] px-3 py-2 font-mono text-xs text-[#0D0D0D] focus:outline-none focus:ring-2 focus:ring-[#C9A84C]"
          placeholder={
            "https://rumble.com/c/channel-one\nhttps://rumble.com/c/channel-two\nhttps://substack.com/@writer-handle\nhttps://substack.com/@another-writer"
          }
          value={bulkUrls}
          onChange={(event) => setBulkUrls(event.target.value)}
          spellCheck={false}
        />
        <FieldHint>
          Supported: rumble.com/c/… and substack.com/@… (or handle.substack.com). Unsupported URLs are reported as invalid in the result summary.
        </FieldHint>

        <label className="mb-4 flex items-start gap-2 text-xs text-[#6B6B6B]">
          <input
            type="checkbox"
            className="mt-0.5 shrink-0"
            checked={bulkTriggerNow}
            onChange={(event) => setBulkTriggerNow(event.target.checked)}
          />
          <span>
            <span className="font-medium text-[#1A1A2E]">Trigger scrape immediately</span>
            {" "}— queues a scrape task for every URL in the list. Leave unchecked for large imports to avoid overwhelming the worker queue.
          </span>
        </label>

        <Button type="submit" variant="accent" size="sm" loading={bulkLoading}>
          Process Bulk Intake
        </Button>
        <div className="mt-3">
          <IntakeSummary summary={bulkSummary} />
          {bulkError ? <p className="mt-2 text-xs text-[#B22222]">{bulkError}</p> : null}
        </div>
      </form>

      {/* ── Seed Name Resolver ── */}
      <div className="flex flex-col rounded-xl border border-[#E8E4DC] bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold tracking-tight text-[#1A1A2E]">
          Creator Name Resolver
        </h2>
        <p className="mb-4 mt-1 text-xs text-[#6B6B6B]">
          Don&apos;t know the exact URL? Enter a creator&apos;s name and we&apos;ll search existing
          channels for fuzzy matches. If no match is found, guessed URLs are suggested as a fallback
          (confidence 0.35).
        </p>

        <Input
          id="resolver-seeds"
          label="Creator Names (max 3, comma-separated)"
          placeholder="e.g. Patrick Bet-David, Kim Iversen, Glenn Beck"
          value={seedNames}
          onChange={(event) => setSeedNames(event.target.value)}
          className="mb-1"
        />
        <FieldHint>
          Names are fuzzy-matched against channel names already in the database. Guessed URLs are generated from the name slug if no match is found — verify before confirming.
        </FieldHint>

        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={resolverLoading}
          onClick={handleResolverSearch}
          className="mb-3"
        >
          Search
        </Button>

        {resolverResults.length > 0 && (
          <>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-[#6B6B6B]">
              Candidates — check the ones to add
            </p>
            <div className="max-h-52 space-y-2 overflow-y-auto pr-1">
              {resolverResults.map((seedResult) => (
                <div key={seedResult.seed_name} className="rounded-md border border-[#E8E4DC] p-2">
                  <p className="mb-1.5 text-xs font-semibold text-[#1A1A2E]">
                    &ldquo;{seedResult.seed_name}&rdquo;
                  </p>
                  {seedResult.candidates.map((candidate) => {
                    const key = `${seedResult.seed_name}|${candidate.channel_url}`;
                    const isGuessed = candidate.source === "guessed";
                    return (
                      <label key={key} className="mb-1.5 flex items-start gap-2 text-xs">
                        <input
                          type="checkbox"
                          className="mt-0.5 shrink-0"
                          checked={resolverSelected[key] ?? false}
                          onChange={(event) =>
                            setResolverSelected((prev) => ({ ...prev, [key]: event.target.checked }))
                          }
                        />
                        <span className="min-w-0">
                          <span className={`inline-block rounded px-1 py-0.5 text-[10px] font-medium uppercase ${candidate.platform === "rumble" ? "bg-[#FFF3CD] text-[#7A5B00]" : "bg-[#EEF7F0] text-[#2F6B3B]"}`}>
                            {candidate.platform}
                          </span>
                          {" "}
                          <span className="break-all text-[#1A1A2E]">{candidate.channel_url}</span>
                          {" "}
                          <span className={`text-[10px] ${isGuessed ? "text-[#C9A84C]" : "text-[#4F8A5B]"}`}>
                            {isGuessed ? `guess (${candidate.confidence})` : `match (${candidate.confidence})`}
                          </span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              ))}
            </div>
          </>
        )}

        {resolverResults.length === 0 && !resolverLoading && (
          <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-[#E8E4DC] py-8 text-center">
            <p className="text-xs text-[#6B6B6B]">Search results will appear here.<br />Select candidates to add them.</p>
          </div>
        )}

        <Button
          type="button"
          variant="accent"
          size="sm"
          loading={resolverConfirmLoading}
          disabled={selectedResolverCandidates.length === 0}
          onClick={handleResolverConfirm}
          className="mt-3"
        >
          Add {selectedResolverCandidates.length > 0 ? `${selectedResolverCandidates.length} ` : ""}Selected
        </Button>
        <p className="mt-1.5 text-[11px] text-[#6B6B6B]">
          Selected channels are added immediately with scrape triggered.
        </p>
        <div className="mt-2">
          <IntakeSummary summary={resolverSummary} />
          {resolverError ? <p className="mt-2 text-xs text-[#B22222]">{resolverError}</p> : null}
        </div>
      </div>
    </div>
  );
}
