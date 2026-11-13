import { authenticatedFetch } from "@/lib/api";
import {
  parsePestCaseSummaryList,
  type PestCaseStatus,
  type PestCaseSummary,
} from "@/lib/pest-cases";

export type InterventionMethodCategory =
  | "CULTURAL"
  | "MECHANICAL"
  | "BIOLOGICAL"
  | "CHEMICAL"
  | "OTHER";

export const INTERVENTION_METHOD_CATEGORIES: InterventionMethodCategory[] = [
  "CULTURAL",
  "MECHANICAL",
  "BIOLOGICAL",
  "CHEMICAL",
  "OTHER",
];

export type TechnicianSummary = {
  id: number;
  username: string;
  full_name: string;
};

export type InterventionCaseRef = {
  id: number;
  pest_name: string | null;
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

export type InterventionDetail = {
  id: number;
  pest_case_id: number;
  method_category: InterventionMethodCategory;
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
  pest_case: InterventionCaseRef;
};

export type InterventionsErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class InterventionsRequestError extends Error {
  constructor(
    public readonly kind: InterventionsErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "InterventionsRequestError";
  }
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

function isMethodCategory(value: unknown): value is InterventionMethodCategory {
  return (
    value === "CULTURAL" ||
    value === "MECHANICAL" ||
    value === "BIOLOGICAL" ||
    value === "CHEMICAL" ||
    value === "OTHER"
  );
}

function parseTechnician(value: unknown): TechnicianSummary {
  if (typeof value !== "object" || value === null) {
    throw new InterventionsRequestError("unexpected", "Technician list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.username !== "string" ||
    typeof entry.full_name !== "string"
  ) {
    throw new InterventionsRequestError("unexpected", "Technician list could not be read.");
  }
  return { id: entry.id, username: entry.username, full_name: entry.full_name };
}

function parseCaseRef(value: unknown): InterventionCaseRef {
  if (typeof value !== "object" || value === null) {
    throw new InterventionsRequestError("unexpected", "Intervention record could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    (entry.pest_name !== null && typeof entry.pest_name !== "string") ||
    !isStatus(entry.status) ||
    typeof entry.reported_area_hectares !== "number"
  ) {
    throw new InterventionsRequestError("unexpected", "Intervention record could not be read.");
  }
  let farm: InterventionCaseRef["farm"] = null;
  if (entry.farm !== null && entry.farm !== undefined) {
    const farmEntry = entry.farm as Record<string, unknown>;
    if (
      typeof farmEntry.id !== "number" ||
      typeof farmEntry.plot_identifier !== "string" ||
      typeof farmEntry.barangay !== "string" ||
      typeof farmEntry.area_hectares !== "number"
    ) {
      throw new InterventionsRequestError("unexpected", "Intervention record could not be read.");
    }
    let farmer: NonNullable<InterventionCaseRef["farm"]>["farmer"] = null;
    if (farmEntry.farmer !== null && farmEntry.farmer !== undefined) {
      const farmerEntry = farmEntry.farmer as Record<string, unknown>;
      if (
        typeof farmerEntry.id !== "number" ||
        typeof farmerEntry.full_name !== "string" ||
        typeof farmerEntry.barangay !== "string"
      ) {
        throw new InterventionsRequestError("unexpected", "Intervention record could not be read.");
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
    pest_name: entry.pest_name as string | null,
    status: entry.status as PestCaseStatus,
    reported_area_hectares: entry.reported_area_hectares as number,
    farm,
  };
}

function parseDetail(value: unknown, fallback: string): InterventionDetail {
  if (typeof value !== "object" || value === null) {
    throw new InterventionsRequestError("unexpected", fallback);
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.pest_case_id !== "number" ||
    !Number.isSafeInteger(entry.pest_case_id) ||
    entry.pest_case_id <= 0 ||
    !isMethodCategory(entry.method_category) ||
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
    throw new InterventionsRequestError("unexpected", fallback);
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
    pest_case: parseCaseRef(entry.pest_case),
  } as InterventionDetail;
}

function parseList(payload: unknown): InterventionDetail[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new InterventionsRequestError("unexpected", "Intervention list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("interventions" in data)) {
    throw new InterventionsRequestError("unexpected", "Intervention list could not be read.");
  }
  const items = (data as { interventions: unknown }).interventions;
  if (!Array.isArray(items)) {
    throw new InterventionsRequestError("unexpected", "Intervention list could not be read.");
  }
  return items.map((item) => parseDetail(item, "Intervention list could not be read."));
}

function parseSingle(payload: unknown, fallback: string): InterventionDetail {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new InterventionsRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("intervention" in data)) {
    throw new InterventionsRequestError("unexpected", fallback);
  }
  return parseDetail((data as { intervention: unknown }).intervention, fallback);
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new InterventionsRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new InterventionsRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new InterventionsRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission for this intervention action."),
    );
  }
  if (status === 404) {
    throw new InterventionsRequestError("not_found", serverMessage(payload, fallback));
  }
  if (status === 409) {
    throw new InterventionsRequestError("conflict", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new InterventionsRequestError(
      "unavailable",
      serverMessage(payload, "Intervention service is unavailable."),
    );
  }
  throw new InterventionsRequestError("unexpected", serverMessage(payload, fallback));
}

export type InterventionFilters = {
  pestCaseId?: number;
  assignedToUserId?: number;
};

export async function listInterventions(
  filters: InterventionFilters = {},
): Promise<InterventionDetail[]> {
  const params = new URLSearchParams();
  if (filters.pestCaseId !== undefined) {
    params.set("pest_case_id", String(filters.pestCaseId));
  }
  if (filters.assignedToUserId !== undefined) {
    params.set("assigned_to_user_id", String(filters.assignedToUserId));
  }
  const query = params.toString();
  const path = query ? `/api/v1/interventions?${query}` : "/api/v1/interventions";
  let response: Response;
  try {
    response = await authenticatedFetch(path, { cache: "no-store" });
  } catch {
    throw new InterventionsRequestError("unavailable", "Intervention service is unavailable.");
  }
  if (response.status === 200) {
    return parseList(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response), "Intervention list could not be read.");
}

/**
 * Field Validated and Reintervention Required cases waiting for an
 * intervention plan, limited by the backend to the caller's case scope.
 * Used instead of the Administrator-only Pest Case list.
 */
export async function listInterventionEligibleCases(): Promise<PestCaseSummary[]> {
  const fallback = "Eligible cases could not be read.";
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/interventions/eligible-cases", {
      cache: "no-store",
    });
  } catch {
    throw new InterventionsRequestError("unavailable", "Intervention service is unavailable.");
  }
  if (response.status === 200) {
    const payload = await readPayload(response);
    try {
      return parsePestCaseSummaryList(payload);
    } catch {
      throw new InterventionsRequestError("unexpected", fallback);
    }
  }
  throwForStatus(response.status, await readPayload(response), fallback);
}

export async function getIntervention(interventionId: number): Promise<InterventionDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/interventions/${interventionId}`, {
      cache: "no-store",
    });
  } catch {
    throw new InterventionsRequestError("unavailable", "Intervention service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Intervention could not be read.");
  }
  throwForStatus(response.status, await readPayload(response), "Intervention could not be read.");
}

export type StartInterventionInput = {
  method_category: InterventionMethodCategory;
  method_description: string;
  scheduled_for: string;
  assigned_to_user_id: number;
  follow_up_due_on?: string;
};

export async function startIntervention(
  caseId: number,
  input: StartInterventionInput,
  csrfToken: string,
): Promise<InterventionDetail> {
  const body: Record<string, unknown> = {
    method_category: input.method_category,
    method_description: input.method_description,
    scheduled_for: input.scheduled_for,
    assigned_to_user_id: input.assigned_to_user_id,
  };
  if (input.follow_up_due_on !== undefined && input.follow_up_due_on !== "") {
    body.follow_up_due_on = input.follow_up_due_on;
  }
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/pest-cases/${caseId}/start-intervention`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new InterventionsRequestError("unavailable", "Intervention service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingle(await readPayload(response), "Intervention could not be started.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Intervention could not be started.",
  );
}

export async function updateInterventionPlan(
  interventionId: number,
  input: {
    method_category?: InterventionMethodCategory;
    method_description?: string;
    scheduled_for?: string;
    assigned_to_user_id?: number;
    follow_up_due_on?: string | null;
  },
  csrfToken: string,
): Promise<InterventionDetail> {
  const body: Record<string, unknown> = {};
  if (input.method_category !== undefined) {
    body.method_category = input.method_category;
  }
  if (input.method_description !== undefined) {
    body.method_description = input.method_description;
  }
  if (input.scheduled_for !== undefined) {
    body.scheduled_for = input.scheduled_for;
  }
  if (input.assigned_to_user_id !== undefined) {
    body.assigned_to_user_id = input.assigned_to_user_id;
  }
  if (input.follow_up_due_on !== undefined) {
    body.follow_up_due_on = input.follow_up_due_on;
  }
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/interventions/${interventionId}/plan`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new InterventionsRequestError("unavailable", "Intervention service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Intervention plan could not be updated.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Intervention plan could not be updated.",
  );
}

export async function completeIntervention(
  interventionId: number,
  input: {
    performed_on: string;
    completion_notes: string;
    follow_up_due_on?: string;
    reuse_planned_follow_up_date?: boolean;
  },
  csrfToken: string,
): Promise<InterventionDetail> {
  const body: Record<string, unknown> = {
    performed_on: input.performed_on,
    completion_notes: input.completion_notes,
  };
  if (input.follow_up_due_on !== undefined && input.follow_up_due_on !== "") {
    body.follow_up_due_on = input.follow_up_due_on;
  }
  if (input.reuse_planned_follow_up_date === true) {
    body.reuse_planned_follow_up_date = true;
  }
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/interventions/${interventionId}/complete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new InterventionsRequestError("unavailable", "Intervention service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Intervention could not be completed.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Intervention could not be completed.",
  );
}
