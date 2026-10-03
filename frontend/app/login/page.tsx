"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { AuthRequestError, login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [auth.status, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const username = data.get("username");
    const password = data.get("password");

    if (typeof username !== "string" || typeof password !== "string") {
      setError("Sign in could not be completed. Try again.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const session = await login(username, password);
      auth.setSession(session);
      form.reset();
      router.replace("/dashboard");
    } catch (failure) {
      if (failure instanceof AuthRequestError && failure.kind === "invalid_credentials") {
        setError("Invalid username or password.");
      } else if (failure instanceof AuthRequestError && failure.kind === "unavailable") {
        setError("Authentication service is unavailable. Try again shortly.");
      } else {
        setError("Sign in could not be completed. Try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const checking = auth.status === "loading";
  const redirecting = auth.status === "authenticated";

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-12">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>
        <h1 className="mt-4 text-2xl font-semibold text-slate-900">Sign in</h1>
        <p className="mt-2 text-sm text-slate-600">
          Sugarcane Pest Inspection and Intervention Workflow Management System
        </p>

        {checking || redirecting ? (
          <p role="status" className="mt-8 text-sm text-slate-600">
            {checking ? "Checking your session..." : "Opening dashboard..."}
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700">
                Username
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                maxLength={128}
                required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                maxLength={1024}
                required
                className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:border-emerald-700 focus:outline-2 focus:outline-emerald-700"
              />
            </div>
            {auth.status === "error" && !error && (
              <p role="alert" className="text-sm text-amber-700">
                Authentication service is unavailable. Try again shortly.
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-red-700">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 disabled:cursor-wait disabled:opacity-60"
            >
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
