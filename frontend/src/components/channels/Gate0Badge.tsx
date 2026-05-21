/**
 * Gate0Badge - displays Gate 0 compliance status.
 */
import { Badge } from "@/components/ui/Badge";
import type { Gate0Status } from "@/types";

interface Gate0BadgeProps {
  status: Gate0Status;
}

const STATUS_CONFIG: Record<
  Gate0Status,
  { variant: "muted" | "success" | "danger" | "warning"; label: string }
> = {
  unchecked: { variant: "muted", label: "Not Checked" },
  pending: { variant: "warning", label: "Checking..." },
  clean: { variant: "success", label: "Clean Lead" },
  dirty: { variant: "danger", label: "Brand Risk" },
};

export function Gate0Badge({ status }: Gate0BadgeProps) {
  const config = STATUS_CONFIG[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
