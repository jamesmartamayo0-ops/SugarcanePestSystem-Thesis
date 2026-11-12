from datetime import date
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import joinedload

from app import evidence
from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import (
    Farm,
    Farmer,
    FollowUp,
    Inspection,
    Intervention,
    PestCase,
    PestCaseEvidencePhoto,
    PestCaseStatus,
    User,
    UserRole,
    normalize_observed_on,
    normalize_pest_name,
    normalize_reported_area,
    normalize_scheduled_for,
    validate_scheduled_for,
    normalize_symptoms,
)
from app.models.intervention import (
    normalize_follow_up_due_on,
    normalize_method_category,
    normalize_method_description,
)
from app.models.intervention import (
    normalize_scheduled_for as normalize_intervention_scheduled_for,
)
from app.scoping import (
    apply_case_scope,
    apply_follow_up_scope,
    apply_inspection_scope,
    apply_intervention_scope,
    can_view_farm,
)

pest_cases_bp = Blueprint("pest_cases", __name__, url_prefix="/api/v1/pest-cases")

# Transaction-scoped advisory lock serializing REPORTED -> FOR_INSPECTION
# transitions so two concurrent submissions cannot race the status check.
# The key mixes a fixed base with the case id; it is distinct from the admin
# status lock (75240202) and the CLI bootstrap lock (75240201).
PEST_CASE_TRANSITION_LOCK_BASE = 75240300

_CREATE_REQUIRED = frozenset({"farm_id", "reported_area_hectares"})
_CREATE_ALLOWED = frozenset(
    {"farm_id", "pest_name", "symptoms", "observed_on", "reported_area_hectares"}
)
_UPDATE_ALLOWED = frozenset(
    {"farm_id", "pest_name", "symptoms", "observed_on", "reported_area_hectares"}
)
_ALLOWED_STATUSES = frozenset({status.value for status in PestCaseStatus})
_MAX_INPUT_LENGTHS = {"pest_name": 500, "symptoms": 5000}
_EVIDENCE_MAX_PHOTOS = 3
_EVIDENCE_MAX_BYTES = 5 * 1024 * 1024
_EVIDENCE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def _iso(value) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return None


def _farmer_reference(farmer) -> dict:
    return {"id": farmer.id, "full_name": farmer.full_name, "barangay": farmer.barangay}


def _farm_reference(farm: Farm) -> dict:
    return {
        "id": farm.id,
        "plot_identifier": farm.plot_identifier,
        "barangay": farm.barangay,
        "area_hectares": float(farm.area_hectares),
        "farmer": _farmer_reference(farm.farmer),
    }


def _reporter_reference(user) -> dict:
    return {"id": user.id, "username": user.username, "full_name": user.full_name}


def _pest_case_summary(case: PestCase) -> dict:
    return {
        "id": case.id,
        "farm_id": case.farm_id,
        "pest_name": case.pest_name,
        "reported_area_hectares": float(case.reported_area_hectares),
        "status": case.status,
        "observed_on": _iso(case.observed_on),
        "reported_at": _iso(case.reported_at),
    }


def _evidence_photo_payload(photo: PestCaseEvidencePhoto) -> dict:
    return {
        "id": photo.id,
        "original_filename": photo.original_filename,
        "content_type": photo.content_type,
        "byte_size": photo.byte_size,
        "uploaded_at": _iso(photo.uploaded_at),
    }


def list_case_evidence_photos(case_id: int):
    return db.session.scalars(
        select(PestCaseEvidencePhoto)
        .where(PestCaseEvidencePhoto.pest_case_id == case_id)
        .order_by(PestCaseEvidencePhoto.id)
    ).all()


def _pest_case_detail(case: PestCase) -> dict:
    summary = _pest_case_summary(case)
    inspection = get_inspection_by_case_id(case.id)
    photos = list_case_evidence_photos(case.id)
    summary.update(
        {
            "symptoms": case.symptoms,
            "confirmed_pest_name": (
                inspection.confirmed_pest_name
                if inspection is not None and inspection.pest_confirmed
                else None
            ),
            "evidence_photos": [_evidence_photo_payload(photo) for photo in photos],
            "farm": _farm_reference(case.farm),
            "reporter": _reporter_reference(case.reporter),
            "updated_at": _iso(case.updated_at),
        }
    )
    return summary


def list_all_pest_cases(
    farm_id: int | None = None,
    status: str | None = None,
    farmer_id: int | None = None,
    search: str | None = None,
    reported_from: date | None = None,
    reported_to: date | None = None,
    user=None,
):
    statement = apply_case_scope(select(PestCase).order_by(PestCase.id), user)
    if farm_id is not None:
        statement = statement.where(PestCase.farm_id == farm_id)
    if status is not None:
        statement = statement.where(PestCase.status == status)
        if status == PestCaseStatus.FOR_INSPECTION.value:
            statement = statement.where(
                ~select(Inspection.id)
                .where(Inspection.pest_case_id == PestCase.id)
                .exists()
            )
    if farmer_id is not None or search is not None:
        statement = statement.join(Farm, Farm.id == PestCase.farm_id).join(
            Farmer, Farmer.id == Farm.farmer_id
        )
    elif reported_from is not None or reported_to is not None:
        pass
    if farmer_id is not None:
        statement = statement.where(Farmer.id == farmer_id)
    if search is not None:
        like = f"%{search}%"
        conditions = [
            PestCase.pest_name.ilike(like),
            PestCase.symptoms.ilike(like),
            Farmer.full_name.ilike(like),
            Farm.plot_identifier.ilike(like),
            Farm.barangay.ilike(like),
            Farmer.barangay.ilike(like),
        ]
        if search.isdigit():
            try:
                candidate = int(search)
                if 0 < candidate <= 2_147_483_647:
                    conditions.append(PestCase.id == candidate)
            except (TypeError, ValueError):
                pass
        statement = statement.where(or_(*conditions))
    if reported_from is not None:
        statement = statement.where(func.date(PestCase.reported_at) >= reported_from)
    if reported_to is not None:
        statement = statement.where(func.date(PestCase.reported_at) <= reported_to)
    statement = statement.options(
        joinedload(PestCase.farm).joinedload(Farm.farmer),
        joinedload(PestCase.reporter),
    )
    return db.session.scalars(statement).all()


def get_pest_case_by_id(case_id: int, user=None):
    return db.session.scalar(
        apply_case_scope(select(PestCase).where(PestCase.id == case_id), user)
    )


def get_pest_case_for_update(case_id: int, user=None):
    statement = apply_case_scope(
        select(PestCase).where(PestCase.id == case_id), user
    )
    return db.session.scalar(
        statement.with_for_update().execution_options(populate_existing=True)
    )


def get_farm_by_id(farm_id: int):
    return db.session.get(Farm, farm_id)


def get_user_by_id(user_id: int):
    return db.session.get(User, user_id)


def acquire_pest_case_transition_lock(case_id: int) -> None:
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": PEST_CASE_TRANSITION_LOCK_BASE + case_id},
    )


def persist_new_pest_case(case: PestCase) -> dict:
    db.session.add(case)
    db.session.flush()
    detail = _pest_case_detail(case)
    db.session.commit()
    return detail


def commit_pest_case_changes() -> None:
    db.session.commit()


def _precheck_payload(payload: dict) -> str | None:
    if "farm_id" in payload:
        farm_id = payload["farm_id"]
        if type(farm_id) is not int or not 0 < farm_id <= 2_147_483_647:
            return "Invalid pest case data."
    for field, limit in _MAX_INPUT_LENGTHS.items():
        if field not in payload:
            continue
        value = payload[field]
        if value in (None, ""):
            continue
        if not isinstance(value, str) or len(value) > limit:
            return "Invalid pest case data."
    if "observed_on" in payload:
        observed = payload["observed_on"]
        if observed in (None, ""):
            pass
        elif not isinstance(observed, str) or len(observed) > 32:
            return "Invalid pest case data."
    if "reported_area_hectares" in payload:
        area = payload["reported_area_hectares"]
        if isinstance(area, bool):
            return "Invalid pest case data."
        if isinstance(area, (int, float)):
            if not isinstance(area, int) and (area != area or area in (float("inf"), float("-inf"))):
                return "Invalid pest case data."
        elif isinstance(area, str):
            if not area.strip() or len(area) > 32:
                return "Invalid pest case data."
        else:
            return "Invalid pest case data."
    return None


def _parse_iso_date(value: str | None, field: str):
    if value is None or value == "":
        return None, None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 32:
        return None, "Invalid pest case filter."
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError:
        return None, "Invalid pest case filter."
    return parsed, None


def _parse_filter_args():
    raw_farm_id = request.args.get("farm_id")
    raw_farmer_id = request.args.get("farmer_id")
    raw_status = request.args.get("status")
    raw_q = request.args.get("q")
    raw_from = request.args.get("reported_from")
    raw_to = request.args.get("reported_to")
    farm_id: int | None = None
    farmer_id: int | None = None
    status: str | None = None
    search: str | None = None
    if raw_farm_id is not None and raw_farm_id != "":
        try:
            farm_id = int(raw_farm_id.strip() if isinstance(raw_farm_id, str) else raw_farm_id)
        except (TypeError, ValueError, AttributeError):
            return None, None, None, None, None, None, "Invalid pest case filter."
        if not 0 < farm_id <= 2_147_483_647:
            return None, None, None, None, None, None, "Invalid pest case filter."
    if raw_farmer_id is not None and raw_farmer_id != "":
        try:
            farmer_id = int(raw_farmer_id.strip() if isinstance(raw_farmer_id, str) else raw_farmer_id)
        except (TypeError, ValueError, AttributeError):
            return None, None, None, None, None, None, "Invalid pest case filter."
        if not 0 < farmer_id <= 2_147_483_647:
            return None, None, None, None, None, None, "Invalid pest case filter."
    if raw_status is not None and raw_status != "":
        cleaned_status = raw_status.strip() if isinstance(raw_status, str) else raw_status
        if cleaned_status not in _ALLOWED_STATUSES:
            return None, None, None, None, None, None, "Invalid pest case filter."
        status = cleaned_status
    if raw_q is not None and raw_q != "":
        if not isinstance(raw_q, str):
            return None, None, None, None, None, None, "Invalid pest case filter."
        cleaned_q = raw_q.strip()
        if cleaned_q == "":
            search = None
        else:
            if len(cleaned_q) > 120:
                return None, None, None, None, None, None, "Invalid pest case filter."
            search = cleaned_q
    reported_from, invalid = _parse_iso_date(raw_from, "reported_from")
    if invalid is not None:
        return None, None, None, None, None, None, invalid
    reported_to, invalid = _parse_iso_date(raw_to, "reported_to")
    if invalid is not None:
        return None, None, None, None, None, None, invalid
    if reported_from is not None and reported_to is not None and reported_from > reported_to:
        return None, None, None, None, None, None, "Invalid pest case filter."
    return farm_id, farmer_id, status, search, reported_from, reported_to, None


@pest_cases_bp.after_request
def _no_store_pest_cases_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@pest_cases_bp.get("")
@pest_cases_bp.get("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_pest_cases():
    farm_id, farmer_id, status, search, reported_from, reported_to, invalid = _parse_filter_args()
    if invalid is not None:
        return auth_error(invalid, 400)
    try:
        cases = list_all_pest_cases(farm_id, status, farmer_id, search, reported_from, reported_to)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case list failed.")
        return auth_error("Pest case service unavailable.", 503)
    return jsonify(
        {
            "data": {"pest_cases": [_pest_case_summary(case) for case in cases]},
            "message": "Pest cases retrieved.",
        }
    )


@pest_cases_bp.get("/<int:case_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_pest_case(case_id: int):
    try:
        case = get_pest_case_by_id(case_id)
        detail = _pest_case_detail(case) if case is not None else None
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)
    return jsonify(
        {"data": {"pest_case": detail}, "message": "Pest case retrieved."}
    )


@pest_cases_bp.post("")
@pest_cases_bp.post("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def create_pest_case():
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid pest case data.", 400)

    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not _CREATE_REQUIRED.issubset(set(payload))
        or not set(payload).issubset(_CREATE_ALLOWED)
    ):
        return auth_error("Invalid pest case data.", 400)

    invalid = _precheck_payload(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        farm = get_farm_by_id(payload["farm_id"])
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case farm lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if farm is None:
        return auth_error("Farm not found.", 404)

    try:
        case = PestCase(
            farm_id=payload["farm_id"],
            pest_name=payload.get("pest_name"),
            symptoms=payload.get("symptoms"),
            observed_on=payload.get("observed_on"),
            reported_area_hectares=payload["reported_area_hectares"],
            status=PestCaseStatus.REPORTED.value,
            reported_by_user_id=g.current_user.id,
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    if case.reported_area_hectares > farm.area_hectares:
        return auth_error(
            "Reported area must not exceed the farm's recorded sugarcane area.", 400
        )

    try:
        detail = persist_new_pest_case(case)
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Pest case creation integrity failure.")
        return auth_error("Pest case service unavailable.", 503)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case creation failed.")
        return auth_error("Pest case service unavailable.", 503)

    response = jsonify({"data": {"pest_case": detail}, "message": "Pest case reported."})
    response.status_code = 201
    return response


@pest_cases_bp.put("/<int:case_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def update_pest_case(case_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid pest case data.", 400)

    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not payload
        or not set(payload).issubset(_UPDATE_ALLOWED)
    ):
        return auth_error("Invalid pest case data.", 400)

    invalid = _precheck_payload(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        # Use the same lock order as submission. The advisory lock serializes
        # the workflow decision, and FOR UPDATE reloads authoritative state
        # before any report fields are changed.
        acquire_pest_case_transition_lock(case_id)
        case = get_pest_case_for_update(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)

    if case.status != PestCaseStatus.REPORTED.value:
        db.session.rollback()
        return auth_error("Only REPORTED pest cases can be edited.", 409)

    target_farm_id = payload.get("farm_id", case.farm_id)
    try:
        if target_farm_id == case.farm_id:
            target_farm = case.farm
        else:
            target_farm = get_farm_by_id(target_farm_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case farm lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if target_farm is None or (
        target_farm_id != case.farm_id and not can_view_farm(g.current_user, target_farm)
    ):
        return auth_error("Farm not found.", 404)

    # Validate every candidate value before mutating the persistent object,
    # so a rejected update leaves the case untouched even without a rollback.
    try:
        new_pest_name = (
            normalize_pest_name(payload["pest_name"])
            if "pest_name" in payload
            else case.pest_name
        )
        new_symptoms = (
            normalize_symptoms(payload["symptoms"])
            if "symptoms" in payload
            else case.symptoms
        )
        new_observed_on = (
            normalize_observed_on(payload["observed_on"])
            if "observed_on" in payload
            else case.observed_on
        )
        new_area = (
            normalize_reported_area(payload["reported_area_hectares"])
            if "reported_area_hectares" in payload
            else case.reported_area_hectares
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    if new_area > target_farm.area_hectares:
        return auth_error(
            "Reported area must not exceed the farm's recorded sugarcane area.", 400
        )

    if target_farm_id != case.farm_id:
        case.farm_id = target_farm_id
        case.farm = target_farm
    case.pest_name = new_pest_name
    case.symptoms = new_symptoms
    case.observed_on = new_observed_on
    case.reported_area_hectares = new_area

    try:
        detail = _pest_case_detail(case)
        commit_pest_case_changes()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case update failed.")
        return auth_error("Pest case service unavailable.", 503)

    return jsonify({"data": {"pest_case": detail}, "message": "Pest case updated."})


def _detect_evidence_type(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def _evidence_directory() -> Path:
    return evidence.local_directory()


def _remove_saved_evidence(files: list[Path]) -> None:
    for path in files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            current_app.logger.error("Evidence photo cleanup failed.")


def persist_evidence_photos(photos: list[PestCaseEvidencePhoto]) -> None:
    db.session.add_all(photos)
    db.session.commit()


def get_case_evidence_photo(case_id: int, photo_id: int):
    return db.session.scalar(
        select(PestCaseEvidencePhoto).where(
            PestCaseEvidencePhoto.id == photo_id,
            PestCaseEvidencePhoto.pest_case_id == case_id,
        )
    )


@pest_cases_bp.post("/<int:case_id>/evidence-photos")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def upload_evidence_photos(case_id: int):
    if evidence.storage_mode() != evidence.LOCAL:
        return auth_error("Direct evidence upload is required.", 409)

    if request.content_length is not None and request.content_length > (
        _EVIDENCE_MAX_BYTES * _EVIDENCE_MAX_PHOTOS
    ):
        return auth_error("Evidence photos must be at most 5 MiB each.", 400)

    uploaded = [item for item in request.files.getlist("photos") if item.filename]
    if not uploaded:
        return auth_error("Select at least one evidence photo.", 400)
    if len(uploaded) > _EVIDENCE_MAX_PHOTOS:
        return auth_error("Upload at most 3 evidence photos per case.", 400)

    try:
        case = get_pest_case_by_id(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence photo case lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)
    if case.status != PestCaseStatus.REPORTED.value:
        return auth_error(
            "Evidence photos can only be added while the case is Reported.", 409
        )

    try:
        acquire_pest_case_transition_lock(case_id)
        existing = list_case_evidence_photos(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence photo count check failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if len(existing) + len(uploaded) > _EVIDENCE_MAX_PHOTOS:
        db.session.rollback()
        return auth_error("Upload at most 3 evidence photos per case.", 400)

    prepared: list[tuple[str, str, str, bytes]] = []
    for item in uploaded:
        data = item.stream.read(_EVIDENCE_MAX_BYTES + 1)
        if len(data) > _EVIDENCE_MAX_BYTES:
            return auth_error("Each evidence photo must be at most 5 MiB.", 400)
        if not data:
            return auth_error("Each evidence photo must not be empty.", 400)
        detected = _detect_evidence_type(data)
        if detected is None or detected[0] not in _EVIDENCE_TYPES:
            return auth_error("Evidence photos must be JPEG, PNG, or WebP.", 400)
        content_type = detected[0]
        original_name = Path(item.filename or "photo").name[:255] or "photo"
        prepared.append(
            (evidence.new_local_name(content_type), original_name, content_type, data)
        )

    saved_paths: list[Path] = []
    try:
        directory = _evidence_directory()
        photos = []
        for stored_name, original_name, content_type, data in prepared:
            path = directory / stored_name
            path.write_bytes(data)
            saved_paths.append(path)
            photos.append(
                PestCaseEvidencePhoto(
                    pest_case_id=case.id,
                    stored_name=stored_name,
                    original_filename=original_name,
                    content_type=content_type,
                    byte_size=len(data),
                    uploaded_by_user_id=g.current_user.id,
                )
            )
        persist_evidence_photos(photos)
    except SQLAlchemyError:
        db.session.rollback()
        _remove_saved_evidence(saved_paths)
        current_app.logger.error("Evidence photo save failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    except OSError:
        db.session.rollback()
        _remove_saved_evidence(saved_paths)
        current_app.logger.error("Evidence photo storage failed.")
        return auth_error("Evidence photo service unavailable.", 503)

    return (
        jsonify(
            {
                "data": {"pest_case": _pest_case_detail(case)},
                "message": "Evidence photos uploaded.",
            }
        ),
        201,
    )


@pest_cases_bp.get("/<int:case_id>/evidence-photos/<int:photo_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_evidence_photo(case_id: int, photo_id: int):
    if evidence.storage_mode() != evidence.LOCAL:
        return auth_error("Direct evidence download is required.", 409)

    try:
        case = get_pest_case_by_id(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence photo case lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if case is None:
        return auth_error("Evidence photo not found.", 404)

    try:
        photo = get_case_evidence_photo(case_id, photo_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence photo lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if photo is None:
        return auth_error("Evidence photo not found.", 404)

    path = evidence.local_path(photo.stored_name)
    if not path.is_file():
        return auth_error("Evidence photo not found.", 404)
    return send_file(
        path,
        mimetype=photo.content_type,
        as_attachment=False,
        download_name=photo.original_filename,
        max_age=0,
    )


@pest_cases_bp.get("/<int:case_id>/evidence-photos/config")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def evidence_photo_config(case_id: int):
    try:
        case = get_pest_case_by_id(case_id)
        photos = list_case_evidence_photos(case_id) if case is not None else []
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence configuration lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)

    return jsonify(
        {
            "data": {
                "storage": evidence.storage_mode(),
                "max_photos": evidence.MAX_PHOTOS,
                "max_bytes": evidence.MAX_BYTES,
                "content_types": list(evidence.CONTENT_TYPES),
                "remaining": max(0, evidence.MAX_PHOTOS - len(photos)),
            },
            "message": "Evidence configuration retrieved.",
        }
    )


@pest_cases_bp.post("/<int:case_id>/evidence-photos/upload-authorize")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def authorize_evidence_upload(case_id: int):
    if evidence.storage_mode() != evidence.BLOB:
        return auth_error("Direct evidence upload is not enabled.", 409)
    if request.content_length is not None and request.content_length > 4096:
        return auth_error("Invalid evidence upload request.", 400)
    if request.data and not request.is_json:
        return auth_error("Invalid evidence upload request.", 400)

    try:
        case = get_pest_case_by_id(case_id)
        photos = list_case_evidence_photos(case_id) if case is not None else []
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence upload authorization lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)
    if case.status != PestCaseStatus.REPORTED.value:
        return auth_error(
            "Evidence photos can only be added while the case is Reported.", 409
        )
    if len(photos) >= evidence.MAX_PHOTOS:
        return auth_error("Upload at most 3 evidence photos per case.", 400)

    return jsonify(
        {
            "data": {
                "prefix": f"ev/{case.id}/",
                "max_bytes": evidence.MAX_BYTES,
                "content_types": list(evidence.CONTENT_TYPES),
                "remaining": evidence.MAX_PHOTOS - len(photos),
            },
            "message": "Evidence upload authorized.",
        }
    )


def _delete_blob_evidence(stored_names: list[str]) -> None:
    for stored_name in stored_names:
        evidence.blob_delete(stored_name)


@pest_cases_bp.post("/<int:case_id>/evidence-photos/finalize")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def finalize_evidence_photos(case_id: int):
    if evidence.storage_mode() != evidence.BLOB:
        return auth_error("Direct evidence upload is not enabled.", 409)
    if not request.is_json or (
        request.content_length is not None and request.content_length > 16384
    ):
        return auth_error("Invalid evidence photo data.", 400)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"photos"}:
        return auth_error("Invalid evidence photo data.", 400)
    uploaded = payload["photos"]
    if not isinstance(uploaded, list) or not 1 <= len(uploaded) <= evidence.MAX_PHOTOS:
        return auth_error("Upload at most 3 evidence photos per case.", 400)

    try:
        case = get_pest_case_by_id(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence finalization case lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)
    if case.status != PestCaseStatus.REPORTED.value:
        return auth_error(
            "Evidence photos can only be added while the case is Reported.", 409
        )

    prepared: list[tuple[str, str, str]] = []
    for item in uploaded:
        if not isinstance(item, dict) or set(item) != {"pathname", "original_filename"}:
            return auth_error("Invalid evidence photo data.", 400)
        pathname = item["pathname"]
        original_filename = item["original_filename"]
        if not isinstance(pathname, str) or not isinstance(original_filename, str):
            return auth_error("Invalid evidence photo data.", 400)
        try:
            _, extension = evidence.parse_blob_name(pathname, case.id)
        except evidence.EvidenceObjectInvalid:
            return auth_error("Invalid evidence photo reference.", 400)
        expected_type = evidence.content_type_for_extension(extension)
        if expected_type is None:
            return auth_error("Invalid evidence photo reference.", 400)
        original_name = Path(original_filename).name[:255] or "photo"
        prepared.append((pathname, original_name, expected_type))

    if len({pathname for pathname, _, _ in prepared}) != len(prepared):
        return auth_error("Invalid evidence photo reference.", 400)

    stored_names = [pathname for pathname, _, _ in prepared]
    try:
        acquire_pest_case_transition_lock(case_id)
        existing = list_case_evidence_photos(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence finalization count check failed.")
        _delete_blob_evidence(stored_names)
        return auth_error("Evidence photo service unavailable.", 503)
    if len(existing) + len(prepared) > evidence.MAX_PHOTOS:
        db.session.rollback()
        _delete_blob_evidence(stored_names)
        return auth_error("Upload at most 3 evidence photos per case.", 400)
    recorded_names = {photo.stored_name for photo in existing}
    if any(stored_name in recorded_names for stored_name in stored_names):
        # Never delete an object that is already referenced by an evidence row.
        db.session.rollback()
        return auth_error("Evidence photo is already recorded.", 409)

    verified: list[tuple[str, str, str, int]] = []
    try:
        for pathname, original_name, expected_type in prepared:
            head = evidence.blob_head(pathname)
            size = getattr(head, "size", None)
            content_type = getattr(head, "content_type", None)
            if type(size) is not int or not 0 < size <= evidence.MAX_BYTES:
                raise evidence.EvidenceObjectInvalid("Invalid evidence photo size.")
            if content_type != expected_type:
                raise evidence.EvidenceObjectInvalid("Invalid evidence photo type.")
            data, _metadata = evidence.blob_get(pathname)
            if not isinstance(data, (bytes, bytearray)) or len(data) != size:
                raise evidence.EvidenceObjectInvalid("Invalid evidence photo content.")
            if len(data) > evidence.MAX_BYTES:
                raise evidence.EvidenceObjectInvalid("Invalid evidence photo size.")
            detected = _detect_evidence_type(bytes(data))
            if detected is None or detected[0] != expected_type:
                raise evidence.EvidenceObjectInvalid("Invalid evidence photo content.")
            verified.append((pathname, original_name, expected_type, size))
    except evidence.EvidenceObjectInvalid as exc:
        current_app.logger.warning("Evidence finalization rejected: %s", exc)
        _delete_blob_evidence(stored_names)
        return auth_error(str(exc), 400)
    except Exception:
        current_app.logger.error("Evidence object verification failed.")
        _delete_blob_evidence(stored_names)
        return auth_error("Evidence photo service unavailable.", 503)

    try:
        photos = [
            PestCaseEvidencePhoto(
                pest_case_id=case.id,
                stored_name=pathname,
                original_filename=original_name,
                content_type=expected_type,
                byte_size=size,
                uploaded_by_user_id=g.current_user.id,
            )
            for pathname, original_name, expected_type, size in verified
        ]
        persist_evidence_photos(photos)
    except SQLAlchemyError:
        db.session.rollback()
        _delete_blob_evidence(stored_names)
        current_app.logger.error("Evidence photo metadata save failed.")
        return auth_error("Evidence photo service unavailable.", 503)

    return (
        jsonify(
            {
                "data": {"pest_case": _pest_case_detail(case)},
                "message": "Evidence photos uploaded.",
            }
        ),
        201,
    )


@pest_cases_bp.get("/<int:case_id>/evidence-photos/<int:photo_id>/authorize-download")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def authorize_evidence_download(case_id: int, photo_id: int):
    try:
        case = get_pest_case_by_id(case_id)
        photo = get_case_evidence_photo(case_id, photo_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Evidence download authorization lookup failed.")
        return auth_error("Evidence photo service unavailable.", 503)
    if case is None or photo is None:
        return auth_error("Evidence photo not found.", 404)

    return jsonify(
        {
            "data": {
                "storage": evidence.storage_mode(),
                "pathname": photo.stored_name,
                "content_type": photo.content_type,
                "original_filename": photo.original_filename,
            },
            "message": "Evidence download authorized.",
        }
    )


@pest_cases_bp.post("/<int:case_id>/submit-for-inspection")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def submit_for_inspection(case_id: int):
    if request.data:
        if not request.is_json:
            return auth_error("Invalid pest case transition.", 400)
        if request.get_json(silent=True) != {}:
            return auth_error("Invalid pest case transition.", 400)

    try:
        acquire_pest_case_transition_lock(case_id)
        case = get_pest_case_for_update(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case transition lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)

    if case.status != PestCaseStatus.REPORTED.value:
        db.session.rollback()
        return auth_error(
            "Pest case has already been submitted for inspection.", 409
        )

    case.status = PestCaseStatus.FOR_INSPECTION.value
    try:
        detail = _pest_case_detail(case)
        commit_pest_case_changes()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case transition failed.")
        return auth_error("Pest case service unavailable.", 503)

    return jsonify(
        {"data": {"pest_case": detail}, "message": "Pest case submitted for inspection."}
    )


_SCHEDULE_INSPECTION_FIELDS = frozenset({"scheduled_for", "assigned_to_user_id"})


def get_inspection_by_case_id(case_id: int):
    return db.session.scalar(
        apply_inspection_scope(
            select(Inspection).where(Inspection.pest_case_id == case_id), None
        ).limit(1)
    )


@pest_cases_bp.post("/<int:case_id>/schedule-inspection")
@login_required
@roles_required("ADMIN")
def schedule_inspection(case_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid inspection data.", 400)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != _SCHEDULE_INSPECTION_FIELDS:
        return auth_error("Invalid inspection data.", 400)
    raw_date = payload.get("scheduled_for")
    raw_assignee = payload.get("assigned_to_user_id")
    if not isinstance(raw_date, str) or not raw_date.strip() or len(raw_date) > 32:
        return auth_error("Invalid inspection data.", 400)
    if type(raw_assignee) is not int or not 0 < raw_assignee <= 2_147_483_647:
        return auth_error("Invalid inspection data.", 400)

    try:
        scheduled_for = validate_scheduled_for(raw_date)
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        # Same lock order as all inspection operations: advisory lock first,
        # then SELECT ... FOR UPDATE with populate_existing, then recheck.
        acquire_pest_case_transition_lock(case_id)
        case = get_pest_case_for_update(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection scheduling lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)

    try:
        existing = get_inspection_by_case_id(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection duplicate check failed.")
        return auth_error("Inspection service unavailable.", 503)
    if existing is not None:
        db.session.rollback()
        return auth_error(
            "This case already has a scheduled inspection. Open the existing inspection "
            "to reschedule the date or change the assigned technician.",
            409,
        )

    if case.status != PestCaseStatus.FOR_INSPECTION.value:
        db.session.rollback()
        return auth_error("Pest case cannot be scheduled for inspection.", 409)

    try:
        technician = get_user_by_id(raw_assignee)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection technician lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if technician is None:
        db.session.rollback()
        return auth_error("Technician not found.", 404)
    if technician.role != UserRole.TECHNICIAN.value or not bool(technician.is_active):
        db.session.rollback()
        return auth_error("Invalid technician assignment.", 400)

    try:
        inspection = Inspection(
            pest_case_id=case.id,
            scheduled_for=scheduled_for,
            assigned_to_user_id=technician.id,
            scheduled_by_user_id=g.current_user.id,
        )
        db.session.add(inspection)
        case.status = PestCaseStatus.INSPECTION_SCHEDULED.value
        db.session.flush()
        inspection.assignee = technician
        inspection.scheduler = g.current_user
        inspection.pest_case = case
        detail = {
            "id": inspection.id,
            "pest_case_id": inspection.pest_case_id,
            "scheduled_for": inspection.scheduled_for.isoformat(),
            "assigned_to_user_id": inspection.assigned_to_user_id,
            "assigned_to": {
                "id": technician.id,
                "username": technician.username,
                "full_name": technician.full_name,
            },
            "scheduled_by_user_id": g.current_user.id,
            "inspected_on": None,
            "findings": None,
            "pest_confirmed": None,
            "confirmed_pest_name": None,
            "validated_area_hectares": None,
            "completed_by_user_id": None,
            "completed_at": None,
            "created_at": _iso(inspection.created_at),
            "updated_at": _iso(inspection.updated_at),
            "pest_case": _pest_case_detail(case),
        }
        commit_pest_case_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Inspection scheduling integrity failure.")
        return auth_error(
            "This case already has a scheduled inspection. Open the existing inspection "
            "to reschedule the date or change the assigned technician.",
            409,
        )
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection scheduling failed.")
        return auth_error("Inspection service unavailable.", 503)

    response = jsonify({"data": {"inspection": detail}, "message": "Inspection scheduled."})
    response.status_code = 201
    return response


_START_INTERVENTION_REQUIRED = frozenset(
    {"method_category", "method_description", "scheduled_for", "assigned_to_user_id"}
)
_START_INTERVENTION_ALLOWED = frozenset(
    {
        "method_category",
        "method_description",
        "scheduled_for",
        "assigned_to_user_id",
        "follow_up_due_on",
    }
)


def get_pending_intervention_by_case_id(case_id: int):
    return db.session.scalar(
        select(Intervention)
        .where(
            Intervention.pest_case_id == case_id,
            Intervention.completed_at.is_(None),
        )
        .limit(1)
    )


def get_latest_completed_intervention_by_case_id(case_id: int):
    return db.session.scalar(
        select(Intervention)
        .where(
            Intervention.pest_case_id == case_id,
            Intervention.completed_at.is_not(None),
        )
        .order_by(Intervention.id.desc())
        .limit(1)
    )


def get_follow_up_by_intervention_id(intervention_id: int):
    return db.session.scalar(
        select(FollowUp).where(FollowUp.intervention_id == intervention_id).limit(1)
    )


@pest_cases_bp.post("/<int:case_id>/start-intervention")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def start_intervention(case_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid intervention data.", 400)
    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not _START_INTERVENTION_REQUIRED.issubset(set(payload))
        or not set(payload).issubset(_START_INTERVENTION_ALLOWED)
    ):
        return auth_error("Invalid intervention data.", 400)
    raw_category = payload.get("method_category")
    raw_description = payload.get("method_description")
    raw_date = payload.get("scheduled_for")
    raw_assignee = payload.get("assigned_to_user_id")
    raw_follow_up = payload.get("follow_up_due_on")
    if not isinstance(raw_category, str) or not raw_category.strip() or len(raw_category) > 32:
        return auth_error("Invalid intervention data.", 400)
    if not isinstance(raw_description, str) or not raw_description.strip() or len(raw_description) > 5000:
        return auth_error("Invalid intervention data.", 400)
    if not isinstance(raw_date, str) or not raw_date.strip() or len(raw_date) > 32:
        return auth_error("Invalid intervention data.", 400)
    if type(raw_assignee) is not int or not 0 < raw_assignee <= 2_147_483_647:
        return auth_error("Invalid intervention data.", 400)
    if raw_follow_up is not None and (
        not isinstance(raw_follow_up, str) or not raw_follow_up.strip() or len(raw_follow_up) > 32
    ):
        return auth_error("Invalid intervention data.", 400)

    try:
        method_category = normalize_method_category(raw_category)
        method_description = normalize_method_description(raw_description)
        scheduled_for = normalize_intervention_scheduled_for(raw_date)
        follow_up_due_on = (
            normalize_follow_up_due_on(raw_follow_up) if raw_follow_up is not None else None
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        # Same lock order as all Phase 3B/3C/3D operations: advisory lock
        # first, then SELECT ... FOR UPDATE with populate_existing, then recheck.
        acquire_pest_case_transition_lock(case_id)
        case = get_pest_case_for_update(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention start lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)

    try:
        existing = get_pending_intervention_by_case_id(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention duplicate check failed.")
        return auth_error("Intervention service unavailable.", 503)
    if existing is not None:
        db.session.rollback()
        return auth_error("Intervention has already been started for this case.", 409)

    if case.status not in (
        PestCaseStatus.FIELD_VALIDATED.value,
        PestCaseStatus.REINTERVENTION_REQUIRED.value,
    ):
        db.session.rollback()
        return auth_error("Intervention cannot be started for this case.", 409)

    if case.status == PestCaseStatus.REINTERVENTION_REQUIRED.value:
        # Repeat intervention: the preceding completed intervention must have
        # a recorded follow-up explicitly requiring reintervention, and no
        # other pending intervention may exist (checked above).
        try:
            preceding = get_latest_completed_intervention_by_case_id(case_id)
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error("Intervention repeat lookup failed.")
            return auth_error("Intervention service unavailable.", 503)
        if preceding is None or preceding.completed_at is None:
            db.session.rollback()
            return auth_error("Intervention cannot be started for this case.", 409)
        try:
            preceding_follow_up = get_follow_up_by_intervention_id(preceding.id)
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error("Intervention repeat lookup failed.")
            return auth_error("Intervention service unavailable.", 503)
        if preceding_follow_up is None:
            db.session.rollback()
            return auth_error("Intervention cannot be started for this case.", 409)
        if preceding_follow_up.outcome != "REINTERVENTION_REQUIRED":
            db.session.rollback()
            return auth_error("Intervention cannot be started for this case.", 409)

    try:
        technician = get_user_by_id(raw_assignee)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention technician lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if technician is None:
        db.session.rollback()
        return auth_error("Technician not found.", 404)
    if technician.role != UserRole.TECHNICIAN.value or not bool(technician.is_active):
        db.session.rollback()
        return auth_error("Invalid technician assignment.", 400)

    try:
        intervention = Intervention(
            pest_case_id=case.id,
            method_category=method_category,
            method_description=method_description,
            scheduled_for=scheduled_for,
            assigned_to_user_id=technician.id,
            created_by_user_id=g.current_user.id,
            follow_up_due_on=follow_up_due_on,
        )
        db.session.add(intervention)
        case.status = PestCaseStatus.UNDER_INTERVENTION.value
        db.session.flush()
        intervention.assignee = technician
        intervention.creator = g.current_user
        intervention.pest_case = case
        detail = {
            "id": intervention.id,
            "pest_case_id": intervention.pest_case_id,
            "method_category": intervention.method_category,
            "method_description": intervention.method_description,
            "scheduled_for": intervention.scheduled_for.isoformat(),
            "assigned_to_user_id": intervention.assigned_to_user_id,
            "assigned_to": {
                "id": technician.id,
                "username": technician.username,
                "full_name": technician.full_name,
            },
            "created_by_user_id": g.current_user.id,
            "performed_on": None,
            "completion_notes": None,
            "follow_up_due_on": intervention.follow_up_due_on.isoformat()
            if intervention.follow_up_due_on is not None
            else None,
            "completed_by_user_id": None,
            "completed_at": None,
            "created_at": intervention.created_at.isoformat()
            if intervention.created_at is not None
            else None,
            "updated_at": intervention.updated_at.isoformat()
            if intervention.updated_at is not None
            else None,
            "pest_case": _pest_case_detail(case),
        }
        commit_pest_case_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Intervention start integrity failure.")
        return auth_error("Intervention has already been started for this case.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention start failed.")
        return auth_error("Intervention service unavailable.", 503)

    response = jsonify({"data": {"intervention": detail}, "message": "Intervention started."})
    response.status_code = 201
    return response


def get_inspections_by_case_id(case_id: int):
    return db.session.scalars(
        apply_inspection_scope(
            select(Inspection)
            .where(Inspection.pest_case_id == case_id)
            .order_by(Inspection.id)
        )
    ).all()


def get_interventions_by_case_id(case_id: int):
    return db.session.scalars(
        apply_intervention_scope(
            select(Intervention)
            .where(Intervention.pest_case_id == case_id)
            .order_by(Intervention.id)
        )
    ).all()


def get_follow_ups_by_case_id(case_id: int):
    return db.session.scalars(
        apply_follow_up_scope(
            select(FollowUp)
            .join(Intervention, Intervention.id == FollowUp.intervention_id)
            .where(Intervention.pest_case_id == case_id)
            .order_by(FollowUp.id)
        )
    ).all()


def _user_ref_or_none(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "username": user.username, "full_name": user.full_name}


def build_case_timeline(case: PestCase) -> list:
    try:
        inspection = get_inspection_by_case_id(case.id)
    except SQLAlchemyError:
        raise
    interventions = get_interventions_by_case_id(case.id)
    follow_ups = get_follow_ups_by_case_id(case.id)
    follow_by_intervention = {item.intervention_id: item for item in follow_ups}

    events: list = []

    def add_event(
        event_type: str,
        category: str,
        title: str,
        description: str,
        occurred_at,
        event_date,
        sequence: int,
        stable_id: int,
        actor=None,
        cycle=None,
        metadata=None,
    ):
        events.append(
            {
                "event_type": event_type,
                "category": category,
                "title": title,
                "description": description,
                "occurred_at": occurred_at.isoformat() if occurred_at is not None else None,
                "event_date": event_date.isoformat() if event_date is not None else None,
                "actor": _user_ref_or_none(actor),
                "cycle": cycle,
                "metadata": metadata or {},
                "_sequence": sequence,
                "_stable_id": stable_id,
            }
        )

    # Case reported: authoritative created timestamp.
    add_event(
        "case_reported",
        "CASE",
        "Pest case reported",
        f"{case.pest_name or 'Pending identification'} reported for farm #{case.farm_id}.",
        case.reported_at,
        case.observed_on,
        10,
        case.id * 1000 + 1,
        actor=case.reporter,
        metadata={
            "status": case.status,
            "suspected_pest": case.pest_name,
            "symptoms": case.symptoms,
            "reported_area_hectares": float(case.reported_area_hectares),
        },
    )

    # Submitted for inspection: exact submission time and submitting user are
    # not stored. Any ADMIN or TECHNICIAN may have performed the transition,
    # so no actor is attributed. Show only when the case has demonstrably
    # moved beyond REPORTED, using the earliest related authoritative
    # timestamp without inventing history.
    if inspection is not None or case.status != PestCaseStatus.REPORTED.value:
        submitted_at = inspection.created_at if inspection is not None else case.updated_at
        add_event(
            "submitted_for_inspection",
            "CASE",
            "Submitted for inspection",
            "Case moved from REPORTED to FOR_INSPECTION. Exact submission time is "
            "not stored; shown using the earliest related record.",
            submitted_at,
            None,
            20,
            case.id * 1000 + 2,
            actor=None,
            metadata={"inferred_timestamp": True},
        )

    if inspection is not None:
        add_event(
            "inspection_scheduled",
            "INSPECTION",
            "Inspection scheduled",
            f"Inspection scheduled for {inspection.scheduled_for.isoformat()}.",
            inspection.created_at,
            inspection.scheduled_for,
            30,
            inspection.id * 1000 + 3,
            actor=inspection.scheduler,
            metadata={
                "inspection_id": inspection.id,
                "scheduled_for": inspection.scheduled_for.isoformat(),
                "assigned_to": _user_ref_or_none(inspection.assignee),
            },
        )
        # No reschedule history is stored; only the current scheduled_for is shown.
        if inspection.completed_at is not None:
            outcome = "confirmed" if inspection.pest_confirmed else "not confirmed"
            add_event(
                "inspection_findings_recorded",
                "INSPECTION",
                f"Field findings recorded ({outcome})",
                (inspection.findings or "")[:500],
                inspection.completed_at,
                inspection.inspected_on,
                40,
                inspection.id * 1000 + 4,
                actor=inspection.completer,
                metadata={
                    "inspection_id": inspection.id,
                    "pest_confirmed": bool(inspection.pest_confirmed),
                    "confirmed_pest_name": inspection.confirmed_pest_name,
                    "validated_area_hectares": float(inspection.validated_area_hectares)
                    if inspection.validated_area_hectares is not None
                    else None,
                },
            )

    for index, intervention in enumerate(interventions, start=1):
        base = 50 + (index - 1) * 3
        add_event(
            "intervention_started",
            "INTERVENTION",
            f"Intervention cycle {index} started",
            f"{intervention.method_category}: {intervention.method_description[:300]}",
            intervention.created_at,
            intervention.scheduled_for,
            base,
            intervention.id * 1000 + 5,
            actor=intervention.creator,
            cycle=index,
            metadata={
                "intervention_id": intervention.id,
                "method_category": intervention.method_category,
                "assigned_to": _user_ref_or_none(intervention.assignee),
            },
        )
        if intervention.completed_at is not None:
            add_event(
                "intervention_completed",
                "INTERVENTION",
                f"Intervention cycle {index} completed",
                (intervention.completion_notes or "")[:500],
                intervention.completed_at,
                intervention.performed_on,
                base + 1,
                intervention.id * 1000 + 6,
                actor=intervention.completer,
                cycle=index,
                metadata={
                    "intervention_id": intervention.id,
                    "follow_up_due_on": intervention.follow_up_due_on.isoformat()
                    if intervention.follow_up_due_on is not None
                    else None,
                },
            )
        follow_up = follow_by_intervention.get(intervention.id)
        if follow_up is not None:
            outcome_label = (
                "resolved" if follow_up.outcome == "RESOLVED" else "further intervention required"
            )
            add_event(
                "follow_up_recorded",
                "FOLLOW_UP",
                f"Follow-up recorded for cycle {index} ({outcome_label})",
                (follow_up.assessment_notes or "")[:500],
                follow_up.created_at,
                follow_up.observed_on,
                base + 2,
                follow_up.id * 1000 + 7,
                actor=follow_up.recorder,
                cycle=index,
                metadata={
                    "follow_up_id": follow_up.id,
                    "intervention_id": intervention.id,
                    "outcome": follow_up.outcome,
                    "pest_observed": bool(follow_up.pest_observed),
                    "observed_affected_area_hectares": float(
                        follow_up.observed_affected_area_hectares
                    )
                    if follow_up.observed_affected_area_hectares is not None
                    else None,
                },
            )

    if case.status == PestCaseStatus.CLOSED.value:
        add_event(
            "case_closed",
            "CLOSURE",
            "Case closed",
            "Final recorded follow-up outcome was resolved. Shown using the case "
            "updated timestamp as the closest authoritative record.",
            case.updated_at,
            None,
            100,
            case.id * 1000 + 8,
            actor=None,
            metadata={"status": case.status},
        )

    def _sort_key(event: dict):
        occurred = event["occurred_at"] or event["event_date"] or ""
        return (occurred, event["_sequence"], event["_stable_id"])

    ordered = sorted(events, key=_sort_key)
    for event in ordered:
        event.pop("_sequence", None)
        event.pop("_stable_id", None)
    return ordered


@pest_cases_bp.get("/<int:case_id>/timeline")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_pest_case_timeline(case_id: int):
    try:
        case = get_pest_case_by_id(case_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case timeline lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)
    try:
        timeline = build_case_timeline(case)
        detail = _pest_case_detail(case)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case timeline build failed.")
        return auth_error("Pest case service unavailable.", 503)
    return jsonify(
        {
            "data": {"pest_case": detail, "timeline": timeline},
            "message": "Pest case timeline retrieved.",
        }
    )
