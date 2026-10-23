"use client";

import { Component, useMemo, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";

import {
  FARM_MAP_LEGEND,
  farmsForMap,
  type FarmMapFarm,
  type FarmMapFilter,
} from "@/lib/farm-map";

const FarmMonitoringMapClient = dynamic(
  () => import("@/components/farm-monitoring-map-client"),
  {
    ssr: false,
    loading: () => (
      <div className="gov-monitoring-map-message" role="status">
        Loading interactive map...
      </div>
    ),
  },
);

const FILTERS: { value: FarmMapFilter; label: string }[] = [
  { value: "ALL", label: "All Farms" },
  { value: "ACTIVE", label: "Active Cases" },
  { value: "NEEDS_ATTENTION", label: "Needs Attention" },
  { value: "TERMINAL", label: "Closed / Terminal" },
];

class MonitoringMapErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? (
      <div className="gov-monitoring-map-message" role="alert">
        The interactive map could not be displayed. Farm counts remain available.
      </div>
    ) : (
      this.props.children
    );
  }
}

export default function FarmMonitoringMap({ farms }: { farms: FarmMapFarm[] }) {
  const [filter, setFilter] = useState<FarmMapFilter>("ALL");
  const mapped = useMemo(() => farmsForMap(farms, filter), [farms, filter]);
  const unmapped = useMemo(() => farms.filter((farm) => farm.location === null), [farms]);

  return (
    <>
      <div className="gov-map-toolbar" aria-label="Farm map filters">
        {FILTERS.map((item) => (
          <button
            key={item.value}
            type="button"
            className={`gov-map-filter${filter === item.value ? " gov-map-filter-active" : ""}`}
            aria-pressed={filter === item.value}
            onClick={() => setFilter(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {mapped.length === 0 ? (
        <div className="gov-monitoring-map-message" role="status">
          {farms.some((farm) => farm.location !== null)
            ? "No mapped farms match this filter."
            : "No farms have an approximate map location yet."}
        </div>
      ) : (
        <MonitoringMapErrorBoundary key={filter}>
          <FarmMonitoringMapClient farms={mapped} />
        </MonitoringMapErrorBoundary>
      )}

      <div className="gov-map-supporting-grid">
        <section aria-labelledby="farm-map-legend-heading">
          <h3 id="farm-map-legend-heading" className="gov-map-subheading">Map legend</h3>
          <ul className="gov-map-legend">
            {FARM_MAP_LEGEND.map((item) => (
              <li key={item.legendLabel}>
                <span
                  className="gov-map-legend-dot"
                  style={{ backgroundColor: item.color }}
                  aria-hidden="true"
                />
                {item.legendLabel}
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="unmapped-farms-heading">
          <h3 id="unmapped-farms-heading" className="gov-map-subheading">
            Unmapped farms ({unmapped.length})
          </h3>
          {unmapped.length === 0 ? (
            <p className="gov-map-help">All registered farms have map locations.</p>
          ) : (
            <details className="gov-unmapped-details">
              <summary>Show farms without locations</summary>
              <ul>
                {unmapped.map((farm) => (
                  <li key={farm.id}>
                    {farm.plot_identifier} — {farm.farmer.full_name}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      </div>
    </>
  );
}
