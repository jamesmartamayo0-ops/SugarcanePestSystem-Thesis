import { authenticatedFetch } from "@/lib/api";
import type { UserRole } from "@/lib/auth";

export type ManagedUser = {
  id: number;
  username: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
};

export type UsersErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unavailable"
  | "unexpected";

export class UsersRequestError extends Error {
  constructor(
    public readonly kind: UsersErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "UsersRequestError";
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

function parseManagedUser(value: unknown): ManagedUser {
  if (typeof value !== "object" || value === null) {
    throw new UsersRequestError("unexpected", "Staff list could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    !Number.isSafeInteger(entry.id) ||
    entry.id <= 0 ||
    typeof entry.username !== "string" ||
    typeof entry.full_name !== "string" ||
    (entry.role !== "ADMIN" && entry.role !== "TECHNICIAN") ||
    typeof entry.is_active !== "boolean"
  ) {
    throw new UsersRequestError("unexpected", "Staff list could not be read.");
  }
  return {
    id: entry.id,
    username: entry.username,
    full_name: entry.full_name,
    role: entry.role,
    is_active: entry.is_active,
  };
}

function parseUserList(payload: unknown): ManagedUser[] {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new UsersRequestError("unexpected", "Staff list could not be read.");
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("users" in data)) {
    throw new UsersRequestError("unexpected", "Staff list could not be read.");
  }
  const users = (data as { users: unknown }).users;
  if (!Array.isArray(users)) {
    throw new UsersRequestError("unexpected", "Staff list could not be read.");
  }
  return users.map(parseManagedUser);
}

function parseSingleUser(payload: unknown, fallback: string): ManagedUser {
  if (typeof payload !== "object" || payload === null || !("data" in payload)) {
    throw new UsersRequestError("unexpected", fallback);
  }
  const data = (payload as { data: unknown }).data;
  if (typeof data !== "object" || data === null || !("user" in data)) {
    throw new UsersRequestError("unexpected", fallback);
  }
  return parseManagedUser((data as { user: unknown }).user);
}

export async function listUsers(): Promise<ManagedUser[]> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/admin/users", {
      cache: "no-store",
    });
  } catch {
    throw new UsersRequestError("unavailable", "Staff service is unavailable.");
  }
  if (response.status === 200) {
    return parseUserList(await readPayload(response));
  }
  const payload = await readPayload(response);
  if (response.status === 401) {
    throw new UsersRequestError("unauthenticated", "Your session has expired.");
  }
  if (response.status === 403) {
    throw new UsersRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to manage staff."),
    );
  }
  if (response.status === 503) {
    throw new UsersRequestError(
      "unavailable",
      serverMessage(payload, "Staff service is unavailable."),
    );
  }
  throw new UsersRequestError("unexpected", serverMessage(payload, "Staff list could not be read."));
}

export type CreateUserInput = {
  username: string;
  full_name: string;
  password: string;
  role: UserRole;
};

export async function createUser(
  input: CreateUserInput,
  csrfToken: string,
): Promise<ManagedUser> {
  let response: Response;
  try {
    response = await authenticatedFetch("/api/v1/admin/users", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(input),
    });
  } catch {
    throw new UsersRequestError("unavailable", "Staff service is unavailable.");
  }
  if (response.status === 201) {
    return parseSingleUser(await readPayload(response), "Staff account could not be created.");
  }
  const payload = await readPayload(response);
  if (response.status === 400) {
    throw new UsersRequestError("invalid", serverMessage(payload, "Staff details are invalid."));
  }
  if (response.status === 401) {
    throw new UsersRequestError("unauthenticated", "Your session has expired.");
  }
  if (response.status === 403) {
    throw new UsersRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to manage staff."),
    );
  }
  if (response.status === 409) {
    throw new UsersRequestError("conflict", serverMessage(payload, "Staff account could not be created."));
  }
  if (response.status === 503) {
    throw new UsersRequestError(
      "unavailable",
      serverMessage(payload, "Staff service is unavailable."),
    );
  }
  throw new UsersRequestError("unexpected", serverMessage(payload, "Staff account could not be created."));
}

export async function setUserActive(
  userId: number,
  isActive: boolean,
  csrfToken: string,
): Promise<ManagedUser> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/admin/users/${userId}/status`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify({ is_active: isActive }),
    });
  } catch {
    throw new UsersRequestError("unavailable", "Staff service is unavailable.");
  }
  if (response.status === 200) {
    return parseSingleUser(await readPayload(response), "Account status could not be updated.");
  }
  const payload = await readPayload(response);
  if (response.status === 400) {
    throw new UsersRequestError("invalid", serverMessage(payload, "Status update is invalid."));
  }
  if (response.status === 401) {
    throw new UsersRequestError("unauthenticated", "Your session has expired.");
  }
  if (response.status === 403) {
    throw new UsersRequestError(
      "forbidden",
      serverMessage(payload, "This status change is not allowed."),
    );
  }
  if (response.status === 404) {
    throw new UsersRequestError("not_found", serverMessage(payload, "Staff account was not found."));
  }
  if (response.status === 409) {
    throw new UsersRequestError("conflict", serverMessage(payload, "This status change is not allowed."));
  }
  if (response.status === 503) {
    throw new UsersRequestError(
      "unavailable",
      serverMessage(payload, "Staff service is unavailable."),
    );
  }
  throw new UsersRequestError("unexpected", serverMessage(payload, "Account status could not be updated."));
}
