import Link from "next/link";

import SystemStatus from "@/components/system-status";
import { OFFICE_NAME, SYSTEM_NAME } from "@/lib/branding";

export default function Home() {
  return (
    <main className="gov-login">
      <div className="gov-card gov-login-card">
        <header className="gov-login-brand">
          <div className="gov-logo-slot gov-logo-slot--login" aria-hidden="true" />
          <p className="gov-login-office">{OFFICE_NAME}</p>
        </header>

        <h1 className="gov-login-title">{SYSTEM_NAME}</h1>
        <p className="gov-login-lead">
          Record and track sugarcane pest cases from field validation through
          intervention and follow-up.
        </p>

        <div className="gov-login-body">
          <Link href="/login" className="gov-button gov-button-primary gov-button-block">
            Sign in
          </Link>
          <SystemStatus />
        </div>

        <p className="gov-login-footnote">Authorized personnel only.</p>
      </div>
    </main>
  );
}
