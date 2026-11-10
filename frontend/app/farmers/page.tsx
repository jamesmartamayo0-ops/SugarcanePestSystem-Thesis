"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";
import {
  PageHeader,
  RequiredLegend,
  SessionNotice,
  useRevealOnChange,
} from "@/components/ui";
import {
  FarmersRequestError,
  createFarmer,
  listFarmers,
  updateFarmer,
  type FarmerSummary,
} from "@/lib/farmers";

export default function FarmersPage() {
  const router = useRouter();
  const auth = useAuth();
  const [farmers, setFarmers] = useState<FarmerSummary[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formNotice, setFormNotice] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const authenticated = auth.status === "authenticated";
  const editRef = useRevealOnChange<HTMLElement>(editingId);

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const refresh = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      setFarmers(await listFarmers());
    } catch (failure) {
      if (failure instanceof FarmersRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setListError(
        failure instanceof FarmersRequestError
          ? failure.message
          : "Farmer list could not be read.",
      );
    } finally {
      setLoadingList(false);
    }
  }, [router]);

  useEffect(() => {
    if (!authenticated) {
      return;
    }
    let active = true;
    listFarmers()
      .then((loaded) => {
        if (active) {
          setFarmers(loaded);
          setListError(null);
          setLoadingList(false);
        }
      })
      .catch((failure: unknown) => {
        if (!active) {
          return;
        }
        if (failure instanceof FarmersRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FarmersRequestError
            ? failure.message
            : "Farmer list could not be read.",
        );
        setLoadingList(false);
      });
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
    const fullName = data.get("full_name");
    const barangay = data.get("barangay");
    const contactNumber = data.get("contact_number");
    if (
      typeof fullName !== "string" ||
      typeof barangay !== "string" ||
      (contactNumber !== null && typeof contactNumber !== "string") ||
      fullName.trim() === "" ||
      barangay.trim() === ""
    ) {
      setFormError("Full name and barangay are required.");
      return;
    }
    setCreating(true);
    setFormError(null);
    setFormNotice(null);
    try {
      const created = await createFarmer(
        {
          full_name: fullName.trim(),
          barangay: barangay.trim(),
          contact_number:
            contactNumber === null || contactNumber.trim() === ""
              ? undefined
              : contactNumber.trim(),
        },
        auth.csrfToken,
      );
      setFarmers((current) =>
        [
          ...current,
          {
            id: created.id,
            full_name: created.full_name,
            barangay: created.barangay,
            contact_number: created.contact_number,
            farm_count: created.farms.length,
          },
        ].sort((left, right) => left.id - right.id),
      );
      setFormNotice(`Farmer ${created.full_name} was added.`);
      form.reset();
    } catch (failure) {
      if (failure instanceof FarmersRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setFormError(
        failure instanceof FarmersRequestError
          ? failure.message
          : "Farmer could not be added.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>, target: FarmerSummary) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const data = new FormData(event.currentTarget);
    const fullName = data.get("full_name");
    const barangay = data.get("barangay");
    const contactNumber = data.get("contact_number");
    if (
      typeof fullName !== "string" ||
      typeof barangay !== "string" ||
      (contactNumber !== null && typeof contactNumber !== "string") ||
      fullName.trim() === "" ||
      barangay.trim() === ""
    ) {
      setEditError("Full name and barangay are required.");
      return;
    }
    setSavingEdit(true);
    setEditError(null);
    setFormNotice(null);
    try {
      const updated = await updateFarmer(
        target.id,
        {
          full_name: fullName.trim(),
          barangay: barangay.trim(),
          contact_number:
            contactNumber === null || contactNumber.trim() === "" ? null : contactNumber.trim(),
        },
        auth.csrfToken,
      );
      setFarmers((current) =>
        current.map((entry) =>
          entry.id === updated.id
            ? {
                id: updated.id,
                full_name: updated.full_name,
                barangay: updated.barangay,
                contact_number: updated.contact_number,
                farm_count: updated.farms.length,
              }
            : entry,
        ),
      );
      setEditingId(null);
      setFormNotice(`Farmer ${updated.full_name} was updated.`);
    } catch (failure) {
      if (failure instanceof FarmersRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setEditError(
        failure instanceof FarmersRequestError
          ? failure.message
          : "Farmer could not be updated.",
      );
    } finally {
      setSavingEdit(false);
    }
  }

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
  }

  // Quick search over the already-loaded (and already authorized) list.
  const normalizedQuery = query.trim().toLowerCase();
  const visibleFarmers =
    normalizedQuery === ""
      ? farmers
      : farmers.filter((entry) =>
          [entry.full_name, entry.barangay, entry.contact_number ?? "", String(entry.id)].some(
            (value) => value.toLowerCase().includes(normalizedQuery),
          ),
        );

  return (
    <main className="gov-page">
      <PageHeader
        title="Farmers"
        description="Manage farmer records used in sugarcane pest case reporting."
        related={[
          { href: "/farms", label: "Farms" },
          { href: "/pest-cases", label: "Pest Cases" },
        ]}
      />

        <section aria-labelledby="add-farmer-heading" className="gov-card gov-record-section">
          <h2 id="add-farmer-heading" className="gov-record-title">
            Add farmer
          </h2>
          <p className="gov-record-intro">
            Register a farmer before recording their farms and pest cases.
          </p>
          <form onSubmit={handleCreate} className="gov-form gov-form-grid">
            <RequiredLegend />
            <div className="gov-field">
              <label htmlFor="full_name" className="gov-label">
                Full name <span className="gov-required" aria-hidden="true">*</span>
              </label>
              <input
                id="full_name"
                name="full_name"
                type="text"
                autoComplete="off"
                maxLength={160}
                required
                className="gov-input"
              />
            </div>
            <div className="gov-field">
              <label htmlFor="barangay" className="gov-label">
                Barangay <span className="gov-required" aria-hidden="true">*</span>
              </label>
              <input
                id="barangay"
                name="barangay"
                type="text"
                autoComplete="off"
                maxLength={120}
                required
                className="gov-input"
              />
            </div>
            <div className="gov-field">
              <label htmlFor="contact_number" className="gov-label">
                Contact number <span className="gov-label-optional">(optional)</span>
              </label>
              <input
                id="contact_number"
                name="contact_number"
                type="text"
                autoComplete="off"
                maxLength={32}
                placeholder="e.g. 09171234567"
                className="gov-input"
              />
            </div>
            <div className="gov-form-actions">
              <button
                type="submit"
                disabled={creating}
                className="gov-button gov-button-primary"
              >
                <Icon name="plus" size={16} />
                {creating ? "Adding..." : "Add farmer"}
              </button>
            </div>
          </form>
          {formError && (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {formError}
            </p>
          )}
          {formNotice && formNotice.endsWith(" was added.") && (
            <p role="status" className="gov-alert gov-alert-success mt-4">
              {formNotice}
            </p>
          )}
        </section>

        <section aria-labelledby="farmer-records-heading" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <div>
              <h2 id="farmer-records-heading" className="gov-record-title">
                Farmer records
              </h2>
              {!loadingList && listError === null && (
                <p className="gov-record-meta">
                  {normalizedQuery === ""
                    ? `${farmers.length} registered`
                    : `${visibleFarmers.length} of ${farmers.length} shown`}
                </p>
              )}
            </div>
            <div className="gov-record-controls">
              <label htmlFor="farmer_search" className="gov-label">
                Search
              </label>
              <input
                id="farmer_search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                maxLength={120}
                autoComplete="off"
                placeholder="Name, barangay, contact, or ID"
                className="gov-input gov-input-search gov-list-search"
              />
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={loadingList}
                className="gov-button gov-button-secondary gov-button-compact"
              >
                <Icon name="refresh" size={15} />
                {loadingList ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {formNotice && formNotice.endsWith(" was updated.") && (
            <p role="status" className="gov-alert gov-alert-success">
              {formNotice}
            </p>
          )}
          {loadingList ? (
            <p role="status" className="gov-loading-state">
              Loading farmers...
            </p>
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : farmers.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No farmer records available. Add the first farmer above.
            </p>
          ) : visibleFarmers.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No farmers match “{query.trim()}”.{" "}
              <button
                type="button"
                onClick={() => setQuery("")}
                className="gov-button gov-button-ghost gov-button-compact"
              >
                Clear search
              </button>
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[640px]">
                <thead>
                  <tr>
                    <th scope="col">Full name</th>
                    <th scope="col">Barangay</th>
                    <th scope="col">Contact</th>
                    <th scope="col" className="gov-cell-num">Farms</th>
                    <th scope="col" className="gov-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleFarmers.map((entry) => (
                    <tr
                      key={entry.id}
                      className={editingId === entry.id ? "gov-row-selected" : undefined}
                    >
                      <td>
                        <span className="gov-cell-primary">{entry.full_name}</span>
                        <span className="gov-cell-meta">Farmer ID {entry.id}</span>
                      </td>
                      <td>{entry.barangay}</td>
                      <td>{entry.contact_number ?? "—"}</td>
                      <td className="gov-cell-num">{entry.farm_count}</td>
                      <td className="gov-col-actions">
                        <button
                          type="button"
                          onClick={() => {
                            setEditingId(editingId === entry.id ? null : entry.id);
                            setEditError(null);
                          }}
                          className="gov-button gov-button-secondary gov-button-compact"
                        >
                          {editingId === entry.id ? "Cancel" : "Edit"}
                          <span className="sr-only"> {entry.full_name}</span>
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
            const target = farmers.find((entry) => entry.id === editingId);
            if (!target) {
              return null;
            }
            return (
              <section
                ref={editRef}
                tabIndex={-1}
                aria-labelledby="edit-farmer-heading"
                className="gov-card gov-record-section gov-record-section--selected"
              >
                <p className="gov-record-eyebrow">Edit farmer · Farmer ID {target.id}</p>
                <h2 id="edit-farmer-heading" className="gov-record-title">
                  {target.full_name}
                </h2>
                <form
                  onSubmit={(event) => void handleEdit(event, target)}
                  className="gov-form gov-form-grid"
                >
                  <RequiredLegend />
                  <div className="gov-field">
                    <label htmlFor="edit_full_name" className="gov-label">
                      Full name <span className="gov-required" aria-hidden="true">*</span>
                    </label>
                    <input
                      id="edit_full_name"
                      name="full_name"
                      type="text"
                      autoComplete="off"
                      maxLength={160}
                      required
                      defaultValue={target.full_name}
                      className="gov-input"
                    />
                  </div>
                  <div className="gov-field">
                    <label htmlFor="edit_barangay" className="gov-label">
                      Barangay <span className="gov-required" aria-hidden="true">*</span>
                    </label>
                    <input
                      id="edit_barangay"
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
                    <label htmlFor="edit_contact_number" className="gov-label">
                      Contact number <span className="gov-label-optional">(optional)</span>
                    </label>
                    <input
                      id="edit_contact_number"
                      name="contact_number"
                      type="text"
                      autoComplete="off"
                      maxLength={32}
                      defaultValue={target.contact_number ?? ""}
                      className="gov-input"
                    />
                  </div>
                  <div className="gov-form-actions">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingId(null);
                        setEditError(null);
                      }}
                      disabled={savingEdit}
                      className="gov-button gov-button-secondary"
                    >
                      Cancel
                    </button>
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
