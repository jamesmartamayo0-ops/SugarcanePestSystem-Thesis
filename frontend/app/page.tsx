import Link from "next/link";

import SystemStatus from "@/components/system-status";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-12">
      <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-12">
        <p className="gov-office-name text-sm font-semibold uppercase tracking-wide">
          Bais City Agriculturist&apos;s Office
        </p>

        <h1 className="mt-5 text-3xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Sugarcane Pest Inspection and Intervention Workflow Management System
        </h1>

        <p className="mt-5 text-base text-slate-600">
          Frontend foundation ready.
        </p>

        <Link
          href="/login"
          className="mt-6 inline-flex rounded-lg bg-emerald-700 px-4 py-2 font-medium text-white hover:bg-emerald-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
        >
          Sign in
        </Link>

        <SystemStatus />
      </div>
    </main>
  );
}
