"use client";

import Link from "next/link";
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
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Farmer Management</h1>
        <p className="mt-2 text-sm text-slate-600">
          View, add, and edit sugarcane farmer records. Farms are managed per farmer.
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
        </div>

        <section aria-label="Add farmer" className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Add farmer</h2>
          <form onSubmit={handleCreate} className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="full_name" className="block text-sm font-medium text-slate-700">
                Full name
              </label>
              <input
                id="full_name"
                name="full_name"
                type="text"
                autoComplete="off"
                maxLength={160}
                required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
            <div>
              <label htmlFor="barangay" className="block text-sm font-medium text-slate-700">
                Barangay
              </label>
              <input
                id="barangay"
                name="barangay"
                type="text"
                autoComplete="off"
                maxLength={120}
                required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
            <div>
              <label htmlFor="contact_number" className="block text-sm font-medium text-slate-700">
                Contact number (optional)
              </label>
              <input
                id="contact_number"
                name="contact_number"
                type="text"
                autoComplete="off"
                maxLength={32}
                placeholder="e.g. 09171234567"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={creating}
                className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
              >
                {creating ? "Adding..." : "Add farmer"}
              </button>
            </div>
          </form>
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

        <section aria-label="Farmer records" className="mt-10">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Farmer records</h2>
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={loadingList}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-wait disabled:opacity-60"
            >
              {loadingList ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {loadingList ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              Loading farmers...
            </p>
          ) : listError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {listError}
            </p>
          ) : farmers.length === 0 ? (
            <p role="status" className="mt-4 text-sm text-slate-600">
              No farmers recorded yet. Add the first farmer above.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Full name</th>
                    <th scope="col" className="px-4 py-3 font-medium">Barangay</th>
                    <th scope="col" className="px-4 py-3 font-medium">Contact</th>
                    <th scope="col" className="px-4 py-3 font-medium">Farms</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {farmers.map((entry) => (
                    <tr key={entry.id}>
                      <td className="px-4 py-3 text-slate-900">{entry.full_name}</td>
                      <td className="px-4 py-3 text-slate-900">{entry.barangay}</td>
                      <td className="px-4 py-3 text-slate-900">{entry.contact_number ?? "—"}</td>
                      <td className="px-4 py-3 text-slate-900">{entry.farm_count}</td>
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
            const target = farmers.find((entry) => entry.id === editingId);
            if (!target) {
              return null;
            }
            return (
              <section aria-label="Edit farmer" className="mt-8 rounded-xl border border-slate-200 p-6">
                <h2 className="text-lg font-semibold text-slate-900">
                  Edit farmer: {target.full_name}
                </h2>
                <form
                  onSubmit={(event) => void handleEdit(event, target)}
                  className="mt-4 grid gap-4 sm:grid-cols-2"
                >
                  <div>
                    <label htmlFor="edit_full_name" className="block text-sm font-medium text-slate-700">
                      Full name
                    </label>
                    <input
                      id="edit_full_name"
                      name="full_name"
                      type="text"
                      autoComplete="off"
                      maxLength={160}
                      required
                      defaultValue={target.full_name}
                      className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
                    />
                  </div>
                  <div>
                    <label htmlFor="edit_barangay" className="block text-sm font-medium text-slate-700">
                      Barangay
                    </label>
                    <input
                      id="edit_barangay"
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
                    <label htmlFor="edit_contact_number" className="block text-sm font-medium text-slate-700">
                      Contact number (optional)
                    </label>
                    <input
                      id="edit_contact_number"
                      name="contact_number"
                      type="text"
                      autoComplete="off"
                      maxLength={32}
                      defaultValue={target.contact_number ?? ""}
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
