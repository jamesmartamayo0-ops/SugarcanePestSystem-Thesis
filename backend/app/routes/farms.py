from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import Farm, Farmer
from app.scoping import apply_farm_scope

farms_bp = Blueprint("farms", __name__, url_prefix="/api/v1/farms")

_CREATE_REQUIRED = frozenset({"farmer_id", "plot_identifier", "barangay", "area_hectares"})
_CREATE_ALLOWED = _CREATE_REQUIRED | {"latitude", "longitude"}
_UPDATE_ALLOWED = frozenset(
    {"plot_identifier", "barangay", "area_hectares", "latitude", "longitude"}
)
_MAX_INPUT_LENGTHS = {"plot_identifier": 500, "barangay": 500}


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return None


def _farmer_reference(farmer: Farmer) -> dict:
    return {"id": farmer.id, "full_name": farmer.full_name, "barangay": farmer.barangay}


def _farm_public(farm: Farm) -> dict:
    return {
        "id": farm.id,
        "farmer_id": farm.farmer_id,
        "plot_identifier": farm.plot_identifier,
        "barangay": farm.barangay,
        "area_hectares": float(farm.area_hectares),
        "latitude": float(farm.latitude) if farm.latitude is not None else None,
        "longitude": float(farm.longitude) if farm.longitude is not None else None,
        "farmer": _farmer_reference(farm.farmer),
        "created_at": _iso(farm.created_at),
        "updated_at": _iso(farm.updated_at),
    }


def list_all_farms(farmer_id: int | None = None, user=None):
    statement = apply_farm_scope(select(Farm).order_by(Farm.id), user)
    if farmer_id is not None:
        statement = statement.where(Farm.farmer_id == farmer_id)
    return db.session.scalars(statement).all()


def get_farm_by_id(farm_id: int, user=None):
    return db.session.scalar(
        apply_farm_scope(select(Farm).where(Farm.id == farm_id), user)
    )


def get_farmer_by_id(farmer_id: int):
    return db.session.get(Farmer, farmer_id)


def plot_taken(farmer_id: int, plot_identifier: str, exclude_id: int | None = None) -> bool:
    statement = select(Farm.id).where(
        Farm.farmer_id == farmer_id, Farm.plot_identifier == plot_identifier
    )
    if exclude_id is not None:
        statement = statement.where(Farm.id != exclude_id)
    return db.session.scalar(statement.limit(1)) is not None


def persist_new_farm(farm: Farm) -> dict:
    db.session.add(farm)
    db.session.flush()
    public_farm = _farm_public(farm)
    db.session.commit()
    return public_farm


def commit_farm_changes() -> None:
    db.session.commit()


@farms_bp.after_request
def _no_store_farms_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@farms_bp.get("")
@farms_bp.get("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def list_farms():
    raw_farmer_id = request.args.get("farmer_id")
    farmer_id: int | None = None
    if raw_farmer_id is not None and raw_farmer_id != "":
        try:
            farmer_id = int(raw_farmer_id)
        except (TypeError, ValueError):
            return auth_error("Invalid farm filter.", 400)
        if not 0 < farmer_id <= 2_147_483_647:
            return auth_error("Invalid farm filter.", 400)
    try:
        farms = list_all_farms(farmer_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm list failed.")
        return auth_error("Farm service unavailable.", 503)
    return jsonify(
        {
            "data": {"farms": [_farm_public(farm) for farm in farms]},
            "message": "Farms retrieved.",
        }
    )


@farms_bp.get("/<int:farm_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def get_farm(farm_id: int):
    try:
        farm = get_farm_by_id(farm_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm lookup failed.")
        return auth_error("Farm service unavailable.", 503)
    if farm is None:
        return auth_error("Farm not found.", 404)
    return jsonify({"data": {"farm": _farm_public(farm)}, "message": "Farm retrieved."})


def _precheck_farm_payload(payload: dict, *, is_create: bool) -> str | None:
    if is_create and "farmer_id" in payload:
        farmer_id = payload["farmer_id"]
        if type(farmer_id) is not int or not 0 < farmer_id <= 2_147_483_647:
            return "Invalid farm data."
    for field, limit in _MAX_INPUT_LENGTHS.items():
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str) or not value or len(value) > limit:
            return "Invalid farm data."
    if "area_hectares" in payload:
        area = payload["area_hectares"]
        if isinstance(area, bool):
            return "Invalid farm data."
        if isinstance(area, (int, float)):
            if not isinstance(area, int) and (area != area or area in (float("inf"), float("-inf"))):
                return "Invalid farm data."
        elif isinstance(area, str):
            if not area.strip() or len(area) > 32:
                return "Invalid farm data."
        else:
            return "Invalid farm data."
    coordinate_fields = {"latitude", "longitude"} & set(payload)
    if coordinate_fields and coordinate_fields != {"latitude", "longitude"}:
        return "Latitude and longitude must be provided together."
    if coordinate_fields and ((payload["latitude"] is None) != (payload["longitude"] is None)):
        return "Latitude and longitude must both be null or both contain values."
    return None


@farms_bp.post("")
@farms_bp.post("/")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def create_farm():
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid farm data.", 400)

    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not _CREATE_REQUIRED.issubset(payload)
        or not set(payload).issubset(_CREATE_ALLOWED)
    ):
        return auth_error("Invalid farm data.", 400)

    invalid = _precheck_farm_payload(payload, is_create=True)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        farmer = get_farmer_by_id(payload["farmer_id"])
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm farmer lookup failed.")
        return auth_error("Farm service unavailable.", 503)
    if farmer is None:
        return auth_error("Farmer not found.", 404)

    try:
        if plot_taken(payload["farmer_id"], payload["plot_identifier"].strip()):
            return auth_error("Farm plot already exists for this farmer.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm duplicate check failed.")
        return auth_error("Farm service unavailable.", 503)

    try:
        farm = Farm(
            farmer_id=payload["farmer_id"],
            plot_identifier=payload["plot_identifier"],
            barangay=payload["barangay"],
            area_hectares=payload["area_hectares"],
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        public_farm = persist_new_farm(farm)
    except IntegrityError:
        db.session.rollback()
        return auth_error("Farm plot already exists for this farmer.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm creation failed.")
        return auth_error("Farm service unavailable.", 503)

    response = jsonify({"data": {"farm": public_farm}, "message": "Farm created."})
    response.status_code = 201
    return response


@farms_bp.put("/<int:farm_id>")
@login_required
@roles_required("ADMIN", "TECHNICIAN")
def update_farm(farm_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid farm data.", 400)

    payload = request.get_json(silent=True)
    if (
        not isinstance(payload, dict)
        or not payload
        or not set(payload).issubset(_UPDATE_ALLOWED)
    ):
        return auth_error("Invalid farm data.", 400)

    invalid = _precheck_farm_payload(payload, is_create=False)
    if invalid is not None:
        return auth_error(invalid, 400)

    try:
        farm = get_farm_by_id(farm_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm lookup failed.")
        return auth_error("Farm service unavailable.", 503)
    if farm is None:
        return auth_error("Farm not found.", 404)

    if "plot_identifier" in payload:
        try:
            if plot_taken(farm.farmer_id, payload["plot_identifier"].strip(), exclude_id=farm.id):
                return auth_error("Farm plot already exists for this farmer.", 409)
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error("Farm duplicate check failed.")
            return auth_error("Farm service unavailable.", 503)

    try:
        if "plot_identifier" in payload:
            farm.plot_identifier = payload["plot_identifier"]
        if "barangay" in payload:
            farm.barangay = payload["barangay"]
        if "area_hectares" in payload:
            farm.area_hectares = payload["area_hectares"]
        if "latitude" in payload:
            farm.latitude = payload["latitude"]
            farm.longitude = payload["longitude"]
    except ValueError as exc:
        db.session.rollback()
        return auth_error(str(exc), 400)

    try:
        public_farm = _farm_public(farm)
        commit_farm_changes()
    except IntegrityError:
        db.session.rollback()
        return auth_error("Farm plot already exists for this farmer.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Farm update failed.")
        return auth_error("Farm service unavailable.", 503)

    return jsonify({"data": {"farm": public_farm}, "message": "Farm updated."})
