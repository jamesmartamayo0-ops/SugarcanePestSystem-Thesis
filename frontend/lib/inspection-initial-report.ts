import { pestLabel } from "./presentation.ts";
import type { EvidencePhoto } from "./pest-cases.ts";

export type InitialReportSource = {
  pest_case_id: number;
  pest_case: {
    pest_name: string | null;
    reported_area_hectares: number;
  };
};

// The Pest Case remains the owner of the initial report; the Inspection only
// displays it. Fetched through the scoped inspection initial-report endpoint,
// because Pest Case Records are Administrator-only.
export type InitialReportCaseRecord = {
  id: number;
  symptoms: string | null;
  evidence_photos: EvidencePhoto[];
};

export type InitialReportView = {
  caseId: number;
  suspectedPest: string;
  reportedArea: string;
  // null while the case record is unavailable (loading, failed, or stale).
  observation: string | null;
  photos: EvidencePhoto[] | null;
};

export const NO_OBSERVATION = "No farmer observation recorded.";

// Read-only presentation of the initial report. It never reads field-validation
// values, so confirmed findings cannot replace what was originally reported.
export function initialReportView(
  inspection: InitialReportSource,
  caseRecord: InitialReportCaseRecord | null,
): InitialReportView {
  const record =
    caseRecord !== null && caseRecord.id === inspection.pest_case_id
      ? caseRecord
      : null;
  const symptoms = record?.symptoms?.trim() ?? "";
  return {
    caseId: inspection.pest_case_id,
    suspectedPest: pestLabel(inspection.pest_case.pest_name),
    reportedArea: `${inspection.pest_case.reported_area_hectares.toFixed(2)} ha`,
    observation: record === null ? null : symptoms !== "" ? symptoms : NO_OBSERVATION,
    photos: record === null ? null : record.evidence_photos,
  };
}
