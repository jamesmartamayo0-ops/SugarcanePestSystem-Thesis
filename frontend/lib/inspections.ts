import { authenticatedFetch } from "@/lib/api";
import {
  parseEvidencePhotoList,
  type EvidencePhoto,
  type PestCaseStatus,
} from "@/lib/pest-cases";

export type TechnicianSummary = {
  id: number;
  username: string;
  full_name: string;
};

export type InspectionCaseRef = {
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

export type InspectionDetail = {
  id: number;
  pest_case_id: number;
  scheduled_for: string;
  assigned_to_user_id: number;
  assigned_to: TechnicianSummary | null;
  scheduled_by_user_id: number;
  inspected_on: string | null;
  findings: string | null;
  pest_confirmed: boolean | null;
  confirmed_pest_name: string | null;
  validated_area_hectares: number | null;
  completed_by_user_id: number | null;
  completed_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  pest_case: InspectionCaseRef;
};

export type InspectionsErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class InspectionsRequestError extends Error {
  constructor(
    public readonly kind: InspectionsErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "InspectionsRequestError";
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

function parseTechnician(value: unknown): TechnicianSummary {
  if (typeof value !== "object" || value === null) {
    throw new InspectionsRequestError("unexpected", "Technician list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.username !== "string" ||
    typeof entry.full_name !== "string"
  ) {
    throw new InspectionsRequestError("unexpected", "Technician list could not be read.");
  }
  return { id: entry.id, username: entry.username, full_name: entry.full_name };
}

function parseCaseRef(value: unknown): InspectionCaseRef {
  if (typeof value !== "object" || value === null) {
    throw new InspectionsRequestError("unexpected", "Inspection record could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    (entry.pest_name !== null && typeof entry.pest_name !== "string") ||
    !isStatus(entry.status) ||
    typeof entry.reported_area_hectares !== "number"
  ) {
    throw new InspectionsRequestError("unexpected", "Inspection record could not be read.");
  }
  let farm: InspectionCaseRef["farm"] = null;
  if (entry.farm !== null && entry.farm !== undefined) {
    const farmEntry = entry.farm as Record<string, unknown>;
    if (
      typeof farmEntry.id !== "number" ||
      typeof farmEntry.plot_identifier !== "string" ||
      typeof farmEntry.barangay !== "string" ||
      typeof farmEntry.area_hectares !== "number"
    ) {
      throw new InspectionsRequestError("unexpected", "Inspection record could not be read.");
    }
    let farmer: NonNullable<InspectionCaseRef["farm"]>["farmer"] = null;
    if (farmEntry.farmer !== null && farmEntry.farmer !== undefined) {
      const farmerEntry = farmEntry.farmer as Record<string, unknown>;
      if (
        typeof farmerEntry.id !== "number" ||
        typeof farmerEntry.full_name !== "string" ||
        typeof farmerEntry.barangay !== "string"
      ) {
        throw new InspectionsRequestError("unexpected", "Inspection record could not be read.");
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

function parseDetail(value: unknown, fallback: string): InspectionDetail {
  if (typeof value !== "object" || value === null) {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.pest_case_id !== "number" ||
    !Number.isSafeInteger(entry.pest_case_id) ||
    entry.pest_case_id <= 0 ||
    typeof entry.scheduled_for !== "string" ||
    typeof entry.assigned_to_user_id !== "number" ||
    (entry.assigned_to !== null && typeof entry.assigned_to !== "object") ||
    typeof entry.scheduled_by_user_id !== "number" ||
    (entry.inspected_on !== null && typeof entry.inspected_on !== "string") ||
    (entry.findings !== null && typeof entry.findings !== "string") ||
    (entry.pest_confirmed !== null && typeof entry.pest_confirmed !== "boolean") ||
    (entry.confirmed_pest_name !== null &&
      entry.confirmed_pest_name !== undefined &&
      typeof entry.confirmed_pest_name !== "string") ||
    (entry.validated_area_hectares !== null &&
      typeof entry.validated_area_hectares !== "number") ||
    (entry.completed_by_user_id !== null &&
      typeof entry.completed_by_user_id !== "number") ||
    (entry.completed_at !== null && typeof entry.completed_at !== "string") ||
    (entry.created_at !== null && typeof entry.created_at !== "string") ||
    (entry.updated_at !== null && typeof entry.updated_at !== "string")
  ) {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  let assignedTo: TechnicianSummary | null = null;
  if (entry.assigned_to !== null) {
    assignedTo = parseTechnician(entry.assigned_to);
  }
  return {
    id: entry.id,
    pest_case_id: entry.pest_case_id,
    scheduled_for: entry.scheduled_for,
    assigned_to_user_id: entry.assigned_to_user_id,
    assigned_to: assignedTo,
    scheduled_by_user_id: entry.scheduled_by_user_id,
    inspected_on: entry.inspected_on,
    findings: entry.findings,
    pest_confirmed: entry.pest_confirmed,
    confirmed_pest_name: (entry.confirmed_pest_name as string | null | undefined) ?? null,
    validated_area_hectares: entry.validated_area_hectares,
    completed_by_user_id: entry.completed_by_user_id,
    completed_at: entry.completed_at,
    created_at: entry.created_at,
    updated_at: entry.updated_at,
    pest_case: parseCaseRef(entry.pest_case),
  } as InspectionDetail;
}

function parseList(payload: unknown): InspectionDetail[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new InspectionsRequestError("unexpected", "Inspection list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("inspections" in data)) {
    throw new InspectionsRequestError("unexpected", "Inspection list could not be read.");
  }
  const items = (data as { inspections: unknown }).inspections;
  if (!Array.isArray(items)) {
    throw new InspectionsRequestError("unexpected", "Inspection list could not be read.");
  }
  return items.map((item) => parseDetail(item, "Inspection list could not be read."));
}

function parseSingle(payload: unknown, fallback: string): InspectionDetail {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("inspection" in data)) {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  return parseDetail((data as { inspection: unknown }).inspection, fallback);
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new InspectionsRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new InspectionsRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new InspectionsRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission for this inspection action."),
    );
  }
  if (status === 404) {
    throw new InspectionsRequestError("not_found", serverMessage(payload, fallback));
  }
  if (status === 409) {
    throw new InspectionsRequestError("conflict", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new InspectionsRequestError(
      "unavailable",
      serverMessage(payload, "Inspection service is unavailable."),
    );
  }
  throw new InspectionsRequestError("unexpected", serverMessage(payload, fallback));
}

export type InspectionFilters = {
  pestCaseId?: number;
  assignedToUserId?: number;
};

export async function listInspections(
  filters: InspectionFilters = {},
): Promise<InspectionDetail[]> {
  const params = new URLSearchParams();
  if (filters.pestCaseId !== undefined) {
    params.set("pest_case_id", String(filters.pestCaseId));
  }
  if (filters.assignedToUserId !== undefined) {
    params.set("assigned_to_user_id", String(filters.assignedToUserId));
  }
  const query = params.toString();
  const path = query ? `/api/v1/inspections?${query}` : "/api/v1/inspections";
  let response: Response;
  try {
    response = await authenticatedFetch(path, { cache: "no-store" });
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 200) {
    return parseList(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response), "Inspection list could not be read.");
}

export async function getInspection(inspectionId: number): Promise<InspectionDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/inspections/${inspectionId}`, {
      cache: "no-store",
    });
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Inspection could not be read.");
  }
  throwForStatus(response.status, await readPayload(response), "Inspection could not be read.");
}

/**
 * The case's initial report (farmer observation and evidence photos), read
 * through the inspection. Pest Case Records are Administrator-only, so this
 * scoped endpoint is how an assigned Agriculture Technician sees it.
 */
export type InspectionInitialReport = {
  id: number;
  pest_name: string | null;
  symptoms: string | null;
  observed_on: string | null;
  reported_at: string | null;
  reported_area_hectares: number;
  evidence_photos: EvidencePhoto[];
};

function parseInitialReport(payload: unknown): InspectionInitialReport {
  const fallback = "Initial report could not be read.";
  const data =
    typeof payload === "object" && payload !== null && "data" in payload
      ? (payload as { data: unknown }).data
      : null;
  const report =
    typeof data === "object" && data !== null && "initial_report" in data
      ? (data as { initial_report: unknown }).initial_report
      : null;
  if (typeof report !== "object" || report === null) {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  const entry = report as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    (entry.pest_name !== null && typeof entry.pest_name !== "string") ||
    (entry.symptoms !== null && typeof entry.symptoms !== "string") ||
    (entry.observed_on !== null && typeof entry.observed_on !== "string") ||
    (entry.reported_at !== null && typeof entry.reported_at !== "string") ||
    typeof entry.reported_area_hectares !== "number" ||
    !Number.isFinite(entry.reported_area_hectares)
  ) {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  let photos: EvidencePhoto[];
  try {
    photos = parseEvidencePhotoList(entry.evidence_photos, fallback);
  } catch {
    throw new InspectionsRequestError("unexpected", fallback);
  }
  return {
    id: entry.id,
    pest_name: entry.pest_name as string | null,
    symptoms: entry.symptoms as string | null,
    observed_on: entry.observed_on as string | null,
    reported_at: entry.reported_at as string | null,
    reported_area_hectares: entry.reported_area_hectares,
    evidence_photos: photos,
  };
}

export async function getInspectionInitialReport(
  inspectionId: number,
): Promise<InspectionInitialReport> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/inspections/${inspectionId}/initial-report`, {
      cache: "no-store",
    });
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 200) {
    return parseInitialReport(await readPayload(response));
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Initial report could not be read.",
  );
}

export async function listTechnicians(): Promise<TechnicianSummary[]> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/inspections/technicians", {
      cache: "no-store",
    });
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 200) {
    const payload = await readPayload(response);
    if (
      typeof payload === "object" &&
      payload !== null &&
      "data" in payload &&
      typeof (payload as { data: unknown }).data === "object"
    ) {
      const data = (payload as { data: { technicians: unknown } }).data;
      if (Array.isArray(data.technicians)) {
        return data.technicians.map(parseTechnician);
      }
    }
    throw new InspectionsRequestError("unexpected", "Technician list could not be read.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Technician list could not be read.",
  );
}

export async function scheduleInspection(
  caseId: number,
  input: { scheduled_for: string; assigned_to_user_id: number },
  csrfToken: string,
): Promise<InspectionDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/pest-cases/${caseId}/schedule-inspection`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingle(await readPayload(response), "Inspection could not be scheduled.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Inspection could not be scheduled.",
  );
}

export async function rescheduleInspection(
  inspectionId: number,
  input: { scheduled_for?: string; assigned_to_user_id?: number },
  csrfToken: string,
): Promise<InspectionDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/inspections/${inspectionId}/schedule`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Inspection could not be rescheduled.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Inspection could not be rescheduled.",
  );
}

export async function recordFindings(
  inspectionId: number,
  input: {
    findings: string;
    pest_confirmed: boolean;
    confirmed_pest_name?: string | null;
    validated_area_hectares: number;
    inspected_on: string;
  },
  csrfToken: string,
): Promise<InspectionDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(
      `/api/v1/inspections/${inspectionId}/record-findings`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify(input),
      },
    );
  } catch {
    throw new InspectionsRequestError("unavailable", "Inspection service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingle(await readPayload(response), "Inspection findings could not be saved.");
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Inspection findings could not be saved.",
  );
}
