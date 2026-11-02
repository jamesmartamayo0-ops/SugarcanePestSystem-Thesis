from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import Farm, Farmer
from app.scoping import apply_farm_scope, apply_farmer_scope, is_admin

farmers_bp = Blueprint("farmers", __name__, url_prefix="/api/v1/farmers")

_CREATE_REQUIRED = frozenset({"full_name", "barangay"})
_CREATE_ALLOWED = frozenset({"full_name", "barangay", "contact_number"})
_UPDATE_ALLOWED = frozenset({"full_name", "barangay", "contact_number"})
_MAX_INPUT_LENGTHS = {"full_name": 500, "barangay": 500, "contact_number": 64}


def _farmer_summary(farmer: Farmer, farms=None) -> dict:
    visible_farms = (farmer.farms or []) if farms is None else farms
    return {
        "id": farmer.id,
        "full_name": farmer.full_name,
        "barangay": farmer.barangay,
        "contact_number": farmer.contact_number,
        "farm_count": len(visible_farms),
    }


def _farm_reference(farm) -> dict:
    return {
        "id": farm.id,
        "plot_identifier": farm.plot_identifier,
        "barangay": farm.barangay,
        "area_hectares": float(farm.area_hectares),
    }


def _farmer_detail(farmer: Farmer, farms=None) -> dict:
    created = farmer.created_at
    updated = farmer.updated_at
    if isinstance(created, datetime) and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    if isinstance(updated, datetime) and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    visible_farms = (farmer.farms or []) if farms is None else farms
    return {
        "id": farmer.id,
        "full_name": farmer.full_name,
        "barangay": farmer.barangay,
        "contact_number": farmer.contact_number,
        "farms": [_farm_reference(farm) for farm in sorted(visible_farms, key=lambda f: f.id)],
        "created_at": created.isoformat() if isinstance(created, datetime) else None,
        "updated_at": updated.isoformat() if isinstance(updated, datetime) else None,
    }


def visible_farms_for_farmer(farmer: Farmer, user=None) -> list:
    farms = sorted(farmer.farms or [], key=lambda farm: farm.id)
    user = user if user is not None else g.current_user
    if user is None or is_admin(user):
        return farms
    statement = apply_farm_scope(
        select(Farm.id).where(Farm.farmer_id == farmer.id), user
    )
    allowed = set(db.session.scalars(statement).all())
    return [farm for farm in farms if farm.id in allowed]


def list_all_farmers(user=None):
    return db.session.scalars(
        apply_farmer_scope(select(Farmer).order_by(Farmer.id), user)
    ).all()


def get_farmer_by_id(farmer_id: int, user=None):
    return db.session.scalar(
        apply_farmer_scope(select(Farmer).where(Farmer.id == farmer_id), user)
    )


def persist_new_farmer(farmer: Farmer) -> dict:
    db.session.add(farmer)
    db.session.flush()
    summary = _farmer_summary(farmer)
    db.session.commit()
    return summary


def commit_farmer_changes() -> None:
    db.session.commit()


def _precheck_text_fields(payload: dict) -> str | None:
    for field, limit in _MAX_INPUT_LENGTHS.items():
        if field not in payload:
            continue
        value = payload[field]
        if field == "contact_number" and value in (None, ""):
            continue
        if not isinstance(value, str) or not value or len(value) > limit:
            return "Invalid farmer data."
    return None


@farmers_bp.after_request
def _no_store_farmers_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@farmers_bp.get("")
@farmers_bp.get("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_farmers():
    try:
        farmers = list_all_farmers()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farmer list failed.")
        return auth_error("Farmer service unavailable.", 503)
    return jsonify(
        {
            "data": {
                "farmers": [
                    _farmer_summary(
                        farmer, visible_farms_for_farmer(farmer, g.current_user)
                    )
                    for farmer in farmers
                ]
            },
            "message": "Farmers retrieved.",
        }
    )


@farmers_bp.get("/<int:farmer_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_farmer(farmer_id: int):
    try:
        farmer = get_farmer_by_id(farmer_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farmer lookup failed.")
        return auth_error("Farmer service unavailable.", 503)
    if farmer is None:
        return auth_error("Farmer not found.", 404)
    return jsonify(
        {
            "data": {
                "farmer": _farmer_detail(
                    farmer, visible_farms_for_farmer(farmer, g.current_user)
                )
            },
            "message": "Farmer retrieved.",
        }
    )


@farmers_bp.post("")
@farmers_bp.post("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def create_farmer():
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid farmer data.", 400)

    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not _CREATE_REQUIRED.issubset(set(payload))
        or not set(payload).issubset(_CREATE_ALLOWED)
    ):
        return auth_error("Invalid farmer data.", 400)

    invalid = _precheck_text_fields(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        farmer = Farmer(
            full_name=payload["full_name"],
            barangay=payload["barangay"],
            contact_number=payload.get("contact_number"),
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        summary = persist_new_farmer(farmer)
    except IntegrityError:
        db.session.rollback()
        current_app.logger.error("Farmer creation integrity failure.")
        return auth_error("Farmer service unavailable.", 503)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farmer creation failed.")
        return auth_error("Farmer service unavailable.", 503)

    response = jsonify({"data": {"farmer": summary}, "message": "Farmer created."})
    response.status_code = 201
    return response


@farmers_bp.put("/<int:farmer_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def update_farmer(farmer_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid farmer data.", 400)

    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not payload
        or not set(payload).issubset(_UPDATE_ALLOWED)
    ):
        return auth_error("Invalid farmer data.", 400)

    invalid = _precheck_text_fields(payload)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        farmer = get_farmer_by_id(farmer_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farmer lookup failed.")
        return auth_error("Farmer service unavailable.", 503)
    if farmer is None:
        return auth_error("Farmer not found.", 404)

    try:
        if "full_name" in payload:
            farmer.full_name = payload["full_name"]
        if "barangay" in payload:
            farmer.barangay = payload["barangay"]
        if "contact_number" in payload:
            farmer.contact_number = payload["contact_number"]
    except ValueError as exc:
        db.session.rollback()
        return auth_error(str(exc), 400)

    try:
        detail = _farmer_detail(
            farmer, visible_farms_for_farmer(farmer, g.current_user)
        )
        commit_farmer_changes()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farmer update failed.")
        return auth_error("Farmer service unavailable.", 503)

    return jsonify({"data": {"farmer": detail}, "message": "Farmer updated."})
