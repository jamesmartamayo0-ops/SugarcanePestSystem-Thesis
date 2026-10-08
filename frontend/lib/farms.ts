import { authenticatedFetch } from "@/lib/api";

export type FarmFarmerRef = {
  id: number;
  full_name: string;
  barangay: string;
};

export type FarmWithFarmer = {
  id: number;
  farmer_id: number;
  plot_identifier: string;
  barangay: string;
  area_hectares: number;
  farmer: FarmFarmerRef;
  created_at: string | null;
  updated_at: string | null;
};

export type FarmsErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class FarmsRequestError extends Error {
  constructor(
    public readonly kind: FarmsErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "FarmsRequestError";
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

function parseFarmerRef(value: unknown): FarmFarmerRef {
  if (typeof value !== "object" || value === null) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.full_name !== "string" ||
    typeof entry.barangay !== "string"
  ) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  return {
    id: entry.id,
    full_name: entry.full_name,
    barangay: entry.barangay,
  };
}

function parseFarm(value: unknown): FarmWithFarmer {
  if (typeof value !== "object" || value === null) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.farmer_id !== "number" ||
    !Number.isSafeInteger(entry.farmer_id) ||
    entry.farmer_id <= 0 ||
    typeof entry.plot_identifier !== "string" ||
    typeof entry.barangay !== "string" ||
    typeof entry.area_hectares !== "number" ||
    !Number.isFinite(entry.area_hectares) ||
    (entry.created_at !== null && typeof entry.created_at !== "string") ||
    (entry.updated_at !== null && typeof entry.updated_at !== "string")
  ) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  return {
    id: entry.id,
    farmer_id: entry.farmer_id,
    plot_identifier: entry.plot_identifier,
    barangay: entry.barangay,
    area_hectares: entry.area_hectares,
    farmer: parseFarmerRef(entry.farmer),
    created_at: entry.created_at,
    updated_at: entry.updated_at,
  };
}

function parseFarmList(payload: unknown): FarmWithFarmer[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("farms" in data)) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  const farms = (data as { farms: unknown }).farms;
  if (!Array.isArray(farms)) {
    throw new FarmsRequestError("unexpected", "Farm list could not be read.");
  }
  return farms.map(parseFarm);
}

function parseSingleFarm(payload: unknown, fallback: string): FarmWithFarmer {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new FarmsRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("farm" in data)) {
    throw new FarmsRequestError("unexpected", fallback);
  }
  return parseFarm((data as { farm: unknown }).farm);
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new FarmsRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new FarmsRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new FarmsRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to manage farms."),
    );
  }
  if (status === 404) {
    throw new FarmsRequestError("not_found", serverMessage(payload, "Farm was not found."));
  }
  if (status === 409) {
    throw new FarmsRequestError("conflict", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new FarmsRequestError(
      "unavailable",
      serverMessage(payload, "Farm service is unavailable."),
    );
  }
  throw new FarmsRequestError("unexpected", serverMessage(payload, fallback));
}

export async function listFarms(farmerId?: number): Promise<FarmWithFarmer[]> {
  const path =
    farmerId === undefined
      ? "/api/v1/farms"
      : `/api/v1/farms?farmer_id=${encodeURIComponent(String(farmerId))}`;
  let response: Response;
  try {
    response = await authenticatedFetch(path, {
      cache: "no-store",
    });
  } catch {
    throw new FarmsRequestError("unavailable", "Farm service is unavailable.");
  }
  if (response.status === 200) {
    return parseFarmList(await readPayload(response));
  }
  throwForStatus(response.status, await readPayload(response), "Farm list could not be read.");
}

export type CreateFarmInput = {
  farmer_id: number;
  plot_identifier: string;
  barangay: string;
  area_hectares: number;
};

export async function createFarm(
  input: CreateFarmInput,
  csrfToken: string,
): Promise<FarmWithFarmer> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/farms", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new FarmsRequestError("unavailable", "Farm service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingleFarm(await readPayload(response), "Farm could not be created.");
  }
  throwForStatus(response.status, await readPayload(response), "Farm could not be created.");
}

export type UpdateFarmInput = {
  plot_identifier?: string;
  barangay?: string;
  area_hectares?: number;
};

export async function updateFarm(
  farmId: number,
  input: UpdateFarmInput,
  csrfToken: string,
): Promise<FarmWithFarmer> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/farms/${farmId}`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new FarmsRequestError("unavailable", "Farm service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingleFarm(await readPayload(response), "Farm could not be updated.");
  }
  throwForStatus(response.status, await readPayload(response), "Farm could not be updated.");
}
