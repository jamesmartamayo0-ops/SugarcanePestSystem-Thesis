"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { formatDisplayDate, pestLabel, workflowLabel, workflowMessage } from "@/lib/presentation";
import { useAuth } from "@/components/auth-provider";
import { Icon } from "@/components/icons";
import {
  PageHeader,
  RequiredLegend,
  SessionNotice,
  useRevealOnChange,
} from "@/components/ui";
import { WorkflowSteps } from "@/components/workflow-steps";
import { DetailSkeleton, TableSkeleton } from "@/components/skeleton";
import {
  FollowUpsRequestError,
  dueBadgeLabel,
  dueStateFor,
  getFollowUp,
  listDueFollowUps,
  listFollowUps,
  manilaTodayIso,
  recordFollowUp,
  type FollowUpDetail,
  type FollowUpDueEntry,
  type FollowUpOutcome,
} from "@/lib/follow-ups";

function dueBadge(state: string | null): string {
  if (state === "OVERDUE") {
    return "gov-status-badge gov-due-overdue";
  }
  if (state === "DUE_TODAY") {
    return "gov-status-badge gov-due-today";
  }
  return "gov-status-badge gov-due-upcoming";
}

function outcomeBadge(outcome: string): string {
  if (outcome === "RESOLVED") {
    return "gov-status-badge gov-status-closed";
  }
  if (outcome === "REINTERVENTION_REQUIRED") {
    return "gov-status-badge gov-status-reintervention-required";
  }
  return "gov-status-badge";
}

function caseBadge(status: string): string {
  return `gov-status-badge gov-status-${status.toLowerCase().replaceAll("_", "-")}`;
}

function cycleLabel(history: FollowUpDetail[], entry: FollowUpDetail): string {
  const sameCase = history
    .filter((item) => item.pest_case?.id === entry.pest_case?.id)
    .sort((left, right) => left.intervention_id - right.intervention_id);
  const position = sameCase.findIndex((item) => item.id === entry.id);
  if (position < 0 || entry.pest_case === null) {
    return `Intervention #${entry.intervention_id}`;
  }
  return `Case #${entry.pest_case.id} — cycle ${position + 1} (intervention #${entry.intervention_id})`;
}

// Rendering only: date-only values retain their calendar day; timestamps use Manila time.
function formatRecordDate(value: string | null): string {
  if (value === null) {
    return "—";
  }
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  // Do not guess a timezone for an unqualified timestamp.
  if (!dateOnly && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) {
    return value;
  }
  const parsed = new Date(dateOnly ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-PH", {
    dateStyle: "medium",
    ...(dateOnly ? {} : { timeStyle: "short" as const }),
    timeZone: dateOnly ? "UTC" : "Asia/Manila",
  }).format(parsed);
}

export default function FollowUpsPage() {
  const router = useRouter();
  const auth = useAuth();
  const [due, setDue] = useState<FollowUpDueEntry[]>([]);
  const [history, setHistory] = useState<FollowUpDetail[]>([]);
  const [outcomeFilter, setOutcomeFilter] = useState<string>("all");
  const [caseFilter, setCaseFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [selectedInterventionId, setSelectedInterventionId] = useState<number | null>(null);
  const [selectedFollowUpId, setSelectedFollowUpId] = useState<number | null>(null);
  const [detail, setDetail] = useState<FollowUpDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const authenticated = auth.status === "authenticated";
  const role = auth.status === "authenticated" ? auth.user.role : null;
  const userId = auth.status === "authenticated" ? auth.user.id : null;
  const recordRef = useRevealOnChange<HTMLElement>(selectedInterventionId);
  const detailRef = useRevealOnChange<HTMLElement>(
    loadingDetail ? null : selectedFollowUpId,
  );

  const canRecord = useCallback(
    (entry: FollowUpDueEntry): boolean => {
      if (!authenticated) {
        return false;
      }
      if (role === "ADMIN") {
        return true;
      }
      return role === "TECHNICIAN" && entry.assigned_to_user_id === userId;
    },
    [authenticated, role, userId],
  );

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  const loadAll = useCallback(
    async (outcome: string, pestCase: string) => {
      setLoading(true);
      setListError(null);
      try {
        const [queue, recorded] = await Promise.all([
          listDueFollowUps(),
          listFollowUps({
            outcome:
              outcome === "all" ? undefined : (outcome as FollowUpOutcome),
            pestCaseId: pestCase === "all" ? undefined : Number(pestCase),
          }),
        ]);
        setDue(queue);
        setHistory(recorded);
      } catch (failure) {
        if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FollowUpsRequestError
            ? failure.message
            : "Follow-up records could not be read.",
        );
      } finally {
        setLoading(false);
      }
    },
    [router],
  );

  useEffect(() => {
    if (!authenticated) {
      return;
    }
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const [queue, recorded] = await Promise.all([
          listDueFollowUps(),
          listFollowUps(),
        ]);
        if (!active) {
          return;
        }
        setDue(queue);
        setHistory(recorded);
        setListError(null);
      } catch (failure: unknown) {
        if (!active) {
          return;
        }
        if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setListError(
          failure instanceof FollowUpsRequestError
            ? failure.message
            : "Follow-up records could not be read.",
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    })();
    return () => {
      active = false;
    };
  }, [authenticated, router]);

  const openDetail = useCallback(
    async (followUpId: number) => {
      setSelectedFollowUpId(followUpId);
      setDetail(null);
      setDetailError(null);
      setLoadingDetail(true);
      try {
        setDetail(await getFollowUp(followUpId));
      } catch (failure) {
        if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
          router.replace("/login");
          return;
        }
        setDetailError(
          failure instanceof FollowUpsRequestError
            ? failure.message
            : "Follow-up could not be read.",
        );
      } finally {
        setLoadingDetail(false);
      }
    },
    [router],
  );

  async function handleRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (auth.status !== "authenticated") {
      return;
    }
    setNotice(null);
    setFormError(null);
    if (selectedInterventionId === null) {
      setFormError("Select a pending intervention from the queue first.");
      return;
    }
    const selected = due.find(
      (entry) => entry.intervention_id === selectedInterventionId,
    );
    if (selected === undefined || !canRecord(selected)) {
      setSelectedInterventionId(null);
      setFormError("You do not have permission to record this follow-up.");
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const observedRaw = data.get("observed_on");
    const pestRaw = data.get("pest_observed");
    const areaRaw = data.get("observed_affected_area_hectares");
    const notesRaw = data.get("assessment_notes");
    const outcomeRaw = data.get("outcome");
    if (
      typeof observedRaw !== "string" ||
      observedRaw.trim() === "" ||
      (typeof pestRaw !== "string" || (pestRaw !== "yes" && pestRaw !== "no")) ||
      typeof notesRaw !== "string" ||
      notesRaw.trim() === "" ||
      notesRaw.trim().length > 2000 ||
      (typeof outcomeRaw !== "string" ||
        (outcomeRaw !== "RESOLVED" && outcomeRaw !== "REINTERVENTION_REQUIRED"))
    ) {
      setFormError(
        "Enter the observed date, whether the pest was seen, notes (1–2000 characters), and an explicit outcome.",
      );
      return;
    }
    let area: number | null = null;
    if (typeof areaRaw === "string" && areaRaw.trim() !== "") {
      const parsed = Number(areaRaw.trim());
      if (!Number.isFinite(parsed) || parsed < 0 || parsed > 10000) {
        setFormError("Observed area must be between 0 and 10000 hectares when provided.");
        return;
      }
      area = parsed;
    }
    // Explicit Manila calendar-date check keeps the UTC bug fixed in Phase 3D
    // from returning: never derive today from new Date().toISOString().
    const todayManila = manilaTodayIso();
    if (observedRaw.trim() > todayManila) {
      setFormError("Observed date cannot be in the future (Asia/Manila).");
      return;
    }
    setRecording(true);
    let created: FollowUpDetail;
    try {
      created = await recordFollowUp(
        selectedInterventionId,
        {
          observed_on: observedRaw.trim(),
          pest_observed: pestRaw === "yes",
          ...(area !== null ? { observed_affected_area_hectares: area } : {}),
          assessment_notes: notesRaw.trim(),
          outcome: outcomeRaw as FollowUpOutcome,
        },
        auth.csrfToken,
      );
    } catch (failure) {
      if (failure instanceof FollowUpsRequestError && failure.kind === "unauthenticated") {
        router.replace("/login");
        return;
      }
      setNotice(null);
      setFormError(
        failure instanceof FollowUpsRequestError
          ? failure.message
          : "Follow-up could not be recorded.",
      );
      return;
    } finally {
      setRecording(false);
    }
    setHistory((current) =>
      [...current, created].sort((left, right) => left.id - right.id),
    );
    setDue((current) =>
      current.filter((entry) => entry.intervention_id !== selectedInterventionId),
    );
    setSelectedInterventionId(null);
    setFormError(null);
    setNotice(
      created.outcome === "RESOLVED"
        ? `Follow-up #${created.id} recorded. Case #${created.pest_case?.id ?? ""} is now CLOSED.`
        : `Follow-up #${created.id} recorded. Case #${created.pest_case?.id ?? ""} now requires reintervention.`,
    );
    form.reset();
  }

  if (auth.status !== "authenticated") {
    return <SessionNotice status={auth.status} />;
  }

  const selectedEntry = due.find(
    (entry) => entry.intervention_id === selectedInterventionId,
  );
  const activeRecordingTarget =
    selectedEntry !== undefined && canRecord(selectedEntry) ? selectedEntry : null;

  return (
    <main className="gov-page">
      <PageHeader
        title="Follow-up & Reassessment"
        description="Record human reassessments for completed interventions. Outcomes are explicitly selected and never inferred. Resolved cases close; cases needing more work return for reintervention. History is preserved."
        related={[
          { href: "/pest-cases", label: "Pest Cases" },
          { href: "/interventions", label: "Interventions" },
          { href: "/reports", label: "Reports" },
        ]}
      />
      <WorkflowSteps current="follow-up" />

        <section aria-labelledby="queue-heading" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <div>
              <h2 id="queue-heading" className="gov-record-title">
                Pending follow-up queue
              </h2>
              <p className="gov-record-meta">
                {loading || listError !== null
                  ? "Completed interventions awaiting reassessment."
                  : `${due.length} ${due.length === 1 ? "intervention" : "interventions"} awaiting reassessment. Due dates follow the Asia/Manila calendar.`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void loadAll(outcomeFilter, caseFilter)}
              disabled={loading}
              className="gov-button gov-button-secondary gov-button-compact"
            >
              <Icon name="refresh" size={15} />
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {loading ? (
            <TableSkeleton
              label="Loading follow-up queue"
              columns={["Case / Farm / Farmer", "Agriculture Technician", "Method / Performed", "Due", "Actions"]}
              tableClassName="min-w-[860px]"
            />
          ) : listError ? (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {listError}
            </p>
          ) : due.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No completed interventions are awaiting follow-up.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[860px]">
                <thead>
                  <tr>
                    <th scope="col">Case / Farm / Farmer</th>
                    <th scope="col">Agriculture Technician</th>
                    <th scope="col">Method / Performed</th>
                    <th scope="col">Due</th>
                    <th scope="col" className="gov-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {due.map((entry) => {
                    const localState = dueStateFor(entry.follow_up_due_on);
                    return (
                      <tr
                        key={entry.intervention_id}
                        className={
                          selectedInterventionId === entry.intervention_id
                            ? "gov-row-selected"
                            : undefined
                        }
                      >
                        <td>
                          <span className="gov-cell-primary">
                            {pestLabel(entry.pest_case?.pest_name)}
                          </span>
                          <span className="gov-cell-meta">Case #{entry.pest_case_id}</span>
                          <span className="gov-cell-meta">
                            {entry.pest_case?.farm?.plot_identifier ?? "—"} —{" "}
                            {entry.pest_case?.farm?.farmer?.full_name ?? "—"}
                          </span>
                        </td>
                        <td>
                          {entry.assigned_to?.full_name ?? `#${entry.assigned_to_user_id}`}
                          {entry.assigned_to_user_id === userId && (
                            <span className="gov-cell-meta">Assigned to you</span>
                          )}
                        </td>
                        <td>
                          {entry.method_category}
                          <span className="gov-cell-meta">
                            Performed {formatDisplayDate(entry.performed_on)}
                          </span>
                        </td>
                        <td>
                          <span className={dueBadge(localState)}>{dueBadgeLabel(localState)}</span>
                          {entry.follow_up_due_on !== null && (
                            <span className="gov-cell-meta">
                              {formatDisplayDate(entry.follow_up_due_on)}
                            </span>
                          )}
                        </td>
                        <td className="gov-col-actions">
                          {canRecord(entry) ? (
                            <button
                              type="button"
                              onClick={() => {
                                if (!canRecord(entry)) {
                                  return;
                                }
                                setSelectedInterventionId(entry.intervention_id);
                                setFormError(null);
                              }}
                              className="gov-button gov-button-secondary gov-button-compact"
                            >
                              {selectedInterventionId === entry.intervention_id
                                ? "Selected"
                                : "Record"}
                              <span className="sr-only">
                                {" "}follow-up for case #{entry.pest_case_id}
                              </span>
                            </button>
                          ) : (
                            <span className="gov-cell-meta">
                              Assigned Agriculture Technician only
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section
          ref={recordRef}
          tabIndex={-1}
          aria-labelledby="record-follow-up-heading"
          className={`gov-card gov-record-section${activeRecordingTarget ? " gov-record-section--selected" : ""}`}
        >
          <p className="gov-record-eyebrow">Reassessment</p>
          <h2 id="record-follow-up-heading" className="gov-record-title">
            Record follow-up
          </h2>
          {activeRecordingTarget === null ? (
            <p role="status" className="gov-empty-state">
              Select a pending intervention from the queue to record its reassessment.
            </p>
          ) : (
            <form onSubmit={handleRecord} className="gov-form gov-form-grid">
              <dl className="gov-detail-grid gov-detail-grid--3 gov-field-wide">
                <div>
                  <dt className="gov-detail-label">Case</dt>
                  <dd className="gov-detail-value">
                    #{activeRecordingTarget.pest_case_id} —{" "}
                    {pestLabel(activeRecordingTarget.pest_case?.pest_name)}
                  </dd>
                </div>
                <div>
                  <dt className="gov-detail-label">Farm / farmer</dt>
                  <dd className="gov-detail-value">
                    {activeRecordingTarget.pest_case?.farm?.plot_identifier ?? "—"} —{" "}
                    {activeRecordingTarget.pest_case?.farm?.farmer?.full_name ?? "—"}
                  </dd>
                </div>
                <div>
                  <dt className="gov-detail-label">Intervention</dt>
                  <dd className="gov-detail-value">
                    #{activeRecordingTarget.intervention_id} · {activeRecordingTarget.method_category}
                    <span className="gov-cell-meta">
                      Performed {formatDisplayDate(activeRecordingTarget.performed_on)} · Follow-up due{" "}
                      {formatDisplayDate(activeRecordingTarget.follow_up_due_on)}
                    </span>
                  </dd>
                </div>
              </dl>
              <p className="gov-callout gov-field-wide">
                The outcome you select controls the next case status: <strong>Resolved</strong>{" "}
                closes the case, and <strong>Further intervention required</strong> returns it
                for another intervention cycle.
              </p>
              <RequiredLegend />
              <div className="gov-field">
                <label htmlFor="observed_on" className="gov-label">
                  Observed date <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <input
                  id="observed_on"
                  name="observed_on"
                  type="date"
                  required
                  max={manilaTodayIso()}
                  className="gov-input"
                />
              </div>
              <fieldset className="gov-radio-group">
                <legend className="gov-label">
                  Pest still observed <span className="gov-required" aria-hidden="true">*</span>
                </legend>
                <div className="gov-choice-group">
                  <label className="gov-choice">
                    <input type="radio" name="pest_observed" value="yes" required />
                    Yes
                  </label>
                  <label className="gov-choice">
                    <input type="radio" name="pest_observed" value="no" required />
                    No
                  </label>
                </div>
              </fieldset>
              <div className="gov-field">
                <label htmlFor="observed_affected_area_hectares" className="gov-label">
                  Observed affected area (hectares, optional)
                </label>
                <input
                  id="observed_affected_area_hectares"
                  name="observed_affected_area_hectares"
                  type="number"
                  min={0}
                  max={10000}
                  step={0.01}
                  placeholder="e.g. 0.50"
                  className="gov-input"
                />
              </div>
              <fieldset className="gov-radio-group gov-field-wide">
                <legend className="gov-label">Outcome <span className="gov-required" aria-hidden="true">*</span></legend>
                <div className="gov-choice-group gov-choice-group--cards">
                  <label className="gov-choice gov-choice-card gov-choice--resolve">
                    <input type="radio" name="outcome" value="RESOLVED" required />
                    <span className="gov-choice-body">
                      <span className="gov-choice-title">
                        <Icon name="check-circle" size={16} />
                        Resolved / No further intervention required
                      </span>
                      <span className="gov-choice-detail">The case will be closed.</span>
                    </span>
                  </label>
                  <label className="gov-choice gov-choice-card gov-choice--reintervene">
                    <input type="radio" name="outcome" value="REINTERVENTION_REQUIRED" required />
                    <span className="gov-choice-body">
                      <span className="gov-choice-title">
                        <Icon name="alert-triangle" size={16} />
                        Further intervention required
                      </span>
                      <span className="gov-choice-detail">
                        The case returns for another intervention cycle.
                      </span>
                    </span>
                  </label>
                </div>
              </fieldset>
              <div className="gov-field gov-field-wide">
                <label htmlFor="assessment_notes" className="gov-label">
                  Assessment notes <span className="gov-required" aria-hidden="true">*</span>
                </label>
                <textarea
                  id="assessment_notes"
                  name="assessment_notes"
                  rows={3}
                  maxLength={2000}
                  required
                  placeholder="e.g. No fresh boring observed on east rows; canopy recovering"
                  className="gov-textarea"
                />
              </div>
              <div className="gov-form-actions">
                <button
                  type="submit"
                  disabled={recording}
                  className="gov-button gov-button-primary"
                >
                  {recording ? "Recording..." : "Record follow-up"}
                </button>
              </div>
            </form>
          )}
          {formError && (
            <p role="alert" className="gov-alert gov-alert-error mt-4">
              {formError}
            </p>
          )}
          {notice && (
            <p role="status" className="gov-alert gov-alert-success mt-4">
              {workflowMessage(notice)}
            </p>
          )}
        </section>

        <section aria-labelledby="history-heading" className="gov-card gov-record-section">
          <div className="gov-record-toolbar">
            <div>
              <h2 id="history-heading" className="gov-record-title">
                Follow-up history
              </h2>
              <p className="gov-record-meta">Recorded reassessments are read-only.</p>
            </div>
            <div className="gov-record-controls">
              <label htmlFor="follow_case_filter" className="gov-label">
                Case
              </label>
              <input
                id="follow_case_filter"
                value={caseFilter === "all" ? "" : caseFilter}
                onChange={(event) => {
                  const next = event.target.value.trim() === "" ? "all" : event.target.value.trim();
                  setCaseFilter(next);
                }}
                placeholder="All"
                inputMode="numeric"
                className="gov-input gov-input-narrow"
              />
              <label htmlFor="follow_outcome_filter" className="gov-label">
                Outcome
              </label>
              <select
                id="follow_outcome_filter"
                value={outcomeFilter}
                onChange={(event) => {
                  const next = event.target.value;
                  setOutcomeFilter(next);
                  void loadAll(next, caseFilter);
                }}
                className="gov-select"
              >
                <option value="all">All outcomes</option>
                <option value="RESOLVED">{workflowLabel("RESOLVED")}</option>
                <option value="REINTERVENTION_REQUIRED">{workflowLabel("REINTERVENTION_REQUIRED")}</option>
              </select>
              <button
                type="button"
                onClick={() => void loadAll(outcomeFilter, caseFilter)}
                disabled={loading}
                className="gov-button gov-button-secondary gov-button-compact"
              >
                <Icon name="refresh" size={15} />
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          </div>
          {loading ? (
            <TableSkeleton
              label="Loading follow-up history"
              columns={["Follow-up", "Observation", "Outcome / Case", "Actions"]}
              tableClassName="min-w-[860px]"
            />
          ) : history.length === 0 ? (
            <p role="status" className="gov-empty-state">
              No recorded reassessments found.
            </p>
          ) : (
            <div className="gov-table-wrap mt-4">
              <table className="gov-table min-w-[860px]">
                <thead>
                  <tr>
                    <th scope="col">Follow-up</th>
                    <th scope="col">Observation</th>
                    <th scope="col">Outcome / Case</th>
                    <th scope="col" className="gov-col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((entry) => (
                    <tr
                      key={entry.id}
                      className={selectedFollowUpId === entry.id ? "gov-row-selected" : undefined}
                    >
                      <td>
                        #{entry.id} — {cycleLabel(history, entry)}
                        <span className="gov-cell-meta">
                          Recorded {formatRecordDate(entry.created_at ?? null)} by{" "}
                          {entry.recorded_by?.full_name ?? `#${entry.recorded_by_user_id}`}
                        </span>
                        <span className="gov-cell-note">
                          {entry.assessment_notes}
                        </span>
                      </td>
                      <td>
                        {entry.pest_observed ? "Pest seen" : "No pest seen"}
                        <span className="gov-cell-meta">
                          Observed {formatDisplayDate(entry.observed_on)}
                        </span>
                        <span className="gov-cell-meta">
                          Area{" "}
                          {entry.observed_affected_area_hectares === null
                            ? "—"
                            : `${entry.observed_affected_area_hectares.toFixed(2)} ha`}
                        </span>
                      </td>
                      <td>
                        <span className="gov-badge-pair">
                          <span className="gov-badge-group">
                            <span className="gov-badge-pair-label">Outcome</span>
                            <span className={outcomeBadge(entry.outcome)}>
                              {workflowLabel(entry.outcome)}
                            </span>
                          </span>
                          <span className="gov-badge-group">
                            <span className="gov-badge-pair-label">Case</span>
                            <span className={caseBadge(entry.pest_case?.status ?? "")}>
                              {workflowLabel(entry.pest_case?.status ?? "—")}
                            </span>
                          </span>
                        </span>
                      </td>
                      <td className="gov-col-actions">
                        <button
                          type="button"
                          onClick={() => void openDetail(entry.id)}
                          className="gov-button gov-button-secondary gov-button-compact"
                        >
                          {selectedFollowUpId === entry.id ? "Selected" : "View"}
                          <span className="sr-only"> follow-up #{entry.id}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {selectedFollowUpId !== null && (
          <section
            ref={detailRef}
            tabIndex={-1}
            aria-label="Follow-up detail"
            className="gov-card gov-record-section gov-record-section--selected"
          >
            {loadingDetail ? (
              <DetailSkeleton label="Loading follow-up details" fields={6} />
            ) : detailError ? (
              <p role="alert" className="gov-alert gov-alert-error">
                {detailError}
              </p>
            ) : detail ? (
              <div>
                <div className="gov-record-toolbar">
                  <div>
                    <p className="gov-record-eyebrow">
                      Follow-up #{detail.id}
                      {detail.pest_case ? ` · Case #${detail.pest_case.id}` : ""}
                    </p>
                    <h2 className="gov-record-title">{pestLabel(detail.pest_case?.pest_name)}</h2>
                  </div>
                  <span className="gov-table-actions">
                    <span className="gov-badge-group">
                      <span className="gov-badge-pair-label">Outcome</span>
                      <span className={outcomeBadge(detail.outcome)}>
                        {workflowLabel(detail.outcome)}
                      </span>
                    </span>
                    {detail.pest_case && (
                      <Link
                        href={`/pest-cases/${detail.pest_case.id}`}
                        className="gov-button gov-button-secondary gov-button-compact"
                      >
                        <Icon name="history" size={15} />
                        Open case record
                      </Link>
                    )}
                  </span>
                </div>
                <dl className="gov-detail-grid">
                  <div>
                    <dt className="gov-detail-label">Intervention cycle</dt>
                    <dd className="gov-detail-value">{cycleLabel(history, detail)}</dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Case status</dt>
                    <dd className="gov-detail-value">
                      <span className={caseBadge(detail.pest_case?.status ?? "")}>
                        {workflowLabel(detail.pest_case?.status ?? "—")}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Observation</dt>
                    <dd className="gov-detail-value">
                      {detail.pest_observed ? "Pest observed" : "No pest observed"} on{" "}
                      {formatDisplayDate(detail.observed_on)}
                    </dd>
                  </div>
                  <div>
                    <dt className="gov-detail-label">Recorded by</dt>
                    <dd className="gov-detail-value">
                      {detail.recorded_by?.full_name ?? `#${detail.recorded_by_user_id}`} on{" "}
                      {formatRecordDate(detail.created_at ?? null)}
                    </dd>
                  </div>
                  <div className="gov-detail-wide">
                    <dt className="gov-detail-label">Assessment notes</dt>
                    <dd className="gov-detail-value">{detail.assessment_notes}</dd>
                  </div>
                </dl>
                <p role="status" className="gov-callout mt-4">
                  Recorded reassessments are read-only history and cannot be edited or
                  deleted in this phase.
                </p>
              </div>
            ) : null}
          </section>
        )}
    </main>
  );
}
