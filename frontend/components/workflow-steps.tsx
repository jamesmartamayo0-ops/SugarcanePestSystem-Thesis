import Link from "next/link";
import type { CSSProperties } from "react";

import { Icon } from "@/components/icons";

/*
 * Presentation of the existing case lifecycle. Stages mirror the workflow
 * enforced by the backend; nothing here changes or infers a status.
 */

export type WorkflowArea = "report" | "inspection" | "intervention" | "follow-up";

type Stage = {
  key: string;
  label: string;
  detail: string;
  href: string | null;
  area: WorkflowArea | null;
};

const STAGES: Stage[] = [
  { key: "report", label: "Report", detail: "Pest case recorded", href: "/pest-cases", area: "report" },
  { key: "assign", label: "Inspection", detail: "Scheduled and assigned", href: "/inspections", area: "inspection" },
  { key: "validate", label: "Field validation", detail: "Findings verified on site", href: "/inspections", area: "inspection" },
  { key: "intervene", label: "Intervention", detail: "Field action recorded", href: "/interventions", area: "intervention" },
  { key: "follow-up", label: "Follow-up", detail: "Reassessment outcome", href: "/follow-ups", area: "follow-up" },
  { key: "closed", label: "Resolved / Closed", detail: "Case completed", href: null, area: null },
];

const STEP_COUNT_STYLE = { "--step-count": STAGES.length } as CSSProperties;

/** Page-level guide: shows where the current page sits in the lifecycle. */
export function WorkflowSteps({ current }: { current: WorkflowArea }) {
  return (
    <nav aria-label="Case workflow" className="gov-steps">
      <div className="gov-steps-head">
        <p className="gov-steps-title">Case workflow</p>
        <p className="gov-steps-note">
          A follow-up that requires further intervention returns the case to Intervention.
        </p>
      </div>
      <ol className="gov-steps-list" style={STEP_COUNT_STYLE}>
        {STAGES.map((stage, index) => {
          const isCurrent = stage.area === current;
          const content = (
            <>
              <span className="gov-step-marker" aria-hidden="true">
                {index + 1}
              </span>
              <span className="gov-step-text">
                <span className="gov-step-label">{stage.label}</span>
                <span className="gov-step-detail">{stage.detail}</span>
              </span>
            </>
          );
          return (
            <li key={stage.key} className={`gov-step${isCurrent ? " gov-step--current" : ""}`}>
              {stage.href && !isCurrent ? (
                <Link href={stage.href} className="gov-step-inner">
                  {content}
                </Link>
              ) : (
                <span className="gov-step-inner" aria-current={isCurrent ? "step" : undefined}>
                  {content}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

type StageState = "done" | "current" | "upcoming" | "skipped";

// Order: report, inspection, field validation, intervention, follow-up, closed.
const CASE_PROGRESS: Record<string, StageState[]> = {
  REPORTED: ["current", "upcoming", "upcoming", "upcoming", "upcoming", "upcoming"],
  FOR_INSPECTION: ["done", "current", "upcoming", "upcoming", "upcoming", "upcoming"],
  INSPECTION_SCHEDULED: ["done", "done", "current", "upcoming", "upcoming", "upcoming"],
  NOT_CONFIRMED: ["done", "done", "done", "skipped", "skipped", "skipped"],
  FIELD_VALIDATED: ["done", "done", "done", "current", "upcoming", "upcoming"],
  UNDER_INTERVENTION: ["done", "done", "done", "current", "upcoming", "upcoming"],
  FOLLOW_UP_DUE: ["done", "done", "done", "done", "current", "upcoming"],
  REINTERVENTION_REQUIRED: ["done", "done", "done", "current", "done", "upcoming"],
  CLOSED: ["done", "done", "done", "done", "done", "done"],
};

const STATE_LABELS: Record<StageState, string> = {
  done: "completed",
  current: "current stage",
  upcoming: "not yet reached",
  skipped: "not applicable",
};

/** Case-level progress derived only from the case's recorded status. */
export function CaseProgress({ status }: { status: string }) {
  const states = CASE_PROGRESS[status];
  if (!states) {
    return null;
  }
  return (
    <nav aria-label="Case progress" className="gov-steps">
      <div className="gov-steps-head">
        <p className="gov-steps-title">Case progress</p>
        <p className="gov-steps-note">
          {status === "NOT_CONFIRMED"
            ? "Field validation did not confirm pest damage, so no intervention stages apply."
            : status === "REINTERVENTION_REQUIRED"
              ? "The latest reassessment requires further intervention. A new intervention cycle is next."
              : "Shown from the case's current recorded status."}
        </p>
      </div>
      <ol className="gov-steps-list" style={STEP_COUNT_STYLE}>
        {STAGES.map((stage, index) => {
          const state = states[index];
          const negativeOutcome = status === "NOT_CONFIRMED" && stage.key === "validate";
          const detail = negativeOutcome
            ? "Not confirmed on site"
            : stage.key === "intervene" && status === "REINTERVENTION_REQUIRED"
              ? "Reintervention required"
              : stage.detail;
          return (
            <li
              key={stage.key}
              className={`gov-step gov-step--${state}${negativeOutcome ? " gov-step--outcome-negative" : ""}`}
            >
              <span className="gov-step-inner" aria-current={state === "current" ? "step" : undefined}>
                <span className="gov-step-marker" aria-hidden="true">
                  {state === "done" && !negativeOutcome ? <Icon name="check" size={14} /> : index + 1}
                </span>
                <span className="gov-step-text">
                  <span className="gov-step-label">
                    {stage.label}
                    <span className="sr-only">, {STATE_LABELS[state]}</span>
                  </span>
                  <span className="gov-step-detail">{detail}</span>
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
