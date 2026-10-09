import { authenticatedFetch } from "@/lib/api";

export type PestCaseStatus =
  | "REPORTED"
  | "FOR_INSPECTION"
  | "INSPECTION_SCHEDULED"
  | "NOT_CONFIRMED"
  | "FIELD_VALIDATED"
  | "UNDER_INTERVENTION"
  | "FOLLOW_UP_DUE"
  | "REINTERVENTION_REQUIRED"
  | "CLOSED";

export type PestCaseSummary = {
  id: number;
  farm_id: number;
  pest_name: string;
  reported_area_hectares: number;
  status: PestCaseStatus;
  observed_on: string | null;
  reported_at: string | null;
};

export type PestCaseFarmRef = {
  id: number;
  plot_identifier: string;
  barangay: string;
  area_hectares: number;
  farmer: {
    id: number;
    full_name: string;
    barangay: string;
  };
};

export type PestCaseReporterRef = {
  id: number;
  username: string;
  full_name: string;
};

export type PestCaseDetail = PestCaseSummary & {
  symptoms: string | null;
  farm: PestCaseFarmRef;
  reporter: PestCaseReporterRef;
  updated_at: string | null;
};

export type PestCasesErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class PestCasesRequestError extends Error {
  constructor(
    public readonly kind: PestCasesErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "PestCasesRequestError";
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

function parseSummary(value: unknown): PestCaseSummary {
  if (typeof value !== "object" || value === null) {
    throw new PestCasesRequestError("unexpected", "Pest case list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.farm_id !== "number" ||
    !Number.isSafeInteger(entry.farm_id) ||
    entry.farm_id <= 0 ||
    typeof entry.pest_name !== "string" ||
    typeof entry.reported_area_hectares !== "number" ||
    !Number.isFinite(entry.reported_area_hectares) ||
    (entry.status !== "REPORTED" &&
      entry.status !== "FOR_INSPECTION" &&
      entry.status !== "INSPECTION_SCHEDULED" &&
      entry.status !== "NOT_CONFIRMED" &&
      entry.status !== "FIELD_VALIDATED" &&
      entry.status !== "UNDER_INTERVENTION" &&
      entry.status !== "FOLLOW_UP_DUE" &&
      entry.status !== "REINTERVENTION_REQUIRED" &&
      entry.status !== "CLOSED") ||
    (entry.observed_on !== null && typeof entry.observed_on !== "string") ||
    (entry.reported_at !== null && typeof entry.reported_at !== "string")
  ) {
    throw new PestCasesRequestError("unexpected", "Pest case list could not be read.");
  }
  return {
    id: entry.id,
    farm_id: entry.farm_id,
    pest_name: entry.pest_name,
    reported_area_hectares: entry.reported_area_hectares,
    status: entry.status,
    observed_on: entry.observed_on,
    reported_at: entry.reported_at,
  };
}

function parseDetail(value: unknown, fallback: string): PestCaseDetail {
  const summary = parseSummary(value);
  if (typeof value !== "object" || value === null) {
    throw new PestCasesRequestError("unexpected", fallback);
  }
  const entry = value as Record<string, unknown>;
  const farm = entry.farm;
  const reporter = entry.reporter;
  if (
    (entry.symptoms !== null && typeof entry.symptoms !== "string") ||
    typeof farm !== "object" ||
    farm === null ||
    typeof reporter !== "object" ||
    reporter === null ||
    (entry.updated_at !== null && typeof entry.updated_at !== "string")
  ) {
    throw new PestCasesRequestError("unexpected", fallback);
  }
  const farmEntry = farm as Record<string, unknown>;
  const farmer = farmEntry.farmer;
  const reporterEntry = reporter as Record<string, unknown>;
  if (
    typeof farmEntry.id !== "number" ||
    typeof farmEntry.plot_identifier !== "string" ||
    typeof farmEntry.barangay !== "string" ||
    typeof farmEntry.area_hectares !== "number" ||
    typeof farmer !== "object" ||
    farmer === null ||
    typeof (farmer as Record<string, unknown>).id !== "number" ||
    typeof (farmer as Record<string, unknown>).full_name !== "string" ||
    typeof (farmer as Record<string, unknown>).barangay !== "string" ||
    typeof reporterEntry.id !== "number" ||
    typeof reporterEntry.username !== "string" ||
    typeof reporterEntry.full_name !== "string"
  ) {
    throw new PestCasesRequestError("unexpected", fallback);
  }
  const farmerEntry = farmer as Record<string, unknown>;
  return {
    ...summary,
    symptoms: entry.symptoms as string | null,
    farm: {
      id: farmEntry.id as number,
      plot_identifier: farmEntry.plot_identifier as string,
      barangay: farmEntry.barangay as string,
      area_hectares: farmEntry.area_hectares as number,
      farmer: {
        id: farmerEntry.id as number,
        full_name: farmerEntry.full_name as string,
        barangay: farmerEntry.barangay as string,
      },
    },
    reporter: {
      id: reporterEntry.id as number,
      username: reporterEntry.username as string,
      full_name: reporterEntry.full_name as string,
    },
    updated_at: entry.updated_at as string | null,
  };
}

function parseCaseList(payload: unknown): PestCaseSummary[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new PestCasesRequestError("unexpected", "Pest case list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("pest_cases" in data)) {
    throw new PestCasesRequestError("unexpected", "Pest case list could not be read.");
  }
  const cases = (data as { pest_cases: unknown }).pest_cases;
  if (!Array.isArray(cases)) {
    throw new PestCasesRequestError("unexpected", "Pest case list could not be read.");
  }
  return cases.map(parseSummary);
}

function parseSingleCase(payload: unknown, fallback: string): PestCaseDetail {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new PestCasesRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("pest_case" in data)) {
    throw new PestCasesRequestError("unexpected", fallback);
  }
  return parseDetail((data as { pest_case: unknown }).pest_case, fallback);
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new PestCasesRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new PestCasesRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new PestCasesRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to manage pest cases."),
    );
  }
  if (status === 404) {
    throw new PestCasesRequestError("not_found", serverMessage(payload, fallback));
  }
  if (status === 409) {
    throw new PestCasesRequestError("conflict", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new PestCasesRequestError(
      "unavailable",
      serverMessage(payload, "Pest case service is unavailable."),
    );
  }
  throw new PestCasesRequestError("unexpected", serverMessage(payload, fallback));
}

export type PestCaseFilters = {
  farmId?: number;
  status?: PestCaseStatus | "all";
};

export async function listPestCases(filters: PestCaseFilters = {}): Promise<PestCaseSummary[]> {
  const params = new URLSearchParams();
  if (filters.farmId !== undefined) {
    params.set("farm_id", String(filters.farmId));
  }
  if (filters.status !== undefined && filters.status !== "all") {
    params.set("status", filters.status);
  }
  const query = params.toString();
  const path = query ? `/api/v1/pest-cases?${query}` : "/api/v1/pest-cases";
  let response: Response;
  try {
    response = await authenticatedFetch(path, {
      cache: "no-store",
    });
  } catch {
    throw new PestCasesRequestError("unavailable", "Pest case service is unavailable.");
  }
  if (response.status === 200) {
    return parseCaseList(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response), "Pest case list could not be read.");
}

export async function getPestCase(caseId: number): Promise<PestCaseDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/pest-cases/${caseId}`, {
      cache: "no-store",
    });
  } catch {
    throw new PestCasesRequestError("unavailable", "Pest case service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingleCase(await readPayload(response), "Pest case could not be read.");
  }
  throwForStatus(response.status, await readPayload(response), "Pest case could not be read.");
}

export type CreatePestCaseInput = {
  farm_id: number;
  pest_name: string;
  symptoms?: string | null;
  observed_on?: string | null;
  reported_area_hectares: number;
};

export async function createPestCase(
  input: CreatePestCaseInput,
  csrfToken: string,
): Promise<PestCaseDetail> {
  const body: Record<string, unknown> = {
    farm_id: input.farm_id,
    pest_name: input.pest_name,
    reported_area_hectares: input.reported_area_hectares,
  };
  if (input.symptoms !== undefined && input.symptoms !== null && input.symptoms !== "") {
    body.symptoms = input.symptoms;
  }
  if (input.observed_on !== undefined && input.observed_on !== null && input.observed_on !== "") {
    body.observed_on = input.observed_on;
  }
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/pest-cases", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new PestCasesRequestError("unavailable", "Pest case service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingleCase(await readPayload(response), "Pest case could not be reported.");
  }
  throwForStatus(response.status, await readPayload(response), "Pest case could not be reported.");
}

export type UpdatePestCaseInput = {
  farm_id?: number;
  pest_name?: string;
  symptoms?: string | null;
  observed_on?: string | null;
  reported_area_hectares?: number;
};

export async function updatePestCase(
  caseId: number,
  input: UpdatePestCaseInput,
  csrfToken: string,
): Promise<PestCaseDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/pest-cases/${caseId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new PestCasesRequestError("unavailable", "Pest case service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingleCase(await readPayload(response), "Pest case could not be updated.");
  }
  throwForStatus(response.status, await readPayload(response), "Pest case could not be updated.");
}

export async function submitForInspection(
  caseId: number,
  csrfToken: string,
): Promise<PestCaseDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/pest-cases/${caseId}/submit-for-inspection`, {
      method: "POST",
      headers: {
        "X-CSRF-Token": csrfToken,
      },
    });
  } catch {
    throw new PestCasesRequestError("unavailable", "Pest case service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingleCase(
      await readPayload(response),
      "Pest case could not be submitted for inspection.",
    );
  }
  if (response.status === 404) {
    throw new PestCasesRequestError(
      "not_found",
      serverMessage(await readPayload(response), "Pest case was not found."),
    );
  }
  throwForStatus(
    response.status,
    await readPayload(response),
    "Pest case could not be submitted for inspection.",
  );
}
