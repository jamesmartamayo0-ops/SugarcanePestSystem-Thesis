"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { formatDisplayDate, pestLabel, workflowBadgeClass, workflowLabel } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import { EvidencePhotoGallery } from "@/components/evidence-photos";
import { Icon } from "@/components/icons";
import {
  PageHeader,
  RequiredLegend,
  SessionNotice,
  StatusScreen,
  useRevealOnChange,
} from "@/components/ui";
import { WorkflowSteps } from "@/components/workflow-steps";
import { DetailSkeleton, TableSkeleton } from "@/components/skeleton";
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
  uploadEvidencePhotos,
  type PestCaseDetail,
  type PestCaseStatus,
  type PestCaseSummary,
} from "@/lib/pest-cases";

const AREA_PATTERN = /^\d+(\.\d{1,2})?$/;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_PHOTO_BYTES = 5 * 1024 * 1024;

function validatePhotoFiles(files: File[], remaining = 3): string | null {
  if (files.length === 0) {
    return null;
  }
  if (files.length > remaining) {
    return `You can add at most ${remaining} more evidence photo${remaining === 1 ? "" : "s"}.`;
  }
  for (const file of files) {
    if (!PHOTO_TYPES.includes(file.type)) {
      return "Evidence photos must be JPEG, PNG, or WebP.";
    }
    if (file.size > MAX_PHOTO_BYTES) {
      return "Each evidence photo must be at most 5 MiB.";
    }
  }
  return null;
}

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
  return workflowBadgeClass(status);
}

function farmSummary(farms: FarmWithFarmer[], farmId: number) {
  const farm = farms.find((item) => item.id === farmId);
  if (farm === undefined) {
    return <span className="gov-cell-meta">Farm #{farmId}</span>;
  }
  return (
    <>
      {farm.plot_identifier}
      <span className="gov-cell-meta">{farm.farmer.full_name}</span>
    </>
  );
}

const CASE_STATUSES: PestCaseStatus[] = [
  "REPORTED",
  "FOR_INSPECTION",
  "INSPECTION_SCHEDULED",
  "FIELD_VALIDATED",
  "NOT_CONFIRMED",
  "UNDER_INTERVENTION",
  "FOLLOW_UP_DUE",
  "REINTERVENTION_REQUIRED",
  "CLOSED",
];

// Dashboard links pass ?status=...; only known workflow values are honoured.
function statusFromParams(raw: string | null): "all" | PestCaseStatus {
  return raw !== null && (CASE_STATUSES as string[]).includes(raw)
    ? (raw as PestCaseStatus)
    : "all";
}

function PestCasesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const [farms, setFarms] = useState<FarmWithFarmer[]>([]);
  const [cases, setCases] = useState<PestCaseSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState<"all" | PestCaseStatus>(() =>
    statusFromParams(searchParams.get("status")),
  );
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
  const [createPhotos, setCreatePhotos] = useState<File[]>([]);
  const [detailPhotos, setDetailPhotos] = useState<File[]>([]);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const authenticated = auth.status === "authenticated";
  const detailRef = useRevealOnChange<HTMLElement>(loadingDetail ? null : selectedId);

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
    const linkedStatus = statusFromParams(searchParams.get("status"));
    (async () => {
      setLoadingList(true);
      setStatusFilter(linkedStatus);
      try {
        const [loadedFarms, loadedCases] = await Promise.all([
          listFarms(),
          listPestCases({ status: linkedStatus }),
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
      setDetailPhotos([]);
      setPhotoError(null);
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
      area === null ||
      (symptoms !== null && typeof symptoms !== "string") ||
      (observedOn !== null && typeof observedOn !== "string")
    ) {
      setFormError(
        "Select a farm and enter the affected area (0–10000 ha, up to 2 decimals).",
      );
      return;
    }
    const photoProblem = validatePhotoFiles(createPhotos);
    if (photoProblem !== null) {
      setFormError(photoProblem);
      return;
    }
    setCreating(true);
    setFormError(null);
    setFormNotice(null);
    try {
      let created = await createPestCase(
        {
          farm_id: farmId,
          pest_name: pestName.trim() === "" ? null : pestName.trim(),
          symptoms:
            symptoms === null || symptoms.trim() === "" ? undefined : symptoms.trim(),
          observed_on:
            observedOn === null || observedOn.trim() === "" ? undefined : observedOn.trim(),
          reported_area_hectares: area,
        },
        auth.csrfToken,
      );
      if (createPhotos.length > 0) {
        try {
          created = await uploadEvidencePhotos(created.id, createPhotos, auth.csrfToken);
        } catch (failure) {
          setFormError(
            `The case was reported, but the evidence photos could not be uploaded. ${
              failure instanceof PestCasesRequestError
                ? failure.message
                : "Open the case to retry."
            }`,
          );
        }
      }
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
      setFormNotice(`Pest case for ${pestLabel(created.pest_name)} was reported.`);
      form.reset();
      setPreselectedFarmId("");
      setCreatePhotos([]);
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
      area === null ||
      (symptoms !== null && typeof symptoms !== "string") ||
      (observedOn !== null && typeof observedOn !== "string")
    ) {
      setEditError("Enter an affected area from 0–10000 ha with up to 2 decimals.");
      return;
    }
    setSavingEdit(true);
    setEditError(null);
    try {
      const updated = await updatePestCase(
        target.id,
        {
          pest_name: pestName.trim() === "" ? null : pestName.trim(),
          symptoms: symptoms === null || symptoms.trim() === "" ? null : symptoms.trim(),
          observed_on:
            observedOn === null || observedOn.trim() === "" ? null : observedOn.trim(),
          reported_area_hectares: area,
        },
        auth.csrfToken,
      );
      setDetail({
        ...updated,
        confirmed_pest_name: target.confirmed_pest_name,
        evidence_photos: target.evidence_photos,
      });
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
      setFormNotice(`Pest case for ${pestLabel(updated.pest_name)} was updated.`);
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
      setFormNotice(
        `Pest case for ${pestLabel(updated.pest_name)} was submitted for inspection.`,
      );
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

  async function handleUploadPhotos(
    event: FormEvent<HTMLFormElement>,
    target: PestCaseDetail,
  ) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const form = event.currentTarget;
    const remaining = 3 - target.evidence_photos.length;
    const photoProblem = validatePhotoFiles(detailPhotos, remaining);
    if (photoProblem !== null) {
      setPhotoError(photoProblem);
      return;
    }
    if (detailPhotos.length === 0) {
      setPhotoError("Select at least one evidence photo.");
      return;
    }
    setUploadingPhotos(true);
    setPhotoError(null);
    try {
      const updated = await uploadEvidencePhotos(target.id, detailPhotos, auth.csrfToken);
      setDetail(updated);
      setDetailPhotos([]);
      setFormNotice(`Evidence photos uploaded for case #${target.id}.`);
      form.reset();
    } catch (failure) {
      if (failure instanceof PestCasesRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setPhotoError(
        failure instanceof PestCasesRequestError
          ? failure.message
          : "Evidence photos could not be uploaded.",
      );
    } finally {
      setUploadingPhotos(false);
    }
  }

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
  }

  return (
    <main className="gov-page">
      <PageHeader
        title="Pest Cases"
        description="Record and manage reported sugarcane pest cases through the inspection and intervention workflow."
        related={[
          { href: "/farms", label: "Farms" },
          { href: "/inspections", label: "Inspections" },
          { href: "/reports", label: "Reports" },
        ]}
      />
      <WorkflowSteps current="report" />

        <section
          id="report-case"
          aria-labelledby="report-case-heading"
          className="gov-card gov-record-section"
        >
          <p className="gov-record-eyebrow">Initial report</p>
          <h2 id="report-case-heading" className="gov-record-title">
            Report pest case
          </h2>
          <p className="gov-record-intro">
            Record a pest report from a farmer or a field observation. Reported details remain
            an initial estimate until a field inspection validates them. The reported area is a
            pre-inspection estimate and must not exceed the farm&apos;s recorded sugarcane area.
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
              <RequiredLegend />
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
                  Suspected Pest <span className="gov-label-optional">(optional)</span>
                </label>
                <input
                  id="pest_name"
                  name="pest_name"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  placeholder="e.g. Stem Borer"
                  aria-describedby="pest_name_help"
                  className="gov-input"
                />
                <p id="pest_name_help" className="gov-field-help">
                  Leave blank if the farmer does not know the pest. It can be confirmed during
                  field inspection.
                </p>
              </div>
              <div className="gov-field gov-field-wide">
                <label htmlFor="symptoms" className="gov-label">
                  Observed Symptoms / Farmer Description
                </label>
                <textarea
                  id="symptoms"
                  name="symptoms"
                  rows={3}
                  maxLength={2000}
                  placeholder="e.g. Naay buslot sa stem ug nag-yellow ang ubang dahon."
                  aria-describedby="symptoms_help"
                  className="gov-textarea"
                />
                <p id="symptoms_help" className="gov-field-help">
                  Record what the farmer noticed on the affected sugarcane.
                </p>
              </div>
              <div className="gov-field">
                <label htmlFor="observed_on" className="gov-label">
                  Observation date <span className="gov-label-optional">(optional)</span>
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
              <div className="gov-field gov-field-wide">
                <label htmlFor="evidence_photos" className="gov-label">
                  Pest / Damage Evidence Photos{" "}
                  <span className="gov-label-optional">(optional)</span>
                </label>
                <input
                  id="evidence_photos"
                  name="evidence_photos"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  onChange={(event) =>
                    setCreatePhotos(Array.from(event.target.files ?? []))
                  }
                  aria-describedby="evidence_photos_help"
                  className="gov-input"
                />
                <p id="evidence_photos_help" className="gov-field-help">
                  Upload up to 3 clear photos. Photos support the initial report and do not
                  constitute confirmed pest identification.
                </p>
                {createPhotos.length > 0 && (
                  <p role="status" className="gov-field-help">
                    {createPhotos.length} photo{createPhotos.length === 1 ? "" : "s"} selected.
                  </p>
                )}
              </div>
              <div className="gov-form-actions">
                <button
                  type="submit"
                  disabled={creating}
                  className="gov-button gov-button-primary"
                >
                  <Icon name="plus" size={16} />
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

        <section aria-labelledby="case-records-heading" className="gov-card gov-record-section">
          <h2 id="case-records-heading" className="gov-record-title">
            Pest case records
          </h2>
          {!loadingList && listError === null && (
            <p className="gov-record-meta">
              {cases.length} {cases.length === 1 ? "case" : "cases"} shown
            </p>
          )}
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
                className="gov-input gov-input-search"
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
                aria-describedby="farmer_filter_help"
                className="gov-input"
              />
              <p id="farmer_filter_help" className="gov-field-help">
                Farmer ID as listed on the Farmers page.
              </p>
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
            <TableSkeleton
              label="Loading pest cases"
              columns={["Case", "Farm and farmer", "Reported area (ha)", "Status", "Observed", "Actions"]}
              tableClassName="min-w-[720px]"
            />
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : cases.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No pest case records found. Adjust the filters or report a new case above.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[720px]">
                <thead>
                  <tr>
                    <th scope="col" className="gov-col-wide">Case</th>
                    <th scope="col">Farm and farmer</th>
                    <th scope="col" className="gov-cell-num">Reported area (ha)</th>
                    <th scope="col">Status</th>
                    <th scope="col">Observed</th>
                    <th scope="col" className="gov-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cases.map((entry) => (
                    <tr
                      key={entry.id}
                      className={selectedId === entry.id ? "gov-row-selected" : undefined}
                    >
                      <td>
                        <span className="gov-cell-primary">{pestLabel(entry.pest_name)}</span>
                        <span className="gov-cell-meta">Case #{entry.id}</span>
                      </td>
                      <td>{farmSummary(farms, entry.farm_id)}</td>
                      <td className="gov-cell-num">{entry.reported_area_hectares.toFixed(2)}</td>
                      <td>
                        <span className={statusBadge(entry.status)}>
                          {workflowLabel(entry.status)}
                        </span>
                      </td>
                      <td className="gov-cell-nowrap">{formatDisplayDate(entry.observed_on)}</td>
                      <td className="gov-col-actions">
                        <div className="gov-table-actions">
                          <button
                            type="button"
                            onClick={() => void openDetail(entry.id)}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            {selectedId === entry.id ? "Selected" : "View"}
                            <span className="sr-only"> details for case #{entry.id}</span>
                          </button>
                          <Link
                            href={`/pest-cases/${entry.id}`}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            <Icon name="history" size={15} />
                            Case record<span className="sr-only"> for case #{entry.id}</span>
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
          <section
            ref={detailRef}
            tabIndex={-1}
            aria-label="Pest case detail"
            className="gov-card gov-record-section gov-record-section--selected"
          >
            {loadingDetail ? (
              <DetailSkeleton label="Loading pest case details" fields={6} />
            ) : detailError ? (
              <p role="alert" className="gov-alert gov-alert-error">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="gov-record-toolbar">
                  <div>
                    <p className="gov-record-eyebrow">Case #{detail.id} · Initial report</p>
                    <h2 className="gov-record-title">{pestLabel(detail.pest_name)}</h2>
                  </div>
                  <span className="gov-table-actions">
                    <span className={statusBadge(detail.status)}>
                      {workflowLabel(detail.status)}
                    </span>
                    <Link
                      href={`/pest-cases/${detail.id}`}
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
                    <dd className="gov-detail-value">{formatDisplayDate(detail.observed_on)}</dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Suspected pest</dt>
                    <dd className="gov-detail-value">{pestLabel(detail.pest_name)}</dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Confirmed pest</dt>
                    <dd className="gov-detail-value">
                      {detail.confirmed_pest_name ?? "Pending Field Validation"}
                    </dd>
                  </div>
                  <div className="gov-detail-wide">
                    <dt className="gov-detail-label">
                      Observed Symptoms / Farmer Description
                    </dt>
                    <dd className="gov-detail-value">{detail.symptoms ?? "—"}</dd>
                  </div>
                  <div className="gov-detail-wide">
                    <dt className="gov-detail-label">Pest / Damage Evidence Photos</dt>
                    <dd className="gov-detail-value">
                      <EvidencePhotoGallery
                        caseId={detail.id}
                        photos={detail.evidence_photos}
                      />
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Reported by</dt>
                    <dd className="gov-detail-value">
                      {detail.reporter.full_name} ({detail.reporter.username})
                    </dd>
                  </div>
                </dl>

                {detail.status === "REPORTED" ? (
                  <div className="gov-workflow-panel">
                    <h3 className="gov-record-title">Pest / Damage Evidence Photos</h3>
                    <p className="gov-record-intro">
                      Upload up to 3 clear photos. Photos support the initial report and do not
                      constitute confirmed pest identification.
                    </p>
                    <form
                      onSubmit={(event) => void handleUploadPhotos(event, detail)}
                      className="gov-form"
                    >
                      <div className="gov-field">
                        <label htmlFor="detail_evidence_photos" className="gov-label">
                          Add evidence photos{" "}
                          <span className="gov-label-optional">(optional)</span>
                        </label>
                        <input
                          id="detail_evidence_photos"
                          name="detail_evidence_photos"
                          type="file"
                          accept="image/jpeg,image/png,image/webp"
                          multiple
                          onChange={(event) =>
                            setDetailPhotos(Array.from(event.target.files ?? []))
                          }
                          aria-describedby="detail_evidence_photos_help"
                          className="gov-input"
                        />
                        <p id="detail_evidence_photos_help" className="gov-field-help">
                          JPEG, PNG, or WebP. Maximum 5 MiB per photo, up to{" "}
                          {Math.max(0, 3 - detail.evidence_photos.length)} more.
                        </p>
                      </div>
                      <div className="gov-form-actions">
                        <button
                          type="submit"
                          disabled={uploadingPhotos}
                          className="gov-button gov-button-secondary"
                        >
                          {uploadingPhotos ? "Uploading..." : "Upload photos"}
                        </button>
                      </div>
                    </form>
                    {photoError && (
                      <p role="alert" className="gov-alert gov-alert-error mt-4">
                        {photoError}
                      </p>
                    )}
                  </div>
                ) : null}

                {detail.status === "REPORTED" ? (
                  <div className="gov-workflow-panel">
                    <h3 className="gov-record-title">Edit report details</h3>
                    <p className="gov-record-intro">
                      Report details can be corrected while the case is Reported. Submitting
                      it for inspection locks the initial report.
                    </p>
                    <form
                      onSubmit={(event) => void handleEdit(event, detail)}
                      className="gov-form gov-form-grid"
                    >
                      <div className="gov-field">
                        <label htmlFor="edit_pest_name" className="gov-label">
                          Suspected Pest <span className="gov-label-optional">(optional)</span>
                        </label>
                        <input
                          id="edit_pest_name"
                          name="pest_name"
                          type="text"
                          autoComplete="off"
                          maxLength={120}
                          defaultValue={detail.pest_name ?? ""}
                          aria-describedby="edit_pest_name_help"
                          className="gov-input"
                        />
                        <p id="edit_pest_name_help" className="gov-field-help">
                          Leave blank if the pest is not known yet.
                        </p>
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
                          Observation date <span className="gov-label-optional">(optional)</span>
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
                          Observed Symptoms / Farmer Description
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
                  <p role="status" className="gov-callout mt-4">
                    Field validation confirmed pest damage. This case is ready for an
                    intervention plan.{" "}
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
                  <p role="status" className="gov-callout mt-4">
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
                ) : detail.status === "NOT_CONFIRMED" ? (
                  <p role="status" className="gov-callout mt-4">
                    The field inspection did not confirm pest damage. The initial report is kept
                    for the record and can no longer be edited here.
                  </p>
                ) : (
                  <p role="status" className="gov-callout mt-4">
                    This case is queued for inspection and can no longer be edited here.{" "}
                    <Link href="/inspections" className="gov-activity-link">
                      Go to inspections
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

export default function PestCasesPage() {
  return (
    <Suspense
      fallback={<StatusScreen message="Loading pest cases..." />}
    >
      <PestCasesPageInner />
    </Suspense>
  );
}
