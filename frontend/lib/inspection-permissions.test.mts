import assert from "node:assert/strict";
import test from "node:test";

import {
  canManageInspectionSchedule,
  canRecordInspection,
  isInspectionPending,
  type InspectionRecordability,
} from "./inspection-permissions.ts";

const ASSIGNED_TECH_ID = 82;
const OTHER_TECH_ID = 99;
const ADMIN_ID = 2;

function pendingInspection(
  overrides: Partial<InspectionRecordability> = {},
): InspectionRecordability {
  return {
    inspected_on: null,
    findings: null,
    pest_confirmed: null,
    completed_at: null,
    assigned_to_user_id: ASSIGNED_TECH_ID,
    pest_case: { status: "INSPECTION_SCHEDULED" },
    ...overrides,
  };
}

test("assigned Technician can record a pending inspection", () => {
  const item = pendingInspection();
  assert.equal(isInspectionPending(item), true);
  assert.equal(canRecordInspection("TECHNICIAN", ASSIGNED_TECH_ID, item), true);
});

test("Admin can record a pending inspection", () => {
  const item = pendingInspection();
  assert.equal(canRecordInspection("ADMIN", ADMIN_ID, item), true);
});

test("unassigned Technician cannot record another Technician's inspection", () => {
  const item = pendingInspection();
  assert.equal(canRecordInspection("TECHNICIAN", OTHER_TECH_ID, item), false);
});

test("completed or non-recordable inspections never expose the form", () => {
  const completed = pendingInspection({
    inspected_on: "2026-11-11",
    findings: "Bored stalks",
    pest_confirmed: true,
    completed_at: "2026-11-11T01:14:00+08:00",
    pest_case: { status: "FIELD_VALIDATED" },
  });
  assert.equal(isInspectionPending(completed), false);
  assert.equal(canRecordInspection("ADMIN", ADMIN_ID, completed), false);
  assert.equal(
    canRecordInspection("TECHNICIAN", ASSIGNED_TECH_ID, completed),
    false,
  );
});

test("a case outside INSPECTION_SCHEDULED is not recordable", () => {
  for (const status of ["REPORTED", "FOR_INSPECTION", "NOT_CONFIRMED"]) {
    const item = pendingInspection({ pest_case: { status } });
    assert.equal(isInspectionPending(item), false);
    assert.equal(canRecordInspection("ADMIN", ADMIN_ID, item), false);
    assert.equal(
      canRecordInspection("TECHNICIAN", ASSIGNED_TECH_ID, item),
      false,
    );
  }
});

test("scheduling and reassignment remain Admin-only", () => {
  assert.equal(canManageInspectionSchedule("ADMIN"), true);
  assert.equal(canManageInspectionSchedule("TECHNICIAN"), false);
  assert.equal(canManageInspectionSchedule(null), false);
});

test("unknown or missing actors cannot record", () => {
  const item = pendingInspection();
  assert.equal(canRecordInspection(null, null, item), false);
  assert.equal(canRecordInspection("VIEWER", ASSIGNED_TECH_ID, item), false);
});
