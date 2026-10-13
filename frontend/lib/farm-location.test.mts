import assert from "node:assert/strict";
import test from "node:test";

import {
  createCoordinatePayload,
  normalizeFarmCoordinates,
  updateCoordinatePayload,
} from "./farm-location.ts";

test("create without a selected location omits the default map center", () => {
  assert.deepEqual(createCoordinatePayload(null), {});
});

test("create with a location sends a complete normalized pair", () => {
  assert.deepEqual(
    createCoordinatePayload({ latitude: 9.59111149, longitude: 123.12277851 }),
    { latitude: 9.591111, longitude: 123.122779 },
  );
});

test("normalization rejects invalid coordinates instead of clamping them", () => {
  assert.throws(() => normalizeFarmCoordinates(90.000001, 123), RangeError);
  assert.throws(() => normalizeFarmCoordinates(9, -180.000001), RangeError);
});

test("unchanged edit omits coordinates so the API preserves them", () => {
  assert.deepEqual(updateCoordinatePayload({ kind: "unchanged" }), {});
});

test("changed edit sends both coordinates", () => {
  const payload = updateCoordinatePayload({
    kind: "selected",
    coordinates: { latitude: 9.5, longitude: 123.1 },
  });
  assert.deepEqual(payload, { latitude: 9.5, longitude: 123.1 });
  assert.equal("latitude" in payload, "longitude" in payload);
});

test("clear edit sends a null pair", () => {
  assert.deepEqual(updateCoordinatePayload({ kind: "cleared" }), {
    latitude: null,
    longitude: null,
  });
});

test("every generated coordinate payload is either empty or paired", () => {
  const payloads = [
    createCoordinatePayload(null),
    createCoordinatePayload({ latitude: 9, longitude: 123 }),
    updateCoordinatePayload({ kind: "unchanged" }),
    updateCoordinatePayload({ kind: "cleared" }),
    updateCoordinatePayload({
      kind: "selected",
      coordinates: { latitude: 9, longitude: 123 },
    }),
  ];

  for (const payload of payloads) {
    assert.equal("latitude" in payload, "longitude" in payload);
  }
});
