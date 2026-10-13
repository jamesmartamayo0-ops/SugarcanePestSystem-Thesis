"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import FarmLocationMap from "@/components/farm-location-map";
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
import {
  createCoordinatePayload,
  normalizeFarmCoordinates,
  updateCoordinatePayload,
  type FarmCoordinates,
  type FarmLocationChange,
} from "@/lib/farm-location";

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

type EditLocationDraft = {
  farmId: number;
  coordinates: FarmCoordinates | null;
  change: FarmLocationChange;
};

function coordinatesFromFarm(farm: FarmWithFarmer): FarmCoordinates | null {
  if (farm.latitude === null || farm.longitude === null) {
    return null;
  }
  return { latitude: farm.latitude, longitude: farm.longitude };
}

type FarmLocationFieldProps = {
  coordinates: FarmCoordinates | null;
  mapKey: string;
  onSelect: (coordinates: FarmCoordinates) => void;
  onClear: () => void;
};

function FarmLocationField({
  coordinates,
  mapKey,
  onSelect,
  onClear,
}: FarmLocationFieldProps) {
  return (
    <section className="gov-location-field" aria-labelledby={`${mapKey}-title`}>
      <div>
        <h3 id={`${mapKey}-title`} className="gov-location-title">
          Approximate Farm Location
        </h3>
        <p className="gov-field-help">
          Select the approximate farm location reported by the farmer.
        </p>
      </div>
      <FarmLocationMap
        key={mapKey}
        coordinates={coordinates}
        onSelect={(latitude, longitude) =>
          onSelect(normalizeFarmCoordinates(latitude, longitude))
        }
      />
      <div className="gov-location-summary" aria-live="polite">
        {coordinates ? (
          <>
            <p>
              <span className="gov-location-summary-label">Selected location:</span>{" "}
              <span className="gov-location-coordinates">
                {coordinates.latitude.toFixed(6)}, {coordinates.longitude.toFixed(6)}
              </span>
            </p>
            <button
              type="button"
              onClick={onClear}
              className="gov-button gov-button-secondary gov-button-compact"
            >
              Clear location
            </button>
          </>
        ) : (
          <p>No farm location selected.</p>
        )}
      </div>
      <p className="gov-location-disclaimer">
        Approximate location for agricultural monitoring. This does not establish legal
        land ownership.
      </p>
    </section>
  );
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
  const [createLocation, setCreateLocation] = useState<FarmCoordinates | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editLocation, setEditLocation] = useState<EditLocationDraft | null>(null);
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
          ...createCoordinatePayload(createLocation),
        },
        auth.csrfToken,
      );
      setFarms((current) =>
        [...current, created].sort((left, right) => left.id - right.id),
      );
      setFormNotice(`Farm ${created.plot_identifier} was added.`);
      form.reset();
      setCreateLocation(null);
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
      const locationChange =
        editLocation?.farmId === target.id
          ? editLocation.change
          : ({ kind: "unchanged" } satisfies FarmLocationChange);
      const updated = await updateFarm(
        target.id,
        {
          plot_identifier: plotIdentifier.trim(),
          barangay: barangay.trim(),
          area_hectares: area,
          ...updateCoordinatePayload(locationChange),
        },
        auth.csrfToken,
      );
      setFarms((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
      setEditingId(null);
      setEditLocation(null);
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
    <main className="gov-page">
      <header className="gov-page-header">
        <h1 className="gov-page-title">Farms</h1>
        <p className="gov-page-description">
          Manage registered sugarcane farm and plot records.
        </p>
        <Link href="/pest-cases" className="gov-button gov-button-secondary mt-3">
          Report pest case
        </Link>
      </header>

        <section aria-label="Add farm" className="gov-card gov-record-section">
          <h2 className="gov-record-title">Add farm</h2>
          {farmers.length === 0 && !loadingList ? (
            <p role="status" className="gov-empty-state">
              Add a farmer first before recording a farm.{" "}
              <Link href="/farmers" className="gov-activity-link">
                Go to farmers
              </Link>
            </p>
          ) : (
            <form onSubmit={handleCreate} className="gov-form gov-form-grid">
              <div className="gov-field">
                <label htmlFor="farmer_id" className="gov-label">
                  Farmer <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <select
                  id="farmer_id"
                  name="farmer_id"
                  required
                  defaultValue=""
                  className="gov-select"
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
              <div className="gov-field">
                <label htmlFor="plot_identifier" className="gov-label">
                  Farm/plot identifier <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="plot_identifier"
                  name="plot_identifier"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  required
                  placeholder="e.g. Plot A"
                  className="gov-input"
                />
              </div>
              <div className="gov-field">
                <label htmlFor="farm_barangay" className="gov-label">
                  Barangay/location <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="farm_barangay"
                  name="barangay"
                  type="text"
                  autoComplete="off"
                  maxLength={120}
                  required
                  className="gov-input"
                />
              </div>
              <div className="gov-field">
                <label htmlFor="area_hectares" className="gov-label">
                  Sugarcane area (hectares) <span className="gov-required" aria-hidden="true">*</span>
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
                  className="gov-input"
                />
              </div>
              <FarmLocationField
                coordinates={createLocation}
                mapKey="create-farm-location"
                onSelect={setCreateLocation}
                onClear={() => setCreateLocation(null)}
              />
              <div className="gov-form-actions">
                <button
                  type="submit"
                  disabled={creating}
                  className="gov-button gov-button-primary"
                >
                  {creating ? "Adding..." : "Add farm"}
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

        <section aria-label="Farm records" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <h2 className="gov-record-title">Farm records</h2>
            <div className="gov-record-controls">
              <label htmlFor="filter_farmer" className="gov-label">
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
                className="gov-select"
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
                className="gov-button gov-button-secondary gov-button-compact"
              >
                {loadingList ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loadingList ? (
            <p role="status" className="gov-empty-state">
              Loading farms...
            </p>
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : farms.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No farm records found. Add the first farm above.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[720px]">
                <thead>
                  <tr>
                    <th scope="col">Farm/plot</th>
                    <th scope="col">Barangay</th>
                    <th scope="col">Area (ha)</th>
                    <th scope="col">Farmer</th>
                    <th scope="col">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {farms.map((entry) => (
                    <tr key={entry.id}>
                      <td>{entry.plot_identifier}</td>
                      <td>{entry.barangay}</td>
                      <td>{entry.area_hectares.toFixed(2)}</td>
                      <td>{entry.farmer.full_name}</td>
                      <td>
                        <div className="gov-table-actions">
                          <button
                            type="button"
                            onClick={() => {
                              if (editingId === entry.id) {
                                setEditingId(null);
                                setEditLocation(null);
                              } else {
                                const coordinates = coordinatesFromFarm(entry);
                                setEditingId(entry.id);
                                setEditLocation({
                                  farmId: entry.id,
                                  coordinates,
                                  change: { kind: "unchanged" },
                                });
                              }
                              setEditError(null);
                            }}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            {editingId === entry.id ? "Cancel" : "Edit"}
                          </button>
                          <Link
                            href={`/pest-cases?farm_id=${entry.id}`}
                            className="gov-button gov-button-secondary gov-button-compact"
                          >
                            Report case
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

        {editingId !== null &&
          (() => {
            const target = farms.find((entry) => entry.id === editingId);
            if (!target) {
              return null;
            }
            const displayedCoordinates =
              editLocation?.farmId === target.id
                ? editLocation.coordinates
                : coordinatesFromFarm(target);
            return (
              <section aria-label="Edit farm" className="gov-card gov-record-section">
                <h2 className="gov-record-title">
                  Edit farm: {target.plot_identifier}
                </h2>
                <p className="gov-field-help">
                  Farmer: {target.farmer.full_name} (farm ownership cannot be changed here)
                </p>
                <form
                  onSubmit={(event) => void handleEdit(event, target)}
                  className="gov-form gov-form-grid"
                >
                  <div className="gov-field">
                    <label htmlFor="edit_plot_identifier" className="gov-label">
                      Farm/plot identifier <span className="gov-required" aria-hidden="true">*</span>
                    </label>
                    <input
                      id="edit_plot_identifier"
                      name="plot_identifier"
                      type="text"
                      autoComplete="off"
                      maxLength={120}
                      required
                      defaultValue={target.plot_identifier}
                      className="gov-input"
                    />
                  </div>
                  <div className="gov-field">
                    <label htmlFor="edit_farm_barangay" className="gov-label">
                      Barangay/location <span className="gov-required" aria-hidden="true">*</span>
                    </label>
                    <input
                      id="edit_farm_barangay"
                      name="barangay"
                      type="text"
                      autoComplete="off"
                      maxLength={120}
                      required
                      defaultValue={target.barangay}
                      className="gov-input"
                    />
                  </div>
                  <div className="gov-field">
                    <label htmlFor="edit_area_hectares" className="gov-label">
                      Sugarcane area (hectares) <span className="gov-required" aria-hidden="true">*</span>
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
                      className="gov-input"
                    />
                  </div>
                  <FarmLocationField
                    coordinates={displayedCoordinates}
                    mapKey={`edit-farm-location-${target.id}`}
                    onSelect={(coordinates) =>
                      setEditLocation({
                        farmId: target.id,
                        coordinates,
                        change: { kind: "selected", coordinates },
                      })
                    }
                    onClear={() =>
                      setEditLocation({
                        farmId: target.id,
                        coordinates: null,
                        change: { kind: "cleared" },
                      })
                    }
                  />
                  <div className="gov-form-actions">
                    <button
                      type="submit"
                      disabled={savingEdit}
                      className="gov-button gov-button-primary"
                    >
                      {savingEdit ? "Saving..." : "Save changes"}
                    </button>
                  </div>
                </form>
                {editError && (
                  <p role="alert" className="gov-alert gov-alert-error mt-4">
                    {editError}
                  </p>
                )}
              </section>
            );
          })()}
    </main>
  );
}
