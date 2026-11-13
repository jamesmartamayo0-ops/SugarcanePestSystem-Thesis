"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { formatDisplayDate, pestLabel, workflowBadgeClass, workflowLabel } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import FarmMonitoringMap from "@/components/farm-monitoring-map";
import { Icon, type IconName } from "@/components/icons";
import { DashboardSummarySkeleton, MonitoringMapSkeleton } from "@/components/skeleton";
import { PageHeader, SessionNotice } from "@/components/ui";
import { canAccessPath } from "@/lib/access-control";
import {
  DashboardRequestError,
  getDashboardSummary,
  type DashboardActionNeeded,
  type DashboardSummary,
} from "@/lib/dashboard";
import {
  FarmMapRequestError,
  getFarmMap,
  type FarmMapProjection,
} from "@/lib/farm-map";
import type { PestCaseStatus } from "@/lib/pest-cases";

// Case lifecycle grouped by stage. Counts come straight from the summary API.
const PIPELINE: { title: string; items: { status: PestCaseStatus; href: string }[] }[] = [
  {
    title: "Intake",
    items: [
      { status: "REPORTED", href: "/pest-cases?status=REPORTED" },
      { status: "FOR_INSPECTION", href: "/inspections" },
      { status: "INSPECTION_SCHEDULED", href: "/inspections" },
    ],
  },
  {
    title: "Field validation",
    items: [
      { status: "FIELD_VALIDATED", href: "/interventions" },
      { status: "NOT_CONFIRMED", href: "/pest-cases?status=NOT_CONFIRMED" },
    ],
  },
  {
    title: "Intervention & follow-up",
    items: [
      { status: "UNDER_INTERVENTION", href: "/interventions" },
      { status: "FOLLOW_UP_DUE", href: "/follow-ups" },
      { status: "REINTERVENTION_REQUIRED", href: "/interventions" },
    ],
  },
  {
    title: "Outcome",
    items: [{ status: "CLOSED", href: "/pest-cases?status=CLOSED" }],
  },
];

type AttentionItem = {
  key: keyof DashboardActionNeeded;
  label: string;
  description: string;
  href: string;
  action: string;
  tone: "danger" | "warning";
};

const ATTENTION_ITEMS: AttentionItem[] = [
  {
    key: "overdue_follow_ups",
    label: "Overdue follow-ups",
    description: "Due before today (Asia/Manila) and still awaiting follow-up.",
    href: "/follow-ups",
    action: "Open follow-ups",
    tone: "danger",
  },
  {
    key: "reintervention_required",
    label: "Requiring reintervention",
    description: "Reassessment found that further intervention is required.",
    href: "/interventions",
    action: "Open interventions",
    tone: "warning",
  },
  {
    key: "awaiting_inspection_scheduling",
    label: "Waiting for inspection scheduling",
    description: "Submitted for inspection; no inspection scheduled yet.",
    href: "/inspections",
    action: "Open inspections",
    tone: "warning",
  },
  {
    key: "validated_awaiting_intervention",
    label: "Validated awaiting intervention",
    description: "Pest damage confirmed in the field; no intervention started yet.",
    href: "/interventions",
    action: "Open interventions",
    tone: "warning",
  },
];

const IN_PROGRESS_ITEMS: {
  key: keyof DashboardActionNeeded;
  label: string;
  hint: string;
  href: string;
  icon: IconName;
}[] = [
  {
    key: "inspections_scheduled_awaiting_validation",
    label: "Scheduled inspections",
    hint: "Field findings not yet recorded",
    href: "/inspections",
    icon: "inspection",
  },
  {
    key: "interventions_in_progress",
    label: "Interventions in progress",
    hint: "Completion not yet recorded",
    href: "/interventions",
    icon: "intervention",
  },
  {
    key: "follow_ups_due",
    label: "Follow-ups due",
    hint: "Completed interventions awaiting reassessment",
    href: "/follow-ups",
    icon: "follow-up",
  },
];

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

  // The sidebar links to the map section; land on it once content above has loaded.
  useEffect(() => {
    if (loadingSummary || loadingFarmMap || window.location.hash !== "#farm-map") {
      return;
    }
    document.getElementById("farm-map")?.scrollIntoView({ block: "start" });
  }, [loadingSummary, loadingFarmMap]);

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
  }

  const isAdmin = auth.user.role === "ADMIN";
  const role = auth.user.role;

  return (
    <main className="gov-page">
      <PageHeader
        title="Dashboard"
        description={
          isAdmin
            ? "Office-wide overview of sugarcane pest cases and field operations."
            : "Overview of the pest cases and field work within your assignments."
        }
        actions={
          isAdmin ? (
            <Link href="/pest-cases#report-case" className="gov-button gov-button-primary">
              <Icon name="plus" size={16} />
              Report pest case
            </Link>
          ) : undefined
        }
      />

      <section aria-labelledby="operational-summary-heading">
        <h2 id="operational-summary-heading" className="sr-only">
          Operational summary
        </h2>
        {loadingSummary ? (
          <DashboardSummarySkeleton
            attentionCards={ATTENTION_ITEMS.length}
            pipelineGroups={PIPELINE.map((group) => group.items.length)}
            progressRows={IN_PROGRESS_ITEMS.length}
          />
        ) : summaryError ? (
          <p role="alert" className="gov-alert gov-alert-error">{summaryError}</p>
        ) : summary ? (
          <>
            <dl className="gov-summary-grid">
              {[
                { label: "Farmers", value: summary.totals.farmers, description: "Registered", icon: "farmers" as const },
                { label: "Farms", value: summary.totals.farms, description: "Registered", icon: "farm" as const },
                { label: "Pest cases", value: summary.totals.pest_cases, description: "Total recorded", icon: "pest" as const },
                { label: "Closed cases", value: summary.by_status.CLOSED, description: "Completed", icon: "check-circle" as const },
              ].map((item) => (
                <div key={item.label} className="gov-stat">
                  <div className="gov-stat-head">
                    <dt className="gov-stat-label">{item.label}</dt>
                    <span className="gov-stat-icon" aria-hidden="true">
                      <Icon name={item.icon} size={18} />
                    </span>
                  </div>
                  <dd className="gov-stat-value">{item.value}</dd>
                  <dd className="gov-stat-note">{item.description}</dd>
                </div>
              ))}
            </dl>

            <section className="gov-dashboard-section" aria-labelledby="attention-heading">
              <div className="gov-section-bar">
                <div>
                  <h2 id="attention-heading" className="gov-section-title">
                    Requires attention
                  </h2>
                  <p className="gov-section-description">
                    Work waiting on the next workflow step.
                  </p>
                </div>
              </div>
              <ul className="gov-attention-grid">
                {ATTENTION_ITEMS.map((item) => {
                  const count = summary.action_needed[item.key];
                  const tone = count > 0 ? item.tone : "clear";
                  return (
                    <li key={item.key}>
                      <Link href={item.href} className={`gov-attention-card gov-attention-card--${tone}`}>
                        <span className="gov-attention-status">
                          <Icon
                            name={tone === "clear" ? "check-circle" : tone === "danger" ? "alert-triangle" : "clock"}
                            size={14}
                          />
                          {tone === "clear" ? "None pending" : tone === "danger" ? "Overdue" : "Pending"}
                        </span>
                        <span className="gov-attention-title">{item.label}</span>
                        <span className="gov-attention-count">{count}</span>
                        <span className="gov-attention-text">{item.description}</span>
                        <span className="gov-attention-link">
                          {item.action}
                          <Icon name="arrow-right" size={14} />
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </section>

            <section className="gov-card gov-dashboard-section" aria-labelledby="workflow-heading">
              <div className="gov-card-header">
                <div>
                  <h2 id="workflow-heading" className="gov-card-header-title">
                    Cases by workflow stage
                  </h2>
                  <p className="gov-card-header-meta">
                    {summary.totals.pest_cases} {summary.totals.pest_cases === 1 ? "case" : "cases"} recorded.
                    Select a status to open the related records.
                  </p>
                </div>
              </div>
              <div className="gov-pipeline">
                {PIPELINE.map((group, index) => (
                  <div key={group.title} className="gov-pipeline-group">
                    <h3 className="gov-pipeline-title">
                      <span className="gov-pipeline-step" aria-hidden="true">{index + 1}</span>
                      {group.title}
                    </h3>
                    <ul className="gov-pipeline-list">
                      {group.items.map((item) => {
                        const count = summary.by_status[item.status];
                        const content = (
                          <>
                            <span className={workflowBadgeClass(item.status)}>
                              {workflowLabel(item.status)}
                            </span>
                            <span
                              className={`gov-pipeline-count${count === 0 ? " gov-pipeline-count--zero" : ""}`}
                            >
                              {count}
                            </span>
                          </>
                        );
                        return (
                          <li key={item.status}>
                            {canAccessPath(role, item.href) ? (
                              <Link href={item.href} className="gov-pipeline-row">
                                {content}
                              </Link>
                            ) : (
                              <div className="gov-pipeline-row">{content}</div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </section>

            <div className="gov-dashboard-grid">
              <section className="gov-card gov-section" aria-labelledby="activity-heading">
                <div className="gov-card-header">
                  <div>
                    <h2 id="activity-heading" className="gov-card-header-title">
                      Recent case activity
                    </h2>
                    <p className="gov-card-header-meta">Most recently updated pest cases.</p>
                  </div>
                  {isAdmin && (
                    <Link href="/pest-cases" className="gov-activity-link">
                      All pest cases
                    </Link>
                  )}
                </div>
                {summary.recent_cases.length === 0 ? (
                  <div className="gov-card-body">
                    <p role="status" className="gov-empty-state">
                      No pest case activity to show yet.
                    </p>
                  </div>
                ) : (
                  <ul className="gov-activity-list">
                    {summary.recent_cases.map((entry) => (
                      <li key={entry.id} className="gov-activity-item">
                        <div>
                          <p className="gov-activity-reference">{pestLabel(entry.pest_name)}</p>
                          <p className="gov-activity-meta">
                            Case #{entry.id} · Updated {formatDisplayDate(entry.updated_at ?? null)}
                          </p>
                        </div>
                        <div className="gov-activity-actions">
                          <span className={workflowBadgeClass(entry.status)}>
                            {workflowLabel(entry.status)}
                          </span>
                          {isAdmin && (
                            <Link
                              href={`/pest-cases/${entry.id}`}
                              className="gov-button gov-button-secondary gov-button-compact"
                            >
                              <Icon name="history" size={15} />
                              Case record<span className="sr-only"> for case #{entry.id}</span>
                            </Link>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="gov-card gov-section" aria-labelledby="in-progress-heading">
                <div className="gov-card-header">
                  <div>
                    <h2 id="in-progress-heading" className="gov-card-header-title">
                      Field work in progress
                    </h2>
                    <p className="gov-card-header-meta">Scheduled and ongoing field activities.</p>
                  </div>
                </div>
                <ul className="gov-progress-list">
                  {IN_PROGRESS_ITEMS.map((item) => (
                    <li key={item.key}>
                      <Link href={item.href} className="gov-progress-row">
                        <span className="gov-progress-label">
                          <Icon name={item.icon} size={18} />
                          <span>
                            {item.label}
                            <span className="gov-progress-hint">{item.hint}</span>
                          </span>
                        </span>
                        <span className="gov-progress-count">{summary.action_needed[item.key]}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </>
        ) : null}
      </section>

      <section
        id="farm-map"
        className="gov-card gov-section gov-map-section"
        aria-labelledby="farm-map-heading"
      >
        <div className="gov-record-toolbar gov-map-heading-row">
          <div>
            <h2 id="farm-map-heading" className="gov-section-title">Farm Monitoring Map</h2>
            <p className="gov-section-description">
              Approximate registered farm locations and their current workflow state.
            </p>
          </div>
          <button
            type="button"
            className="gov-button gov-button-secondary gov-button-compact"
            onClick={() => void loadFarmMap()}
            disabled={loadingFarmMap}
          >
            <Icon name="refresh" size={15} />
            {loadingFarmMap ? "Loading..." : "Refresh map"}
          </button>
        </div>
        <p className="gov-callout gov-map-disclaimer">
          Farm locations shown on this map are approximate operational reference points
          and do not represent surveyed property boundaries or establish land ownership.
        </p>
        {loadingFarmMap && farmMap === null ? (
          <MonitoringMapSkeleton label="Loading farm monitoring data" />
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
            <dl className="gov-summary-grid gov-summary-grid--compact gov-map-summary-grid">
              {[
                { label: "Mapped farms", value: farmMap.summary.mapped_farms, description: "With an approximate location" },
                { label: "Unmapped farms", value: farmMap.summary.unmapped_farms, description: "No location recorded" },
                { label: "Active cases", value: farmMap.summary.active_cases, description: "Not closed or ruled out" },
                { label: "Needs attention", value: farmMap.summary.needs_attention_cases, description: "Waiting on the next action" },
              ].map((item) => (
                <div key={item.label} className="gov-stat">
                  <dt className="gov-stat-label">{item.label}</dt>
                  <dd className="gov-stat-value">{item.value}</dd>
                  <dd className="gov-stat-note">{item.description}</dd>
                </div>
              ))}
            </dl>
            <FarmMonitoringMap farms={farmMap.farms} showRecordLinks={isAdmin} />
          </>
        ) : null}
      </section>
    </main>
  );
}
