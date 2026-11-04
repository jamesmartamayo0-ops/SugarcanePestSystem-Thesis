"use client";

import Image from "next/image";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { AuthRequestError, login } from "@/lib/auth";
import {
  BAIS_CITY_SEAL_ALT,
  BAIS_CITY_SEAL_SRC,
  OFFICE_NAME,
  SYSTEM_NAME,
} from "@/lib/branding";

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
      <div className="gov-card gov-login-card">
        <header className="gov-login-brand">
          <div className="gov-logo-slot gov-logo-slot--login">
            <Image
              src={BAIS_CITY_SEAL_SRC}
              alt={BAIS_CITY_SEAL_ALT}
              width={192}
              height={192}
              loading="eager"
            />
          </div>
          <p className="gov-login-office">{OFFICE_NAME}</p>
        </header>
        <h1 className="gov-login-title">{SYSTEM_NAME}</h1>

        <div className="gov-login-body">
          <h2 className="gov-record-title">Sign in</h2>

          {checking || redirecting ? (
            <p role="status" className="gov-empty-state">
              {checking ? "Checking your session..." : "Opening dashboard..."}
            </p>
          ) : (
            <>
              <p className="gov-field-help">
                Enter the username and password assigned to you.
              </p>
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
                  className="gov-button gov-button-primary gov-button-block"
                >
                  {submitting ? "Signing in..." : "Sign in"}
                </button>
              </form>
            </>
          )}
        </div>

        <p className="gov-login-footnote">Authorized personnel only.</p>
      </div>
    </main>
  );
}
