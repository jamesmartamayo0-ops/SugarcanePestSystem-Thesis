from datetime import date, datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import Farm, FollowUp, Intervention, PestCase, PestCaseStatus, User, UserRole
from app.models.follow_up import (
    manila_today,
    normalize_assessment_notes,
    normalize_follow_up_observed_on,
    normalize_follow_up_outcome,
    normalize_observed_area,
    normalize_pest_observed,
)

follow_ups_bp = Blueprint("follow_ups", __name__, url_prefix="/api/v1")

_RECORD_ALLOWED = frozenset(
    {
        "observed_on",
        "pest_observed",
        "observed_affected_area_hectares",
        "assessment_notes",
        "outcome",
    }
)
_RECORD_REQUIRED = frozenset({"observed_on", "pest_observed", "assessment_notes", "outcome"})
_FOLLOW_UP_OUTCOMES = frozenset({"RESOLVED", "REINTERVENTION_REQUIRED"})

# Reuse the per-case transaction-scoped advisory lock from Phase 3B/3C/3D so
# follow-up recording serializes on the same key as existing pest case,
# inspection, and intervention transitions. Consistent order everywhere:
# advisory lock for the case first, then SELECT ... FOR UPDATE on the case,
# then SELECT ... FOR UPDATE on the intervention.
PEST_CASE_TRANSITION_LOCK_BASE = 75240300


def acquire_follow_up_case_lock(case_id: int) -> None:
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


def get_follow_up_by_id(follow_up_id: int):
    return db.session.get(FollowUp, follow_up_id)


def get_follow_up_by_intervention_id(intervention_id: int):
    return db.session.scalar(
        select(FollowUp).where(FollowUp.intervention_id == intervention_id).limit(1)
    )


def get_follow_up_for_update_by_intervention(intervention_id: int):
    return db.session.scalar(
        select(FollowUp)
        .where(FollowUp.intervention_id == intervention_id)
        .with_for_update()
        .execution_options(populate_existing=True)
        .limit(1)
    )


def get_latest_completed_intervention_id(case_id: int):
    return db.session.scalar(
        select(Intervention.id)
        .where(
            Intervention.pest_case_id == case_id,
            Intervention.completed_at.is_not(None),
        )
        .order_by(Intervention.id.desc())
        .limit(1)
    )


def get_farm_by_id(farm_id: int):
    return db.session.get(Farm, farm_id)


def list_all_follow_ups(pest_case_id: int | None = None, intervention_id: int | None = None, outcome: str | None = None):
    statement = select(FollowUp).order_by(FollowUp.id)
    if outcome is not None:
        statement = statement.where(FollowUp.outcome == outcome)
    if intervention_id is not None:
        statement = statement.where(FollowUp.intervention_id == intervention_id)
    if pest_case_id is not None:
        statement = statement.join(
            Intervention, Intervention.id == FollowUp.intervention_id
        ).where(Intervention.pest_case_id == pest_case_id)
    return db.session.scalars(statement).all()


def list_due_interventions():
    statement = (
        select(Intervention)
        .join(PestCase, PestCase.id == Intervention.pest_case_id)
        .outerjoin(FollowUp, FollowUp.intervention_id == Intervention.id)
        .where(
            Intervention.completed_at.is_not(None),
            PestCase.status == PestCaseStatus.FOLLOW_UP_DUE.value,
            FollowUp.id.is_(None),
        )
        .order_by(Intervention.follow_up_due_on, Intervention.id)
    )
    return db.session.scalars(statement).all()


def commit_follow_up_changes() -> None:
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


def _intervention_ref(intervention: Intervention) -> dict:
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
    }


def _follow_up_detail(follow_up: FollowUp) -> dict:
    intervention = follow_up.intervention
    case = intervention.pest_case if intervention is not None else None
    return {
        "id": follow_up.id,
        "intervention_id": follow_up.intervention_id,
        "observed_on": _iso(follow_up.observed_on),
        "pest_observed": bool(follow_up.pest_observed),
        "observed_affected_area_hectares": (
            float(follow_up.observed_affected_area_hectares)
            if follow_up.observed_affected_area_hectares is not None
            else None
        ),
        "assessment_notes": follow_up.assessment_notes,
        "outcome": follow_up.outcome,
        "recorded_by_user_id": follow_up.recorded_by_user_id,
        "recorded_by": _user_ref(follow_up.recorder),
        "created_at": _iso(follow_up.created_at),
        "updated_at": _iso(follow_up.updated_at),
        "intervention": _intervention_ref(intervention) if intervention is not None else None,
        "assigned_to": (
            _user_ref(intervention.assignee)
            if intervention is not None and intervention.assignee is not None
            else None
        ),
        "pest_case": _case_farm_payload(case) if case is not None else None,
    }


def _due_state(follow_up_due_on: date) -> str:
    today = manila_today()
    if follow_up_due_on < today:
        return "OVERDUE"
    if follow_up_due_on == today:
        return "DUE_TODAY"
    return "UPCOMING"


def _due_entry(intervention: Intervention) -> dict:
    case = intervention.pest_case
    return {
        "intervention_id": intervention.id,
        "pest_case_id": intervention.pest_case_id,
        "method_category": intervention.method_category,
        "method_description": intervention.method_description,
        "scheduled_for": _iso(intervention.scheduled_for),
        "assigned_to_user_id": intervention.assigned_to_user_id,
        "assigned_to": _user_ref(intervention.assignee),
        "performed_on": _iso(intervention.performed_on),
        "follow_up_due_on": _iso(intervention.follow_up_due_on),
        "due_state": (
            _due_state(intervention.follow_up_due_on)
            if intervention.follow_up_due_on is not None
            else None
        ),
        "case_status": case.status if case is not None else None,
        "pest_case": _case_farm_payload(case) if case is not None else None,
        "intervention": _intervention_ref(intervention),
    }


def _parse_list_filters():
    raw_case = request.args.get("pest_case_id")
    raw_intervention = request.args.get("intervention_id")
    raw_outcome = request.args.get("outcome")
    pest_case_id: int | None = None
    intervention_id: int | None = None
    outcome: str | None = None
    if raw_case is not None and raw_case != "":
        try:
            pest_case_id = int(raw_case)
        except (TypeError, ValueError):
            return None, None, None, "Invalid follow-up filter."
        if not 0 < pest_case_id <= 2_147_483_647:
            return None, None, None, "Invalid follow-up filter."
    if raw_intervention is not None and raw_intervention != "":
        try:
            intervention_id = int(raw_intervention)
        except (TypeError, ValueError):
            return None, None, None, "Invalid follow-up filter."
        if not 0 < intervention_id <= 2_147_483_647:
            return None, None, None, "Invalid follow-up filter."
    if raw_outcome is not None and raw_outcome != "":
        if raw_outcome not in _FOLLOW_UP_OUTCOMES:
            return None, None, None, "Invalid follow-up filter."
        outcome = raw_outcome
    return pest_case_id, intervention_id, outcome, None


def _precheck_record(payload: dict) -> str | None:
    observed = payload.get("observed_on")
    if not isinstance(observed, str) or not observed.strip() or len(observed) > 32:
        return "Invalid follow-up data."
    if type(payload.get("pest_observed")) is not bool:
        return "Invalid follow-up data."
    if "observed_affected_area_hectares" in payload:
        area = payload["observed_affected_area_hectares"]
        if area is not None:
            if isinstance(area, bool):
                return "Invalid follow-up data."
            if isinstance(area, (int, float)):
                if not isinstance(area, int) and (
                    area != area or area in (float("inf"), float("-inf"))
                ):
                    return "Invalid follow-up data."
            elif isinstance(area, str):
                if not area.strip() or len(area) > 32:
                    return "Invalid follow-up data."
            else:
                return "Invalid follow-up data."
    notes = payload.get("assessment_notes")
    if not isinstance(notes, str) or not notes.strip() or len(notes) > 5000:
        return "Invalid follow-up data."
    outcome = payload.get("outcome")
    if not isinstance(outcome, str) or not outcome.strip() or len(outcome) > 32:
        return "Invalid follow-up data."
    return None


def _is_completed(intervention: Intervention) -> bool:
    return (
        intervention.completed_at is not None
        and intervention.completed_by_user_id is not None
        and intervention.performed_on is not None
        and intervention.completion_notes is not None
    )


def _can_act_on(intervention: Intervention) -> bool:
    if g.current_user.role == UserRole.ADMIN.value:
        return True
    return (
        g.current_user.role == UserRole.TECHNICIAN.value
        and intervention.assigned_to_user_id == g.current_user.id
    )


@follow_ups_bp.after_request
def _no_store_follow_ups_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@follow_ups_bp.get("/follow-ups")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_follow_ups():
    pest_case_id, intervention_id, outcome, invalid = _parse_list_filters()
    if invalid is not None:
        return auth_error(invalid, 400)
    try:
        follow_ups = list_all_follow_ups(pest_case_id, intervention_id, outcome)
        payload = [_follow_up_detail(item) for item in follow_ups]
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up list failed.")
        return auth_error("Follow-up service unavailable.", 503)
    return jsonify({"data": {"follow_ups": payload}, "message": "Follow-ups retrieved."})


@follow_ups_bp.get("/follow-ups/due")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_due_follow_ups():
    try:
        pending = list_due_interventions()
        payload = [_due_entry(item) for item in pending]
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up queue failed.")
        return auth_error("Follow-up service unavailable.", 503)
    return jsonify({"data": {"due": payload}, "message": "Follow-up queue retrieved."})


@follow_ups_bp.get("/follow-ups/<int:follow_up_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_follow_up(follow_up_id: int):
    try:
        follow_up = get_follow_up_by_id(follow_up_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up lookup failed.")
        return auth_error("Follow-up service unavailable.", 503)
    if follow_up is None:
        return auth_error("Follow-up not found.", 404)
    return jsonify(
        {"data": {"follow_up": _follow_up_detail(follow_up)}, "message": "Follow-up retrieved."}
    )


@follow_ups_bp.post("/interventions/<int:intervention_id>/record-follow-up")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def record_follow_up(intervention_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid follow-up data.", 400)
    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not _RECORD_REQUIRED.issubset(set(payload))
        or not set(payload).issubset(_RECORD_ALLOWED)
    ):
        return auth_error("Invalid follow-up data.", 400)
    invalid = _precheck_record(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        prelim = get_intervention_by_id(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up lookup failed.")
        return auth_error("Follow-up service unavailable.", 503)
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
    # The outcome is explicitly human-selected; it is never inferred.
    try:
        observed_on = normalize_follow_up_observed_on(payload["observed_on"])
        pest_observed = normalize_pest_observed(payload["pest_observed"])
        observed_area = normalize_observed_area(payload.get("observed_affected_area_hectares"))
        assessment_notes = normalize_assessment_notes(payload["assessment_notes"])
        outcome = normalize_follow_up_outcome(payload["outcome"])
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        # Same lock order as all Phase 3B/3C/3D/3E operations: advisory lock
        # for the immutable case first, then SELECT ... FOR UPDATE on the
        # case, then SELECT ... FOR UPDATE on the intervention.
        acquire_follow_up_case_lock(case_id)
        case = get_case_for_update(case_id)
        intervention = get_intervention_for_update(intervention_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up recording lookup failed.")
        return auth_error("Follow-up service unavailable.", 503)
    if case is None:
        db.session.rollback()
        return auth_error("Pest case not found.", 404)
    if intervention is None or intervention.pest_case_id != case.id:
        db.session.rollback()
        return auth_error("Intervention not found.", 404)

    if not _can_act_on(intervention):
        db.session.rollback()
        return auth_error("Permission denied.", 403)
    if not _is_completed(intervention):
        db.session.rollback()
        return auth_error("Intervention has not been completed.", 409)

    try:
        latest_id = get_latest_completed_intervention_id(case.id)
        existing = get_follow_up_for_update_by_intervention(intervention.id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up duplicate check failed.")
        return auth_error("Follow-up service unavailable.", 503)
    # Duplicate takes precedence over stale status so a retried submission
    # reports the recorded reassessment instead of a status mismatch.
    if existing is not None:
        db.session.rollback()
        return auth_error("Follow-up has already been recorded for this intervention.", 409)
    if case.status != PestCaseStatus.FOLLOW_UP_DUE.value:
        db.session.rollback()
        return auth_error("Follow-up cannot be recorded for this case.", 409)
    if latest_id is None or latest_id != intervention.id:
        db.session.rollback()
        return auth_error(
            "Follow-up can only be recorded for the latest completed intervention.", 409
        )

    if observed_on < intervention.performed_on:
        db.session.rollback()
        return auth_error("Observed date must not be earlier than the performed date.", 400)

    try:
        farm = get_farm_by_id(case.farm_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up farm lookup failed.")
        return auth_error("Follow-up service unavailable.", 503)
    if farm is None:
        db.session.rollback()
        return auth_error("Follow-up service unavailable.", 503)
    if observed_area is not None and observed_area > farm.area_hectares:
        db.session.rollback()
        return auth_error(
            "Observed area must not exceed the farm's recorded sugarcane area.", 400
        )

    try:
        follow_up = FollowUp(
            intervention_id=intervention.id,
            observed_on=observed_on,
            pest_observed=pest_observed,
            observed_affected_area_hectares=observed_area,
            assessment_notes=assessment_notes,
            outcome=outcome,
            recorded_by_user_id=g.current_user.id,
        )
        db.session.add(follow_up)
        if outcome == "RESOLVED":
            case.status = PestCaseStatus.CLOSED.value
        else:
            case.status = PestCaseStatus.REINTERVENTION_REQUIRED.value
        db.session.flush()
        follow_up.intervention = intervention
        try:
            follow_up.recorder = g.current_user
        except Exception:
            pass
        detail = _follow_up_detail(follow_up)
        detail["pest_case"]["status"] = case.status
        commit_follow_up_changes()
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Follow-up recording integrity failure.")
        return auth_error("Follow-up has already been recorded for this intervention.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Follow-up recording failed.")
        return auth_error("Follow-up service unavailable.", 503)

    response = jsonify({"data": {"follow_up": detail}, "message": "Follow-up recorded."})
    response.status_code = 201
    return response
