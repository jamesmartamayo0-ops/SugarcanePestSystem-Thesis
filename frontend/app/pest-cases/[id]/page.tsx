"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { workflowLabel } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import {
  TimelineRequestError,
  getCaseTimeline,
  type CaseTimeline,
} from "@/lib/timeline";

function categoryBadge(category: string): string {
  return `gov-event-label gov-event-${category.toLowerCase().replaceAll("_", "-")}`;
}

// Rendering only: date-only values retain their calendar day; timestamps use Manila time.
function formatTimelineDate(value: string | null): string {
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

export default function PestCaseTimelinePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const auth = useAuth();
  const [data, setData] = useState<CaseTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const rawId = params.id;
  const caseId = typeof rawId === "string" ? Number(rawId) : NaN;
  const validId = Number.isSafeInteger(caseId) && caseId > 0 ? caseId : null;

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  useEffect(() => {
    if (auth.status !== "authenticated" || validId === null) {
      return;
    }
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const loaded = await getCaseTimeline(validId);
        if (!active) {
          return;
        }
        setData(loaded);
        setError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          failure instanceof TimelineRequestError &&
          failure.kind === "unauthenticated"
        ) {
          router.replace("/login");
          return;
        }
        setError(
          failure instanceof TimelineRequestError
            ? failure.message
            : "Case timeline could not be read.",
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
  }, [auth.status, router, validId]);

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
        <Link href="/pest-cases" className="gov-activity-link">
          Back to pest cases
        </Link>
        <h1 className="gov-page-title mt-3">Case Timeline</h1>
      </header>

        {validId === null ? (
          <p role="alert" className="gov-alert gov-alert-error">
            Invalid pest case reference.
          </p>
        ) : loading ? (
          <p role="status" className="gov-empty-state">
            Loading case timeline...
          </p>
        ) : error ? (
          <p role="alert" className="gov-alert gov-alert-error">
            {error}
          </p>
        ) : data ? (
          <div>
            <section aria-label="Case summary" className="gov-card gov-record-section">
              <div className="gov-record-toolbar">
                <h2 className="gov-record-title">
                  Case #{data.pest_case.id} — {data.pest_case.pest_name}
                </h2>
                <span className={`gov-status-badge gov-status-${data.pest_case.status.toLowerCase().replaceAll("_", "-")}`}>
                  {workflowLabel(data.pest_case.status)}
                </span>
              </div>
              <dl className="gov-detail-grid">
                <div>
                  <dt className="gov-detail-label">Farmer</dt>
                  <dd className="gov-detail-value">
                    {data.pest_case.farm.farmer.full_name} —{" "}
                    {data.pest_case.farm.farmer.barangay}
                  </dd>
                </div>
                <div>
                  <dt className="gov-detail-label">Farm</dt>
                  <dd className="gov-detail-value">
                    {data.pest_case.farm.plot_identifier} — {data.pest_case.farm.barangay} (
                    {data.pest_case.farm.area_hectares.toFixed(2)} ha)
                  </dd>
                </div>
                <div>
                  <dt className="gov-detail-label">Reported</dt>
                  <dd className="gov-detail-value">{formatTimelineDate(data.pest_case.reported_at)}</dd>
                </div>
                <div>
                  <dt className="gov-detail-label">Reported affected area</dt>
                  <dd className="gov-detail-value">{data.pest_case.reported_area_hectares.toFixed(2)} ha</dd>
                </div>
                <div>
                  <dt className="gov-detail-label">Symptoms</dt>
                  <dd className="gov-detail-value">{data.pest_case.symptoms ?? "—"}</dd>
                </div>
              </dl>
            </section>

            <section aria-label="Chronological timeline" className="gov-card gov-record-section">
              <h2 className="gov-record-title">
                Chronological timeline
              </h2>
              <p className="gov-timeline-note">
                Assembled from stored case, inspection, intervention, and follow-up
                records. Reschedule history is not stored, so only the current
                inspection schedule is shown.
              </p>
              {data.timeline.length === 0 ? (
                <p role="status" className="gov-empty-state">
                  No timeline events found.
                </p>
              ) : (
                <ol className="gov-timeline">
                  {data.timeline.map((event, index) => (
                    <li
                      key={`${event.event_type}-${index}`}
                      className="gov-timeline-item"
                    >
                      <div className="gov-timeline-meta">
                        <span
                          className={categoryBadge(event.category)}
                        >
                          {event.category}
                          {event.cycle !== null ? ` · Cycle ${event.cycle}` : ""}
                        </span>
                        <span className="gov-timeline-date">
                          {formatTimelineDate(event.occurred_at ?? event.event_date)}
                        </span>
                      </div>
                      <h3 className="gov-timeline-title">
                        {event.title}
                      </h3>
                      <p className="gov-timeline-description">{event.description}</p>
                      {event.actor && (
                        <p className="gov-timeline-actor">
                          By {event.actor.full_name} ({event.actor.username})
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        ) : null}
    </main>
  );
}
