"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

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
  return status === "REPORTED"
    ? "bg-amber-100 text-amber-800"
    : "bg-sky-100 text-sky-800";
}

function PestCasesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const auth = useAuth();
  const [farms, setFarms] = useState<FarmWithFarmer[]>([]);
  const [cases, setCases] = useState<PestCaseSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState<"all" | PestCaseStatus>("all");
  const [farmFilter, setFarmFilter] = useState<string>("all");
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
    async (status: "all" | PestCaseStatus, farmId: string) => {
      setLoadingList(true);
      setListError(null);
      try {
        const [loadedFarms, loadedCases] = await Promise.all([
          listFarms(),
          listPestCases({
            status,
            farmId: farmId === "all" ? undefined : Number(farmId),
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
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Pest Case Reporting</h1>
        <p className="mt-2 text-sm text-slate-600">
          Report pest observations per farm plot. Reported area is a pre-inspection
          estimate and must not exceed the farm&apos;s recorded sugarcane area.
        </p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link
            href="/dashboard"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            Back to dashboard
          </Link>
          <Link
            href="/farms"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View farms
          </Link>
          <Link
            href="/inspections"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View inspections
          </Link>
          <Link
            href="/interventions"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View interventions
          </Link>
          <Link
            href="/follow-ups"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View follow-ups
          </Link>
        </div>

        <section aria-label="Report pest case" className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Report pest case</h2>
          {farms.length === 0 && !loadingList ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Record a farm first before reporting a pest case.{" "}
              <Link href="/farms" className="font-medium text-emerald-700 hover:text-emerald-800">
                Go to farms
              </Link>
            </p>
          ) : (
            <form onSubmit={handleCreate} className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="farm_id" className="block text-sm font-medium text-slate-700">
                  Farm
                </label>
                <select
                  id="farm_id"
                  name="farm_id"
                  required
                  value={preselectedFarmId}
                  onChange={(event) => setPreselectedFarmId(event.target.value)}
                  className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
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
              <div>
                <label htmlFor="pest_name" className="block text-sm font-medium text-slate-700">
                  Pest name
                </label>
                <input
                  id="pest_name"
                  name="pest_name"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  required
                  placeholder="e.g. Stem Borer"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="symptoms" className="block text-sm font-medium text-slate-700">
                  Symptoms / observations (optional)
                </label>
                <textarea
                  id="symptoms"
                  name="symptoms"
                  rows={3}
                  maxLength={2000}
                  placeholder="e.g. Bored stalks and wilting shoots on the east rows"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div>
                <label htmlFor="observed_on" className="block text-sm font-medium text-slate-700">
                  Observation date (optional)
                </label>
                <input
                  id="observed_on"
                  name="observed_on"
                  type="date"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div>
                <label htmlFor="reported_area_hectares" className="block text-sm font-medium text-slate-700">
                  Estimated affected area (hectares)
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
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                >
                  {creating ? "Reporting..." : "Report pest case"}
                </button>
              </div>
            </form>
          )}
          {formError && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {formError}
            </p>
          )}
          {formNotice && (
            <p role="status" className="mt-4 text-sm text-emerald-700">
              {formNotice}
            </p>
          )}
        </section>

        <section aria-label="Pest case records" className="mt-10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Pest case records</h2>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="status_filter" className="text-sm font-medium text-slate-700">
                Status
              </label>
              <select
                id="status_filter"
                value={statusFilter}
                onChange={(event) => {
                  const next = event.target.value as "all" | PestCaseStatus;
                  setStatusFilter(next);
                  void loadAll(next, farmFilter);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
              >
                <option value="all">All statuses</option>
                <option value="REPORTED">REPORTED</option>
                <option value="FOR_INSPECTION">FOR_INSPECTION</option>
                <option value="INSPECTION_SCHEDULED">INSPECTION_SCHEDULED</option>
                <option value="NOT_CONFIRMED">NOT_CONFIRMED</option>
                <option value="FIELD_VALIDATED">FIELD_VALIDATED</option>
                <option value="UNDER_INTERVENTION">UNDER_INTERVENTION</option>
                <option value="FOLLOW_UP_DUE">FOLLOW_UP_DUE</option>
                <option value="REINTERVENTION_REQUIRED">REINTERVENTION_REQUIRED</option>
                <option value="CLOSED">CLOSED</option>
              </select>
              <label htmlFor="farm_filter" className="text-sm font-medium text-slate-700">
                Farm
              </label>
              <select
                id="farm_filter"
                value={farmFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setFarmFilter(next);
                  void loadAll(statusFilter, next);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
              >
                <option value="all">All farms</option>
                {farms.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.plot_identifier} — {entry.farmer.full_name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void loadAll(statusFilter, farmFilter)}
                disabled={loadingList}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
              >
                {loadingList ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loadingList ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading pest cases...
            </p>
          ) : listError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {listError}
            </p>
          ) : cases.length === 0 ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No pest cases found. Report the first case above.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Pest</th>
                    <th scope="col" className="px-4 py-3 font-medium">Area (ha)</th>
                    <th scope="col" className="px-4 py-3 font-medium">Status</th>
                    <th scope="col" className="px-4 py-3 font-medium">Observed</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {cases.map((entry) => (
                    <tr key={entry.id}>
                      <td className="px-4 py-3 text-slate-900">{entry.pest_name}</td>
                      <td className="px-4 py-3 text-slate-900">
                        {entry.reported_area_hectares.toFixed(2)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadge(entry.status)}`}
                        >
                          {entry.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-900">{entry.observed_on ?? "—"}</td>
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
          <section aria-label="Pest case detail" className="mt-8 rounded-xl border border-slate-200 p-6">
            {loadingDetail ? (
              <p role="status" className="text-sm text-slate-600">
                Loading pest case details...
              </p>
            ) : detailError ? (
              <p role="alert" className="text-sm text-red-700">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold text-slate-900">
                    {detail.pest_name}
                  </h2>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadge(detail.status)}`}
                  >
                    {detail.status}
                  </span>
                </div>
                <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="font-medium text-slate-600">Farm plot</dt>
                    <dd className="text-slate-900">
                      {detail.farm.plot_identifier} — {detail.farm.barangay} (
                      {detail.farm.area_hectares.toFixed(2)} ha)
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Farmer</dt>
                    <dd className="text-slate-900">
                      {detail.farm.farmer.full_name} — {detail.farm.farmer.barangay}
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Estimated affected area</dt>
                    <dd className="text-slate-900">
                      {detail.reported_area_hectares.toFixed(2)} ha
                    </dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Observed on</dt>
                    <dd className="text-slate-900">{detail.observed_on ?? "—"}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="font-medium text-slate-600">Symptoms</dt>
                    <dd className="text-slate-900">{detail.symptoms ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="font-medium text-slate-600">Reported by</dt>
                    <dd className="text-slate-900">
                      {detail.reporter.full_name} ({detail.reporter.username})
                    </dd>
                  </div>
                </dl>

                {detail.status === "REPORTED" ? (
                  <div className="mt-6">
                    <h3 className="text-sm font-semibold text-slate-900">Edit report details</h3>
                    <form
                      onSubmit={(event) => void handleEdit(event, detail)}
                      className="mt-3 grid gap-4 sm:grid-cols-2"
                    >
                      <div>
                        <label htmlFor="edit_pest_name" className="block text-sm font-medium text-slate-700">
                          Pest name
                        </label>
                        <input
                          id="edit_pest_name"
                          name="pest_name"
                          type="text"
                          autoComplete="off"
                          maxLength={120}
                          required
                          defaultValue={detail.pest_name}
                          className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                        />
                      </div>
                      <div>
                        <label htmlFor="edit_area" className="block text-sm font-medium text-slate-700">
                          Estimated affected area (hectares)
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
                          className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                        />
                      </div>
                      <div>
                        <label htmlFor="edit_observed_on" className="block text-sm font-medium text-slate-700">
                          Observation date (optional)
                        </label>
                        <input
                          id="edit_observed_on"
                          name="observed_on"
                          type="date"
                          defaultValue={detail.observed_on ?? ""}
                          className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                        />
                      </div>
                      <div>
                        <label htmlFor="edit_symptoms" className="block text-sm font-medium text-slate-700">
                          Symptoms (optional)
                        </label>
                        <textarea
                          id="edit_symptoms"
                          name="symptoms"
                          rows={2}
                          maxLength={2000}
                          defaultValue={detail.symptoms ?? ""}
                          className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                        />
                      </div>
                      <div className="flex flex-wrap items-end gap-3 sm:col-span-2">
                        <button
                          type="submit"
                          disabled={savingEdit || submitting}
                          className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                        >
                          {savingEdit ? "Saving..." : "Save changes"}
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleSubmit(detail)}
                          disabled={savingEdit || submitting}
                          className="rounded-lg bg-sky-700 px-4 py-2 font-medium text-white hover:bg-sky-800 disabled:cursor-wait disabled:opacity-60"
                        >
                          {submitting ? "Submitting..." : "Submit for inspection"}
                        </button>
                      </div>
                    </form>
                    {editError && (
                      <p role="alert" className="mt-4 text-sm text-red-700">
                        {editError}
                      </p>
                    )}
                  </div>
                ) : detail.status === "FIELD_VALIDATED" ? (
                  <p role="status" className="mt-6 text-sm text-slate-600">
                    This case is validated and ready for an intervention plan.{" "}
                    <Link
                      href="/interventions"
                      className="font-medium text-emerald-700 hover:text-emerald-800"
                    >
                      Go to interventions
                    </Link>
                  </p>
                ) : detail.status === "UNDER_INTERVENTION" ||
                  detail.status === "FOLLOW_UP_DUE" ||
                  detail.status === "REINTERVENTION_REQUIRED" ||
                  detail.status === "CLOSED" ? (
                  <p role="status" className="mt-6 text-sm text-slate-600">
                    This case has an intervention record.{" "}
                    <Link
                      href="/interventions"
                      className="font-medium text-emerald-700 hover:text-emerald-800"
                    >
                      Go to interventions
                    </Link>{" "}
                    <Link
                      href="/follow-ups"
                      className="font-medium text-emerald-700 hover:text-emerald-800"
                    >
                      Go to follow-ups
                    </Link>
                  </p>
                ) : (
                  <p role="status" className="mt-6 text-sm text-slate-600">
                    This case is queued for inspection and can no longer be edited here.
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
