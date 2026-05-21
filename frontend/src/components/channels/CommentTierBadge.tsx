/**
 * CommentTierBadge — displays comment engagement tier.
 */
import { Badge } from "@/components/ui/Badge";
import type { CommentTier } from "@/types";

interface CommentTierBadgeProps {
  tier?: CommentTier | null;
}

const TIER_CONFIG: Record<
  CommentTier,
  { variant: "muted" | "info" | "purple"; label: string }
> = {
  active: { variant: "muted", label: "Active" },
  sweet_spot: { variant: "info", label: "Sweet Spot" },
  whale: { variant: "purple", label: "Whale" },
};

export function CommentTierBadge({ tier }: CommentTierBadgeProps) {
  const config = tier ? TIER_CONFIG[tier] : null;
  if (!config) {
    return <span className="text-sm text-[#6B6B6B]">—</span>;
  }
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
