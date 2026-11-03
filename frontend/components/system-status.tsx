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

function statusToneClass(status: DisplayStatus | "Running") {
  if (status === "Running" || status === "Connected") {
    return "gov-tone-success";
  }

  if (status === "Unavailable") {
    return "gov-tone-warning";
  }

  return "gov-tone-neutral";
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
    <section aria-label="System status" className="gov-system-status">
      <h2 className="gov-system-status-title">System status</h2>
      <dl className="gov-system-status-list">
        {rows.map(({ label, value }) => (
          <div key={label} className="gov-system-status-row">
            <dt>{label}</dt>
            <dd className={`gov-status-badge ${statusToneClass(value)}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <p role="status" className="gov-field-help">
        {status.message}
      </p>
    </section>
  );
}
