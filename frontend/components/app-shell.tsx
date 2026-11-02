"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { logout, type UserRole } from "@/lib/auth";

type NavItem = {
  href: string;
  label: string;
  adminOnly?: boolean;
};

/*
 * Authorized navigation. Permission logic is intentionally unchanged:
 * every authenticated role sees the operational areas, while
 * User Management remains ADMIN-only (mirrors the dashboard link
 * gating and the /admin page redirect).
 */
const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/farmers", label: "Farmers" },
  { href: "/farms", label: "Farms" },
  { href: "/pest-cases", label: "Pest Cases" },
  { href: "/inspections", label: "Inspections" },
  { href: "/interventions", label: "Interventions" },
  { href: "/follow-ups", label: "Follow-ups" },
  { href: "/reports", label: "Reports" },
  { href: "/admin", label: "User Management", adminOnly: true },
];

/*
 * Display labels only. Underlying role values (ADMIN / TECHNICIAN)
 * are unchanged everywhere else.
 */
export function roleDisplayName(role: UserRole): string {
  return role === "ADMIN" ? "Administrator" : "Agriculture Technician";
}

function isNavActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(href + "/");
}

export function AppShell({ children }: { children: ReactNode }) {
  const rawPathname = usePathname();
  const pathname = rawPathname ?? "";
  const router = useRouter();
  const auth = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(false);

  // Public routes and non-authenticated states render untouched so
  // existing loading / redirect / error UI is preserved exactly.
  if (pathname === "/" || pathname === "/login" || auth.status !== "authenticated") {
    return <>{children}</>;
  }

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.adminOnly || auth.user.role === "ADMIN",
  );

  // Capture narrowed session values for use inside event handlers.
  const currentUser = auth.user;
  const csrfToken = auth.csrfToken;

  async function handleSignOut() {
    if (signingOut) {
      return;
    }
    setSigningOut(true);
    setSignOutError(false);
    try {
      await logout(csrfToken);
      auth.setSession(null);
      router.replace("/login");
    } catch {
      // Keep the displayed session until the server confirms sign out.
      setSignOutError(true);
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <div className="gov-app">
      <a href="#gov-main-content" className="gov-skip-link">
        Skip to main content
      </a>
      <header className="gov-header">
        <div className="gov-header-brand">
          <strong>Bais City Agriculturist&apos;s Office</strong>
          <span>
            Sugarcane Pest Inspection and Intervention Workflow Management System
          </span>
        </div>
        <div className="gov-header-user">
          <p>
            <strong>{currentUser.full_name}</strong>
            <span className="gov-role-badge">
              {roleDisplayName(currentUser.role)}
            </span>
          </p>
          <button
            type="button"
            onClick={() => void handleSignOut()}
            disabled={signingOut}
            className="gov-button gov-button-secondary"
          >
            {signingOut ? "Signing out..." : "Sign out"}
          </button>
          {signOutError && (
            <p role="alert">
              Sign out could not be confirmed. Your session may still be
              active. Try again.
            </p>
          )}
        </div>
      </header>
      <div className="gov-layout">
        <aside className="gov-sidebar" aria-label="Primary">
          <nav className="gov-nav" aria-label="Primary navigation">
            {visibleItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={
                  isNavActive(pathname, item.href) ? "page" : undefined
                }
                className="gov-nav-link"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <div id="gov-main-content" className="gov-main">
          {children}
        </div>
      </div>
    </div>
  );
}
