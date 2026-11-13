import assert from "node:assert/strict";
import test from "node:test";

import {
  ACCESS_DENIED_REDIRECT,
  accessibleLinks,
  canAccessPath,
  isAdminOnlyPath,
  routeAccess,
} from "./access-control.ts";
import { navigationFor } from "./navigation.ts";

const ADMIN_ROUTES = ["/farmers", "/farms", "/pest-cases", "/admin"];

test("Administrator may open every route", () => {
  for (const href of [...ADMIN_ROUTES, "/pest-cases/12", "/dashboard", "/reports"]) {
    assert.equal(canAccessPath("ADMIN", href), true, href);
    assert.deepEqual(routeAccess("ADMIN", href), { allowed: true });
  }
});

test("Technician is denied every administration route", () => {
  for (const href of [
    ...ADMIN_ROUTES,
    "/farmers/7",
    "/farms/7",
    "/pest-cases/12",
    "/pest-cases/12/timeline",
    "/admin/users",
  ]) {
    assert.equal(canAccessPath("TECHNICIAN", href), false, href);
    assert.deepEqual(routeAccess("TECHNICIAN", href), {
      allowed: false,
      redirectTo: ACCESS_DENIED_REDIRECT,
    });
  }
});

test("Technician keeps the operational routes", () => {
  for (const href of ["/dashboard", "/inspections", "/interventions", "/follow-ups", "/reports"]) {
    assert.equal(canAccessPath("TECHNICIAN", href), true, href);
  }
});

test("route matching ignores case, trailing slash, query, and hash", () => {
  for (const href of ["/PEST-CASES", "/pest-cases/", "/pest-cases?status=REPORTED", "/pest-cases/9#timeline"]) {
    assert.equal(isAdminOnlyPath(href), true, href);
  }
  assert.equal(isAdminOnlyPath("/pest-cases-archive"), false);
  assert.equal(isAdminOnlyPath("/dashboard"), false);
});

test("an unknown or missing role may open nothing", () => {
  assert.equal(canAccessPath(null, "/dashboard"), false);
  assert.equal(canAccessPath(undefined, "/pest-cases"), false);
  assert.deepEqual(routeAccess("TECHNICIAN", "/admin"), {
    allowed: false,
    redirectTo: "/dashboard",
  });
});

test("a denied role is never redirected to another denied route", () => {
  const deniedEverything = routeAccess("TECHNICIAN", "/farmers");
  assert.equal(deniedEverything.allowed, false);
  if (!deniedEverything.allowed) {
    assert.equal(canAccessPath("TECHNICIAN", deniedEverything.redirectTo ?? ""), true);
  }
});

test("accessibleLinks filters only the denied links", () => {
  const links = [
    { href: "/pest-cases", label: "Pest Cases" },
    { href: "/inspections", label: "Inspections" },
  ];
  assert.deepEqual(accessibleLinks("TECHNICIAN", links), [links[1]]);
  assert.deepEqual(accessibleLinks("ADMIN", links), links);
});

test("Administrator navigation includes every area", () => {
  const groups = navigationFor("ADMIN");
  const hrefs = groups.flatMap((group) => group.items.map((item) => item.href));
  for (const href of [...ADMIN_ROUTES, "/dashboard", "/inspections", "/interventions", "/follow-ups", "/reports"]) {
    assert.ok(hrefs.includes(href), href);
  }
});

test("Technician navigation hides Farmer, Farm, Pest Case, and User Management", () => {
  const hrefs = navigationFor("TECHNICIAN").flatMap((group) =>
    group.items.map((item) => item.href),
  );
  assert.deepEqual(hrefs, [
    "/dashboard",
    "/inspections",
    "/interventions",
    "/follow-ups",
    "/dashboard#farm-map",
    "/reports",
  ]);
  for (const href of ADMIN_ROUTES) {
    assert.ok(!hrefs.includes(href), href);
  }
});
