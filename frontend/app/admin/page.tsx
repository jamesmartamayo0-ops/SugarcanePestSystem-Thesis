"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { roleDisplayName } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Icon } from "@/components/icons";
import {
  PageHeader,
  RequiredLegend,
  SessionNotice,
  StatusScreen,
} from "@/components/ui";
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
  const [confirmTarget, setConfirmTarget] = useState<ManagedUser | null>(null);

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

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
  }

  if (auth.user.role !== "ADMIN") {
    return <StatusScreen message="Redirecting to dashboard..." />;
  }

  const selfId = auth.user.id;
  const activeCount = users.filter((entry) => entry.is_active).length;

  return (
    <main className="gov-page">
      <PageHeader
        title="User Management"
        description="Manage authorized personnel accounts and system access. Available to Administrators only."
      />

        <section aria-labelledby="create-account-heading" className="gov-card gov-record-section">
          <h2 id="create-account-heading" className="gov-record-title">
            Create staff account
          </h2>
          <p className="gov-record-intro">
            Create a sign-in account for an authorized staff member. The role determines what
            the account can see and do.
          </p>
          <form onSubmit={handleCreate} className="gov-form gov-form-grid">
            <RequiredLegend />
            <div className="gov-field">
              <label htmlFor="username" className="gov-label">
                Username <span className="gov-required" aria-hidden="true">*</span>
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="off"
                maxLength={128}
                required
                className="gov-input"
              />
            </div>
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
              <label htmlFor="password" className="gov-label">
                Initial password <span className="gov-required" aria-hidden="true">*</span>
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                maxLength={1024}
                minLength={12}
                required
                aria-describedby="password_help"
                className="gov-input"
              />
              <p id="password_help" className="gov-field-help">
                At least 12 characters. Give it to the staff member privately.
              </p>
            </div>
            <div className="gov-field">
              <label htmlFor="role" className="gov-label">
                Role
              </label>
              <select
                id="role"
                name="role"
                defaultValue="TECHNICIAN"
                aria-describedby="role_help"
                className="gov-select"
              >
                <option value="TECHNICIAN">Agriculture Technician</option>
                <option value="ADMIN">Administrator</option>
              </select>
              <p id="role_help" className="gov-field-help">
                Agriculture Technicians see the records connected to their assigned work.
                Administrators have office-wide access.
              </p>
            </div>
            <div className="gov-form-actions">
              <button
                type="submit"
                disabled={creating}
                className="gov-button gov-button-primary"
              >
                <Icon name="plus" size={16} />
                {creating ? "Creating..." : "Create account"}
              </button>
            </div>
          </form>
          {formError && (
            <p role="alert" className="gov-alert gov-alert-error gov-feedback">
              {formError}
            </p>
          )}
          {formNotice && (
            <p role="status" className="gov-alert gov-alert-success gov-feedback">
              {formNotice}
            </p>
          )}
        </section>

        <section aria-labelledby="staff-accounts-heading" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <div>
              <h2 id="staff-accounts-heading" className="gov-record-title">
                Staff accounts
              </h2>
              {!loadingList && listError === null && (
                <p className="gov-record-meta">
                  {users.length} {users.length === 1 ? "account" : "accounts"} · {activeCount} active
                </p>
              )}
            </div>
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
          {loadingList ? (
            <p role="status" className="gov-loading-state">
              Loading staff accounts...
            </p>
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error gov-feedback">
              {listError}
            </p>
          ) : users.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No staff accounts found.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[640px]">
                <thead>
                  <tr>
                    <th scope="col">Username</th>
                    <th scope="col">Full name</th>
                    <th scope="col">Role</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="gov-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((entry) => {
                    const isSelf = entry.id === selfId;
                    const busy = togglingId === entry.id;
                    return (
                      <tr key={entry.id}>
                        <td>
                          <span className="gov-cell-primary">{entry.username}</span>
                          {isSelf && (
                            <span className="gov-status-badge gov-tone-brand ml-2">
                              You
                            </span>
                          )}
                        </td>
                        <td>{entry.full_name}</td>
                        <td><span className={`gov-status-badge ${entry.role === "ADMIN" ? "gov-role-admin" : "gov-role-technician"}`}>{roleDisplayName(entry.role)}</span></td>
                        <td>
                          <span
                            className={entry.is_active
                                ? "gov-status-badge gov-tone-success"
                                : "gov-status-badge gov-tone-neutral"}
                          >
                            {entry.is_active ? "Active" : "Inactive"}
                          </span>
                        </td>
                        <td className="gov-col-actions">
                          <button
                            type="button"
                            onClick={() => {
                              if (entry.is_active) {
                                setConfirmTarget(entry);
                              } else {
                                void handleToggle(entry);
                              }
                            }}
                            disabled={isSelf || busy}
                            title={
                              isSelf
                                ? "Your own account cannot be deactivated here."
                                : entry.is_active
                                  ? `Deactivate ${entry.username}`
                                  : `Activate ${entry.username}`
                            }
                            className={
                              entry.is_active
                                ? "gov-button gov-button-danger gov-button-compact"
                                : "gov-button gov-button-secondary gov-button-compact"
                            }
                          >
                            {busy
                              ? "Saving..."
                              : entry.is_active
                                ? "Deactivate"
                                : "Activate"}
                          </button>
                          {isSelf && <p className="gov-field-help">Your own account cannot be deactivated here.</p>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {actionError && (
            <p role="alert" className="gov-alert gov-alert-error gov-feedback">
              {actionError}
            </p>
          )}
        </section>

        <ConfirmDialog
          open={confirmTarget !== null}
          title={`Deactivate ${confirmTarget?.username ?? "account"}?`}
          description={
            <>
              <p>
                {confirmTarget?.full_name ?? "This staff member"} will be signed out and will no
                longer be able to sign in.
              </p>
              <p>
                Records they created stay in the system. The account can be activated again
                later.
              </p>
            </>
          }
          confirmLabel="Deactivate account"
          busyLabel="Deactivating..."
          busy={confirmTarget !== null && togglingId === confirmTarget.id}
          onCancel={() => setConfirmTarget(null)}
          onConfirm={() => {
            const target = confirmTarget;
            if (target === null) {
              return;
            }
            void handleToggle(target).finally(() => setConfirmTarget(null));
          }}
        />
    </main>
  );
}
