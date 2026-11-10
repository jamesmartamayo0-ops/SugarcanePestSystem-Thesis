import { authenticatedFetch } from "@/lib/api";
import type { PestCaseStatus } from "@/lib/pest-cases";

export type ReportSummary = {
  total_cases: number;
  open_cases: number;
  closed_cases: number;
  not_confirmed_cases: number;
  under_intervention: number;
  follow_ups_due: number;
  reintervention_required: number;
};

export type ReportByStatus = Record<PestCaseStatus, number>;

export type ReportFollowUpSummary = {
  pending: number;
  overdue: number;
  completed: number;
  resolved: number;
  reintervention_required: number;
};

export type ReportInterventionSummary = {
  total_records: number;
  completed: number;
  pending: number;
  cases_with_repeat_intervention: number;
};

export type ReportCaseRow = {
  case_id: number;
  farmer: string | null;
  farm: string | null;
  barangay: string | null;
  pest_name: string | null;
  current_status: PestCaseStatus;
  reported_at: string | null;
  reported_area_hectares: number;
  latest_intervention_cycle: number | null;
  latest_follow_up_outcome: "RESOLVED" | "REINTERVENTION_REQUIRED" | null;
};

export type OperationalReport = {
  summary: ReportSummary;
  by_status: ReportByStatus;
  follow_up_summary: ReportFollowUpSummary;
  intervention_summary: ReportInterventionSummary;
  cases: ReportCaseRow[];
};

export type ReportsErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "unavailable"
  | "unexpected";

export class ReportsRequestError extends Error {
  constructor(
    public readonly kind: ReportsErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "ReportsRequestError";
  }
}

const ALL_STATUSES: PestCaseStatus[] = [
  "REPORTED",
  "FOR_INSPECTION",
  "INSPECTION_SCHEDULED",
  "FIELD_VALIDATED",
  "NOT_CONFIRMED",
  "UNDER_INTERVENTION",
  "FOLLOW_UP_DUE",
  "REINTERVENTION_REQUIRED",
  "CLOSED",
];

function isStatus(value: unknown): value is PestCaseStatus {
  return (ALL_STATUSES as string[]).includes(value as string);
}

function serverMessage(value: unknown, fallback: string): string {
  if (typeof value === "object" && value !== null && "message" in value) {
    const message = (value as { message?: unknown }).message;
    if (typeof message === "string" && message.length > 0 && message.length <= 500) {
      return message;
    }
  }
  return fallback;
}

async function readPayload(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function isFollowUpOutcome(value: unknown): value is "RESOLVED" | "REINTERVENTION_REQUIRED" {
  return value === "RESOLVED" || value === "REINTERVENTION_REQUIRED";
}

function parseReport(value: unknown): OperationalReport {
  if (typeof value !== "object" || value === null || !("data" in value)) {
    throw new ReportsRequestError("unexpected", "Operational report could not be read.");
  }
  const data = (value as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("report" in data)) {
    throw new ReportsRequestError("unexpected", "Operational report could not be read.");
  }
  const report: unknown = (data as { report: unknown }).report;
  if (typeof report !== "object" || report === null || Array.isArray(report)) {
    throw new ReportsRequestError("unexpected", "Operational report could not be read.");
  }
  const reportEntry = report as Record<string, unknown>;
  const summary: unknown = reportEntry.summary;
  const byStatus: unknown = reportEntry.by_status;
  const followUp: unknown = reportEntry.follow_up_summary;
  const intervention: unknown = reportEntry.intervention_summary;
  const cases: unknown = reportEntry.cases;
  if (
    typeof summary !== "object" ||
    summary === null ||
    Array.isArray(summary) ||
    typeof byStatus !== "object" ||
    byStatus === null ||
    Array.isArray(byStatus) ||
    typeof followUp !== "object" ||
    followUp === null ||
    Array.isArray(followUp) ||
    typeof intervention !== "object" ||
    intervention === null ||
    Array.isArray(intervention) ||
    !Array.isArray(cases)
  ) {
    throw new ReportsRequestError("unexpected", "Operational report could not be read.");
  }
  const summaryRecord = summary as Record<string, unknown>;
  const byStatusRecord = byStatus as Record<string, unknown>;
  const followUpRecord = followUp as Record<string, unknown>;
  const interventionRecord = intervention as Record<string, unknown>;
  const summaryKeys = [
    "total_cases",
    "open_cases",
    "closed_cases",
    "not_confirmed_cases",
    "under_intervention",
    "follow_ups_due",
    "reintervention_required",
  ];
  for (const key of summaryKeys) {
    if (typeof summaryRecord[key] !== "number") {
      throw new ReportsRequestError("unexpected", "Operational report could not be read.");
    }
  }
  for (const status of ALL_STATUSES) {
    if (typeof byStatusRecord[status] !== "number") {
      throw new ReportsRequestError("unexpected", "Operational report could not be read.");
    }
  }
  for (const key of ["pending", "overdue", "completed", "resolved", "reintervention_required"]) {
    if (typeof followUpRecord[key] !== "number") {
      throw new ReportsRequestError("unexpected", "Operational report could not be read.");
    }
  }
  for (const key of ["total_records", "completed", "pending", "cases_with_repeat_intervention"]) {
    if (typeof interventionRecord[key] !== "number") {
      throw new ReportsRequestError("unexpected", "Operational report could not be read.");
    }
  }
  const rows: ReportCaseRow[] = cases.map((entry: unknown) => {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) {
      throw new ReportsRequestError("unexpected", "Operational report could not be read.");
    }
    const item = entry as Record<string, unknown>;
    if (
      typeof item.case_id !== "number" ||
      (item.farmer !== null && typeof item.farmer !== "string") ||
      (item.farm !== null && typeof item.farm !== "string") ||
      (item.barangay !== null && typeof item.barangay !== "string") ||
      (item.pest_name !== null && typeof item.pest_name !== "string") ||
      !isStatus(item.current_status) ||
      (item.reported_at !== null && typeof item.reported_at !== "string") ||
      typeof item.reported_area_hectares !== "number" ||
      (item.latest_intervention_cycle !== null &&
        typeof item.latest_intervention_cycle !== "number") ||
      (item.latest_follow_up_outcome !== null &&
        !isFollowUpOutcome(item.latest_follow_up_outcome))
    ) {
      throw new ReportsRequestError("unexpected", "Operational report could not be read.");
    }
    return {
      case_id: item.case_id,
      farmer: item.farmer,
      farm: item.farm,
      barangay: item.barangay,
      pest_name: item.pest_name,
      current_status: item.current_status,
      reported_at: item.reported_at,
      reported_area_hectares: item.reported_area_hectares,
      latest_intervention_cycle: item.latest_intervention_cycle,
      latest_follow_up_outcome: item.latest_follow_up_outcome,
    } as ReportCaseRow;
  });
  return {
    summary: summaryRecord as unknown as ReportSummary,
    by_status: byStatusRecord as unknown as ReportByStatus,
    follow_up_summary: followUpRecord as unknown as ReportFollowUpSummary,
    intervention_summary: interventionRecord as unknown as ReportInterventionSummary,
    cases: rows,
  };
}

function throwForStatus(status: number, payload: unknown): never {
  if (status === 400) {
    throw new ReportsRequestError("invalid", serverMessage(payload, "Invalid report filter."));
  }
  if (status === 401) {
    throw new ReportsRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new ReportsRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to view reports."),
    );
  }
  if (status === 503) {
    throw new ReportsRequestError(
      "unavailable",
      serverMessage(payload, "Report service is unavailable."),
    );
  }
  throw new ReportsRequestError(
    "unexpected",
    serverMessage(payload, "Operational report could not be read."),
  );
}

export type ReportFilters = {
  status?: PestCaseStatus | "all";
  farmerId?: number;
  farmId?: number;
  reportedFrom?: string;
  reportedTo?: string;
};

export async function getOperationalReport(
  filters: ReportFilters = {},
): Promise<OperationalReport> {
  const params = new URLSearchParams();
  if (filters.status !== undefined && filters.status !== "all") {
    params.set("status", filters.status);
  }
  if (filters.farmerId !== undefined) {
    params.set("farmer_id", String(filters.farmerId));
  }
  if (filters.farmId !== undefined) {
    params.set("farm_id", String(filters.farmId));
  }
  if (filters.reportedFrom !== undefined && filters.reportedFrom !== "") {
    params.set("reported_from", filters.reportedFrom);
  }
  if (filters.reportedTo !== undefined && filters.reportedTo !== "") {
    params.set("reported_to", filters.reportedTo);
  }
  const query = params.toString();
  const path = query ? `/api/v1/reports/operational?${query}` : "/api/v1/reports/operational";
  let response: Response;
  try {
    response = await authenticatedFetch(path, { cache: "no-store" });
  } catch {
    throw new ReportsRequestError("unavailable", "Report service is unavailable.");
  }
  if (response.status === 200) {
    return parseReport(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response));
}
