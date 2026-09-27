import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sugarcane Pest Workflow Management System",
  description:
    "Locally hosted sugarcane pest inspection and intervention workflow management system for the Bais City Agriculturist's Office.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
