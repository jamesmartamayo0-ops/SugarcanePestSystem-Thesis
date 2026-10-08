from datetime import date

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
    normalize_observed_on,
    normalize_pest_name,
    normalize_reported_area,
    normalize_scheduled_for,
    normalize_symptoms,
)

pest_cases_bp = Blueprint("pest_cases", __name__, url_prefix="/api/v1/pest-cases")

# Transaction-scoped advisory lock serializing REPORTED -> FOR_INSPECTION
# transitions so two concurrent submissions cannot race the status check.
# The key mixes a fixed base with the case id; it is distinct from the admin
# status lock (75240202) and the CLI bootstrap lock (75240201).
PEST_CASE_TRANSITION_LOCK_BASE = 75240300

_CREATE_REQUIRED = frozenset({"farm_id", "pest_name", "reported_area_hectares"})
_CREATE_ALLOWED = frozenset(
    {"farm_id", "pest_name", "symptoms", "observed_on", "reported_area_hectares"}
)
_UPDATE_ALLOWED = frozenset(
    {"farm_id", "pest_name", "symptoms", "observed_on", "reported_area_hectares"}
)
_ALLOWED_STATUSES = frozenset({status.value for status in PestCaseStatus})
_MAX_INPUT_LENGTHS = {"pest_name": 500, "symptoms": 5000}


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


def _pest_case_detail(case: PestCase) -> dict:
    summary = _pest_case_summary(case)
    summary.update(
        {
            "symptoms": case.symptoms,
            "farm": _farm_reference(case.farm),
            "reporter": _reporter_reference(case.reporter),
            "updated_at": _iso(case.updated_at),
        }
    )
    return summary


def list_all_pest_cases(farm_id: int | None = None, status: str | None = None):
    statement = select(PestCase).order_by(PestCase.id)
    if farm_id is not None:
        statement = statement.where(PestCase.farm_id == farm_id)
    if status is not None:
        statement = statement.where(PestCase.status == status)
    return db.session.scalars(statement).all()


def get_pest_case_by_id(case_id: int):
    return db.session.get(PestCase, case_id)


def get_pest_case_for_update(case_id: int):
    return db.session.scalar(
        select(PestCase)
        .where(PestCase.id == case_id)
        .with_for_update()
        .execution_options(populate_existing=True)
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
        if field == "symptoms" and value in (None, ""):
            continue
        if not isinstance(value, str) or not value or len(value) > limit:
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


def _parse_filter_args():
    raw_farm_id = request.args.get("farm_id")
    raw_status = request.args.get("status")
    farm_id: int | None = None
    status: str | None = None
    if raw_farm_id is not None and raw_farm_id != "":
        try:
            farm_id = int(raw_farm_id)
        except (TypeError, ValueError):
            return None, None, "Invalid pest case filter."
        if not 0 < farm_id <= 2_147_483_647:
            return None, None, "Invalid pest case filter."
    if raw_status is not None and raw_status != "":
        if raw_status not in _ALLOWED_STATUSES:
            return None, None, "Invalid pest case filter."
        status = raw_status
    return farm_id, status, None


@pest_cases_bp.after_request
def _no_store_pest_cases_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@pest_cases_bp.get("")
@pest_cases_bp.get("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_pest_cases():
    farm_id, status, invalid = _parse_filter_args()
    if invalid is not None:
        return auth_error(invalid, 400)
    try:
        cases = list_all_pest_cases(farm_id, status)
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
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Pest case lookup failed.")
        return auth_error("Pest case service unavailable.", 503)
    if case is None:
        return auth_error("Pest case not found.", 404)
    return jsonify(
        {"data": {"pest_case": _pest_case_detail(case)}, "message": "Pest case retrieved."}
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
            pest_name=payload["pest_name"],
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
    if target_farm is None:
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
        select(Inspection).where(Inspection.pest_case_id == case_id).limit(1)
    )


@pest_cases_bp.post("/<int:case_id>/schedule-inspection")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
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
        scheduled_for = normalize_scheduled_for(raw_date)
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
        return auth_error("Inspection has already been scheduled for this case.", 409)

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
            "validated_area_hectares": None,
            "completed_by_user_id": None,
            "completed_at": None,
            "pest_case": _pest_case_detail(case),
        }
        commit_pest_case_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Inspection scheduling integrity failure.")
        return auth_error("Inspection has already been scheduled for this case.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Inspection scheduling failed.")
        return auth_error("Inspection service unavailable.", 503)

    response = jsonify({"data": {"inspection": detail}, "message": "Inspection scheduled."})
    response.status_code = 201
    return response
