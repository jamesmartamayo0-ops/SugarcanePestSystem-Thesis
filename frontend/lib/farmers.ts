import { authenticatedFetch } from "@/lib/api";

export type FarmerSummary = {
  id: number;
  full_name: string;
  barangay: string;
  contact_number: string | null;
  farm_count: number;
};

export type FarmerFarmRef = {
  id: number;
  plot_identifier: string;
  barangay: string;
  area_hectares: number;
};

export type FarmerDetail = {
  id: number;
  full_name: string;
  barangay: string;
  contact_number: string | null;
  farms: FarmerFarmRef[];
  created_at: string | null;
  updated_at: string | null;
};

export type FarmersErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class FarmersRequestError extends Error {
  constructor(
    public readonly kind: FarmersErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "FarmersRequestError";
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

function parseFarmerSummary(value: unknown): FarmerSummary {
  if (typeof value !== "object" || value === null) {
    throw new FarmersRequestError("unexpected", "Farmer list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.full_name !== "string" ||
    typeof entry.barangay !== "string" ||
    (entry.contact_number !== null && typeof entry.contact_number !== "string") ||
    typeof entry.farm_count !== "number" ||
    !Number.isSafeInteger(entry.farm_count) ||
    entry.farm_count < 0
  ) {
    throw new FarmersRequestError("unexpected", "Farmer list could not be read.");
  }
  return {
    id: entry.id,
    full_name: entry.full_name,
    barangay: entry.barangay,
    contact_number: entry.contact_number,
    farm_count: entry.farm_count,
  };
}

function parseFarmRef(value: unknown): FarmerFarmRef {
  if (typeof value !== "object" || value === null) {
    throw new FarmersRequestError("unexpected", "Farmer details could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.plot_identifier !== "string" ||
    typeof entry.barangay !== "string" ||
    typeof entry.area_hectares !== "number" ||
    !Number.isFinite(entry.area_hectares)
  ) {
    throw new FarmersRequestError("unexpected", "Farmer details could not be read.");
  }
  return {
    id: entry.id,
    plot_identifier: entry.plot_identifier,
    barangay: entry.barangay,
    area_hectares: entry.area_hectares,
  };
}

function parseFarmerDetail(value: unknown): FarmerDetail {
  if (typeof value !== "object" || value === null) {
    throw new FarmersRequestError("unexpected", "Farmer details could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.full_name !== "string" ||
    typeof entry.barangay !== "string" ||
    (entry.contact_number !== null && typeof entry.contact_number !== "string") ||
    !Array.isArray(entry.farms) ||
    (entry.created_at !== null && typeof entry.created_at !== "string") ||
    (entry.updated_at !== null && typeof entry.updated_at !== "string")
  ) {
    throw new FarmersRequestError("unexpected", "Farmer details could not be read.");
  }
  return {
    id: entry.id,
    full_name: entry.full_name,
    barangay: entry.barangay,
    contact_number: entry.contact_number,
    farms: entry.farms.map(parseFarmRef),
    created_at: entry.created_at,
    updated_at: entry.updated_at,
  };
}

function parseFarmerList(payload: unknown): FarmerSummary[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FarmersRequestError("unexpected", "Farmer list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("farmers" in data)) {
    throw new FarmersRequestError("unexpected", "Farmer list could not be read.");
  }
  const farmers = (data as { farmers: unknown }).farmers;
  if (!Array.isArray(farmers)) {
    throw new FarmersRequestError("unexpected", "Farmer list could not be read.");
  }
  return farmers.map(parseFarmerSummary);
}

function parseSingleFarmer(payload: unknown, fallback: string): FarmerDetail {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FarmersRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("farmer" in data)) {
    throw new FarmersRequestError("unexpected", fallback);
  }
  const farmer = (data as { farmer: unknown }).farmer;
  if (
    typeof farmer !== "object" ||
    farmer === null ||
    !("farms" in (farmer as Record<string, unknown>))
  ) {
    // Create responses carry a summary shape; upgrade it to a detail shape.
    const summary = parseFarmerSummary(farmer);
    return {
      ...summary,
      farms: [],
      created_at: null,
      updated_at: null,
    };
  }
  return parseFarmerDetail(farmer);
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new FarmersRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new FarmersRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new FarmersRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to manage farmers."),
    );
  }
  if (status === 404) {
    throw new FarmersRequestError("not_found", serverMessage(payload, "Farmer was not found."));
  }
  if (status === 409) {
    throw new FarmersRequestError("conflict", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new FarmersRequestError(
      "unavailable",
      serverMessage(payload, "Farmer service is unavailable."),
    );
  }
  throw new FarmersRequestError("unexpected", serverMessage(payload, fallback));
}

export async function listFarmers(): Promise<FarmerSummary[]> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/farmers", {
      cache: "no-store",
    });
  } catch {
    throw new FarmersRequestError("unavailable", "Farmer service is unavailable.");
  }
  if (response.status === 200) {
    return parseFarmerList(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response), "Farmer list could not be read.");
}

export type CreateFarmerInput = {
  full_name: string;
  barangay: string;
  contact_number?: string | null;
};

export async function createFarmer(
  input: CreateFarmerInput,
  csrfToken: string,
): Promise<FarmerDetail> {
  const body: Record<string, unknown> = {
    full_name: input.full_name,
    barangay: input.barangay,
  };
  if (input.contact_number !== undefined && input.contact_number !== null && input.contact_number !== "") {
    body.contact_number = input.contact_number;
  }
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/farmers", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(body),
    });
  } catch {
    throw new FarmersRequestError("unavailable", "Farmer service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingleFarmer(await readPayload(response), "Farmer could not be created.");
  }
  throwForStatus(response.status, await readPayload(response), "Farmer could not be created.");
}

export type UpdateFarmerInput = {
  full_name?: string;
  barangay?: string;
  contact_number?: string | null;
};

export async function updateFarmer(
  farmerId: number,
  input: UpdateFarmerInput,
  csrfToken: string,
): Promise<FarmerDetail> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/farmers/${farmerId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new FarmersRequestError("unavailable", "Farmer service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingleFarmer(await readPayload(response), "Farmer could not be updated.");
  }
  throwForStatus(response.status, await readPayload(response), "Farmer could not be updated.");
}
