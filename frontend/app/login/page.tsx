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
    <main className="gov-login">
      <div className="gov-card gov-login-panel">
        <header className="gov-login-identity">
          <p className="gov-login-office">Bais City Agriculturist&apos;s Office</p>
          <p className="gov-page-description">
            Sugarcane Pest Inspection and Intervention Workflow Management System
          </p>
        </header>
        <h1 className="gov-page-title">Sign in</h1>

        {checking || redirecting ? (
          <p role="status" className="gov-empty-state">
            {checking ? "Checking your session..." : "Opening dashboard..."}
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="gov-form gov-login-form">
            <div className="gov-field">
              <label htmlFor="username" className="gov-label">
                Username <span className="gov-required" aria-hidden="true">*</span>
              </label>
              <input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                maxLength={128}
                required
                className="gov-input"
              />
            </div>
            <div className="gov-field">
              <label htmlFor="password" className="gov-label">
                Password <span className="gov-required" aria-hidden="true">*</span>
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                maxLength={1024}
                required
                className="gov-input"
              />
            </div>
            {auth.status === "error" && !error && (
              <p role="alert" className="gov-alert gov-alert-warning">
                Authentication service is unavailable. Try again shortly.
              </p>
            )}
            {error && (
              <p role="alert" className="gov-alert gov-alert-error">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="gov-button gov-button-primary"
            >
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        )}
        <p className="gov-field-help">Authorized personnel only.</p>
      </div>
    </main>
  );
}
