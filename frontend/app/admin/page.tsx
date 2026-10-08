"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import {
  UsersRequestError,
  createUser,
  listUsers,
  setUserActive,
  type ManagedUser,
} from "@/lib/users";

export default function AdminPage() {
  const router = useRouter();
  const auth = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formNotice, setFormNotice] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const role = auth.status === "authenticated" ? auth.user.role : null;
  const isAdmin = role === "ADMIN";

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    } else if (role !== null && role !== "ADMIN") {
      router.replace("/dashboard");
    }
  }, [auth.status, role, router]);

  const refresh = useCallback(async () => {
    setLoadingList(true);
    setListError(null);
    try {
      setUsers(await listUsers());
    } catch (failure) {
      if (failure instanceof UsersRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setListError(
        failure instanceof UsersRequestError
          ? failure.message
          : "Staff list could not be read.",
      );
    } finally {
      setLoadingList(false);
    }
  }, [router]);

  useEffect(() => {
    if (!isAdmin) {
      return;
    }
    let active = true;
    listUsers()
      .then((loaded) => {
        if (active) {
          setUsers(loaded);
          setListError(null);
          setLoadingList(false);
        }
      })
      .catch((failure: unknown) => {
        if (!active) {
          return;
        }
        if (failure instanceof UsersRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof UsersRequestError
            ? failure.message
            : "Staff list could not be read.",
        );
        setLoadingList(false);
      });
    return () => {
      active = false;
    };
  }, [isAdmin, router]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const username = data.get("username");
    const fullName = data.get("full_name");
    const password = data.get("password");
    const role = data.get("role");
    if (
      typeof username !== "string" ||
      typeof fullName !== "string" ||
      typeof password !== "string" ||
      (role !== "ADMIN" && role !== "TECHNICIAN")
    ) {
      setFormError("Staff details are invalid.");
      return;
    }
    setCreating(true);
    setFormError(null);
    setFormNotice(null);
    setActionError(null);
    try {
      const created = await createUser(
        { username, full_name: fullName, password, role },
        auth.csrfToken,
      );
      setUsers((current) =>
        [...current, created].sort((left, right) => left.id - right.id),
      );
      setFormNotice(`Account ${created.username} was created.`);
      form.reset();
    } catch (failure) {
      if (failure instanceof UsersRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setFormError(
        failure instanceof UsersRequestError
          ? failure.message
          : "Staff account could not be created.",
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleToggle(target: ManagedUser) {
    if (auth.status !== "authenticated" || target.id === auth.user.id) {
      return;
    }
    setTogglingId(target.id);
    setActionError(null);
    setFormNotice(null);
    try {
      const updated = await setUserActive(
        target.id,
        !target.is_active,
        auth.csrfToken,
      );
      setUsers((current) =>
        current.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
    } catch (failure) {
      if (failure instanceof UsersRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setActionError(
        failure instanceof UsersRequestError
          ? failure.message
          : "Account status could not be updated.",
      );
    } finally {
      setTogglingId(null);
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

  if (auth.user.role !== "ADMIN") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-12">
        <p role="status">Redirecting to dashboard...</p>
      </main>
    );
  }

  const selfId = auth.user.id;

  return (
    <main className="min-h-screen bg-slate-50 px-6 py-12">
      <div className="mx-auto max-w-5xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-3xl font-semibold text-slate-900">Admin Management</h1>
        <p className="mt-2 text-sm text-slate-600">
          View staff accounts, create ADMIN or TECHNICIAN accounts, and activate or
          deactivate accounts.
        </p>
        <Link
          href="/dashboard"
          className="mt-4 inline-flex text-sm font-medium text-emerald-700 hover:text-emerald-800"
        >
          Back to dashboard
        </Link>

        <section aria-label="Create staff account" className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">Create staff account</h2>
          <form onSubmit={handleCreate} className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="off"
                maxLength={128}
                required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
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
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                Password (at least 12 characters)
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                maxLength={1024}
                minLength={12}
                required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
            <div>
              <label htmlFor="role" className="block text-sm font-medium text-slate-700">
                Role
              </label>
              <select
                id="role"
                name="role"
                defaultValue="TECHNICIAN"
                className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              >
                <option value="TECHNICIAN">TECHNICIAN</option>
                <option value="ADMIN">ADMIN</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={creating}
                className="rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
              >
                {creating ? "Creating..." : "Create account"}
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

        <section aria-label="Staff accounts" className="mt-10">
          <div className="flex items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-slate-900">Staff accounts</h2>
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
              Loading staff accounts...
            </p>
          ) : listError ? (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {listError}
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Username</th>
                    <th scope="col" className="px-4 py-3 font-medium">Full name</th>
                    <th scope="col" className="px-4 py-3 font-medium">Role</th>
                    <th scope="col" className="px-4 py-3 font-medium">Status</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {users.map((entry) => {
                    const isSelf = entry.id === selfId;
                    const busy = togglingId === entry.id;
                    return (
                      <tr key={entry.id}>
                        <td className="px-4 py-3 text-slate-900">
                          {entry.username}
                          {isSelf && (
                            <span className="ml-2 rounded-full bg-slate-200 px-2 py-0.5 text-xs font-semibold text-slate-700">
                              You
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-900">{entry.full_name}</td>
                        <td className="px-4 py-3 text-slate-900">{entry.role}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-3 py-1 text-xs font-semibold ${
                              entry.is_active
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-slate-200 text-slate-700"
                            }`}
                          >
                            {entry.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => void handleToggle(entry)}
                            disabled={isSelf || busy}
                            title={
                              isSelf
                                ? "Your own account cannot be deactivated here."
                                : entry.is_active
                                  ? `Deactivate ${entry.username}`
                                  : `Activate ${entry.username}`
                            }
                            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {busy
                              ? "Saving..."
                              : entry.is_active
                                ? "Deactivate"
                                : "Activate"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {actionError && (
            <p role="alert" className="mt-4 text-sm text-red-700">
              {actionError}
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
