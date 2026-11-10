"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";

import { Icon } from "@/components/icons";
import { BAIS_CITY_SEAL_ALT, BAIS_CITY_SEAL_SRC, OFFICE_NAME } from "@/lib/branding";

/*
 * Shared presentation components. They hold no workflow or permission logic:
 * pages decide what to show, these only decide how it looks.
 */

type SealProps = {
  size: number;
  className?: string;
  decorative?: boolean;
};

/** Official City of Bais seal, always rendered at its native square ratio. */
export function Seal({ size, className, decorative = false }: SealProps) {
  return (
    <span
      className={className ? `gov-seal ${className}` : "gov-seal"}
      style={{ width: size, height: size }}
    >
      <Image
        src={BAIS_CITY_SEAL_SRC}
        alt={decorative ? "" : BAIS_CITY_SEAL_ALT}
        width={size * 2}
        height={size * 2}
        loading="eager"
      />
    </span>
  );
}

export type RelatedLink = { href: string; label: string };

type PageHeaderProps = {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  related?: RelatedLink[];
  backLink?: RelatedLink;
};

export function PageHeader({ title, description, actions, related, backLink }: PageHeaderProps) {
  return (
    <header className="gov-page-header">
      <div className="gov-page-heading">
        {backLink && (
          <Link href={backLink.href} className="gov-back-link">
            <Icon name="arrow-left" size={16} />
            {backLink.label}
          </Link>
        )}
        <h1 className="gov-page-title">{title}</h1>
        {description && <p className="gov-page-description">{description}</p>}
        {related && related.length > 0 && (
          <nav aria-label="Related pages" className="gov-related">
            <span className="gov-related-label">Related</span>
            <ul>
              {related.map((link) => (
                <li key={link.href}>
                  <Link href={link.href} className="gov-related-link">
                    {link.label}
                    <Icon name="chevron-right" size={14} />
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        )}
      </div>
      {actions && <div className="gov-page-actions">{actions}</div>}
    </header>
  );
}

/** Explains the required-field marker once per form. */
export function RequiredLegend() {
  return (
    <p className="gov-form-legend">
      Fields marked <span className="gov-required" aria-hidden="true">*</span>
      <span className="sr-only">with an asterisk</span> are required.
    </p>
  );
}

/** Full-screen branded status message (session checks and redirects). */
export function StatusScreen({ message }: { message: string }) {
  return (
    <main className="gov-status-page">
      <div className="gov-status-card">
        <Seal size={64} decorative />
        <p className="gov-status-office">{OFFICE_NAME}</p>
        <p role="status" className="gov-status-message">
          {message}
        </p>
      </div>
    </main>
  );
}

type SessionNoticeProps = {
  status: "loading" | "unauthenticated" | "error";
};

/** Shown by every authenticated page until the session is confirmed. */
export function SessionNotice({ status }: SessionNoticeProps) {
  if (status === "error") {
    return (
      <main className="gov-status-page">
        <div className="gov-status-card">
          <Seal size={64} decorative />
          <h1 className="gov-status-title">Unable to verify your session</h1>
          <p className="gov-status-text">
            The authentication service is unavailable. Reload this page to try again.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="gov-button gov-button-primary"
          >
            <Icon name="refresh" size={16} />
            Reload
          </button>
        </div>
      </main>
    );
  }
  return (
    <StatusScreen
      message={status === "loading" ? "Checking your session..." : "Redirecting to sign in..."}
    />
  );
}

/**
 * Scrolls a panel into view and moves focus to it whenever `trigger`
 * becomes a new non-null value (for example, a record selected in a table).
 */
export function useRevealOnChange<T extends HTMLElement>(trigger: unknown) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (trigger === null || trigger === undefined || trigger === false) {
      return;
    }
    const node = ref.current;
    if (!node) {
      return;
    }
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    node.focus({ preventScroll: true });
  }, [trigger]);
  return ref;
}
