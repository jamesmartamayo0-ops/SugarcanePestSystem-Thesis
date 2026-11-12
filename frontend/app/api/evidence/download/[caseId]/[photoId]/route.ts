import { issueSignedToken, presignUrl } from "@vercel/blob";
import { NextResponse } from "next/server";

import { isEvidenceObjectKeyForCase } from "@/lib/evidence-object";

export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ caseId: string; photoId: string }>;
};

type AuthorizationData = {
  storage?: unknown;
  pathname?: unknown;
  content_type?: unknown;
  original_filename?: unknown;
};

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

function positiveInteger(value: string): number | null {
  if (!/^[1-9][0-9]*$/.test(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed <= 2_147_483_647 ? parsed : null;
}

export async function GET(
  request: Request,
  context: RouteContext,
): Promise<NextResponse | Response> {
  const backend = backendOrigin();
  const { caseId: rawCaseId, photoId: rawPhotoId } = await context.params;
  const caseId = positiveInteger(rawCaseId);
  const photoId = positiveInteger(rawPhotoId);
  if (backend === null) {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }
  if (caseId === null || photoId === null) {
    return NextResponse.json(
      { error: "Evidence photo not found." },
      { status: 404 },
    );
  }

  const cookie = request.headers.get("cookie");
  if (!cookie) {
    return NextResponse.json(
      { error: "Authentication is required." },
      { status: 401 },
    );
  }

  let authorization: Response;
  try {
    authorization = await fetch(
      `${backend}/api/v1/pest-cases/${caseId}/evidence-photos/${photoId}/authorize-download`,
      {
        headers: { Cookie: cookie },
        cache: "no-store",
      },
    );
  } catch {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }
  if (!authorization.ok) {
    return NextResponse.json(
      { error: "Evidence photo not found." },
      {
        status:
          authorization.status === 401 || authorization.status === 403
            ? authorization.status
            : 404,
      },
    );
  }

  let data: AuthorizationData;
  try {
    const payload = (await authorization.json()) as { data?: unknown };
    data =
      typeof payload.data === "object" && payload.data !== null
        ? (payload.data as AuthorizationData)
        : {};
  } catch {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }

  if (
    data.storage !== "local" &&
    data.storage !== "blob"
  ) {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }
  if (typeof data.pathname !== "string" || data.pathname.length === 0) {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }
  if (
    data.storage === "blob" &&
    !isEvidenceObjectKeyForCase(data.pathname, caseId)
  ) {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }

  if (data.storage === "local") {
    let upstream: Response;
    try {
      upstream = await fetch(
        `${backend}/api/v1/pest-cases/${caseId}/evidence-photos/${photoId}`,
        {
          headers: { Cookie: cookie },
          cache: "no-store",
        },
      );
    } catch {
      return NextResponse.json(
        { error: "Evidence photo is unavailable." },
        { status: 503 },
      );
    }
    if (!upstream.ok) {
      return NextResponse.json(
        { error: "Evidence photo not found." },
        {
          status:
            upstream.status === 401 ||
            upstream.status === 403 ||
            upstream.status === 404
              ? upstream.status
              : 503,
        },
      );
    }
    const headers = new Headers();
    const contentType = upstream.headers.get("content-type");
    const contentDisposition = upstream.headers.get("content-disposition");
    if (contentType) {
      headers.set("Content-Type", contentType);
    }
    if (contentDisposition) {
      headers.set("Content-Disposition", contentDisposition);
    }
    headers.set("Cache-Control", "no-store");
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(upstream.body, { status: 200, headers });
  }

  try {
    const token = await issueSignedToken({
      pathname: data.pathname,
      operations: ["get"],
      validUntil: Date.now() + 60_000,
    });
    const { presignedUrl } = await presignUrl(token, {
      operation: "get",
      pathname: data.pathname,
      access: "private",
      validUntil: Date.now() + 300_000,
    });
    return NextResponse.redirect(presignedUrl, {
      status: 302,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json(
      { error: "Evidence photo is unavailable." },
      { status: 503 },
    );
  }
}
