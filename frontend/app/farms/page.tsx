"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import {
  FarmersRequestError,
  listFarmers,
  type FarmerSummary,
} from "@/lib/farmers";
import {
  FarmsRequestError,
  createFarm,
  listFarms,
  updateFarm,
  type FarmWithFarmer,
} from "@/lib/farms";

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

export default function FarmsPage() {
  const router = useRouter();
  const auth = useAuth();
  const [farmers, setFarmers] = useState<FarmerSummary[]>([]);
  const [farms, setFarms] = useState<FarmWithFarmer[]>([]);
  const [filterFarmerId, setFilterFarmerId] = useState<string>("all");
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formNotice, setFormNotice] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const authenticated = auth.status === "authenticated";

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const loadAll = useCallback(
    async (farmerId: string) => {
      setLoadingList(true);
      setListError(null);
      try {
        const [loadedFarmers, loadedFarms] = await Promise.all([
          listFarmers(),
          listFarms(farmerId === "all" ? undefined : Number(farmerId)),
        ]);
        setFarmers(loadedFarmers);
        setFarms(loadedFarms);
      } catch (failure) {
        if (
          (failure instanceof FarmsRequestError && failure.kind === "unauthenticated") ||
          (failure instanceof FarmersRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FarmsRequestError || failure instanceof FarmersRequestError
            ? failure.message
            : "Farm records could not be read.",
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
        const [loadedFarmers, loadedFarms] = await Promise.all([
          listFarmers(),
          listFarms(),
        ]);
        if (!active) {
          return;
        }
        setFarmers(loadedFarmers);
        setFarms(loadedFarms);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (
          (failure instanceof FarmsRequestError && failure.kind === "unauthenticated") ||
          (failure instanceof FarmersRequestError && failure.kind === "unauthenticated")
        ) {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FarmsRequestError || failure instanceof FarmersRequestError
            ? failure.message
            : "Farm records could not be read.",
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
  }, [authenticated, router]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const farmerIdRaw = data.get("farmer_id");
    const plotIdentifier = data.get("plot_identifier");
    const barangay = data.get("barangay");
    const areaRaw = data.get("area_hectares");
    const farmerId = typeof farmerIdRaw === "string" ? Number(farmerIdRaw) : NaN;
    const area = typeof areaRaw === "string" ? parseArea(areaRaw) : null;
    if (
      !Number.isSafeInteger(farmerId) ||
      farmerId <= 0 ||
      typeof plotIdentifier !== "string" ||
      plotIdentifier.trim() === "" ||
      typeof barangay !== "string" ||
      barangay.trim() === "" ||
      area === null
    ) {
      setFormError(
        "Select a farmer and enter a plot identifier, barangay, and area (0–10000 ha, up to 2 decimals).",
      );
      return;
    }
    setCreating(true);
    setFormError(null);
    setFormNotice(null);
    try {
      const created = await createFarm(
        {
          farmer_id: farmerId,
          plot_identifier: plotIdentifier.trim(),
          barangay: barangay.trim(),
          area_hectares: area,
        },
        auth.csrfToken,
      );
      setFarms((current) =>
        [...current, created].sort((left, right) => left.id - right.id),
      );
      setFormNotice(`Farm ${created.plot_identifier} was added.`);
      form.reset();
    } catch (failure) {
      if (failure instanceof FarmsRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setFormError(
        failure instanceof FarmsRequestError ? failure.message : "Farm could not be added.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>, target: FarmWithFarmer) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const data = new FormData(event.currentTarget);
    const plotIdentifier = data.get("plot_identifier");
    const barangay = data.get("barangay");
    const areaRaw = data.get("area_hectares");
    const area = typeof areaRaw === "string" ? parseArea(areaRaw) : null;
    if (
      typeof plotIdentifier !== "string" ||
      plotIdentifier.trim() === "" ||
      typeof barangay !== "string" ||
      barangay.trim() === "" ||
      area === null
    ) {
      setEditError(
        "Plot identifier, barangay, and area (0–10000 ha, up to 2 decimals) are required.",
      );
      return;
    }
    setSavingEdit(true);
    setEditError(null);
    setFormNotice(null);
    try {
      const updated = await updateFarm(
        target.id,
        {
          plot_identifier: plotIdentifier.trim(),
          barangay: barangay.trim(),
          area_hectares: area,
        },
        auth.csrfToken,
      );
      setFarms((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setEditingId(null);
      setFormNotice(`Farm ${updated.plot_identifier} was updated.`);
    } catch (failure) {
      if (failure instanceof FarmsRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setEditError(
        failure instanceof FarmsRequestError ? failure.message : "Farm could not be updated.",
      );
    } finally {
      setSavingEdit(false);
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
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Farm Management</h1>
        <p className="mt-2 text-sm text-slate-600">
          View, add, and edit sugarcane farm plots and their assigned farmers.
        </p>
        <div className="mt-4 flex flex-wrap gap-4">
          <Link
            href="/dashboard"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            Back to dashboard
          </Link>
          <Link
            href="/farmers"
            className="inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
          >
            View farmers
          </Link>
        </div>

        <section aria-label="Add farm" className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Add farm</h2>
          {farmers.length === 0 && !loadingList ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Add a farmer first before recording a farm.{" "}
              <Link href="/farmers" className="font-medium text-emerald-700 hover:text-emerald-800">
                Go to farmers
              </Link>
            </p>
          ) : (
            <form onSubmit={handleCreate} className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="farmer_id" className="block text-sm font-medium text-slate-700">
                  Farmer
                </label>
                <select
                  id="farmer_id"
                  name="farmer_id"
                  required
                  defaultValue=""
                  className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                >
                  <option value="" disabled>
                    Select a farmer
                  </option>
                  {farmers.map((entry) => (
                    <option key={entry.id} value={entry.id}>
                      {entry.full_name} — {entry.barangay}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="plot_identifier" className="block text-sm font-medium text-slate-700">
                  Farm/plot identifier
                </label>
                <input
                  id="plot_identifier"
                  name="plot_identifier"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  required
                  placeholder="e.g. Plot A"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div>
                <label htmlFor="farm_barangay" className="block text-sm font-medium text-slate-700">
                  Barangay/location
                </label>
                <input
                  id="farm_barangay"
                  name="barangay"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  required
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div>
                <label htmlFor="area_hectares" className="block text-sm font-medium text-slate-700">
                  Sugarcane area (hectares)
                </label>
                <input
                  id="area_hectares"
                  name="area_hectares"
                  type="number"
                  min={0.01}
                  max={10000}
                  step={0.01}
                  required
                  placeholder="e.g. 2.50"
                  className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                />
              </div>
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                >
                  {creating ? "Adding..." : "Add farm"}
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

        <section aria-label="Farm records" className="mt-10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Farm records</h2>
            <div className="flex items-center gap-2">
              <label htmlFor="filter_farmer" className="text-sm font-medium text-slate-700">
                Farmer
              </label>
              <select
                id="filter_farmer"
                value={filterFarmerId}
                onChange={(event) => {
                  const next = event.target.value;
                  setFilterFarmerId(next);
                  void loadAll(next);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-900"
              >
                <option value="all">All farmers</option>
                {farmers.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.full_name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void loadAll(filterFarmerId)}
                disabled={loadingList}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
              >
                {loadingList ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loadingList ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading farms...
            </p>
          ) : listError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {listError}
            </p>
          ) : farms.length === 0 ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No farm records found. Add the first farm above.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Farm/plot</th>
                    <th scope="col" className="px-4 py-3 font-medium">Barangay</th>
                    <th scope="col" className="px-4 py-3 font-medium">Area (ha)</th>
                    <th scope="col" className="px-4 py-3 font-medium">Farmer</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {farms.map((entry) => (
                    <tr key={entry.id}>
                      <td className="px-4 py-3 text-slate-900">{entry.plot_identifier}</td>
                      <td className="px-4 py-3 text-slate-900">{entry.barangay}</td>
                      <td className="px-4 py-3 text-slate-900">{entry.area_hectares.toFixed(2)}</td>
                      <td className="px-4 py-3 text-slate-900">{entry.farmer.full_name}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(editingId === entry.id ? null : entry.id);
                            setEditError(null);
                          }}
                          className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                        >
                          {editingId === entry.id ? "Cancel" : "Edit"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {editingId !== null &&
          (() => {
            const target = farms.find((entry) => entry.id === editingId);
            if (!target) {
              return null;
            }
            return (
              <section aria-label="Edit farm" className="mt-8 rounded-xl border border-slate-200 p-6">
                <h2 className="text-lg font-semibold text-slate-900">
                  Edit farm: {target.plot_identifier}
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  Farmer: {target.farmer.full_name} (farm ownership cannot be changed here)
                </p>
                <form
                  onSubmit={(event) => void handleEdit(event, target)}
                  className="mt-4 grid gap-4 sm:grid-cols-2"
                >
                  <div>
                    <label htmlFor="edit_plot_identifier" className="block text-sm font-medium text-slate-700">
                      Farm/plot identifier
                    </label>
                    <input
                      id="edit_plot_identifier"
                      name="plot_identifier"
                      type="text"
                      autoComplete="off"
                      maxLength={120}
                      required
                      defaultValue={target.plot_identifier}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                    />
                  </div>
                  <div>
                    <label htmlFor="edit_farm_barangay" className="block text-sm font-medium text-slate-700">
                      Barangay/location
                    </label>
                    <input
                      id="edit_farm_barangay"
                      name="barangay"
                      type="text"
                      autoComplete="off"
                      maxLength={120}
                      required
                      defaultValue={target.barangay}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                    />
                  </div>
                  <div>
                    <label htmlFor="edit_area_hectares" className="block text-sm font-medium text-slate-700">
                      Sugarcane area (hectares)
                    </label>
                    <input
                      id="edit_area_hectares"
                      name="area_hectares"
                      type="number"
                      min={0.01}
                      max={10000}
                      step={0.01}
                      required
                      defaultValue={target.area_hectares}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      type="submit"
                      disabled={savingEdit}
                      className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
                    >
                      {savingEdit ? "Saving..." : "Save changes"}
                    </button>
                  </div>
                </form>
                {editError && (
                  <p role="alert" className="mt-4 text-sm text-red-700">
                    {editError}
                  </p>
                )}
              </section>
            );
          })()}
      </div>
    </main>
  );
}
