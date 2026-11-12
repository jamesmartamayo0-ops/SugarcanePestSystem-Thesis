import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";
import { NextResponse } from "next/server";

import { isEvidenceObjectKeyForCase } from "@/lib/evidence-object";

export const runtime = "nodejs";

const CONTENT_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_BYTES = 5 * 1024 * 1024;

function backendOrigin(): string | null {
  const value = process.env.BACKEND_API_URL?.trim();
  if (!value) {
    return null;
  }
  try {
    const parsed = new URL(value);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      parsed.username ||
      parsed.password ||
      parsed.pathname !== "/" ||
      parsed.search ||
      parsed.hash
    ) {
      return null;
    }
    return parsed.origin;
  } catch {
    return null;
  }
}

export async function POST(request: Request): Promise<NextResponse> {
  const backend = backendOrigin();
  if (backend === null) {
    return NextResponse.json(
      { error: "Evidence upload is not configured." },
      { status: 503 },
    );
  }

  const cookie = request.headers.get("cookie");
  const csrfToken = request.headers.get("x-csrf-token");
  if (!cookie || !csrfToken || csrfToken.length > 128) {
    return NextResponse.json(
      { error: "Authentication is required." },
      { status: 401 },
    );
  }

  let body: HandleUploadBody;
  try {
    body = (await request.json()) as HandleUploadBody;
  } catch {
    return NextResponse.json({ error: "Invalid upload request." }, { status: 400 });
  }

  if (body.type === "blob.upload-completed") {
    return NextResponse.json({ success: true });
  }

  const clientPayload =
    body.type === "blob.generate-client-token" ? body.payload.clientPayload : null;
  const caseId = (() => {
    if (typeof clientPayload !== "string") {
      return null;
    }
    try {
      const parsed = JSON.parse(clientPayload) as { caseId?: unknown };
      return typeof parsed.caseId === "number" &&
        Number.isSafeInteger(parsed.caseId) &&
        parsed.caseId > 0
        ? parsed.caseId
        : null;
    } catch {
      return null;
    }
  })();
  if (caseId === null) {
    return NextResponse.json({ error: "Invalid upload request." }, { status: 400 });
  }

  const origin = request.headers.get("origin") ?? new URL(request.url).origin;
  try {
    const authorization = await fetch(
      `${backend}/api/v1/pest-cases/${caseId}/evidence-photos/upload-authorize`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          Origin: origin,
          Cookie: cookie,
        },
        body: "{}",
        cache: "no-store",
      },
    );
    if (!authorization.ok) {
      return NextResponse.json(
        { error: "Evidence upload is not authorized." },
        {
          status:
            authorization.status === 401
              ? 401
              : authorization.status === 404
                ? 404
                : authorization.status === 409
                  ? 409
                  : 403,
        },
      );
    }
  } catch {
    return NextResponse.json(
      { error: "Evidence upload is unavailable." },
      { status: 503 },
    );
  }

  try {
    const jsonResponse = await handleUpload({
      body,
      request,
      onBeforeGenerateToken: async (pathname) => {
        if (!isEvidenceObjectKeyForCase(pathname, caseId)) {
          throw new Error("Invalid evidence object name.");
        }
        return {
          allowedContentTypes: CONTENT_TYPES,
          maximumSizeInBytes: MAX_BYTES,
          addRandomSuffix: false,
          allowOverwrite: false,
          tokenPayload: JSON.stringify({ caseId }),
        };
      },
      onUploadCompleted: async () => {},
    });
    return NextResponse.json(jsonResponse);
  } catch {
    return NextResponse.json(
      { error: "Evidence upload could not be authorized." },
      { status: 400 },
    );
  }
}
