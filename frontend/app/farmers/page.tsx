"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
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

  const authenticated = auth.status === "authenticated";

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

  if (auth.status === "loading") {
    return (
      <main className="gov-status-page">
        <p role="status" className="gov-status-message">Checking your session...</p>
      </main>
    );
  }

  if (auth.status === "unauthenticated") {
    return (
      <main className="gov-status-page">
        <p role="status" className="gov-status-message">Redirecting to sign in...</p>
      </main>
    );
  }

  if (auth.status === "error") {
    return (
      <main className="gov-status-page">
        <h1 className="gov-section-title">Unable to verify your session</h1>
        <p className="gov-field-help">
          The authentication service is unavailable. Reload this page to try again.
        </p>
      </main>
    );
  }

  return (
    <main className="gov-page">
      <header className="gov-page-header">
        <h1 className="gov-page-title">Farmers</h1>
        <p className="gov-page-description">
          Manage farmer records used in sugarcane pest case reporting.
        </p>
      </header>

        <section aria-label="Add farmer" className="gov-card gov-record-section">
          <h2 className="gov-record-title">Add farmer</h2>
          <form onSubmit={handleCreate} className="gov-form gov-form-grid">
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
                Contact number (optional)
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
                {creating ? "Adding..." : "Add farmer"}
              </button>
            </div>
          </form>
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

        <section aria-label="Farmer records" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <div>
              <h2 className="gov-record-title">Farmer records</h2>
              {!loadingList && listError === null && (
                <p className="gov-record-meta">{farmers.length} registered</p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loadingList}
              className="gov-button gov-button-secondary gov-button-compact"
            >
              {loadingList ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {loadingList ? (
            <p role="status" className="gov-empty-state">
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
                  {farmers.map((entry) => (
                    <tr key={entry.id}>
                      <td className="gov-cell-primary">{entry.full_name}</td>
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
              <section aria-label="Edit farmer" className="gov-card gov-record-section">
                <h2 className="gov-record-title">
                  Edit farmer: {target.full_name}
                </h2>
                <form
                  onSubmit={(event) => void handleEdit(event, target)}
                  className="gov-form gov-form-grid"
                >
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
                      Contact number (optional)
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
