"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { formatDisplayDate, workflowLabel, workflowMessage } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";
import {
  PageHeader,
  RequiredLegend,
  SessionNotice,
  useRevealOnChange,
} from "@/components/ui";
import { WorkflowSteps } from "@/components/workflow-steps";
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
  return `gov-status-badge gov-status-${status.toLowerCase().replaceAll("_", "-")}`;
}

function manilaTodayInputValue(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
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
  const detailRef = useRevealOnChange<HTMLElement>(loadingDetail ? null : selectedId);

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
    const today = manilaTodayInputValue();
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
    if (dateRaw.trim() < today) {
      setFormError("Scheduled inspection date cannot be in the past.");
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

      try {
        const [loadedInspections, loadedCases] = await Promise.all([
          listInspections(),
          listPestCases({ status: "FOR_INSPECTION" }),
        ]);
        setInspections(loadedInspections);
        setEligibleCases(loadedCases);
      } catch {
        setNotice(
          "Inspection was scheduled successfully, but the list could not be refreshed. Refresh the page to see the latest record.",
        );
      }
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
    const today = manilaTodayInputValue();
    if (typeof dateRaw === "string" && dateRaw.trim() !== "") {
      if (dateRaw.trim() < today) {
        setActionError("Scheduled inspection date cannot be in the past.");
        return;
      }
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

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
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
  const today = manilaTodayInputValue();

  // Confirmations about the open inspection are shown beside it, not in the form above.
  const detailNotice =
    notice !== null && detail !== null && notice.includes(`#${detail.id} `) ? notice : null;

  return (
    <main className="gov-page">
      <PageHeader
        title="Inspections"
        description="Schedule initial field inspections, reassign pending visits, and record validated findings. Reported area stays unchanged; validated area is the inspector's independent measurement."
        related={[
          { href: "/pest-cases", label: "Pest Cases" },
          { href: "/interventions", label: "Interventions" },
          { href: "/reports", label: "Reports" },
        ]}
      />
      <WorkflowSteps current="inspection" />

        {role === "ADMIN" && (
        <section aria-labelledby="schedule-heading" className="gov-card gov-record-section">
          <p className="gov-record-eyebrow">Inspection assignment</p>
          <h2 id="schedule-heading" className="gov-record-title">
            Schedule inspection
          </h2>
          <p className="gov-record-intro">
            Cases submitted for inspection are listed here. Choose the case, assign an
            Agriculture Technician, and set the inspection date.
          </p>
          {eligibleCases.length === 0 && !loading ? (
            <p role="status" className="gov-empty-state">
              No cases are waiting for inspection scheduling. Submit a Reported case
              for inspection first.{" "}
              <Link href="/pest-cases" className="gov-activity-link">
                Go to pest cases
              </Link>
            </p>
          ) : (
            <form
              noValidate
              onSubmit={handleSchedule}
              className="gov-form gov-form-grid"
            >
              <RequiredLegend />
              <div className="gov-field">
                <label
                  htmlFor="pest_case_id"
                  className="gov-label"
                >
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
                      #{entry.id} — {entry.pest_name} ({entry.reported_area_hectares.toFixed(2)} ha)
                    </option>
                  ))}
                </select>
              </div>
              <div className="gov-field">
                <label
                  htmlFor="assigned_to_user_id"
                  className="gov-label"
                >
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
                <label
                  htmlFor="scheduled_for"
                  className="gov-label"
                >
                  Scheduled inspection date <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="scheduled_for"
                  name="scheduled_for"
                  type="date"
                  required
                  min={today}
                  aria-describedby="scheduled_for_help"
                  className="gov-input"
                />
                <p id="scheduled_for_help" className="gov-field-help">
                  Select the date the assigned Agriculture Technician is expected to conduct the field inspection.
                </p>
              </div>
              <div className="gov-form-actions">
                <button
                  type="submit"
                  disabled={scheduling}
                  className="gov-button gov-button-primary"
                >
                  {scheduling ? "Scheduling..." : "Schedule inspection"}
                </button>
              </div>
            </form>
          )}
          {formError && (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {formError}
            </p>
          )}
          {notice && notice !== detailNotice && (
            <p role="status" className="gov-alert gov-alert-success mt-4">
              {workflowMessage(notice)}
            </p>
          )}
        </section>
        )}

        <section aria-labelledby="inspection-records-heading" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <div>
              <h2 id="inspection-records-heading" className="gov-record-title">
                Inspection records
              </h2>
              {!loading && listError === null && (
                <p className="gov-record-meta">
                  {inspections.length} {inspections.length === 1 ? "record" : "records"} shown
                </p>
              )}
            </div>
            <div className="gov-record-controls">
              <label
                htmlFor="technician_filter"
                className="gov-label"
              >
                Agriculture Technician
              </label>
              <select
                id="technician_filter"
                value={technicianFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setTechnicianFilter(next);
                  void loadAll(next);
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
                onClick={() => void loadAll(technicianFilter)}
                disabled={loading}
                className="gov-button gov-button-secondary gov-button-compact"
              >
                <Icon name="refresh" size={15} />
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loading ? (
            <p role="status" className="gov-loading-state">
              Loading inspections...
            </p>
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : inspections.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No inspection records available. Schedule the first inspection above.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[760px]">
                <thead>
                  <tr>
                    <th scope="col">Inspection</th>
                    <th scope="col">Case / Farm / Farmer</th>
                    <th scope="col">Agriculture Technician</th>
                    <th scope="col">Scheduled</th>
                    <th scope="col">Case status</th>
                    <th scope="col" className="gov-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {inspections.map((entry) => (
                    <tr
                      key={entry.id}
                      className={selectedId === entry.id ? "gov-row-selected" : undefined}
                    >
                      <td className="gov-cell-id">#{entry.id}</td>
                      <td>
                        <span className="gov-cell-primary">{entry.pest_case.pest_name}</span>
                        <span className="gov-cell-meta">
                          Case #{entry.pest_case_id} · {entry.pest_case.farm?.plot_identifier ?? "—"} —{" "}
                          {entry.pest_case.farm?.farmer?.full_name ?? "—"}
                        </span>
                      </td>
                      <td>
                        {entry.assigned_to?.full_name ?? `#${entry.assigned_to_user_id}`}
                        {entry.assigned_to_user_id === userId && (
                          <span className="gov-cell-meta">Assigned to you</span>
                        )}
                      </td>
                      <td className="gov-cell-nowrap">{formatDisplayDate(entry.scheduled_for)}</td>
                      <td>
                        <span
                          className={statusBadge(entry.pest_case.status)}
                        >
                          {workflowLabel(entry.pest_case.status)}
                        </span>
                      </td>
                      <td className="gov-col-actions">
                        <button
                          type="button"
                          onClick={() => void openDetail(entry.id)}
                          className="gov-button gov-button-secondary gov-button-compact"
                        >
                          {selectedId === entry.id ? "Selected" : "View"}
                          <span className="sr-only"> inspection #{entry.id}</span>
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
            ref={detailRef}
            tabIndex={-1}
            aria-label="Inspection detail"
            className="gov-card gov-record-section gov-record-section--selected"
          >
            {loadingDetail ? (
              <p role="status" className="gov-loading-state">
                Loading inspection details...
              </p>
            ) : detailError ? (
              <p role="alert" className="gov-alert gov-alert-error">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="gov-record-toolbar">
                  <div>
                    <p className="gov-record-eyebrow">
                      Inspection #{detail.id} · Case #{detail.pest_case_id}
                    </p>
                    <h2 className="gov-record-title">{detail.pest_case.pest_name}</h2>
                  </div>
                  <span className="gov-table-actions">
                    <span className={statusBadge(detail.pest_case.status)}>
                      {workflowLabel(detail.pest_case.status)}
                    </span>
                    <Link
                      href={`/pest-cases/${detail.pest_case_id}`}
                      className="gov-button gov-button-secondary gov-button-compact"
                    >
                      <Icon name="history" size={15} />
                      Open case record
                    </Link>
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
                    <dt className="gov-detail-label">Assigned Agriculture Technician</dt>
                    <dd className="gov-detail-value">
                      {detail.assigned_to?.full_name ?? `#${detail.assigned_to_user_id}`}
                      {detail.assigned_to_user_id === userId && " (you)"}
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Scheduled for</dt>
                    <dd className="gov-detail-value">{formatDisplayDate(detail.scheduled_for)}</dd>
                  </div>
                </dl>
                <div className="gov-compare">
                  <div className="gov-compare-panel gov-compare-panel--reported">
                    <div className="gov-compare-head">
                      <h3 className="gov-compare-title">
                        <Icon name="file-text" size={17} />
                        Initial report
                      </h3>
                      <span className="gov-tag">As reported</span>
                    </div>
                    <dl className="gov-detail-grid">
                      <div>
                        <dt className="gov-detail-label">Reported pest</dt>
                        <dd className="gov-detail-value">{detail.pest_case.pest_name}</dd>
                      </div>
                      <div>
                        <dt className="gov-detail-label">Reported area</dt>
                        <dd className="gov-detail-value">
                          {detail.pest_case.reported_area_hectares.toFixed(2)} ha (unchanged)
                        </dd>
                      </div>
                    </dl>
                  </div>
                  <div
                    className={`gov-compare-panel ${
                      detail.pest_confirmed === null
                        ? "gov-compare-panel--pending"
                        : detail.pest_confirmed
                          ? "gov-compare-panel--confirmed"
                          : "gov-compare-panel--not-confirmed"
                    }`}
                  >
                    <div className="gov-compare-head">
                      <h3 className="gov-compare-title">
                        <Icon name="inspection" size={17} />
                        Field validation result
                      </h3>
                      <span className={detail.pest_confirmed === null ? "gov-status-badge" : detail.pest_confirmed ? "gov-status-badge gov-status-field-validated" : "gov-status-badge gov-status-not-confirmed"}>
                      {detail.pest_confirmed === null
                        ? "Pending"
                        : detail.pest_confirmed
                          ? `Confirmed — ${(detail.validated_area_hectares ?? 0).toFixed(2)} ha`
                          : "Not confirmed — 0.00 ha"}
                      </span>
                    </div>
                    {detail.pest_confirmed === null ? (
                      <p className="gov-compare-caption">
                        Field findings have not been recorded yet. The reported information
                        remains unverified until field validation is recorded.
                      </p>
                    ) : (
                      <dl className="gov-detail-grid">
                        <div>
                          <dt className="gov-detail-label">Validated affected area</dt>
                          <dd className="gov-detail-value">
                            {(detail.validated_area_hectares ?? 0).toFixed(2)} ha
                          </dd>
                        </div>
                        <div>
                          <dt className="gov-detail-label">Inspected on</dt>
                          <dd className="gov-detail-value">{formatDisplayDate(detail.inspected_on)}</dd>
                        </div>
                        {detail.findings !== null && (
                          <div>
                            <dt className="gov-detail-label">Findings</dt>
                            <dd className="gov-detail-value">{detail.findings}</dd>
                          </div>
                        )}
                      </dl>
                    )}
                  </div>
                </div>

                {isPending(detail) && role === "ADMIN" ? (
                  <div className="gov-form">
                    <div className="gov-workflow-panel">
                      <h3 className="gov-record-title">
                        Reschedule or reassign
                      </h3>
                      <p className="gov-record-intro">
                        Change the inspection date or the assigned Agriculture Technician while
                        findings are pending. Leave a field blank to keep its current value.
                      </p>
                      <form
                        onSubmit={(event) => void handleReschedule(event, detail)}
                        className="gov-form gov-form-grid"
                      >
                        <div className="gov-field">
                          <label
                            htmlFor="reschedule_date"
                            className="gov-label"
                          >
                            New date <span className="gov-label-optional">(optional)</span>
                          </label>
                          <input
                            id="reschedule_date"
                            name="scheduled_for"
                            type="date"
                            min={today}
                            aria-describedby="reschedule_date_help"
                            className="gov-input"
                          />
                          <p id="reschedule_date_help" className="gov-field-help">
                            Select today or a future date for the expected field visit.
                          </p>
                        </div>
                        <div className="gov-field">
                          <label
                            htmlFor="reassign_technician"
                            className="gov-label"
                          >
                            New Agriculture Technician <span className="gov-label-optional">(optional)</span>
                          </label>
                          <select
                            id="reassign_technician"
                            name="assigned_to_user_id"
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
                        <div className="gov-form-actions">
                          <button
                            type="submit"
                            disabled={rescheduling || recording}
                            className="gov-button gov-button-secondary"
                          >
                            {rescheduling ? "Saving..." : "Save schedule"}
                          </button>
                        </div>
                      </form>
                    </div>
                    {canRecord(detail) ? (
                      <div className="gov-workflow-panel">
                        <div className="gov-panel-heading">
                          <span
                            className="gov-panel-heading-icon gov-panel-heading-icon--validation"
                            aria-hidden="true"
                          >
                            <Icon name="inspection" size={18} />
                          </span>
                          <div>
                            <h3 className="gov-record-title">Record field validation</h3>
                            <p className="gov-record-intro">
                              Record what was verified on site. Validated findings are stored
                              separately from the initial report, which stays unchanged.
                            </p>
                          </div>
                        </div>
                        <form
                          onSubmit={(event) => void handleRecordFindings(event, detail)}
                          className="gov-form gov-form-grid"
                        >
                          <RequiredLegend />
                          <div className="gov-field gov-field-wide">
                            <label
                              htmlFor="findings"
                              className="gov-label"
                            >
                              Field findings <span className="gov-required" aria-hidden="true">*</span>
                            </label>
                            <textarea
                              id="findings"
                              name="findings"
                              rows={3}
                              maxLength={2000}
                              required
                              placeholder="e.g. Bored stalks on east rows, frass present"
                              className="gov-textarea"
                            />
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="pest_confirmed"
                              className="gov-label"
                            >
                              Pest damage confirmed on site? <span className="gov-required" aria-hidden="true">*</span>
                            </label>
                            <select
                              id="pest_confirmed"
                              name="pest_confirmed"
                              required
                              defaultValue=""
                              className="gov-select"
                            >
                              <option value="" disabled>
                                Select confirmation
                              </option>
                              <option value="true">Yes — damage confirmed</option>
                              <option value="false">No — not confirmed</option>
                            </select>
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="validated_area_hectares"
                              className="gov-label"
                            >
                              Validated affected area (ha) <span className="gov-required" aria-hidden="true">*</span>
                            </label>
                            <input
                              id="validated_area_hectares"
                              name="validated_area_hectares"
                              type="number"
                              min={0}
                              max={10000}
                              step={0.01}
                              required
                              placeholder="e.g. 1.25"
                              aria-describedby="validated_area_help"
                              className="gov-input"
                            />
                            <p id="validated_area_help" className="gov-field-help">
                              Measured on site. Must be greater than 0 when damage is confirmed,
                              and 0 when it is not confirmed.
                            </p>
                          </div>
                          <div className="gov-field">
                            <label
                              htmlFor="inspected_on"
                              className="gov-label"
                            >
                              Inspection date <span className="gov-required" aria-hidden="true">*</span>
                            </label>
                            <input
                              id="inspected_on"
                              name="inspected_on"
                              type="date"
                              required
                              className="gov-input"
                            />
                          </div>
                          <div className="gov-form-actions">
                            <button
                              type="submit"
                              disabled={recording || rescheduling}
                              className="gov-button gov-button-primary"
                            >
                              {recording ? "Saving..." : "Save findings"}
                            </button>
                          </div>
                        </form>
                      </div>
                    ) : (
                      <p role="status" className="gov-callout">
                        Only an Administrator or the assigned Agriculture Technician can record
                        field findings for this inspection.
                      </p>
                    )}
                  </div>
                ) : (
                  <p role="status" className="gov-callout mt-4">
                    Findings have been recorded and can no longer be edited in this
                    phase.
                    {detail.pest_case.status === "FIELD_VALIDATED" && (
                      <>
                        {" "}
                        <Link href="/interventions" className="gov-activity-link">
                          Plan the intervention
                        </Link>
                      </>
                    )}
                  </p>
                )}
                {actionError && (
                  <p role="alert" className="gov-alert gov-alert-error mt-4">
                    {actionError}
                  </p>
                )}
                {detailNotice && (
                  <p role="status" className="gov-alert gov-alert-success">
                    {workflowMessage(detailNotice)}
                  </p>
                )}
              </div>
            ) : null}
          </section>
        )}
    </main>
  );
}
