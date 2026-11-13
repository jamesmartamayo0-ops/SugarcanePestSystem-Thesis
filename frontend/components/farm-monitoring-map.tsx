"use client";

import { Component, useMemo, useState, type ReactNode } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";

import {
  FARM_MAP_LEGEND,
  farmMapFilterCounts,
  farmsForMap,
  type FarmMapFarm,
  type FarmMapFilter,
} from "@/lib/farm-map";
import { MapCanvasLoading } from "@/components/skeleton";

const FarmMonitoringMapClient = dynamic(
  () => import("@/components/farm-monitoring-map-client"),
  {
    ssr: false,
    loading: () => <MapCanvasLoading label="Loading interactive map" />,
  },
);

const FILTERS: { value: FarmMapFilter; label: string }[] = [
  { value: "ALL", label: "All farms" },
  { value: "ACTIVE", label: "Active cases" },
  { value: "NEEDS_ATTENTION", label: "Needs attention" },
  { value: "TERMINAL", label: "Closed / not confirmed" },
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

export default function FarmMonitoringMap({
  farms,
  showRecordLinks,
}: {
  farms: FarmMapFarm[];
  showRecordLinks: boolean;
}) {
  const [filter, setFilter] = useState<FarmMapFilter>("ALL");
  const mapped = useMemo(() => farmsForMap(farms, filter), [farms, filter]);
  const counts = useMemo(() => farmMapFilterCounts(farms), [farms]);
  const unmapped = useMemo(() => farms.filter((farm) => farm.location === null), [farms]);

  return (
    <>
      <div className="gov-map-toolbar">
        <div className="gov-map-filter-group" role="group" aria-label="Farm map filters">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={`gov-map-filter${filter === item.value ? " gov-map-filter-active" : ""}`}
              aria-pressed={filter === item.value}
              onClick={() => setFilter(item.value)}
            >
              <span>{item.label}</span>
              <span className="gov-map-filter-count" aria-hidden="true">
                {counts[item.value]}
              </span>
            </button>
          ))}
        </div>
        <p className="gov-map-filter-summary" role="status">
          Showing {mapped.length} of {counts.ALL} mapped {counts.ALL === 1 ? "farm" : "farms"}.
        </p>
      </div>

      {mapped.length === 0 ? (
        <div className="gov-monitoring-map-message gov-map-empty" role="status">
          {counts.ALL > 0 ? (
            "No mapped farms match this filter."
          ) : (
            <span>
              No mapped farms available. Farms appear here once an approximate location is
              recorded{showRecordLinks ? (
                <>
                  {" "}on the{" "}
                  <Link href="/farms" className="gov-activity-link">
                    Farms page
                  </Link>
                  .
                </>
              ) : (
                "."
              )}
            </span>
          )}
        </div>
      ) : (
        <MonitoringMapErrorBoundary key={filter}>
          <FarmMonitoringMapClient farms={mapped} showRecordLinks={showRecordLinks} />
        </MonitoringMapErrorBoundary>
      )}

      <div className="gov-map-supporting-grid">
        <section aria-labelledby="farm-map-status-heading">
          <h3 id="farm-map-status-heading" className="gov-map-subheading">
            Status guide
          </h3>
          <p className="gov-map-help">
            Marker colours show the latest workflow state you are authorized to see for
            each farm. Hover over a marker for a summary, or select it to review farm and
            case details.
          </p>
          <ul className="gov-map-legend">
            {FARM_MAP_LEGEND.map((item) => (
              <li key={item.legendLabel}>
                <span
                  className="gov-map-legend-dot"
                  style={{ backgroundColor: item.color }}
                  aria-hidden="true"
                />
                <span>{item.legendLabel}</span>
              </li>
            ))}
          </ul>
        </section>
        <section aria-labelledby="unmapped-farms-heading">
          <h3 id="unmapped-farms-heading" className="gov-map-subheading">
            Unmapped farms ({unmapped.length})
          </h3>
          <p className="gov-map-help">
            Farms without an approximate location remain in the registry but do not
            appear as markers.
          </p>
          {unmapped.length === 0 ? (
            <p className="gov-map-help">All authorized farms have map locations.</p>
          ) : (
            <details className="gov-unmapped-details">
              <summary>Show farms without locations</summary>
              <ul>
                {unmapped.map((farm) => (
                  <li key={farm.id}>
                    {farm.plot_identifier} — {farm.farmer.full_name} ({farm.barangay})
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
