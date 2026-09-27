"use client";

import { useEffect, useState } from "react";

import { fetchHealth } from "@/lib/api";

type DisplayStatus = "Checking" | "Connected" | "Unavailable";

type SystemStatusState = {
  backend: DisplayStatus;
  database: DisplayStatus;
  message: string;
};

const initialStatus: SystemStatusState = {
  backend: "Checking",
  database: "Checking",
  message: "Checking local services...",
};

function statusClass(status: DisplayStatus | "Running") {
  if (status === "Running" || status === "Connected") {
    return "bg-emerald-100 text-emerald-800";
  }

  if (status === "Unavailable") {
    return "bg-amber-100 text-amber-800";
  }

  return "bg-slate-200 text-slate-700";
}

export default function SystemStatus() {
  const [status, setStatus] = useState<SystemStatusState>(initialStatus);

  useEffect(() => {
    const controller = new AbortController();

    fetchHealth(controller.signal)
      .then((health) => {
        const backend =
          health.data.backend === "connected" ? "Connected" : "Unavailable";
        const database =
          health.data.database === "connected" ? "Connected" : "Unavailable";

        setStatus({
          backend,
          database,
          message:
            backend === "Unavailable"
              ? "Backend health service is unavailable."
              : database === "Unavailable"
                ? "Database health check failed."
                : "System health check successful.",
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setStatus({
            backend: "Unavailable",
            database: "Unavailable",
            message: "Backend health service is unavailable.",
          });
        }
      });

    return () => controller.abort();
  }, []);

  const rows = [
    { label: "Frontend", value: "Running" as const },
    { label: "Backend", value: status.backend },
    { label: "Database", value: status.database },
  ];

  return (
    <section aria-label="System status" className="mt-10">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
        System status
      </h2>
      <dl className="mt-4 divide-y divide-slate-200 rounded-xl border border-slate-200 bg-slate-50 px-5">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between gap-4 py-4">
            <dt className="font-medium text-slate-700">{label}</dt>
            <dd
              className={`rounded-full px-3 py-1 text-sm font-semibold ${statusClass(value)}`}
            >
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <p role="status" className="mt-4 text-sm text-slate-600">
        {status.message}
      </p>
    </section>
  );
}
