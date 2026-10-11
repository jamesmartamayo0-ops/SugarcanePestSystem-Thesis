"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import {
  FollowUpsRequestError,
  dueBadgeLabel,
  dueStateFor,
  getFollowUp,
  listDueFollowUps,
  listFollowUps,
  manilaTodayIso,
  recordFollowUp,
  type FollowUpDetail,
  type FollowUpDueEntry,
  type FollowUpOutcome,
} from "@/lib/follow-ups";

function dueBadge(state: string | null): string {
  if (state === "OVERDUE") {
    return "bg-red-100 text-red-800";
  }
  if (state === "DUE_TODAY") {
    return "bg-amber-100 text-amber-800";
  }
  if (state === "UPCOMING") {
    return "bg-sky-100 text-sky-800";
  }
  return "bg-slate-200 text-slate-700";
}

function outcomeBadge(outcome: string): string {
  if (outcome === "RESOLVED") {
    return "bg-slate-800 text-white";
  }
  if (outcome === "REINTERVENTION_REQUIRED") {
    return "bg-orange-100 text-orange-800";
  }
  return "bg-slate-200 text-slate-700";
}

function caseBadge(status: string): string {
  if (status === "CLOSED") {
    return "bg-slate-800 text-white";
  }
  if (status === "REINTERVENTION_REQUIRED") {
    return "bg-orange-100 text-orange-800";
  }
  if (status === "FOLLOW_UP_DUE") {
    return "bg-teal-100 text-teal-800";
  }
  if (status === "UNDER_INTERVENTION") {
    return "bg-violet-100 text-violet-800";
  }
  return "bg-sky-100 text-sky-800";
}

function cycleLabel(history: FollowUpDetail[], entry: FollowUpDetail): string {
  const sameCase = history
    .filter((item) => item.pest_case?.id === entry.pest_case?.id)
    .sort((left, right) => left.intervention_id - right.intervention_id);
  const position = sameCase.findIndex((item) => item.id === entry.id);
  if (position < 0 || entry.pest_case === null) {
    return `Intervention #${entry.intervention_id}`;
  }
  return `Case #${entry.pest_case.id} — cycle ${position + 1} (intervention #${entry.intervention_id})`;
}

export default function FollowUpsPage() {
  const router = useRouter();
  const auth = useAuth();
  const [due, setDue] = useState<FollowUpDueEntry[]>([]);
  const [history, setHistory] = useState<FollowUpDetail[]>([]);
  const [outcomeFilter, setOutcomeFilter] = useState<string>("all");
  const [caseFilter, setCaseFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [selectedInterventionId, setSelectedInterventionId] = useState<number | null>(null);
  const [selectedFollowUpId, setSelectedFollowUpId] = useState<number | null>(null);
  const [detail, setDetail] = useState<FollowUpDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const authenticated = auth.status === "authenticated";
  const role = auth.status === "authenticated" ? auth.user.role : null;
  const userId = auth.status === "authenticated" ? auth.user.id : null;

  const canRecord = useCallback(
    (entry: FollowUpDueEntry): boolean => {
      if (!authenticated) {
        return false;
      }
      if (role === "ADMIN") {
        return true;
      }
      return role === "TECHNICIAN" && entry.assigned_to_user_id === userId;
    },
    [authenticated, role, userId],
  );

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const loadAll = useCallback(
    async (outcome: string, pestCase: string) => {
      setLoading(true);
      setListError(null);
      try {
        const [queue, recorded] = await Promise.all([
          listDueFollowUps(),
          listFollowUps({
            outcome:
              outcome === "all" ? undefined : (outcome as FollowUpOutcome),
            pestCaseId: pestCase === "all" ? undefined : Number(pestCase),
          }),
        ]);
        setDue(queue);
        setHistory(recorded);
      } catch (failure) {
        if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FollowUpsRequestError
            ? failure.message
            : "Follow-up records could not be read.",
        );
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!authenticated) {
      return;
    }
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const [queue, recorded] = await Promise.all([
          listDueFollowUps(),
          listFollowUps(),
        ]);
        if (!active) {
          return;
        }
        setDue(queue);
        setHistory(recorded);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FollowUpsRequestError
            ? failure.message
            : "Follow-up records could not be read.",
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
  }, [authenticated, router]);

  const openDetail = useCallback(
    async (followUpId: number) => {
      setSelectedFollowUpId(followUpId);
      setDetail(null);
      setDetailError(null);
      setLoadingDetail(true);
      try {
        setDetail(await getFollowUp(followUpId));
      } catch (failure) {
        if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setDetailError(
          failure instanceof FollowUpsRequestError
            ? failure.message
            : "Follow-up could not be read.",
        );
      } finally {
        setLoadingDetail(false);
      }
    },
    [router],
  );

  async function handleRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    setNotice(null);
    setFormError(null);
    if (selectedInterventionId === null) {
      setFormError("Select a pending intervention from the queue first.");
      return;
    }
    const selected = due.find(
      (entry) => entry.intervention_id === selectedInterventionId,
    );
    if (selected === undefined || !canRecord(selected)) {
      setSelectedInterventionId(null);
      setFormError("You do not have permission to record this follow-up.");
      return;
    }
    const data = new FormData(event.currentTarget);
    const observedRaw = data.get("observed_on");
    const pestRaw = data.get("pest_observed");
    const areaRaw = data.get("observed_affected_area_hectares");
    const notesRaw = data.get("assessment_notes");
    const outcomeRaw = data.get("outcome");
    if (
      typeof observedRaw !== "string" ||
      observedRaw.trim() === "" ||
      (typeof pestRaw !== "string" || (pestRaw !== "yes" && pestRaw !== "no")) ||
      typeof notesRaw !== "string" ||
      notesRaw.trim() === "" ||
      notesRaw.trim().length > 2000 ||
      (typeof outcomeRaw !== "string" ||
        (outcomeRaw !== "RESOLVED" && outcomeRaw !== "REINTERVENTION_REQUIRED"))
    ) {
      setFormError(
        "Enter the observed date, whether the pest was seen, notes (1–2000 characters), and an explicit outcome.",
      );
      return;
    }
    let area: number | null = null;
    if (typeof areaRaw === "string" && areaRaw.trim() !== "") {
      const parsed = Number(areaRaw.trim());
      if (!Number.isFinite(parsed) || parsed < 0 || parsed > 10000) {
        setFormError("Observed area must be between 0 and 10000 hectares when provided.");
        return;
      }
      area = parsed;
    }
    // Explicit Manila calendar-date check keeps the UTC bug fixed in Phase 3D
    // from returning: never derive today from new Date().toISOString().
    const todayManila = manilaTodayIso();
    if (observedRaw.trim() > todayManila) {
      setFormError("Observed date cannot be in the future (Asia/Manila).");
      return;
    }
    setRecording(true);
    try {
      const created = await recordFollowUp(
        selectedInterventionId,
        {
          observed_on: observedRaw.trim(),
          pest_observed: pestRaw === "yes",
          ...(area !== null ? { observed_affected_area_hectares: area } : {}),
          assessment_notes: notesRaw.trim(),
          outcome: outcomeRaw as FollowUpOutcome,
        },
        auth.csrfToken,
      );
      setHistory((current) =>
        [...current, created].sort((left, right) => left.id - right.id),
      );
      setDue((current) =>
        current.filter((entry) => entry.intervention_id !== selectedInterventionId),
      );
      setSelectedInterventionId(null);
      setFormError(null);
      setNotice(
        created.outcome === "RESOLVED"
          ? `Follow-up #${created.id} recorded. Case #${created.pest_case?.id ?? ""} is now CLOSED.`
          : `Follow-up #${created.id} recorded. Case #${created.pest_case?.id ?? ""} now requires reintervention.`,
      );
      event.currentTarget.reset();
    } catch (failure) {
      if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setNotice(null);
      setFormError(
        failure instanceof FollowUpsRequestError
          ? failure.message
          : "Follow-up could not be recorded.",
      );
    } finally {
      setRecording(false);
    }
  }

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

  const selectedEntry = due.find(
    (entry) => entry.intervention_id === selectedInterventionId,
  );
  const activeRecordingTarget =
    selectedEntry !== undefined && canRecord(selectedEntry) ? selectedEntry : null;

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">
          Follow-up &amp; Reassessment
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Record human reassessments for completed interventions. Outcomes are
          explicitly selected and never inferred. Resolved cases close; cases
          needing more work return for reintervention. History is preserved.
        </p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link
            href="/dashboard"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            Back to dashboard
          </Link>
          <Link
            href="/pest-cases"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View pest cases
          </Link>
          <Link
            href="/interventions"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View interventions
          </Link>
          <Link
            href="/reports"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View reports
          </Link>
        </div>

        <section aria-label="Pending follow-up queue" className="mt-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Pending follow-up queue</h2>
            <button
              type="button"
              onClick={() => void loadAll(outcomeFilter, caseFilter)}
              disabled={loading}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
            >
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {loading ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading follow-up queue...
            </p>
          ) : listError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {listError}
            </p>
          ) : due.length === 0 ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No completed interventions are awaiting follow-up.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Case / Farm / Farmer</th>
                    <th scope="col" className="px-4 py-3 font-medium">Technician</th>
                    <th scope="col" className="px-4 py-3 font-medium">Method / Performed</th>
                    <th scope="col" className="px-4 py-3 font-medium">Due</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {due.map((entry) => {
                    const localState = dueStateFor(entry.follow_up_due_on);
                    return (
                      <tr key={entry.intervention_id}>
                        <td className="px-4 py-3 text-slate-900">
                          #{entry.pest_case_id} — {entry.pest_case?.pest_name ?? "—"}
                          <span className="block text-xs text-slate-600">
                            {entry.pest_case?.farm?.plot_identifier ?? "—"} —{" "}
                            {entry.pest_case?.farm?.farmer?.full_name ?? "—"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-900">
                          {entry.assigned_to?.full_name ?? `#${entry.assigned_to_user_id}`}
                        </td>
                        <td className="px-4 py-3 text-slate-900">
                          {entry.method_category}
                          <span className="block text-xs text-slate-600">
                            Performed {entry.performed_on ?? "—"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-semibold ${dueBadge(localState)}`}
                          >
                            {entry.follow_up_due_on ?? "Not set"} —{" "}
                            {dueBadgeLabel(localState)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {canRecord(entry) ? (
                            <button
                              type="button"
                              onClick={() => {
                                if (!canRecord(entry)) {
                                  return;
                                }
                                setSelectedInterventionId(entry.intervention_id);
                                setFormError(null);
                              }}
                              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                            >
                              {selectedInterventionId === entry.intervention_id
                                ? "Selected"
                                : "Record"}
                            </button>
                          ) : (
                            <span className="text-xs text-slate-500">
                              Assigned technician only
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section aria-label="Record follow-up" className="mt-10">
          <h2 className="text-lg font-semibold text-slate-900">Record follow-up</h2>
          {activeRecordingTarget === null ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Select a pending intervention from the queue to record its reassessment.
            </p>
          ) : (
            <form onSubmit={handleRecord} className="mt-4 grid gap-4 sm:grid-cols-2">
              <p className="text-sm text-slate-700 sm:col-span-2">
                Recording for intervention #{activeRecordingTarget.intervention_id}. The outcome you
                select controls the next case status.
              </p>
              <div>
                <label htmlFor="observed_on" className="block text-sm font-medium text-slate-700">
                  Observed date
                </label>
                <input
                  id="observed_on"
                  name="observed_on"
                  type="date"
                  required
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                />
              </div>
              <div>
                <span className="block text-sm font-medium text-slate-700">
                  Pest still observed
                </span>
                <div className="mt-2 flex gap-4">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input type="radio" name="pest_observed" value="yes" required className="h-4 w-4" />
                    Yes
                  </label>
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input type="radio" name="pest_observed" value="no" required className="h-4 w-4" />
                    No
                  </label>
                </div>
              </div>
              <div>
                <label htmlFor="observed_affected_area_hectares" className="block text-sm font-medium text-slate-700">
                  Observed affected area (hectares, optional)
                </label>
                <input
                  id="observed_affected_area_hectares"
                  name="observed_affected_area_hectares"
                  type="number"
                  min={0}
                  max={10000}
                  step={0.01}
                  placeholder="e.g. 0.50"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                />
              </div>
              <div>
                <span className="block text-sm font-medium text-slate-700">Outcome (required)</span>
                <div className="mt-2 grid gap-2">
                  <label className="inline-flex items-start gap-2 text-sm text-slate-700">
                    <input type="radio" name="outcome" value="RESOLVED" required className="mt-1 h-4 w-4" />
                    Resolved / No further intervention required
                  </label>
                  <label className="inline-flex items-start gap-2 text-sm text-slate-700">
                    <input type="radio" name="outcome" value="REINTERVENTION_REQUIRED" required className="mt-1 h-4 w-4" />
                    Further intervention required
                  </label>
                </div>
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="assessment_notes" className="block text-sm font-medium text-slate-700">
                  Assessment notes
                </label>
                <textarea
                  id="assessment_notes"
                  name="assessment_notes"
                  rows={3}
                  maxLength={2000}
                  required
                  placeholder="e.g. No fresh boring observed on east rows; canopy recovering"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                />
              </div>
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  disabled={recording}
                  className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                >
                  {recording ? "Recording..." : "Record follow-up"}
                </button>
              </div>
            </form>
          )}
          {formError && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {formError}
            </p>
          )}
          {notice && (
            <p role="status" className="mt-4 text-sm text-emerald-700">
              {notice}
            </p>
          )}
        </section>

        <section aria-label="Follow-up history" className="mt-10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Follow-up history</h2>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="follow_case_filter" className="text-sm font-medium text-slate-700">
                Case
              </label>
              <input
                id="follow_case_filter"
                value={caseFilter === "all" ? "" : caseFilter}
                onChange={(event) => {
                  const next = event.target.value.trim() === "" ? "all" : event.target.value.trim();
                  setCaseFilter(next);
                }}
                placeholder="All"
                inputMode="numeric"
                className="w-24 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
              />
              <label htmlFor="follow_outcome_filter" className="text-sm font-medium text-slate-700">
                Outcome
              </label>
              <select
                id="follow_outcome_filter"
                value={outcomeFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setOutcomeFilter(next);
                  void loadAll(next, caseFilter);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
              >
                <option value="all">All outcomes</option>
                <option value="RESOLVED">RESOLVED</option>
                <option value="REINTERVENTION_REQUIRED">REINTERVENTION_REQUIRED</option>
              </select>
              <button
                type="button"
                onClick={() => void loadAll(outcomeFilter, caseFilter)}
                disabled={loading}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
              >
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loading ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading follow-up history...
            </p>
          ) : history.length === 0 ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No recorded reassessments found.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Follow-up</th>
                    <th scope="col" className="px-4 py-3 font-medium">Observation</th>
                    <th scope="col" className="px-4 py-3 font-medium">Outcome / Case</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {history.map((entry) => (
                    <tr key={entry.id}>
                      <td className="px-4 py-3 text-slate-900">
                        #{entry.id} — {cycleLabel(history, entry)}
                        <span className="block text-xs text-slate-600">
                          Recorded {entry.created_at ?? "—"} by{" "}
                          {entry.recorded_by?.full_name ?? `#${entry.recorded_by_user_id}`}
                        </span>
                        <span className="mt-1 block text-xs text-slate-600">
                          {entry.assessment_notes}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-900">
                        {entry.pest_observed ? "Pest seen" : "No pest seen"} —{" "}
                        {entry.observed_on}
                        <span className="block text-xs text-slate-600">
                          Area{" "}
                          {entry.observed_affected_area_hectares === null
                            ? "—"
                            : `${entry.observed_affected_area_hectares.toFixed(2)} ha`}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${outcomeBadge(entry.outcome)}`}
                        >
                          {entry.outcome}
                        </span>
                        <span
                          className={`ml-2 rounded-full px-3 py-1 text-xs font-semibold ${caseBadge(entry.pest_case?.status ?? "")}`}
                        >
                          {entry.pest_case?.status ?? "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => void openDetail(entry.id)}
                          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                        >
                          {selectedFollowUpId === entry.id ? "Selected" : "View"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selectedFollowUpId !== null && (
          <section
            aria-label="Follow-up detail"
            className="mt-8 rounded-xl border border-slate-200 p-6"
          >
            {loadingDetail ? (
              <p role="status" className="text-sm text-slate-600">
                Loading follow-up details...
              </p>
            ) : detailError ? (
              <p role="alert" className="text-sm text-red-700">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold text-slate-900">
                    Follow-up #{detail.id} — {detail.pest_case?.pest_name ?? "—"}
                  </h2>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${outcomeBadge(detail.outcome)}`}
                  >
                    {detail.outcome}
                  </span>
                </div>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="font-medium text-slate-600">Intervention cycle</dt>
                    <dd className="text-slate-900">{cycleLabel(history, detail)}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Case status</dt>
                    <dd className="text-slate-900">{detail.pest_case?.status ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Observation</dt>
                    <dd className="text-slate-900">
                      {detail.pest_observed ? "Pest observed" : "No pest observed"} on{" "}
                      {detail.observed_on}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Recorded by</dt>
                    <dd className="text-slate-900">
                      {detail.recorded_by?.full_name ?? `#${detail.recorded_by_user_id}`} on{" "}
                      {detail.created_at ?? "—"}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="font-medium text-slate-600">Assessment notes</dt>
                    <dd className="text-slate-900">{detail.assessment_notes}</dd>
                  </div>
                </dl>
                <p role="status" className="mt-6 text-sm text-slate-600">
                  Recorded reassessments are read-only history and cannot be edited or
                  deleted in this phase.
                </p>
              </div>
            ) : null}
          </section>
        )}
      </div>
    </main>
  );
}
