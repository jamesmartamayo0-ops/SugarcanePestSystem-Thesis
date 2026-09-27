import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from sqlalchemy.engine import URL


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def configure_app(app: Flask) -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    password = os.getenv("DB_PASSWORD") or None
    app.config.from_object(Config)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    app.config["DB_PASSWORD_CONFIGURED"] = password is not None
    app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
        "postgresql+psycopg",
        username=os.getenv("DB_USER", "sugarcane_app"),
        password=password,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5434")),
        database=os.getenv("DB_NAME", "sugarcane_pest_db"),
    )
