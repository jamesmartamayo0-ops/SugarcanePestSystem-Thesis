// Presentation only: never use these labels as API values or workflow comparisons.
const WORKFLOW_LABELS: Record<string, string> = {
  REPORTED: "Reported",
  FOR_INSPECTION: "For Inspection",
  INSPECTION_SCHEDULED: "Inspection Scheduled",
  FIELD_VALIDATED: "Field Validated",
  NOT_CONFIRMED: "Not Confirmed",
  UNDER_INTERVENTION: "Under Intervention",
  FOLLOW_UP_DUE: "Follow-up Due",
  REINTERVENTION_REQUIRED: "Reintervention Required",
  CLOSED: "Closed",
  RESOLVED: "Resolved",
};

export function workflowLabel(value: string): string {
  return Object.hasOwn(WORKFLOW_LABELS, value) ? WORKFLOW_LABELS[value] : value;
}

// Only for generated success feedback; do not rewrite user-entered record text.
export function workflowMessage(value: string): string {
  return value.replace(/\b[A-Z]+(?:_[A-Z]+)*\b/g, workflowLabel);
}

// Rendering only: date-only values retain their calendar day; timestamps use Manila time.
export function formatDisplayDate(value: string | null): string {
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
