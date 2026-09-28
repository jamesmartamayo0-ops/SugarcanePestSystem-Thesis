import secrets
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request, session
from sqlalchemy.exc import SQLAlchemyError

from app import auth as auth_service
from app.auth import auth_error, login_required
from app.models import normalize_username


auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")
_INVALID_CREDENTIALS = "Invalid username or password."


def _public_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
    }


@auth_bp.post("/login")
def login():
    if not request.is_json or (
        request.content_length is not None and request.content_length > 4096
    ):
        return auth_error("Invalid login request.", 400)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"username", "password"}:
        return auth_error("Invalid login request.", 400)

    username_input = payload["username"]
    password = payload["password"]
    if (
        not isinstance(username_input, str)
        or not isinstance(password, str)
        or not username_input
        or not password
        or len(username_input) > 128
        or len(password) > 1024
    ):
        return auth_error("Invalid login request.", 400)

    try:
        username = normalize_username(username_input)
    except ValueError:
        return auth_error("Invalid login request.", 400)

    try:
        user = auth_service.get_user_by_username(username)
    except SQLAlchemyError:
        current_app.logger.error("Login user lookup failed.")
        return auth_error("Authentication service unavailable.", 503)

    if user is None:
        auth_service.check_unknown_password(password)
        return auth_error(_INVALID_CREDENTIALS, 401)
    if not user.check_password(password) or not user.is_active:
        return auth_error(_INVALID_CREDENTIALS, 401)

    # Capture all public/session values before commit; after save_last_login
    # SQLAlchemy may expire the user and trigger an unsanitized refresh.
    user_id = user.id
    auth_version = user.auth_version
    public_user = _public_user(user)

    try:
        auth_service.save_last_login(user, datetime.now(timezone.utc))
    except SQLAlchemyError:
        current_app.logger.error("Login timestamp update failed.")
        return auth_error("Authentication service unavailable.", 503)

    session.clear()
    session["user_id"] = user_id
    session["auth_version"] = auth_version
    session["issued_at"] = auth_service.now_epoch_seconds()
    session["csrf_token"] = secrets.token_hex(32)
    session.permanent = True

    return jsonify({
        "data": {"user": public_user, "csrf_token": session["csrf_token"]},
        "message": "Login successful.",
    })


@auth_bp.get("/me")
@login_required
def me():
    return jsonify({
        "data": {"user": _public_user(g.current_user), "csrf_token": session["csrf_token"]},
        "message": "Authenticated.",
    })


@auth_bp.post("/logout")
@login_required
def logout():
    session.clear()
    return "", 204
