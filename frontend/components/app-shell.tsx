"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";
import { StatusScreen } from "@/components/ui";
import { routeAccess } from "@/lib/access-control";
import { logout, type UserRole } from "@/lib/auth";
import {
  BAIS_CITY_SEAL_ALT,
  BAIS_CITY_SEAL_SRC,
  OFFICE_NAME,
  SYSTEM_NAME,
} from "@/lib/branding";
import { navigationFor, type NavGroup, type NavItem } from "@/lib/navigation";

/*
 * Displays labels only. Underlying role values (ADMIN / TECHNICIAN)
 * are unchanged everywhere else.
 */
export function roleDisplayName(role: UserRole): string {
  return role === "ADMIN" ? "Administrator" : "Agriculture Technician";
}

function isNavActive(pathname: string, item: NavItem): boolean {
  if (item.section) {
    return false;
  }
  return pathname === item.href || pathname.startsWith(item.href + "/");
}

function initials(fullName: string): string {
  const letters = fullName
    .trim()
    .split(/\s+/)
    .map((part) => part.match(/\p{L}/u)?.[0] ?? "")
    .filter((letter) => letter !== "");
  if (letters.length === 0) {
    return "?";
  }
  const first = letters[0];
  const last = letters.length > 1 ? letters[letters.length - 1] : "";
  return (first + last).toUpperCase();
}

type Crumb = { label: string; href?: string };

function breadcrumbFor(pathname: string, groups: NavGroup[]): Crumb[] {
  for (const group of groups) {
    for (const item of group.items) {
      if (!isNavActive(pathname, item)) {
        continue;
      }
      if (pathname === item.href) {
        return [{ label: group.label }, { label: item.label }];
      }
      const rest = pathname.slice(item.href.length + 1);
      const detail = item.href === "/pest-cases" && /^\d+$/.test(rest) ? `Case #${rest}` : "Record";
      return [{ label: group.label }, { label: item.label, href: item.href }, { label: detail }];
    }
  }
  return [];
}

export function AppShell({ children }: { children: ReactNode }) {
  const rawPathname = usePathname();
  const pathname = rawPathname ?? "";
  const router = useRouter();
  const auth = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Mobile drawer: focus the close control, close on Escape, and close if
  // the viewport grows to the desktop layout while the drawer is open.
  useEffect(() => {
    if (!navOpen) {
      return;
    }
    closeButtonRef.current?.focus();
    const desktop = window.matchMedia("(min-width: 1024px)");
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setNavOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    function handleResize(event: MediaQueryListEvent) {
      if (event.matches) {
        setNavOpen(false);
      }
    }
    document.addEventListener("keydown", handleKey);
    desktop.addEventListener("change", handleResize);
    return () => {
      document.removeEventListener("keydown", handleKey);
      desktop.removeEventListener("change", handleResize);
    };
  }, [navOpen]);

  // Route guard: an ADMIN-only page (Farmer, Farm, Pest Case Records, User
  // Management) is never rendered for a role that may not open it, even when
  // the URL is entered directly. The backend rejects the same APIs with 403.
  const access =
    auth.status === "authenticated" ? routeAccess(auth.user.role, pathname) : null;
  const deniedRedirect = access !== null && !access.allowed ? access.redirectTo : null;
  useEffect(() => {
    if (deniedRedirect !== null) {
      router.replace(deniedRedirect);
    }
  }, [deniedRedirect, router]);

  // Public routes and non-authenticated states render untouched so
  // existing loading / redirect / error UI is preserved exactly.
  if (pathname === "/" || pathname === "/login" || auth.status !== "authenticated") {
    return <>{children}</>;
  }

  const currentUser = auth.user;
  const csrfToken = auth.csrfToken;
  const pageAllowed = access?.allowed ?? false;

  const visibleGroups = navigationFor(currentUser.role);

  const crumbs = pageAllowed ? breadcrumbFor(pathname, visibleGroups) : [];

  function closeNav() {
    setNavOpen(false);
  }

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
    <div className="gov-app" data-nav-open={navOpen ? "true" : undefined}>
      <a href="#gov-main-content" className="gov-skip-link">
        Skip to main content
      </a>

      <aside id="gov-sidebar" className="gov-sidebar" aria-label="Primary">
        <div className="gov-sidebar-brand">
          <span className="gov-sidebar-seal">
            <Image
              src={BAIS_CITY_SEAL_SRC}
              alt={BAIS_CITY_SEAL_ALT}
              width={104}
              height={104}
              loading="eager"
            />
          </span>
          <div>
            <p className="gov-sidebar-office">{OFFICE_NAME}</p>
            <p className="gov-sidebar-system">{SYSTEM_NAME}</p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="gov-sidebar-close"
            onClick={() => {
              setNavOpen(false);
              menuButtonRef.current?.focus();
            }}
            aria-label="Close navigation menu"
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        <nav className="gov-nav" aria-label="Primary navigation">
          {visibleGroups.map((group) => {
            const groupId = `gov-nav-${group.label.toLowerCase().replaceAll(" ", "-")}`;
            return (
              <div key={group.label}>
                <p id={groupId} className="gov-nav-group-label">
                  {group.label}
                </p>
                <ul className="gov-nav-list" aria-labelledby={groupId}>
                  {group.items.map((item) => (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={isNavActive(pathname, item) ? "page" : undefined}
                        className="gov-nav-link"
                        onClick={closeNav}
                      >
                        <Icon name={item.icon} size={18} />
                        <span>{item.label}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </nav>

        <div className="gov-sidebar-footer">
          <p>For authorized personnel of the {OFFICE_NAME}.</p>
        </div>
      </aside>

      <button
        type="button"
        className="gov-nav-backdrop"
        aria-hidden="true"
        tabIndex={-1}
        onClick={closeNav}
      />

      <div className="gov-workspace">
        <header className="gov-topbar">
          <button
            ref={menuButtonRef}
            type="button"
            className="gov-topbar-menu"
            aria-controls="gov-sidebar"
            aria-expanded={navOpen}
            aria-label="Open navigation menu"
            onClick={() => setNavOpen(true)}
          >
            <Icon name="menu" size={20} />
          </button>

          <nav aria-label="Breadcrumb" className="gov-breadcrumb">
            {crumbs.length > 0 && (
              <ol>
                {crumbs.map((crumb, index) => {
                  const last = index === crumbs.length - 1;
                  return (
                    <li key={`${crumb.label}-${index}`} aria-current={last ? "page" : undefined}>
                      {crumb.href && !last ? <Link href={crumb.href}>{crumb.label}</Link> : crumb.label}
                    </li>
                  );
                })}
              </ol>
            )}
          </nav>

          <div className="gov-topbar-user">
            <div className="gov-user">
              <span className="gov-avatar" aria-hidden="true">
                {initials(currentUser.full_name)}
              </span>
              <span className="gov-user-meta" aria-hidden="true">
                <span className="gov-user-name">{currentUser.full_name}</span>
                <span className="gov-user-role">{roleDisplayName(currentUser.role)}</span>
              </span>
              <span className="sr-only">
                Signed in as {currentUser.full_name}, {roleDisplayName(currentUser.role)}
              </span>
            </div>
            <span className="gov-topbar-divider" aria-hidden="true" />
            <button
              type="button"
              onClick={() => void handleSignOut()}
              disabled={signingOut}
              className="gov-button gov-button-secondary gov-button-compact"
            >
              <Icon name="logout" size={16} />
              {signingOut ? "Signing out..." : "Sign out"}
            </button>
          </div>
        </header>

        {signOutError && (
          <p role="alert" className="gov-shell-alert">
            Sign out could not be confirmed. Your session may still be active. Try again.
          </p>
        )}

        <div id="gov-main-content" className="gov-main" tabIndex={-1}>
          {pageAllowed ? (
            children
          ) : (
            <StatusScreen
              message={
                deniedRedirect !== null
                  ? "This page is available to Administrators only. Redirecting to your dashboard..."
                  : "This page is available to Administrators only."
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
