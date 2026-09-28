import hmac
import re
import time
from functools import lru_cache, wraps

from flask import current_app, g, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import User


UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_CSRF_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def now_epoch_seconds() -> int:
    return int(time.time())


def get_user_by_id(user_id: int) -> User | None:
    return db.session.get(User, user_id)


def get_user_by_username(username: str) -> User | None:
    return db.session.scalar(select(User).where(User.username == username))


def save_last_login(user: User, timestamp) -> None:
    user.last_login_at = timestamp
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    # One process-local dummy hash keeps unknown-user checks from skipping scrypt.
    return generate_password_hash("not-a-real-account-password")


def check_unknown_password(password: str) -> None:
    check_password_hash(_dummy_password_hash(), password)


def auth_error(message: str, status: int):
    response = jsonify({"data": None, "message": message})
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def trusted_origin() -> bool:
    origin = request.headers.get("Origin")
    return origin is not None and origin in current_app.config["AUTH_TRUSTED_ORIGINS"]


def valid_csrf_token() -> bool:
    supplied = request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token")
    return (
        isinstance(supplied, str)
        and isinstance(expected, str)
        and _CSRF_PATTERN.fullmatch(supplied) is not None
        and _CSRF_PATTERN.fullmatch(expected) is not None
        and hmac.compare_digest(supplied, expected)
    )


def load_current_user():
    g.current_user = None
    if "user_id" not in session:
        if any(key in session for key in ("auth_version", "issued_at", "csrf_token")):
            session.clear()
        return None
    user_id = session["user_id"]

    auth_version = session.get("auth_version")
    issued_at = session.get("issued_at")
    csrf_token = session.get("csrf_token")
    now = now_epoch_seconds()
    lifetime = int(current_app.permanent_session_lifetime.total_seconds())
    valid_state = (
        type(user_id) is int
        and 0 < user_id <= 2_147_483_647
        and type(auth_version) is int
        and auth_version >= 0
        and type(issued_at) is int
        and 0 <= now - issued_at <= lifetime
        and isinstance(csrf_token, str)
        and _CSRF_PATTERN.fullmatch(csrf_token) is not None
    )
    if not valid_state:
        session.clear()
        return None

    try:
        user = get_user_by_id(user_id)
    except SQLAlchemyError:
        current_app.logger.error("Current user lookup failed.")
        return auth_error("Authentication service unavailable.", 503)

    if user is None or not user.is_active or user.auth_version != auth_version:
        session.clear()
        return None

    g.current_user = user
    return None


def enforce_unsafe_request():
    if request.method not in UNSAFE_METHODS:
        return None
    if request.endpoint == "auth.login":
        if not trusted_origin():
            return auth_error("Request origin is not allowed.", 403)
        return None
    if g.current_user is None:
        return None
    if not trusted_origin():
        return auth_error("Request origin is not allowed.", 403)
    if not valid_csrf_token():
        return auth_error("CSRF validation failed.", 403)
    return None


def no_store_auth_response(response):
    if request.path.startswith("/api/v1/auth/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.current_user is None:
            return auth_error("Authentication required.", 401)
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles: str):
    if not roles:
        raise ValueError("At least one role is required.")

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.current_user is None:
                return auth_error("Authentication required.", 401)
            if g.current_user.role not in roles:
                return auth_error("Permission denied.", 403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
