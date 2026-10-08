from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import auth as auth_service
from app.auth import auth_error, login_required, roles_required
from app.extensions import db
from app.models import User, UserRole, normalize_username

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1/admin")

# Transaction-scoped advisory lock serializing admin status changes so two
# concurrent deactivations cannot remove the last active ADMIN. Distinct from
# the CLI bootstrap lock (75240201) used by `flask create-admin`.
ADMIN_STATUS_ADVISORY_LOCK_KEY = 75240202

_CREATE_FIELDS = frozenset({"username", "full_name", "password", "role"})
_STATUS_FIELDS = frozenset({"is_active"})
_ALLOWED_ROLES = frozenset({UserRole.ADMIN.value, UserRole.TECHNICIAN.value})


def _admin_public_user(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": bool(user.is_active),
    }


def acquire_admin_status_lock() -> None:
    db.session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADMIN_STATUS_ADVISORY_LOCK_KEY}
    )


def list_all_users():
    return db.session.scalars(select(User).order_by(User.id)).all()


def username_taken(username: str) -> bool:
    return (
        db.session.scalar(select(User.id).where(User.username == username).limit(1))
        is not None
    )


def count_active_admins() -> int:
    return int(
        db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
        or 0
    )


def persist_new_user(user: User) -> dict:
    db.session.add(user)
    db.session.flush()
    public_user = _admin_public_user(user)
    db.session.commit()
    return public_user


def commit_status_change() -> None:
    db.session.commit()


@admin_bp.after_request
def _no_store_admin_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@admin_bp.get("/users")
@login_required
@roles_required("ADMIN")
def list_users():
    try:
        users = list_all_users()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Admin user list failed.")
        return auth_error("Administrator service unavailable.", 503)
    return jsonify(
        {
            "data": {"users": [_admin_public_user(user) for user in users]},
            "message": "Staff accounts retrieved.",
        }
    )


@admin_bp.post("/users")
@login_required
@roles_required("ADMIN")
def create_user():
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid user data.", 400)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != _CREATE_FIELDS:
        return auth_error("Invalid user data.", 400)

    username_input = payload["username"]
    full_name_input = payload["full_name"]
    password = payload["password"]
    role_input = payload["role"]

    if (
        not isinstance(username_input, str)
        or not username_input
        or len(username_input) > 128
        or not isinstance(full_name_input, str)
        or not full_name_input
        or len(full_name_input) > 500
        or not isinstance(password, str)
        or not password
        or len(password) > 1024
        or not isinstance(role_input, str)
    ):
        return auth_error("Invalid user data.", 400)
    if role_input not in _ALLOWED_ROLES:
        return auth_error("Invalid user data.", 400)

    try:
        username = normalize_username(username_input)
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        if username_taken(username):
            return auth_error("Username already exists.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Admin username check failed.")
        return auth_error("Administrator service unavailable.", 503)

    try:
        user = User(
            username=username,
            full_name=full_name_input,
            role=role_input,
            is_active=True,
        )
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        user.set_password(password)
    except ValueError as exc:
        return auth_error(str(exc), 400)

    try:
        public_user = persist_new_user(user)
    except IntegrityError:
        db.session.rollback()
        return auth_error("Username already exists.", 409)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Admin user creation failed.")
        return auth_error("Administrator service unavailable.", 503)

    response = jsonify(
        {"data": {"user": public_user}, "message": "Staff account created."}
    )
    response.status_code = 201
    return response


@admin_bp.patch("/users/<int:user_id>/status")
@login_required
@roles_required("ADMIN")
def update_user_status(user_id: int):
    if not request.is_json or (
        request.content_length is not None and request.content_length > 1024
    ):
        return auth_error("Invalid status update.", 400)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != _STATUS_FIELDS:
        return auth_error("Invalid status update.", 400)

    is_active = payload["is_active"]
    if type(is_active) is not bool:
        return auth_error("Invalid status update.", 400)

    try:
        target = auth_service.get_user_by_id(user_id)
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Admin user lookup failed.")
        return auth_error("Administrator service unavailable.", 503)

    if target is None:
        return auth_error("User not found.", 404)

    if bool(target.is_active) is is_active:
        return jsonify(
            {"data": {"user": _admin_public_user(target)}, "message": "Account status updated."}
        )

    if is_active:
        target.is_active = True
        try:
            public_user = _admin_public_user(target)
            commit_status_change()
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error("Admin user activation failed.")
            return auth_error("Administrator service unavailable.", 503)
        return jsonify(
            {"data": {"user": public_user}, "message": "Account status updated."}
        )

    # Deactivation path.
    if target.id == g.current_user.id:
        return auth_error("You cannot deactivate your own account.", 403)

    try:
        acquire_admin_status_lock()
        if target.role == UserRole.ADMIN and bool(target.is_active):
            remaining = count_active_admins()
            if remaining <= 1:
                db.session.rollback()
                return auth_error(
                    "Cannot deactivate the last active administrator.", 409
                )
        target.is_active = False
        target.auth_version = int(target.auth_version) + 1
        public_user = _admin_public_user(target)
        commit_status_change()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error("Admin user deactivation failed.")
        return auth_error("Administrator service unavailable.", 503)

    return jsonify(
        {"data": {"user": public_user}, "message": "Account status updated."}
    )
