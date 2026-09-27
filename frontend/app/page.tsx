import SystemStatus from "@/components/system-status";

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 px-6 py-12">
      <div className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-12">
        <p className="text-sm font-semibold uppercase tracking-wide text-emerald-700">
          Bais City Agriculturist&apos;s Office
        </p>

        <h1 className="mt-5 text-3xl font-semibold leading-tight tracking-tight text-slate-900 sm:text-4xl">
          Sugarcane Pest Inspection and Intervention Workflow Management System
        </h1>

        <p className="mt-5 text-base text-slate-600">
          Frontend foundation ready.
        </p>

        <SystemStatus />
      </div>
    </main>
  );
}
