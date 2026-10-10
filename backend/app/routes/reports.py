from datetime import date

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import FollowUp, Intervention, PestCase, PestCaseStatus
from app.models.intervention import manila_today
from app.routes.pest_cases import list_all_pest_cases

reports_bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")

_ALL_STATUSES = [status.value for status in PestCaseStatus]
_ALLOWED_STATUSES = frozenset(_ALL_STATUSES)


def _parse_int_param(value: str | None):
    if value is None or value == "":
        return None, None
    try:
        parsed = int(value.strip() if isinstance(value, str) else value)
    except (TypeError, ValueError, AttributeError):
        return None, "Invalid report filter."
    if not 0 < parsed <= 2_147_483_647:
        return None, "Invalid report filter."
    return parsed, None


def _parse_iso_date(value: str | None):
    if value is None or value == "":
        return None, None
    cleaned = value.strip() if isinstance(value, str) else ""
    if not cleaned or len(cleaned) > 32:
        return None, "Invalid report filter."
    try:
        return date.fromisoformat(cleaned), None
    except ValueError:
        return None, "Invalid report filter."


def _parse_report_filters():
    farm_id, invalid = _parse_int_param(request.args.get("farm_id"))
    if invalid is not None:
        return None, None, None, None, None, invalid
    farmer_id, invalid = _parse_int_param(request.args.get("farmer_id"))
    if invalid is not None:
        return None, None, None, None, None, invalid
    raw_status = request.args.get("status")
    status = None
    if raw_status is not None and raw_status != "":
        cleaned = raw_status.strip() if isinstance(raw_status, str) else raw_status
        if cleaned not in _ALLOWED_STATUSES:
            return None, None, None, None, None, "Invalid report filter."
        status = cleaned
    reported_from, invalid = _parse_iso_date(request.args.get("reported_from"))
    if invalid is not None:
        return None, None, None, None, None, invalid
    reported_to, invalid = _parse_iso_date(request.args.get("reported_to"))
    if invalid is not None:
        return None, None, None, None, None, invalid
    if reported_from is not None and reported_to is not None and reported_from > reported_to:
        return None, None, None, None, None, "Invalid report filter."
    return status, farmer_id, farm_id, reported_from, reported_to, None


def get_filtered_cases(status=None, farmer_id=None, farm_id=None, reported_from=None, reported_to=None):
    return list_all_pest_cases(
        farm_id=farm_id,
        status=status,
        farmer_id=farmer_id,
        search=None,
        reported_from=reported_from,
        reported_to=reported_to,
    )


def get_interventions_for_cases(case_ids: list) -> list:
    if not case_ids:
        return []
    return db.session.scalars(
        select(Intervention).where(Intervention.pest_case_id.in_(case_ids)).order_by(Intervention.id)
    ).all()


def get_follow_ups_for_interventions(intervention_ids: list) -> list:
    if not intervention_ids:
        return []
    return db.session.scalars(
        select(FollowUp).where(FollowUp.intervention_id.in_(intervention_ids)).order_by(FollowUp.id)
    ).all()


def build_operational_report(cases: list) -> dict:
    case_ids = [case.id for case in cases]
    by_status = {status: 0 for status in _ALL_STATUSES}
    for case in cases:
        if case.status in by_status:
            by_status[case.status] += 1
    total_cases = len(cases)
    closed_cases = by_status.get("CLOSED", 0)
    not_confirmed_cases = by_status.get("NOT_CONFIRMED", 0)
    open_cases = total_cases - closed_cases - not_confirmed_cases

    interventions = get_interventions_for_cases(case_ids)
    follow_ups = get_follow_ups_for_interventions([item.id for item in interventions])
    follow_by_intervention = {item.intervention_id: item for item in follow_ups}

    by_case_interventions: dict = {}
    for item in interventions:
        by_case_interventions.setdefault(item.pest_case_id, []).append(item)

    today = manila_today()
    pending = 0
    overdue = 0
    for item in interventions:
        if item.completed_at is None:
            continue
        case = next((c for c in cases if c.id == item.pest_case_id), None)
        if case is None or case.status != PestCaseStatus.FOLLOW_UP_DUE.value:
            continue
        if item.id in follow_by_intervention:
            continue
        pending += 1
        if item.follow_up_due_on is not None and item.follow_up_due_on < today:
            overdue += 1

    completed_follow_ups = len(follow_ups)
    resolved = sum(1 for item in follow_ups if item.outcome == "RESOLVED")
    reintervention = sum(1 for item in follow_ups if item.outcome == "REINTERVENTION_REQUIRED")

    completed_interventions = sum(1 for item in interventions if item.completed_at is not None)
    pending_interventions = sum(1 for item in interventions if item.completed_at is None)
    cases_with_repeat = sum(1 for items in by_case_interventions.values() if len(items) >= 2)

    rows = []
    for case in sorted(cases, key=lambda c: c.id):
        items = by_case_interventions.get(case.id, [])
        latest = items[-1] if items else None
        latest_follow = follow_by_intervention.get(latest.id) if latest is not None else None
        farm = case.farm
        farmer = farm.farmer if farm is not None else None
        rows.append(
            {
                "case_id": case.id,
                "farmer": farmer.full_name if farmer is not None else None,
                "farm": farm.plot_identifier if farm is not None else None,
                "barangay": farm.barangay if farm is not None else None,
                "pest_name": case.pest_name,
                "current_status": case.status,
                "reported_at": case.reported_at.isoformat() if case.reported_at is not None else None,
                "reported_area_hectares": float(case.reported_area_hectares),
                "latest_intervention_cycle": len(items) if items else None,
                "latest_follow_up_outcome": latest_follow.outcome if latest_follow is not None else None,
            }
        )

    return {
        "summary": {
            "total_cases": total_cases,
            "open_cases": open_cases,
            "closed_cases": closed_cases,
            "not_confirmed_cases": not_confirmed_cases,
            "under_intervention": by_status.get("UNDER_INTERVENTION", 0),
            "follow_ups_due": pending,
            "reintervention_required": by_status.get("REINTERVENTION_REQUIRED", 0),
        },
        "by_status": by_status,
        "follow_up_summary": {
            "pending": pending,
            "overdue": overdue,
            "completed": completed_follow_ups,
            "resolved": resolved,
            "reintervention_required": reintervention,
        },
        "intervention_summary": {
            "total_records": len(interventions),
            "completed": completed_interventions,
            "pending": pending_interventions,
            "cases_with_repeat_intervention": cases_with_repeat,
        },
        "cases": rows,
    }


@reports_bp.after_request
def _no_store_reports_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@reports_bp.get("/operational")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def operational_report():
    status, farmer_id, farm_id, reported_from, reported_to, invalid = _parse_report_filters()
    if invalid is not None:
        return auth_error(invalid, 400)
    try:
        cases = get_filtered_cases(
            status=status,
            farmer_id=farmer_id,
            farm_id=farm_id,
            reported_from=reported_from,
            reported_to=reported_to,
        )
        report = build_operational_report(cases)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Operational report failed.")
        return auth_error("Report service unavailable.", 503)
    return jsonify({"data": {"report": report}, "message": "Operational report retrieved."})
