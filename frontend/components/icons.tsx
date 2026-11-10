import type { ReactNode } from "react";

/*
 * Small inline icon set (24px grid, 1.75 stroke). Icons support labels and
 * never replace the text of a critical action. Decorative by default.
 */
const PATHS = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="8.5" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="5" rx="1.5" />
      <rect x="13.5" y="11.5" width="7" height="9" rx="1.5" />
      <rect x="3.5" y="15" width="7" height="5.5" rx="1.5" />
    </>
  ),
  farmers: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5" />
      <path d="M15.5 4.8a3.5 3.5 0 0 1 0 6.4" />
      <path d="M18 14.9c1.8.8 3 2.5 3.4 5.1" />
    </>
  ),
  farm: (
    <>
      <path d="M3.5 20.5h17" />
      <path d="M5 20.5V10l7-5.5 7 5.5v10.5" />
      <path d="M9.5 20.5v-5.5h5v5.5" />
      <path d="M9.5 10.5h5" />
    </>
  ),
  pest: (
    <>
      <rect x="8" y="7.5" width="8" height="12.5" rx="4" />
      <path d="M12 7.5V5" />
      <path d="M10 5 8.5 3.5M14 5l1.5-1.5" />
      <path d="M8 11.5H4.5M8 15.5H5M16 11.5h3.5M16 15.5h3" />
      <path d="M12 11v9" />
    </>
  ),
  inspection: (
    <>
      <path d="M9 4.5H7a2 2 0 0 0-2 2V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6.5a2 2 0 0 0-2-2h-2" />
      <rect x="9" y="3" width="6" height="3" rx="1" />
      <path d="m9 13.5 2 2 4-4.5" />
    </>
  ),
  intervention: (
    <>
      <path d="M12 21v-8.5" />
      <path d="M12 12.5c0-4.2 2.8-7 7-7 0 4.2-2.8 7-7 7Z" />
      <path d="M12 15c0-3.2-2.2-5.2-5.5-5.2 0 3.2 2.2 5.2 5.5 5.2Z" />
    </>
  ),
  "follow-up": (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 10h17" />
      <path d="M8 3v4M16 3v4" />
      <path d="m9.5 15.2 1.8 1.8 3.4-3.5" />
    </>
  ),
  map: (
    <>
      <path d="M9 4.5 3.5 6.5v13L9 17.5l6 2 5.5-2v-13L15 6.5l-6-2Z" />
      <path d="M9 4.5v13M15 6.5v13" />
    </>
  ),
  reports: (
    <>
      <path d="M4 20.5h16" />
      <path d="M7 16.5v-5M12 16.5V6.5M17 16.5V9.5" />
    </>
  ),
  "user-admin": (
    <>
      <path d="M12 3 5 6v5c0 4.5 3 8.3 7 9.5 4-1.2 7-5 7-9.5V6l-7-3Z" />
      <circle cx="12" cy="10" r="2.5" />
      <path d="M8.5 16c.7-1.5 2-2.4 3.5-2.4s2.8.9 3.5 2.4" />
    </>
  ),
  logout: (
    <>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="m10 17-5-5 5-5" />
      <path d="M5 12h11" />
    </>
  ),
  menu: <path d="M4 6.5h16M4 12h16M4 17.5h16" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  "chevron-right": <path d="m9.5 6 6 6-6 6" />,
  "arrow-left": (
    <>
      <path d="M19 12H5" />
      <path d="m11 6-6 6 6 6" />
    </>
  ),
  "arrow-right": (
    <>
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  "eye-off": (
    <>
      <path d="M3 3l18 18" />
      <path d="M10.6 5.6c.5-.1.9-.1 1.4-.1 6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-3 3.9" />
      <path d="M6.6 6.6C3.9 8.4 2.5 12 2.5 12S6 18.5 12 18.5c1.8 0 3.4-.6 4.7-1.4" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 11a8 8 0 0 0-14.6-4.5L4 8" />
      <path d="M4 3.5V8h4.5" />
      <path d="M4 13a8 8 0 0 0 14.6 4.5L20 16" />
      <path d="M20 20.5V16h-4.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  printer: (
    <>
      <path d="M7 9V3.5h10V9" />
      <rect x="3.5" y="9" width="17" height="8" rx="2" />
      <path d="M7 14h10v6.5H7z" />
    </>
  ),
  "alert-triangle": (
    <>
      <path d="M12 3.5 2.5 20h19L12 3.5Z" />
      <path d="M12 10v4" />
      <path d="M12 17h.01" />
    </>
  ),
  "check-circle": (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  history: (
    <>
      <path d="M3.5 12a8.5 8.5 0 1 0 2.5-6L3.5 8.5" />
      <path d="M3.5 4v4.5H8" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  "map-pin": (
    <>
      <path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z" />
      <circle cx="12" cy="10" r="2.5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.75" />
      <path d="M4.5 20.5c.8-3.7 3.8-6 7.5-6s6.7 2.3 7.5 6" />
    </>
  ),
  lock: (
    <>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </>
  ),
  "file-text": (
    <>
      <path d="M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-10L14 3.5Z" />
      <path d="M14 3.5v5h5" />
      <path d="M8.5 13h7M8.5 16.5h5" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

type IconProps = {
  name: IconName;
  size?: number;
  className?: string;
  /** Accessible name; omit for decorative icons beside visible text. */
  title?: string;
};

export function Icon({ name, size = 18, className, title }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className ? `gov-icon ${className}` : "gov-icon"}
      focusable="false"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}
