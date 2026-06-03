/**
 * Gate0Badge - displays previous gold affiliation status.
 */
import { Badge } from "@/components/ui/Badge";
import type { Gate0Status } from "@/types";

interface Gate0BadgeProps {
  status: Gate0Status;
  flaggedBrand?: string | null;
}

const STATUS_CONFIG: Record<
  Gate0Status,
  { variant: "muted" | "success" | "danger" | "warning"; label: string }
> = {
  unchecked: { variant: "muted", label: "No" },
  pending: { variant: "warning", label: "No" },
  clean: { variant: "success", label: "No" },
  needs_review: { variant: "warning", label: "Review" },
  dirty: { variant: "danger", label: "Yes — Other company" },
};

function getAffiliationLabel(flaggedBrand?: string | null): string {
  if (!flaggedBrand) return "Yes — Other company";
  const normalized = flaggedBrand.trim().toLowerCase();
  if (normalized.includes("goldco")) return "Yes — Goldco";
  if (normalized.includes("augusta")) return "Yes — Augusta Precious Metals";
  if (normalized.includes("birch")) return "Yes — Birch Gold";
  if (normalized.includes("noble")) return "Yes — Noble Gold";
  return "Yes — Other company";
}

export function Gate0Badge({ status, flaggedBrand }: Gate0BadgeProps) {
  const config = STATUS_CONFIG[status];
  const label = status === "dirty" ? getAffiliationLabel(flaggedBrand) : config.label;
  return <Badge variant={config.variant}>{label}</Badge>;
}
