/**
 * SeedCreatorInput — input form for up to 3 seed creators.
 */
"use client";

import { Plus, X } from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";

interface SeedCreatorInputProps {
  seeds: string[];
  onChange: (seeds: string[]) => void;
  onSearch: () => void;
  loading: boolean;
}

export function SeedCreatorInput({
  seeds,
  onChange,
  onSearch,
  loading,
}: SeedCreatorInputProps) {
  const canAdd = seeds.length < 3;
  const hasValidSeed = seeds.some((s) => s.trim().length > 0);

  const updateSeed = (index: number, value: string) => {
    const next = [...seeds];
    next[index] = value;
    onChange(next);
  };

  const addSeed = () => {
    if (canAdd) {
      onChange([...seeds, ""]);
    }
  };

  const removeSeed = (index: number) => {
    onChange(seeds.filter((_, i) => i !== index));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (hasValidSeed) {
      onSearch();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-[#1A1A2E]">
          Seed Creators
        </h2>
        <p className="mt-1 text-sm text-[#6B6B6B]">
          Enter up to 3 proven creator names to find lookalikes
        </p>
      </div>

      <div className="space-y-3">
        {seeds.map((seed, idx) => (
          <div key={idx} className="flex items-end gap-2">
            <div className="flex-1">
              <Input
                id={`seed-${idx}`}
                label={`Creator ${idx + 1}`}
                placeholder="Creator name e.g. Glenn Beck"
                value={seed}
                onChange={(e) => updateSeed(idx, e.target.value)}
              />
            </div>
            {idx > 0 && (
              <button
                type="button"
                onClick={() => removeSeed(idx)}
                className="mb-0.5 flex h-9 w-9 items-center justify-center rounded-lg text-[#6B6B6B] transition-colors hover:bg-[#B22222]/10 hover:text-[#B22222] cursor-pointer"
              >
                <X size={16} />
              </button>
            )}
          </div>
        ))}
      </div>

      {canAdd && (
        <button
          type="button"
          onClick={addSeed}
          className="flex items-center gap-1.5 text-sm font-medium text-[#C9A84C] transition-colors hover:text-[#B8953E] cursor-pointer"
        >
          <Plus size={14} />
          Add Creator
        </button>
      )}

      <Button
        type="submit"
        variant="accent"
        size="lg"
        loading={loading}
        disabled={!hasValidSeed}
        className="w-full"
      >
        Find Lookalikes
      </Button>
    </form>
  );
}
