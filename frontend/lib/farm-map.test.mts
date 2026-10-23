import assert from "node:assert/strict";
import test from "node:test";

import {
  farmMatchesFilter,
  farmsForMap,
  formatArea,
  markerPresentation,
  type FarmMapFarm,
  type FarmMarkerState,
} from "./farm-map.ts";

function farm(overrides: Partial<FarmMapFarm> = {}): FarmMapFarm {
  return {
    id: 1,
    plot_identifier: "Plot A",
    farmer: { id: 1, full_name: "Farmer A" },
    barangay: "Tangculogan",
    area_hectares: 3,
    location: { latitude: 9.591111, longitude: 123.122778 },
    marker_state: "REGISTERED_NO_CASE",
    has_active_case: false,
    needs_attention: false,
    case: null,
    ...overrides,
  };
}

test("marker states map to the required semantic color groups", () => {
  const expected: Record<FarmMarkerState, string> = {
    REGISTERED_NO_CASE: "#64748b",
    REPORTED: "#2563a6",
    FOR_INSPECTION: "#2563a6",
    INSPECTION_SCHEDULED: "#2563a6",
    FIELD_VALIDATED: "#b42318",
    UNDER_INTERVENTION: "#c45d05",
    FOLLOW_UP_DUE: "#c45d05",
    REINTERVENTION_REQUIRED: "#7f1d1d",
    NOT_CONFIRMED: "#8a929a",
    CLOSED: "#2f6f44",
  };
  for (const [state, color] of Object.entries(expected)) {
    assert.equal(markerPresentation(state as FarmMarkerState).color, color);
  }
});

test("registered farms without cases retain an explicit gray state", () => {
  const presentation = markerPresentation("REGISTERED_NO_CASE");
  assert.equal(presentation.label, "Registered — no case");
  assert.equal(presentation.legendLabel, "Registered / no case");
});

test("All Farms filter accepts every farm", () => {
  assert.equal(farmMatchesFilter(farm(), "ALL"), true);
  assert.equal(farmMatchesFilter(farm({ marker_state: "CLOSED" }), "ALL"), true);
});

test("Active Cases filter uses the backend has_active_case flag", () => {
  assert.equal(farmMatchesFilter(farm({ has_active_case: true }), "ACTIVE"), true);
  assert.equal(
    farmMatchesFilter(farm({ marker_state: "REPORTED", has_active_case: false }), "ACTIVE"),
    false,
  );
});

test("Needs Attention filter relies only on the backend needs_attention flag", () => {
  assert.equal(
    farmMatchesFilter(
      farm({ marker_state: "REGISTERED_NO_CASE", needs_attention: true }),
      "NEEDS_ATTENTION",
    ),
    true,
  );
  assert.equal(
    farmMatchesFilter(
      farm({ marker_state: "REINTERVENTION_REQUIRED", needs_attention: false }),
      "NEEDS_ATTENTION",
    ),
    false,
  );
});

test("Closed / Terminal filter includes only closed and not-confirmed marker states", () => {
  assert.equal(farmMatchesFilter(farm({ marker_state: "CLOSED" }), "TERMINAL"), true);
  assert.equal(
    farmMatchesFilter(farm({ marker_state: "NOT_CONFIRMED" }), "TERMINAL"),
    true,
  );
  assert.equal(
    farmMatchesFilter(farm({ marker_state: "FIELD_VALIDATED" }), "TERMINAL"),
    false,
  );
});

test("unmapped farms are excluded from every marker collection", () => {
  const mapped = farm({ id: 1 });
  const unmapped = farm({ id: 2, location: null, has_active_case: true });
  assert.deepEqual(farmsForMap([mapped, unmapped], "ALL").map((item) => item.id), [1]);
  assert.deepEqual(farmsForMap([mapped, unmapped], "ACTIVE"), []);
});

test("area formatting never displays null or non-finite values", () => {
  assert.equal(formatArea(null), "Not available");
  assert.equal(formatArea(Number.NaN), "Not available");
  assert.equal(formatArea(1.2), "1.20 ha");
});
