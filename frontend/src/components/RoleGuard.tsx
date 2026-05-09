"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useAuth } from "@/lib/AuthProvider";
import { canAccess, getPostLoginRedirect } from "@/lib/roles";
import { Loader2 } from "lucide-react";

interface RoleGuardProps {
  children: React.ReactNode;
  allowedRoles?: string[];
}

export function RoleGuard({ children, allowedRoles }: RoleGuardProps) {
  const { user, role, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading) return;

    // Not logged in → redirect to login
    if (!user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }

    // Backend verification is mandatory. If role is missing, treat as unauthorized.
    if (!role) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }

    // Role-specific check
    if (!canAccess(pathname, role)) {
      // Wrong role — redirect to their correct dashboard
      router.replace(getPostLoginRedirect(role));
    }

    // If specific roles provided, check against those
    if (allowedRoles && !allowedRoles.includes(role)) {
      router.replace(getPostLoginRedirect(role));
    }
  }, [user, role, loading, pathname, router, allowedRoles]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-paper">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-10 animate-spin text-leaf" />
          <p className="text-sm font-bold text-ink/50">Verifying access…</p>
        </div>
      </div>
    );
  }

  // Show nothing while redirect is happening
  if (!user || !role || !canAccess(pathname, role)) {
    return null;
  }

  return <>{children}</>;
}
