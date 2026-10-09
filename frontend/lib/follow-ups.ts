import { authenticatedFetch } from "@/lib/api";
import type { PestCaseStatus } from "@/lib/pest-cases";

export type FollowUpOutcome = "RESOLVED" | "REINTERVENTION_REQUIRED";

export type FollowUpDueState = "UPCOMING" | "DUE_TODAY" | "OVERDUE";

export const FOLLOW_UP_OUTCOMES: FollowUpOutcome[] = [
  "RESOLVED",
  "REINTERVENTION_REQUIRED",
];

export type TechnicianSummary = {
  id: number;
  username: string;
  full_name: string;
};

export type FollowUpCaseRef = {
  id: number;
  pest_name: string;
  status: PestCaseStatus;
  reported_area_hectares: number;
  farm: {
    id: number;
    plot_identifier: string;
    barangay: string;
    area_hectares: number;
    farmer: {
      id: number;
      full_name: string;
      barangay: string;
    } | null;
  } | null;
};

export type FollowUpInterventionRef = {
  id: number;
  pest_case_id: number;
  method_category: string;
  method_description: string;
  scheduled_for: string;
  assigned_to_user_id: number;
  assigned_to: TechnicianSummary | null;
  created_by_user_id: number;
  performed_on: string | null;
  completion_notes: string | null;
  follow_up_due_on: string | null;
  completed_by_user_id: number | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type FollowUpDetail = {
  id: number;
  intervention_id: number;
  observed_on: string;
  pest_observed: boolean;
  observed_affected_area_hectares: number | null;
  assessment_notes: string;
  outcome: FollowUpOutcome;
  recorded_by_user_id: number;
  recorded_by: TechnicianSummary | null;
  created_at: string | null;
  updated_at: string | null;
  intervention: FollowUpInterventionRef | null;
  assigned_to: TechnicianSummary | null;
  pest_case: FollowUpCaseRef | null;
};

export type FollowUpDueEntry = {
  intervention_id: number;
  pest_case_id: number;
  method_category: string;
  method_description: string;
  scheduled_for: string;
  assigned_to_user_id: number;
  assigned_to: TechnicianSummary | null;
  performed_on: string | null;
  follow_up_due_on: string | null;
  due_state: FollowUpDueState | null;
  case_status: PestCaseStatus | null;
  pest_case: FollowUpCaseRef | null;
  intervention: FollowUpInterventionRef;
};

export type FollowUpsErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class FollowUpsRequestError extends Error {
  constructor(
    public readonly kind: FollowUpsErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "FollowUpsRequestError";
  }
}

export function manilaTodayIso(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);

  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;

  if (!year || !month || !day) {
    throw new Error("Unable to determine Manila calendar date");
  }

  return `${year}-${month}-${day}`;
}

export function dueStateFor(followUpDueOn: string | null): FollowUpDueState | null {
  if (followUpDueOn === null) {
    return null;
  }
  const today = manilaTodayIso();
  if (followUpDueOn < today) {
    return "OVERDUE";
  }
  if (followUpDueOn === today) {
    return "DUE_TODAY";
  }
  return "UPCOMING";
}

export function dueBadgeLabel(state: FollowUpDueState | null): string {
  if (state === "OVERDUE") {
    return "Overdue";
  }
  if (state === "DUE_TODAY") {
    return "Due today";
  }
  if (state === "UPCOMING") {
    return "Upcoming";
  }
  return "Not set";
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

function isStatus(value: unknown): value is PestCaseStatus {
  return (
    value === "REPORTED" ||
    value === "FOR_INSPECTION" ||
    value === "INSPECTION_SCHEDULED" ||
    value === "NOT_CONFIRMED" ||
    value === "FIELD_VALIDATED" ||
    value === "UNDER_INTERVENTION" ||
    value === "FOLLOW_UP_DUE" ||
    value === "REINTERVENTION_REQUIRED" ||
    value === "CLOSED"
  );
}

function isOutcome(value: unknown): value is FollowUpOutcome {
  return value === "RESOLVED" || value === "REINTERVENTION_REQUIRED";
}

function isDueState(value: unknown): value is FollowUpDueState {
  return value === "UPCOMING" || value === "DUE_TODAY" || value === "OVERDUE";
}

function parseTechnician(value: unknown): TechnicianSummary {
  if (typeof value !== "object" || value === null) {
    throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.username !== "string" ||
    typeof entry.full_name !== "string"
  ) {
    throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
  }
  return { id: entry.id, username: entry.username, full_name: entry.full_name };
}

function parseCaseRef(value: unknown): FollowUpCaseRef {
  if (typeof value !== "object" || value === null) {
    throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    typeof entry.pest_name !== "string" ||
    !isStatus(entry.status) ||
    typeof entry.reported_area_hectares !== "number"
  ) {
    throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
  }
  let farm: FollowUpCaseRef["farm"] = null;
  if (entry.farm !== null && entry.farm !== undefined) {
    const farmEntry = entry.farm as Record<string, unknown>;
    if (
      typeof farmEntry.id !== "number" ||
      typeof farmEntry.plot_identifier !== "string" ||
      typeof farmEntry.barangay !== "string" ||
      typeof farmEntry.area_hectares !== "number"
    ) {
      throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
    }
    let farmer: NonNullable<FollowUpCaseRef["farm"]>["farmer"] = null;
    if (farmEntry.farmer !== null && farmEntry.farmer !== undefined) {
      const farmerEntry = farmEntry.farmer as Record<string, unknown>;
      if (
        typeof farmerEntry.id !== "number" ||
        typeof farmerEntry.full_name !== "string" ||
        typeof farmerEntry.barangay !== "string"
      ) {
        throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
      }
      farmer = {
        id: farmerEntry.id,
        full_name: farmerEntry.full_name,
        barangay: farmerEntry.barangay,
      };
    }
    farm = {
      id: farmEntry.id,
      plot_identifier: farmEntry.plot_identifier,
      barangay: farmEntry.barangay,
      area_hectares: farmEntry.area_hectares,
      farmer,
    };
  }
  return {
    id: entry.id as number,
    pest_name: entry.pest_name as string,
    status: entry.status as PestCaseStatus,
    reported_area_hectares: entry.reported_area_hectares as number,
    farm,
  };
}

function parseInterventionRef(value: unknown): FollowUpInterventionRef {
  if (typeof value !== "object" || value === null) {
    throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    typeof entry.pest_case_id !== "number" ||
    typeof entry.method_category !== "string" ||
    typeof entry.method_description !== "string" ||
    typeof entry.scheduled_for !== "string" ||
    typeof entry.assigned_to_user_id !== "number" ||
    (entry.assigned_to !== null && typeof entry.assigned_to !== "object") ||
    typeof entry.created_by_user_id !== "number" ||
    (entry.performed_on !== null && typeof entry.performed_on !== "string") ||
    (entry.completion_notes !== null && typeof entry.completion_notes !== "string") ||
    (entry.follow_up_due_on !== null && typeof entry.follow_up_due_on !== "string") ||
    (entry.completed_by_user_id !== null && typeof entry.completed_by_user_id !== "number") ||
    (entry.completed_at !== null && typeof entry.completed_at !== "string") ||
    (entry.created_at !== null && typeof entry.created_at !== "string") ||
    (entry.updated_at !== null && typeof entry.updated_at !== "string")
  ) {
    throw new FollowUpsRequestError("unexpected", "Follow-up record could not be read.");
  }
  let assignedTo: TechnicianSummary | null = null;
  if (entry.assigned_to !== null) {
    assignedTo = parseTechnician(entry.assigned_to);
  }
  return {
    id: entry.id,
    pest_case_id: entry.pest_case_id,
    method_category: entry.method_category,
    method_description: entry.method_description,
    scheduled_for: entry.scheduled_for,
    assigned_to_user_id: entry.assigned_to_user_id,
    assigned_to: assignedTo,
    created_by_user_id: entry.created_by_user_id,
    performed_on: entry.performed_on,
    completion_notes: entry.completion_notes,
    follow_up_due_on: entry.follow_up_due_on,
    completed_by_user_id: entry.completed_by_user_id,
    completed_at: entry.completed_at,
    created_at: entry.created_at,
    updated_at: entry.updated_at,
  } as FollowUpInterventionRef;
}

function parseDetail(value: unknown, fallback: string): FollowUpDetail {
  if (typeof value !== "object" || value === null) {
    throw new FollowUpsRequestError("unexpected", fallback);
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.intervention_id !== "number" ||
    !Number.isSafeInteger(entry.intervention_id) ||
    entry.intervention_id <= 0 ||
    typeof entry.observed_on !== "string" ||
    typeof entry.pest_observed !== "boolean" ||
    (entry.observed_affected_area_hectares !== null &&
      typeof entry.observed_affected_area_hectares !== "number") ||
    typeof entry.assessment_notes !== "string" ||
    !isOutcome(entry.outcome) ||
    typeof entry.recorded_by_user_id !== "number" ||
    (entry.recorded_by !== null && typeof entry.recorded_by !== "object") ||
    (entry.created_at !== null && typeof entry.created_at !== "string") ||
    (entry.updated_at !== null && typeof entry.updated_at !== "string")
  ) {
    throw new FollowUpsRequestError("unexpected", fallback);
  }
  let recordedBy: TechnicianSummary | null = null;
  if (entry.recorded_by !== null) {
    recordedBy = parseTechnician(entry.recorded_by);
  }
  let intervention: FollowUpInterventionRef | null = null;
  if (entry.intervention !== null && entry.intervention !== undefined) {
    intervention = parseInterventionRef(entry.intervention);
  }
  let assignedTo: TechnicianSummary | null = null;
  if (entry.assigned_to !== null && entry.assigned_to !== undefined) {
    assignedTo = parseTechnician(entry.assigned_to);
  }
  let pestCase: FollowUpCaseRef | null = null;
  if (entry.pest_case !== null && entry.pest_case !== undefined) {
    pestCase = parseCaseRef(entry.pest_case);
  }
  return {
    id: entry.id,
    intervention_id: entry.intervention_id,
    observed_on: entry.observed_on,
    pest_observed: entry.pest_observed,
    observed_affected_area_hectares: entry.observed_affected_area_hectares,
    assessment_notes: entry.assessment_notes,
    outcome: entry.outcome,
    recorded_by_user_id: entry.recorded_by_user_id,
    recorded_by: recordedBy,
    created_at: entry.created_at,
    updated_at: entry.updated_at,
    intervention,
    assigned_to: assignedTo,
    pest_case: pestCase,
  } as FollowUpDetail;
}

function parseDueEntry(value: unknown): FollowUpDueEntry {
  if (typeof value !== "object" || value === null) {
    throw new FollowUpsRequestError("unexpected", "Follow-up queue could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.intervention_id !== "number" ||
    typeof entry.pest_case_id !== "number" ||
    typeof entry.method_category !== "string" ||
    typeof entry.method_description !== "string" ||
    typeof entry.scheduled_for !== "string" ||
    typeof entry.assigned_to_user_id !== "number" ||
    (entry.assigned_to !== null && typeof entry.assigned_to !== "object") ||
    (entry.performed_on !== null && typeof entry.performed_on !== "string") ||
    (entry.follow_up_due_on !== null && typeof entry.follow_up_due_on !== "string") ||
    (entry.due_state !== null &&
      entry.due_state !== undefined &&
      !isDueState(entry.due_state)) ||
    (entry.case_status !== null &&
      entry.case_status !== undefined &&
      !isStatus(entry.case_status))
  ) {
    throw new FollowUpsRequestError("unexpected", "Follow-up queue could not be read.");
  }
  let assignedTo: TechnicianSummary | null = null;
  if (entry.assigned_to !== null) {
    assignedTo = parseTechnician(entry.assigned_to);
  }
  let pestCase: FollowUpCaseRef | null = null;
  if (entry.pest_case !== null && entry.pest_case !== undefined) {
    pestCase = parseCaseRef(entry.pest_case);
  }
  if (entry.intervention === null || entry.intervention === undefined) {
    throw new FollowUpsRequestError("unexpected", "Follow-up queue could not be read.");
  }
  return {
    intervention_id: entry.intervention_id,
    pest_case_id: entry.pest_case_id,
    method_category: entry.method_category,
    method_description: entry.method_description,
    scheduled_for: entry.scheduled_for,
    assigned_to_user_id: entry.assigned_to_user_id,
    assigned_to: assignedTo,
    performed_on: entry.performed_on,
    follow_up_due_on: entry.follow_up_due_on,
    due_state: (entry.due_state ?? null) as FollowUpDueState | null,
    case_status: (entry.case_status ?? null) as PestCaseStatus | null,
    pest_case: pestCase,
    intervention: parseInterventionRef(entry.intervention),
  } as FollowUpDueEntry;
}

function parseList(payload: unknown): FollowUpDetail[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FollowUpsRequestError("unexpected", "Follow-up list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("follow_ups" in data)) {
    throw new FollowUpsRequestError("unexpected", "Follow-up list could not be read.");
  }
  const items = (data as { follow_ups: unknown }).follow_ups;
  if (!Array.isArray(items)) {
    throw new FollowUpsRequestError("unexpected", "Follow-up list could not be read.");
  }
  return items.map((item) => parseDetail(item, "Follow-up list could not be read."));
}

function parseDueList(payload: unknown): FollowUpDueEntry[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FollowUpsRequestError("unexpected", "Follow-up queue could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("due" in data)) {
    throw new FollowUpsRequestError("unexpected", "Follow-up queue could not be read.");
  }
  const items = (data as { due: unknown }).due;
  if (!Array.isArray(items)) {
    throw new FollowUpsRequestError("unexpected", "Follow-up queue could not be read.");
  }
  return items.map(parseDueEntry);
}

function parseSingle(payload: unknown, fallback: string): FollowUpDetail {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FollowUpsRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("follow_up" in data)) {
    throw new FollowUpsRequestError("unexpected", fallback);
  }
  return parseDetail((data as { follow_up: unknown }).follow_up, fallback);
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new FollowUpsRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new FollowUpsRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new FollowUpsRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission for this follow-up action."),
    );
  }
  if (status === 404) {
    throw new FollowUpsRequestError("not_found", serverMessage(payload, fallback));
  }
  if (status === 409) {
    throw new FollowUpsRequestError("conflict", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new FollowUpsRequestError(
      "unavailable",
      serverMessage(payload, "Follow-up service is unavailable."),
    );
  }
  throw new FollowUpsRequestError("unexpected", serverMessage(payload, fallback));
}

export type FollowUpFilters = {
  pestCaseId?: number;
  interventionId?: number;
  outcome?: FollowUpOutcome;
};

export async function listFollowUps(
  filters: FollowUpFilters = {},
): Promise<FollowUpDetail[]> {
  const params = new URLSearchParams();
  if (filters.pestCaseId !== undefined) {
    params.set("pest_case_id", String(filters.pestCaseId));
  }
  if (filters.interventionId !== undefined) {
    params.set("intervention_id", String(filters.interventionId));
  }
  if (filters.outcome !== undefined) {
    params.set("outcome", filters.outcome);
  }
  const query = params.toString();
  const path = query ? `/api/v1/follow-ups?${query}` : "/api/v1/follow-ups";
  let response: Response;
  try {
    response = await authenticatedFetch(path, { cache: "no-store" });
  } catch {
    throw new FollowUpsRequestError("unavailable", "Follow-up service is unavailable.");
  }
  if (response.status === 200) {
    return parseList(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response), "Follow-up list could not be read.");
}

export async function listDueFollowUps(): Promise<FollowUpDueEntry[]> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/follow-ups/due", {
      cache: "no-store",
    });
  } catch {
    throw new FollowUpsRequestError("unavailable", "Follow-up service is unavailable.");
  }
  if (response.status === 200) {
    return parseDueList(await readPayload(response));
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Follow-up queue could not be read.",
  );
}

export async function getFollowUp(followUpId: number): Promise<FollowUpDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/follow-ups/${followUpId}`, {
      cache: "no-store",
    });
  } catch {
    throw new FollowUpsRequestError("unavailable", "Follow-up service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Follow-up could not be read.");
  }
  throwForStatus(response.status, await readPayload(response), "Follow-up could not be read.");
}

export type RecordFollowUpInput = {
  observed_on: string;
  pest_observed: boolean;
  observed_affected_area_hectares?: number | null;
  assessment_notes: string;
  outcome: FollowUpOutcome;
};

export async function recordFollowUp(
  interventionId: number,
  input: RecordFollowUpInput,
  csrfToken: string,
): Promise<FollowUpDetail> {
  const body: Record<string, unknown> = {
    observed_on: input.observed_on,
    pest_observed: input.pest_observed,
    assessment_notes: input.assessment_notes,
    outcome: input.outcome,
  };
  if (
    input.observed_affected_area_hectares !== undefined &&
    input.observed_affected_area_hectares !== null
  ) {
    body.observed_affected_area_hectares = input.observed_affected_area_hectares;
  }
  let response: Response;
  try {
    response = await authenticatedFetch(
      `/api/v1/interventions/${interventionId}/record-follow-up`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify(body),
      },
    );
  } catch {
    throw new FollowUpsRequestError("unavailable", "Follow-up service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingle(await readPayload(response), "Follow-up could not be recorded.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Follow-up could not be recorded.",
  );
}
