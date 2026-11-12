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
 * identity on the left, the task on the right.
 */
export function AuthLayout({ children }: { children: ReactNode }) {
  const year = new Date().getFullYear();

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

        <div className="gov-auth-footer">
          <p>For authorized personnel of the {OFFICE_NAME}.</p>
          <p>
            &copy; {year} {OFFICE_NAME}. All rights reserved.
          </p>
        </div>
      </section>

      <main className="gov-auth-main">
        {children}
        <p className="gov-auth-legal">
          Use of this system is monitored. Unauthorized access is prohibited.
        </p>
      </main>
    </div>
  );
}
