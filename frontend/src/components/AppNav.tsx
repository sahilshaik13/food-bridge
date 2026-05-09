"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Globe, LogOut, User, Bell, ChevronDown } from "lucide-react";
import { useAuth } from "@/lib/AuthProvider";
import { getPostLoginRedirect } from "@/lib/roles";
import { useEffect, useMemo } from "react";

const ROLE_LABEL: Record<string, string> = {
  super_admin: "Super Admin",
  municipal_admin: "Municipal Admin",
  donor: "Restaurant / Donor",
  ngo_coordinator: "NGO Coordinator",
  ngo_volunteer: "Field Volunteer",
};

const ROLE_COLOR: Record<string, string> = {
  super_admin: "bg-chili text-white",
  municipal_admin: "bg-civic text-white",
  donor: "bg-leaf text-white",
  ngo_coordinator: "bg-saffron text-ink",
  ngo_volunteer: "bg-ink text-paper",
};

export function AppNav() {
  const { user, role, profile, loading, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const dashboardHref = useMemo(() => {
    if (!role) return "/";
    return getPostLoginRedirect(role);
  }, [role]);

  const handleSignOut = async () => {
    await signOut();
    router.push("/");
  };

  return (
    <nav className="sticky top-0 z-50 border-b border-ink/8 bg-paper/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between gap-4 px-5">
        {/* Logo */}
        <Link
          href={role ? getPostLoginRedirect(role) : "/"}
          className="flex items-center gap-2 font-bold text-leaf"
        >
          <Globe className="size-5" />
          <span className="text-lg">FoodBridge</span>
        </Link>

        {/* Right side */}
        <div className="flex items-center gap-3">
          {loading ? (
            <div className="h-8 w-32 animate-pulse rounded-full bg-ink/10" />
          ) : user && role ? (
            /* ── LOGGED IN ── */
            <>
              {/* Role badge */}
              <span className={`hidden rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-widest sm:inline-block ${ROLE_COLOR[role] ?? "bg-field text-ink"}`}>
                {ROLE_LABEL[role] ?? role}
              </span>

              {/* Notifications */}
              <button className="relative rounded-full p-1.5 text-ink/60 hover:bg-field hover:text-ink">
                <Bell className="size-5" />
              </button>

              {/* Profile dropdown */}
              <div className="group relative">
                <button className="flex items-center gap-2 rounded-full border border-ink/10 bg-white pl-3 pr-2 py-1.5 text-sm font-bold text-ink shadow-sm hover:bg-field">
                  <span className="max-w-[120px] truncate">
                    {profile?.name || profile?.display_name || user.email?.split("@")[0]}
                  </span>
                  <User className="size-4 text-ink/50" />
                  <ChevronDown className="size-3 text-ink/40 transition-transform group-hover:rotate-180" />
                </button>

                {/* Dropdown */}
                <div className="invisible absolute right-0 top-full mt-2 w-52 rounded-xl border border-ink/10 bg-white p-2 shadow-lift group-hover:visible">
                  <div className="mb-2 border-b border-ink/5 px-3 pb-2 pt-1">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-ink/40">Signed in as</p>
                    <p className="truncate text-sm font-bold text-ink">{user.email}</p>
                  </div>
                  <Link
                    href={dashboardHref}
                    className="block rounded-lg px-3 py-2 text-sm font-bold text-ink/70 hover:bg-field hover:text-ink"
                  >
                    My Dashboard
                  </Link>
                  {role === "ngo_coordinator" && (
                    <Link
                      href="/ngo/history"
                      className="block rounded-lg px-3 py-2 text-sm font-bold text-ink/70 hover:bg-field hover:text-ink"
                    >
                      History
                    </Link>
                  )}
                  {role === "donor" && (
                    <Link
                      href="/donor/history"
                      className="block rounded-lg px-3 py-2 text-sm font-bold text-ink/70 hover:bg-field hover:text-ink"
                    >
                      History
                    </Link>
                  )}
                  <button
                    onClick={handleSignOut}
                    className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-bold text-chili hover:bg-chili/5"
                  >
                    <LogOut className="size-4" />
                    Sign Out
                  </button>
                </div>
              </div>
            </>
          ) : (
            /* ── LOGGED OUT ── */
            <>
              <Link
                href="/login"
                className="rounded-full border border-ink/15 px-4 py-1.5 text-sm font-bold text-ink hover:bg-field"
              >
                Sign In
              </Link>
              <Link
                href="/onboarding/donor"
                className="rounded-full bg-leaf px-4 py-1.5 text-sm font-bold text-white shadow-line hover:bg-ink"
              >
                Register
              </Link>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
