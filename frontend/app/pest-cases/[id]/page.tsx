"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import {
  formatDisplayDate,
  pestLabel,
  workflowBadgeClass,
  workflowLabel,
  workflowMessage,
} from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import { EvidencePhotoGallery } from "@/components/evidence-photos";
import { Icon, type IconName } from "@/components/icons";
import { PageHeader, SessionNotice } from "@/components/ui";
import { CaseProgress } from "@/components/workflow-steps";
import {
  TimelineRequestError,
  getCaseTimeline,
  type CaseTimeline,
  type TimelineEvent,
} from "@/lib/timeline";

const CATEGORY_LABELS: Record<string, string> = {
  CASE: "Case",
  INSPECTION: "Inspection",
  INTERVENTION: "Intervention",
  FOLLOW_UP: "Follow-up",
  CLOSURE: "Closure",
};

const CATEGORY_ICONS: Record<string, IconName> = {
  CASE: "file-text",
  INSPECTION: "inspection",
  INTERVENTION: "intervention",
  FOLLOW_UP: "follow-up",
  CLOSURE: "check",
};

function categoryLabel(category: string): string {
  return Object.hasOwn(CATEGORY_LABELS, category) ? CATEGORY_LABELS[category] : category;
}

function categoryModifier(category: string): string {
  return category.toLowerCase().replaceAll("_", "-");
}

type NextStep = {
  title: string;
  text: string;
  href?: string;
  action?: string;
  tone: "default" | "attention" | "terminal" | "neutral";
};

// Guidance only: links open the page where the permitted action is recorded.
const NEXT_STEPS: Record<string, NextStep> = {
  REPORTED: {
    title: "Submit for inspection",
    text: "Review the initial report on the Pest Cases page, then submit it for inspection.",
    href: "/pest-cases",
    action: "Open Pest Cases",
    tone: "default",
  },
  FOR_INSPECTION: {
    title: "Schedule the field inspection",
    text: "Schedule an inspection date and assign an Agriculture Technician.",
    href: "/inspections",
    action: "Open Inspections",
    tone: "attention",
  },
  INSPECTION_SCHEDULED: {
    title: "Record field validation",
    text: "After the site visit, the assigned Agriculture Technician or an Administrator records the field findings.",
    href: "/inspections",
    action: "Open Inspections",
    tone: "default",
  },
  FIELD_VALIDATED: {
    title: "Plan an intervention",
    text: "Pest damage was confirmed in the field. Authorized personnel decide on and record the intervention.",
    href: "/interventions",
    action: "Open Interventions",
    tone: "attention",
  },
  NOT_CONFIRMED: {
    title: "No intervention required",
    text: "The field inspection did not confirm pest damage. No further workflow action applies to this case.",
    tone: "neutral",
  },
  UNDER_INTERVENTION: {
    title: "Record intervention completion",
    text: "Record the date the work was performed, completion notes, and the follow-up due date.",
    href: "/interventions",
    action: "Open Interventions",
    tone: "default",
  },
  FOLLOW_UP_DUE: {
    title: "Record the follow-up reassessment",
    text: "Reassess the farm and record the outcome: resolved, or further intervention required.",
    href: "/follow-ups",
    action: "Open Follow-ups",
    tone: "attention",
  },
  REINTERVENTION_REQUIRED: {
    title: "Start the next intervention cycle",
    text: "The latest reassessment found that further intervention is required.",
    href: "/interventions",
    action: "Open Interventions",
    tone: "attention",
  },
  CLOSED: {
    title: "Case closed",
    text: "The final reassessment outcome was resolved. The full history remains available in the timeline.",
    tone: "terminal",
  },
};

type PersonRef = { full_name: string; username: string };

function personRef(value: unknown): PersonRef | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const entry = value as Record<string, unknown>;
  return typeof entry.full_name === "string" && typeof entry.username === "string"
    ? { full_name: entry.full_name, username: entry.username }
    : null;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function lastEvent(timeline: TimelineEvent[], eventType: string): TimelineEvent | null {
  for (let index = timeline.length - 1; index >= 0; index -= 1) {
    if (timeline[index].event_type === eventType) {
      return timeline[index];
    }
  }
  return null;
}

function EventOutcome({ event }: { event: TimelineEvent }) {
  if (event.event_type === "inspection_findings_recorded") {
    const confirmed = event.metadata.pest_confirmed === true;
    const area = numberOrNull(event.metadata.validated_area_hectares);
    const confirmedName =
      typeof event.metadata.confirmed_pest_name === "string"
        ? event.metadata.confirmed_pest_name
        : null;
    return (
      <span className={workflowBadgeClass(confirmed ? "FIELD_VALIDATED" : "NOT_CONFIRMED")}>
        {confirmed
          ? `Confirmed${confirmedName !== null ? ` · ${confirmedName}` : ""}${
              area !== null ? ` · ${area.toFixed(2)} ha validated` : ""
            }`
          : "Not confirmed"}
      </span>
    );
  }
  if (event.event_type === "follow_up_recorded") {
    const outcome = event.metadata.outcome;
    if (outcome === "RESOLVED") {
      return <span className={workflowBadgeClass("RESOLVED")}>Resolved</span>;
    }
    if (outcome === "REINTERVENTION_REQUIRED") {
      return (
        <span className={workflowBadgeClass("REINTERVENTION_REQUIRED")}>
          Further intervention required
        </span>
      );
    }
  }
  return null;
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

  // Map popups link to #case-summary and #timeline; honour them once loaded.
  useEffect(() => {
    if (data === null) {
      return;
    }
    const hash = window.location.hash;
    if (hash === "#timeline" || hash === "#case-summary") {
      document.getElementById(hash.slice(1))?.scrollIntoView({ block: "start" });
    }
  }, [data]);

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
  }

  const pestCase = data?.pest_case ?? null;
  const timeline = data?.timeline ?? [];
  const findings = lastEvent(timeline, "inspection_findings_recorded");
  const scheduled = lastEvent(timeline, "inspection_scheduled");
  const latestIntervention = lastEvent(timeline, "intervention_started");
  const interventionCycles = timeline.filter((event) => event.event_type === "intervention_started").length;
  const inspectionAssignee = scheduled ? personRef(scheduled.metadata.assigned_to) : null;
  const interventionAssignee = latestIntervention ? personRef(latestIntervention.metadata.assigned_to) : null;
  const nextStep = pestCase ? NEXT_STEPS[pestCase.status] : undefined;
  const confirmed = findings ? findings.metadata.pest_confirmed === true : null;
  const validatedArea = findings ? numberOrNull(findings.metadata.validated_area_hectares) : null;
  const confirmedPestName =
    findings && typeof findings.metadata.confirmed_pest_name === "string"
      ? findings.metadata.confirmed_pest_name
      : null;
  // A case past the inspection stages with no stored inspection record is not "pending".
  const inspectionNotRecorded =
    findings === null &&
    scheduled === null &&
    pestCase !== null &&
    pestCase.status !== "REPORTED" &&
    pestCase.status !== "FOR_INSPECTION";

  return (
    <main className="gov-page">
      <PageHeader
        backLink={{ href: "/pest-cases", label: "Back to pest cases" }}
        title={
          pestCase ? (
            <span className="gov-page-title-row">
              <span>
                Case #{pestCase.id} · {pestLabel(pestCase.pest_name)}
              </span>
              <span className={`${workflowBadgeClass(pestCase.status)} gov-status-badge--large`}>
                {workflowLabel(pestCase.status)}
              </span>
            </span>
          ) : (
            "Case record"
          )
        }
        description="Chronological record of this pest case, from the initial report through field validation, intervention, and follow-up."
      />

      {validId === null ? (
        <p role="alert" className="gov-alert gov-alert-error">
          Invalid pest case reference.
        </p>
      ) : loading ? (
        <p role="status" className="gov-loading-state gov-loading-state--tall">
          Loading case record...
        </p>
      ) : error ? (
        <p role="alert" className="gov-alert gov-alert-error">
          {error}
        </p>
      ) : data && pestCase ? (
        <>
          <CaseProgress status={pestCase.status} />

          <div className="gov-case-layout">
            <div className="gov-case-main">
              <section
                id="case-summary"
                aria-labelledby="case-summary-heading"
                className="gov-card gov-record-section"
              >
                <h2 id="case-summary-heading" className="gov-record-title">
                  Report and field validation
                </h2>
                <p className="gov-record-intro">
                  The initial report is what was reported before inspection. Field validation
                  is what the inspector verified on site. They are recorded separately.
                </p>
                <div className="gov-compare">
                  <div className="gov-compare-panel gov-compare-panel--reported">
                    <div className="gov-compare-head">
                      <h3 className="gov-compare-title">
                        <Icon name="file-text" size={17} />
                        Initial report
                      </h3>
                      <span className="gov-tag">As reported</span>
                    </div>
                    <dl className="gov-detail-grid">
                      <div>
                        <dt className="gov-detail-label">Suspected Pest</dt>
                        <dd className="gov-detail-value">{pestLabel(pestCase.pest_name)}</dd>
                      </div>
                      <div>
                        <dt className="gov-detail-label">Estimated affected area</dt>
                        <dd className="gov-detail-value">
                          {pestCase.reported_area_hectares.toFixed(2)} ha
                        </dd>
                      </div>
                      <div>
                        <dt className="gov-detail-label">Observed on</dt>
                        <dd className="gov-detail-value">{formatDisplayDate(pestCase.observed_on)}</dd>
                      </div>
                      <div className="gov-detail-wide">
                        <dt className="gov-detail-label">
                          Observed Symptoms / Farmer Description
                        </dt>
                        <dd className="gov-detail-value">{pestCase.symptoms ?? "—"}</dd>
                      </div>
                      <div className="gov-detail-wide">
                        <dt className="gov-detail-label">Pest / Damage Evidence Photos</dt>
                        <dd className="gov-detail-value">
                          <EvidencePhotoGallery
                            caseId={pestCase.id}
                            photos={pestCase.evidence_photos}
                          />
                        </dd>
                      </div>
                    </dl>
                  </div>

                  <div
                    className={`gov-compare-panel ${
                      confirmed === null
                        ? "gov-compare-panel--pending"
                        : confirmed
                          ? "gov-compare-panel--confirmed"
                          : "gov-compare-panel--not-confirmed"
                    }`}
                  >
                    <div className="gov-compare-head">
                      <h3 className="gov-compare-title">
                        <Icon name="inspection" size={17} />
                        Field validation
                      </h3>
                      {confirmed === null ? (
                        <span className="gov-status-badge">
                          {inspectionNotRecorded ? "No record" : "Pending"}
                        </span>
                      ) : (
                        <span className={workflowBadgeClass(confirmed ? "FIELD_VALIDATED" : "NOT_CONFIRMED")}>
                          {confirmed ? "Pest damage confirmed" : "Not confirmed"}
                        </span>
                      )}
                    </div>
                    {findings ? (
                      <dl className="gov-detail-grid">
                        <div>
                          <dt className="gov-detail-label">Confirmed Pest</dt>
                          <dd className="gov-detail-value">
                            {confirmed
                              ? confirmedPestName ?? "Confirmed (pest name not recorded)"
                              : "Not applicable — infestation not confirmed"}
                          </dd>
                        </div>
                        <div>
                          <dt className="gov-detail-label">Validated affected area</dt>
                          <dd className="gov-detail-value">
                            {validatedArea !== null ? `${validatedArea.toFixed(2)} ha` : "—"}
                          </dd>
                        </div>
                        <div>
                          <dt className="gov-detail-label">Inspected on</dt>
                          <dd className="gov-detail-value">{formatDisplayDate(findings.event_date)}</dd>
                        </div>
                        <div>
                          <dt className="gov-detail-label">Recorded by</dt>
                          <dd className="gov-detail-value">
                            {findings.actor ? `${findings.actor.full_name} (${findings.actor.username})` : "—"}
                          </dd>
                        </div>
                        {findings.description !== "" && (
                          <div>
                            <dt className="gov-detail-label">Findings</dt>
                            <dd className="gov-detail-value">{findings.description}</dd>
                          </div>
                        )}
                      </dl>
                    ) : (
                      <p className="gov-compare-caption">
                        <strong>Confirmed Pest: Pending Field Validation. </strong>
                        {scheduled
                          ? `Inspection scheduled for ${formatDisplayDate(
                              typeof scheduled.metadata.scheduled_for === "string"
                                ? scheduled.metadata.scheduled_for
                                : scheduled.event_date,
                            )}${inspectionAssignee ? `, assigned to ${inspectionAssignee.full_name}` : ""}. Findings have not been recorded yet.`
                          : inspectionNotRecorded
                            ? "No field inspection record is stored for this case."
                            : "No field inspection has been scheduled yet. Reported information is unverified until field validation is recorded."}
                      </p>
                    )}
                  </div>
                </div>
              </section>

              <section
                id="timeline"
                aria-labelledby="timeline-heading"
                className="gov-card gov-record-section"
              >
                <div className="gov-record-toolbar">
                  <div>
                    <h2 id="timeline-heading" className="gov-record-title">
                      Chronological timeline
                    </h2>
                    <p className="gov-record-meta">
                      {timeline.length} {timeline.length === 1 ? "event" : "events"} recorded
                    </p>
                  </div>
                </div>
                <p className="gov-timeline-note">
                  Assembled from stored case, inspection, intervention, and follow-up
                  records. Reschedule history is not stored, so only the current
                  inspection schedule is shown.
                </p>
                {timeline.length === 0 ? (
                  <p role="status" className="gov-empty-state">
                    No timeline events found.
                  </p>
                ) : (
                  <ol className="gov-timeline">
                    {timeline.map((event, index) => (
                      <li
                        key={`${event.event_type}-${index}`}
                        className={`gov-timeline-item gov-timeline-item--${categoryModifier(event.category)}`}
                      >
                        <span className="gov-timeline-node" aria-hidden="true">
                          <Icon name={CATEGORY_ICONS[event.category] ?? "file-text"} size={14} />
                        </span>
                        <article className="gov-timeline-card">
                          <div className="gov-timeline-meta">
                            <span className="gov-timeline-tags">
                              <span
                                className={`gov-event-label gov-event-${categoryModifier(event.category)}`}
                              >
                                {categoryLabel(event.category)}
                              </span>
                              {event.cycle !== null && (
                                <span className="gov-tag">Cycle {event.cycle}</span>
                              )}
                              {event.metadata.inferred_timestamp === true && (
                                <span
                                  className="gov-tag"
                                  title="The exact time of this step is not stored; the earliest related record is shown."
                                >
                                  Approximate time
                                </span>
                              )}
                            </span>
                            <time className="gov-timeline-date">
                              {formatDisplayDate(event.occurred_at ?? event.event_date)}
                            </time>
                          </div>
                          <h3 className="gov-timeline-title">{event.title}</h3>
                          {event.description !== "" && (
                            <p className="gov-timeline-description">
                              {event.event_type === "submitted_for_inspection"
                                ? workflowMessage(event.description)
                                : event.description}
                            </p>
                          )}
                          {(event.actor || event.event_type === "inspection_findings_recorded" || event.event_type === "follow_up_recorded") && (
                            <div className="gov-timeline-footer">
                              <EventOutcome event={event} />
                              {event.actor && (
                                <p className="gov-timeline-actor">
                                  <Icon name="user" size={14} />
                                  {event.actor.full_name} ({event.actor.username})
                                </p>
                              )}
                            </div>
                          )}
                        </article>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </div>

            <aside className="gov-case-aside" aria-label="Case overview">
              {nextStep && (
                <section
                  aria-labelledby="next-step-heading"
                  className={`gov-card gov-next-step gov-next-step--${nextStep.tone}`}
                >
                  <p className="gov-next-step-label">Next step</p>
                  <h2 id="next-step-heading" className="gov-next-step-title">
                    {nextStep.title}
                  </h2>
                  <p className="gov-next-step-text">{nextStep.text}</p>
                  {nextStep.href && nextStep.action && (
                    <Link href={nextStep.href} className="gov-button gov-button-secondary gov-button-compact">
                      {nextStep.action}
                      <Icon name="arrow-right" size={14} />
                    </Link>
                  )}
                </section>
              )}

              <section aria-labelledby="case-facts-heading" className="gov-card">
                <h2 id="case-facts-heading" className="gov-card-header">
                  Case details
                </h2>
                <dl className="gov-fact-list">
                  <div>
                    <dt>Farmer</dt>
                    <dd>
                      {pestCase.farm.farmer.full_name}
                      <span className="gov-cell-meta">{pestCase.farm.farmer.barangay}</span>
                    </dd>
                  </div>
                  <div>
                    <dt>Farm</dt>
                    <dd>
                      {pestCase.farm.plot_identifier}
                      <span className="gov-cell-meta">
                        {pestCase.farm.barangay} · {pestCase.farm.area_hectares.toFixed(2)} ha sugarcane area
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Reported by</dt>
                    <dd>
                      {pestCase.reporter.full_name} ({pestCase.reporter.username})
                      <span className="gov-cell-meta">{formatDisplayDate(pestCase.reported_at)}</span>
                    </dd>
                  </div>
                  {inspectionAssignee && (
                    <div>
                      <dt>Inspection assigned to</dt>
                      <dd>{inspectionAssignee.full_name}</dd>
                    </div>
                  )}
                  {interventionCycles > 0 && (
                    <div>
                      <dt>Intervention cycles</dt>
                      <dd>
                        {interventionCycles}
                        {interventionAssignee && (
                          <span className="gov-cell-meta">
                            Latest assigned to {interventionAssignee.full_name}
                          </span>
                        )}
                      </dd>
                    </div>
                  )}
                  <div>
                    <dt>Last updated</dt>
                    <dd>{formatDisplayDate(pestCase.updated_at)}</dd>
                  </div>
                </dl>
              </section>
            </aside>
          </div>
        </>
      ) : null}
    </main>
  );
}
