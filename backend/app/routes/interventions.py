from datetime import date, datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import Intervention, PestCase, PestCaseStatus, User, UserRole
from app.models.intervention import (
    normalize_completion_notes,
    normalize_follow_up_due_on,
    normalize_method_category,
    normalize_method_description,
    normalize_performed_on,
    normalize_scheduled_for as normalize_intervention_scheduled_for,
)

interventions_bp = Blueprint("interventions", __name__, url_prefix="/api/v1/interventions")

_PLAN_ALLOWED = frozenset(
    {
        "method_category",
        "method_description",
        "scheduled_for",
        "assigned_to_user_id",
        "follow_up_due_on",
    }
)
_COMPLETE_ALLOWED = frozenset(
    {
        "performed_on",
        "completion_notes",
        "follow_up_due_on",
        "reuse_planned_follow_up_date",
    }
)

# Reuse the per-case transaction-scoped advisory lock from Phase 3B/3C so
# intervention planning, re-planning, and completion all serialize on the
# same key as existing pest case and inspection transitions. Consistent
# order everywhere: advisory lock for the case first, then SELECT ... FOR
# UPDATE on the case, then (when an intervention row exists) SELECT ...
# FOR UPDATE on the intervention.
PEST_CASE_TRANSITION_LOCK_BASE = 75240300


def acquire_intervention_case_lock(case_id: int) -> None:
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


def get_intervention_by_id(intervention_id: int):
    return db.session.get(Intervention, intervention_id)


def get_intervention_for_update(intervention_id: int):
    return db.session.scalar(
        select(Intervention)
        .where(Intervention.id == intervention_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def get_pending_intervention_for_update(case_id: int):
    return db.session.scalar(
        select(Intervention)
        .where(
            Intervention.pest_case_id == case_id,
            Intervention.completed_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def list_all_interventions(pest_case_id: int | None = None, assigned_to: int | None = None):
    statement = select(Intervention).order_by(Intervention.id)
    if pest_case_id is not None:
        statement = statement.where(Intervention.pest_case_id == pest_case_id)
    if assigned_to is not None:
        statement = statement.where(Intervention.assigned_to_user_id == assigned_to)
    return db.session.scalars(statement).all()


def get_user_by_id(user_id: int):
    return db.session.get(User, user_id)


def commit_intervention_changes() -> None:
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


def _intervention_detail(intervention: Intervention) -> dict:
    return {
        "id": intervention.id,
        "pest_case_id": intervention.pest_case_id,
        "method_category": intervention.method_category,
        "method_description": intervention.method_description,
        "scheduled_for": _iso(intervention.scheduled_for),
        "assigned_to_user_id": intervention.assigned_to_user_id,
        "assigned_to": _user_ref(intervention.assignee),
        "created_by_user_id": intervention.created_by_user_id,
        "performed_on": _iso(intervention.performed_on),
        "completion_notes": intervention.completion_notes,
        "follow_up_due_on": _iso(intervention.follow_up_due_on),
        "completed_by_user_id": intervention.completed_by_user_id,
        "completed_at": _iso(intervention.completed_at),
        "created_at": _iso(intervention.created_at),
        "updated_at": _iso(intervention.updated_at),
        "pest_case": _case_farm_payload(intervention.pest_case),
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
            return None, None, "Invalid intervention filter."
        if not 0 < pest_case_id <= 2_147_483_647:
            return None, None, "Invalid intervention filter."
    if raw_assigned is not None and raw_assigned != "":
        try:
            assigned_to = int(raw_assigned)
        except (TypeError, ValueError):
            return None, None, "Invalid intervention filter."
        if not 0 < assigned_to <= 2_147_483_647:
            return None, None, "Invalid intervention filter."
    return pest_case_id, assigned_to, None


def _precheck_plan_update(payload: dict) -> str | None:
    if "method_category" in payload:
        value = payload["method_category"]
        if not isinstance(value, str) or not value.strip() or len(value) > 32:
            return "Invalid intervention data."
    if "method_description" in payload:
        value = payload["method_description"]
        if not isinstance(value, str) or not value.strip() or len(value) > 5000:
            return "Invalid intervention data."
    if "scheduled_for" in payload:
        value = payload["scheduled_for"]
        if not isinstance(value, str) or not value.strip() or len(value) > 32:
            return "Invalid intervention data."
    if "assigned_to_user_id" in payload:
        value = payload["assigned_to_user_id"]
        if type(value) is not int or not 0 < value <= 2_147_483_647:
            return "Invalid intervention data."
    if "follow_up_due_on" in payload:
        value = payload["follow_up_due_on"]
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > 32
        ):
            return "Invalid intervention data."
    return None


def _precheck_completion(payload: dict) -> str | None:
    performed = payload.get("performed_on")
    if not isinstance(performed, str) or not performed.strip() or len(performed) > 32:
        return "Invalid intervention completion."
    notes = payload.get("completion_notes")
    if not isinstance(notes, str) or not notes.strip() or len(notes) > 5000:
        return "Invalid intervention completion."
    if "follow_up_due_on" in payload:
        value = payload["follow_up_due_on"]
        if not isinstance(value, str) or not value.strip() or len(value) > 32:
            return "Invalid intervention completion."
    if "reuse_planned_follow_up_date" in payload:
        if payload["reuse_planned_follow_up_date"] is not True:
            return "Invalid intervention completion."
    return None


def _resolve_technician(user_id: int):
    try:
        user = get_user_by_id(user_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention technician lookup failed.")
        return None, auth_error("Intervention service unavailable.", 503)
    if user is None:
        return None, auth_error("Technician not found.", 404)
    if user.role != UserRole.TECHNICIAN.value or not bool(user.is_active):
        return None, auth_error("Invalid technician assignment.", 400)
    return user, None


def _is_completed(intervention: Intervention) -> bool:
    return (
        intervention.completed_at is not None
        or intervention.completed_by_user_id is not None
        or intervention.performed_on is not None
        or intervention.completion_notes is not None
    )


def _can_act_on(intervention: Intervention) -> bool:
    if g.current_user.role == UserRole.ADMIN.value:
        return True
    return (
        g.current_user.role == UserRole.TECHNICIAN.value
        and intervention.assigned_to_user_id == g.current_user.id
    )


@interventions_bp.after_request
def _no_store_interventions_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@interventions_bp.get("")
@interventions_bp.get("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_interventions():
    pest_case_id, assigned_to, invalid = _parse_list_filters()
    if invalid is not None:
        return auth_error(invalid, 400)
    try:
        interventions = list_all_interventions(pest_case_id, assigned_to)
        payload = [_intervention_detail(item) for item in interventions]
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention list failed.")
        return auth_error("Intervention service unavailable.", 503)
    return jsonify({"data": {"interventions": payload}, "message": "Interventions retrieved."})


@interventions_bp.get("/<int:intervention_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_intervention(intervention_id: int):
    try:
        intervention = get_intervention_by_id(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if intervention is None:
        return auth_error("Intervention not found.", 404)
    return jsonify(
        {"data": {"intervention": _intervention_detail(intervention)}, "message": "Intervention retrieved."}
    )


@interventions_bp.put("/<int:intervention_id>/plan")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def update_intervention_plan(intervention_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid intervention data.", 400)
    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not payload
        or not set(payload).issubset(_PLAN_ALLOWED)
    ):
        return auth_error("Invalid intervention data.", 400)
    invalid = _precheck_plan_update(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        prelim = get_intervention_by_id(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if prelim is None:
        return auth_error("Intervention not found.", 404)
    # Fast permission check before locking; authoritative check repeats while locked.
    if g.current_user.role != UserRole.ADMIN.value and (
        g.current_user.role != UserRole.TECHNICIAN.value
        or prelim.assigned_to_user_id != g.current_user.id
    ):
        return auth_error("Permission denied.", 403)
    case_id = prelim.pest_case_id

    # Validate candidate values before taking the lock so malformed input
    # fails fast without holding the per-case advisory lock.
    try:
        new_category = (
            normalize_method_category(payload["method_category"])
            if "method_category" in payload
            else None
        )
        new_description = (
            normalize_method_description(payload["method_description"])
            if "method_description" in payload
            else None
        )
        new_scheduled = (
            normalize_intervention_scheduled_for(payload["scheduled_for"])
            if "scheduled_for" in payload
            else None
        )
        new_follow_up = (
            normalize_follow_up_due_on(payload["follow_up_due_on"])
            if "follow_up_due_on" in payload
            else "__unchanged__"
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        acquire_intervention_case_lock(case_id)
        case = get_case_for_update(case_id)
        intervention = get_intervention_for_update(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention plan lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)
    if intervention is None or intervention.pest_case_id != case.id:
        db.session.rollback()
        return auth_error("Intervention not found.", 404)

    if not _can_act_on(intervention):
        db.session.rollback()
        return auth_error("Permission denied.", 403)
    if _is_completed(intervention):
        db.session.rollback()
        return auth_error("Completed interventions cannot be edited.", 409)
    if case.status != PestCaseStatus.UNDER_INTERVENTION.value:
        db.session.rollback()
        return auth_error("Intervention plan can no longer be edited.", 409)

    if "assigned_to_user_id" in payload:
        technician, error = _resolve_technician(payload["assigned_to_user_id"])
        if error is not None:
            db.session.rollback()
            db.session.rollback()
            return error
        intervention.assigned_to_user_id = technician.id
        intervention.assignee = technician
    if new_category is not None:
        intervention.method_category = new_category
    if new_description is not None:
        intervention.method_description = new_description
    if new_scheduled is not None:
        intervention.scheduled_for = new_scheduled
    if new_follow_up != "__unchanged__":
        intervention.follow_up_due_on = new_follow_up

    try:
        detail = _intervention_detail(intervention)
        commit_intervention_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Intervention plan integrity failure.")
        return auth_error("Intervention service unavailable.", 503)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention plan save failed.")
        return auth_error("Intervention service unavailable.", 503)
    return jsonify({"data": {"intervention": detail}, "message": "Intervention plan updated."})


@interventions_bp.post("/<int:intervention_id>/complete")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def complete_intervention(intervention_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid intervention completion.", 400)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or not set(payload).issubset(_COMPLETE_ALLOWED):
        return auth_error("Invalid intervention completion.", 400)
    if "performed_on" not in payload or "completion_notes" not in payload:
        return auth_error("Invalid intervention completion.", 400)
    if "follow_up_due_on" not in payload and payload.get("reuse_planned_follow_up_date") is not True:
        return auth_error("Follow-up date is required.", 400)
    invalid = _precheck_completion(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        prelim = get_intervention_by_id(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if prelim is None:
        return auth_error("Intervention not found.", 404)
    # Fast permission check before locking; authoritative check repeats while locked.
    if g.current_user.role != UserRole.ADMIN.value and (
        g.current_user.role != UserRole.TECHNICIAN.value
        or prelim.assigned_to_user_id != g.current_user.id
    ):
        return auth_error("Permission denied.", 403)
    case_id = prelim.pest_case_id

    # Normalize field values before locking so malformed input fails fast.
    try:
        performed_on = normalize_performed_on(payload["performed_on"])
        completion_notes = normalize_completion_notes(payload["completion_notes"])
        if "follow_up_due_on" in payload:
            follow_up_due_on = normalize_follow_up_due_on(payload["follow_up_due_on"])
        else:
            follow_up_due_on = "__reuse__"
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        acquire_intervention_case_lock(case_id)
        case = get_case_for_update(case_id)
        intervention = get_intervention_for_update(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention completion lookup failed.")
        return auth_error("Intervention service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)
    if intervention is None or intervention.pest_case_id != case.id:
        db.session.rollback()
        return auth_error("Intervention not found.", 404)

    if not _can_act_on(intervention):
        db.session.rollback()
        return auth_error("Permission denied.", 403)
    if _is_completed(intervention):
        db.session.rollback()
        return auth_error("Intervention has already been completed.", 409)
    if case.status != PestCaseStatus.UNDER_INTERVENTION.value:
        db.session.rollback()
        return auth_error("Intervention cannot be completed for this case.", 409)

    if follow_up_due_on == "__reuse__":
        if intervention.follow_up_due_on is None:
            db.session.rollback()
            return auth_error("Follow-up date is required.", 400)
        resolved_follow_up = intervention.follow_up_due_on
    else:
        resolved_follow_up = follow_up_due_on
    if resolved_follow_up < performed_on:
        db.session.rollback()
        return auth_error("Follow-up date must not be earlier than the performed date.", 400)

    intervention.performed_on = performed_on
    intervention.completion_notes = completion_notes
    intervention.follow_up_due_on = resolved_follow_up
    intervention.completed_by_user_id = g.current_user.id
    intervention.completed_at = datetime.now(timezone.utc)
    try:
        intervention.completer = g.current_user
    except Exception:
        pass
    case.status = PestCaseStatus.FOLLOW_UP_DUE.value

    try:
        detail = _intervention_detail(intervention)
        detail["pest_case"]["status"] = case.status
        commit_intervention_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Intervention completion integrity failure.")
        return auth_error("Intervention service unavailable.", 503)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Intervention completion save failed.")
        return auth_error("Intervention service unavailable.", 503)

    return jsonify({"data": {"intervention": detail}, "message": "Intervention completed."})
