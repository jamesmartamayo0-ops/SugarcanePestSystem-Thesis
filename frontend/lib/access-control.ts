import type { UserRole } from "./auth.ts";

/*
 * Route-level authorization for the frontend.
 *
 * The backend is the real gate: the Farmer, Farm, and Pest Case Records APIs
 * and User Management answer 403 to an Agriculture Technician. These rules
 * mirror that so the interface never offers or renders an administration
 * area the account cannot use. Technicians reach the farmer, farm, and case
 * context of their assigned work through Inspections, Interventions, and
 * Follow-ups instead.
 */

export const ADMIN_ONLY_ROUTES = ["/farmers", "/farms", "/pest-cases", "/admin"] as const;

/** Where a signed-in user is sent when the requested page is not available to them. */
export const ACCESS_DENIED_REDIRECT = "/dashboard";

function normalizePath(href: string): string {
  let path = href.split(/[?#]/, 1)[0] ?? "";
  try {
    path = decodeURIComponent(path);
  } catch {
    // Keep the raw value; a malformed escape cannot match a route anyway.
  }
  path = path.trim().toLowerCase().replace(/\/{2,}/g, "/");
  if (path.length > 1) {
    path = path.replace(/\/+$/, "");
  }
  return path === "" ? "/" : path;
}

export function isAdminOnlyPath(href: string): boolean {
  const path = normalizePath(href);
  return ADMIN_ONLY_ROUTES.some((route) => path === route || path.startsWith(`${route}/`));
}

export function canAccessPath(role: UserRole | null | undefined, href: string): boolean {
  if (role === "ADMIN") {
    return true;
  }
  if (role === "TECHNICIAN") {
    return !isAdminOnlyPath(href);
  }
  return false;
}

export type RouteAccess =
  | { allowed: true }
  | { allowed: false; redirectTo: string | null };

/**
 * Decision used by the application shell before rendering a page. A denied
 * route never renders; the redirect target is only offered when the same
 * role may open it, so the guard cannot loop.
 */
export function routeAccess(role: UserRole, pathname: string): RouteAccess {
  if (canAccessPath(role, pathname)) {
    return { allowed: true };
  }
  return {
    allowed: false,
    redirectTo: canAccessPath(role, ACCESS_DENIED_REDIRECT) ? ACCESS_DENIED_REDIRECT : null,
  };
}

/** Keeps only the links the role may open (page headers, related-page lists). */
export function accessibleLinks<T extends { href: string }>(
  role: UserRole | null | undefined,
  links: T[],
): T[] {
  return links.filter((link) => canAccessPath(role, link.href));
}
