import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.engine import URL

from app.evidence import validate_storage_mode


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_NAME = "sugarcane_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_PATH = "/"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = False
    AUTH_TRUSTED_ORIGINS = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    CORS_ORIGINS = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def validate_secret_key(value: str | None) -> str:
    if not value or not value.strip():
        raise ValueError("A strong SECRET_KEY must be configured.")

    normalized = "".join(character for character in value.lower() if character.isalnum())
    placeholder_markers = ("changeme", "replaceme", "placeholder", "example", "yoursecret", "secretkey")
    if any(marker in normalized for marker in placeholder_markers):
        raise ValueError("A strong SECRET_KEY must be configured.")
    return value


def session_cookie_secure_from_env(value: str | None) -> bool:
    if value is None:
        return False
    if value.strip().lower() == "true":
        return True
    if value.strip().lower() == "false":
        return False
    raise ValueError("SESSION_COOKIE_SECURE must be true or false.")


def parse_trusted_origins(value: str | None) -> tuple[str, ...]:
    if value is None:
        return Config.AUTH_TRUSTED_ORIGINS

    origins = tuple(origin.strip() for origin in value.split(","))
    if not origins or any(not origin for origin in origins):
        raise ValueError("AUTH_TRUSTED_ORIGINS must contain valid origins.")
    for origin in origins:
        try:
            parsed = urlsplit(origin)
            parsed.port  # Access validates an optional numeric port.
            valid = (
                parsed.scheme in {"http", "https"}
                and parsed.hostname is not None
                and parsed.username is None
                and parsed.password is None
                and not parsed.path
                and not parsed.query
                and not parsed.fragment
                and "*" not in origin
                and origin == f"{parsed.scheme}://{parsed.netloc}"
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("AUTH_TRUSTED_ORIGINS must contain valid origins.")
    return origins


def configure_app(app: Flask) -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    password = os.getenv("DB_PASSWORD") or None
    app.config.from_object(Config)
    app.config["AUTH_TRUSTED_ORIGINS"] = parse_trusted_origins(
        os.getenv("AUTH_TRUSTED_ORIGINS")
    )
    app.config["SECRET_KEY"] = validate_secret_key(os.getenv("SECRET_KEY"))
    app.config["SESSION_COOKIE_SECURE"] = session_cookie_secure_from_env(
        os.getenv("SESSION_COOKIE_SECURE")
    )
    app.config["DB_PASSWORD_CONFIGURED"] = password is not None
    app.config["EVIDENCE_UPLOAD_DIR"] = os.getenv("EVIDENCE_UPLOAD_DIR") or str(
        Path(app.instance_path) / "pest-evidence"
    )
    app.config["EVIDENCE_STORAGE"] = validate_storage_mode(
        os.getenv("EVIDENCE_STORAGE")
    )
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER", "sugarcane_app"),
        password=password,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5434")),
        database=os.getenv("DB_NAME", "sugarcane_pest_db"),
    )
