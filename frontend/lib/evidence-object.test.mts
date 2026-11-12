import assert from "node:assert/strict";
import test from "node:test";

import {
  evidenceObjectExtension,
  evidenceObjectKey,
  isEvidenceObjectKeyForCase,
} from "./evidence-object.ts";

const UUID = "0123456789abcdef0123456789abcdef";

test("maps only supported evidence content types", () => {
  assert.equal(evidenceObjectExtension("image/jpeg"), "jpg");
  assert.equal(evidenceObjectExtension("image/png"), "png");
  assert.equal(evidenceObjectExtension("image/webp"), "webp");
  assert.equal(evidenceObjectExtension("image/gif"), null);
  assert.equal(evidenceObjectExtension("__proto__"), null);
  assert.equal(evidenceObjectExtension("constructor"), null);
});

test("builds a safe case-scoped object key", () => {
  assert.equal(
    evidenceObjectKey(12, "image/png", UUID),
    `ev/12/${UUID}.png`,
  );
  assert.equal(
    evidenceObjectKey(12, "image/png", "01234567-89ab-cdef-0123-456789abcdef"),
    `ev/12/${UUID}.png`,
  );
});

test("rejects invalid case ids, types, and UUIDs", () => {
  assert.equal(evidenceObjectKey(0, "image/png", UUID), null);
  assert.equal(evidenceObjectKey(-1, "image/png", UUID), null);
  assert.equal(evidenceObjectKey(1.5, "image/png", UUID), null);
  assert.equal(evidenceObjectKey(1, "image/gif", UUID), null);
  assert.equal(evidenceObjectKey(1, "image/png", "../escape"), null);
  assert.equal(evidenceObjectKey(1, "image/png", "not-a-uuid"), null);
});

test("accepts only keys owned by the requested case", () => {
  const key = `ev/12/${UUID}.jpg`;
  assert.equal(isEvidenceObjectKeyForCase(key, 12), true);
  assert.equal(isEvidenceObjectKeyForCase(key, 13), false);
  assert.equal(isEvidenceObjectKeyForCase(`ev/12/${UUID}.gif`, 12), false);
  assert.equal(isEvidenceObjectKeyForCase(`ev/12/../${UUID}.jpg`, 12), false);
  assert.equal(isEvidenceObjectKeyForCase(null, 12), false);
});
