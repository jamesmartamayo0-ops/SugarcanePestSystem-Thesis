import { authenticatedFetch } from "@/lib/api";
import type { PestCaseStatus } from "@/lib/pest-cases";

export type DashboardTotals = {
  farmers: number;
  farms: number;
  pest_cases: number;
};

export type DashboardByStatus = Record<PestCaseStatus, number>;

export type DashboardActionNeeded = {
  awaiting_inspection_scheduling: number;
  inspections_scheduled_awaiting_validation: number;
  validated_awaiting_intervention: number;
  interventions_in_progress: number;
  follow_ups_due: number;
  overdue_follow_ups: number;
  reintervention_required: number;
};

export type DashboardRecentCase = {
  id: number;
  pest_name: string | null;
  status: PestCaseStatus;
  farm_id: number;
  updated_at: string | null;
};

export type DashboardSummary = {
  totals: DashboardTotals;
  by_status: DashboardByStatus;
  action_needed: DashboardActionNeeded;
  recent_cases: DashboardRecentCase[];
};

export type DashboardErrorKind =
  | "unauthenticated"
  | "forbidden"
  | "unavailable"
  | "unexpected";

export class DashboardRequestError extends Error {
  constructor(
    public readonly kind: DashboardErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "DashboardRequestError";
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

function parseSummary(value: unknown): DashboardSummary {
  if (typeof value !== "object" || value === null || !("data" in value)) {
    throw new DashboardRequestError("unexpected", "Dashboard summary could not be read.");
  }
  const data = (value as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("summary" in data)) {
    throw new DashboardRequestError("unexpected", "Dashboard summary could not be read.");
  }
  const summary = (data as { summary: unknown }).summary as Record<string, unknown>;
  const totals = summary.totals as Record<string, unknown>;
  const byStatus = summary.by_status as Record<string, unknown>;
  const action = summary.action_needed as Record<string, unknown>;
  const recent = summary.recent_cases;
  if (
    typeof totals !== "object" ||
    totals === null ||
    typeof totals.farmers !== "number" ||
    typeof totals.farms !== "number" ||
    typeof totals.pest_cases !== "number" ||
    typeof byStatus !== "object" ||
    byStatus === null ||
    typeof action !== "object" ||
    action === null ||
    !Array.isArray(recent)
  ) {
    throw new DashboardRequestError("unexpected", "Dashboard summary could not be read.");
  }
  for (const status of ALL_STATUSES) {
    if (typeof byStatus[status] !== "number") {
      throw new DashboardRequestError("unexpected", "Dashboard summary could not be read.");
    }
  }
  const actionKeys: (keyof DashboardActionNeeded)[] = [
    "awaiting_inspection_scheduling",
    "inspections_scheduled_awaiting_validation",
    "validated_awaiting_intervention",
    "interventions_in_progress",
    "follow_ups_due",
    "overdue_follow_ups",
    "reintervention_required",
  ];
  for (const key of actionKeys) {
    if (typeof action[key] !== "number") {
      throw new DashboardRequestError("unexpected", "Dashboard summary could not be read.");
    }
  }
  const parsedRecent: DashboardRecentCase[] = recent.map((entry) => {
    const item = entry as Record<string, unknown>;
    if (
      typeof item.id !== "number" ||
      (item.pest_name !== null && typeof item.pest_name !== "string") ||
      !isStatus(item.status) ||
      typeof item.farm_id !== "number" ||
      (item.updated_at !== null && typeof item.updated_at !== "string")
    ) {
      throw new DashboardRequestError("unexpected", "Dashboard summary could not be read.");
    }
    return {
      id: item.id,
      pest_name: item.pest_name,
      status: item.status,
      farm_id: item.farm_id,
      updated_at: item.updated_at,
    } as DashboardRecentCase;
  });
  return {
    totals: {
      farmers: totals.farmers,
      farms: totals.farms,
      pest_cases: totals.pest_cases,
    },
    by_status: byStatus as unknown as DashboardByStatus,
    action_needed: action as unknown as DashboardActionNeeded,
    recent_cases: parsedRecent,
  };
}

function throwForStatus(status: number, payload: unknown): never {
  if (status === 401) {
    throw new DashboardRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new DashboardRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to view the dashboard."),
    );
  }
  if (status === 503) {
    throw new DashboardRequestError(
      "unavailable",
      serverMessage(payload, "Dashboard service is unavailable."),
    );
  }
  throw new DashboardRequestError(
    "unexpected",
    serverMessage(payload, "Dashboard summary could not be read."),
  );
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/dashboard/summary", {
      cache: "no-store",
    });
  } catch {
    throw new DashboardRequestError("unavailable", "Dashboard service is unavailable.");
  }
  if (response.status === 200) {
    return parseSummary(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response));
}
