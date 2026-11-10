"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { AuthLayout } from "@/components/auth-layout";
import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";
import { AuthRequestError, login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const auth = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

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
      setShowPassword(false);
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
    <AuthLayout>
      <div className="gov-auth-card">
        <p className="gov-auth-eyebrow">Staff access</p>
        <h2 className="gov-auth-title">Sign in</h2>

        {checking || redirecting ? (
          <p role="status" className="gov-loading-state gov-auth-pending">
            {checking ? "Checking your session..." : "Opening dashboard..."}
          </p>
        ) : (
          <>
            <p className="gov-auth-text">Enter the username and password assigned to you.</p>
            <form onSubmit={handleSubmit} className="gov-form gov-auth-form">
              <div className="gov-field">
                <label htmlFor="username" className="gov-label">
                  Username <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="username"
                  name="username"
                  type="text"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  maxLength={128}
                  required
                  className="gov-input"
                />
              </div>
              <div className="gov-field">
                <label htmlFor="password" className="gov-label">
                  Password <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <div className="gov-input-group">
                  <input
                    id="password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    maxLength={1024}
                    required
                    className="gov-input"
                  />
                  <button
                    type="button"
                    className="gov-input-addon"
                    onClick={() => setShowPassword((current) => !current)}
                    aria-pressed={showPassword}
                    aria-controls="password"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    title={showPassword ? "Hide password" : "Show password"}
                  >
                    <Icon name={showPassword ? "eye-off" : "eye"} size={18} />
                  </button>
                </div>
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
                aria-busy={submitting || undefined}
                className="gov-button gov-button-primary gov-button-block"
              >
                {submitting && <span className="gov-button-spinner" aria-hidden="true" />}
                {submitting ? "Signing in..." : "Sign in"}
              </button>
            </form>
          </>
        )}

        <p className="gov-auth-note">
          <Icon name="lock" size={16} />
          Authorized personnel only.
        </p>
      </div>
    </AuthLayout>
  );
}
