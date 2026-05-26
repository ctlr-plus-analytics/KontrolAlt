/**
 * TopBar — top navigation bar for the dashboard.
 */
"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";

const PAGE_TITLES: Record<string, string> = {
  "/": "Channels",
  "/lookalike": "Lookalike Search",
  "/admin": "Admin Control",
};

function getPageTitle(pathname: string): string {
  if (pathname.startsWith("/channel/")) {
    return "Channel Detail";
  }
  return PAGE_TITLES[pathname] ?? "Dashboard";
}

export function TopBar() {
  const pathname = usePathname();
  const { user } = useAuth();

  const initial = user?.email?.charAt(0)?.toUpperCase() ?? "U";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#E8E4DC] bg-white px-6">
      <h2 className="text-lg font-semibold tracking-tight text-[#1A1A2E]">
        {getPageTitle(pathname)}
      </h2>

      <div className="flex items-center gap-4">
        {/* Platform Pill */}
        <span className="rounded-full border border-[#E8E4DC] px-3 py-1 text-xs font-medium text-[#1A1A2E]">
          Rumble + BitChute + Substack
        </span>

        {/* User Avatar */}
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#C9A84C] text-xs font-bold text-white">
          {initial}
        </div>
      </div>
    </header>
  );
}
