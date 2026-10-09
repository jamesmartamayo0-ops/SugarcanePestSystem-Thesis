import { authenticatedFetch } from "@/lib/api";
import { parsePestCaseDetail, type PestCaseDetail, type PestCaseStatus } from "@/lib/pest-cases";

export type TimelineCategory = "CASE" | "INSPECTION" | "INTERVENTION" | "FOLLOW_UP" | "CLOSURE";

export type TimelineActor = {
  id: number;
  username: string;
  full_name: string;
} | null;

export type TimelineEvent = {
  event_type: string;
  category: TimelineCategory;
  title: string;
  description: string;
  occurred_at: string | null;
  event_date: string | null;
  actor: TimelineActor;
  cycle: number | null;
  metadata: Record<string, unknown>;
};

export type CaseTimeline = {
  pest_case: PestCaseDetail;
  timeline: TimelineEvent[];
};

export type TimelineErrorKind =
  | "invalid"
  | "unauthenticated"
  | "forbidden"
  | "not_found"
  | "unavailable"
  | "unexpected";

export class TimelineRequestError extends Error {
  constructor(
    public readonly kind: TimelineErrorKind,
    message: string,
  ) {
    super(message);
    this.name = "TimelineRequestError";
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

function isCategory(value: unknown): value is TimelineCategory {
  return (
    value === "CASE" ||
    value === "INSPECTION" ||
    value === "INTERVENTION" ||
    value === "FOLLOW_UP" ||
    value === "CLOSURE"
  );
}

function parseActor(value: unknown): TimelineActor {
  if (value === null) {
    return null;
  }
  if (typeof value !== "object" || value === null) {
    throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.id !== "number" ||
    typeof entry.username !== "string" ||
    typeof entry.full_name !== "string"
  ) {
    throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
  }
  return { id: entry.id, username: entry.username, full_name: entry.full_name };
}

function parseEvent(value: unknown): TimelineEvent {
  if (typeof value !== "object" || value === null) {
    throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
  }
  const entry = value as Record<string, unknown>;
  if (
    typeof entry.event_type !== "string" ||
    !isCategory(entry.category) ||
    typeof entry.title !== "string" ||
    typeof entry.description !== "string" ||
    (entry.occurred_at !== null && typeof entry.occurred_at !== "string") ||
    (entry.event_date !== null && typeof entry.event_date !== "string") ||
    (entry.cycle !== null && typeof entry.cycle !== "number") ||
    typeof entry.metadata !== "object" ||
    entry.metadata === null
  ) {
    throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
  }
  return {
    event_type: entry.event_type,
    category: entry.category,
    title: entry.title,
    description: entry.description,
    occurred_at: entry.occurred_at,
    event_date: entry.event_date,
    actor: parseActor(entry.actor),
    cycle: entry.cycle,
    metadata: entry.metadata as Record<string, unknown>,
  };
}

function throwForStatus(status: number, payload: unknown, fallback: string): never {
  if (status === 400) {
    throw new TimelineRequestError("invalid", serverMessage(payload, fallback));
  }
  if (status === 401) {
    throw new TimelineRequestError("unauthenticated", "Your session has expired.");
  }
  if (status === 403) {
    throw new TimelineRequestError(
      "forbidden",
      serverMessage(payload, "You do not have permission to view case timelines."),
    );
  }
  if (status === 404) {
    throw new TimelineRequestError("not_found", serverMessage(payload, fallback));
  }
  if (status === 503) {
    throw new TimelineRequestError(
      "unavailable",
      serverMessage(payload, "Timeline service is unavailable."),
    );
  }
  throw new TimelineRequestError("unexpected", serverMessage(payload, fallback));
}

export async function getCaseTimeline(caseId: number): Promise<CaseTimeline> {
  let response: Response;
  try {
    response = await authenticatedFetch(`/api/v1/pest-cases/${caseId}/timeline`, {
      cache: "no-store",
    });
  } catch {
    throw new TimelineRequestError("unavailable", "Timeline service is unavailable.");
  }
  if (response.status === 200) {
    const payload = await readPayload(response);
    if (
      typeof payload !== "object" ||
      payload === null ||
      !("data" in payload) ||
      typeof (payload as { data: unknown }).data !== "object"
    ) {
      throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
    }
    const data = (payload as { data: { pest_case: unknown; timeline: unknown } }).data;
    if (!Array.isArray(data.timeline)) {
      throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
    }
    let pestCase: PestCaseDetail;
    try {
      pestCase = parsePestCaseDetail(data.pest_case);
    } catch {
      throw new TimelineRequestError("unexpected", "Case timeline could not be read.");
    }
    const timeline = (data.timeline as unknown[]).map(parseEvent);
    return { pest_case: pestCase, timeline };
  }
  throwForStatus(response.status, await readPayload(response), "Case timeline could not be read.");
}

export type { PestCaseStatus };
