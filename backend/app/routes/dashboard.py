from flask import Blueprint, current_app, jsonify
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.dashboard_farm_map import load_farm_map_projection
from app.extensions import db
from app.models import Farmer, Farm, FollowUp, Intervention, PestCase, PestCaseStatus
from app.models.intervention import manila_today
from app.scoping import (
    apply_case_scope,
    apply_farm_scope,
    apply_farmer_scope,
    apply_intervention_scope,
)

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/v1/dashboard")

_ALL_STATUSES = [status.value for status in PestCaseStatus]


def count_farmers() -> int:
    statement = apply_farmer_scope(select(func.count()).select_from(Farmer))
    return int(db.session.scalar(statement) or 0)


def count_farms() -> int:
    statement = apply_farm_scope(select(func.count()).select_from(Farm))
    return int(db.session.scalar(statement) or 0)


def count_cases_by_status() -> dict:
    statement = apply_case_scope(
        select(PestCase.status, func.count()).group_by(PestCase.status)
    )
    rows = db.session.execute(statement).all()
    counts = {status: 0 for status in _ALL_STATUSES}
    for status, total in rows:
        if status in counts:
            counts[status] = int(total)
    return counts


def count_total_cases(status_counts: dict | None = None) -> int:
    if status_counts is None:
        statement = apply_case_scope(select(func.count()).select_from(PestCase))
        return int(db.session.scalar(statement) or 0)
    return int(sum(status_counts.values()))


def count_follow_ups_due() -> int:
    statement = (
        select(func.count())
        .select_from(Intervention)
        .join(PestCase, PestCase.id == Intervention.pest_case_id)
        .outerjoin(FollowUp, FollowUp.intervention_id == Intervention.id)
        .where(
            Intervention.completed_at.is_not(None),
            PestCase.status == PestCaseStatus.FOLLOW_UP_DUE.value,
            FollowUp.id.is_(None),
        )
    )
    return int(db.session.scalar(apply_intervention_scope(statement)) or 0)


def count_overdue_follow_ups() -> int:
    today = manila_today()
    statement = (
        select(func.count())
        .select_from(Intervention)
        .join(PestCase, PestCase.id == Intervention.pest_case_id)
        .outerjoin(FollowUp, FollowUp.intervention_id == Intervention.id)
        .where(
            Intervention.completed_at.is_not(None),
            PestCase.status == PestCaseStatus.FOLLOW_UP_DUE.value,
            FollowUp.id.is_(None),
            Intervention.follow_up_due_on.is_not(None),
            Intervention.follow_up_due_on < today,
        )
    )
    return int(db.session.scalar(apply_intervention_scope(statement)) or 0)


def get_recent_cases(limit: int = 5):
    statement = apply_case_scope(
        select(PestCase)
        .order_by(PestCase.updated_at.desc(), PestCase.id.desc())
        .limit(limit)
    )
    return db.session.scalars(statement).all()


def build_dashboard_summary() -> dict:
    by_status = count_cases_by_status()
    follow_ups_due = count_follow_ups_due()
    overdue = count_overdue_follow_ups()
    recent = get_recent_cases()
    return {
        "totals": {
            "farmers": count_farmers(),
            "farms": count_farms(),
            "pest_cases": count_total_cases(by_status),
        },
        "by_status": by_status,
        "action_needed": {
            "awaiting_inspection_scheduling": by_status.get("FOR_INSPECTION", 0),
            "inspections_scheduled_awaiting_validation": by_status.get(
                "INSPECTION_SCHEDULED", 0
            ),
            "validated_awaiting_intervention": by_status.get("FIELD_VALIDATED", 0),
            "interventions_in_progress": by_status.get("UNDER_INTERVENTION", 0),
            "follow_ups_due": follow_ups_due,
            "overdue_follow_ups": overdue,
            "reintervention_required": by_status.get("REINTERVENTION_REQUIRED", 0),
        },
        "recent_cases": [
            {
                "id": case.id,
                "pest_name": case.pest_name,
                "status": case.status,
                "farm_id": case.farm_id,
                "updated_at": case.updated_at.isoformat()
                if case.updated_at is not None
                else None,
            }
            for case in recent
        ],
    }


@dashboard_bp.after_request
def _no_store_dashboard_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@dashboard_bp.get("/summary")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def dashboard_summary():
    try:
        summary = build_dashboard_summary()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Dashboard summary failed.")
        return auth_error("Dashboard service unavailable.", 503)
    return jsonify({"data": {"summary": summary}, "message": "Dashboard summary retrieved."})


@dashboard_bp.get("/farm-map")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def dashboard_farm_map():
    try:
        projection = load_farm_map_projection()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Dashboard farm map failed.")
        return auth_error("Dashboard service unavailable.", 503)
    return jsonify(
        {"data": projection, "message": "Farm monitoring map retrieved."}
    )
