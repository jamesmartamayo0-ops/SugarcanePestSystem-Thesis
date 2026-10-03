export type UserRole = "ADMIN" | "TECHNICIAN";

export type AuthUser = {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
};

export type AuthSession = {
  user: AuthUser;
  csrfToken: string;
};

export type AuthErrorKind =
  | "invalid_credentials"
  | "unauthenticated"
  | "forbidden"
  | "unavailable"
  | "unexpected";

export class AuthRequestError extends Error {
  constructor(public readonly kind: AuthErrorKind) {
    super("Authentication request failed.");
    this.name = "AuthRequestError";
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch("/api/v1/auth" + path, {
      ...init,
      cache: "no-store",
      credentials: "include",
    });
  } catch {
    throw new AuthRequestError("unavailable");
  }
}

function parseSession(value: unknown): AuthSession {
  if (typeof value !== "object" || value === null || !("data" in value)) {
    throw new AuthRequestError("unexpected");
  }

  const data = value.data;
  if (typeof data !== "object" || data === null || !("user" in data) || !("csrf_token" in data)) {
    throw new AuthRequestError("unexpected");
  }

  const user = data.user;
  const token = data.csrf_token;
  if (
    typeof user !== "object" ||
    user === null ||
    !("id" in user) ||
    !("username" in user) ||
    !("full_name" in user) ||
    !("role" in user) ||
    typeof user.id !== "number" ||
    !Number.isSafeInteger(user.id) ||
    user.id <= 0 ||
    typeof user.username !== "string" ||
    typeof user.full_name !== "string" ||
    (user.role !== "ADMIN" && user.role !== "TECHNICIAN") ||
    typeof token !== "string" ||
    !/^[0-9a-f]{64}$/.test(token)
  ) {
    throw new AuthRequestError("unexpected");
  }

  return {
    user: {
      id: user.id,
      username: user.username,
      full_name: user.full_name,
      role: user.role,
    },
    csrfToken: token,
  };
}

async function sessionResponse(response: Response): Promise<AuthSession> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new AuthRequestError("unexpected");
  }
  return parseSession(payload);
}

export async function login(username: string, password: string): Promise<AuthSession> {
  const response = await request("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (response.status === 401) {
    throw new AuthRequestError("invalid_credentials");
  }
  if (response.status === 503) {
    throw new AuthRequestError("unavailable");
  }
  if (!response.ok) {
    throw new AuthRequestError("unexpected");
  }
  return sessionResponse(response);
}

export async function getCurrentUser(signal?: AbortSignal): Promise<AuthSession | null> {
  const response = await request("/me", { signal });

  if (response.status === 401) {
    return null;
  }
  if (response.status === 503) {
    throw new AuthRequestError("unavailable");
  }
  if (!response.ok) {
    throw new AuthRequestError("unexpected");
  }
  return sessionResponse(response);
}

export async function logout(csrfToken: string): Promise<void> {
  const response = await request("/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });

  if (response.status === 204) {
    return;
  }
  if (response.status === 401) {
    throw new AuthRequestError("unauthenticated");
  }
  if (response.status === 403) {
    throw new AuthRequestError("forbidden");
  }
  if (response.status === 503) {
    throw new AuthRequestError("unavailable");
  }
  throw new AuthRequestError("unexpected");
}
