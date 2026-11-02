"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { workflowLabel } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import {
  INTERVENTION_METHOD_CATEGORIES,
  InterventionsRequestError,
  completeIntervention,
  getIntervention,
  listInterventions,
  startIntervention,
  updateInterventionPlan,
  type InterventionDetail,
  type InterventionMethodCategory,
  type TechnicianSummary,
} from "@/lib/interventions";
import { listTechnicians } from "@/lib/inspections";
import {
  PestCasesRequestError,
  listPestCases,
  type PestCaseSummary,
} from "@/lib/pest-cases";

function todayIso(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);

  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;

  if (!year || !month || !day) {
    throw new Error("Unable to determine Manila calendar date");
  }

  return `${year}-${month}-${day}`;
}

function followUpLabel(followUp: string | null, completed: boolean): string {
  if (followUp === null) {
    return "Not set";
  }
  const today = todayIso();
  if (followUp < today) {
    return `${followUp} — Overdue`;
  }
  if (followUp === today) {
    return `${followUp} — Due today`;
  }
  return completed ? `${followUp} — Upcoming` : `${followUp} — Planned`;
}

function followUpBadge(followUp: string | null): string {
  if (followUp === null) {
    return "gov-status-badge";
  }
  const today = todayIso();
  if (followUp < today) {
    return "gov-status-badge gov-status-reintervention-required";
  }
  if (followUp === today) {
    return "gov-status-badge gov-status-follow-up-due";
  }
  return "gov-status-badge";
}

function statusBadge(status: string): string {
  return `gov-status-badge gov-status-${status.toLowerCase().replaceAll("_", "-")}`;
}

function cycleFor(all: InterventionDetail[], item: InterventionDetail): number {
  const sameCase = all
    .filter((entry) => entry.pest_case_id === item.pest_case_id)
    .sort((left, right) => left.id - right.id);
  const position = sameCase.findIndex((entry) => entry.id === item.id);
  return position < 0 ? 1 : position + 1;
}

function isPending(item: InterventionDetail): boolean {
  return (
    item.performed_on === null &&
    item.completion_notes === null &&
    item.completed_at === null &&
    item.pest_case.status === "UNDER_INTERVENTION"
  );
}

export default function InterventionsPage() {
  const router = useRouter();
  const auth = useAuth();
  const [interventions, setInterventions] = useState<InterventionDetail[]>([]);
  const [eligibleCases, setEligibleCases] = useState<PestCaseSummary[]>([]);
  const [technicians, setTechnicians] = useState<TechnicianSummary[]>([]);
  const [caseFilter, setCaseFilter] = useState<string>("all");
  const [technicianFilter, setTechnicianFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<InterventionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [savingPlan, setSavingPlan] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const authenticated = auth.status === "authenticated";
  const role = auth.status === "authenticated" ? auth.user.role : null;
  const userId = auth.status === "authenticated" ? auth.user.id : null;

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const loadAll = useCallback(
    async (caseId: string, technicianId: string) => {
      setLoading(true);
      setListError(null);
      try {
        const [loadedInterventions, loadedValidated, loadedReintervention, loadedTechnicians] =
          await Promise.all([
            listInterventions({
              pestCaseId: caseId === "all" ? undefined : Number(caseId),
              assignedToUserId: technicianId === "all" ? undefined : Number(technicianId),
            }),
            listPestCases({ status: "FIELD_VALIDATED" }),
            listPestCases({ status: "REINTERVENTION_REQUIRED" }),
            listTechnicians(),
          ]);
        const loadedCases = [...loadedValidated, ...loadedReintervention].sort(
          (left, right) => left.id - right.id,
        );
        setInterventions(loadedInterventions);
        setEligibleCases(loadedCases);
        setTechnicians(loadedTechnicians);
      } catch (failure) {
        if (
          (failure instanceof InterventionsRequestError &&
            failure.kind === "unauthenticated") ||
          (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof InterventionsRequestError ||
            failure instanceof PestCasesRequestError
            ? failure.message
            : "Intervention records could not be read.",
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
        const [loadedInterventions, loadedValidated, loadedReintervention, loadedTechnicians] =
          await Promise.all([
            listInterventions(),
            listPestCases({ status: "FIELD_VALIDATED" }),
            listPestCases({ status: "REINTERVENTION_REQUIRED" }),
            listTechnicians(),
          ]);
        if (!active) {
          return;
        }
        const loadedCases = [...loadedValidated, ...loadedReintervention].sort(
          (left, right) => left.id - right.id,
        );
        setInterventions(loadedInterventions);
        setEligibleCases(loadedCases);
        setTechnicians(loadedTechnicians);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          (failure instanceof InterventionsRequestError &&
            failure.kind === "unauthenticated") ||
          (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof InterventionsRequestError ||
            failure instanceof PestCasesRequestError
            ? failure.message
            : "Intervention records could not be read.",
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
    async (interventionId: number) => {
      setSelectedId(interventionId);
      setDetail(null);
      setDetailError(null);
      setActionError(null);
      setLoadingDetail(true);
      try {
        setDetail(await getIntervention(interventionId));
      } catch (failure) {
        if (
          failure instanceof InterventionsRequestError &&
          failure.kind === "unauthenticated"
        ) {
          router.replace("/login");
          return;
        }
        setDetailError(
          failure instanceof InterventionsRequestError
            ? failure.message
            : "Intervention could not be read.",
        );
      } finally {
        setLoadingDetail(false);
      }
    },
    [router],
  );

  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    setNotice(null);
    setFormError(null);
    setActionError(null);
    const data = new FormData(event.currentTarget);
    const caseRaw = data.get("pest_case_id");
    const categoryRaw = data.get("method_category");
    const descriptionRaw = data.get("method_description");
    const techRaw = data.get("assigned_to_user_id");
    const dateRaw = data.get("scheduled_for");
    const followRaw = data.get("follow_up_due_on");
    const caseId = typeof caseRaw === "string" ? Number(caseRaw) : NaN;
    const technicianId = typeof techRaw === "string" ? Number(techRaw) : NaN;
    if (
      !Number.isSafeInteger(caseId) ||
      caseId <= 0 ||
      typeof categoryRaw !== "string" ||
      !(INTERVENTION_METHOD_CATEGORIES as string[]).includes(categoryRaw) ||
      typeof descriptionRaw !== "string" ||
      descriptionRaw.trim() === "" ||
      descriptionRaw.trim().length > 2000 ||
      !Number.isSafeInteger(technicianId) ||
      technicianId <= 0 ||
      typeof dateRaw !== "string" ||
      dateRaw.trim() === ""
    ) {
      setFormError("Select an eligible case, category, technician, date, and description.");
      return;
    }
    const followUp =
      typeof followRaw === "string" && followRaw.trim() !== "" ? followRaw.trim() : undefined;
    setStarting(true);
    try {
      const created = await startIntervention(
        caseId,
        {
          method_category: categoryRaw as InterventionMethodCategory,
          method_description: descriptionRaw.trim(),
          scheduled_for: (dateRaw as string).trim(),
          assigned_to_user_id: technicianId,
          ...(followUp !== undefined ? { follow_up_due_on: followUp } : {}),
        },
        auth.csrfToken,
      );
      setInterventions((current) =>
        [...current, created].sort((left, right) => left.id - right.id),
      );
      setEligibleCases((current) => current.filter((entry) => entry.id !== caseId));
      setFormError(null);
      setNotice(`Intervention #${created.id} was started.`);
      event.currentTarget.reset();
    } catch (failure) {
      if (
        failure instanceof InterventionsRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setNotice(null);
      setFormError(
        failure instanceof InterventionsRequestError
          ? failure.message
          : "Intervention could not be started.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function handlePlan(event: FormEvent<HTMLFormElement>, target: InterventionDetail) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    setNotice(null);
    setFormError(null);
    setActionError(null);
    const data = new FormData(event.currentTarget);
    const categoryRaw = data.get("method_category");
    const descriptionRaw = data.get("method_description");
    const dateRaw = data.get("scheduled_for");
    const techRaw = data.get("assigned_to_user_id");
    const followRaw = data.get("follow_up_due_on");
    const payload: {
      method_category?: InterventionMethodCategory;
      method_description?: string;
      scheduled_for?: string;
      assigned_to_user_id?: number;
      follow_up_due_on?: string | null;
    } = {};
    if (typeof categoryRaw === "string" && categoryRaw !== "") {
      if (!(INTERVENTION_METHOD_CATEGORIES as string[]).includes(categoryRaw)) {
        setActionError("Select a valid intervention category.");
        return;
      }
      payload.method_category = categoryRaw as InterventionMethodCategory;
    }
    if (typeof descriptionRaw === "string" && descriptionRaw.trim() !== "") {
      if (descriptionRaw.trim().length > 2000) {
        setActionError("Description must be at most 2000 characters.");
        return;
      }
      payload.method_description = descriptionRaw.trim();
    }
    if (typeof dateRaw === "string" && dateRaw.trim() !== "") {
      payload.scheduled_for = dateRaw.trim();
    }
    if (typeof techRaw === "string" && techRaw.trim() !== "") {
      const parsed = Number(techRaw);
      if (!Number.isSafeInteger(parsed) || parsed <= 0) {
        setActionError("Select a valid technician for reassignment.");
        return;
      }
      payload.assigned_to_user_id = parsed;
    }
    if (typeof followRaw === "string") {
      if (followRaw.trim() === "") {
        payload.follow_up_due_on = null;
      } else {
        payload.follow_up_due_on = followRaw.trim();
      }
    }
    if (Object.keys(payload).length === 0) {
      setActionError("Change at least one planning field before saving.");
      return;
    }
    setSavingPlan(true);
    try {
      const updated = await updateInterventionPlan(target.id, payload, auth.csrfToken);
      setDetail(updated);
      setInterventions((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setActionError(null);
      setNotice(`Intervention #${updated.id} plan was updated.`);
    } catch (failure) {
      if (
        failure instanceof InterventionsRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setNotice(null);
      setActionError(
        failure instanceof InterventionsRequestError
          ? failure.message
          : "Intervention plan could not be updated.",
      );
    } finally {
      setSavingPlan(false);
    }
  }

  async function handleComplete(event: FormEvent<HTMLFormElement>, target: InterventionDetail) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    setNotice(null);
    setFormError(null);
    setActionError(null);
    const data = new FormData(event.currentTarget);
    const performedRaw = data.get("performed_on");
    const notesRaw = data.get("completion_notes");
    const followRaw = data.get("follow_up_due_on");
    const reuseRaw = data.get("reuse_planned_follow_up_date");
    if (
      typeof performedRaw !== "string" ||
      performedRaw.trim() === "" ||
      typeof notesRaw !== "string" ||
      notesRaw.trim() === "" ||
      notesRaw.trim().length > 2000
    ) {
      setActionError("Enter the performed date and completion notes (1–2000 characters).");
      return;
    }
    const followUp =
      typeof followRaw === "string" && followRaw.trim() !== "" ? followRaw.trim() : undefined;
    const reusePlanned = reuseRaw === "on";
    if (followUp === undefined && !reusePlanned) {
      setActionError("Enter a follow-up due date or reuse the planned follow-up date.");
      return;
    }
    setCompleting(true);
    try {
      const updated = await completeIntervention(
        target.id,
        {
          performed_on: performedRaw.trim(),
          completion_notes: notesRaw.trim(),
          ...(followUp !== undefined ? { follow_up_due_on: followUp } : {}),
          ...(reusePlanned ? { reuse_planned_follow_up_date: true } : {}),
        },
        auth.csrfToken,
      );
      setDetail(updated);
      setInterventions((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setActionError(null);
      setNotice(`Intervention #${updated.id} was completed.`);
    } catch (failure) {
      if (
        failure instanceof InterventionsRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setNotice(null);
      setActionError(
        failure instanceof InterventionsRequestError
          ? failure.message
          : "Intervention could not be completed.",
      );
    } finally {
      setCompleting(false);
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

  const canAct = (item: InterventionDetail): boolean => {
    if (!isPending(item)) {
      return false;
    }
    if (role === "ADMIN") {
      return true;
    }
    return role === "TECHNICIAN" && item.assigned_to_user_id === userId;
  };

  return (
    <main className="gov-page">
      <header className="gov-page-header">
        <h1 className="gov-page-title">Interventions</h1>
        <p className="gov-page-description">
          Plan human-selected field actions for Field Validated and
          Reintervention Required cases, then record completion with a follow-up
          due date. Historical interventions are preserved so first and repeat
          cycles stay distinguishable. Categories are documentation labels only
          and never prescribe chemicals, rates, or dosages.
        </p>
        <div className="gov-record-controls mt-3">
          <Link
            href="/pest-cases"
            className="gov-activity-link"
          >
            View pest cases
          </Link>
          <Link
            href="/inspections"
            className="gov-activity-link"
          >
            View inspections
          </Link>
          <Link
            href="/follow-ups"
            className="gov-activity-link"
          >
            View follow-ups
          </Link>
          <Link
            href="/reports"
            className="gov-activity-link"
          >
            View reports
          </Link>
        </div>
      </header>

        <section aria-label="Start intervention" className="gov-card gov-record-section">
          <h2 className="gov-record-title">Start intervention</h2>
          {eligibleCases.length === 0 && !loading ? (
            <p role="status" className="gov-empty-state">
              No Field Validated or Reintervention Required cases are waiting for an
              intervention plan.
            </p>
          ) : (
            <form onSubmit={handleStart} className="gov-form gov-form-grid">
              <div className="gov-field">
                <label htmlFor="pest_case_id" className="gov-label">
                  Eligible case <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <select
                  id="pest_case_id"
                  name="pest_case_id"
                  required
                  defaultValue=""
                  className="gov-select"
                >
                  <option value="" disabled>
                    Select a case
                  </option>
                  {eligibleCases.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      #{entry.id} — {entry.pest_name} ({entry.reported_area_hectares.toFixed(2)} ha) —{" "}
                      {workflowLabel(entry.status)}
                    </option>
                  ))}
                </select>
              </div>
              <div className="gov-field">
                <label htmlFor="method_category" className="gov-label">
                  Category (human-selected) <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <select
                  id="method_category"
                  name="method_category"
                  required
                  defaultValue=""
                  className="gov-select"
                >
                  <option value="" disabled>
                    Select a category
                  </option>
                  {INTERVENTION_METHOD_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
              <div className="gov-field gov-field-wide">
                <label htmlFor="method_description" className="gov-label">
                  Description of planned work <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <textarea
                  id="method_description"
                  name="method_description"
                  rows={3}
                  maxLength={2000}
                  required
                  placeholder="e.g. Manual removal of affected shoots on east rows"
                  className="gov-textarea"
                />
              </div>
              <div className="gov-field">
                <label htmlFor="assigned_to_user_id" className="gov-label">
                  Assigned Agriculture Technician <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <select
                  id="assigned_to_user_id"
                  name="assigned_to_user_id"
                  required
                  defaultValue=""
                  className="gov-select"
                >
                  <option value="" disabled>
                    Select an Agriculture Technician
                  </option>
                  {technicians.map((tech) => (
                    <option key={tech.id} value={tech.id}>
                      {tech.full_name} ({tech.username})
                    </option>
                  ))}
                </select>
              </div>
              <div className="gov-field">
                <label htmlFor="scheduled_for" className="gov-label">
                  Scheduled date <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="scheduled_for"
                  name="scheduled_for"
                  type="date"
                  required
                  className="gov-input"
                />
              </div>
              <div className="gov-field gov-field-wide">
                <label htmlFor="follow_up_due_on" className="gov-label">
                  Planned follow-up date (optional)
                </label>
                <input
                  id="follow_up_due_on"
                  name="follow_up_due_on"
                  type="date"
                  className="gov-input"
                />
              </div>
              <div className="gov-form-actions">
                <button
                  type="submit"
                  disabled={starting}
                  className="gov-button gov-button-primary"
                >
                  {starting ? "Starting..." : "Start intervention"}
                </button>
              </div>
            </form>
          )}
          {formError && (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {formError}
            </p>
          )}
          {notice && (
            <p role="status" className="gov-alert gov-alert-success mt-4">
              {notice}
            </p>
          )}
        </section>

        <section aria-label="Intervention records" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <h2 className="gov-record-title">Intervention records</h2>
            <div className="gov-record-controls">
              <label htmlFor="case_filter" className="gov-label">
                Case
              </label>
              <input
                id="case_filter"
                value={caseFilter === "all" ? "" : caseFilter}
                onChange={(event) => {
                  const next = event.target.value.trim() === "" ? "all" : event.target.value.trim();
                  setCaseFilter(next);
                }}
                placeholder="All"
                inputMode="numeric"
                className="gov-input w-24"
              />
              <label htmlFor="technician_filter" className="gov-label">
                Agriculture Technician
              </label>
              <select
                id="technician_filter"
                value={technicianFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setTechnicianFilter(next);
                  void loadAll(caseFilter, next);
                }}
                className="gov-select"
              >
                <option value="all">All Agriculture Technicians</option>
                {technicians.map((tech) => (
                  <option key={tech.id} value={tech.id}>
                    {tech.full_name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void loadAll(caseFilter, technicianFilter)}
                disabled={loading}
                className="gov-button gov-button-secondary gov-button-compact"
              >
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loading ? (
            <p role="status" className="gov-empty-state">
              Loading interventions...
            </p>
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : interventions.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No interventions found. Start the first intervention above.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[820px]">
                <thead>
                  <tr>
                    <th scope="col">Intervention</th>
                    <th scope="col">Case / Farm / Farmer</th>
                    <th scope="col">Agriculture Technician</th>
                    <th scope="col">Status</th>
                    <th scope="col">Follow-up</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {interventions.map((entry) => {
                    const completed = !isPending(entry);
                    const cycle = cycleFor(interventions, entry);
                    return (
                      <tr key={entry.id}>
                        <td>
                          #{entry.id} — {entry.method_category} (cycle {cycle})
                          <span className="block text-xs text-slate-600">
                            Scheduled {entry.scheduled_for}
                          </span>
                        </td>
                        <td>
                          #{entry.pest_case_id} — {entry.pest_case.pest_name}
                          <span className="block text-xs text-slate-600">
                            {entry.pest_case.farm?.plot_identifier ?? "—"} —{" "}
                            {entry.pest_case.farm?.farmer?.full_name ?? "—"}
                          </span>
                        </td>
                        <td>
                          {entry.assigned_to?.full_name ?? `#${entry.assigned_to_user_id}`}
                        </td>
                        <td>
                          <span
                            className={statusBadge(entry.pest_case.status)}
                          >
                            {workflowLabel(entry.pest_case.status)}
                          </span>
                        </td>
                        <td>
                          <span
                            className={followUpBadge(entry.follow_up_due_on)}
                          >
                            {followUpLabel(entry.follow_up_due_on, completed)}
                          </span>
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={() => void openDetail(entry.id)}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            {selectedId === entry.id ? "Selected" : "View"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selectedId !== null && (
          <section
            aria-label="Intervention detail"
            className="gov-card gov-record-section"
          >
            {loadingDetail ? (
              <p role="status" className="gov-empty-state">
                Loading intervention details...
              </p>
            ) : detailError ? (
              <p role="alert" className="gov-alert gov-alert-error">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="gov-record-toolbar">
                  <h2 className="gov-record-title">
                    Intervention #{detail.id} — {detail.pest_case.pest_name} (cycle{" "}
                    {cycleFor(interventions, detail)})
                  </h2>
                  <span
                    className={statusBadge(detail.pest_case.status)}
                  >
                    {workflowLabel(detail.pest_case.status)}
                  </span>
                </div>
                <dl className="gov-detail-grid">
                  <div>
                    <dt className="gov-detail-label">Farm plot</dt>
                    <dd className="gov-detail-value">
                      {detail.pest_case.farm?.plot_identifier ?? "—"} —{" "}
                      {detail.pest_case.farm?.barangay ?? "—"} (
                      {(detail.pest_case.farm?.area_hectares ?? 0).toFixed(2)} ha)
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Farmer</dt>
                    <dd className="gov-detail-value">
                      {detail.pest_case.farm?.farmer?.full_name ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Category</dt>
                    <dd className="gov-detail-value">{detail.method_category}</dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Assigned Agriculture Technician</dt>
                    <dd className="gov-detail-value">
                      {detail.assigned_to?.full_name ?? `#${detail.assigned_to_user_id}`}
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Scheduled for</dt>
                    <dd className="gov-detail-value">{detail.scheduled_for}</dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Follow-up due</dt>
                    <dd className="gov-detail-value">
                      <span
                        className={followUpBadge(detail.follow_up_due_on)}
                      >
                        {followUpLabel(detail.follow_up_due_on, !isPending(detail))}
                      </span>
                    </dd>
                  </div>
                  <div className="gov-detail-wide">
                    <dt className="gov-detail-label">Description</dt>
                    <dd className="gov-detail-value">{detail.method_description}</dd>
                  </div>
                  {detail.performed_on !== null && (
                    <div>
                      <dt className="gov-detail-label">Performed on</dt>
                      <dd className="gov-detail-value">{detail.performed_on}</dd>
                    </div>
                  )}
                  {detail.completion_notes !== null && (
                    <div className="gov-detail-wide">
                      <dt className="gov-detail-label">Completion notes</dt>
                      <dd className="gov-detail-value">{detail.completion_notes}</dd>
                    </div>
                  )}
                </dl>

                {isPending(detail) ? (
                  canAct(detail) ? (
                    <div className="gov-form">
                      <div className="gov-workflow-panel">
                        <h3 className="gov-record-title">
                          Edit intervention plan
                        </h3>
                        <form
                          onSubmit={(event) => void handlePlan(event, detail)}
                          className="gov-form gov-form-grid"
                        >
                          <div className="gov-field">
                            <label
                              htmlFor="plan_category"
                              className="gov-label"
                            >
                              Category (optional)
                            </label>
                            <select
                              id="plan_category"
                              name="method_category"
                              defaultValue=""
                              className="gov-select"
                            >
                              <option value="">Keep current ({detail.method_category})</option>
                              {INTERVENTION_METHOD_CATEGORIES.map((category) => (
                                <option key={category} value={category}>
                                  {category}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="plan_scheduled"
                              className="gov-label"
                            >
                              Scheduled date (optional)
                            </label>
                            <input
                              id="plan_scheduled"
                              name="scheduled_for"
                              type="date"
                              className="gov-input"
                            />
                          </div>
                          <div className="gov-field gov-field-wide">
                            <label
                              htmlFor="plan_description"
                              className="gov-label"
                            >
                              Description (optional)
                            </label>
                            <textarea
                              id="plan_description"
                              name="method_description"
                              rows={2}
                              maxLength={2000}
                              placeholder={detail.method_description}
                              className="gov-textarea"
                            />
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="plan_technician"
                              className="gov-label"
                            >
                              Agriculture Technician (optional)
                            </label>
                            <select
                              id="plan_technician"
                              name="assigned_to_user_id"
                              defaultValue=""
                              className="gov-select"
                            >
                              <option value="">Keep current</option>
                              {technicians.map((tech) => (
                                <option key={tech.id} value={tech.id}>
                                  {tech.full_name} ({tech.username})
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="plan_follow_up"
                              className="gov-label"
                            >
                              Planned follow-up (optional, blank clears)
                            </label>
                            <input
                              id="plan_follow_up"
                              name="follow_up_due_on"
                              type="date"
                              className="gov-input"
                            />
                          </div>
                          <div className="gov-form-actions">
                            <button
                              type="submit"
                              disabled={savingPlan || completing}
                              className="gov-button gov-button-primary"
                            >
                              {savingPlan ? "Saving..." : "Save plan"}
                            </button>
                          </div>
                        </form>
                      </div>
                      <div className="gov-workflow-panel">
                        <h3 className="gov-record-title">
                          Record completion
                        </h3>
                        <form
                          onSubmit={(event) => void handleComplete(event, detail)}
                          className="gov-form gov-form-grid"
                        >
                          <div className="gov-field">
                            <label
                              htmlFor="performed_on"
                              className="gov-label"
                            >
                              Performed date <span className="gov-required" aria-hidden="true">*</span>
                            </label>
                            <input
                              id="performed_on"
                              name="performed_on"
                              type="date"
                              required
                              className="gov-input"
                            />
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="complete_follow_up"
                              className="gov-label"
                            >
                              Follow-up due date
                            </label>
                            <input
                              id="complete_follow_up"
                              name="follow_up_due_on"
                              type="date"
                              className="gov-input"
                            />
                          </div>
                          <div className="gov-field gov-field-wide">
                            <label
                              htmlFor="completion_notes"
                              className="gov-label"
                            >
                              Completion notes <span className="gov-required" aria-hidden="true">*</span>
                            </label>
                            <textarea
                              id="completion_notes"
                              name="completion_notes"
                              rows={3}
                              maxLength={2000}
                              required
                              placeholder="e.g. Cleared affected shoots on east rows; regrowth check needed"
                              className="gov-textarea"
                            />
                          </div>
                          {detail.follow_up_due_on !== null && (
                            <div className="gov-inline-field gov-field-wide">
                              <input
                                id="reuse_planned_follow_up_date"
                                name="reuse_planned_follow_up_date"
                                type="checkbox"
                                className="h-4 w-4 rounded border-slate-300"
                              />
                              <label
                                htmlFor="reuse_planned_follow_up_date"
                                className="text-sm text-slate-700"
                              >
                                Reuse planned follow-up date ({detail.follow_up_due_on})
                              </label>
                            </div>
                          )}
                          <div className="gov-form-actions">
                            <button
                              type="submit"
                              disabled={completing || savingPlan}
                              className="gov-button gov-button-primary"
                            >
                              {completing ? "Saving..." : "Record completion"}
                            </button>
                          </div>
                        </form>
                      </div>
                    </div>
                  ) : (
                    <p role="status" className="gov-timeline-note">
                      Only an administrator or the assigned agriculture technician can edit or
                      complete this intervention.
                    </p>
                  )
                ) : (
                  <p role="status" className="gov-timeline-note">
                    This intervention is complete and read-only. Follow-up is pending
                    for {detail.follow_up_due_on ?? "an unset date"}.{" "}
                    <Link
                      href="/follow-ups"
                      className="gov-activity-link"
                    >
                      Go to follow-ups
                    </Link>
                  </p>
                )}
                {actionError && (
                  <p role="alert" className="gov-alert gov-alert-error mt-4">
                    {actionError}
                  </p>
                )}
              </div>
            ) : null}
          </section>
        )}
    </main>
  );
}
