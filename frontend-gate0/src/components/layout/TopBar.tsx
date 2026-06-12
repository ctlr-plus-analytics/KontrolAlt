"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, LayoutDashboard, Shield } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const BASE_NAV: NavItem[] = [
  { label: "Channels", href: "/", icon: <LayoutDashboard size={15} /> },
];

function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/channel");
  return pathname.startsWith(href);
}

export function TopBar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, signOut } = useAuth();

  const appRole = user?.app_metadata?.role;
  const appAdmin = user?.app_metadata?.is_admin;
  const userRole = user?.user_metadata?.role;
  const userAdmin = user?.user_metadata?.is_admin;
  const isAdminUser =
    appRole === "admin" ||
    appAdmin === true ||
    appAdmin === "true" ||
    userRole === "admin" ||
    userAdmin === true ||
    userAdmin === "true";

  const navItems: NavItem[] = isAdminUser
    ? [...BASE_NAV, { label: "Admin", href: "/admin", icon: <Shield size={15} /> }]
    : BASE_NAV;

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
  };

  const initial = user?.email?.charAt(0)?.toUpperCase() ?? "U";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#E8E4DC] bg-white px-6">
      {/* ── Left: logo + nav ── */}
      <div className="flex items-center gap-6">
        <Link
          href="/"
          className="text-sm font-bold tracking-widest text-[#C9A84C] hover:opacity-80 transition-opacity"
        >
          KONTROL_ALT
        </Link>

        <div className="h-5 w-px bg-[#E8E4DC]" />

        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const active = isActive(item.href, pathname);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-150",
                  active
                    ? "bg-[#C9A84C]/10 text-[#C9A84C]"
                    : "text-[#1A1A2E]/50 hover:bg-[#1A1A2E]/5 hover:text-[#1A1A2E]"
                )}
              >
                {item.icon}
                {item.label}
                {active && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#C9A84C]" />
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* ── Right: user info + sign out ── */}
      <div className="flex items-center gap-3">
        <p className="hidden text-xs text-[#1A1A2E]/40 sm:block truncate max-w-[200px]">
          {user?.email ?? ""}
        </p>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#C9A84C] text-xs font-bold text-white shrink-0">
          {initial}
        </div>
        <button
          onClick={handleSignOut}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-[#1A1A2E]/40 transition-colors hover:bg-[#1A1A2E]/5 hover:text-[#1A1A2E] cursor-pointer"
          title="Sign out"
        >
          <LogOut size={14} />
          <span className="hidden sm:block">Sign Out</span>
        </button>
      </div>
    </header>
  );
}
