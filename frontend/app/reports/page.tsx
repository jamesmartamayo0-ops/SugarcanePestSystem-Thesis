"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import {
  ReportsRequestError,
  getOperationalReport,
  type OperationalReport,
} from "@/lib/reports";
import type { PestCaseStatus } from "@/lib/pest-cases";

export default function ReportsPage() {
  const router = useRouter();
  const auth = useAuth();
  const [report, setReport] = useState<OperationalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [farmerFilter, setFarmerFilter] = useState<string>("all");
  const [farmFilter, setFarmFilter] = useState<string>("all");
  const [reportedFrom, setReportedFrom] = useState<string>("");
  const [reportedTo, setReportedTo] = useState<string>("");

  const authenticated = auth.status === "authenticated";

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const loadReport = useCallback(
    async (options: {
      status: string;
      farmerId: string;
      farmId: string;
      from: string;
      to: string;
    }) => {
      if (options.from !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(options.from)) {
        setFilterError("Reported-from must use YYYY-MM-DD format.");
        return;
      }
      if (options.to !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(options.to)) {
        setFilterError("Reported-to must use YYYY-MM-DD format.");
        return;
      }
      if (options.from !== "" && options.to !== "" && options.from > options.to) {
        setFilterError("Reported-from must not be later than reported-to.");
        return;
      }
      setFilterError(null);
      setLoading(true);
      setListError(null);
      try {
        const loaded = await getOperationalReport({
          status: (options.status === "all" ? "all" : options.status) as
            | PestCaseStatus
            | "all",
          farmerId: options.farmerId === "all" ? undefined : Number(options.farmerId),
          farmId: options.farmId === "all" ? undefined : Number(options.farmId),
          reportedFrom: options.from === "" ? undefined : options.from,
          reportedTo: options.to === "" ? undefined : options.to,
        });
        setReport(loaded);
      } catch (failure) {
        if (failure instanceof ReportsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        if (failure instanceof ReportsRequestError && failure.kind === "invalid") {
          setFilterError(failure.message);
          return;
        }
        setListError(
          failure instanceof ReportsRequestError
            ? failure.message
            : "Operational report could not be read.",
        );
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!authenticated) {
      return;
    }
    let active = true;
    (async () => {
      try {
        const loaded = await getOperationalReport();
        if (!active) {
          return;
        }
        setReport(loaded);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (failure instanceof ReportsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof ReportsRequestError
            ? failure.message
            : "Operational report could not be read.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [authenticated, router]);

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
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Operational Reports</h1>
        <p className="mt-2 text-sm text-slate-600">
          Factual workflow counts and case rows. No treatment-effectiveness scoring.
        </p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link
            href="/dashboard"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            Back to dashboard
          </Link>
          <Link
            href="/pest-cases"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View pest cases
          </Link>
        </div>

        <form
          aria-label="Report filters"
          onSubmit={(event) => {
            event.preventDefault();
            void loadReport({
              status: statusFilter,
              farmerId: farmerFilter,
              farmId: farmFilter,
              from: reportedFrom,
              to: reportedTo,
            });
          }}
          className="mt-8 grid gap-4 rounded-xl border border-slate-200 p-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          <div>
            <label htmlFor="report_status" className="block text-sm font-medium text-slate-700">
              Status
            </label>
            <select
              id="report_status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
            >
              <option value="all">All statuses</option>
              <option value="REPORTED">REPORTED</option>
              <option value="FOR_INSPECTION">FOR_INSPECTION</option>
              <option value="INSPECTION_SCHEDULED">INSPECTION_SCHEDULED</option>
              <option value="NOT_CONFIRMED">NOT_CONFIRMED</option>
              <option value="FIELD_VALIDATED">FIELD_VALIDATED</option>
              <option value="UNDER_INTERVENTION">UNDER_INTERVENTION</option>
              <option value="FOLLOW_UP_DUE">FOLLOW_UP_DUE</option>
              <option value="REINTERVENTION_REQUIRED">REINTERVENTION_REQUIRED</option>
              <option value="CLOSED">CLOSED</option>
            </select>
          </div>
          <div>
            <label htmlFor="report_farmer" className="block text-sm font-medium text-slate-700">
              Farmer ID
            </label>
            <input
              id="report_farmer"
              value={farmerFilter === "all" ? "" : farmerFilter}
              onChange={(event) => {
                setFarmerFilter(event.target.value.trim() === "" ? "all" : event.target.value.trim());
              }}
              placeholder="All"
              inputMode="numeric"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900"
            />
          </div>
          <div>
            <label htmlFor="report_farm" className="block text-sm font-medium text-slate-700">
              Farm ID
            </label>
            <input
              id="report_farm"
              value={farmFilter === "all" ? "" : farmFilter}
              onChange={(event) => {
                setFarmFilter(event.target.value.trim() === "" ? "all" : event.target.value.trim());
              }}
              placeholder="All"
              inputMode="numeric"
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900"
            />
          </div>
          <div>
            <label htmlFor="report_from" className="block text-sm font-medium text-slate-700">
              Reported from
            </label>
            <input
              id="report_from"
              type="date"
              value={reportedFrom}
              onChange={(event) => setReportedFrom(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900"
            />
          </div>
          <div>
            <label htmlFor="report_to" className="block text-sm font-medium text-slate-700">
              Reported to
            </label>
            <input
              id="report_to"
              type="date"
              value={reportedTo}
              onChange={(event) => setReportedTo(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-900"
            />
          </div>
          <div className="flex flex-wrap items-end gap-2 sm:col-span-2 lg:col-span-3">
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-emerald-700 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
            >
              {loading ? "Loading..." : "Apply filters"}
            </button>
            <button
              type="button"
              onClick={() => {
                setStatusFilter("all");
                setFarmerFilter("all");
                setFarmFilter("all");
                setReportedFrom("");
                setReportedTo("");
                setFilterError(null);
                void loadReport({ status: "all", farmerId: "all", farmId: "all", from: "", to: "" });
              }}
              disabled={loading}
              className="rounded-lg border border-slate-300 px-4 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
            >
              Clear filters
            </button>
          </div>
        </form>
        {filterError && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {filterError}
          </p>
        )}

        {loading ? (
          <p role="status" className="mt-6 text-sm text-slate-600">
            Loading operational report...
          </p>
        ) : listError ? (
          <p role="alert" className="mt-6 text-sm text-red-700">
            {listError}
          </p>
        ) : report ? (
          <div>
            <section aria-label="Report summary" className="mt-6">
              <h2 className="text-lg font-semibold text-slate-900">Summary</h2>
              <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Total cases</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {report.summary.total_cases}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Open cases</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {report.summary.open_cases}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Closed cases</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {report.summary.closed_cases}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-4">
                  <p className="text-sm font-medium text-slate-600">Follow-ups due</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-900">
                    {report.summary.follow_ups_due}
                  </p>
                </div>
              </div>
            </section>

            <section aria-label="Cases by status" className="mt-8">
              <h2 className="text-lg font-semibold text-slate-900">Cases by status</h2>
              <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                {(
                  Object.entries(report.by_status) as [string, number][]
                ).map(([status, count]) => (
                  <div key={status} className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                    <dt className="text-sm font-medium text-slate-600">{status}</dt>
                    <dd className="text-sm font-semibold text-slate-900">{count}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section aria-label="Follow-up summary" className="mt-8">
              <h2 className="text-lg font-semibold text-slate-900">Follow-up summary</h2>
              <dl className="mt-3 grid gap-3 sm:grid-cols-3">
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Pending follow-up</dt>
                  <dd className="text-sm font-semibold text-slate-900">{report.follow_up_summary.pending}</dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-2">
                  <dt className="text-sm font-medium text-red-800">Overdue</dt>
                  <dd className="text-sm font-semibold text-red-900">{report.follow_up_summary.overdue}</dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Completed reassessments</dt>
                  <dd className="text-sm font-semibold text-slate-900">{report.follow_up_summary.completed}</dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Resolved follow-up</dt>
                  <dd className="text-sm font-semibold text-slate-900">{report.follow_up_summary.resolved}</dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Further intervention required</dt>
                  <dd className="text-sm font-semibold text-slate-900">
                    {report.follow_up_summary.reintervention_required}
                  </dd>
                </div>
              </dl>
            </section>

            <section aria-label="Intervention summary" className="mt-8">
              <h2 className="text-lg font-semibold text-slate-900">Intervention summary</h2>
              <dl className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Completed interventions</dt>
                  <dd className="text-sm font-semibold text-slate-900">{report.intervention_summary.completed}</dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Pending interventions</dt>
                  <dd className="text-sm font-semibold text-slate-900">{report.intervention_summary.pending}</dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Cases with repeat intervention</dt>
                  <dd className="text-sm font-semibold text-slate-900">
                    {report.intervention_summary.cases_with_repeat_intervention}
                  </dd>
                </div>
                <div className="flex justify-between gap-4 rounded-lg border border-slate-200 px-4 py-2">
                  <dt className="text-sm font-medium text-slate-600">Total records</dt>
                  <dd className="text-sm font-semibold text-slate-900">{report.intervention_summary.total_records}</dd>
                </div>
              </dl>
            </section>

            <section aria-label="Report cases" className="mt-8">
              <h2 className="text-lg font-semibold text-slate-900">Report cases</h2>
              {report.cases.length === 0 ? (
                <p role="status" className="mt-3 text-sm text-slate-600">
                  No cases match the current filters.
                </p>
              ) : (
                <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full min-w-[860px] text-left text-sm">
                    <thead className="bg-slate-50 text-slate-600">
                      <tr>
                        <th scope="col" className="px-4 py-3 font-medium">Case</th>
                        <th scope="col" className="px-4 py-3 font-medium">Farmer / Farm</th>
                        <th scope="col" className="px-4 py-3 font-medium">Status</th>
                        <th scope="col" className="px-4 py-3 font-medium">Cycle / Follow-up</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {report.cases.map((entry) => (
                        <tr key={entry.case_id}>
                          <td className="px-4 py-3 text-slate-900">
                            #{entry.case_id} — {entry.pest_name}
                            <span className="block text-xs text-slate-600">
                              Reported {entry.reported_at ?? "—"} ·{" "}
                              {entry.reported_area_hectares.toFixed(2)} ha
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-900">
                            {entry.farmer ?? "—"}
                            <span className="block text-xs text-slate-600">
                              {entry.farm ?? "—"} · {entry.barangay ?? "—"}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-slate-900">{entry.current_status}</td>
                          <td className="px-4 py-3 text-slate-900">
                            {entry.latest_intervention_cycle === null
                              ? "—"
                              : `Cycle ${entry.latest_intervention_cycle}`}
                            <span className="block text-xs text-slate-600">
                              {entry.latest_follow_up_outcome ?? "No recorded follow-up"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </div>
        ) : null}
      </div>
    </main>
  );
}
