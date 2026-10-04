export type ConnectionStatus = "connected" | "unavailable";

let authSessionVersion = 0;
const sessionExpiredListeners = new Set<() => void>();

export function getAuthSessionVersion(): number {
  return authSessionVersion;
}

export function advanceAuthSessionVersion(): void {
  authSessionVersion += 1;
}

export function onSessionExpired(listener: () => void): () => void {
  sessionExpiredListeners.add(listener);
  return () => sessionExpiredListeners.delete(listener);
}

export async function authenticatedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const requestVersion = authSessionVersion;
  const response = await fetch(path, {
    ...init,
    credentials: "include",
  });

  if (response.status === 401 && requestVersion === authSessionVersion) {
    advanceAuthSessionVersion();
    sessionExpiredListeners.forEach((listener) => listener());
  }

  return response;
}

export type HealthResponse = {
  data: {
    service: "sugarcane-pest-api";
    backend: ConnectionStatus;
    database: ConnectionStatus;
  };
  message: string;
};

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
  const response = await fetch("/api/v1/health", {
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
