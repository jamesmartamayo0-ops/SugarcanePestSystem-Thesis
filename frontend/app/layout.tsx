import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { AuthProvider } from "@/components/auth-provider";
import { OFFICE_NAME } from "@/lib/branding";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sugarcane Pest Workflow Management System",
  description: `Locally hosted sugarcane pest inspection and intervention workflow management system for the ${OFFICE_NAME}.`,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
