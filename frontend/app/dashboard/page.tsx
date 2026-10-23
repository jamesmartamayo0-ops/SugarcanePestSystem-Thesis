"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { formatDisplayDate } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import FarmMonitoringMap from "@/components/farm-monitoring-map";
import {
  DashboardRequestError,
  getDashboardSummary,
  type DashboardSummary,
} from "@/lib/dashboard";
import {
  FarmMapRequestError,
  getFarmMap,
  type FarmMapProjection,
} from "@/lib/farm-map";

const WORKFLOW_ITEMS = [
  { status: "REPORTED", label: "Reported", href: "/pest-cases?status=REPORTED" },
  { status: "FOR_INSPECTION", label: "For Inspection", href: "/inspections" },
  { status: "INSPECTION_SCHEDULED", label: "Inspection Scheduled", href: "/inspections" },
  { status: "FIELD_VALIDATED", label: "Field Validated", href: "/interventions" },
  { status: "NOT_CONFIRMED", label: "Not Confirmed", href: "/pest-cases?status=NOT_CONFIRMED" },
  { status: "UNDER_INTERVENTION", label: "Under Intervention", href: "/interventions" },
  { status: "FOLLOW_UP_DUE", label: "Follow-up Due", href: "/follow-ups" },
  { status: "REINTERVENTION_REQUIRED", label: "Reintervention Required", href: "/follow-ups" },
  { status: "CLOSED", label: "Closed", href: "/pest-cases?status=CLOSED" },
] as const;

const ATTENTION_ITEMS = [
  { key: "overdue_follow_ups", label: "Overdue follow-ups", description: "Due before today (Asia/Manila) and still awaiting follow-up.", accent: "danger" },
  { key: "reintervention_required", label: "Requiring reintervention", accent: "warning" },
  { key: "awaiting_inspection_scheduling", label: "Waiting for inspection scheduling", accent: "warning" },
  { key: "validated_awaiting_intervention", label: "Validated awaiting intervention", accent: "warning" },
] as const;

export default function DashboardPage() {
  const router = useRouter();
  const auth = useAuth();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [farmMap, setFarmMap] = useState<FarmMapProjection | null>(null);
  const [loadingFarmMap, setLoadingFarmMap] = useState(true);
  const [farmMapError, setFarmMapError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  async function loadFarmMap() {
    setLoadingFarmMap(true);
    setFarmMapError(null);
    try {
      setFarmMap(await getFarmMap());
    } catch (failure: unknown) {
      if (
        failure instanceof FarmMapRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setFarmMapError(
        failure instanceof FarmMapRequestError
          ? failure.message
          : "Farm monitoring map could not be read.",
      );
    } finally {
      setLoadingFarmMap(false);
    }
  }

  useEffect(() => {
    if (auth.status !== "authenticated") {
      return;
    }
    let active = true;
    (async () => {
      setLoadingFarmMap(true);
      try {
        const loaded = await getFarmMap();
        if (!active) {
          return;
        }
        setFarmMap(loaded);
        setFarmMapError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          failure instanceof FarmMapRequestError &&
          failure.kind === "unauthenticated"
        ) {
          router.replace("/login");
          return;
        }
        setFarmMapError(
          failure instanceof FarmMapRequestError
            ? failure.message
            : "Farm monitoring map could not be read.",
        );
      } finally {
        if (active) {
          setLoadingFarmMap(false);
        }
      }
    })();
    return () => {
      active = false;
    };
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
    <main className="gov-page">
      <header className="gov-page-header">
        <h1 className="gov-page-title">Dashboard</h1>
        <p className="gov-page-description">
          Operational overview of sugarcane pest cases and field activities.
        </p>
      </header>
      <section aria-label="Operational summary">
        {loadingSummary ? (
          <p role="status" className="gov-page-description">Loading operational summary...</p>
        ) : summaryError ? (
          <p role="alert" className="gov-alert gov-alert-error">{summaryError}</p>
        ) : summary ? (
          <>
            <dl className="gov-summary-grid">
              {[
                { label: "Farmers", value: summary.totals.farmers, description: "Registered" },
                { label: "Farms", value: summary.totals.farms, description: "Registered" },
                { label: "Pest Cases", value: summary.totals.pest_cases, description: "Total recorded" },
                { label: "Closed Cases", value: summary.by_status.CLOSED, description: "Completed" },
              ].map((item) => (
                <div key={item.label} className="gov-stat">
                  <dt className="gov-stat-label">{item.label}</dt>
                  <dd className="gov-stat-value">{item.value}</dd>
                  <dd className="gov-page-description">{item.description}</dd>
                </div>
              ))}
            </dl>
            <div className="gov-dashboard-grid">
              <section className="gov-card gov-section" aria-labelledby="workflow-heading">
                <h2 id="workflow-heading" className="gov-card-header">Workflow Status</h2>
                <ul className="gov-status-grid">
                  {WORKFLOW_ITEMS.map((item) => (
                    <li key={item.status}>
                      <Link href={item.href} className="gov-status-row">
                        <span>{item.label}</span>
                        <strong>{summary.by_status[item.status]}</strong>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
              <section className="gov-card gov-section" aria-labelledby="attention-heading">
                <h2 id="attention-heading" className="gov-card-header">Requires Attention</h2>
                <dl className="gov-attention-list">
                  {ATTENTION_ITEMS.map((item) => (
                    <div
                      key={item.key}
                      className={`gov-attention-row${summary.action_needed[item.key] > 0 ? ` gov-attention-${item.accent}` : ""}`}
                    >
                      <dt>
                        {item.label}
                        {"description" in item && (
                          <span className="gov-attention-description">{item.description}</span>
                        )}
                      </dt>
                      <dd>{summary.action_needed[item.key]}</dd>
                    </div>
                  ))}
                </dl>
              </section>
            </div>
            <section className="gov-card gov-section" aria-labelledby="activity-heading">
              <h2 id="activity-heading" className="gov-card-header">Recent Activity</h2>
              {summary.recent_cases.length === 0 ? (
                <p role="status" className="gov-card-body gov-page-description">No pest cases yet.</p>
              ) : (
                <ul className="gov-activity-list">
                  {summary.recent_cases.map((entry) => (
                    <li key={entry.id} className="gov-activity-item">
                      <div>
                        <p className="gov-activity-reference">#{entry.id} — {entry.pest_name}</p>
                        <p className="gov-page-description">Updated {formatDisplayDate(entry.updated_at ?? null)}</p>
                      </div>
                      <div className="gov-activity-actions">
                        <span className="status-badge">
                          {WORKFLOW_ITEMS.find((item) => item.status === entry.status)?.label ?? entry.status}
                        </span>
                        <Link href={`/pest-cases/${entry.id}`} className="gov-activity-link">
                          Timeline<span className="sr-only"> for case #{entry.id}</span>
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {action && (
                <p className="gov-dashboard-note">
                  Follow-ups due: {action.follow_ups_due} · In progress:{" "}
                  {action.interventions_in_progress} · Scheduled inspections:{" "}
                  {action.inspections_scheduled_awaiting_validation}
                </p>
              )}
            </section>
          </>
        ) : null}
      </section>
      <section className="gov-card gov-section gov-map-section" aria-labelledby="farm-map-heading">
        <div className="gov-record-toolbar gov-map-heading-row">
          <div>
            <h2 id="farm-map-heading" className="gov-card-header">Farm Monitoring Map</h2>
            <p className="gov-map-intro">
              Approximate registered farm locations and their current workflow state.
            </p>
          </div>
          <button
            type="button"
            className="gov-button gov-button-secondary gov-button-compact"
            onClick={() => void loadFarmMap()}
            disabled={loadingFarmMap}
          >
            {loadingFarmMap ? "Loading..." : "Refresh map"}
          </button>
        </div>
        {loadingFarmMap && farmMap === null ? (
          <div className="gov-monitoring-map-message" role="status">
            Loading farm monitoring data...
          </div>
        ) : farmMapError ? (
          <div className="gov-map-error">
            <p className="gov-alert gov-alert-error" role="alert">{farmMapError}</p>
            <button
              type="button"
              className="gov-button gov-button-secondary gov-button-compact"
              onClick={() => void loadFarmMap()}
            >
              Try again
            </button>
          </div>
        ) : farmMap ? (
          <>
            <dl className="gov-summary-grid gov-map-summary-grid">
              {[
                { label: "Mapped Farms", value: farmMap.summary.mapped_farms, description: "Farm count" },
                { label: "Unmapped Farms", value: farmMap.summary.unmapped_farms, description: "Farm count" },
                { label: "Active Cases", value: farmMap.summary.active_cases, description: "Case count" },
                { label: "Needs Attention", value: farmMap.summary.needs_attention_cases, description: "Case count" },
              ].map((item) => (
                <div key={item.label} className="gov-stat">
                  <dt className="gov-stat-label">{item.label}</dt>
                  <dd className="gov-stat-value">{item.value}</dd>
                  <dd className="gov-page-description">{item.description}</dd>
                </div>
              ))}
            </dl>
            <FarmMonitoringMap farms={farmMap.farms} />
          </>
        ) : null}
      </section>
    </main>
  );
}
