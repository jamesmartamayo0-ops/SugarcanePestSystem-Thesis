"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

/*
 * Loading placeholders. Presentation only: no data, no requests, no workflow
 * or permission logic. A skeleton is shown strictly while a request is in
 * flight; pages keep rendering their own error and empty states unchanged.
 *
 * Every placeholder shape is decorative (aria-hidden, never focusable). The
 * accessible message is the visually hidden label of <LoadingRegion>.
 */

/** After this long a visible "still loading" notice joins the skeleton. */
export const SLOW_LOADING_MS = 12_000;

export const SLOW_LOADING_MESSAGE =
  "This is taking longer than usual. Check your connection, or refresh the page if it does not finish.";

function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(" ");
}

type SkeletonProps = {
  width?: CSSProperties["width"];
  height?: CSSProperties["height"];
  className?: string;
};

/** One decorative placeholder block. */
export function Skeleton({ width, height, className }: SkeletonProps) {
  return (
    <span
      aria-hidden="true"
      className={cx("gov-skeleton", className)}
      style={width !== undefined || height !== undefined ? { width, height } : undefined}
    />
  );
}

type SkeletonTextProps = {
  lines?: number;
  /** Widths per line; the last value repeats for any remaining lines. */
  widths?: CSSProperties["width"][];
  className?: string;
};

export function SkeletonText({ lines = 2, widths = ["100%", "72%"], className }: SkeletonTextProps) {
  return (
    <span aria-hidden="true" className={cx("gov-skeleton-text", className)}>
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} width={widths[Math.min(index, widths.length - 1)]} />
      ))}
    </span>
  );
}

function useSlowLoading(delayMs: number): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setSlow(true), delayMs);
    return () => window.clearTimeout(timer);
  }, [delayMs]);
  return slow;
}

type LoadingRegionProps = {
  /** Announced to screen readers, e.g. "Loading pest cases". */
  label: string;
  children: ReactNode;
  className?: string;
  slowAfterMs?: number;
};

/**
 * Accessible wrapper around decorative skeleton shapes. It exposes a single
 * polite status message and, if loading runs long, a visible notice so the
 * placeholder never sits silently forever.
 */
export function LoadingRegion({
  label,
  children,
  className,
  slowAfterMs = SLOW_LOADING_MS,
}: LoadingRegionProps) {
  const slow = useSlowLoading(slowAfterMs);
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className={cx("gov-skeleton-region", className)}
    >
      <span className="sr-only">{slow ? `${label}. ${SLOW_LOADING_MESSAGE}` : label}</span>
      <div aria-hidden="true" className="gov-skeleton-body">
        {children}
      </div>
      {slow && (
        <p aria-hidden="true" className="gov-skeleton-slow">
          {SLOW_LOADING_MESSAGE}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Building blocks (decorative; render inside a LoadingRegion)         */
/* ------------------------------------------------------------------ */

type StatTilesProps = {
  count?: number;
  compact?: boolean;
  withIcon?: boolean;
  withNote?: boolean;
  className?: string;
};

/** Mirrors .gov-summary-grid / .gov-stat tiles. */
export function StatTilesSkeleton({
  count = 4,
  compact = false,
  withIcon = false,
  withNote = true,
  className,
}: StatTilesProps) {
  return (
    <div className={cx("gov-summary-grid", compact && "gov-summary-grid--compact", className)}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="gov-stat">
          <div className="gov-stat-head">
            <Skeleton className="gov-skeleton-stat-label" width="52%" />
            {withIcon && <Skeleton className="gov-skeleton-stat-icon" />}
          </div>
          <Skeleton className="gov-skeleton-stat-value" />
          {withNote && <Skeleton className="gov-skeleton-stat-note" width="44%" />}
        </div>
      ))}
    </div>
  );
}

type TableSkeletonBodyProps = {
  /** Real column headings of the table being loaded (static labels, not data). */
  columns: string[];
  rows?: number;
  /** Matches the loaded table's min-width utility, e.g. "min-w-[720px]". */
  tableClassName?: string;
  className?: string;
};

/** Mirrors .gov-table-wrap / .gov-table with placeholder rows. */
export function TableSkeletonBody({
  columns,
  rows = 5,
  tableClassName,
  className,
}: TableSkeletonBodyProps) {
  const last = columns.length - 1;
  return (
    <div className={cx("gov-table-wrap gov-skeleton-table-wrap", className)}>
      <table className={cx("gov-table gov-skeleton-table", tableClassName)}>
        <thead>
          <tr>
            {columns.map((column, index) => (
              <th key={column} className={index === last ? "gov-col-actions" : undefined}>
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, row) => (
            <tr key={row}>
              {columns.map((column, index) => (
                <td key={column} className={index === last ? "gov-col-actions" : undefined}>
                  {index === last ? (
                    <Skeleton className="gov-skeleton-button" />
                  ) : index === 0 ? (
                    <SkeletonText lines={2} widths={[row % 2 ? "70%" : "82%", "46%"]} />
                  ) : (
                    <SkeletonText lines={1} widths={[(row + index) % 3 === 0 ? "54%" : "74%"]} />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Field label + value pairs laid out like .gov-detail-grid. */
export function DetailGridSkeleton({ fields = 4, className }: { fields?: number; className?: string }) {
  return (
    <div className={cx("gov-detail-grid", className)}>
      {Array.from({ length: fields }, (_, index) => (
        <div key={index}>
          <Skeleton className="gov-skeleton-detail-label" width={index % 2 ? "38%" : "46%"} />
          <Skeleton className="gov-skeleton-detail-value" width={index % 3 === 2 ? "58%" : "76%"} />
        </div>
      ))}
    </div>
  );
}

/** Title row of a record panel: eyebrow, title, status badge, action. */
export function RecordToolbarSkeleton() {
  return (
    <div className="gov-record-toolbar">
      <div className="gov-skeleton-heading">
        <Skeleton className="gov-skeleton-eyebrow" width={150} />
        <Skeleton className="gov-skeleton-title" width={220} />
      </div>
      <span className="gov-table-actions">
        <Skeleton className="gov-skeleton-badge" />
        <Skeleton className="gov-skeleton-button gov-skeleton-button--wide" />
      </span>
    </div>
  );
}

/** "Initial report" versus "field validation" side-by-side panels. */
export function ComparePanelsSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <div className="gov-compare">
      {[0, 1].map((panel) => (
        <div key={panel} className="gov-compare-panel">
          <div className="gov-compare-head">
            <Skeleton className="gov-skeleton-title" width="46%" />
            <Skeleton className="gov-skeleton-badge" />
          </div>
          <DetailGridSkeleton fields={fields} />
        </div>
      ))}
    </div>
  );
}

/** Thumbnail tiles laid out like <EvidencePhotoGallery>. */
export function EvidencePhotosSkeleton({ count = 3 }: { count?: number }) {
  return (
    <LoadingRegion label="Loading evidence photos">
      <div className="gov-photo-grid">
        {Array.from({ length: count }, (_, index) => (
          <span key={index} className="gov-photo-link">
            <Skeleton className="gov-skeleton-photo" />
            <Skeleton className="gov-skeleton-photo-caption" width="70%" />
          </span>
        ))}
      </div>
    </LoadingRegion>
  );
}

/** Rows of a label/count list (.gov-report-list, .gov-progress-list). */
export function CountListSkeleton({ rows, className }: { rows: number; className?: string }) {
  return (
    <div className={cx("gov-skeleton-count-list", className)}>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="gov-skeleton-count-row">
          <Skeleton width={index % 2 ? "46%" : "60%"} />
          <Skeleton className="gov-skeleton-count" />
        </div>
      ))}
    </div>
  );
}

/** Same footprint as the interactive farm monitoring map. */
export function MapCanvasSkeleton({ small = false }: { small?: boolean }) {
  return (
    <div className={small ? "gov-map-message gov-skeleton-map" : "gov-monitoring-map-message gov-skeleton-map"}>
      <span className="gov-skeleton-map-pin" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Ready-made skeletons                                                */
/* ------------------------------------------------------------------ */

type TableSkeletonProps = TableSkeletonBodyProps & { label: string };

/** Loading placeholder for a records table. */
export function TableSkeleton({ label, ...table }: TableSkeletonProps) {
  return (
    <LoadingRegion label={label}>
      <TableSkeletonBody {...table} />
    </LoadingRegion>
  );
}

type DetailSkeletonProps = {
  label: string;
  fields?: number;
  compare?: boolean;
};

/** Loading placeholder for a selected-record detail panel. */
export function DetailSkeleton({ label, fields = 4, compare = false }: DetailSkeletonProps) {
  return (
    <LoadingRegion label={label}>
      <RecordToolbarSkeleton />
      <DetailGridSkeleton fields={fields} />
      {compare && <ComparePanelsSkeleton />}
    </LoadingRegion>
  );
}

/** Loading placeholder for a form whose options are still being read. */
export function FormSkeleton({ label, fields = 4 }: { label: string; fields?: number }) {
  return (
    <LoadingRegion label={label} className="gov-skeleton-form">
      <div className="gov-form-grid">
        {Array.from({ length: fields }, (_, index) => (
          <div key={index} className="gov-field">
            <Skeleton className="gov-skeleton-field-label" width={index % 2 ? "34%" : "42%"} />
            <Skeleton className="gov-skeleton-input" />
          </div>
        ))}
      </div>
      <Skeleton className="gov-skeleton-button gov-skeleton-button--wide gov-skeleton-form-action" />
    </LoadingRegion>
  );
}

/** Loading placeholder for the monitoring map: summary tiles plus map canvas. */
export function MonitoringMapSkeleton({ label = "Loading farm monitoring map" }: { label?: string }) {
  return (
    <LoadingRegion label={label}>
      <StatTilesSkeleton
        compact
        className="gov-map-summary-grid"
      />
      <MapCanvasSkeleton />
    </LoadingRegion>
  );
}

/** Loading placeholder for the map canvas alone (map script still loading). */
export function MapCanvasLoading({ label, small = false }: { label: string; small?: boolean }) {
  return (
    <LoadingRegion label={label}>
      <MapCanvasSkeleton small={small} />
    </LoadingRegion>
  );
}

type DashboardSkeletonProps = {
  attentionCards: number;
  /** Number of status rows in each workflow-stage group. */
  pipelineGroups: number[];
  progressRows: number;
};

/** Loading placeholder matching the dashboard's operational summary. */
export function DashboardSummarySkeleton({
  attentionCards,
  pipelineGroups,
  progressRows,
}: DashboardSkeletonProps) {
  return (
    <LoadingRegion label="Loading operational summary">
      <StatTilesSkeleton withIcon />

      <div className="gov-dashboard-section">
        <div className="gov-section-bar">
          <div className="gov-skeleton-heading">
            <Skeleton className="gov-skeleton-title" width={180} />
            <Skeleton className="gov-skeleton-meta" width={260} />
          </div>
        </div>
        <div className="gov-attention-grid">
          {Array.from({ length: attentionCards }, (_, index) => (
            <div key={index} className="gov-attention-card gov-skeleton-attention-card">
              <Skeleton className="gov-skeleton-badge" />
              <SkeletonText lines={2} widths={["86%", "52%"]} className="gov-skeleton-attention-title" />
              <Skeleton className="gov-skeleton-attention-count" />
              <SkeletonText lines={2} widths={["100%", "64%"]} />
            </div>
          ))}
        </div>
      </div>

      <div className="gov-card gov-dashboard-section">
        <div className="gov-card-header">
          <div className="gov-skeleton-heading">
            <Skeleton className="gov-skeleton-title" width={210} />
            <Skeleton className="gov-skeleton-meta" width={300} />
          </div>
        </div>
        <div className="gov-pipeline">
          {pipelineGroups.map((rows, index) => (
            <div key={index} className="gov-pipeline-group">
              <Skeleton className="gov-skeleton-title" width="58%" />
              <CountListSkeleton rows={rows} className="gov-skeleton-pipeline-list" />
            </div>
          ))}
        </div>
      </div>

      <div className="gov-dashboard-grid">
        <div className="gov-card gov-section">
          <div className="gov-card-header">
            <div className="gov-skeleton-heading">
              <Skeleton className="gov-skeleton-title" width={180} />
              <Skeleton className="gov-skeleton-meta" width={220} />
            </div>
          </div>
          <div className="gov-activity-list">
            {Array.from({ length: 5 }, (_, index) => (
              <div key={index} className="gov-activity-item">
                <SkeletonText lines={2} widths={[index % 2 ? "150px" : "190px", "220px"]} />
                <span className="gov-activity-actions">
                  <Skeleton className="gov-skeleton-badge" />
                  <Skeleton className="gov-skeleton-button gov-skeleton-button--wide" />
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="gov-card gov-section">
          <div className="gov-card-header">
            <div className="gov-skeleton-heading">
              <Skeleton className="gov-skeleton-title" width={170} />
              <Skeleton className="gov-skeleton-meta" width={230} />
            </div>
          </div>
          <CountListSkeleton rows={progressRows} className="gov-progress-list" />
        </div>
      </div>
    </LoadingRegion>
  );
}

/** Loading placeholder matching the operational report body. */
export function ReportSkeleton({ statusRows, tableColumns }: { statusRows: number; tableColumns: string[] }) {
  return (
    <LoadingRegion label="Loading operational report">
      <div className="gov-card gov-record-section">
        <Skeleton className="gov-skeleton-title" width={110} />
        <Skeleton className="gov-skeleton-meta" width={200} />
        <StatTilesSkeleton withNote={false} className="gov-report-summary" />
      </div>

      <div className="gov-report-columns">
        <div className="gov-card gov-record-section">
          <Skeleton className="gov-skeleton-title" width={140} />
          <CountListSkeleton rows={statusRows} className="gov-skeleton-report-list" />
        </div>
        <div className="gov-report-stack">
          {[5, 4].map((rows, index) => (
            <div key={index} className="gov-card gov-record-section">
              <Skeleton className="gov-skeleton-title" width={170} />
              <CountListSkeleton rows={rows} className="gov-skeleton-report-list" />
            </div>
          ))}
        </div>
      </div>

      <div className="gov-card gov-record-section">
        <Skeleton className="gov-skeleton-title" width={120} />
        <Skeleton className="gov-skeleton-meta" width={220} />
        <TableSkeletonBody columns={tableColumns} tableClassName="min-w-[860px]" className="mt-3" />
      </div>
    </LoadingRegion>
  );
}

/** Matches the number of stages drawn by <CaseProgress>. */
const CASE_STAGE_COUNT = 6;

/** Loading placeholder for a full case record (progress, sections, aside). */
export function CaseRecordSkeleton() {
  return (
    <LoadingRegion label="Loading case record">
      <div className="gov-steps">
        <div className="gov-steps-head">
          <Skeleton className="gov-skeleton-meta" width={110} />
          <Skeleton className="gov-skeleton-meta" width={240} />
        </div>
        <div className="gov-steps-list">
          {Array.from({ length: CASE_STAGE_COUNT }, (_, index) => (
            <span key={index} className="gov-step-inner">
              <Skeleton className="gov-skeleton-step-marker" />
              <SkeletonText lines={2} widths={["70%", "90%"]} className="gov-skeleton-step-text" />
            </span>
          ))}
        </div>
      </div>
      <div className="gov-case-layout">
        <div className="gov-case-main">
          <div className="gov-card gov-record-section">
            <Skeleton className="gov-skeleton-title" width={240} />
            <SkeletonText lines={2} widths={["90%", "60%"]} className="gov-skeleton-intro" />
            <ComparePanelsSkeleton fields={4} />
          </div>
          <div className="gov-card gov-record-section">
            <Skeleton className="gov-skeleton-title" width={180} />
            <DetailGridSkeleton fields={4} />
          </div>
        </div>
        <div className="gov-case-aside">
          {[4, 3].map((fields, index) => (
            <div key={index} className="gov-card gov-record-section">
              <Skeleton className="gov-skeleton-title" width={140} />
              <DetailGridSkeleton fields={fields} className="gov-skeleton-aside-grid" />
            </div>
          ))}
        </div>
      </div>
    </LoadingRegion>
  );
}
