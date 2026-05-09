// Role constants matching Firebase custom claims exactly
export const ROLES = {
  SUPER_ADMIN: "super_admin",
  MUNICIPAL_ADMIN: "municipal_admin",
  DONOR: "donor",
  NGO_COORDINATOR: "ngo_coordinator",
  NGO_VOLUNTEER: "ngo_volunteer",
} as const;

export type Role = (typeof ROLES)[keyof typeof ROLES];

// Maps each role to its dashboard route
export const ROLE_REDIRECT: Record<Role, string> = {
  super_admin: "/admin",
  municipal_admin: "/municipal",
  donor: "/donor",
  ngo_coordinator: "/ngo",
  ngo_volunteer: "/volunteer",
};

// Maps each protected route to which roles are allowed
export const ROUTE_ROLES: Record<string, Role[]> = {
  "/donor": ["donor"],
  "/donor/donate": ["donor"],
  "/donor/reports": ["donor"],
  "/donor/history": ["donor"],
  "/ngo": ["ngo_coordinator"],
  "/ngo/emergency": ["ngo_coordinator"],
  "/ngo/profile": ["ngo_coordinator"],
  "/ngo/history": ["ngo_coordinator"],
  "/volunteer": ["ngo_volunteer"],
  "/admin": ["super_admin"],
  "/admin/users": ["super_admin"],
  "/municipal": ["municipal_admin", "super_admin"],
};

export function getPostLoginRedirect(role: string): string {
  return ROLE_REDIRECT[role as Role] ?? "/";
}

export function canAccess(route: string, role: string | null): boolean {
  if (route.startsWith("/volunteer/register")) return true;
  if (!role) return false;
  // Find matching route prefix
  const allowed = Object.entries(ROUTE_ROLES).find(([r]) => route.startsWith(r));
  if (!allowed) return true; // Public route
  return allowed[1].includes(role as Role);
}
