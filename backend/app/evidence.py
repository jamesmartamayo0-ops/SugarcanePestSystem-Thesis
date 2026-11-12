"""Evidence storage adapter.

LOCAL mode keeps the existing filesystem layout used by the laptop demo and
tests. BLOB mode stores objects in a private Vercel Blob store; Flask still
owns authorization and validates each object before its metadata is recorded.
"""

import re
import uuid
from pathlib import Path
from typing import Any

from flask import current_app

LOCAL = "local"
BLOB = "blob"
STORAGE_MODES = frozenset({LOCAL, BLOB})

MAX_PHOTOS = 3
MAX_BYTES = 5 * 1024 * 1024
CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
_CONTENT_TYPE_BY_EXTENSION = {
    extension: content_type
    for content_type, extension in _EXTENSION_BY_CONTENT_TYPE.items()
}

_LOCAL_NAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")
_BLOB_NAME_PATTERN = re.compile(
    r"^ev/(?P<case_id>[1-9][0-9]*)/(?P<generated>[0-9a-f]{32})\.(?P<extension>jpg|png|webp)$"
)


class EvidenceStorageError(Exception):
    """Base error for evidence storage operations."""


class EvidenceObjectInvalid(EvidenceStorageError):
    """The requested object name is not a safe evidence object name."""


def validate_storage_mode(value: str | None) -> str:
    mode = (value or LOCAL).strip().lower()
    if mode not in STORAGE_MODES:
        raise ValueError("EVIDENCE_STORAGE must be local or blob.")
    return mode


def storage_mode() -> str:
    return current_app.config["EVIDENCE_STORAGE"]


def extension_for_content_type(content_type: str | None) -> str | None:
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type or "")


def content_type_for_extension(extension: str) -> str | None:
    return _CONTENT_TYPE_BY_EXTENSION.get(extension)


def new_local_name(content_type: str) -> str:
    extension = extension_for_content_type(content_type)
    if extension is None:
        raise ValueError("Unsupported evidence content type.")
    return f"{uuid.uuid4().hex}.{extension}"


def new_blob_name(case_id: int, content_type: str) -> str:
    if type(case_id) is not int or not 0 < case_id <= 2_147_483_647:
        raise ValueError("Invalid pest case reference.")
    extension = extension_for_content_type(content_type)
    if extension is None:
        raise ValueError("Unsupported evidence content type.")
    return f"ev/{case_id}/{uuid.uuid4().hex}.{extension}"


def parse_blob_name(stored_name: str, case_id: int | None = None) -> tuple[int, str]:
    if not isinstance(stored_name, str) or len(stored_name) > 64:
        raise EvidenceObjectInvalid("Invalid evidence object name.")
    match = _BLOB_NAME_PATTERN.fullmatch(stored_name)
    if match is None:
        raise EvidenceObjectInvalid("Invalid evidence object name.")
    parsed_case_id = int(match.group("case_id"))
    if parsed_case_id > 2_147_483_647:
        raise EvidenceObjectInvalid("Invalid evidence object name.")
    if case_id is not None and parsed_case_id != case_id:
        raise EvidenceObjectInvalid("Evidence object does not belong to this case.")
    return parsed_case_id, match.group("extension")


def is_safe_blob_name(stored_name: str, case_id: int | None = None) -> bool:
    try:
        parse_blob_name(stored_name, case_id)
    except EvidenceObjectInvalid:
        return False
    return True


def local_directory() -> Path:
    directory = Path(current_app.config["EVIDENCE_UPLOAD_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def local_path(stored_name: str) -> Path:
    if not isinstance(stored_name, str) or not _LOCAL_NAME_PATTERN.fullmatch(stored_name):
        raise EvidenceObjectInvalid("Invalid evidence object name.")
    return local_directory() / stored_name


def write_local(stored_name: str, data: bytes) -> None:
    local_path(stored_name).write_bytes(data)


def delete_local(stored_name: str) -> None:
    try:
        local_path(stored_name).unlink(missing_ok=True)
    except (EvidenceObjectInvalid, OSError):
        current_app.logger.error("Evidence photo cleanup failed.")


def _blob_sdk():
    # Imported lazily so local mode and unit tests never import the cloud SDK.
    from vercel.blob import sync

    return sync


def blob_head(stored_name: str) -> Any:
    return _blob_sdk().head_blob(stored_name)


def blob_get(stored_name: str) -> tuple[bytes, Any]:
    result = _blob_sdk().get_blob(stored_name, access="private")
    return result.body, result.metadata


def blob_delete(stored_name: str) -> None:
    try:
        _blob_sdk().delete_blob(stored_name)
    except Exception:  # Cleanup is best-effort; never mask the original failure.
        current_app.logger.error("Evidence blob cleanup failed.")
