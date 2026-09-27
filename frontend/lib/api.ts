export type ConnectionStatus = "connected" | "unavailable";

export type HealthResponse = {
  data: {
    service: "sugarcane-pest-api";
    backend: ConnectionStatus;
    database: ConnectionStatus;
  };
  message: string;
};

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  "http://127.0.0.1:5000/api/v1";

function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null || !("data" in value)) {
    return false;
  }

  const data = value.data;
  if (typeof data !== "object" || data === null) {
    return false;
  }

  const health = data as Record<string, unknown>;
  return (
    health.service === "sugarcane-pest-api" &&
    (health.backend === "connected" || health.backend === "unavailable") &&
    (health.database === "connected" || health.database === "unavailable") &&
    "message" in value &&
    typeof value.message === "string"
  );
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl.replace(/\/+$/, "")}/health`, {
    cache: "no-store",
    credentials: "omit",
    signal,
  });

  if (response.status !== 200 && response.status !== 503) {
    throw new Error("Health service returned an unexpected status.");
  }

  const payload: unknown = await response.json();
  if (!isHealthResponse(payload)) {
    throw new Error("Health service returned an invalid response.");
  }

  return payload;
}
