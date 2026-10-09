"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import {
  TimelineRequestError,
  getCaseTimeline,
  type CaseTimeline,
} from "@/lib/timeline";

function categoryBadge(category: string): string {
  if (category === "CASE") {
    return "bg-amber-100 text-amber-800";
  }
  if (category === "INSPECTION") {
    return "bg-violet-100 text-violet-800";
  }
  if (category === "INTERVENTION") {
    return "bg-sky-100 text-sky-800";
  }
  if (category === "FOLLOW_UP") {
    return "bg-teal-100 text-teal-800";
  }
  return "bg-slate-800 text-white";
}

export default function PestCaseTimelinePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const auth = useAuth();
  const [data, setData] = useState<CaseTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const rawId = params.id;
  const caseId = typeof rawId === "string" ? Number(rawId) : NaN;
  const validId = Number.isSafeInteger(caseId) && caseId > 0 ? caseId : null;

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  useEffect(() => {
    if (auth.status !== "authenticated" || validId === null) {
      return;
    }
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const loaded = await getCaseTimeline(validId);
        if (!active) {
          return;
        }
        setData(loaded);
        setError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          failure instanceof TimelineRequestError &&
          failure.kind === "unauthenticated"
        ) {
          router.replace("/login");
          return;
        }
        setError(
          failure instanceof TimelineRequestError
            ? failure.message
            : "Case timeline could not be read.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [auth.status, router, validId]);

  if (auth.status === "loading") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="status">Checking your session...</p>
      </main>
    );
  }

  if (auth.status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="status">Redirecting to sign in...</p>
      </main>
    );
  }

  if (auth.status === "error") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <h1 className="text-2xl font-semibold">Unable to verify your session</h1>
        <p className="mt-3 text-slate-600">
          The authentication service is unavailable. Reload this page to try again.
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Case Timeline</h1>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link
            href="/pest-cases"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            Back to pest cases
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            Back to dashboard
          </Link>
        </div>

        {validId === null ? (
          <p role="alert" className="mt-6 text-sm text-red-700">
            Invalid pest case reference.
          </p>
        ) : loading ? (
          <p role="status" className="mt-6 text-sm text-slate-600">
            Loading case timeline...
          </p>
        ) : error ? (
          <p role="alert" className="mt-6 text-sm text-red-700">
            {error}
          </p>
        ) : data ? (
          <div>
            <section aria-label="Case summary" className="mt-6 rounded-xl border border-slate-200 p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-semibold text-slate-900">
                  #{data.pest_case.id} — {data.pest_case.pest_name}
                </h2>
                <span className="rounded-full bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-800">
                  {data.pest_case.status}
                </span>
              </div>
              <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="font-medium text-slate-600">Farmer</dt>
                  <dd className="text-slate-900">
                    {data.pest_case.farm.farmer.full_name} —{" "}
                    {data.pest_case.farm.farmer.barangay}
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-600">Farm</dt>
                  <dd className="text-slate-900">
                    {data.pest_case.farm.plot_identifier} — {data.pest_case.farm.barangay} (
                    {data.pest_case.farm.area_hectares.toFixed(2)} ha)
                  </dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-600">Reported</dt>
                  <dd className="text-slate-900">{data.pest_case.reported_at ?? "—"}</dd>
                </div>
                <div>
                  <dt className="font-medium text-slate-600">Symptoms</dt>
                  <dd className="text-slate-900">{data.pest_case.symptoms ?? "—"}</dd>
                </div>
              </dl>
            </section>

            <section aria-label="Chronological timeline" className="mt-8">
              <h2 className="text-lg font-semibold text-slate-900">
                Chronological timeline
              </h2>
              <p className="mt-2 text-xs text-slate-500">
                Assembled from stored case, inspection, intervention, and follow-up
                records. Reschedule history is not stored, so only the current
                inspection schedule is shown.
              </p>
              {data.timeline.length === 0 ? (
                <p role="status" className="mt-4 text-sm text-slate-600">
                  No timeline events found.
                </p>
              ) : (
                <ol className="mt-4 space-y-4">
                  {data.timeline.map((event, index) => (
                    <li
                      key={`${event.event_type}-${index}`}
                      className="rounded-xl border border-slate-200 p-4"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${categoryBadge(event.category)}`}
                        >
                          {event.category}
                          {event.cycle !== null ? ` · Cycle ${event.cycle}` : ""}
                        </span>
                        <span className="text-xs text-slate-500">
                          {event.occurred_at ?? event.event_date ?? "—"}
                        </span>
                      </div>
                      <h3 className="mt-2 text-sm font-semibold text-slate-900">
                        {event.title}
                      </h3>
                      <p className="mt-1 text-sm text-slate-700">{event.description}</p>
                      {event.actor && (
                        <p className="mt-1 text-xs text-slate-500">
                          By {event.actor.full_name} ({event.actor.username})
                        </p>
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        ) : null}
      </div>
    </main>
  );
}
