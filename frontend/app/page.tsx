import Link from "next/link";

import { AuthLayout } from "@/components/auth-layout";
import { Icon } from "@/components/icons";

export default function Home() {
  return (
    <AuthLayout>
      <div className="gov-auth-card">
        <p className="gov-auth-eyebrow">Internal system</p>
        <h2 className="gov-auth-title">Staff access</h2>
        <p className="gov-auth-text">
          Record and track sugarcane pest cases from field validation through intervention
          and follow-up.
        </p>

        <div className="gov-auth-pending">
          <Link href="/login" className="gov-button gov-button-primary gov-button-block">
            Sign in
            <Icon name="arrow-right" size={18} />
          </Link>
        </div>

        <p className="gov-auth-note">
          <Icon name="lock" size={16} />
          Authorized personnel only.
        </p>
      </div>
    </AuthLayout>
  );
}
