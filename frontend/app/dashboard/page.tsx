"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { logout } from "@/lib/auth";

export default function DashboardPage() {
  const router = useRouter();
  const auth = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState(false);

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  async function handleLogout() {
    if (auth.status !== "authenticated") {
      return;
    }

    setLoggingOut(true);
    setLogoutError(false);
    try {
      await logout(auth.csrfToken);
      auth.setSession(null);
      router.replace("/login");
    } catch {
      // Keep the displayed session until the server confirms logout.
      setLogoutError(true);
    } finally {
      setLoggingOut(false);
    }
  }

  if (auth.status === "loading") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="status">Checking your session...</p>
      </main>
    );
  }

  if (auth.status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="status">Redirecting to sign in...</p>
      </main>
    );
  }

  if (auth.status === "error") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Unable to verify your session</h1>
        <p className="mt-3 text-slate-600">
          The authentication service is unavailable. Reload this page to try again.
        </p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="mt-6 rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white"
        >
          Reload
        </button>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-2 text-sm text-slate-600">
          Manage farmer and farm records for pest inspection workflows.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link
            href="/farmers"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Farmer Management
          </Link>
          <Link
            href="/farms"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Farm Management
          </Link>
          <Link
            href="/pest-cases"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Pest Case Reporting
          </Link>
          <Link
            href="/inspections"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Inspection Scheduling
          </Link>
          {auth.user.role === "ADMIN" && (
            <Link
              href="/admin"
              className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
            >
              Admin Management
            </Link>
          )}
        </div>

        <dl className="mt-8 divide-y divide-slate-200 border-y border-slate-200">
          <div className="flex justify-between gap-4 py-3">
            <dt className="font-medium text-slate-600">Full name</dt>
            <dd className="text-right text-slate-900">{auth.user.full_name}</dd>
          </div>
          <div className="flex justify-between gap-4 py-3">
            <dt className="font-medium text-slate-600">Username</dt>
            <dd className="text-right text-slate-900">{auth.user.username}</dd>
          </div>
          <div className="flex justify-between gap-4 py-3">
            <dt className="font-medium text-slate-600">Role</dt>
            <dd className="text-right text-slate-900">{auth.user.role}</dd>
          </div>
        </dl>

        {logoutError && (
          <p role="alert" className="mt-6 text-sm text-red-700">
            Sign out could not be confirmed. Your session may still be active. Try again or reload.
          </p>
        )}
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="mt-6 rounded-lg bg-slate-800 px-4 py-2 font-medium text-white hover:bg-slate-900 disabled:cursor-wait disabled:opacity-60"
        >
          {loggingOut ? "Signing out..." : "Sign out"}
        </button>
      </div>
    </main>
  );
}
