"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { workflowLabel } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import {
  FarmsRequestError,
  listFarms,
  type FarmWithFarmer,
} from "@/lib/farms";
import {
  PestCasesRequestError,
  createPestCase,
  getPestCase,
  listPestCases,
  submitForInspection,
  updatePestCase,
  type PestCaseDetail,
  type PestCaseStatus,
  type PestCaseSummary,
} from "@/lib/pest-cases";

const AREA_PATTERN = /^\d+(\.\d{1,2})?$/;

function parseArea(raw: string): number | null {
  const trimmed = raw.trim();
  if (!AREA_PATTERN.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value <= 0 || value > 10000) {
    return null;
  }
  return value;
}

function statusBadge(status: PestCaseStatus): string {
  return `gov-status-badge gov-status-${status.toLowerCase().replaceAll("_", "-")}`;
}

function PestCasesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const [farms, setFarms] = useState<FarmWithFarmer[]>([]);
  const [cases, setCases] = useState<PestCaseSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState<"all" | PestCaseStatus>("all");
  const [farmFilter, setFarmFilter] = useState<string>("all");
  const [farmerFilter, setFarmerFilter] = useState<string>("all");
  const [searchInput, setSearchInput] = useState<string>("");
  const [reportedFrom, setReportedFrom] = useState<string>("");
  const [reportedTo, setReportedTo] = useState<string>("");
  const [filterError, setFilterError] = useState<string | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formNotice, setFormNotice] = useState<string | null>(null);
  const [preselectedFarmId, setPreselectedFarmId] = useState<string>(() => {
    const raw = searchParams.get("farm_id");
    if (raw === null || raw === "") {
      return "";
    }
    const parsed = Number(raw);
    return Number.isSafeInteger(parsed) && parsed > 0 ? String(parsed) : "";
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<PestCaseDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const authenticated = auth.status === "authenticated";

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const loadAll = useCallback(
    async (options: {
      status: "all" | PestCaseStatus;
      farmId: string;
      farmerId: string;
      q: string;
      from: string;
      to: string;
    }) => {
      const trimmedQ = options.q.trim();
      if (trimmedQ.length > 120) {
        setFilterError("Search text must be at most 120 characters.");
        return;
      }
      if (options.from !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(options.from)) {
        setFilterError("Reported-from must use YYYY-MM-DD format.");
        return;
      }
      if (options.to !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(options.to)) {
        setFilterError("Reported-to must use YYYY-MM-DD format.");
        return;
      }
      if (options.from !== "" && options.to !== "" && options.from > options.to) {
        setFilterError("Reported-from must not be later than reported-to.");
        return;
      }
      setFilterError(null);
      setLoadingList(true);
      setListError(null);
      try {
        const [loadedFarms, loadedCases] = await Promise.all([
          listFarms(),
          listPestCases({
            status: options.status,
            farmId: options.farmId === "all" ? undefined : Number(options.farmId),
            farmerId: options.farmerId === "all" ? undefined : Number(options.farmerId),
            q: trimmedQ === "" ? undefined : trimmedQ,
            reportedFrom: options.from === "" ? undefined : options.from,
            reportedTo: options.to === "" ? undefined : options.to,
          }),
        ]);
        setFarms(loadedFarms);
        setCases(loadedCases);
      } catch (failure) {
        if (
          (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") ||
          (failure instanceof FarmsRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        if (failure instanceof PestCasesRequestError && failure.kind === "invalid") {
          setFilterError(failure.message);
          return;
        }
        setListError(
          failure instanceof PestCasesRequestError || failure instanceof FarmsRequestError
            ? failure.message
            : "Pest case records could not be read.",
        );
      } finally {
        setLoadingList(false);
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
      setLoadingList(true);
      try {
        const [loadedFarms, loadedCases] = await Promise.all([
          listFarms(),
          listPestCases(),
        ]);
        if (!active) {
          return;
        }
        setFarms(loadedFarms);
        setCases(loadedCases);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") ||
          (failure instanceof FarmsRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof PestCasesRequestError || failure instanceof FarmsRequestError
            ? failure.message
            : "Pest case records could not be read.",
        );
      } finally {
        if (active) {
          setLoadingList(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [authenticated, router, searchParams]);

  const openDetail = useCallback(
    async (caseId: number) => {
      setSelectedId(caseId);
      setDetail(null);
      setDetailError(null);
      setEditError(null);
      setActionError(null);
      setLoadingDetail(true);
      try {
        setDetail(await getPestCase(caseId));
      } catch (failure) {
        if (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setDetailError(
          failure instanceof PestCasesRequestError
            ? failure.message
            : "Pest case could not be read.",
        );
      } finally {
        setLoadingDetail(false);
      }
    },
    [router],
  );

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const farmIdRaw = data.get("farm_id");
    const pestName = data.get("pest_name");
    const symptoms = data.get("symptoms");
    const observedOn = data.get("observed_on");
    const areaRaw = data.get("reported_area_hectares");
    const farmId = typeof farmIdRaw === "string" ? Number(farmIdRaw) : NaN;
    const area = typeof areaRaw === "string" ? parseArea(areaRaw) : null;
    if (
      !Number.isSafeInteger(farmId) ||
      farmId <= 0 ||
      typeof pestName !== "string" ||
      pestName.trim() === "" ||
      area === null ||
      (symptoms !== null && typeof symptoms !== "string") ||
      (observedOn !== null && typeof observedOn !== "string")
    ) {
      setFormError(
        "Select a farm and enter a pest name and affected area (0–10000 ha, up to 2 decimals).",
      );
      return;
    }
    setCreating(true);
    setFormError(null);
    setFormNotice(null);
    try {
      const created = await createPestCase(
        {
          farm_id: farmId,
          pest_name: pestName.trim(),
          symptoms:
            symptoms === null || symptoms.trim() === "" ? undefined : symptoms.trim(),
          observed_on:
            observedOn === null || observedOn.trim() === "" ? undefined : observedOn.trim(),
          reported_area_hectares: area,
        },
        auth.csrfToken,
      );
      setCases((current) =>
        [
          ...current,
          {
            id: created.id,
            farm_id: created.farm_id,
            pest_name: created.pest_name,
            reported_area_hectares: created.reported_area_hectares,
            status: created.status,
            observed_on: created.observed_on,
            reported_at: created.reported_at,
          },
        ].sort((left, right) => left.id - right.id),
      );
      setFormNotice(`Pest case for ${created.pest_name} was reported.`);
      form.reset();
      setPreselectedFarmId("");
    } catch (failure) {
      if (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setFormError(
        failure instanceof PestCasesRequestError
          ? failure.message
          : "Pest case could not be reported.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>, target: PestCaseDetail) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const data = new FormData(event.currentTarget);
    const pestName = data.get("pest_name");
    const symptoms = data.get("symptoms");
    const observedOn = data.get("observed_on");
    const areaRaw = data.get("reported_area_hectares");
    const area = typeof areaRaw === "string" ? parseArea(areaRaw) : null;
    if (
      typeof pestName !== "string" ||
      pestName.trim() === "" ||
      area === null ||
      (symptoms !== null && typeof symptoms !== "string") ||
      (observedOn !== null && typeof observedOn !== "string")
    ) {
      setEditError("Pest name and affected area (0–10000 ha, up to 2 decimals) are required.");
      return;
    }
    setSavingEdit(true);
    setEditError(null);
    try {
      const updated = await updatePestCase(
        target.id,
        {
          pest_name: pestName.trim(),
          symptoms: symptoms === null || symptoms.trim() === "" ? null : symptoms.trim(),
          observed_on:
            observedOn === null || observedOn.trim() === "" ? null : observedOn.trim(),
          reported_area_hectares: area,
        },
        auth.csrfToken,
      );
      setDetail(updated);
      setCases((current) =>
        current.map((entry) =>
          entry.id === updated.id
            ? {
                id: updated.id,
                farm_id: updated.farm_id,
                pest_name: updated.pest_name,
                reported_area_hectares: updated.reported_area_hectares,
                status: updated.status,
                observed_on: updated.observed_on,
                reported_at: updated.reported_at,
              }
            : entry,
        ),
      );
      setFormNotice(`Pest case for ${updated.pest_name} was updated.`);
    } catch (failure) {
      if (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setEditError(
        failure instanceof PestCasesRequestError
          ? failure.message
          : "Pest case could not be updated.",
      );
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleSubmit(target: PestCaseDetail) {
    if (auth.status !== "authenticated") {
      return;
    }
    setSubmitting(true);
    setActionError(null);
    try {
      const updated = await submitForInspection(target.id, auth.csrfToken);
      setDetail(updated);
      setCases((current) =>
        current.map((entry) =>
          entry.id === updated.id ? { ...entry, status: updated.status } : entry,
        ),
      );
      setFormNotice(`Pest case for ${updated.pest_name} was submitted for inspection.`);
    } catch (failure) {
      if (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setActionError(
        failure instanceof PestCasesRequestError
          ? failure.message
          : "Pest case could not be submitted for inspection.",
      );
    } finally {
      setSubmitting(false);
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

  return (
    <main className="gov-page">
      <header className="gov-page-header">
        <h1 className="gov-page-title">Pest Cases</h1>
        <p className="gov-page-description">
          Record and manage reported sugarcane pest cases through the inspection and
          intervention workflow.
        </p>
      </header>

        <section aria-label="Report pest case" className="gov-card gov-record-section">
          <h2 className="gov-record-title">Report pest case</h2>
          <p className="gov-field-help">
            Reported area is a pre-inspection estimate and must not exceed the farm&apos;s recorded sugarcane area.
          </p>
          {farms.length === 0 && !loadingList ? (
            <p role="status" className="gov-empty-state">
              Record a farm first before reporting a pest case.{" "}
              <Link href="/farms" className="gov-activity-link">
                Go to farms
              </Link>
            </p>
          ) : (
            <form onSubmit={handleCreate} className="gov-form gov-form-grid">
              <div className="gov-field">
                <label htmlFor="farm_id" className="gov-label">
                  Farm <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <select
                  id="farm_id"
                  name="farm_id"
                  required
                  value={preselectedFarmId}
                  onChange={(event) => setPreselectedFarmId(event.target.value)}
                  className="gov-select"
                >
                  <option value="" disabled>
                    Select a farm
                  </option>
                  {farms.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.plot_identifier} — {entry.farmer.full_name} (
                      {entry.area_hectares.toFixed(2)} ha)
                    </option>
                  ))}
                </select>
              </div>
              <div className="gov-field">
                <label htmlFor="pest_name" className="gov-label">
                  Pest name <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="pest_name"
                  name="pest_name"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  required
                  placeholder="e.g. Stem Borer"
                  className="gov-input"
                />
              </div>
              <div className="gov-field gov-field-wide">
                <label htmlFor="symptoms" className="gov-label">
                  Symptoms / observations (optional)
                </label>
                <textarea
                  id="symptoms"
                  name="symptoms"
                  rows={3}
                  maxLength={2000}
                  placeholder="e.g. Bored stalks and wilting shoots on the east rows"
                  className="gov-textarea"
                />
              </div>
              <div className="gov-field">
                <label htmlFor="observed_on" className="gov-label">
                  Observation date (optional)
                </label>
                <input
                  id="observed_on"
                  name="observed_on"
                  type="date"
                  className="gov-input"
                />
              </div>
              <div className="gov-field">
                <label htmlFor="reported_area_hectares" className="gov-label">
                  Estimated affected area (hectares) <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="reported_area_hectares"
                  name="reported_area_hectares"
                  type="number"
                  min={0.01}
                  max={10000}
                  step={0.01}
                  required
                  placeholder="e.g. 1.25"
                  className="gov-input"
                />
              </div>
              <div className="gov-form-actions">
                <button
                  type="submit"
                  disabled={creating}
                  className="gov-button gov-button-primary"
                >
                  {creating ? "Reporting..." : "Report pest case"}
                </button>
              </div>
            </form>
          )}
          {formError && (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {formError}
            </p>
          )}
          {formNotice && (
            <p role="status" className="gov-alert gov-alert-success mt-4">
              {formNotice}
            </p>
          )}
        </section>

        <section aria-label="Pest case records" className="gov-card gov-record-section">
          <h2 className="gov-record-title">Pest case records</h2>
          <form
            aria-label="Search and filter pest cases"
            onSubmit={(event) => {
              event.preventDefault();
              void loadAll({
                status: statusFilter,
                farmId: farmFilter,
                farmerId: farmerFilter,
                q: searchInput,
                from: reportedFrom,
                to: reportedTo,
              });
            }}
            className="gov-form gov-record-filters"
          >
            <div className="gov-field">
              <label htmlFor="case_search" className="gov-label">
                Search (pest, farmer, plot, barangay, ID)
              </label>
              <input
                id="case_search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                maxLength={120}
                autoComplete="off"
                placeholder="e.g. Stem Borer, Juan, Plot A, Bunao"
                className="gov-input"
              />
            </div>
            <div className="gov-field">
              <label htmlFor="status_filter" className="gov-label">
                Status
              </label>
              <select
                id="status_filter"
                value={statusFilter}
                onChange={(event) => {
                  const next = event.target.value as "all" | PestCaseStatus;
                  setStatusFilter(next);
                }}
                className="gov-select"
              >
                <option value="all">All statuses</option>
                <option value="REPORTED">{workflowLabel("REPORTED")}</option>
                <option value="FOR_INSPECTION">{workflowLabel("FOR_INSPECTION")}</option>
                <option value="INSPECTION_SCHEDULED">{workflowLabel("INSPECTION_SCHEDULED")}</option>
                <option value="NOT_CONFIRMED">{workflowLabel("NOT_CONFIRMED")}</option>
                <option value="FIELD_VALIDATED">{workflowLabel("FIELD_VALIDATED")}</option>
                <option value="UNDER_INTERVENTION">{workflowLabel("UNDER_INTERVENTION")}</option>
                <option value="FOLLOW_UP_DUE">{workflowLabel("FOLLOW_UP_DUE")}</option>
                <option value="REINTERVENTION_REQUIRED">{workflowLabel("REINTERVENTION_REQUIRED")}</option>
                <option value="CLOSED">{workflowLabel("CLOSED")}</option>
              </select>
            </div>
            <div className="gov-field">
              <label htmlFor="farm_filter" className="gov-label">
                Farm
              </label>
              <select
                id="farm_filter"
                value={farmFilter}
                onChange={(event) => setFarmFilter(event.target.value)}
                className="gov-select"
              >
                <option value="all">All farms</option>
                {farms.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.plot_identifier} — {entry.farmer.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="gov-field">
              <label htmlFor="farmer_filter" className="gov-label">
                Farmer ID
              </label>
              <input
                id="farmer_filter"
                value={farmerFilter === "all" ? "" : farmerFilter}
                onChange={(event) => {
                  const next = event.target.value.trim() === "" ? "all" : event.target.value.trim();
                  setFarmerFilter(next);
                }}
                placeholder="All"
                inputMode="numeric"
                className="gov-input"
              />
            </div>
            <div className="gov-field">
              <label htmlFor="reported_from" className="gov-label">
                Reported from
              </label>
              <input
                id="reported_from"
                type="date"
                value={reportedFrom}
                onChange={(event) => setReportedFrom(event.target.value)}
                className="gov-input"
              />
            </div>
            <div className="gov-field">
              <label htmlFor="reported_to" className="gov-label">
                Reported to
              </label>
              <input
                id="reported_to"
                type="date"
                value={reportedTo}
                onChange={(event) => setReportedTo(event.target.value)}
                className="gov-input"
              />
            </div>
            <div className="gov-form-actions">
              <button
                type="submit"
                disabled={loadingList}
                className="gov-button gov-button-primary gov-button-compact"
              >
                {loadingList ? "Searching..." : "Search"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStatusFilter("all");
                  setFarmFilter("all");
                  setFarmerFilter("all");
                  setSearchInput("");
                  setReportedFrom("");
                  setReportedTo("");
                  setFilterError(null);
                  void loadAll({
                    status: "all",
                    farmId: "all",
                    farmerId: "all",
                    q: "",
                    from: "",
                    to: "",
                  });
                }}
                disabled={loadingList}
                className="gov-button gov-button-secondary gov-button-compact"
              >
                Clear filters
              </button>
            </div>
          </form>
          {filterError && (
            <p role="alert" className="gov-alert gov-alert-error mt-3">
              {filterError}
            </p>
          )}
          {loadingList ? (
            <p role="status" className="gov-empty-state">
              Loading pest cases...
            </p>
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : cases.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No pest cases found. Report the first case above.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[720px]">
                <thead>
                  <tr>
                    <th scope="col">Pest</th>
                    <th scope="col">Area (ha)</th>
                    <th scope="col">Status</th>
                    <th scope="col">Observed</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((entry) => (
                    <tr key={entry.id}>
                      <td>{entry.pest_name}</td>
                      <td>
                        {entry.reported_area_hectares.toFixed(2)}
                      </td>
                      <td>
                        <span
                          className={statusBadge(entry.status)}
                        >
                          {workflowLabel(entry.status)}
                        </span>
                      </td>
                      <td>{entry.observed_on ?? "—"}</td>
                      <td>
                        <div className="gov-table-actions">
                          <button
                            type="button"
                            onClick={() => void openDetail(entry.id)}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            {selectedId === entry.id ? "Selected" : "View"}
                          </button>
                          <Link
                            href={`/pest-cases/${entry.id}`}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            Timeline
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selectedId !== null && (
          <section aria-label="Pest case detail" className="gov-card gov-record-section">
            {loadingDetail ? (
              <p role="status" className="gov-page-description">
                Loading pest case details...
              </p>
            ) : detailError ? (
              <p role="alert" className="gov-alert gov-alert-error">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="gov-record-toolbar">
                  <h2 className="gov-record-title">
                    {detail.pest_name}
                  </h2>
                  <span className="gov-table-actions">
                    <span
                      className={statusBadge(detail.status)}
                    >
                      {workflowLabel(detail.status)}
                    </span>
                    <Link
                      href={`/pest-cases/${detail.id}`}
                      className="gov-button gov-button-secondary gov-button-compact"
                    >
                      Full timeline
                    </Link>
                  </span>
                </div>
                <dl className="gov-detail-grid">
                  <div>
                    <dt className="gov-detail-label">Farm plot</dt>
                    <dd className="gov-detail-value">
                      {detail.farm.plot_identifier} — {detail.farm.barangay} (
                      {detail.farm.area_hectares.toFixed(2)} ha)
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Farmer</dt>
                    <dd className="gov-detail-value">
                      {detail.farm.farmer.full_name} — {detail.farm.farmer.barangay}
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Estimated affected area</dt>
                    <dd className="gov-detail-value">
                      {detail.reported_area_hectares.toFixed(2)} ha
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Observed on</dt>
                    <dd className="gov-detail-value">{detail.observed_on ?? "—"}</dd>
                  </div>
                  <div className="gov-detail-wide">
                    <dt className="gov-detail-label">Symptoms</dt>
                    <dd className="gov-detail-value">{detail.symptoms ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Reported by</dt>
                    <dd className="gov-detail-value">
                      {detail.reporter.full_name} ({detail.reporter.username})
                    </dd>
                  </div>
                </dl>

                {detail.status === "REPORTED" ? (
                  <div className="mt-6">
                    <h3 className="gov-record-title">Edit report details</h3>
                    <form
                      onSubmit={(event) => void handleEdit(event, detail)}
                      className="gov-form gov-form-grid"
                    >
                      <div className="gov-field">
                        <label htmlFor="edit_pest_name" className="gov-label">
                          Pest name <span className="gov-required" aria-hidden="true">*</span>
                        </label>
                        <input
                          id="edit_pest_name"
                          name="pest_name"
                          type="text"
                          autoComplete="off"
                          maxLength={120}
                          required
                          defaultValue={detail.pest_name}
                          className="gov-input"
                        />
                      </div>
                      <div className="gov-field">
                        <label htmlFor="edit_area" className="gov-label">
                          Estimated affected area (hectares) <span className="gov-required" aria-hidden="true">*</span>
                        </label>
                        <input
                          id="edit_area"
                          name="reported_area_hectares"
                          type="number"
                          min={0.01}
                          max={10000}
                          step={0.01}
                          required
                          defaultValue={detail.reported_area_hectares}
                          className="gov-input"
                        />
                      </div>
                      <div className="gov-field">
                        <label htmlFor="edit_observed_on" className="gov-label">
                          Observation date (optional)
                        </label>
                        <input
                          id="edit_observed_on"
                          name="observed_on"
                          type="date"
                          defaultValue={detail.observed_on ?? ""}
                          className="gov-input"
                        />
                      </div>
                      <div className="gov-field">
                        <label htmlFor="edit_symptoms" className="gov-label">
                          Symptoms (optional)
                        </label>
                        <textarea
                          id="edit_symptoms"
                          name="symptoms"
                          rows={2}
                          maxLength={2000}
                          defaultValue={detail.symptoms ?? ""}
                          className="gov-textarea"
                        />
                      </div>
                      <div className="gov-form-actions">
                        <button
                          type="submit"
                          disabled={savingEdit || submitting}
                          className="gov-button gov-button-secondary"
                        >
                          {savingEdit ? "Saving..." : "Save changes"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleSubmit(detail)}
                          disabled={savingEdit || submitting}
                          className="gov-button gov-button-primary"
                        >
                          {submitting ? "Submitting..." : "Submit for inspection"}
                        </button>
                      </div>
                    </form>
                    {editError && (
                      <p role="alert" className="gov-alert gov-alert-error mt-4">
                        {editError}
                      </p>
                    )}
                  </div>
                ) : detail.status === "FIELD_VALIDATED" ? (
                  <p role="status" className="gov-timeline-note mt-4">
                    This case is validated and ready for an intervention plan.{" "}
                    <Link
                      href="/interventions"
                      className="gov-activity-link"
                    >
                      Go to interventions
                    </Link>
                  </p>
                ) : detail.status === "UNDER_INTERVENTION" ||
                  detail.status === "FOLLOW_UP_DUE" ||
                  detail.status === "REINTERVENTION_REQUIRED" ||
                  detail.status === "CLOSED" ? (
                  <p role="status" className="gov-timeline-note mt-4">
                    This case has an intervention record.{" "}
                    <Link
                      href="/interventions"
                      className="gov-activity-link"
                    >
                      Go to interventions
                    </Link>{" "}
                    <Link
                      href="/follow-ups"
                      className="gov-activity-link"
                    >
                      Go to follow-ups
                    </Link>
                  </p>
                ) : (
                  <p role="status" className="gov-timeline-note mt-4">
                    This case is queued for inspection and can no longer be edited here.
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

export default function PestCasesPage() {
  return (
    <Suspense
      fallback={
        <main className="mx-auto max-w-3xl px-6 py-12">
          <p role="status">Loading pest cases...</p>
        </main>
      }
    >
      <PestCasesPageInner />
    </Suspense>
  );
}
