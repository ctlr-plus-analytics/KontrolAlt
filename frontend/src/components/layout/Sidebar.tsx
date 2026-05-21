/**
 * Sidebar — navigation sidebar for the dashboard.
 */
"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutDashboard, GitBranch, LogOut, Shield } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const BASE_NAV_ITEMS: NavItem[] = [
  {
    label: "Channels",
    href: "/",
    icon: <LayoutDashboard size={18} />,
  },
  {
    label: "Lookalike",
    href: "/lookalike",
    icon: <GitBranch size={18} />,
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();
  const appRole = user?.app_metadata?.role;
  const appAdmin = user?.app_metadata?.is_admin;
  const userRole = user?.user_metadata?.role;
  const userAdmin = user?.user_metadata?.is_admin;
  const isAdmin =
    appRole === "admin" ||
    appAdmin === true ||
    appAdmin === "true" ||
    userRole === "admin" ||
    userAdmin === true ||
    userAdmin === "true";
  const navItems: NavItem[] = isAdmin
    ? [
        ...BASE_NAV_ITEMS,
        {
          label: "Admin",
          href: "/admin",
          icon: <Shield size={18} />,
        },
      ]
    : BASE_NAV_ITEMS;

  const isActive = (href: string): boolean => {
    if (href === "/") {
      return pathname === "/" || pathname.startsWith("/channel");
    }
    return pathname.startsWith(href);
  };

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-[#1A1A2E]">
      {/* ─── Logo ─── */}
      <div className="flex h-14 items-center px-6">
        <span className="text-sm font-bold tracking-widest text-[#C9A84C]">
          KONTROL_ALT
        </span>
      </div>
      <div className="mx-6 mb-4 h-px bg-[#C9A84C]/20" />

      {/* ─── Navigation ─── */}
      <nav className="flex-1 px-3">
        <ul className="space-y-1">
          {navItems.map((item) => {
            const active = isActive(item.href);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                    active
                      ? "border-l-4 border-[#C9A84C] bg-[#C9A84C]/10 text-[#C9A84C] pl-2"
                      : "text-[#F7F4EE]/60 hover:bg-[#F7F4EE]/5 hover:text-[#F7F4EE]"
                  )}
                >
                  {item.icon}
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* ─── User Section ─── */}
      <div className="border-t border-[#F7F4EE]/10 p-4">
        <p className="mb-3 truncate text-xs text-[#F7F4EE]/40">
          {user?.email ?? "—"}
        </p>
        <button
          onClick={handleSignOut}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-[#F7F4EE]/50 transition-colors hover:bg-[#F7F4EE]/5 hover:text-[#F7F4EE] cursor-pointer"
        >
          <LogOut size={14} />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
