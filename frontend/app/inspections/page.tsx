"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import {
  InspectionsRequestError,
  getInspection,
  listInspections,
  listTechnicians,
  recordFindings,
  rescheduleInspection,
  scheduleInspection,
  type InspectionDetail,
  type TechnicianSummary,
} from "@/lib/inspections";
import {
  PestCasesRequestError,
  listPestCases,
  type PestCaseSummary,
} from "@/lib/pest-cases";

const AREA_PATTERN = /^\d+(\.\d{1,2})?$/;

function parseArea(raw: string, allowZero: boolean): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return null;
  }
  if (!AREA_PATTERN.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value > 10000) {
    return null;
  }
  if (!allowZero && value <= 0) {
    return null;
  }
  if (allowZero && value < 0) {
    return null;
  }
  return value;
}

function statusBadge(status: string): string {
  if (status === "FIELD_VALIDATED") {
    return "bg-emerald-100 text-emerald-800";
  }
  if (status === "FOLLOW_UP_DUE") {
    return "bg-teal-100 text-teal-800";
  }
  if (status === "UNDER_INTERVENTION") {
    return "bg-violet-100 text-violet-800";
  }
  if (status === "REINTERVENTION_REQUIRED") {
    return "bg-orange-100 text-orange-800";
  }
  if (status === "CLOSED") {
    return "bg-slate-800 text-white";
  }
  if (status === "NOT_CONFIRMED") {
    return "bg-slate-200 text-slate-700";
  }
  if (status === "INSPECTION_SCHEDULED") {
    return "bg-violet-100 text-violet-800";
  }
  if (status === "FOR_INSPECTION") {
    return "bg-sky-100 text-sky-800";
  }
  return "bg-amber-100 text-amber-800";
}

function isPending(item: InspectionDetail): boolean {
  return (
    item.inspected_on === null &&
    item.findings === null &&
    item.pest_confirmed === null &&
    item.completed_at === null &&
    item.pest_case.status === "INSPECTION_SCHEDULED"
  );
}

export default function InspectionsPage() {
  const router = useRouter();
  const auth = useAuth();
  const [inspections, setInspections] = useState<InspectionDetail[]>([]);
  const [eligibleCases, setEligibleCases] = useState<PestCaseSummary[]>([]);
  const [technicians, setTechnicians] = useState<TechnicianSummary[]>([]);
  const [technicianFilter, setTechnicianFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [scheduling, setScheduling] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<InspectionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [rescheduling, setRescheduling] = useState(false);
  const [recording, setRecording] = useState(false);
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
    async (assignedFilter: string) => {
      setLoading(true);
      setListError(null);
      try {
        const [loadedInspections, loadedCases, loadedTechnicians] = await Promise.all([
          listInspections({
            assignedToUserId:
              assignedFilter === "all" ? undefined : Number(assignedFilter),
          }),
          listPestCases({ status: "FOR_INSPECTION" }),
          listTechnicians(),
        ]);
        setInspections(loadedInspections);
        setEligibleCases(loadedCases);
        setTechnicians(loadedTechnicians);
      } catch (failure) {
        if (
          (failure instanceof InspectionsRequestError &&
            failure.kind === "unauthenticated") ||
          (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof InspectionsRequestError ||
            failure instanceof PestCasesRequestError
            ? failure.message
            : "Inspection records could not be read.",
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
        const [loadedInspections, loadedCases, loadedTechnicians] = await Promise.all([
          listInspections(),
          listPestCases({ status: "FOR_INSPECTION" }),
          listTechnicians(),
        ]);
        if (!active) {
          return;
        }
        setInspections(loadedInspections);
        setEligibleCases(loadedCases);
        setTechnicians(loadedTechnicians);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          (failure instanceof InspectionsRequestError &&
            failure.kind === "unauthenticated") ||
          (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof InspectionsRequestError ||
            failure instanceof PestCasesRequestError
            ? failure.message
            : "Inspection records could not be read.",
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
    async (inspectionId: number) => {
      setSelectedId(inspectionId);
      setDetail(null);
      setDetailError(null);
      setActionError(null);
      setLoadingDetail(true);
      try {
        setDetail(await getInspection(inspectionId));
      } catch (failure) {
        if (
          failure instanceof InspectionsRequestError &&
          failure.kind === "unauthenticated"
        ) {
          router.replace("/login");
          return;
        }
        setDetailError(
          failure instanceof InspectionsRequestError
            ? failure.message
            : "Inspection could not be read.",
        );
      } finally {
        setLoadingDetail(false);
      }
    },
    [router],
  );

  async function handleSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const data = new FormData(event.currentTarget);
    const caseRaw = data.get("pest_case_id");
    const techRaw = data.get("assigned_to_user_id");
    const dateRaw = data.get("scheduled_for");
    const caseId = typeof caseRaw === "string" ? Number(caseRaw) : NaN;
    const technicianId = typeof techRaw === "string" ? Number(techRaw) : NaN;
    if (
      !Number.isSafeInteger(caseId) ||
      caseId <= 0 ||
      !Number.isSafeInteger(technicianId) ||
      technicianId <= 0 ||
      typeof dateRaw !== "string" ||
      dateRaw.trim() === ""
    ) {
      setFormError("Select an eligible case, a technician, and an inspection date.");
      return;
    }
    setScheduling(true);
    setFormError(null);
    setNotice(null);
    try {
      const created = await scheduleInspection(
        caseId,
        { scheduled_for: dateRaw.trim(), assigned_to_user_id: technicianId },
        auth.csrfToken,
      );
      setInspections((current) =>
        [...current, created].sort((left, right) => left.id - right.id),
      );
      setEligibleCases((current) => current.filter((entry) => entry.id !== caseId));
      setNotice(`Inspection #${created.id} was scheduled.`);
      event.currentTarget.reset();
    } catch (failure) {
      if (
        failure instanceof InspectionsRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setFormError(
        failure instanceof InspectionsRequestError
          ? failure.message
          : "Inspection could not be scheduled.",
      );
    } finally {
      setScheduling(false);
    }
  }

  async function handleReschedule(
    event: FormEvent<HTMLFormElement>,
    target: InspectionDetail,
  ) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const data = new FormData(event.currentTarget);
    const dateRaw = data.get("scheduled_for");
    const techRaw = data.get("assigned_to_user_id");
    const payload: { scheduled_for?: string; assigned_to_user_id?: number } = {};
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
    if (Object.keys(payload).length === 0) {
      setActionError("Change the date or technician before rescheduling.");
      return;
    }
    setRescheduling(true);
    setActionError(null);
    try {
      const updated = await rescheduleInspection(target.id, payload, auth.csrfToken);
      setDetail(updated);
      setInspections((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setNotice(`Inspection #${updated.id} was rescheduled.`);
    } catch (failure) {
      if (
        failure instanceof InspectionsRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setActionError(
        failure instanceof InspectionsRequestError
          ? failure.message
          : "Inspection could not be rescheduled.",
      );
    } finally {
      setRescheduling(false);
    }
  }

  async function handleRecordFindings(
    event: FormEvent<HTMLFormElement>,
    target: InspectionDetail,
  ) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const data = new FormData(event.currentTarget);
    const findingsRaw = data.get("findings");
    const confirmedRaw = data.get("pest_confirmed");
    const areaRaw = data.get("validated_area_hectares");
    const inspectedRaw = data.get("inspected_on");
    if (
      typeof findingsRaw !== "string" ||
      findingsRaw.trim() === "" ||
      (confirmedRaw !== "true" && confirmedRaw !== "false") ||
      typeof areaRaw !== "string" ||
      typeof inspectedRaw !== "string" ||
      inspectedRaw.trim() === ""
    ) {
      setActionError(
        "Enter findings, confirmation choice, validated area, and inspection date.",
      );
      return;
    }
    const pestConfirmed = confirmedRaw === "true";
    const area = parseArea(areaRaw, true);
    if (area === null) {
      setActionError("Validated area must be 0–10000 ha with up to 2 decimals.");
      return;
    }
    if (pestConfirmed && area <= 0) {
      setActionError("Validated area must be positive when damage is confirmed.");
      return;
    }
    if (!pestConfirmed && area !== 0) {
      setActionError("Validated area must be zero when damage is not confirmed.");
      return;
    }
    setRecording(true);
    setActionError(null);
    try {
      const updated = await recordFindings(
        target.id,
        {
          findings: findingsRaw.trim(),
          pest_confirmed: pestConfirmed,
          validated_area_hectares: area,
          inspected_on: inspectedRaw.trim(),
        },
        auth.csrfToken,
      );
      setDetail(updated);
      setInspections((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setNotice(
        `Findings for inspection #${updated.id} were saved as ${updated.pest_case.status}.`,
      );
    } catch (failure) {
      if (
        failure instanceof InspectionsRequestError &&
        failure.kind === "unauthenticated"
      ) {
        router.replace("/login");
        return;
      }
      setActionError(
        failure instanceof InspectionsRequestError
          ? failure.message
          : "Inspection findings could not be saved.",
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

  const canRecord = (item: InspectionDetail): boolean => {
    if (!isPending(item)) {
      return false;
    }
    if (role === "ADMIN") {
      return true;
    }
    return role === "TECHNICIAN" && item.assigned_to_user_id === userId;
  };

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">
          Inspection Scheduling
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Schedule initial field inspections, reassign pending visits, and record
          validated findings. Reported area stays unchanged; validated area is the
          inspector&apos;s independent measurement.
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
        </div>

        <section aria-label="Schedule inspection" className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Schedule inspection</h2>
          {eligibleCases.length === 0 && !loading ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No cases are waiting for inspection scheduling. Submit a REPORTED case
              for inspection first.
            </p>
          ) : (
            <form onSubmit={handleSchedule} className="mt-4 grid gap-4 sm:grid-cols-3">
              <div>
                <label
                  htmlFor="pest_case_id"
                  className="block text-sm font-medium text-slate-700"
                >
                  Eligible case
                </label>
                <select
                  id="pest_case_id"
                  name="pest_case_id"
                  required
                  className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900"
                >
                  <option value="" disabled selected>
                    Select a case
                  </option>
                  {eligibleCases.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      #{entry.id} — {entry.pest_name} ({entry.reported_area_hectares.toFixed(2)} ha)
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="assigned_to_user_id"
                  className="block text-sm font-medium text-slate-700"
                >
                  Assigned technician
                </label>
                <select
                  id="assigned_to_user_id"
                  name="assigned_to_user_id"
                  required
                  className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900"
                >
                  <option value="" disabled selected>
                    Select a technician
                  </option>
                  {technicians.map((tech) => (
                    <option key={tech.id} value={tech.id}>
                      {tech.full_name} ({tech.username})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="scheduled_for"
                  className="block text-sm font-medium text-slate-700"
                >
                  Inspection date
                </label>
                <input
                  id="scheduled_for"
                  name="scheduled_for"
                  type="date"
                  required
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                />
              </div>
              <div className="sm:col-span-3">
                <button
                  type="submit"
                  disabled={scheduling}
                  className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                >
                  {scheduling ? "Scheduling..." : "Schedule inspection"}
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

        <section aria-label="Inspection records" className="mt-10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Inspection records</h2>
            <div className="flex flex-wrap items-center gap-2">
              <label
                htmlFor="technician_filter"
                className="text-sm font-medium text-slate-700"
              >
                Technician
              </label>
              <select
                id="technician_filter"
                value={technicianFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setTechnicianFilter(next);
                  void loadAll(next);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
              >
                <option value="all">All technicians</option>
                {technicians.map((tech) => (
                  <option key={tech.id} value={tech.id}>
                    {tech.full_name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void loadAll(technicianFilter)}
                disabled={loading}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
              >
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loading ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading inspections...
            </p>
          ) : listError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {listError}
            </p>
          ) : inspections.length === 0 ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No inspections found. Schedule the first inspection above.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Inspection</th>
                    <th scope="col" className="px-4 py-3 font-medium">Case / Farm / Farmer</th>
                    <th scope="col" className="px-4 py-3 font-medium">Technician</th>
                    <th scope="col" className="px-4 py-3 font-medium">Scheduled</th>
                    <th scope="col" className="px-4 py-3 font-medium">Status</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {inspections.map((entry) => (
                    <tr key={entry.id}>
                      <td className="px-4 py-3 text-slate-900">#{entry.id}</td>
                      <td className="px-4 py-3 text-slate-900">
                        #{entry.pest_case_id} — {entry.pest_case.pest_name}
                        <span className="block text-xs text-slate-600">
                          {entry.pest_case.farm?.plot_identifier ?? "—"} —{" "}
                          {entry.pest_case.farm?.farmer?.full_name ?? "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-900">
                        {entry.assigned_to?.full_name ?? `#${entry.assigned_to_user_id}`}
                      </td>
                      <td className="px-4 py-3 text-slate-900">{entry.scheduled_for}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadge(entry.pest_case.status)}`}
                        >
                          {entry.pest_case.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => void openDetail(entry.id)}
                          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                        >
                          {selectedId === entry.id ? "Selected" : "View"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selectedId !== null && (
          <section
            aria-label="Inspection detail"
            className="mt-8 rounded-xl border border-slate-200 p-6"
          >
            {loadingDetail ? (
              <p role="status" className="text-sm text-slate-600">
                Loading inspection details...
              </p>
            ) : detailError ? (
              <p role="alert" className="text-sm text-red-700">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold text-slate-900">
                    Inspection #{detail.id} — {detail.pest_case.pest_name}
                  </h2>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadge(detail.pest_case.status)}`}
                  >
                    {detail.pest_case.status}
                  </span>
                </div>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="font-medium text-slate-600">Farm plot</dt>
                    <dd className="text-slate-900">
                      {detail.pest_case.farm?.plot_identifier ?? "—"} —{" "}
                      {detail.pest_case.farm?.barangay ?? "—"} (
                      {(detail.pest_case.farm?.area_hectares ?? 0).toFixed(2)} ha)
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Farmer</dt>
                    <dd className="text-slate-900">
                      {detail.pest_case.farm?.farmer?.full_name ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Reported area</dt>
                    <dd className="text-slate-900">
                      {detail.pest_case.reported_area_hectares.toFixed(2)} ha (unchanged)
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Assigned technician</dt>
                    <dd className="text-slate-900">
                      {detail.assigned_to?.full_name ?? `#${detail.assigned_to_user_id}`}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Scheduled for</dt>
                    <dd className="text-slate-900">{detail.scheduled_for}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Field result</dt>
                    <dd className="text-slate-900">
                      {detail.pest_confirmed === null
                        ? "Pending"
                        : detail.pest_confirmed
                          ? `Confirmed — ${(detail.validated_area_hectares ?? 0).toFixed(2)} ha`
                          : "Not confirmed — 0.00 ha"}
                    </dd>
                  </div>
                  {detail.findings !== null && (
                    <div className="sm:col-span-2">
                      <dt className="font-medium text-slate-600">Findings</dt>
                      <dd className="text-slate-900">{detail.findings}</dd>
                    </div>
                  )}
                </dl>

                {isPending(detail) ? (
                  <div className="mt-6 grid gap-6">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900">
                        Reschedule or reassign
                      </h3>
                      <form
                        onSubmit={(event) => void handleReschedule(event, detail)}
                        className="mt-3 grid gap-4 sm:grid-cols-3"
                      >
                        <div>
                          <label
                            htmlFor="reschedule_date"
                            className="block text-sm font-medium text-slate-700"
                          >
                            New date (optional)
                          </label>
                          <input
                            id="reschedule_date"
                            name="scheduled_for"
                            type="date"
                            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                          />
                        </div>
                        <div>
                          <label
                            htmlFor="reassign_technician"
                            className="block text-sm font-medium text-slate-700"
                          >
                            New technician (optional)
                          </label>
                          <select
                            id="reassign_technician"
                            name="assigned_to_user_id"
                            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900"
                          >
                            <option value="">Keep current</option>
                            {technicians.map((tech) => (
                              <option key={tech.id} value={tech.id}>
                                {tech.full_name} ({tech.username})
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="flex items-end">
                          <button
                            type="submit"
                            disabled={rescheduling || recording}
                            className="rounded-lg bg-sky-700 px-4 py-2 font-medium text-white hover:bg-sky-800 disabled:cursor-wait disabled:opacity-60"
                          >
                            {rescheduling ? "Saving..." : "Save schedule"}
                          </button>
                        </div>
                      </form>
                    </div>
                    {canRecord(detail) ? (
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">
                          Record field findings
                        </h3>
                        <form
                          onSubmit={(event) => void handleRecordFindings(event, detail)}
                          className="mt-3 grid gap-4 sm:grid-cols-2"
                        >
                          <div className="sm:col-span-2">
                            <label
                              htmlFor="findings"
                              className="block text-sm font-medium text-slate-700"
                            >
                              Findings
                            </label>
                            <textarea
                              id="findings"
                              name="findings"
                              rows={3}
                              maxLength={2000}
                              required
                              placeholder="e.g. Bored stalks on east rows, frass present"
                              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                            />
                          </div>
                          <div>
                            <label
                              htmlFor="pest_confirmed"
                              className="block text-sm font-medium text-slate-700"
                            >
                              Pest damage confirmed?
                            </label>
                            <select
                              id="pest_confirmed"
                              name="pest_confirmed"
                              required
                              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900"
                            >
                              <option value="" disabled selected>
                                Select confirmation
                              </option>
                              <option value="true">Yes — damage confirmed</option>
                              <option value="false">No — not confirmed</option>
                            </select>
                          </div>
                          <div>
                            <label
                              htmlFor="validated_area_hectares"
                              className="block text-sm font-medium text-slate-700"
                            >
                              Validated affected area (ha)
                            </label>
                            <input
                              id="validated_area_hectares"
                              name="validated_area_hectares"
                              type="number"
                              min={0}
                              max={10000}
                              step={0.01}
                              required
                              placeholder="e.g. 1.25 (0 when not confirmed)"
                              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                            />
                          </div>
                          <div>
                            <label
                              htmlFor="inspected_on"
                              className="block text-sm font-medium text-slate-700"
                            >
                              Inspection date
                            </label>
                            <input
                              id="inspected_on"
                              name="inspected_on"
                              type="date"
                              required
                              className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900"
                            />
                          </div>
                          <div className="flex items-end">
                            <button
                              type="submit"
                              disabled={recording || rescheduling}
                              className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                            >
                              {recording ? "Saving..." : "Save findings"}
                            </button>
                          </div>
                        </form>
                      </div>
                    ) : (
                      <p role="status" className="text-sm text-slate-600">
                        Only an administrator or the assigned technician can record
                        findings for this inspection.
                      </p>
                    )}
                  </div>
                ) : (
                  <p role="status" className="mt-6 text-sm text-slate-600">
                    Findings have been recorded and can no longer be edited in this
                    phase.
                  </p>
                )}
                {actionError && (
                  <p role="alert" className="mt-4 text-sm text-red-700">
                    {actionError}
                  </p>
                )}
              </div>
            ) : null}
          </section>
        )}
      </div>
    </main>
  );
}
