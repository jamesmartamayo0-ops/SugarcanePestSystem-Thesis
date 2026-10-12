"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { workflowLabel } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import {
  ReportsRequestError,
  getOperationalReport,
  type OperationalReport,
} from "@/lib/reports";
import type { PestCaseStatus } from "@/lib/pest-cases";

// Rendering only: date-only values retain their calendar day; timestamps use Manila time.
function formatRecordDate(value: string | null): string {
  if (value === null) {
    return "—";
  }
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  // Do not guess a timezone for an unqualified timestamp.
  if (!dateOnly && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) {
    return value;
  }
  const parsed = new Date(dateOnly ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-PH", {
    dateStyle: "medium",
    ...(dateOnly ? {} : { timeStyle: "short" as const }),
    timeZone: dateOnly ? "UTC" : "Asia/Manila",
  }).format(parsed);
}

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
    <main className="gov-page">
      <header className="gov-page-header">
        <h1 className="gov-page-title">Operational Reports</h1>
        <p className="gov-page-description">Factual workflow counts and case rows. No treatment-effectiveness scoring.</p>
        <Link href="/pest-cases" className="gov-activity-link">View pest cases</Link>
      </header>

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
          className="gov-card gov-record-section gov-form gov-report-filters"
        >
          <h2 className="gov-record-title gov-field-wide">Filter report</h2>
          <div className="gov-field">
            <label htmlFor="report_status" className="gov-label">
              Status
            </label>
            <select
              id="report_status"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="gov-select"
            >
              <option value="all">All statuses</option>
              <option value="REPORTED">{workflowLabel("REPORTED")}</option>
              <option value="FOR_INSPECTION">{workflowLabel("FOR_INSPECTION")}</option>
              <option value="INSPECTION_SCHEDULED">{workflowLabel("INSPECTION_SCHEDULED")}</option>
              <option value="NOT_CONFIRMED">{workflowLabel("NOT_CONFIRMED")}</option>
              <option value="FIELD_VALIDATED">{workflowLabel("FIELD_VALIDATED")}</option>
              <option value="UNDER_INTERVENTION">{workflowLabel("UNDER_INTERVENTION")}</option>
              <option value="FOLLOW_UP_DUE">{workflowLabel("FOLLOW_UP_DUE")}</option>
              <option value="REINTERVENTION_REQUIRED">{workflowLabel("REINTERVENTION_REQUIRED")}</option>
              <option value="CLOSED">{workflowLabel("CLOSED")}</option>
            </select>
          </div>
          <div className="gov-field">
            <label htmlFor="report_farmer" className="gov-label">
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
              className="gov-input"
            />
          </div>
          <div className="gov-field">
            <label htmlFor="report_farm" className="gov-label">
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
              className="gov-input"
            />
          </div>
          <div className="gov-field">
            <label htmlFor="report_from" className="gov-label">
              Reported from
            </label>
            <input
              id="report_from"
              type="date"
              value={reportedFrom}
              onChange={(event) => setReportedFrom(event.target.value)}
              className="gov-input"
            />
          </div>
          <div className="gov-field">
            <label htmlFor="report_to" className="gov-label">
              Reported to
            </label>
            <input
              id="report_to"
              type="date"
              value={reportedTo}
              onChange={(event) => setReportedTo(event.target.value)}
              className="gov-input"
            />
          </div>
          <div className="gov-form-actions">
            <button
              type="submit"
              disabled={loading}
              className="gov-button gov-button-primary"
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
              className="gov-button gov-button-secondary gov-button-compact"
            >
              Clear filters
            </button>
          </div>
        </form>
        {filterError && (
          <p role="alert" className="gov-alert gov-alert-error gov-feedback">
            {filterError}
          </p>
        )}

        {loading ? (
          <p role="status" className="gov-empty-state">
            Loading operational report...
          </p>
        ) : listError ? (
          <p role="alert" className="gov-alert gov-alert-error gov-feedback">
            {listError}
          </p>
        ) : report ? (
          <div>
            <section aria-label="Report summary" className="gov-card gov-record-section">
              <h2 className="gov-record-title">Summary</h2>
              <div className="gov-summary-grid gov-report-summary">
                <div className="gov-stat">
                  <p className="gov-stat-label">Total cases</p>
                  <p className="gov-stat-value">
                    {report.summary.total_cases}
                  </p>
                </div>
                <div className="gov-stat">
                  <p className="gov-stat-label">Open cases</p>
                  <p className="gov-stat-value">
                    {report.summary.open_cases}
                  </p>
                </div>
                <div className="gov-stat">
                  <p className="gov-stat-label">Closed cases</p>
                  <p className="gov-stat-value">
                    {report.summary.closed_cases}
                  </p>
                </div>
                <div className="gov-stat">
                  <p className="gov-stat-label">Follow-ups due</p>
                  <p className="gov-stat-value">
                    {report.summary.follow_ups_due}
                  </p>
                </div>
              </div>
            </section>

            <section aria-label="Cases by status" className="gov-card gov-record-section">
              <h2 className="gov-record-title">Cases by status</h2>
              <dl className="gov-report-list">
                {(
                  Object.entries(report.by_status) as [string, number][]
                ).map(([status, count]) => (
                  <div key={status} className="gov-report-row">
                    <dt><span className={`gov-status-badge gov-status-${status.toLowerCase().replaceAll("_", "-")}`}>{workflowLabel(status)}</span></dt>
                    <dd className="gov-report-count">{count}</dd>
                  </div>
                ))}
              </dl>
            </section>

            <section aria-label="Follow-up summary" className="gov-card gov-record-section">
              <h2 className="gov-record-title">Follow-up summary</h2>
              <dl className="gov-report-list">
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Pending follow-up</dt>
                  <dd className="gov-report-count">{report.follow_up_summary.pending}</dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Overdue</dt>
                  <dd className="gov-report-count">{report.follow_up_summary.overdue}</dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Completed reassessments</dt>
                  <dd className="gov-report-count">{report.follow_up_summary.completed}</dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Resolved follow-up</dt>
                  <dd className="gov-report-count">{report.follow_up_summary.resolved}</dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Further intervention required</dt>
                  <dd className="gov-report-count">
                    {report.follow_up_summary.reintervention_required}
                  </dd>
                </div>
              </dl>
            </section>

            <section aria-label="Intervention summary" className="gov-card gov-record-section">
              <h2 className="gov-record-title">Intervention summary</h2>
              <dl className="gov-report-list">
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Completed interventions</dt>
                  <dd className="gov-report-count">{report.intervention_summary.completed}</dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Pending interventions</dt>
                  <dd className="gov-report-count">{report.intervention_summary.pending}</dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Cases with repeat intervention</dt>
                  <dd className="gov-report-count">
                    {report.intervention_summary.cases_with_repeat_intervention}
                  </dd>
                </div>
                <div className="gov-report-row">
                  <dt className="gov-stat-label">Total records</dt>
                  <dd className="gov-report-count">{report.intervention_summary.total_records}</dd>
                </div>
              </dl>
            </section>

            <section aria-label="Report cases" className="gov-card gov-record-section">
              <h2 className="gov-record-title">Report cases</h2>
              {report.cases.length === 0 ? (
                <p role="status" className="gov-empty-state">
                  No cases match the current filters.
                </p>
              ) : (
                <div className="gov-table-wrap mt-3">
                  <table className="gov-table min-w-[860px]">
                    <thead>
                      <tr>
                        <th scope="col">Case</th>
                        <th scope="col">Farmer / Farm</th>
                        <th scope="col">Status</th>
                        <th scope="col">Cycle / Follow-up</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.cases.map((entry) => (
                        <tr key={entry.case_id}>
                          <td>
                            #{entry.case_id} — {entry.pest_name}
                            <span className="block text-xs text-slate-600">
                              Reported {formatRecordDate(entry.reported_at)} ·{" "}
                              {entry.reported_area_hectares.toFixed(2)} ha
                            </span>
                          </td>
                          <td>
                            {entry.farmer ?? "—"}
                            <span className="block text-xs text-slate-600">
                              {entry.farm ?? "—"} · {entry.barangay ?? "—"}
                            </span>
                          </td>
                          <td><span className={`gov-status-badge gov-status-${entry.current_status.toLowerCase().replaceAll("_", "-")}`}>{workflowLabel(entry.current_status)}</span></td>
                          <td>
                            {entry.latest_intervention_cycle === null
                              ? "—"
                              : `Cycle ${entry.latest_intervention_cycle}`}
                            <span className="block text-xs text-slate-600">
                              {workflowLabel(entry.latest_follow_up_outcome ?? "No recorded follow-up")}
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
    </main>
  );
}
