import assert from "node:assert/strict";
import test from "node:test";

import {
  NO_OBSERVATION,
  initialReportView,
  type InitialReportCaseRecord,
} from "./inspection-initial-report.ts";
import {
  canManageInspectionSchedule,
  canRecordInspection,
  isInspectionPending,
} from "./inspection-permissions.ts";
import { PENDING_IDENTIFICATION } from "./presentation.ts";

const CASE_ID = 148;
const ASSIGNED_TECH_ID = 82;

const PHOTOS: InitialReportCaseRecord["evidence_photos"] = [
  {
    id: 1,
    original_filename: "stalk-damage.jpg",
    content_type: "image/jpeg",
    byte_size: 1024,
    uploaded_at: "2026-11-10T08:00:00+08:00",
  },
  {
    id: 2,
    original_filename: "leaf-holes.png",
    content_type: "image/png",
    byte_size: 2048,
    uploaded_at: "2026-11-10T08:01:00+08:00",
  },
];

function inspection(overrides: Record<string, unknown> = {}) {
  return {
    pest_case_id: CASE_ID,
    inspected_on: null,
    findings: null,
    pest_confirmed: null,
    confirmed_pest_name: null,
    validated_area_hectares: null,
    completed_at: null,
    assigned_to_user_id: ASSIGNED_TECH_ID,
    pest_case: {
      pest_name: null as string | null,
      reported_area_hectares: 0.5,
      status: "INSPECTION_SCHEDULED",
    },
    ...overrides,
  };
}

function caseRecord(
  overrides: Partial<InitialReportCaseRecord> = {},
): InitialReportCaseRecord {
  return {
    id: CASE_ID,
    symptoms: "Leaves drying, holes in stalks near the base",
    evidence_photos: PHOTOS,
    ...overrides,
  };
}

test("initial suspected pest displays as reported", () => {
  const item = inspection({
    pest_case: { pest_name: "Stem Borer", reported_area_hectares: 0.5, status: "INSPECTION_SCHEDULED" },
  });
  assert.equal(initialReportView(item, caseRecord()).suspectedPest, "Stem Borer");
});

test("null suspected pest displays Pending Identification", () => {
  const view = initialReportView(inspection(), caseRecord());
  assert.equal(view.suspectedPest, PENDING_IDENTIFICATION);
  assert.equal(view.reportedArea, "0.50 ha");
});

test("farmer observation appears in the inspection's initial report", () => {
  const view = initialReportView(inspection(), caseRecord());
  assert.equal(view.observation, "Leaves drying, holes in stalks near the base");
  const blank = initialReportView(inspection(), caseRecord({ symptoms: "  " }));
  assert.equal(blank.observation, NO_OBSERVATION);
});

test("evidence gallery data is present when the case has photos", () => {
  const view = initialReportView(inspection(), caseRecord());
  assert.equal(view.caseId, CASE_ID);
  assert.deepEqual(
    view.photos?.map((photo) => photo.id),
    [1, 2],
  );
});

test("case record from another case is never shown (stale or mismatched fetch)", () => {
  const view = initialReportView(inspection(), caseRecord({ id: 999 }));
  assert.equal(view.observation, null);
  assert.equal(view.photos, null);
  const unloaded = initialReportView(inspection(), null);
  assert.equal(unloaded.photos, null);
});

test("field validation stays separate and never overwrites the initial report", () => {
  const completed = inspection({
    inspected_on: "2026-11-11",
    findings: "Bored stalks confirmed",
    pest_confirmed: true,
    confirmed_pest_name: "Stem Borer",
    validated_area_hectares: 0.45,
    completed_at: "2026-11-11T09:00:00+08:00",
    pest_case: { pest_name: null, reported_area_hectares: 0.5, status: "FIELD_VALIDATED" },
  });
  const view = initialReportView(completed, caseRecord());
  assert.equal(view.suspectedPest, PENDING_IDENTIFICATION);
  assert.equal(view.reportedArea, "0.50 ha");
  assert.equal(completed.confirmed_pest_name, "Stem Borer");
  assert.equal(completed.validated_area_hectares, 0.45);
  assert.ok(!("confirmedPest" in view));
  assert.ok(!Object.values(view).includes("Stem Borer"));
});

test("assigned Technician sees evidence and can record, without Admin scheduling", () => {
  const item = inspection();
  const view = initialReportView(item, caseRecord());
  assert.equal(view.photos?.length, 2);
  assert.equal(canRecordInspection("TECHNICIAN", ASSIGNED_TECH_ID, item), true);
  assert.equal(canManageInspectionSchedule("TECHNICIAN"), false);
});

test("completed inspection keeps initial report visible but no editable form", () => {
  const completed = inspection({
    inspected_on: "2026-11-11",
    findings: "Bored stalks confirmed",
    pest_confirmed: true,
    confirmed_pest_name: "Stem Borer",
    validated_area_hectares: 0.45,
    completed_at: "2026-11-11T09:00:00+08:00",
    pest_case: { pest_name: null, reported_area_hectares: 0.5, status: "FIELD_VALIDATED" },
  });
  assert.equal(isInspectionPending(completed), false);
  assert.equal(canRecordInspection("TECHNICIAN", ASSIGNED_TECH_ID, completed), false);
  assert.equal(canRecordInspection("ADMIN", 2, completed), false);
  const view = initialReportView(completed, caseRecord());
  assert.equal(view.photos?.length, 2);
  assert.notEqual(view.observation, null);
});
