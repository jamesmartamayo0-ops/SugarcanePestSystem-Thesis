"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { logout } from "@/lib/auth";
import {
  DashboardRequestError,
  getDashboardSummary,
  type DashboardSummary,
} from "@/lib/dashboard";

function statusBadge(status: string): string {
  if (status === "CLOSED") {
    return "bg-slate-800 text-white";
  }
  if (status === "REINTERVENTION_REQUIRED") {
    return "bg-orange-100 text-orange-800";
  }
  if (status === "FOLLOW_UP_DUE") {
    return "bg-teal-100 text-teal-800";
  }
  if (status === "UNDER_INTERVENTION") {
    return "bg-violet-100 text-violet-800";
  }
  if (status === "FIELD_VALIDATED") {
    return "bg-emerald-100 text-emerald-800";
  }
  return "bg-sky-100 text-sky-800";
}

export default function DashboardPage() {
  const router = useRouter();
  const auth = useAuth();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  useEffect(() => {
    if (auth.status !== "authenticated") {
      return;
    }
    let active = true;
    (async () => {
      setLoadingSummary(true);
      try {
        const loaded = await getDashboardSummary();
        if (!active) {
          return;
        }
        setSummary(loaded);
        setSummaryError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          failure instanceof DashboardRequestError &&
          failure.kind === "unauthenticated"
        ) {
          router.replace("/login");
          return;
        }
        setSummaryError(
          failure instanceof DashboardRequestError
            ? failure.message
            : "Dashboard summary could not be read.",
        );
      } finally {
        if (active) {
          setLoadingSummary(false);
        }
      }
    })();
    return () => {
      active = false;
    };
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

  const action = summary?.action_needed;

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-2 text-sm text-slate-600">
          Operational overview of farmer, farm, and pest-case workflows.
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
          <Link
            href="/interventions"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Intervention Management
          </Link>
          <Link
            href="/follow-ups"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Follow-up &amp; Reassessment
          </Link>
          <Link
            href="/reports"
            className="inline-flex rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50"
          >
            Operational Reports
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

        <section aria-label="Operational summary" className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Operational summary</h2>
          {loadingSummary ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading operational summary...
            </p>
          ) : summaryError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {summaryError}
            </p>
          ) : summary ? (
            <div>
              <div className="mt-4 grid gap-4 sm:grid-cols-3">
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Farmers</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {summary.totals.farmers}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Farms</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {summary.totals.farms}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Pest Cases</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {summary.totals.pest_cases}
                  </p>
                </div>
              </div>

              <h3 className="mt-8 text-sm font-semibold text-slate-900">Workflow queues</h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Link
                  href="/pest-cases?status=REPORTED"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Reported</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.REPORTED}
                  </p>
                </Link>
                <Link
                  href="/inspections"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">For Inspection</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.FOR_INSPECTION}
                  </p>
                </Link>
                <Link
                  href="/inspections"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Inspection Scheduled</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.INSPECTION_SCHEDULED}
                  </p>
                </Link>
                <Link
                  href="/pest-cases?status=NOT_CONFIRMED"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Not Confirmed</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.NOT_CONFIRMED}
                  </p>
                </Link>
                <Link
                  href="/interventions"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Field Validated</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.FIELD_VALIDATED}
                  </p>
                </Link>
                <Link
                  href="/interventions"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Under Intervention</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.UNDER_INTERVENTION}
                  </p>
                </Link>
                <Link
                  href="/follow-ups"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Follow-up Due</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.FOLLOW_UP_DUE}
                  </p>
                </Link>
                <Link
                  href="/follow-ups"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Reintervention Required</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.REINTERVENTION_REQUIRED}
                  </p>
                </Link>
                <Link
                  href="/pest-cases?status=CLOSED"
                  className="rounded-xl border border-slate-200 p-4 hover:bg-slate-50"
                >
                  <p className="text-sm font-medium text-slate-600">Closed</p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.by_status.CLOSED}
                  </p>
                </Link>
              </div>

              <h3 className="mt-8 text-sm font-semibold text-slate-900">Needs attention</h3>
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                  <p className="text-sm font-medium text-red-800">Overdue follow-ups</p>
                  <p className="mt-1 text-xl font-semibold text-red-900">
                    {summary.action_needed.overdue_follow_ups}
                  </p>
                  <p className="mt-1 text-xs text-red-700">
                    Due before today (Asia/Manila) and still awaiting follow-up.
                  </p>
                </div>
                <div className="rounded-xl border border-orange-200 bg-orange-50 p-4">
                  <p className="text-sm font-medium text-orange-800">
                    Requiring reintervention
                  </p>
                  <p className="mt-1 text-xl font-semibold text-orange-900">
                    {summary.action_needed.reintervention_required}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">
                    Waiting for inspection scheduling
                  </p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.action_needed.awaiting_inspection_scheduling}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">
                    Validated awaiting intervention
                  </p>
                  <p className="mt-1 text-xl font-semibold text-slate-900">
                    {summary.action_needed.validated_awaiting_intervention}
                  </p>
                </div>
              </div>

              <h3 className="mt-8 text-sm font-semibold text-slate-900">Recent activity</h3>
              {summary.recent_cases.length === 0 ? (
                <p role="status" className="mt-3 text-sm text-slate-600">
                  No pest cases yet.
                </p>
              ) : (
                <ul className="mt-3 divide-y divide-slate-200 rounded-xl border border-slate-200">
                  {summary.recent_cases.map((entry) => (
                    <li key={entry.id} className="flex items-center justify-between gap-4 px-4 py-3">
                      <span className="text-sm text-slate-900">
                        #{entry.id} — {entry.pest_name}
                        <span className="block text-xs text-slate-600">
                          Updated {entry.updated_at ?? "—"}
                        </span>
                      </span>
                      <span className="flex items-center gap-2">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadge(entry.status)}`}
                        >
                          {entry.status}
                        </span>
                        <Link
                          href={`/pest-cases/${entry.id}`}
                          className="text-sm font-medium text-emerald-700 hover:text-emerald-800"
                        >
                          Timeline
                        </Link>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {action && (
                <p className="mt-4 text-xs text-slate-500">
                  Follow-ups due: {action.follow_ups_due} · In progress:{" "}
                  {action.interventions_in_progress} · Scheduled inspections:{" "}
                  {action.inspections_scheduled_awaiting_validation}
                </p>
              )}
            </div>
          ) : null}
        </section>

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
