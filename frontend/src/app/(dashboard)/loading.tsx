/**
 * Loading state for dashboard routes.
 */
import { Spinner } from "@/components/ui/Spinner";

export default function DashboardLoading() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3">
      <Spinner size="lg" />
      <p className="text-sm text-[#6B6B6B]">Loading...</p>
    </div>
  );
}
