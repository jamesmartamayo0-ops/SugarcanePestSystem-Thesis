import { authenticatedFetch } from "./api.ts";
import type { PestCaseStatus } from "./pest-cases.ts";

export type FarmMarkerState = PestCaseStatus | "REGISTERED_NO_CASE";
export type FarmMapFilter = "ALL" | "ACTIVE" | "NEEDS_ATTENTION" | "TERMINAL";

export type FarmMapSummary = {
  mapped_farms: number;
  unmapped_farms: number;
  active_cases: number;
  needs_attention_cases: number;
};

export type FarmMapCase = {
  id: number;
  pest_name: string;
  status: PestCaseStatus;
  reported_area_hectares: number;
  validated_area_hectares: number | null;
  updated_at: string | null;
};

export type FarmMapFarm = {
  id: number;
  plot_identifier: string;
  farmer: { id: number; full_name: string };
  barangay: string;
  area_hectares: number;
  location: { latitude: number; longitude: number } | null;
  marker_state: FarmMarkerState;
  has_active_case: boolean;
  needs_attention: boolean;
  case: FarmMapCase | null;
};

export type FarmMapProjection = {
  summary: FarmMapSummary;
  farms: FarmMapFarm[];
};

export type MarkerPresentation = {
  label: string;
  legendLabel: string;
  color: string;
};

const CASE_STATUSES: PestCaseStatus[] = [
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

const MARKER_STATES: FarmMarkerState[] = ["REGISTERED_NO_CASE", ...CASE_STATUSES];

const PRESENTATION: Record<FarmMarkerState, MarkerPresentation> = {
  REGISTERED_NO_CASE: {
    label: "Registered — no case",
    legendLabel: "Registered / no case",
    color: "#64748b",
  },
  REPORTED: { label: "Reported", legendLabel: "Reporting / inspection", color: "#2563a6" },
  FOR_INSPECTION: {
    label: "For Inspection",
    legendLabel: "Reporting / inspection",
    color: "#2563a6",
  },
  INSPECTION_SCHEDULED: {
    label: "Inspection Scheduled",
    legendLabel: "Reporting / inspection",
    color: "#2563a6",
  },
  FIELD_VALIDATED: {
    label: "Field Validated",
    legendLabel: "Field validated",
    color: "#b42318",
  },
  UNDER_INTERVENTION: {
    label: "Under Intervention",
    legendLabel: "Intervention / follow-up",
    color: "#c45d05",
  },
  FOLLOW_UP_DUE: {
    label: "Follow-up Due",
    legendLabel: "Intervention / follow-up",
    color: "#c45d05",
  },
  REINTERVENTION_REQUIRED: {
    label: "Reintervention Required",
    legendLabel: "Reintervention required",
    color: "#7f1d1d",
  },
  NOT_CONFIRMED: {
    label: "Not Confirmed",
    legendLabel: "Not confirmed",
    color: "#8a929a",
  },
  CLOSED: { label: "Closed", legendLabel: "Closed", color: "#2f6f44" },
};

export const FARM_MAP_LEGEND: MarkerPresentation[] = [
  PRESENTATION.REGISTERED_NO_CASE,
  PRESENTATION.REPORTED,
  PRESENTATION.FIELD_VALIDATED,
  PRESENTATION.UNDER_INTERVENTION,
  PRESENTATION.REINTERVENTION_REQUIRED,
  PRESENTATION.NOT_CONFIRMED,
  PRESENTATION.CLOSED,
];

export class FarmMapRequestError extends Error {
  public readonly kind: "unauthenticated" | "forbidden" | "unavailable" | "unexpected";

  constructor(
    kind: "unauthenticated" | "forbidden" | "unavailable" | "unexpected",
    message: string,
  ) {
    super(message);
    this.name = "FarmMapRequestError";
    this.kind = kind;
  }
}

export function markerPresentation(state: FarmMarkerState): MarkerPresentation {
  return PRESENTATION[state];
}

export function farmMatchesFilter(farm: FarmMapFarm, filter: FarmMapFilter): boolean {
  if (filter === "ACTIVE") {
    return farm.has_active_case;
  }
  if (filter === "NEEDS_ATTENTION") {
    return farm.needs_attention;
  }
  if (filter === "TERMINAL") {
    return farm.marker_state === "CLOSED" || farm.marker_state === "NOT_CONFIRMED";
  }
  return true;
}

export function farmsForMap(
  farms: FarmMapFarm[],
  filter: FarmMapFilter = "ALL",
): FarmMapFarm[] {
  return farms.filter(
    (farm) => farm.location !== null && farmMatchesFilter(farm, filter),
  );
}

export function formatArea(value: number | null): string {
  return value === null || !Number.isFinite(value) ? "Not available" : `${value.toFixed(2)} ha`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function isCount(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isCaseStatus(value: unknown): value is PestCaseStatus {
  return CASE_STATUSES.includes(value as PestCaseStatus);
}

function isMarkerState(value: unknown): value is FarmMarkerState {
  return MARKER_STATES.includes(value as FarmMarkerState);
}

function invalidContract(): never {
  throw new FarmMapRequestError("unexpected", "Farm monitoring map data could not be read.");
}

function parseCase(value: unknown): FarmMapCase | null {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    return invalidContract();
  }
  if (
    !isId(value.id) ||
    typeof value.pest_name !== "string" ||
    !isCaseStatus(value.status) ||
    !isNumber(value.reported_area_hectares) ||
    (value.validated_area_hectares !== null && !isNumber(value.validated_area_hectares)) ||
    (value.updated_at !== null && typeof value.updated_at !== "string")
  ) {
    return invalidContract();
  }
  return {
    id: value.id,
    pest_name: value.pest_name,
    status: value.status,
    reported_area_hectares: value.reported_area_hectares,
    validated_area_hectares: value.validated_area_hectares,
    updated_at: value.updated_at,
  };
}

function parseFarm(value: unknown): FarmMapFarm {
  if (!isRecord(value) || !isRecord(value.farmer)) {
    return invalidContract();
  }
  const location = value.location;
  if (
    !isId(value.id) ||
    typeof value.plot_identifier !== "string" ||
    !isId(value.farmer.id) ||
    typeof value.farmer.full_name !== "string" ||
    typeof value.barangay !== "string" ||
    !isNumber(value.area_hectares) ||
    !isMarkerState(value.marker_state) ||
    typeof value.has_active_case !== "boolean" ||
    typeof value.needs_attention !== "boolean"
  ) {
    return invalidContract();
  }
  let parsedLocation: FarmMapFarm["location"] = null;
  if (location !== null) {
    if (
      !isRecord(location) ||
      !isNumber(location.latitude) ||
      location.latitude < -90 ||
      location.latitude > 90 ||
      !isNumber(location.longitude) ||
      location.longitude < -180 ||
      location.longitude > 180
    ) {
      return invalidContract();
    }
    parsedLocation = {
      latitude: location.latitude,
      longitude: location.longitude,
    };
  }
  return {
    id: value.id,
    plot_identifier: value.plot_identifier,
    farmer: { id: value.farmer.id, full_name: value.farmer.full_name },
    barangay: value.barangay,
    area_hectares: value.area_hectares,
    location: parsedLocation,
    marker_state: value.marker_state,
    has_active_case: value.has_active_case,
    needs_attention: value.needs_attention,
    case: parseCase(value.case),
  };
}

function parseProjection(value: unknown): FarmMapProjection {
  if (!isRecord(value) || !isRecord(value.data)) {
    return invalidContract();
  }
  const summary = value.data.summary;
  const farms = value.data.farms;
  if (
    !isRecord(summary) ||
    !isCount(summary.mapped_farms) ||
    !isCount(summary.unmapped_farms) ||
    !isCount(summary.active_cases) ||
    !isCount(summary.needs_attention_cases) ||
    !Array.isArray(farms)
  ) {
    return invalidContract();
  }
  return {
    summary: {
      mapped_farms: summary.mapped_farms,
      unmapped_farms: summary.unmapped_farms,
      active_cases: summary.active_cases,
      needs_attention_cases: summary.needs_attention_cases,
    },
    farms: farms.map(parseFarm),
  };
}

async function readPayload(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function serverMessage(value: unknown, fallback: string): string {
  if (isRecord(value) && typeof value.message === "string" && value.message.length <= 500) {
    return value.message || fallback;
  }
  return fallback;
}

export async function getFarmMap(): Promise<FarmMapProjection> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/dashboard/farm-map", {
      cache: "no-store",
    });
  } catch {
    throw new FarmMapRequestError(
      "unavailable",
      "Farm monitoring map service is unavailable.",
    );
  }
  const payload = await readPayload(response);
  if (response.status === 200) {
    return parseProjection(payload);
  }
  if (response.status === 401) {
    throw new FarmMapRequestError("unauthenticated", "Your session has expired.");
  }
  if (response.status === 403) {
    throw new FarmMapRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to view the farm monitoring map."),
    );
  }
  if (response.status === 503) {
    throw new FarmMapRequestError(
      "unavailable",
      serverMessage(payload, "Farm monitoring map service is unavailable."),
    );
  }
  throw new FarmMapRequestError(
    "unexpected",
    serverMessage(payload, "Farm monitoring map data could not be read."),
  );
}
