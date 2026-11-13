import type { IconName } from "../components/icons.tsx";
import { canAccessPath } from "./access-control.ts";
import type { UserRole } from "./auth.ts";

export type NavItem = {
  href: string;
  label: string;
  icon: IconName;
  /** In-page link to a section of another route; never marked active. */
  section?: boolean;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

/*
 * Authorized navigation. Every entry is filtered through the same route
 * rules that guard the pages (lib/access-control): Administrators see every
 * area; Agriculture Technicians see the operational areas only, because
 * Farmer, Farm, and Pest Case Records and User Management are ADMIN-only on
 * the backend. The Farm Monitoring Map lives on the dashboard and links to
 * its section.
 */
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [{ href: "/dashboard", label: "Dashboard", icon: "dashboard" }],
  },
  {
    label: "Records",
    items: [
      { href: "/farmers", label: "Farmers", icon: "farmers" },
      { href: "/farms", label: "Farms", icon: "farm" },
      { href: "/pest-cases", label: "Pest Cases", icon: "pest" },
    ],
  },
  {
    label: "Field Operations",
    items: [
      { href: "/inspections", label: "Inspections", icon: "inspection" },
      { href: "/interventions", label: "Interventions", icon: "intervention" },
      { href: "/follow-ups", label: "Follow-ups", icon: "follow-up" },
    ],
  },
  {
    label: "Monitoring",
    items: [
      { href: "/dashboard#farm-map", label: "Farm Monitoring Map", icon: "map", section: true },
      { href: "/reports", label: "Reports", icon: "reports" },
    ],
  },
  {
    label: "Administration",
    items: [{ href: "/admin", label: "User Management", icon: "user-admin" }],
  },
];

/** Navigation groups the role may open; empty groups are dropped. */
export function navigationFor(role: UserRole): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => canAccessPath(role, item.href)),
  })).filter((group) => group.items.length > 0);
}
