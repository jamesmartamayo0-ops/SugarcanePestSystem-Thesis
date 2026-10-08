from datetime import date, datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import (
    Farm,
    Inspection,
    PestCase,
    PestCaseStatus,
    User,
    UserRole,
    normalize_findings,
    normalize_inspected_on,
    normalize_scheduled_for,
    normalize_validated_area,
)

inspections_bp = Blueprint("inspections", __name__, url_prefix="/api/v1/inspections")

_SCHEDULE_UPDATE_ALLOWED = frozenset({"scheduled_for", "assigned_to_user_id"})
_FINDINGS_REQUIRED = frozenset(
    {"findings", "pest_confirmed", "validated_area_hectares", "inspected_on"}
)

# Reuse the per-case transaction-scoped advisory lock from Phase 3B so
# scheduling, rescheduling, and findings all serialize on the same key as
# existing pest case transitions. Consistent order everywhere: advisory lock
# for the case first, then SELECT ... FOR UPDATE on the case, then (when an
# inspection row exists) SELECT ... FOR UPDATE on the inspection.
PEST_CASE_TRANSITION_LOCK_BASE = 75240300


def acquire_inspection_case_lock(case_id: int) -> None:
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": PEST_CASE_TRANSITION_LOCK_BASE + case_id},
    )


def get_case_for_update(case_id: int):
    return db.session.scalar(
        select(PestCase)
        .where(PestCase.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def get_inspection_by_id(inspection_id: int):
    return db.session.get(Inspection, inspection_id)


def get_inspection_for_update(inspection_id: int):
    return db.session.scalar(
        select(Inspection)
        .where(Inspection.id == inspection_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def get_inspection_by_case_for_update(case_id: int):
    return db.session.scalar(
        select(Inspection)
        .where(Inspection.pest_case_id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def list_all_inspections(pest_case_id: int | None = None, assigned_to: int | None = None):
    statement = select(Inspection).order_by(Inspection.id)
    if pest_case_id is not None:
        statement = statement.where(Inspection.pest_case_id == pest_case_id)
    if assigned_to is not None:
        statement = statement.where(Inspection.assigned_to_user_id == assigned_to)
    return db.session.scalars(statement).all()


def get_user_by_id(user_id: int):
    return db.session.get(User, user_id)


def get_farm_by_id(farm_id: int):
    return db.session.get(Farm, farm_id)


def list_active_technicians():
    return db.session.scalars(
        select(User)
        .where(User.role == UserRole.TECHNICIAN.value, User.is_active.is_(True))
        .order_by(User.id)
    ).all()


def commit_inspection_changes() -> None:
    db.session.commit()


def _iso(value) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return None


def _user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "username": user.username, "full_name": user.full_name}


def _case_farm_payload(case: PestCase) -> dict:
    farm = case.farm
    farmer = farm.farmer if farm is not None else None
    return {
        "id": case.id,
        "pest_name": case.pest_name,
        "status": case.status,
        "reported_area_hectares": float(case.reported_area_hectares),
        "farm": (
            {
                "id": farm.id,
                "plot_identifier": farm.plot_identifier,
                "barangay": farm.barangay,
                "area_hectares": float(farm.area_hectares),
                "farmer": (
                    {
                        "id": farmer.id,
                        "full_name": farmer.full_name,
                        "barangay": farmer.barangay,
                    }
                    if farmer is not None
                    else None
                ),
            }
            if farm is not None
            else None
        ),
    }


def _inspection_detail(inspection: Inspection) -> dict:
    return {
        "id": inspection.id,
        "pest_case_id": inspection.pest_case_id,
        "scheduled_for": _iso(inspection.scheduled_for),
        "assigned_to_user_id": inspection.assigned_to_user_id,
        "assigned_to": _user_ref(inspection.assignee),
        "scheduled_by_user_id": inspection.scheduled_by_user_id,
        "inspected_on": _iso(inspection.inspected_on),
        "findings": inspection.findings,
        "pest_confirmed": inspection.pest_confirmed,
        "validated_area_hectares": (
            float(inspection.validated_area_hectares)
            if inspection.validated_area_hectares is not None
            else None
        ),
        "completed_by_user_id": inspection.completed_by_user_id,
        "completed_at": _iso(inspection.completed_at),
        "created_at": _iso(inspection.created_at),
        "updated_at": _iso(inspection.updated_at),
        "pest_case": _case_farm_payload(inspection.pest_case),
    }


def _parse_list_filters():
    raw_case = request.args.get("pest_case_id")
    raw_assigned = request.args.get("assigned_to_user_id")
    # Backwards-tolerant aliases documented for the frontend filters.
    if raw_case is None:
        raw_case = request.args.get("case_id")
    if raw_assigned is None:
        raw_assigned = request.args.get("technician_id")
    pest_case_id: int | None = None
    assigned_to: int | None = None
    if raw_case is not None and raw_case != "":
        try:
            pest_case_id = int(raw_case)
        except (TypeError, ValueError):
            return None, None, "Invalid inspection filter."
        if not 0 < pest_case_id <= 2_147_483_647:
            return None, None, "Invalid inspection filter."
    if raw_assigned is not None and raw_assigned != "":
        try:
            assigned_to = int(raw_assigned)
        except (TypeError, ValueError):
            return None, None, "Invalid inspection filter."
        if not 0 < assigned_to <= 2_147_483_647:
            return None, None, "Invalid inspection filter."
    return pest_case_id, assigned_to, None


def _precheck_schedule_update(payload: dict) -> str | None:
    if "scheduled_for" in payload:
        value = payload["scheduled_for"]
        if not isinstance(value, str) or not value.strip() or len(value) > 32:
            return "Invalid inspection data."
    if "assigned_to_user_id" in payload:
        value = payload["assigned_to_user_id"]
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            return "Invalid inspection data."
    return None


def _precheck_findings(payload: dict) -> str | None:
    findings = payload.get("findings")
    if not isinstance(findings, str) or not findings.strip() or len(findings) > 5000:
        return "Invalid inspection findings."
    if type(payload.get("pest_confirmed")) is not bool:
        return "Invalid inspection findings."
    area = payload.get("validated_area_hectares")
    if isinstance(area, bool):
        return "Invalid inspection findings."
    if isinstance(area, (int, float)):
        if not isinstance(area, int) and (
            area != area or area in (float("inf"), float("-inf"))
        ):
            return "Invalid inspection findings."
    elif isinstance(area, str):
        if not area.strip() or len(area) > 32:
            return "Invalid inspection findings."
    else:
        return "Invalid inspection findings."
    inspected = payload.get("inspected_on")
    if not isinstance(inspected, str) or not inspected.strip() or len(inspected) > 32:
        return "Invalid inspection findings."
    return None


def _resolve_technician(user_id: int):
    try:
        user = get_user_by_id(user_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection technician lookup failed.")
        return None, auth_error("Inspection service unavailable.", 503)
    if user is None:
        return None, auth_error("Technician not found.", 404)
    if user.role != UserRole.TECHNICIAN.value or not bool(user.is_active):
        return None, auth_error("Invalid technician assignment.", 400)
    return user, None


def _is_completed(inspection: Inspection) -> bool:
    return (
        inspection.completed_at is not None
        or inspection.completed_by_user_id is not None
        or inspection.inspected_on is not None
        or inspection.findings is not None
        or inspection.pest_confirmed is not None
        or inspection.validated_area_hectares is not None
    )


@inspections_bp.after_request
def _no_store_inspections_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@inspections_bp.get("")
@inspections_bp.get("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_inspections():
    pest_case_id, assigned_to, invalid = _parse_list_filters()
    if invalid is not None:
        return auth_error(invalid, 400)
    try:
        inspections = list_all_inspections(pest_case_id, assigned_to)
        payload = [_inspection_detail(item) for item in inspections]
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection list failed.")
        return auth_error("Inspection service unavailable.", 503)
    return jsonify({"data": {"inspections": payload}, "message": "Inspections retrieved."})


@inspections_bp.get("/technicians")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_technicians():
    try:
        users = list_active_technicians()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection technician list failed.")
        return auth_error("Inspection service unavailable.", 503)
    return jsonify(
        {
            "data": {"technicians": [_user_ref(user) for user in users]},
            "message": "Technicians retrieved.",
        }
    )


@inspections_bp.get("/<int:inspection_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_inspection(inspection_id: int):
    try:
        inspection = get_inspection_by_id(inspection_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if inspection is None:
        return auth_error("Inspection not found.", 404)
    return jsonify(
        {"data": {"inspection": _inspection_detail(inspection)}, "message": "Inspection retrieved."}
    )


@inspections_bp.put("/<int:inspection_id>/schedule")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def reschedule_inspection(inspection_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid inspection data.", 400)
    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not payload
        or not set(payload).issubset(_SCHEDULE_UPDATE_ALLOWED)
    ):
        return auth_error("Invalid inspection data.", 400)
    invalid = _precheck_schedule_update(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        prelim = get_inspection_by_id(inspection_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if prelim is None:
        return auth_error("Inspection not found.", 404)
    case_id = prelim.pest_case_id

    # Validate candidate dates before taking the lock so malformed input
    # fails fast without holding the per-case advisory lock.
    try:
        new_scheduled = (
            normalize_scheduled_for(payload["scheduled_for"])
            if "scheduled_for" in payload
            else None
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        acquire_inspection_case_lock(case_id)
        case = get_case_for_update(case_id)
        inspection = get_inspection_for_update(inspection_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection reschedule lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)
    if inspection is None or inspection.pest_case_id != case.id:
        db.session.rollback()
        return auth_error("Inspection not found.", 404)
    if case.status != PestCaseStatus.INSPECTION_SCHEDULED.value:
        db.session.rollback()
        return auth_error("Inspection can no longer be rescheduled.", 409)
    if _is_completed(inspection):
        db.session.rollback()
        return auth_error("Inspection can no longer be rescheduled.", 409)

    if "assigned_to_user_id" in payload:
        technician, error = _resolve_technician(payload["assigned_to_user_id"])
        if error is not None:
            db.session.rollback()
            # _resolve_technician already rolled back on DB failure; calling
            # rollback again is harmless and releases the advisory lock.
            db.session.rollback()
            return error
        inspection.assigned_to_user_id = technician.id
        inspection.assignee = technician
    if new_scheduled is not None:
        inspection.scheduled_for = new_scheduled

    try:
        detail = _inspection_detail(inspection)
        commit_inspection_changes()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection reschedule failed.")
        return auth_error("Inspection service unavailable.", 503)
    return jsonify({"data": {"inspection": detail}, "message": "Inspection rescheduled."})


@inspections_bp.post("/<int:inspection_id>/record-findings")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def record_findings(inspection_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid inspection findings.", 400)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != _FINDINGS_REQUIRED:
        return auth_error("Invalid inspection findings.", 400)
    invalid = _precheck_findings(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        prelim = get_inspection_by_id(inspection_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if prelim is None:
        return auth_error("Inspection not found.", 404)
    # Fast permission check before locking; authoritative check repeats while locked.
    if g.current_user.role != UserRole.ADMIN.value and (
        g.current_user.role != UserRole.TECHNICIAN.value
        or prelim.assigned_to_user_id != g.current_user.id
    ):
        return auth_error("Permission denied.", 403)
    case_id = prelim.pest_case_id

    # Normalize field values before locking so malformed input fails fast.
    try:
        findings = normalize_findings(payload["findings"])
        inspected_on = normalize_inspected_on(payload["inspected_on"])
        validated = normalize_validated_area(payload["validated_area_hectares"])
    except ValueError as exc:
        return auth_error(str(exc), 400)
    pest_confirmed = payload["pest_confirmed"]
    if type(pest_confirmed) is not bool:
        return auth_error("Invalid inspection findings.", 400)
    if pest_confirmed and (validated is None or validated <= 0):
        return auth_error(
            "Validated area must be positive when pest damage is confirmed.", 400
        )
    if not pest_confirmed and (validated is None or validated != 0):
        return auth_error(
            "Validated area must be zero when pest damage is not confirmed.", 400
        )

    try:
        acquire_inspection_case_lock(case_id)
        case = get_case_for_update(case_id)
        inspection = get_inspection_for_update(inspection_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection findings lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)
    if inspection is None or inspection.pest_case_id != case.id:
        db.session.rollback()
        return auth_error("Inspection not found.", 404)

    if g.current_user.role != UserRole.ADMIN.value and (
        g.current_user.role != UserRole.TECHNICIAN.value
        or inspection.assigned_to_user_id != g.current_user.id
    ):
        db.session.rollback()
        return auth_error("Permission denied.", 403)

    if case.status != PestCaseStatus.INSPECTION_SCHEDULED.value:
        db.session.rollback()
        if _is_completed(inspection) or case.status in (
            PestCaseStatus.NOT_CONFIRMED.value,
            PestCaseStatus.FIELD_VALIDATED.value,
        ):
            return auth_error("Inspection findings have already been recorded.", 409)
        return auth_error("Inspection findings cannot be recorded for this case.", 409)
    if _is_completed(inspection):
        db.session.rollback()
        return auth_error("Inspection findings have already been recorded.", 409)

    try:
        farm = get_farm_by_id(case.farm_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection farm lookup failed.")
        return auth_error("Inspection service unavailable.", 503)
    if farm is None:
        db.session.rollback()
        return auth_error("Inspection service unavailable.", 503)
    if validated > farm.area_hectares:
        db.session.rollback()
        return auth_error(
            "Validated area must not exceed the farm's recorded sugarcane area.", 400
        )

    inspection.findings = findings
    inspection.inspected_on = inspected_on
    inspection.pest_confirmed = pest_confirmed
    inspection.validated_area_hectares = validated
    inspection.completed_by_user_id = g.current_user.id
    inspection.completed_at = datetime.now(timezone.utc)
    try:
        inspection.completer = g.current_user
    except Exception:
        pass
    if pest_confirmed:
        case.status = PestCaseStatus.FIELD_VALIDATED.value
    else:
        case.status = PestCaseStatus.NOT_CONFIRMED.value

    try:
        detail = _inspection_detail(inspection)
        # Include the server-controlled next status for convenience.
        detail["pest_case"]["status"] = case.status
        commit_inspection_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Inspection findings integrity failure.")
        return auth_error("Inspection service unavailable.", 503)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection findings save failed.")
        return auth_error("Inspection service unavailable.", 503)

    message = (
        "Field inspection validated."
        if pest_confirmed
        else "Inspection completed with no pest damage confirmed."
    )
    return jsonify({"data": {"inspection": detail}, "message": message})
