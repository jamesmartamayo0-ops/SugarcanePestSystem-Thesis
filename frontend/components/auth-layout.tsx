import Image from "next/image";
import type { ReactNode } from "react";

import {
  BAIS_CITY_SEAL_ALT,
  BAIS_CITY_SEAL_SRC,
  OFFICE_NAME,
  SYSTEM_NAME,
} from "@/lib/branding";

/*
 * Shared layout for the public landing and sign-in screens: official
 * identity on the left, the task on the right. The workflow list restates
 * the stages the system records; it makes no performance or outcome claims.
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="gov-auth">
      <section className="gov-auth-brand" aria-label={OFFICE_NAME}>
        <div className="gov-auth-identity">
          <span className="gov-seal gov-auth-seal">
            <Image
              src={BAIS_CITY_SEAL_SRC}
              alt={BAIS_CITY_SEAL_ALT}
              width={176}
              height={176}
              loading="eager"
            />
          </span>
          <p className="gov-auth-office">{OFFICE_NAME}</p>
          <h1 className="gov-auth-system">{SYSTEM_NAME}</h1>
        </div>

        <p className="gov-auth-intro">
          Records and tracks sugarcane pest cases from the initial report through field
          inspection, validation, intervention, and follow-up, with each case&apos;s
          history kept in one place.
        </p>

        <div className="gov-auth-workflow">
          <p className="gov-auth-stages-title">Case workflow</p>
          <ol className="gov-auth-stages">
            <li>Pest case reported</li>
            <li>Inspection scheduled and assigned</li>
            <li>Field validation of findings</li>
            <li>Intervention recorded by authorized personnel</li>
            <li>Follow-up and reassessment</li>
            <li>Resolved and closed, or further intervention</li>
          </ol>
        </div>

        <div className="gov-auth-footer">
          <p>For authorized personnel of the {OFFICE_NAME}.</p>
        </div>
      </section>

      <main className="gov-auth-main">{children}</main>
    </div>
  );
}
