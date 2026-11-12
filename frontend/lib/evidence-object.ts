const EXTENSION_BY_CONTENT_TYPE: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

const CASE_KEY_PATTERN =
  /^ev\/([1-9][0-9]*)\/[0-9a-f]{32}\.(jpg|png|webp)$/;

export function evidenceObjectExtension(contentType: string): string | null {
  return Object.hasOwn(EXTENSION_BY_CONTENT_TYPE, contentType)
    ? EXTENSION_BY_CONTENT_TYPE[contentType]
    : null;
}

export function evidenceObjectKey(
  caseId: number,
  contentType: string,
  uuid: string,
): string | null {
  if (!Number.isSafeInteger(caseId) || caseId <= 0) {
    return null;
  }
  const extension = evidenceObjectExtension(contentType);
  const normalized = uuid.replaceAll("-", "").toLowerCase();
  if (extension === null || !/^[0-9a-f]{32}$/.test(normalized)) {
    return null;
  }
  return `ev/${caseId}/${normalized}.${extension}`;
}

export function isEvidenceObjectKeyForCase(
  value: unknown,
  caseId: number,
): boolean {
  if (typeof value !== "string") {
    return false;
  }
  const match = CASE_KEY_PATTERN.exec(value);
  return match !== null && Number(match[1]) === caseId;
}
